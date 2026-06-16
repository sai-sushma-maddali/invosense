"""Per-field confidence scoring (0-1).

Confidence is derived from cheap, deterministic validation: format regexes,
date parseability, and the arithmetic identity ``total == taxable + tax``. If
the model reports its own certainty it is blended in.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from extraction.contract import EXTRACTION_FIELDS
from extraction.normalize import normalize_date

# Malaysian GST (12 digits) and SST-style ids; also a generic alnum fallback.
_GST_PATTERNS = [
    re.compile(r"^\d{12}$"),                         # GST: 000123456789
    re.compile(r"^[A-Z]\d{2}-\d{4}-\d{8}$"),         # SST: A01-1234-12345678
    re.compile(r"^[A-Z]?\d{8,15}$"),                 # generic tax id
]


def _present(value) -> bool:
    return value is not None and str(value).strip() != ""


def score_gst_id(value: Optional[str]) -> float:
    if not _present(value):
        return 0.0
    v = str(value).strip().upper().replace(" ", "")
    if any(p.match(v) for p in _GST_PATTERNS):
        return 1.0
    return 0.3  # present but malformed


def score_date(value: Optional[str]) -> float:
    if not _present(value):
        return 0.0
    return 1.0 if normalize_date(value) is not None else 0.2


def score_amounts(
    taxable: Optional[float], tax: Optional[float], total: Optional[float]
) -> Dict[str, float]:
    """Score the three monetary fields using the additive identity."""
    scores = {
        "taxable": 0.5 if taxable is not None else 0.0,
        "tax": 0.5 if tax is not None else 0.0,
        "total": 0.6 if total is not None else 0.0,
    }
    if taxable is not None and tax is not None and total is not None:
        if abs(total - (taxable + tax)) <= 0.01:
            scores["taxable"] = scores["tax"] = scores["total"] = 1.0
        else:
            # Numbers present but inconsistent -> moderate confidence.
            scores["taxable"] = scores["tax"] = scores["total"] = 0.4
    elif total is not None and taxable is None and tax is None:
        # Many receipts only print a total; that single value is still reliable.
        scores["total"] = 0.8
    return scores


def score_text(value: Optional[str], min_len: int = 2) -> float:
    if not _present(value):
        return 0.0
    s = str(value).strip()
    if len(s) < min_len:
        return 0.3
    return 0.9


def compute(
    data: Dict,
    model_certainty: Optional[float] = None,
) -> Dict[str, float]:
    """Compute a 0-1 confidence for every field in ``EXTRACTION_FIELDS``."""
    scores: Dict[str, float] = {}
    scores["company"] = score_text(data.get("company"), min_len=3)
    scores["gst_id"] = score_gst_id(data.get("gst_id"))
    scores["invoice_no"] = score_text(data.get("invoice_no"), min_len=1)
    scores["date"] = score_date(data.get("date"))
    scores.update(
        score_amounts(data.get("taxable"), data.get("tax"), data.get("total"))
    )

    if model_certainty is not None:
        mc = max(0.0, min(1.0, float(model_certainty)))
        # Average validation score with the model's self-reported certainty.
        scores = {k: round((v + mc) / 2, 4) for k, v in scores.items()}

    # Ensure every contract field has a score.
    for field in EXTRACTION_FIELDS:
        scores.setdefault(field, 0.0)
    return scores


def overall(scores: Dict[str, float]) -> float:
    if not scores:
        return 0.0
    vals = [scores[f] for f in EXTRACTION_FIELDS if f in scores]
    return round(sum(vals) / len(vals), 4) if vals else 0.0
