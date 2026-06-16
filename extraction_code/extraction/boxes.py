"""Optional word-box extraction via pytesseract.

Matches each extracted field value to OCR words by string similarity and
returns a pixel box ``[x, y, w, h]`` per matched field. Degrades gracefully
(returns ``{}``) when pytesseract or the tesseract binary is unavailable.

Refinements over naive fuzzy matching:

* **Upscale** -- small scans are 2x upscaled (LANCZOS) so faint glyphs survive
  OCR; coordinates are scaled back to the original image space.
* **Date variants** -- the contract stores ``YYYY-MM-DD`` but receipts print
  ``23/03/2018`` etc., so each value is expanded into several string candidates.
* **Keyword anchoring** -- amount fields share identical values (a subtotal and
  a total can both read ``41.20``), so a candidate window is rewarded when a
  field-specific label (e.g. ``total``) sits on the same row to its left.

The tuning knobs are exposed as ``extract_boxes`` keyword args so alternatives
can be benchmarked (see ``eval/compare_boxes.py``); the defaults are the
production configuration.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from extraction.normalize import normalize_amount

_tesseract_configured = False


def _configure_tesseract() -> None:
    """Point pytesseract at TESSERACT_CMD when the binary is not on PATH."""
    global _tesseract_configured
    if _tesseract_configured:
        return
    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd
    _tesseract_configured = True

_MATCH_THRESHOLD = 0.6
_KEYWORD_BONUS = 0.4

# Upscale small scans so faint amount glyphs survive OCR; coordinates are
# scaled back to the original image space before returning.
_OCR_SCALE = 2
_OCR_MIN_WIDTH = 1600

# Label tokens (matched case-insensitively, exact word) that should sit on the
# same row, to the left of an amount, to disambiguate duplicate values.
_FIELD_KEYWORDS = {
    "taxable": {"subtotal", "taxable", "amount", "amt", "nett", "net"},
    "tax": {"tax", "gst"},
    "total": {"total", "grandtotal"},
}

_AMOUNT_FIELDS = {"taxable", "tax", "total"}

_DATE_VARIANTS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d %B %Y",
    "%m/%d/%Y",
]


def _preprocess(image, mode: str):
    """Return ``(processed_image, scale)`` for OCR.

    ``mode`` is one of ``"none"``, ``"upscale"`` (default production), or
    ``"gray"`` (grayscale + autocontrast + upscale). Divide returned
    coordinates by ``scale`` to map back to the original image space.
    """
    from PIL import Image, ImageOps

    if mode == "none":
        return image, 1
    img = image
    if mode == "gray":
        img = ImageOps.autocontrast(img.convert("L"))
    scale = _OCR_SCALE if img.width < _OCR_MIN_WIDTH else 1
    if scale != 1:
        img = img.resize(
            (img.width * scale, img.height * scale), resample=Image.LANCZOS
        )
    return img, scale


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _candidates(field: str, value: str, use_date_variants: bool) -> List[str]:
    """Expand a normalized field value into OCR-friendly string variants."""
    value = value.strip()
    if field == "date" and use_date_variants:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return [value]
        out = [dt.strftime(fmt) for fmt in _DATE_VARIANTS]
        out.append(value)
        return list(dict.fromkeys(out))
    if field in _AMOUNT_FIELDS:
        amt = normalize_amount(value)
        if amt is None:
            return [value]
        fixed = f"{amt:.2f}"
        return list(
            dict.fromkeys([fixed, fixed.replace(".", ","), str(amt), value])
        )
    return [value]


def _keyword_bonus(field: str, window: List[dict], words: List[dict]) -> float:
    """Reward a label keyword on the same row, left of the window."""
    keywords = _FIELD_KEYWORDS.get(field)
    if not keywords:
        return 0.0
    win_top = min(w["top"] for w in window)
    win_h = max(w["height"] for w in window)
    win_left = min(w["left"] for w in window)
    win_mid = win_top + win_h / 2
    for w in words:
        if w["left"] >= win_left:
            continue
        w_mid = w["top"] + w["height"] / 2
        if abs(w_mid - win_mid) > win_h:
            continue
        token = "".join(ch for ch in w["text"].lower() if ch.isalpha())
        if token in keywords:
            return _KEYWORD_BONUS
    return 0.0


def _ocr_words(image_bytes: bytes, preprocess_mode: str) -> List[dict]:
    """Run OCR and return normalized word dicts in original-image coordinates."""
    import pytesseract
    from PIL import Image

    _configure_tesseract()
    image = Image.open(io.BytesIO(image_bytes))
    prepped, scale = _preprocess(image, preprocess_mode)
    data = pytesseract.image_to_data(
        prepped, output_type=pytesseract.Output.DICT
    )
    words = []
    for i, text in enumerate(data.get("text", [])):
        t = (text or "").strip()
        if not t:
            continue
        words.append(
            {
                "text": t,
                "left": int(int(data["left"][i]) / scale),
                "top": int(int(data["top"][i]) / scale),
                "width": int(int(data["width"][i]) / scale),
                "height": int(int(data["height"][i]) / scale),
            }
        )
    return words


def match_fields(
    image_bytes: bytes,
    values: Dict[str, Optional[str]],
    *,
    match_threshold: float = _MATCH_THRESHOLD,
    preprocess_mode: str = "upscale",
    use_keywords: bool = True,
    use_date_variants: bool = True,
) -> Dict[str, dict]:
    """Match each field value to OCR words.

    Returns ``{field: {"box": [x, y, w, h], "text": <ocr text>,
    "score": <base similarity>}}``. Empty dict if OCR is unavailable.
    """
    try:
        words = _ocr_words(image_bytes, preprocess_mode)
    except Exception:
        return {}
    if not words:
        return {}

    out: Dict[str, dict] = {}
    for field, value in values.items():
        if value is None or str(value).strip() == "":
            continue
        targets = _candidates(field, str(value), use_date_variants)
        max_tokens = max(len(t.split()) for t in targets)
        best_total = 0.0
        best_base = 0.0
        best_window = None
        for start in range(len(words)):
            for win in range(1, min(max_tokens + 2, len(words) - start + 1)):
                chunk = words[start : start + win]
                joined = " ".join(w["text"] for w in chunk)
                base = max(_similar(joined, t) for t in targets)
                if base < match_threshold:
                    continue
                bonus = (
                    _keyword_bonus(field, chunk, words) if use_keywords else 0.0
                )
                total = base + bonus
                if total > best_total:
                    best_total = total
                    best_base = base
                    best_window = chunk
        if best_window and best_base >= match_threshold:
            x = min(w["left"] for w in best_window)
            y = min(w["top"] for w in best_window)
            x2 = max(w["left"] + w["width"] for w in best_window)
            y2 = max(w["top"] + w["height"] for w in best_window)
            out[field] = {
                "box": [x, y, x2 - x, y2 - y],
                "text": " ".join(w["text"] for w in best_window),
                "score": round(best_base, 3),
            }
    return out


def extract_boxes(
    image_bytes: bytes, values: Dict[str, Optional[str]], **kwargs
) -> Dict[str, List[int]]:
    """Return ``{field: [x, y, w, h]}`` for fields matched to OCR words.

    Accepts the same tuning kwargs as :func:`match_fields`.
    """
    matched = match_fields(image_bytes, values, **kwargs)
    return {field: m["box"] for field, m in matched.items()}
