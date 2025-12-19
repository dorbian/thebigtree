# bigtree/inc/auth.py
# Central auth middleware for BigTree's dynamic web stack.
# Supports:
#   - API keys (X-Bigtree-Key / X-API-Key / Authorization: Bearer <KEY>)
#   - Optional JWT (Authorization: Bearer <JWT>) with shared secret
# Scopes:
#   - API keys: WEB.api_key_scopes maps KEY -> "scope1,scope2"
#   - JWT: if claim "scopes" exists (list or comma-string), enforce it; otherwise allow if route has no scopes

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Set, Dict, Any, Callable
from aiohttp import web
import bigtree
from bigtree.inc import web_tokens

try:
    import jwt  # PyJWT (optional)
    from jwt import InvalidTokenError
except Exception:  # pragma: no cover
    jwt = None
    InvalidTokenError = Exception

@dataclass
class _Cfg:
    api_keys: Set[str]
    scopes_map: Dict[str, str]
    jwt_secret: Optional[str]
    jwt_algorithms: tuple[str, ...] = ("HS256",)

def _cfg() -> _Cfg:
    c = bigtree.config.config.get("WEB", {})
    return _Cfg(
        api_keys=set(c.get("api_keys", []) or []),
        scopes_map=c.get("api_key_scopes", {}) or {},
        jwt_secret=(c.get("jwt_secret") or None),
        jwt_algorithms=tuple(c.get("jwt_algorithms", ["HS256"])),
    )

def _extract_token(req: web.Request) -> Optional[str]:
    # Priority: Authorization: Bearer <token>, fallback to X-Bigtree-Key / X-API-Key
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    return req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key")

def _split_scopes(s: str | None) -> Set[str]:
    if not s:
        return set()
    return {x.strip() for x in s.split(",") if x.strip()}

def _scopes_ok(needed: Set[str], granted: Set[str]) -> bool:
    if not needed:
        return True
    if "*" in granted:
        return True
    return needed.issubset(granted)

def _verify_api_key(token: str, cfg: _Cfg, needed: Set[str]) -> bool:
    if token not in cfg.api_keys:
        return False
    # If no scopes map is configured, any key is full-power:
    if not cfg.scopes_map:
        return True
    return _scopes_ok(needed, _split_scopes(cfg.scopes_map.get(token)))

def _verify_dynamic_token(token: str, needed: Set[str]) -> bool:
    try:
        return web_tokens.validate_token(token, needed)
    except Exception:
        return False

def _verify_jwt(token: str, cfg: _Cfg, needed: Set[str]) -> bool:
    if not cfg.jwt_secret or jwt is None:
        return False
    try:
        claims = jwt.decode(token, cfg.jwt_secret, algorithms=list(cfg.jwt_algorithms), options={"verify_aud": False})
    except InvalidTokenError:
        return False
    # If the token carries scopes, enforce them. If not, allow only if no route-scopes are required.
    raw = claims.get("scopes")
    granted: Set[str]
    if isinstance(raw, list):
        granted = {str(x) for x in raw}
    elif isinstance(raw, str):
        granted = _split_scopes(raw)
    else:
        granted = set()
    return _scopes_ok(needed, granted) if needed else True

def auth_middleware() -> Callable:
    """
    Aiohttp middleware:
      - Lets public routes / OPTIONS pass
      - Otherwise, accepts either a valid API key or a valid JWT
    Expects handler to carry attribute '_bt_route' with fields: allow_public, scopes (Set[str])
    """
    @web.middleware
    async def _mw(request: web.Request, handler):
        # Resolve route object (wired in inc/webserver.py)
        route_obj = getattr(handler, "_bt_route", None)
        if not route_obj or route_obj.allow_public or request.method == "OPTIONS":
            return await handler(request)

        cfg = _cfg()
        needed_scopes: Set[str] = getattr(route_obj, "scopes", set()) or set()
        token = _extract_token(request)

        ok = False
        if token:
            # Try API key first
            ok = _verify_api_key(token, cfg, needed_scopes)
            if not ok:
                ok = _verify_dynamic_token(token, needed_scopes)
            # If that didn't match, try JWT (if configured)
            if not ok and cfg.jwt_secret:
                ok = _verify_jwt(token, cfg, needed_scopes)

        if not ok:
            # Be explicit but non-leaky
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

        return await handler(request)
    return _mw
