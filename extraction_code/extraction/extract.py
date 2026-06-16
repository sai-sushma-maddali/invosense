"""Public entry point: turn an invoice image into ``ExtractedInvoice``.

    from extraction import run
    result = run(image_bytes, invoice_id="X51007262330")
    print(result.to_json())

The vision LLM call is routed through the TrueFoundry gateway so usage and
cost are logged centrally.
"""

from __future__ import annotations

from typing import Optional

from extraction import confidence
from extraction.contract import EXTRACTION_FIELDS, ExtractedInvoice
from extraction.gateway import (
    GatewayConfig,
    build_client,
    image_to_data_uri,
    sniff_mime,
)
from extraction.normalize import normalize_amount, normalize_date, normalize_text
from extraction.prompt import build_messages, safe_parse_json

_AMOUNT_FIELDS = {"taxable", "tax", "total"}


def _call_vision_llm(image_bytes: bytes, config: Optional[GatewayConfig]):
    """Send the image to the vision model and return raw JSON text."""
    cfg = config or GatewayConfig.from_env()
    client = build_client(cfg)
    data_uri = image_to_data_uri(image_bytes, mime=sniff_mime(image_bytes))

    kwargs = dict(
        model=cfg.model,
        messages=build_messages(data_uri),
        temperature=0,
    )
    try:
        # Prefer strict JSON mode when the provider supports it.
        resp = client.chat.completions.create(
            response_format={"type": "json_object"}, **kwargs
        )
    except Exception:
        resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def _normalize_fields(raw: dict) -> dict:
    """Coerce raw model values to the contract's normalized types."""
    out = {}
    out["company"] = normalize_text(raw.get("company"))
    out["gst_id"] = normalize_text(raw.get("gst_id"))
    out["invoice_no"] = normalize_text(raw.get("invoice_no"))
    out["date"] = normalize_date(raw.get("date"))
    out["taxable"] = normalize_amount(raw.get("taxable"))
    out["tax"] = normalize_amount(raw.get("tax"))
    out["total"] = normalize_amount(raw.get("total"))
    return out


def run(
    image_bytes: bytes,
    invoice_id: str,
    *,
    config: Optional[GatewayConfig] = None,
    with_boxes: bool = False,
    raw_json: Optional[dict] = None,
) -> ExtractedInvoice:
    """Extract structured invoice data from image bytes.

    Args:
        image_bytes: Raw bytes of the invoice image (jpeg/png/webp).
        invoice_id: Identifier carried through to the output contract.
        config: Optional gateway config override (otherwise read from .env).
        with_boxes: If True, attempt pytesseract word-box matching.
        raw_json: Pre-parsed model output, bypassing the LLM call. Useful for
            offline tests; production callers leave this as None.

    Returns:
        An ``ExtractedInvoice`` (Contract 1).
    """
    if raw_json is None:
        content = _call_vision_llm(image_bytes, config)
        raw = safe_parse_json(content)
    else:
        raw = dict(raw_json)

    model_certainty = raw.get("confidence")
    if not isinstance(model_certainty, (int, float)):
        model_certainty = None

    fields = _normalize_fields(raw)
    scores = confidence.compute(fields, model_certainty=model_certainty)

    boxes = None
    if with_boxes:
        from extraction.boxes import extract_boxes

        box_values = {
            f: (str(fields[f]) if fields[f] is not None else None)
            for f in EXTRACTION_FIELDS
        }
        found = extract_boxes(image_bytes, box_values)
        boxes = found or None

    return ExtractedInvoice(
        invoice_id=invoice_id,
        confidence=scores,
        overall_confidence=confidence.overall(scores),
        boxes=boxes,
        **fields,
    )
