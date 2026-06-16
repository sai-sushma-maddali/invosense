"""ClickHouse data layer for compliance reference tables."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

try:
    import clickhouse_connect
    from clickhouse_connect.driver.client import Client
except ImportError:  # pragma: no cover - verified at connect() time
    clickhouse_connect = None  # type: ignore[assignment]
    Client = Any  # type: ignore[misc, assignment]

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
CITED_MD_SOURCE_PATH = REPO_ROOT / "cited-md-malaysia-tax-rules.md"
CITED_MD_PATH = ROOT / "cited.md"

CITED_MD_URL = (
    "https://github.com/aakashvardhan/invosense/blob/polling/"
    "cited-md-malaysia-tax-rules.md"
)

TABLES = ("invoice_history", "vendor_master", "tax_rules", "policy_config")


def _database() -> str:
    return os.getenv("CLICKHOUSE_DATABASE", "invosense")


def _secure() -> bool:
    return os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true"


def _default_port(secure: bool) -> int:
    return 8443 if secure else 8123


def _client_kwargs(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    connect_timeout: int,
    send_receive_timeout: int,
) -> dict[str, Any]:
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "database": database,
        "secure": _secure(),
        "connect_timeout": connect_timeout,
        "send_receive_timeout": send_receive_timeout,
    }


def connect(
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> Client:
    """Open a ClickHouse client using env vars or explicit overrides."""
    if clickhouse_connect is None:
        raise RuntimeError(
            "clickhouse-connect is not installed. Run: pip install clickhouse-connect"
        )

    db_name = database or _database()
    secure = _secure()
    host_val = host or os.getenv("CLICKHOUSE_HOST", "localhost")
    port_val = port or int(os.getenv("CLICKHOUSE_PORT", str(_default_port(secure))))
    user_val = username or os.getenv("CLICKHOUSE_USER", "default")
    pass_val = password if password is not None else os.getenv("CLICKHOUSE_PASSWORD", "")
    timeout = int(os.getenv("CLICKHOUSE_CONNECT_TIMEOUT", "10"))
    recv_timeout = int(os.getenv("CLICKHOUSE_SEND_RECEIVE_TIMEOUT", "90"))

    bootstrap = clickhouse_connect.get_client(
        **_client_kwargs(
            host=host_val,
            port=port_val,
            username=user_val,
            password=pass_val,
            database="default",
            connect_timeout=timeout,
            send_receive_timeout=recv_timeout,
        )
    )
    bootstrap.command(f"CREATE DATABASE IF NOT EXISTS {db_name}")
    bootstrap.close()

    return clickhouse_connect.get_client(
        **_client_kwargs(
            host=host_val,
            port=port_val,
            username=user_val,
            password=pass_val,
            database=db_name,
            connect_timeout=timeout,
            send_receive_timeout=recv_timeout,
        )
    )


def init_schema(conn: Client) -> None:
    """Create compliance tables in ClickHouse."""
    db = _database()
    conn.command(
        f"""
        CREATE TABLE IF NOT EXISTS {db}.vendor_master (
            vendor_id String,
            company_name String,
            gst_id String,
            approved UInt8
        ) ENGINE = MergeTree()
        ORDER BY vendor_id
        """
    )
    conn.command(
        f"""
        CREATE TABLE IF NOT EXISTS {db}.invoice_history (
            history_id String,
            invoice_no String,
            vendor_id String,
            company_name String,
            total Float64,
            invoice_date Date
        ) ENGINE = MergeTree()
        ORDER BY (invoice_no, history_id)
        """
    )
    conn.command(
        f"""
        CREATE TABLE IF NOT EXISTS {db}.tax_rules (
            rule_id UInt32,
            effective_from Date,
            effective_to Nullable(Date),
            rate Float64,
            description String
        ) ENGINE = MergeTree()
        ORDER BY rule_id
        """
    )
    conn.command(
        f"""
        CREATE TABLE IF NOT EXISTS {db}.policy_config (
            config_key String,
            config_value String
        ) ENGINE = MergeTree()
        ORDER BY config_key
        """
    )


def truncate_tables(conn: Client) -> None:
    db = _database()
    for table in TABLES:
        conn.command(f"TRUNCATE TABLE IF EXISTS {db}.{table}")


def fetch_one(conn: Client, sql: str, parameters: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_all(conn, sql, parameters)
    return rows[0] if rows else None


def fetch_all(conn: Client, sql: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = conn.query(sql, parameters=parameters or {})
    return [_normalize_row(row) for row in result.named_results()]


def scalar(conn: Client, sql: str, parameters: dict[str, Any] | None = None) -> Any:
    result = conn.query(sql, parameters=parameters or {})
    if not result.result_rows:
        return None
    return result.result_rows[0][0]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (date, datetime)):
            out[key] = value.isoformat()[:10]
        else:
            out[key] = value
    return out


def get_policy(conn: Optional[Client] = None) -> dict[str, Any]:
    """Return policy thresholds for routing (Person A)."""
    own_conn = conn is None
    db = conn or connect()
    try:
        rows = fetch_all(db, "SELECT config_key, config_value FROM policy_config")
        policy: dict[str, Any] = {}
        for row in rows:
            key, raw = row["config_key"], str(row["config_value"])
            if key in {"high_value_cap", "totals_tolerance", "near_dup_window_days"}:
                policy[key] = float(raw)
            elif key == "auto_pay_enabled":
                policy[key] = raw.lower() == "true"
            else:
                policy[key] = raw
        return policy
    finally:
        if own_conn:
            db.close()


def lookup_vendor(
    conn: Client,
    company: Optional[str],
    gst_id: Optional[str],
) -> Optional[dict[str, Any]]:
    if gst_id:
        row = fetch_one(
            conn,
            "SELECT * FROM vendor_master WHERE gst_id = {gst_id:String} LIMIT 1",
            {"gst_id": gst_id.strip()},
        )
        if row:
            return row
    if company:
        row = fetch_one(
            conn,
            """
            SELECT * FROM vendor_master
            WHERE lower(trimBoth(company_name)) = lower({company:String})
            LIMIT 1
            """,
            {"company": company.strip()},
        )
        if row:
            return row
    return None


def lookup_tax_rate(conn: Client, invoice_date: str) -> Optional[float]:
    row = fetch_one(
        conn,
        """
        SELECT rate FROM tax_rules
        WHERE effective_from <= {invoice_date:Date}
          AND (effective_to IS NULL OR effective_to >= {invoice_date:Date})
        ORDER BY effective_from DESC
        LIMIT 1
        """,
        {"invoice_date": invoice_date},
    )
    return float(row["rate"]) if row else None
