"""FastAPI entrypoint for the autonomous AP agent."""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from composio_gmail import get_gmail_connection_status, start_gmail_connection
from folder_watcher import FolderWatcher
from gmail_watcher import GmailWatcher
from ingest import bootstrap_inbox, correct_extraction, retry_compliance, retry_extraction, save_attachment
from ingest import _extract_for_invoice
from storage import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff"}
CITED_MD_PATH = Path(__file__).resolve().parent / "compliance_code" / "cited.md"

_gmail_watcher: GmailWatcher | None = None
_folder_watcher: FolderWatcher | None = None


class ExtractionCorrection(BaseModel):
    company: str | None = None
    gst_id: str | None = None
    invoice_no: str | None = None
    date: str | None = None
    taxable: float | None = None
    tax: float | None = None
    total: float | None = None
    refresh_boxes: bool = Field(default=False, description="Re-run OCR box matching after edit")


def _run_pipeline_async(invoice_id: str, saved_path: str) -> None:
    threading.Thread(
        target=_extract_for_invoice,
        args=(invoice_id, saved_path),
        daemon=True,
        name=f"pipeline-{invoice_id[:8]}",
    ).start()


def _save_from_path(
    path: Path,
    source: str,
    filename: str | None = None,
    message_id: str | None = None,
) -> None:
    invoice_id = save_attachment(
        path,
        source=source,  # type: ignore[arg-type]
        original_filename=filename,
        message_id=message_id,
        run_extract=False,
    )
    record = store.get(invoice_id)
    if record:
        _run_pipeline_async(invoice_id, record.saved_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _gmail_watcher, _folder_watcher

    bootstrap_inbox(_run_pipeline_async)

    def on_gmail_attachment(path: Path, filename: str, message_id: str) -> None:
        _save_from_path(path, "gmail", filename, message_id)

    def on_folder_file(path: Path) -> None:
        _save_from_path(path, "folder", path.name.replace(".processing", ""))

    _gmail_watcher = GmailWatcher(on_attachment=on_gmail_attachment)
    _gmail_watcher.start()

    _folder_watcher = FolderWatcher(on_file=on_folder_file)
    _folder_watcher.start()

    logger.info("AP agent pipeline ready")
    yield

    if _gmail_watcher:
        _gmail_watcher.stop()
    if _folder_watcher:
        _folder_watcher.stop()


app = FastAPI(
    title="InvoSense AP Agent",
    description="Gmail ingest → extract → compliance → decision",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    gmail_status = get_gmail_connection_status()
    return {
        "status": "ok",
        "gmail_watcher": bool(_gmail_watcher and _gmail_watcher.enabled),
        "gmail_connected": gmail_status.get("connected", False),
        "folder_watcher": True,
    }


@app.get("/connect/gmail")
def connect_gmail():
    try:
        return start_gmail_connection(open_browser=False)
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/connect/gmail/status")
def connect_gmail_status():
    return get_gmail_connection_status()


@app.get("/compliance/tax-rules")
def tax_rules_document():
    """Serve the cited tax-rules markdown referenced by compliance flags."""
    if CITED_MD_PATH.is_file():
        return FileResponse(CITED_MD_PATH, media_type="text/markdown; charset=utf-8")
    return PlainTextResponse("Tax rules document not found.", status_code=404)


@app.get("/invoices")
def list_invoices():
    records = store.list_all()
    return {
        "count": len(records),
        "invoices": [record.to_dict() for record in records],
    }


@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str):
    record = store.get(invoice_id)
    if not record:
        return {"error": "not_found", "invoice_id": invoice_id}
    return record.to_dict()


@app.post("/invoices/{invoice_id}/retry")
def retry_invoice(invoice_id: str, background_tasks: BackgroundTasks, reextract: bool = False):
    """Re-run pipeline (saved), refresh boxes (reextract), or compliance only."""
    record = store.get(invoice_id)
    if not record:
        return {"error": "not_found", "invoice_id": invoice_id}

    if reextract and record.extraction:
        try:
            retry_extraction(invoice_id)
        except Exception as exc:
            updated = store.get(invoice_id)
            payload = updated.to_dict() if updated else {"invoice_id": invoice_id}
            payload["error"] = str(exc)
            return payload
        updated = store.get(invoice_id)
        return updated.to_dict() if updated else {"error": "retry_failed", "invoice_id": invoice_id}

    if record.status in {"saved", "failed"} and not record.extraction:
        background_tasks.add_task(_extract_for_invoice, invoice_id, record.saved_path)
        return {"status": "accepted", "invoice_id": invoice_id, "action": "pipeline"}

    if not record.extraction:
        return {"error": "no_extraction", "invoice_id": invoice_id}

    try:
        retry_compliance(invoice_id)
    except Exception as exc:
        updated = store.get(invoice_id)
        payload = updated.to_dict() if updated else {"invoice_id": invoice_id}
        payload["error"] = str(exc)
        return payload

    updated = store.get(invoice_id)
    return updated.to_dict() if updated else {"error": "retry_failed", "invoice_id": invoice_id}


@app.patch("/invoices/{invoice_id}/extraction")
def patch_invoice_extraction(invoice_id: str, body: ExtractionCorrection):
    """Apply user corrections to extracted fields and re-run compliance."""
    record = store.get(invoice_id)
    if not record:
        return {"error": "not_found", "invoice_id": invoice_id}
    if not record.extraction:
        return {"error": "no_extraction", "invoice_id": invoice_id}

    updates = body.model_dump(exclude={"refresh_boxes"}, exclude_none=True)
    if not updates:
        return {"error": "no_fields", "invoice_id": invoice_id, "message": "No fields to update"}

    try:
        correct_extraction(
            invoice_id,
            updates,
            refresh_boxes=body.refresh_boxes,
        )
    except Exception as exc:
        updated = store.get(invoice_id)
        payload = updated.to_dict() if updated else {"invoice_id": invoice_id}
        payload["error"] = str(exc)
        return payload

    updated = store.get(invoice_id)
    return updated.to_dict() if updated else {"error": "correction_failed", "invoice_id": invoice_id}


@app.post("/upload")
async def upload_invoice(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    suffix = Path(file.filename or "invoice.pdf").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {
            "error": "unsupported_file_type",
            "allowed": sorted(ALLOWED_EXTENSIONS),
        }

    contents = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="upload_")
    tmp.write(contents)
    tmp.close()
    tmp_path = Path(tmp.name)

    def _process() -> None:
        try:
            invoice_id = save_attachment(
                tmp_path,
                source="upload",
                original_filename=file.filename,
                run_extract=False,
            )
            record = store.get(invoice_id)
            if record:
                _run_pipeline_async(invoice_id, record.saved_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    background_tasks.add_task(_process)

    return {
        "status": "accepted",
        "message": "Invoice queued for processing",
        "filename": file.filename,
    }
