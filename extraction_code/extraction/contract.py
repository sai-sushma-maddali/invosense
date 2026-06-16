"""Contract 1: the ``ExtractedInvoice`` data contract.

This is the only public output shape of the extraction module. It is kept
self-contained (no imports from sibling project modules) so the extraction
package can be used in isolation.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

#: Canonical extraction field order. Used by the prompt, confidence scoring and
#: the evaluation harness so everything stays in sync.
EXTRACTION_FIELDS: List[str] = [
    "company",
    "gst_id",
    "invoice_no",
    "date",
    "taxable",
    "tax",
    "total",
]


class ExtractedInvoice(BaseModel):
    """Structured result for a single invoice image.

    ``date`` is normalized to ``YYYY-MM-DD``. ``taxable``/``tax``/``total`` are
    floats (currency symbols and thousands separators stripped). ``confidence``
    holds a 0-1 score for every field in :data:`EXTRACTION_FIELDS`.
    """

    invoice_id: str

    company: Optional[str] = None
    gst_id: Optional[str] = None
    invoice_no: Optional[str] = None
    date: Optional[str] = None  # YYYY-MM-DD
    taxable: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

    confidence: Dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0

    #: Optional pixel boxes per field: {field: [x, y, w, h]}.
    boxes: Optional[Dict[str, List[int]]] = None

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.model_dump(), indent=indent, ensure_ascii=False)
