# bigtree/webmods/admin_tokens.py
# Admin panel for managing web tokens
# Routes: list tokens, revoke tokens, issue tokens, view scope documentation

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from aiohttp import web
import json

from bigtree.inc.webserver import route
from bigtree.inc import web_tokens
from bigtree.inc.scope_registry import get_scope_registry, scope_to_dict
from bigtree.inc.database import get_database
from bigtree.inc.logging import auth_logger
from bigtree.inc.auth import TOKEN_COOKIE_NAME

import bigtree


@route("GET", "/admin/tokens", scopes=["admin:*", "admin:web"])
async def list_tokens(req: web.Request) -> web.Response:
    """List all active web tokens with user info and scopes."""
    try:
        include_expired = req.query.get("include_expired", "false").lower() == "true"
        tokens = web_tokens.list_tokens(include_expired=include_expired)
        
        result = []
        for token_doc in tokens:
            # Mask the actual token for security
            masked_token = token_doc.get("token", "")
            if len(masked_token) > 8:
                masked_token = masked_token[:4] + "..." + masked_token[-4:]
            
            scopes = token_doc.get("scopes", [])
            if isinstance(scopes, str):
                scopes = [scopes]
            
            expires_at = token_doc.get("expires_at")
            if isinstance(expires_at, (int, float)):
                expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                expires_str = expires_dt.isoformat()
            elif isinstance(expires_at, str):
                expires_str = expires_at
            else:
                expires_str = None
            
            created_at = token_doc.get("created_at")
            if isinstance(created_at, (int, float)):
                created_dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
                created_str = created_dt.isoformat()
            elif isinstance(created_at, str):
                created_str = created_at
            else:
                created_str = None
            
            revoked_at = token_doc.get("revoked_at")
            if isinstance(revoked_at, (int, float)):
                revoked_dt = datetime.fromtimestamp(revoked_at, tz=timezone.utc)
                revoked_str = revoked_dt.isoformat()
            elif isinstance(revoked_at, str):
                revoked_str = revoked_at
            else:
                revoked_str = None
            
            result.append({
                "token": token_doc.get("token"),  # Full token in API response (admin only)
                "token_masked": masked_token,
                "user_id": token_doc.get("user_id"),
                "user_name": token_doc.get("user_name"),
                "user_icon": token_doc.get("user_icon"),
                "scopes": scopes,
                "created_at": created_str,
                "expires_at": expires_str,
                "revoked": token_doc.get("revoked", False),
                "revoked_at": revoked_str,
            })
        
        return web.json_response({"ok": True, "tokens": result})
    except Exception as exc:
        auth_logger.exception("[admin_tokens] list error")
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=500
        )


@route("POST", "/admin/tokens/{token_id}/revoke", scopes=["admin:*", "admin:web"])
async def revoke_token(req: web.Request) -> web.Response:
    """Revoke a specific token immediately."""
    try:
        token_id = req.match_info.get("token_id", "").strip()
        if not token_id:
            return web.json_response(
                {"ok": False, "error": "token_id required"},
                status=400
            )
        
        success = web_tokens.revoke_token(token_id)
        if success:
            auth_logger.info("[admin_tokens] revoked token=%s", token_id[:8])
            return web.json_response({"ok": True, "revoked": True})
        else:
            return web.json_response(
                {"ok": False, "error": "token not found or already revoked"},
                status=404
            )
    except Exception as exc:
        auth_logger.exception("[admin_tokens] revoke error")
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=500
        )


@route("POST", "/admin/tokens", scopes=["admin:*", "admin:web"])
async def issue_token(req: web.Request) -> web.Response:
    """Issue a new web token with specified scopes."""
    try:
        body = await req.json()
    except Exception:
        return web.json_response(
            {"ok": False, "error": "invalid JSON"},
            status=400
        )
    
    try:
        user_id = body.get("user_id")
        scopes = body.get("scopes", ["*"])
        ttl_seconds = body.get("ttl_seconds", 24 * 60 * 60)
        user_name = body.get("user_name", "")
        user_icon = body.get("user_icon", "")
        discord_id = body.get("discord_id")
        
        if not user_id:
            return web.json_response(
                {"ok": False, "error": "user_id required"},
                status=400
            )
        
        if isinstance(scopes, str):
            scopes = [scopes]
        if not isinstance(scopes, list):
            scopes = ["*"]
        
        try:
            ttl_seconds = int(ttl_seconds)
        except Exception:
            ttl_seconds = 24 * 60 * 60
        
        metadata = {}
        if discord_id is not None:
            try:
                metadata["discord_id"] = int(discord_id)
            except Exception:
                metadata["discord_id"] = str(discord_id)
        doc = web_tokens.issue_token(
            user_id=int(user_id),
            scopes=scopes,
            ttl_seconds=ttl_seconds,
            user_name=user_name or None,
            user_icon=user_icon or None,
            metadata=metadata or None,
        )
        
        auth_logger.info(
            "[admin_tokens] issued user=%s scopes=%s",
            user_id,
            ",".join(doc.get("scopes", []))
        )
        
        expires_at = doc.get("expires_at")
        if isinstance(expires_at, (int, float)):
            expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
            expires_str = expires_dt.isoformat()
        else:
            expires_str = str(expires_at)
        
        return web.json_response({
            "ok": True,
            "token": doc.get("token"),
            "user_id": doc.get("user_id"),
            "scopes": doc.get("scopes", []),
            "expires_at": expires_str,
        })
    except Exception as exc:
        auth_logger.exception("[admin_tokens] issue error")
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=500
        )


