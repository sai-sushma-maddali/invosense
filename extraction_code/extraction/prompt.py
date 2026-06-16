"""Vision prompt and safe JSON parsing for invoice extraction."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

SYSTEM_PROMPT = (
    "You are an precise invoice data extractor. You read a single invoice or "
    "receipt image and return ONLY a JSON object. Do not add explanations, "
    "markdown, or code fences."
)

USER_PROMPT = """Extract these fields from the invoice image and return ONLY a JSON object with exactly these keys:

- "company": the seller/merchant legal name (string)
- "gst_id": the GST / SST / tax registration id printed on the invoice (string)
- "invoice_no": the invoice or receipt number (string)
- "date": the invoice date in strict YYYY-MM-DD format (string)
- "taxable": the subtotal amount BEFORE tax, as a plain number (no currency symbol, no thousands separators)
- "tax": the tax amount (GST/SST/VAT), as a plain number
- "total": the grand total amount payable, as a plain number

Rules:
- Output a single JSON object and nothing else.
- Use null for any field that is not present on the invoice.
- "date" MUST be YYYY-MM-DD. Convert from whatever format appears on the invoice.
- Numbers MUST be plain decimals, e.g. 41.20 not "RM 41.20" or "41,20".
- "taxable" + "tax" should normally equal "total".
"""

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def build_messages(image_data_uri: str) -> list:
    """Build the chat messages payload for the vision call."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": USER_PROMPT},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ],
        },
    ]


def safe_parse_json(content: str) -> Dict[str, Any]:
    """Parse model output into a dict, tolerating fences and surrounding prose.

    Raises ``ValueError`` if no JSON object can be recovered.
    """
    if not content:
        raise ValueError("empty model response")

    stripped = _FENCE_RE.sub("", content.strip())
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Fallback: grab the first {...} block from anywhere in the text.
    match = _OBJECT_RE.search(content)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    raise ValueError(f"could not parse JSON from model response: {content[:200]!r}")
