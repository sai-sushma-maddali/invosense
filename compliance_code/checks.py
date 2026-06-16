"""Four compliance checks — each returns a flag dict on failure, else None."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from clickhouse_connect.driver.client import Client

from compliance_code.contract import ExtractedInvoice
from compliance_code.db import (
    CITED_MD_PATH,
    fetch_all,
    fetch_one,
    get_policy,
    lookup_tax_rate,
    lookup_vendor,
)

_RATE_TOLERANCE = 0.005
# Always a browser-openable URL (frontend proxies /tax-rules to the backend doc).
TAX_RULES_SOURCE_URL = os.getenv("TAX_RULES_SOURCE_URL", "/tax-rules").strip() or "/tax-rules"


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _flag(
    check: str,
    reason: str,
    message: str,
    *,
    source: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "check": check,
        "passed": False,
        "reason": reason,
        "message": message,
    }
    if source:
        out["source"] = source
    if details:
        out["details"] = details
    return out


def detect_duplicate(
    invoice: ExtractedInvoice, conn: Client
) -> Optional[dict[str, Any]]:
    """Exact duplicate (invoice_no in history) and near-dup (vendor + total, 5 days)."""
    policy = get_policy(conn)
    window_days = int(policy.get("near_dup_window_days", 5))
    invoice_no = (invoice.invoice_no or "").strip()
    if not invoice_no:
        return None

    exact = fetch_one(
        conn,
        """
        SELECT history_id, invoice_date FROM invoice_history
        WHERE invoice_no = {invoice_no:String}
        LIMIT 1
        """,
        {"invoice_no": invoice_no},
    )
    if exact:
        return _flag(
            "detect_duplicate",
            "exact_duplicate",
            f"Invoice number {invoice_no} already exists in history",
            details={"history_id": exact["history_id"], "invoice_date": exact["invoice_date"]},
        )

    if invoice.date is None or invoice.total is None:
        return None

    vendor = lookup_vendor(conn, invoice.company, invoice.gst_id)
    if not vendor:
        return None

    rows = fetch_all(
        conn,
        """
        SELECT history_id, invoice_no, invoice_date, total
        FROM invoice_history
        WHERE vendor_id = {vendor_id:String} AND total = {total:Float64}
        """,
        {"vendor_id": vendor["vendor_id"], "total": float(invoice.total)},
    )

    invoice_dt = _parse_date(invoice.date)
    for row in rows:
        hist_dt = _parse_date(str(row["invoice_date"]))
        delta = abs((invoice_dt - hist_dt).days)
        if delta <= window_days:
            return _flag(
                "detect_duplicate",
                "near_duplicate",
                (
                    f"Near-duplicate: vendor {vendor['company_name']} has total "
                    f"{invoice.total} within {window_days} days of {row['invoice_no']}"
                ),
                details={
                    "matched_invoice_no": row["invoice_no"],
                    "matched_date": row["invoice_date"],
                    "days_apart": delta,
                },
            )
    return None


def validate_totals(
    invoice: ExtractedInvoice, conn: Client
) -> Optional[dict[str, Any]]:
    """Fail if |taxable + tax - total| > tolerance (default 0.05)."""
    _ = conn
    policy = get_policy()
    tolerance = float(policy.get("totals_tolerance", 0.05))
    if invoice.taxable is None or invoice.tax is None or invoice.total is None:
        return _flag(
            "validate_totals",
            "missing_amounts",
            "Cannot validate totals: taxable, tax, or total is missing",
        )

    diff = abs((invoice.taxable + invoice.tax) - invoice.total)
    if diff > tolerance:
        return _flag(
            "validate_totals",
            "totals_mismatch",
            f"Totals mismatch: |taxable + tax - total| = {diff:.4f} > {tolerance}",
            details={
                "taxable": invoice.taxable,
                "tax": invoice.tax,
                "total": invoice.total,
                "difference": round(diff, 4),
                "tolerance": tolerance,
            },
        )
    return None


def check_vendor(
    invoice: ExtractedInvoice, conn: Client
) -> Optional[dict[str, Any]]:
    """Fail if vendor missing, not approved, or gst_id mismatch."""
    company = (invoice.company or "").strip()
    gst_id = (invoice.gst_id or "").strip()

    if not company and not gst_id:
        return _flag(
            "check_vendor",
            "vendor_missing",
            "Vendor not found: company and gst_id are both missing",
        )

    vendor = lookup_vendor(conn, invoice.company, invoice.gst_id)
    if not vendor:
        return _flag(
            "check_vendor",
            "vendor_missing",
            f"Vendor not found in vendor_master: {company or gst_id}",
        )

    if int(vendor["approved"]) == 0:
        return _flag(
            "check_vendor",
            "vendor_not_approved",
            f"Vendor {vendor['company_name']} is not approved",
            details={"vendor_id": vendor["vendor_id"]},
        )

    if gst_id and gst_id != vendor["gst_id"]:
        return _flag(
            "check_vendor",
            "gst_id_mismatch",
            f"GST ID mismatch: invoice has {gst_id}, vendor_master has {vendor['gst_id']}",
            details={"expected_gst_id": vendor["gst_id"], "actual_gst_id": gst_id},
        )
    return None


def _parse_rates_from_cited_md(path: Path = CITED_MD_PATH) -> list[tuple[str, str | None, float]]:
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8")

    # Prefer machine-readable JSON block from cited-md-malaysia-tax-rules.md
    start = text.find("```json")
    if start != -1:
        end = text.find("```", start + 7)
        if end != -1:
            try:
                payload = json.loads(text[start + 7 : end].strip())
                rows: list[tuple[str, str | None, float]] = []
                for rule in payload.get("tax_rules", []):
                    rows.append(
                        (
                            rule["valid_from"],
                            rule.get("valid_to"),
                            float(rule["rate"]),
                        )
                    )
                if rows:
                    return rows
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

    # Fallback: simple markdown table (legacy cited.md format)
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line or "effective_from" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3:
            continue
        effective_from, effective_to, rate_str = parts[0], parts[1], parts[2]
        end = effective_to or None
        rows.append((effective_from, end, float(rate_str)))
    return rows


def _rate_from_cited_md(invoice_date: str) -> Optional[float]:
    for effective_from, effective_to, rate in _parse_rates_from_cited_md():
        if effective_from <= invoice_date and (
            effective_to is None or effective_to >= invoice_date
        ):
            return rate
    return None


def check_tax_rate(
    invoice: ExtractedInvoice, conn: Client
) -> Optional[dict[str, Any]]:
    """Look up correct rate for date; fail if charged rate differs."""
    if invoice.date is None or invoice.taxable is None or invoice.tax is None:
        return None
    if invoice.taxable <= 0:
        return None

    expected_rate = _rate_from_cited_md(invoice.date)
    source = TAX_RULES_SOURCE_URL
    if expected_rate is None:
        expected_rate = lookup_tax_rate(conn, invoice.date)

    if expected_rate is None:
        return _flag(
            "check_tax_rate",
            "rate_lookup_failed",
            f"No tax rule found for date {invoice.date}",
            source=source,
        )

    charged_rate = round(float(invoice.tax) / float(invoice.taxable), 4)
    if abs(charged_rate - expected_rate) > _RATE_TOLERANCE:
        return _flag(
            "check_tax_rate",
            "tax_rate_mismatch",
            (
                f"Tax rate mismatch on {invoice.date}: charged {charged_rate:.2%}, "
                f"expected {expected_rate:.2%}"
            ),
            source=source,
            details={
                "charged_rate": charged_rate,
                "expected_rate": expected_rate,
                "invoice_date": invoice.date,
            },
        )
    return None


ALL_CHECKS = [
    detect_duplicate,
    validate_totals,
    check_vendor,
    check_tax_rate,
]