@route("GET", "/api/scopes", scopes=["admin:*", "admin:web"])
async def get_scopes(req: web.Request) -> web.Response:
    """Get documentation on all available scopes and which routes they grant access to."""
    try:
        registry = get_scope_registry()
        result = {}
        for scope, info in registry.items():
            result[scope] = scope_to_dict(info)
        
        return web.json_response({
            "ok": True,
            "scopes": result,
            "total_scopes": len(result),
        })
    except Exception as exc:
        auth_logger.exception("[scopes] error")
        return web.json_response(
            {"ok": False, "error": str(exc)},
            status=500
        )


@route("GET", "/admin/dashboard", scopes=["admin:*", "admin:web"], allow_public=True)
async def dashboard_page(req: web.Request) -> web.Response:
    """Serve the token management dashboard HTML. Accepts token via ?token=... query param."""
    # Check auth from query param if not in header/cookie
    token = req.query.get("token")
    if token:
        # Validate token has admin access
        try:
            valid = web_tokens.validate_token(token, {"admin:web", "admin:*"})
            if not valid:
                return web.Response(
                    text="<h1>Access Denied</h1><p>Invalid or insufficient token permissions. Need admin:web or admin:* scope.</p>",
                    content_type="text/html",
                    status=403
                )
        except Exception as e:
            return web.Response(
                text=f"<h1>Auth Error</h1><p>{e}</p>",
                content_type="text/html",
                status=500
            )
    else:
        # No token in query param, check header (handled by middleware)
        # If we got here with allow_public=True but no token, show login prompt
        auth_header = req.headers.get("Authorization", "")
        cookie_token = req.cookies.get(TOKEN_COOKIE_NAME) if req.cookies else None
        if cookie_token:
            try:
                valid = web_tokens.validate_token(cookie_token, {"admin:web", "admin:*"})
                if not valid:
                    return web.Response(
                        text="<h1>Access Denied</h1><p>Invalid or insufficient token permissions. Need admin:web or admin:* scope.</p>",
                        content_type="text/html",
                        status=403
                    )
            except Exception as e:
                return web.Response(
                    text=f"<h1>Auth Error</h1><p>{e}</p>",
                    content_type="text/html",
                    status=500
                )
        elif not auth_header or not auth_header.startswith("Bearer "):
            return web.Response(
                text="""
<!DOCTYPE html>
<html>
<head><title>Login Required</title></head>
<body style="font-family: Arial; padding: 40px; text-align: center;">
<h1>🔐 Authentication Required</h1>
<p>Please provide your admin token to access the dashboard.</p>
<p>Run <code>/auth</code> in Discord to get your token, then visit:</p>
<p><code>http://localhost:8443/admin/dashboard?token=YOUR_TOKEN_HERE</code></p>
</body>
</html>
                """,
                content_type="text/html",
                status=401
            )
    
    try:
        from importlib.resources import files as pkg_files, as_file
        
        # Try to load from package resources
        try:
            files = pkg_files("bigtree.web")
            dashboard_file = files / "admin_dashboard.html"
            with as_file(dashboard_file) as path:
                if path.exists():
                    html = path.read_text("utf-8")
                    return web.Response(text=html, content_type="text/html")
        except Exception:
            pass
        
        # Fallback: return error prompting to create the file
        return web.Response(
            text="""
<!DOCTYPE html>
<html>
<head><title>Dashboard Setup</title></head>
<body>
<h1>Dashboard not yet loaded</h1>
<p>The admin dashboard will be served once created.</p>
<p>Check <a href="/api/scopes">/api/scopes</a> for scope documentation.</p>
<p>Use <a href="/admin/tokens">/admin/tokens</a> API to manage tokens.</p>
</body>
</html>
            """,
            content_type="text/html"
        )
    except Exception as exc:
        auth_logger.exception("[dashboard] error")
        return web.Response(
            text=f"<h1>Error</h1><p>{exc}</p>",
            content_type="text/html",
            status=500
        )
