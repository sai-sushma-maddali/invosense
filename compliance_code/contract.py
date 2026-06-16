"""Contract shapes for the compliance module (Contract 1 input, Contract 2 output)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


@dataclass
class ExtractedInvoice:
    """Contract 1 — structured extraction result fed into compliance."""

    invoice_id: str
    company: Optional[str] = None
    gst_id: Optional[str] = None
    invoice_no: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD
    taxable: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedInvoice:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ComplianceResult:
    """Contract 2 — compliance outcome for one invoice."""

    invoice_id: str
    status: Literal["clean", "flagged"]
    flags: list[dict[str, Any]] = field(default_factory=list)
    vendor_verified: bool = True
    amount_verified: bool = True
    duplicate_check_passed: bool = True
    notes: str = ""

    @property
    def has_flags(self) -> bool:
        return bool(self.flags) or self.status == "flagged"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComplianceResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
