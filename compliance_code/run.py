"""Run all compliance checks and return Contract 2."""

from __future__ import annotations

from typing import Optional

from clickhouse_connect.driver.client import Client

from compliance_code.checks import ALL_CHECKS
from compliance_code.contract import ComplianceResult, ExtractedInvoice
from compliance_code.db import connect, get_policy, scalar
from compliance_code.seed import seed


def run(
    invoice: ExtractedInvoice,
    conn: Optional[Client] = None,
) -> ComplianceResult:
    """Run all four checks; status is flagged if any check fails."""
    own_conn = conn is None
    db = conn or connect()
    if own_conn:
        count = scalar(db, "SELECT count() FROM vendor_master")
        if not count:
            seed(db, reset=True)

    flags = []
    for check_fn in ALL_CHECKS:
        flag = check_fn(invoice, db)
        if flag:
            flags.append(flag)

    failed_checks = {f["check"] for f in flags}
    result = ComplianceResult(
        invoice_id=invoice.invoice_id,
        status="flagged" if flags else "clean",
        flags=flags,
        vendor_verified="check_vendor" not in failed_checks,
        amount_verified=not failed_checks.intersection(
            {"validate_totals", "check_tax_rate"}
        ),
        duplicate_check_passed="detect_duplicate" not in failed_checks,
        notes="" if not flags else f"{len(flags)} compliance flag(s) raised",
    )

    if own_conn:
        db.close()
    return result


__all__ = ["run", "get_policy"]
