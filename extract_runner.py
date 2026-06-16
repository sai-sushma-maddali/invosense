"""Bridge to extraction_code — run vision extraction on saved invoice images."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
EXTRACTION_ROOT = ROOT_DIR / "extraction_code"
EXTRACTIONS_DIR = ROOT_DIR / "data" / "extractions"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff"}

_extraction_imported = False


def _ensure_extraction_import() -> None:
    global _extraction_imported
    if _extraction_imported:
        return
    if not EXTRACTION_ROOT.is_dir():
        raise RuntimeError(f"extraction_code folder not found at {EXTRACTION_ROOT}")
    root = str(EXTRACTION_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    _extraction_imported = True


def _with_boxes_enabled() -> bool:
    return os.getenv("EXTRACT_WITH_BOXES", "true").lower() == "true"


def _raw_json_from_extraction(existing: dict[str, Any]) -> dict[str, Any]:
    """Build vision-model-shaped JSON from a saved extraction (skip LLM on refresh)."""
    return {
        "company": existing.get("company"),
        "gst_id": existing.get("gst_id"),
        "invoice_no": existing.get("invoice_no"),
        "date": existing.get("date"),
        "taxable": existing.get("taxable"),
        "tax": existing.get("tax"),
        "total": existing.get("total"),
        "confidence": existing.get("confidence"),
    }


def refresh_extraction_boxes(invoice_id: str, saved_path: str, existing: dict[str, Any]) -> dict[str, Any]:
    """Re-run pytesseract box matching without calling the vision LLM again."""
    _ensure_extraction_import()
    from extraction import run as extract_run  # noqa: WPS433

    image_path = ROOT_DIR / saved_path
    if not image_path.is_file():
        raise FileNotFoundError(f"Saved attachment not found: {image_path}")

    image_bytes = image_path.read_bytes()
    with_boxes = _with_boxes_enabled()
    logger.info(
        "Refreshing extraction boxes invoice_id=%s file=%s with_boxes=%s",
        invoice_id,
        saved_path,
        with_boxes,
    )
    result = extract_run(
        image_bytes,
        invoice_id=invoice_id,
        with_boxes=with_boxes,
        raw_json=_raw_json_from_extraction(existing),
    )
    payload = result.model_dump()

    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = EXTRACTIONS_DIR / f"{invoice_id}.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Extraction boxes refreshed invoice_id=%s path=%s", invoice_id, out_file)
    return payload


def run_extraction(invoice_id: str, saved_path: str) -> dict[str, Any]:
    """Run extraction on a saved inbox file and return Contract 1 JSON."""
    _ensure_extraction_import()
    from extraction import run as extract_run  # noqa: WPS433

    image_path = ROOT_DIR / saved_path
    if not image_path.is_file():
        raise FileNotFoundError(f"Saved attachment not found: {image_path}")

    suffix = image_path.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError(f"Extraction supports images only; got {suffix}")

    image_bytes = image_path.read_bytes()
    with_boxes = _with_boxes_enabled()
    logger.info(
        "Running extraction invoice_id=%s file=%s with_boxes=%s",
        invoice_id,
        saved_path,
        with_boxes,
    )
    result = extract_run(image_bytes, invoice_id=invoice_id, with_boxes=with_boxes)
    payload = result.model_dump()

    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = EXTRACTIONS_DIR / f"{invoice_id}.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Extraction saved invoice_id=%s path=%s", invoice_id, out_file)
    return payload
