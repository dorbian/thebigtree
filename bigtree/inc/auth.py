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
from bigtree.inc.logging import auth_logger

try:
    import jwt  # PyJWT (optional)
    from jwt import InvalidTokenError
except Exception:  # pragma: no cover
    jwt = None
    InvalidTokenError = Exception

TOKEN_COOKIE_NAME = "bt_api_key"

@dataclass
class _Cfg:
    api_keys: Set[str]
    scopes_map: Dict[str, str]
    jwt_secret: Optional[str]
    jwt_algorithms: tuple[str, ...] = ("HS256",)

_AUTH_CFG: Optional[_Cfg] = None


def _cfg() -> _Cfg:
    global _AUTH_CFG
    if _AUTH_CFG is not None:
        return _AUTH_CFG
    c: Dict[str, Any] = {}
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section("WEB")
            if sec is not None:
                # ConfigObj Section: use .get() method to safely extract values
                # DO NOT use dict(sec) — ConfigObj iterates string chars when cast to dict
                c = {
                    "api_keys": sec.get("api_keys") or [],
                    "api_key_scopes": sec.get("api_key_scopes") or {},
                    "jwt_secret": sec.get("jwt_secret") or None,
                    "jwt_algorithms": sec.get("jwt_algorithms") or ["HS256"],
                }
    except Exception:
        c = {}
    # Fallback: load settings directly (avoids reliance on bigtree.settings being set)
    if not c or (not c.get("api_keys") and not c.get("api_key_scopes")):
        try:
            from bigtree.inc.settings import load_settings
            s = load_settings()
            raw_keys = s.get("WEB.api_keys", [], cast="json")
            raw_scopes = s.get("WEB.api_key_scopes", {}, cast="json")
            if raw_keys or raw_scopes:
                c = {"api_keys": raw_keys, "api_key_scopes": raw_scopes}
        except Exception:
            pass
    if not c or (not c.get("api_keys") and not c.get("api_key_scopes")):
        try:
            cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
            c = cfg.get("WEB", {}) or {}
        except Exception:
            c = {}
    _AUTH_CFG = _Cfg(
        api_keys=set(c.get("api_keys", []) or []),
        scopes_map=c.get("api_key_scopes", {}) or {},
        jwt_secret=(c.get("jwt_secret") or None),
        jwt_algorithms=tuple(c.get("jwt_algorithms", ["HS256"])),
    )
    return _AUTH_CFG

def _extract_token(req: web.Request) -> Optional[str]:
    # Priority: Authorization: Bearer <token>, fallback to X-Bigtree-Key / X-API-Key
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    token = req.headers.get("X-Bigtree-Key") or req.headers.get("X-API-Key")
    if token:
        return token
    cookie = req.cookies.get(TOKEN_COOKIE_NAME) if req.cookies else None
    return cookie or None

def _split_scopes(s: str | None) -> Set[str]:
    if not s:
        return set()
    return {x.strip() for x in s.split(",") if x.strip()}

def _scopes_ok(needed: Set[str], granted: Set[str]) -> bool:
    if not needed:
        return True
    if "*" in granted:
        return True
    # Treat route scopes as "any-of" to allow shared admin scopes.
    return any(scope in granted for scope in needed)

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

def _dynamic_token_scopes(token: str) -> Optional[Set[str]]:
    doc = web_tokens.find_token(token)
    if not doc:
        return None
    if "scopes" not in doc:
        return {"*"}
    raw = doc.get("scopes")
    if isinstance(raw, list):
        return {str(x) for x in raw}
    if isinstance(raw, str):
        return _split_scopes(raw)
    return set()

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

def _jwt_scopes(token: str, cfg: _Cfg) -> Optional[Set[str]]:
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

def auth_middleware() -> Callable:
    """
    Aiohttp middleware:
      - Lets public routes / OPTIONS pass
      - Otherwise, accepts either a valid API key, JWT, dynamic token, or Pegas HMAC auth
    Expects handler to carry attribute '_bt_route' with fields: allow_public, scopes (Set[str])
    """
    @web.middleware
    async def _mw(request: web.Request, handler):
        # Resolve route object (wired in inc/webserver.py)
        route_obj = getattr(handler, "_bt_route", None)
        if not route_obj or route_obj.allow_public or request.method == "OPTIONS":
            return await handler(request)

        # ---- Pegas HMAC auth (bypasses normal token auth) ----
        try:
            from bigtree.inc.pegas_auth import is_pegas_request, validate_pegas_request, get_sender_id
        except Exception:
            is_pegas_request = None
            validate_pegas_request = None

        _pegas_ok = is_pegas_request and callable(is_pegas_request) and is_pegas_request(request.headers)
        if _pegas_ok:
            auth_logger.warning("[auth] DEBUG PEGAS OK path=%s method=%s scopes=%s",
                request.path, request.method,
                ",".join(sorted(needed_scopes)) if needed_scopes else "-",
            )
            if validate_pegas_request and callable(validate_pegas_request):
                valid, err, user_id = await validate_pegas_request(request)
                if valid:
                    auth_logger.info("[auth] Pegas HMAC auth success for user_id=%s path=%s", user_id, request.path)
                    request["pegas_authenticated"] = True
                    request["pegas_user_id"] = user_id
                    return await handler(request)
                else:
                    auth_logger.warning("[auth] Pegas HMAC rejected: %s path=%s", err, request.path)
                    return web.json_response({"ok": False, "error": f"Pegas auth failed: {err}"}, status=401)

        cfg = _cfg()
        auth_logger.warning("[auth] DEBUG cfg api_keys=%s scopes_map=%s", cfg.api_keys, cfg.scopes_map)
        needed_scopes: Set[str] = getattr(route_obj, "scopes", set()) or set()
        token = _extract_token(request)
        auth_logger.warning("[auth] DEBUG token=%s", repr(token) if token else "NONE")

        valid = False
        scope_ok = False
        if token:
            if token in cfg.api_keys:
                valid = True
                if not cfg.scopes_map:
                    scope_ok = True
                else:
                    scope_ok = _scopes_ok(needed_scopes, _split_scopes(cfg.scopes_map.get(token)))
            if not scope_ok:
                dyn_scopes = _dynamic_token_scopes(token)
                if dyn_scopes is not None:
                    valid = True
                    scope_ok = _scopes_ok(needed_scopes, dyn_scopes)
            if not scope_ok and cfg.jwt_secret:
                jwt_scopes = _jwt_scopes(token, cfg)
                if jwt_scopes is not None:
                    valid = True
                    scope_ok = _scopes_ok(needed_scopes, jwt_scopes) if needed_scopes else True

        if not valid:
            auth_logger.warning(
                "[auth] unauthorized path=%s method=%s scopes=%s token=%s",
                request.path,
                request.method,
                ",".join(sorted(needed_scopes)) if needed_scopes else "-",
                "yes" if token else "no",
            )
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        if not scope_ok:
            auth_logger.warning(
                "[auth] forbidden path=%s method=%s scopes=%s token=%s",
                request.path,
                request.method,
                ",".join(sorted(needed_scopes)) if needed_scopes else "-",
                "yes",
            )
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)

        return await handler(request)
    return _mw
