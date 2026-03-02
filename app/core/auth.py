"""
Centralized authentication helpers for the Nexus-Chatbot API.

Provides FastAPI dependencies that can be used at the router or
individual endpoint level to enforce authentication.
"""

import hashlib
import hmac
from typing import Optional

from fastapi import Header, HTTPException, Request

from app.core.config import settings


# ── API Key guard (internal / admin endpoints) ─────────────────────

def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
) -> None:
    """Validate the ``X-Api-Key`` header against ``API_SECRET``.

    Use as a FastAPI dependency on routers or endpoints that should only
    be accessible by trusted callers (the Nexus-App frontend, admin
    scripts, etc.).
    """
    if not settings.api_secret:
        raise HTTPException(
            status_code=500,
            detail="API_SECRET is not configured on the server",
        )
    if not x_api_key or x_api_key != settings.api_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── CRON / queue bearer-token guard ────────────────────────────────

def require_cron_secret(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Validate the ``Authorization: Bearer <CRON_SECRET>`` header.

    Used by Supabase Edge Functions and scheduled cron jobs to call
    ``/api/whatsapp/process``.
    """
    if not settings.cron_secret:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured on the server",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── WhatsApp webhook HMAC signature verification ──────────────────

async def verify_webhook_signature(request: Request) -> None:
    """Verify the ``X-Hub-Signature-256`` header sent by Meta.

    Meta signs every webhook payload with HMAC-SHA256 using the *App
    Secret* of your Facebook/WhatsApp application.  This dependency
    reads the raw body, computes the expected signature and compares
    it (constant-time) with the one provided in the header.

    If ``WHATSAPP_APP_SECRET`` is not configured the check is skipped
    (with a warning) so that local development is not blocked.
    """
    app_secret = settings.whatsapp_app_secret
    if not app_secret:
        # Allow operation but warn — should be set in production
        print(
            "[security] WARNING: WHATSAPP_APP_SECRET not set, "
            "skipping webhook signature verification"
        )
        return

    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Hub-Signature-256 header",
        )

    body = await request.body()
    expected_signature = (
        "sha256="
        + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(
            status_code=403,
            detail="Invalid webhook signature",
        )
