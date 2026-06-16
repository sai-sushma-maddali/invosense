"""Value normalization shared by extraction and evaluation.

Keeps date and amount coercion in one place so extracted values and ground
truth are compared on the same footing.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_AMOUNT_RE = re.compile(r"-?\d[\d,]*\.?\d*")

# Date formats seen in SROIE-style receipts plus the canonical output format.
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %y",
    "%Y/%m/%d",
]


def normalize_amount(value) -> Optional[float]:
    """Coerce ``"RM 1,234.50"`` / ``"1.234,50"`` style strings to a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = _AMOUNT_RE.search(s.replace(" ", ""))
    if not m:
        return None
    num = m.group(0).replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None


def normalize_date(value) -> Optional[str]:
    """Parse a wide range of date strings into ``YYYY-MM-DD``.

    Returns ``None`` if the value cannot be parsed as a real date.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Trim to a date-looking token if extra text is present.
    token = re.search(r"\d{1,4}[\-/.\s][\w]{1,9}[\-/.\s]\d{1,4}", s)
    candidate = token.group(0) if token else s
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def normalize_text(value) -> Optional[str]:
    """Collapse whitespace and strip; preserve original casing."""
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None
