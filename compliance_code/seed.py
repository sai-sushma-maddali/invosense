"""Seed compliance reference tables and publish tax rules to cited.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compliance_code.db import (  # noqa: E402
    CITED_MD_PATH,
    CITED_MD_SOURCE_PATH,
    CITED_MD_URL,
    connect,
    init_schema,
    truncate_tables,
)
from clickhouse_connect.driver.client import Client  # noqa: E402

VENDORS = [
    ("V001", "UNIHAKKA INTERNATIONAL SDN BHD", "000565195584", 1),
    ("V002", "LAVENDER CONFECTIONERY & BAKERY S/B", "001872379904", 1),
    ("V003", "BLOCKED SUPPLIES LTD", "111111111111", 0),
    ("V004", "ACME SUPPLIES CO", "999888777666", 1),
]

INVOICE_HISTORY = [
    ("H1", "INV-001", "V001", "UNIHAKKA INTERNATIONAL SDN BHD", 6.0, "2018-06-11"),
    ("H2", "B063895", "V002", "LAVENDER CONFECTIONERY & BAKERY S/B", 26.5, "2018-06-17"),
]

TAX_RULES = [
    (1, "2015-04-01", "2018-05-31", 0.06, "Malaysia GST 6%"),
    (2, "2018-06-01", "2018-08-31", 0.00, "Zero-rated transition period (tax holiday)"),
    (3, "2018-09-01", None, 0.06, "Malaysia SST 6% service / 10% sales"),
]

POLICY_CONFIG = [
    ("high_value_cap", "5000"),
    ("auto_pay_enabled", "true"),
    ("totals_tolerance", "0.05"),
    ("near_dup_window_days", "5"),
    ("require_vendor_verification", "true"),
]


def publish_cited_md() -> Path:
    """Publish cited-md-malaysia-tax-rules.md to compliance_code/cited.md."""
    if not CITED_MD_SOURCE_PATH.is_file():
        raise FileNotFoundError(
            f"Tax rules source not found: {CITED_MD_SOURCE_PATH}"
        )
    content = CITED_MD_SOURCE_PATH.read_text(encoding="utf-8")
    header = (
        f"<!-- Published from {CITED_MD_SOURCE_PATH.name} -->\n"
        f"<!-- Canonical URL: {CITED_MD_URL} -->\n\n"
    )
    CITED_MD_PATH.write_text(header + content, encoding="utf-8")
    return CITED_MD_PATH


def _insert_rows(conn: Client, table: str, rows: list[tuple], columns: list[str]) -> None:
    if rows:
        conn.insert(table, rows, column_names=columns)


def seed(conn: Client | None = None, *, reset: bool = True) -> Client:
    """Create tables and load seed data into ClickHouse."""
    own_conn = conn is None
    db = conn or connect()
    init_schema(db)

    if reset:
        truncate_tables(db)

    _insert_rows(
        db,
        "vendor_master",
        VENDORS,
        ["vendor_id", "company_name", "gst_id", "approved"],
    )
    _insert_rows(
        db,
        "invoice_history",
        INVOICE_HISTORY,
        ["history_id", "invoice_no", "vendor_id", "company_name", "total", "invoice_date"],
    )
    tax_rows = [
        (rule_id, eff_from, eff_to, rate, desc)
        for rule_id, eff_from, eff_to, rate, desc in TAX_RULES
    ]
    _insert_rows(
        db,
        "tax_rules",
        tax_rows,
        ["rule_id", "effective_from", "effective_to", "rate", "description"],
    )
    _insert_rows(
        db,
        "policy_config",
        POLICY_CONFIG,
        ["config_key", "config_value"],
    )
    publish_cited_md()
    return db if not own_conn else db


def main() -> None:
    client = seed()
    client.close()
    print(f"Seeded ClickHouse and published {CITED_MD_PATH}")


if __name__ == "__main__":
    main()
