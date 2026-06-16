"""Production vendor + history data for hackathon demo invoices."""

from __future__ import annotations

# Approved vendors from hackathon vendor_master.csv + GST IDs from real extractions.
# Company names match LLM extraction output so check_vendor passes.
VENDORS = [
    ("V001", "SWC ENTERPRISE SDN BHD", "002017808384", 1),
    ("V002", "SANYU STATIONERY SHOP", "001531760640", 1),
    ("V003", "AIK HUAT HARDWARE ENTERPRISE (SETIA ALAM) SDN BHD", "000394528768", 1),
    ("V004", "AEON CO. (M) BHD", "002017394688", 1),
    ("V005", "UNIHAKKA INTERNATIONAL SDN BHD", "000656195584", 1),
    ("V006", "LAVENDER CONFECTIONERY & BAKERY S/B", "001872379904", 1),
    ("V007", "MR. D.I.Y. (M) SDN BHD", "000306020352", 1),
    # Synthetic / verify-only entries (must stay rejected in tests)
    ("V008", "BLOCKED SUPPLIES LTD", "111111111111", 0),
    ("V009", "ACME SUPPLIES CO", "999888777666", 1),
]

# Past payments for compliance unit tests only — must NOT overlap the 10 demo JPGs.
INVOICE_HISTORY = [
    ("H1", "INV-001", "V005", "UNIHAKKA INTERNATIONAL SDN BHD", 6.0, "2018-01-15"),
    ("H2", "HIST-ACME-50", "V009", "ACME SUPPLIES CO", 50.0, "2018-09-10"),
]

# Real demo invoice filenames (hackathon/invoices/*.jpg) — used by batch_test_invoices.py
DEMO_INVOICE_FILES = [
    "X51007262330.jpg",
    "X51007339156.jpg",
    "X51007339164.jpg",
    "X51007339642.jpg",
    "X51007339653.jpg",
    "X51007339657.jpg",
    "X51007846305.jpg",
    "X51007846309.jpg",
    "X51007846412.jpg",
    "X51008064061.jpg",
]

SYNTHETIC_SUBDIR = "Synthetic_scenarios"
