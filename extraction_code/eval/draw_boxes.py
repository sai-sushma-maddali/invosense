"""Recompute field boxes from out/*.json values and overlay them on images.

Boxes are re-derived from the already-extracted field values (no LLM call) via
``extraction.boxes.extract_boxes``, the JSON is updated in place, and an
annotated ``<id>_boxes.png`` is written next to it.

Usage:
    python eval/draw_boxes.py X51007262330      # one invoice
    python eval/draw_boxes.py --all             # every out/*.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from extraction.boxes import extract_boxes
from extraction.contract import EXTRACTION_FIELDS

_COLORS = {
    "company": "#e6194b",
    "gst_id": "#3cb44b",
    "invoice_no": "#4363d8",
    "date": "#f58231",
    "taxable": "#911eb4",
    "tax": "#0082c8",
    "total": "#f032e6",
}


def _font(size: int = 16):
    try:
        return ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf", size
        )
    except Exception:
        return ImageFont.load_default()


def process(invoice_id: str, invoices: Path, out: Path) -> bool:
    json_path = out / f"{invoice_id}.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))

    try:
        img_path = next(invoices.glob(f"{invoice_id}.*"))
    except StopIteration:
        print(f"  {invoice_id}: image not found, skipping")
        return False

    image_bytes = img_path.read_bytes()
    values = {
        f: (str(data[f]) if data.get(f) is not None else None)
        for f in EXTRACTION_FIELDS
    }
    boxes = extract_boxes(image_bytes, values) or None
    data["boxes"] = boxes
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    if not boxes:
        print(f"  {invoice_id}: no boxes matched")
        return False

    image = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = _font()
    for field, (x, y, w, h) in boxes.items():
        color = _COLORS.get(field, "#ff0000")
        draw.rectangle([x, y, x + w, y + h], outline=color, width=3)
        ty = max(0, y - 18)
        tw = draw.textlength(field, font=font) + 6
        draw.rectangle([x, ty, x + tw, ty + 18], fill=color)
        draw.text((x + 3, ty + 1), field, fill="white", font=font)

    dest = out / f"{invoice_id}_boxes.png"
    image.save(dest)
    print(f"  {invoice_id}: {len(boxes)} boxes -> {dest}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("invoice_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--invoices", default="invoices")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    invoices = Path(args.invoices)
    out = Path(args.out)

    if args.all:
        ids = sorted(p.stem for p in out.glob("*.json"))
    elif args.invoice_id:
        ids = [args.invoice_id]
    else:
        ap.error("provide an invoice_id or --all")
        return 2

    for invoice_id in ids:
        process(invoice_id, invoices, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
