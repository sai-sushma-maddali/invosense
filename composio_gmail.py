"""Composio Gmail helpers — connect accounts and check status."""

from __future__ import annotations

import os
import webbrowser
from typing import Any

from composio import Composio


def get_client() -> Composio:
    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        raise ValueError("COMPOSIO_API_KEY is not set in .env")
    return Composio(api_key=api_key)


def get_user_id() -> str:
    return os.getenv("COMPOSIO_USER_ID", "default")


def resolve_gmail_auth_config_id(composio: Composio | None = None) -> str:
    """Return Gmail auth config id from env, or find/create one automatically."""
    configured = os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID")
    if configured:
        return configured

    client = composio or get_client()
    response = client.auth_configs.list(toolkit_slug="gmail")
    items = getattr(response, "items", None) or []

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    if client_id and client_secret:
        for item in items:
            if not getattr(item, "is_composio_managed", True):
                return item.id

        created = client.auth_configs.create(
            "gmail",
            options={
                "name": "ap_agent_gmail_custom",
                "type": "use_custom_auth",
                "auth_scheme": "OAUTH2",
                "credentials": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "oauth_redirect_uri": os.getenv(
                        "GMAIL_OAUTH_REDIRECT_URI",
                        "https://backend.composio.dev/api/v3.1/toolkits/auth/callback",
                    ),
                },
            },
        )
        return created.id

    if items:
        return items[0].id

    created = client.auth_configs.create(
        "gmail",
        options={"type": "use_composio_managed_auth"},
    )
    return created.id


def start_gmail_connection(
    *,
    open_browser: bool = True,
    callback_url: str | None = None,
) -> dict[str, Any]:
    """Generate a Composio OAuth link so the user can connect Gmail."""
    composio = get_client()
    user_id = get_user_id()
    auth_config_id = resolve_gmail_auth_config_id(composio)

    connection = composio.connected_accounts.link(
        user_id=user_id,
        auth_config_id=auth_config_id,
        callback_url=callback_url or os.getenv("COMPOSIO_CALLBACK_URL"),
    )

    redirect_url = connection.redirect_url
    if open_browser and redirect_url:
        webbrowser.open(redirect_url)

    return {
        "user_id": user_id,
        "auth_config_id": auth_config_id,
        "connection_request_id": connection.id,
        "redirect_url": redirect_url,
        "status": connection.status,
        "instructions": "Open redirect_url in a browser, sign in with Gmail, and approve access.",
    }


def wait_for_gmail_connection(
    connection_request_id: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Block until the Gmail connection becomes ACTIVE."""
    composio = get_client()
    connected = composio.connected_accounts.wait_for_connection(
        connection_request_id,
        timeout,
    )
    return {
        "connected_account_id": connected.id,
        "status": connected.status,
        "user_id": get_user_id(),
    }


def get_gmail_connection_status() -> dict[str, Any]:
    """Check whether Gmail is connected for the configured user_id."""
    composio = get_client()
    user_id = get_user_id()

    try:
        auth_config_id = resolve_gmail_auth_config_id(composio)
    except Exception as exc:
        return {
            "connected": False,
            "user_id": user_id,
            "error": str(exc),
        }

    response = composio.connected_accounts.list(
        user_ids=[user_id],
        auth_config_ids=[auth_config_id],
        statuses=["ACTIVE"],
    )
    items = getattr(response, "items", None) or []

    if not items:
        return {
            "connected": False,
            "user_id": user_id,
            "auth_config_id": auth_config_id,
            "message": "No active Gmail connection. Run connect_gmail.py or GET /connect/gmail.",
        }

    account = items[0]
    return {
        "connected": True,
        "user_id": user_id,
        "auth_config_id": auth_config_id,
        "connected_account_id": account.id,
        "status": account.status,
    }
