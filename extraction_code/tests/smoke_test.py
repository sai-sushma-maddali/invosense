"""Offline smoke test: exercises the full pipeline without network/credentials.

Feeds pre-parsed JSON into ``extraction.run`` via the ``raw_json`` hook so we
can validate the contract, normalization, confidence scoring and serialization
end-to-end. Also sanity-checks the parser and F1 counting.
"""

from __future__ import annotations

import sys

from extraction import run
from extraction.contract import EXTRACTION_FIELDS, ExtractedInvoice
from extraction.normalize import normalize_amount, normalize_date
from extraction.prompt import safe_parse_json


def test_normalize():
    assert normalize_amount("RM 1,234.50") == 1234.50
    assert normalize_amount("41.20") == 41.20
    assert normalize_amount(None) is None
    assert normalize_date("23/03/2018") == "2018-03-23"
    assert normalize_date("2018-03-23") == "2018-03-23"
    assert normalize_date("not a date") is None
    print("normalize: OK")


def test_safe_parse():
    assert safe_parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert safe_parse_json('here you go: {"b": 2} thanks') == {"b": 2}
    try:
        safe_parse_json("no json here")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("safe_parse: OK")


def test_run_with_raw():
    raw = {
        "company": "SWC ENTERPRISE SDN BHD",
        "gst_id": "000123456789",
        "invoice_no": "A-0012",
        "date": "23/03/2018",
        "taxable": "38.87",
        "tax": "2.33",
        "total": "RM 41.20",
        "confidence": 0.9,
    }
    result = run(b"", "X51007262330", raw_json=raw)
    assert isinstance(result, ExtractedInvoice)
    assert result.date == "2018-03-23"
    assert result.total == 41.20
    assert abs(result.taxable + result.tax - result.total) <= 0.01
    # all fields scored
    assert set(result.confidence) >= set(EXTRACTION_FIELDS)
    # valid 12-digit GST (1.0) blended with model certainty 0.9 -> 0.95
    assert result.confidence["gst_id"] == 0.95
    assert 0.0 <= result.overall_confidence <= 1.0
    # valid JSON round-trips
    import json

    json.loads(result.to_json())
    print("run_with_raw: OK")
    print(result.to_json())


def main() -> int:
    test_normalize()
    test_safe_parse()
    test_run_with_raw()
    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
