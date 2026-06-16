"""In-memory invoice ingest + extraction state."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

Source = Literal["gmail", "upload", "folder"]
InvoiceStatus = Literal[
    "saved", "extracting", "compliance_checking", "completed", "failed"
]
DecisionOutcome = Literal["auto_approve", "rejected"]


@dataclass
class InvoiceRecord:
    invoice_id: str
    source: Source
    filename: str
    saved_path: str
    status: InvoiceStatus
    created_at: str
    updated_at: str
    message_id: str | None = None
    extraction: dict[str, Any] | None = None
    extraction_path: str | None = None
    compliance: dict[str, Any] | None = None
    compliance_path: str | None = None
    decision: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "invoice_id": self.invoice_id,
            "source": self.source,
            "filename": self.filename,
            "saved_path": self.saved_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_id": self.message_id,
        }
        if self.extraction is not None:
            data["extraction"] = self.extraction
        if self.extraction_path is not None:
            data["extraction_path"] = self.extraction_path
        if self.compliance is not None:
            data["compliance"] = self.compliance
        if self.compliance_path is not None:
            data["compliance_path"] = self.compliance_path
        if self.decision is not None:
            data["decision"] = self.decision
        if self.error is not None:
            data["error"] = self.error
        return data


class InvoiceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, InvoiceRecord] = {}

    def create(
        self,
        invoice_id: str,
        source: Source,
        filename: str,
        saved_path: str,
        message_id: str | None = None,
    ) -> InvoiceRecord:
        now = _utc_now()
        record = InvoiceRecord(
            invoice_id=invoice_id,
            source=source,
            filename=filename,
            saved_path=saved_path,
            status="saved",
            created_at=now,
            updated_at=now,
            message_id=message_id,
        )
        with self._lock:
            self._records[invoice_id] = record
        return record

    def update(self, invoice_id: str, **fields: Any) -> InvoiceRecord | None:
        with self._lock:
            record = self._records.get(invoice_id)
            if not record:
                return None
            for key, value in fields.items():
                setattr(record, key, value)
            record.updated_at = _utc_now()
            return record

    def mark_failed(self, invoice_id: str, error: str) -> InvoiceRecord | None:
        return self.update(invoice_id, status="failed", error=error)

    def get(self, invoice_id: str) -> InvoiceRecord | None:
        with self._lock:
            return self._records.get(invoice_id)

    def list_all(self) -> list[InvoiceRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


store = InvoiceStore()
