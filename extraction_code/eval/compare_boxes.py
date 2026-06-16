"""Benchmark box-matching configurations across all out/*.json invoices.

No ground-truth boxes exist, so quality is proxied by *verifiable* matches:
a match counts as "exact" when the matched OCR text normalizes back to the
field's true value (amounts/date) or is >=0.9 similar (text fields). This
separates trustworthy boxes from low-confidence fuzzy guesses, so a config
with high recall but low exact-rate is over-matching.

Usage:
    PYTHONPATH=. python eval/compare_boxes.py
"""

from __future__ import annotations

import json
from pathlib import Path

from difflib import SequenceMatcher

from extraction import boxes as B
from extraction.contract import EXTRACTION_FIELDS
from extraction.normalize import normalize_amount, normalize_date

_AMOUNT_FIELDS = {"taxable", "tax", "total"}

# (label, kwargs) -- kwargs feed straight into match_fields.
CONFIGS = [
    ("baseline", dict(preprocess_mode="none", use_keywords=False,
                      use_date_variants=False, match_threshold=0.6)),
    ("+date+keyword", dict(preprocess_mode="none", use_keywords=True,
                           use_date_variants=True, match_threshold=0.6)),
    ("+upscale (prod)", dict(preprocess_mode="upscale", use_keywords=True,
                             use_date_variants=True, match_threshold=0.6)),
    ("+gray", dict(preprocess_mode="gray", use_keywords=True,
                   use_date_variants=True, match_threshold=0.6)),
    ("+lowthresh 0.5", dict(preprocess_mode="upscale", use_keywords=True,
                            use_date_variants=True, match_threshold=0.5)),
]


def is_exact(field: str, true_value, matched_text: str) -> bool:
    """True when the matched OCR text verifiably equals the field value."""
    if field in _AMOUNT_FIELDS:
        a, b = normalize_amount(true_value), normalize_amount(matched_text)
        return a is not None and b is not None and abs(a - b) < 0.005
    if field == "date":
        return normalize_date(matched_text) == str(true_value)
    ratio = SequenceMatcher(None, str(true_value).lower(),
                            matched_text.lower()).ratio()
    return ratio >= 0.9


def main() -> int:
    out = Path("out")
    invoices = Path("invoices")
    records = []
    for jp in sorted(out.glob("*.json")):
        data = json.loads(jp.read_text(encoding="utf-8"))
        try:
            img = next(invoices.glob(f"{jp.stem}.*"))
        except StopIteration:
            continue
        values = {
            f: (str(data[f]) if data.get(f) is not None else None)
            for f in EXTRACTION_FIELDS
        }
        present = {f for f, v in values.items() if v is not None}
        records.append((jp.stem, img.read_bytes(), values, data, present))

    total_present = sum(len(p) for *_, p in records)

    rows = []
    per_field = {label: {f: [0, 0] for f in EXTRACTION_FIELDS}
                 for label, _ in CONFIGS}
    for label, kwargs in CONFIGS:
        matched = exact = 0
        for _stem, img_bytes, values, data, present in records:
            res = B.match_fields(img_bytes, values, **kwargs)
            for f in present:
                if f in res:
                    matched += 1
                    per_field[label][f][0] += 1
                    if is_exact(f, data[f], res[f]["text"]):
                        exact += 1
                        per_field[label][f][1] += 1
        rows.append((label, matched, exact))

    print(f"\n{len(records)} invoices, {total_present} field values present\n")
    print(f"{'config':<18}{'matched':>9}{'exact':>8}{'recall':>9}{'exact%':>9}")
    print("-" * 53)
    for label, matched, exact in rows:
        rec = matched / total_present if total_present else 0
        exr = exact / matched if matched else 0
        print(f"{label:<18}{matched:>9}{exact:>8}{rec:>8.0%}{exr:>9.0%}")

    print("\nper-field exact / matched:")
    header = "field".ljust(12) + "".join(l[:14].rjust(16) for l, _ in CONFIGS)
    print(header)
    print("-" * len(header))
    for f in EXTRACTION_FIELDS:
        cells = "".join(
            f"{per_field[l][f][1]}/{per_field[l][f][0]}".rjust(16)
            for l, _ in CONFIGS
        )
        print(f.ljust(12) + cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
