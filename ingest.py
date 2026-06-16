"""Save invoice attachments and run extraction in one flow."""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from compliance_runner import run_compliance_and_decide
from extract_runner import refresh_extraction_boxes, run_extraction
from storage import Source, store

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
INBOX_DIR = ROOT_DIR / "data" / "inbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)


def _relative_path(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def save_attachment(
    source_path: Path,
    source: Source,
    original_filename: str | None = None,
    message_id: str | None = None,
    *,
    run_extract: bool = True,
) -> str:
    """Copy attachment to inbox, optionally run extraction, return invoice_id."""
    invoice_id = str(uuid.uuid4())
    filename = original_filename or source_path.name
    dest = INBOX_DIR / f"{invoice_id}_{filename}"
    shutil.copy2(source_path, dest)
    saved_path = _relative_path(dest)

    store.create(
        invoice_id,
        source=source,
        filename=filename,
        saved_path=saved_path,
        message_id=message_id,
    )
    logger.info(
        "Saved attachment invoice_id=%s source=%s file=%s path=%s",
        invoice_id,
        source,
        filename,
        dest,
    )

    if run_extract:
        import threading

        threading.Thread(
            target=_extract_for_invoice,
            args=(invoice_id, saved_path),
            daemon=True,
            name=f"pipeline-{invoice_id[:8]}",
        ).start()

    return invoice_id


def bootstrap_inbox(on_pipeline: Callable[[str, str], None]) -> None:
    """Register inbox files from a prior run; skip ones already extracted on disk."""
    extractions_dir = ROOT_DIR / "data" / "extractions"
    compliance_dir = ROOT_DIR / "data" / "compliance"
    max_load = int(os.getenv("MAX_BOOTSTRAP_LOAD", "20"))

    pending: list[tuple[float, Path, str, str]] = []
    for path in sorted(INBOX_DIR.iterdir()):
        if not path.is_file():
            continue
        stem = path.stem
        if "_" not in stem:
            continue
        invoice_id, filename = stem.split("_", 1)
        if store.get(invoice_id):
            continue
        pending.append((path.stat().st_mtime, path, invoice_id, filename))

    pending.sort(key=lambda row: row[0], reverse=True)
    loaded = 0

    for _, path, invoice_id, filename in pending:
        saved_path = _relative_path(path)
        extraction_path = extractions_dir / f"{invoice_id}.json"
        compliance_path = compliance_dir / f"{invoice_id}.json"

        if extraction_path.is_file():
            if loaded >= max_load:
                continue
            loaded += 1
            import json

            extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
            compliance = (
                json.loads(compliance_path.read_text(encoding="utf-8"))
                if compliance_path.is_file()
                else None
            )
            decision = None
            if compliance:
                flags = compliance.get("flags") or []
                if flags:
                    decision = {
                        "invoice_id": invoice_id,
                        "decision": "rejected",
                        "reason": f"Compliance failed ({len(flags)} flag(s))",
                        "compliance_status": compliance.get("status", "flagged"),
                        "rejection_reasons": [
                            {
                                "check": f.get("check", "unknown"),
                                "reason": f.get("reason", "unknown"),
                                "message": f.get("message", ""),
                                "source": f.get("source"),
                            }
                            for f in flags
                        ],
                    }
                else:
                    decision = {
                        "invoice_id": invoice_id,
                        "decision": "auto_approve",
                        "reason": "Compliance clean and within policy limits",
                        "compliance_status": compliance.get("status", "clean"),
                        "rejection_reasons": [],
                    }

            store.create(
                invoice_id,
                source="folder",
                filename=filename,
                saved_path=saved_path,
            )
            store.update(
                invoice_id,
                status="completed" if compliance else "saved",
                extraction=extraction,
                extraction_path=_relative_path(extraction_path),
                compliance=compliance,
                compliance_path=_relative_path(compliance_path) if compliance else None,
                decision=decision,
            )
            logger.info("Loaded persisted invoice_id=%s from disk", invoice_id)
            continue

        store.create(
            invoice_id,
            source="folder",
            filename=filename,
            saved_path=saved_path,
        )
        logger.info("Bootstrapped inbox invoice_id=%s path=%s", invoice_id, saved_path)
        on_pipeline(invoice_id, saved_path)


def _extract_for_invoice(invoice_id: str, saved_path: str) -> None:
    store.update(invoice_id, status="extracting")
    try:
        extraction = run_extraction(invoice_id, saved_path)
        extraction_path = _relative_path(ROOT_DIR / "data" / "extractions" / f"{invoice_id}.json")
        store.update(
            invoice_id,
            extraction=extraction,
            extraction_path=extraction_path,
            error=None,
        )
        logger.info("Extraction completed invoice_id=%s", invoice_id)

        store.update(invoice_id, status="compliance_checking")
        compliance, decision = run_compliance_and_decide(extraction)
        compliance_path = _relative_path(ROOT_DIR / "data" / "compliance" / f"{invoice_id}.json")
        store.update(
            invoice_id,
            status="completed",
            compliance=compliance,
            compliance_path=compliance_path,
            decision=decision,
        )
        logger.info(
            "Pipeline completed invoice_id=%s decision=%s",
            invoice_id,
            decision.get("decision"),
        )
    except Exception as exc:
        logger.exception("Pipeline failed invoice_id=%s", invoice_id)
        store.mark_failed(invoice_id, str(exc))


def retry_extraction(invoice_id: str) -> None:
    """Re-run pytesseract box matching for an invoice that already has extraction."""
    record = store.get(invoice_id)
    if not record:
        raise ValueError(f"Invoice {invoice_id} not found")
    if not record.extraction:
        raise ValueError(f"Invoice {invoice_id} has no extraction to refresh")

    extraction = refresh_extraction_boxes(
        invoice_id,
        record.saved_path,
        record.extraction,
    )
    extraction_path = _relative_path(ROOT_DIR / "data" / "extractions" / f"{invoice_id}.json")
    store.update(
        invoice_id,
        extraction=extraction,
        extraction_path=extraction_path,
        error=None,
    )
    logger.info("Extraction boxes refreshed invoice_id=%s", invoice_id)


def _normalize_correction(field: str, value: object) -> object:
    """Coerce user-edited values to extraction contract types."""
    import sys

    extraction_root = str(ROOT_DIR / "extraction_code")
    if extraction_root not in sys.path:
        sys.path.insert(0, extraction_root)
    from extraction.normalize import normalize_amount, normalize_date, normalize_text

    if field in {"taxable", "tax", "total"}:
        if isinstance(value, (int, float)):
            return float(value)
        return normalize_amount(str(value))
    if field == "date":
        return normalize_date(str(value)) if value is not None else None
    if field in {"company", "gst_id", "invoice_no"}:
        return normalize_text(str(value)) if value is not None else None
    return value


def correct_extraction(
    invoice_id: str,
    updates: dict[str, object],
    *,
    refresh_boxes: bool = False,
) -> None:
    """Merge user corrections into extraction JSON and re-run compliance."""
    record = store.get(invoice_id)
    if not record:
        raise ValueError(f"Invoice {invoice_id} not found")
    if not record.extraction:
        raise ValueError(f"Invoice {invoice_id} has no extraction to correct")

    allowed = {"company", "gst_id", "invoice_no", "date", "taxable", "tax", "total"}
    extraction = dict(record.extraction)
    for field, raw in updates.items():
        if field not in allowed:
            continue
        extraction[field] = _normalize_correction(field, raw)

    # When tax/taxable change, keep total in sync unless user explicitly edited total.
    taxable = extraction.get("taxable")
    tax = extraction.get("tax")
    if taxable is not None and tax is not None and "total" not in updates:
        extraction["total"] = round(float(taxable) + float(tax), 2)

    correction_count = int(extraction.get("correction_count") or 0) + 1
    corrected_at = datetime.now(timezone.utc).isoformat()
    extraction["invoice_id"] = invoice_id
    extraction["corrected_at"] = corrected_at
    extraction["correction_count"] = correction_count

    if refresh_boxes:
        extraction = refresh_extraction_boxes(invoice_id, record.saved_path, extraction)
        extraction["corrected_at"] = corrected_at
        extraction["correction_count"] = correction_count

    extraction_path = ROOT_DIR / "data" / "extractions" / f"{invoice_id}.json"
    extraction_path.parent.mkdir(parents=True, exist_ok=True)
    extraction_path.write_text(
        json.dumps(extraction, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    store.update(
        invoice_id,
        status="compliance_checking",
        extraction=extraction,
        extraction_path=_relative_path(extraction_path),
        error=None,
    )

    try:
        compliance, decision = run_compliance_and_decide(extraction)
        compliance_path = _relative_path(ROOT_DIR / "data" / "compliance" / f"{invoice_id}.json")
        store.update(
            invoice_id,
            status="completed",
            compliance=compliance,
            compliance_path=compliance_path,
            decision=decision,
            error=None,
        )
        logger.info(
            "Correction completed invoice_id=%s decision=%s",
            invoice_id,
            decision.get("decision"),
        )
    except Exception as exc:
        logger.exception("Correction failed invoice_id=%s", invoice_id)
        store.mark_failed(invoice_id, str(exc))
        raise


def retry_compliance(invoice_id: str) -> None:
    """Re-run compliance + decision for a failed invoice that already has extraction."""
    record = store.get(invoice_id)
    if not record:
        raise ValueError(f"Invoice {invoice_id} not found")
    if not record.extraction:
        raise ValueError(f"Invoice {invoice_id} has no extraction to retry")

    store.update(invoice_id, status="compliance_checking", error=None)
    try:
        compliance, decision = run_compliance_and_decide(record.extraction)
        compliance_path = _relative_path(ROOT_DIR / "data" / "compliance" / f"{invoice_id}.json")
        store.update(
            invoice_id,
            status="completed",
            compliance=compliance,
            compliance_path=compliance_path,
            decision=decision,
            error=None,
        )
        logger.info(
            "Retry completed invoice_id=%s decision=%s",
            invoice_id,
            decision.get("decision"),
        )
    except Exception as exc:
        logger.exception("Retry failed invoice_id=%s", invoice_id)
        store.mark_failed(invoice_id, str(exc))
        raise
