"""Evaluation harness for the invoice extraction module.

Runs ``extraction.run`` over every image in the invoices directory, compares
each result to the matching SROIE-style ground-truth JSON, and prints a
field-level precision/recall/F1 report against a target (default 0.9).

Usage:
    python -m eval.run_eval \
        --invoices "invoices" \
        --ground-truth "ground truth" \
        --out "out" \
        --target 0.9

Only fields present in a ground-truth file are scored, so this works both with
the stock SROIE GT (company/date/total) and an extended 7-field GT.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Dict, Optional, Tuple

from extraction import run
from extraction.contract import EXTRACTION_FIELDS
from extraction.normalize import normalize_amount, normalize_date, normalize_text

# Ground-truth keys that map onto contract fields. GT keys not listed here
# (e.g. "address") are ignored for scoring.
GT_KEY_MAP = {
    "company": "company",
    "gst_id": "gst_id",
    "gst": "gst_id",
    "invoice_no": "invoice_no",
    "invoice": "invoice_no",
    "date": "date",
    "taxable": "taxable",
    "subtotal": "taxable",
    "tax": "tax",
    "total": "total",
}

_AMOUNT_FIELDS = {"taxable", "tax", "total"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def canon(field: str, value) -> Optional[str]:
    """Canonicalize a value for equality comparison."""
    if value is None or str(value).strip() == "":
        return None
    if field in _AMOUNT_FIELDS:
        amt = normalize_amount(value)
        return f"{amt:.2f}" if amt is not None else None
    if field == "date":
        return normalize_date(value)
    text = normalize_text(value)
    return text.lower() if text else None


def load_ground_truth(path: Path) -> Dict[str, Optional[str]]:
    """Load a GT file and map it to canonical contract fields."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    gt: Dict[str, Optional[str]] = {}
    for key, value in raw.items():
        field = GT_KEY_MAP.get(key.strip().lower())
        if field:
            gt[field] = canon(field, value)
    return gt


class Counts:
    __slots__ = ("tp", "fp", "fn")

    def __init__(self):
        self.tp = self.fp = self.fn = 0

    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) else 0.0


def update_counts(counts: Counts, pred: Optional[str], gt: Optional[str]) -> None:
    """Single-value field scoring per document."""
    if gt is not None and pred is not None and pred == gt:
        counts.tp += 1
    else:
        if pred is not None:
            counts.fp += 1
        if gt is not None:
            counts.fn += 1


def find_pairs(invoices: Path, gt_dir: Path) -> list:
    """Match image files to ground-truth .txt files by stem."""
    gt_by_stem = {p.stem: p for p in gt_dir.glob("*.txt")}
    pairs = []
    for img in sorted(invoices.iterdir()):
        if img.suffix.lower() in _IMAGE_EXTS and img.stem in gt_by_stem:
            pairs.append((img, gt_by_stem[img.stem]))
    return pairs


def evaluate(args) -> int:
    invoices = Path(args.invoices)
    gt_dir = Path(args.ground_truth)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs = find_pairs(invoices, gt_dir)
    if not pairs:
        print(f"No image/ground-truth pairs found in {invoices} / {gt_dir}")
        return 2

    counts: Dict[str, Counts] = {f: Counts() for f in EXTRACTION_FIELDS}
    valid_contract = 0
    errors = 0

    for img_path, gt_path in pairs:
        invoice_id = img_path.stem
        gt = load_ground_truth(gt_path)
        try:
            image_bytes = img_path.read_bytes()
            result = run(image_bytes, invoice_id, with_boxes=args.with_boxes)
            valid_contract += 1
            (out_dir / f"{invoice_id}.json").write_text(
                result.to_json(), encoding="utf-8"
            )
            pred = {f: canon(f, getattr(result, f)) for f in EXTRACTION_FIELDS}
            status = "ok"
        except Exception as exc:  # keep going; report at the end
            errors += 1
            pred = {f: None for f in EXTRACTION_FIELDS}
            status = f"ERROR: {type(exc).__name__}: {exc}"
            if args.verbose:
                traceback.print_exc()

        for field in EXTRACTION_FIELDS:
            if field in gt:  # only score fields the GT actually provides
                update_counts(counts[field], pred[field], gt[field])
        print(f"  {invoice_id}: {status}")

    _print_report(counts, pairs, valid_contract, errors, args.target)

    macro = _macro_f1(counts)
    return 0 if (macro >= args.target and errors == 0) else 1


def _macro_f1(counts: Dict[str, Counts]) -> float:
    scored = [c for c in counts.values() if (c.tp + c.fp + c.fn) > 0]
    return sum(c.f1() for c in scored) / len(scored) if scored else 0.0


def _micro_f1(counts: Dict[str, Counts]) -> Tuple[float, float, float]:
    tp = sum(c.tp for c in counts.values())
    fp = sum(c.fp for c in counts.values())
    fn = sum(c.fn for c in counts.values())
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


def _print_report(counts, pairs, valid_contract, errors, target) -> None:
    print("\n" + "=" * 60)
    print("FIELD-LEVEL F1 REPORT")
    print("=" * 60)
    print(f"{'field':<14}{'P':>8}{'R':>8}{'F1':>8}{'TP':>5}{'FP':>5}{'FN':>5}")
    print("-" * 60)
    for field in EXTRACTION_FIELDS:
        c = counts[field]
        if (c.tp + c.fp + c.fn) == 0:
            print(f"{field:<14}{'  (not in ground truth)':>40}")
            continue
        print(
            f"{field:<14}{c.precision():>8.3f}{c.recall():>8.3f}"
            f"{c.f1():>8.3f}{c.tp:>5}{c.fp:>5}{c.fn:>5}"
        )
    print("-" * 60)
    macro = _macro_f1(counts)
    mp, mr, mf = _micro_f1(counts)
    print(f"{'macro F1':<14}{'':>16}{macro:>8.3f}")
    print(f"{'micro':<14}{mp:>8.3f}{mr:>8.3f}{mf:>8.3f}")
    print("=" * 60)
    print(f"valid Contract-1 JSON: {valid_contract}/{len(pairs)}  errors: {errors}")
    verdict = "PASS" if (macro >= target and errors == 0) else "FAIL"
    print(f"target macro F1 >= {target}: {verdict} (macro F1 = {macro:.3f})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Invoice extraction F1 eval")
    parser.add_argument("--invoices", default="invoices")
    parser.add_argument("--ground-truth", default="ground truth")
    parser.add_argument("--out", default="out")
    parser.add_argument("--target", type=float, default=0.9)
    parser.add_argument("--with-boxes", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    return evaluate(args)


if __name__ == "__main__":
    sys.exit(main())
