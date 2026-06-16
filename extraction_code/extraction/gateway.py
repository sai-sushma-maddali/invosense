"""TrueFoundry AI Gateway client.

The gateway is OpenAI-compatible, so we drive it with the standard ``openai``
SDK pointed at the gateway base URL. Routing every call through the gateway
means usage and cost are logged centrally by TrueFoundry.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class GatewayConfigError(RuntimeError):
    """Raised when required TrueFoundry settings are missing."""


@dataclass
class GatewayConfig:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        base_url = os.getenv("TFY_GATEWAY_URL", "").strip()
        api_key = os.getenv("TFY_API_KEY", "").strip()
        model = os.getenv("TFY_MODEL", "").strip()
        missing = [
            name
            for name, val in (
                ("TFY_GATEWAY_URL", base_url),
                ("TFY_API_KEY", api_key),
                ("TFY_MODEL", model),
            )
            if not val
        ]
        if missing:
            raise GatewayConfigError(
                "Missing required env vars: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in the values."
            )
        return cls(base_url=base_url, api_key=api_key, model=model)


def build_client(config: Optional[GatewayConfig] = None):
    """Create an OpenAI client bound to the TrueFoundry gateway."""
    from openai import OpenAI  # imported lazily so the module imports without the dep

    cfg = config or GatewayConfig.from_env()
    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)


def image_to_data_uri(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Encode raw image bytes as a base64 ``data:`` URI for the vision API."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def sniff_mime(image_bytes: bytes) -> str:
    """Best-effort MIME detection from magic bytes (jpeg/png/webp)."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"
