"""Connect Gmail to Composio using credentials from .env."""

from __future__ import annotations

import argparse
import os
import re
import sys
import webbrowser

from dotenv import load_dotenv

load_dotenv()

from composio import Composio
from composio_gmail import (
    get_client,
    get_gmail_connection_status,
    get_user_id,
    start_gmail_connection,
    wait_for_gmail_connection,
)


def _ensure_custom_auth_config() -> str:
    """Create a Composio auth config from GMAIL_CLIENT_ID / SECRET if needed."""
    configured = os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID")
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env")

    client = get_client()
    redirect = os.getenv(
        "GMAIL_OAUTH_REDIRECT_URI",
        "https://backend.composio.dev/api/v3.1/toolkits/auth/callback",
    )

    if configured:
        return configured

    created = client.auth_configs.create(
        "gmail",
        options={
            "name": "invosense_gmail_custom",
            "type": "use_custom_auth",
            "auth_scheme": "OAUTH2",
            "credentials": {
                "client_id": client_id,
                "client_secret": client_secret,
                "oauth_redirect_uri": redirect,
            },
        },
    )
    auth_id = created.id
    _write_auth_config_id(auth_id)
    print(f"Created auth config: {auth_id} (saved to .env)")
    return auth_id


def _write_auth_config_id(auth_id: str) -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    text = open(env_path, encoding="utf-8").read()
    if re.search(r"^COMPOSIO_GMAIL_AUTH_CONFIG_ID=", text, re.M):
        text = re.sub(
            r"^COMPOSIO_GMAIL_AUTH_CONFIG_ID=.*$",
            f"COMPOSIO_GMAIL_AUTH_CONFIG_ID={auth_id}",
            text,
            flags=re.M,
        )
    else:
        text = text.rstrip() + f"\nCOMPOSIO_GMAIL_AUTH_CONFIG_ID={auth_id}\n"
    open(env_path, "w", encoding="utf-8").write(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect Gmail via Composio")
    parser.add_argument("--status", action="store_true", help="Check connection only")
    parser.add_argument("--wait", action="store_true", help="Wait for OAuth to finish")
    parser.add_argument(
        "--recreate-auth-config",
        action="store_true",
        help="Ignore COMPOSIO_GMAIL_AUTH_CONFIG_ID and create a new auth config",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if not os.getenv("COMPOSIO_API_KEY"):
        print("Error: COMPOSIO_API_KEY is missing in .env", file=sys.stderr)
        return 1

    try:
        get_client()
    except Exception as exc:
        print(f"Error: Composio API key invalid — {exc}", file=sys.stderr)
        print("Get a new key from https://app.composio.dev/settings", file=sys.stderr)
        return 1

    if args.recreate_auth_config:
        os.environ.pop("COMPOSIO_GMAIL_AUTH_CONFIG_ID", None)

    if args.status:
        status = get_gmail_connection_status()
        print(status)
        return 0 if status.get("connected") else 1

    auth_id = _ensure_custom_auth_config()
    os.environ["COMPOSIO_GMAIL_AUTH_CONFIG_ID"] = auth_id

    result = start_gmail_connection(open_browser=not args.no_browser)
    print(f"\nuser_id:       {get_user_id()}")
    print(f"auth_config:   {auth_id}")
    print(f"\nOpen this URL to sign in with Gmail:\n  {result['redirect_url']}\n")

    if args.wait:
        print("Waiting for OAuth (complete sign-in in the browser)...")
        connected = wait_for_gmail_connection(result["connection_request_id"])
        print("Connected:", connected)
        print(get_gmail_connection_status())
    else:
        print("Run with --wait to block until OAuth completes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
