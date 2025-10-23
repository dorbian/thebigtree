# bigtree/webmods/web_admin_config.py
from __future__ import annotations
from aiohttp import web
from typing import Any, Dict
import copy
import bigtree
from bigtree.inc.webserver import route, get_server

_ALLOWED_KEYS = {"base_url", "api_keys", "api_key_scopes", "jwt_secret", "jwt_algorithms"}

def _web_cfg() -> Dict[str, Any]:
    return bigtree.config.config.setdefault("WEB", {})

def _redact(cfg: Dict[str, Any]) -> Dict[str, Any]:
    safe = copy.deepcopy(cfg)
    if "api_keys" in safe:
        safe["api_keys"] = [f"***{k[-4:]}" if isinstance(k, str) and len(k) >= 6 else "***" for k in safe["api_keys"]]
    if "api_key_scopes" in safe:
        # mask keys, keep scopes visible
        safe["api_key_scopes"] = { (f"***{k[-4:]}" if isinstance(k, str) and len(k) >= 6 else "***"): v
                                   for k, v in safe["api_key_scopes"].items() }
    if "jwt_secret" in safe and safe["jwt_secret"]:
        safe["jwt_secret"] = "***redacted***"
    return safe

@route("GET", "/admin/web/config", scopes=["admin:web"])
async def get_web_config(_req: web.Request):
    return web.json_response({"ok": True, "WEB": _redact(_web_cfg())})

@route("PATCH", "/admin/web/config", scopes=["admin:web"])
async def patch_web_config(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    if not isinstance(body, dict):
        return web.json_response({"ok": False, "error": "body must be object"}, status=400)

    cfg = _web_cfg()
    changed = {}
    for k, v in body.items():
        if k not in _ALLOWED_KEYS:
            return web.json_response({"ok": False, "error": f"key '{k}' not allowed"}, status=400)
        cfg[k] = v
        changed[k] = True

    # make changes effective for server internals (host/port still require restart)
    srv = get_server()
    if srv:
        srv.reload_runtime_config()

    return web.json_response({"ok": True, "changed": list(changed.keys()), "WEB": _redact(cfg)})
