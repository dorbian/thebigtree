# bigtree/inc/pegas_auth.py
"""
Pegas HMAC mutual-auth middleware for BigTree.

Setup flow:
  1. Dorbian registers Pegas via POST /admin/pegas/register
     → stores the secret hash in bigtree config
  2. Pegas calls APIs with:
       X-Pegas-Signature: HMAC-SHA256(timestamp + method + path + body, secret)
       X-Pegas-Timestamp: unix timestamp
       X-Pegas-Identity: pegas
  3. This middleware validates the signature and binds requests to Dorbian's identity.

Only Dorbian (sender_id 212401699531390977) can register the secret.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

try:
    import bigtree
    from bigtree.inc.logging import logger
except Exception:
    bigtree = None
    logger = print

PEGAS_SECRET_CONFIG_KEY = "PEGAS_SHARED_SECRET"
PEGAS_IDENTITY_CONFIG_KEY = "PEGAS_IDENTITY"
PEGAS_SENDER_ID_CONFIG_KEY = "PEGAS_SENDER_ID"
PEGAS_TIMESTAMP_TTL = 300  # 5 minutes — prevents replay attacks


def get_secret() -> Optional[str]:
    """Fetch the stored shared secret from bigtree config."""
    try:
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(f"BOT.{PEGAS_SECRET_CONFIG_KEY}", None)
    except Exception:
        pass
    return os.getenv(f"BIGTREE__BOT__{PEGAS_SECRET_CONFIG_KEY}", None)


def get_sender_id() -> int:
    """Dorbian's Discord user ID — the only allowed sender."""
    try:
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            val = bigtree.settings.get(f"BOT.{PEGAS_SENDER_ID_CONFIG_KEY}", None)
            if val:
                return int(val)
    except Exception:
        pass
    return int(os.getenv(f"BIGTREE__BOT__{PEGAS_SENDER_ID_CONFIG_KEY}", "212401699531390977"))


def get_identity() -> str:
    """Pegas identity label."""
    try:
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(f"BOT.{PEGAS_IDENTITY_CONFIG_KEY}", "pegas")
    except Exception:
        pass
    return os.getenv(f"BIGTREE__BOT__{PEGAS_IDENTITY_CONFIG_KEY}", "pegas")


def store_secret(secret: str, sender_id: int, identity: str) -> bool:
    """Persist the shared secret to bigtree config."""
    try:
        from configobj import ConfigObj
        from bigtree.inc.settings import load_settings
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            path = getattr(bigtree.settings, "path", "") or os.path.expanduser("~/.config/bigtree.ini")
        else:
            path = os.path.expanduser("~/.config/bigtree.ini")
        cfg = ConfigObj(str(path), encoding="utf-8")
        cfg.setdefault("BOT", {})
        cfg["BOT"]["PEGAS_SHARED_SECRET"] = secret
        cfg["BOT"]["PEGAS_IDENTITY"] = identity
        cfg["BOT"]["PEGAS_SENDER_ID"] = str(sender_id)
        cfg.write()
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            bigtree.settings = load_settings(path)
        logger.info("[pegas_auth] Secret stored successfully")
        return True
    except Exception as e:
        if logger:
            logger.warning(f"[pegas_auth] Failed to store secret: {e}")
        return False


def clear_secret() -> bool:
    """Remove the stored shared secret."""
    try:
        from configobj import ConfigObj
        from bigtree.inc.settings import load_settings
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            path = getattr(bigtree.settings, "path", "") or os.path.expanduser("~/.config/bigtree.ini")
        else:
            path = os.path.expanduser("~/.config/bigtree.ini")
        cfg = ConfigObj(str(path), encoding="utf-8")
        cfg["BOT"].pop("PEGAS_SHARED_SECRET", None)
        cfg["BOT"].pop("PEGAS_IDENTITY", None)
        cfg["BOT"].pop("PEGAS_SENDER_ID", None)
        cfg.write()
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            bigtree.settings = load_settings(path)
        return True
    except Exception as e:
        if logger:
            logger.warning(f"[pegas_auth] Failed to clear secret: {e}")
        return False


def compute_signature(timestamp: str, method: str, path: str, body: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for a request."""
    payload = f"{timestamp}{method.upper()}{path}{body}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_signature(
    signature: str,
    timestamp: str,
    method: str,
    path: str,
    body: str,
    secret: str,
) -> bool:
    """Verify a signature against the shared secret."""
    expected = compute_signature(timestamp, method, path, body, secret)
    return hmac.compare_digest(expected, signature)


def is_pegas_request(headers) -> bool:
    """Check if this request has Pegas auth headers."""
    return (
        bool(headers.get("X-Pegas-Signature"))
        and bool(headers.get("X-Pegas-Timestamp"))
        and bool(headers.get("X-Pegas-Identity"))
    )


async def validate_pegas_request(request) -> tuple[bool, str, int]:
    """
    Validate a Pegas-authenticated request.
    Returns (success, error_message, effective_user_id).
    On success: (True, "", Dorbian's user_id)
    On failure: (False, error_reason, 0)
    """
    headers = request.headers

    signature = headers.get("X-Pegas-Signature", "")
    timestamp = headers.get("X-Pegas-Timestamp", "")
    identity = headers.get("X-Pegas-Identity", "")

    secret = get_secret()
    if not secret:
        return False, "Pegas auth not configured (no secret stored)", 0

    # Verify identity matches
    expected_identity = get_identity()
    if identity != expected_identity:
        return False, f"Unknown Pegas identity: {identity}", 0

    # Timestamp freshness check
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False, "Invalid timestamp format", 0

    now = int(time.time())
    if abs(now - ts) > PEGAS_TIMESTAMP_TTL:
        return False, f"Timestamp expired or too far in future (delta={abs(now-ts)}s, max={PEGAS_TIMESTAMP_TTL}s)", 0

    # Reconstruct body (aiohttp body is async stream, must await)
    body = ""
    try:
        body_bytes = await request.read()
        body = body_bytes.decode("utf-8")
    except Exception:
        body = ""

    # Verify signature
    path = request.path
    method = request.method

    if not verify_signature(signature, timestamp, method, path, body, secret):
        return False, "Invalid signature", 0

    # Signature valid — bind to Dorbian's user ID
    sender_id = get_sender_id()
    return True, "", sender_id


def pegas_auth_middleware(app):
    """
    Middleware factory that wraps an aiohttp app.
    Intercepts requests with Pegas headers and validates them BEFORE normal auth.
    On success, injects a synthetic auth token for downstream route scope checking.
    """
    @web.middleware
    async def middleware(request, handler):
        if not is_pegas_request(request.headers):
            return await handler(request)

        valid, err, user_id = await validate_pegas_request(request)
        if not valid:
            logger.warning(f"[pegas_auth] Rejected: {err} | path={request.path}")
            return web.Response(status=401, text=f"Pegas auth failed: {err}")

        # Auth succeeded — inject synthetic auth for scope checking
        # We set fake Authorization so normal scope resolution works downstream
        request.headers["Authorization"] = f"Bearer pegas_magic_token"
        request["pegas_authenticated"] = True
        request["pegas_user_id"] = user_id

        logger.info(f"[pegas_auth] Accepted request from Pegas for user_id={user_id} path={request.path}")
        return await handler(request)

    # Apply to app only if we can import web
    try:
        from aiohttp import web
        app.middlewares.append(middleware)
    except Exception:
        pass

    return middleware