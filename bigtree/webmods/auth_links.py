# bigtree/webmods/auth_links.py
from __future__ import annotations
from aiohttp import web
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
import os
import time
import json
import bigtree
from bigtree.inc.webserver import route, get_server, DynamicWebServer
from bigtree.inc.logging import auth_logger
from bigtree.inc import web_tokens
from bigtree.inc import temp_links
from bigtree.inc import auth as auth_mod

try:
    import jwt  # PyJWT (optional)
    from jwt import InvalidTokenError
except Exception:  # pragma: no cover
    jwt = None
    InvalidTokenError = Exception


def _read_role_scopes() -> Dict[str, list[str]]:
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section("BOT")
            if isinstance(sec, dict) and "auth_role_scopes" in sec:
                return sec.get("auth_role_scopes") or {}
            return bigtree.settings.get("BOT.auth_role_scopes", {}, cast="json") or {}
    except Exception:
        pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        sec = cfg.get("BOT", {}) or {}
        role_scopes = sec.get("auth_role_scopes") or {}
        if role_scopes:
            return role_scopes
    except Exception:
        role_scopes = {}
    path = _auth_roles_path()
    if not path:
        return role_scopes or {}
    return _read_auth_roles_file(path) or {}


def _auth_roles_path() -> Path | None:
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            base = bigtree.settings.get("BOT.DATA_DIR", None)
        else:
            base = None
    except Exception:
        base = None
    if not base:
        base = getattr(bigtree, "datadir", None)
    if not base:
        return None
    return Path(base) / "auth_roles.json"


def _read_auth_roles_file(path: Path) -> Dict[str, list[str]]:
    try:
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}
    return {}

def _split_scopes(raw: str | None) -> Set[str]:
    if not raw:
        return set()
    return {s.strip() for s in raw.split(",") if s.strip()}

def _extract_token(req: web.Request) -> str:
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    return req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key") or ""

def _jwt_scopes(token: str) -> Optional[Set[str]]:
    cfg = auth_mod._cfg()
    if not cfg.jwt_secret or jwt is None:
        return None
    try:
        claims = jwt.decode(token, cfg.jwt_secret, algorithms=list(cfg.jwt_algorithms), options={"verify_aud": False})
    except InvalidTokenError:
        return None
    raw = claims.get("scopes")
    if isinstance(raw, list):
        return {str(x) for x in raw}
    if isinstance(raw, str):
        return _split_scopes(raw)
    return set()

def _get_token_scopes(token: str) -> Optional[Set[str]]:
    if not token:
        return None
    cfg = auth_mod._cfg()
    if token in cfg.api_keys:
        if not cfg.scopes_map:
            return {"*"}
        return _split_scopes(cfg.scopes_map.get(token))
    doc = web_tokens.find_token(token)
    if doc:
        if "scopes" not in doc:
            return {"*"}
        raw = doc.get("scopes")
        if isinstance(raw, list):
            return {str(x) for x in raw}
        if isinstance(raw, str):
            return _split_scopes(raw)
        return set()
    return _jwt_scopes(token)

def _scopes_allowed(requested: List[str], caller_scopes: Set[str]) -> bool:
    if "*" in caller_scopes:
        return True
    return all(scope in caller_scopes for scope in requested)


def _resolve_scopes(role_ids: List[str], scopes: List[str]) -> List[str]:
    if scopes:
        return [s for s in scopes if s]
    if not role_ids:
        return []
    role_scopes = _read_role_scopes()
    resolved: List[str] = []
    for role_id in role_ids:
        raw = role_scopes.get(str(role_id), []) or []
        if isinstance(raw, str):
            raw = [s.strip() for s in raw.split(",") if s.strip()]
        for scope in raw:
            if scope not in resolved:
                resolved.append(scope)
    return resolved


@route("POST", "/api/auth/temp-links", scopes=["admin:web"])
async def create_temp_link(req: web.Request):
    try:
        payload = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    role_ids = payload.get("role_ids") or []
    if isinstance(role_ids, str):
        role_ids = [role_ids]
    role_ids = [str(x).strip() for x in role_ids if str(x).strip()]

    scopes = payload.get("scopes") or []
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split(",") if s.strip()]
    else:
        scopes = [str(s).strip() for s in scopes if str(s).strip()]

    ttl_seconds = int(payload.get("ttl_seconds") or 0)
    if ttl_seconds <= 0:
        ttl_seconds = temp_links.LINK_TTL_SECONDS

    resolved = _resolve_scopes(role_ids, scopes)
    if not resolved:
        return web.json_response({"ok": False, "error": "No scopes selected."}, status=400)
    caller_scopes = _get_token_scopes(_extract_token(req)) or set()
    if not _scopes_allowed(resolved, caller_scopes):
        auth_logger.warning("[auth] temp link denied scopes=%s caller=%s", resolved, ",".join(sorted(caller_scopes)))
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    doc = temp_links.issue_link(resolved, ttl_seconds=ttl_seconds, role_ids=role_ids)
    base_url = f"{req.scheme}://{req.host}".rstrip("/")
    link_url = f"{base_url}/auth/temp/{doc['token']}"
    auth_logger.info("[auth] temp link issued scopes=%s ttl=%s", resolved, ttl_seconds)
    return web.json_response({
        "ok": True,
        "link_url": link_url,
        "expires_at": doc.get("expires_at"),
        "scopes": resolved,
    })


@route("GET", "/auth/temp/{token}", allow_public=True)
async def temp_login_page(req: web.Request):
    token = req.match_info.get("token") or ""
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("temp_login.html", {"TOKEN": token}) if srv else "<h1>Temporary Access</h1>"
    return web.Response(text=html, content_type="text/html")


@route("POST", "/auth/temp/{token}", allow_public=True)
async def temp_login_submit(req: web.Request):
    token = req.match_info.get("token") or ""
    try:
        payload = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    name = str(payload.get("name") or "").strip()
    if not name:
        return web.json_response({"ok": False, "error": "Name required."}, status=400)

    link = temp_links.consume_link(token, name)
    if not link:
        return web.json_response({"ok": False, "error": "Link invalid or expired."}, status=404)

    scopes = link.get("scopes") or []
    user_id = int(time.time())
    doc = web_tokens.issue_token(user_id=user_id, scopes=scopes, ttl_seconds=temp_links.LINK_TTL_SECONDS, user_name=name)
    now = int(time.time())
    expires_at = int(doc.get("expires_at") or 0)
    return web.json_response({
        "ok": True,
        "token": doc.get("token"),
        "scopes": scopes,
        "user_name": name,
        "expires_at": expires_at,
        "expires_in": max(0, expires_at - now),
        "redirect": "/overlay",
    })
