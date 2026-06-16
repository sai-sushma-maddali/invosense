"""Run compliance on extraction output and persist Contract 2."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from approve import InvoiceDecision, decide
from compliance_code.contract import ExtractedInvoice
from compliance_code.run import run as compliance_run

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
COMPLIANCE_DIR = ROOT_DIR / "data" / "compliance"
COMPLIANCE_DIR.mkdir(parents=True, exist_ok=True)

_MAX_ATTEMPTS = 3


def _is_transient(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "timeout" in msg or "timed out" in msg or "connection" in msg


def run_compliance_and_decide(extraction: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Take extraction JSON (Contract 1), return (compliance dict, decision dict)."""
    last_err: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return _run_once(extraction)
        except Exception as exc:
            last_err = exc
            if _is_transient(exc) and attempt < _MAX_ATTEMPTS:
                wait = 2 ** attempt
                logger.warning(
                    "Compliance attempt %s/%s failed (transient), retrying in %ss: %s",
                    attempt,
                    _MAX_ATTEMPTS,
                    wait,
                    exc,
                )
                time.sleep(wait)
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("Compliance failed without exception")


def _run_once(extraction: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    invoice = ExtractedInvoice.from_dict(extraction)
    result = compliance_run(invoice)
    compliance_payload = result.to_dict()

    out_file = COMPLIANCE_DIR / f"{invoice.invoice_id}.json"
    out_file.write_text(json.dumps(compliance_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Compliance saved invoice_id=%s path=%s status=%s", invoice.invoice_id, out_file, result.status)

    decision = decide(invoice, result)
    decision_payload = decision.to_dict()
    logger.info(
        "Decision invoice_id=%s outcome=%s reason=%s",
        invoice.invoice_id,
        decision.decision,
        decision.reason,
    )
    return compliance_payload, decision_payload
