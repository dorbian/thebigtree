# bigtree/inc/webserver.py
from __future__ import annotations
import asyncio, importlib, pkgutil, logging
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Set, Optional
from aiohttp import web, WSMsgType
from aiohttp.http_exceptions import InvalidURLError
from importlib.resources import files as pkg_files, as_file
import bigtree
from bigtree.inc.auth import auth_middleware  # <-- NEW

log = getattr(bigtree, "logger", logging.getLogger("bigtree"))

@dataclass
class APIRoute:
    method: str
    path: str
    handler: Callable
    scopes: Set[str] = field(default_factory=set)
    allow_public: bool = False

_registry: List[APIRoute] = []
def clear_registry(): _registry.clear()

def route(method: str, path: str, *, scopes: List[str] | None = None, allow_public: bool=False):
    method = method.upper()
    def deco(fn):
        _registry.append(APIRoute(method, path, fn, set(scopes or []), allow_public))
        return fn
    return deco

def frontend_route(method: str, path: str, *, scopes: List[str] | None = None, allow_public: bool=False):
    """Register a route only if frontend serving is enabled."""
    method = method.upper()
    def deco(fn):
        cfg = _cfg()
        if cfg.get("serve_frontend", True):
            _registry.append(APIRoute(method, path, fn, set(scopes or []), allow_public))
        return fn
    return deco

def _cfg():
    # Preferred: new settings loader
    st = getattr(bigtree, "settings", None)
    if st is not None:
        host = st.get("WEB.listen_host", "0.0.0.0")
        port = st.get("WEB.listen_port", 8443, int)
        base = st.get("WEB.base_url", f"http://{host}:{port}")
        cors = st.get("webapi.cors_origin", "*")  # legacy CORS if you still keep it there
        jwt_secret = st.get("WEB.jwt_secret", "")
        jwt_algs = st.get("WEB.jwt_algorithms", ["HS256"], cast="json")
        api_keys = st.get("WEB.api_keys", [], cast="json")
        scopes   = st.get("WEB.api_key_scopes", {}, cast="json")
        max_mb = st.get("WEB.client_max_size_mb", 32, int)
        serve_frontend = st.get("WEB.serve_frontend", True, bool)
        return {
            "host": host, "port": port, "base_url": base,
            "cors_origin": cors,
            "jwt_secret": jwt_secret, "jwt_algorithms": jwt_algs,
            "api_keys": api_keys, "api_key_scopes": scopes,
            "client_max_size": max(1, int(max_mb)) * 1024 * 1024,
            "serve_frontend": serve_frontend,
        }

    # Fallback: legacy ConfigObj path (old code paths)
    cfg = getattr(bigtree, "config", None)
    if cfg and getattr(cfg, "config", None):
        web = cfg.config.get("WEB", {}) or {}
        host = web.get("listen_host", "0.0.0.0")
        try:
            port = int(str(web.get("listen_port", 8443)))
        except Exception:
            port = 8443
        base = (web.get("base_url") or f"http://{host}:{port}").rstrip("/")
        cors = (cfg.config.get("webapi", {}).get("cors_origin") or "*")
        max_mb = web.get("client_max_size_mb", 32)
        try:
            max_mb = int(str(max_mb))
        except Exception:
            max_mb = 32
        return {
            "host": host, "port": port, "base_url": base,
            "cors_origin": cors,
            "jwt_secret": web.get("jwt_secret", ""),
            "jwt_algorithms": web.get("jwt_algorithms", ["HS256"]),
            "api_keys": web.get("api_keys", []),
            "api_key_scopes": web.get("api_key_scopes", {}),
            "client_max_size": max(1, int(max_mb)) * 1024 * 1024,
        }

    # Last resort defaults
    return {
        "host": "0.0.0.0", "port": 8443, "base_url": "http://0.0.0.0:8443",
        "cors_origin": "*", "jwt_secret": "", "jwt_algorithms": ["HS256"],
        "api_keys": [], "api_key_scopes": {},
        "client_max_size": 32 * 1024 * 1024,
        "serve_frontend": True,
    }

class DynamicWebServer:
    def __init__(self):
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.ws_active: Set[web.WebSocketResponse] = set()
        self._cfg = _cfg()
        # middlewares: CORS + (externalized) AUTH
        self.app = web.Application(
            middlewares=[self._cors_mw, auth_middleware()],
            client_max_size=int(self._cfg.get("client_max_size") or 32 * 1024 * 1024),
        )

        self.app["ws_active"] = self.ws_active
    def reload_runtime_config(self):
        """Refresh in-memory WEB config (host/port changes require restart)."""
        self._cfg = _cfg()
        log.info("[web] runtime config reloaded (host/port changes require restart)")

    def _attach(self, route_obj: APIRoute, handler):
        # prevent duplicates when re-wiring after reloads
        if not hasattr(self, "_registered"):
            self._registered = set()
        key = (route_obj.method if route_obj.method != "WS" else "GET", route_obj.path)
        if key in self._registered:
            return
        self._registered.add(key)
        handler._bt_route = route_obj
        self.app.router.add_route(key[0], key[1], handler)
    
    def serves_frontend(self) -> bool:
        """Check if frontend HTML/static serving is enabled."""
        return self._cfg.get("serve_frontend", True)
    # ---------- Template loader ----------
    @staticmethod
    def render_template(relpath: str, mapping: Dict[str, str]) -> str:
        """
        Load and render a template file with variable substitution.
        
        Args:
            relpath: Relative path to template in bigtree.web.templates
            mapping: Dictionary of variables to substitute in template
        
        Returns:
            Rendered template string, or empty string if template not found
        """
        pkg = "bigtree.web.templates"
        try:
            p = pkg_files(pkg).joinpath(relpath)
            with as_file(p) as fp:
                txt = fp.read_text(encoding="utf-8")
        except FileNotFoundError as e:
            log.error(f"[web] template not found: {pkg}/{relpath}")
            txt = ""
        except (OSError, IOError) as e:
            log.error(f"[web] template read error: {pkg}/{relpath}: {e}")
            txt = ""
        
        if not txt:
            return txt
            
        try:
            return txt.format(**mapping)
        except KeyError as e:
            # Missing template variable - log and fallback
            log.warning(f"[web] template missing variable {e}: {relpath}")
            for key, val in (mapping or {}).items():
                txt = txt.replace("{" + str(key) + "}", str(val))
            return txt
        except Exception as e:
            # Other formatting errors - fallback to simple replacement
            log.warning(f"[web] template format error: {relpath}: {e}")
            for key, val in (mapping or {}).items():
                txt = txt.replace("{" + str(key) + "}", str(val))
            return txt

    # ---------- CORS ----------
    @web.middleware
    async def _cors_mw(self, request: web.Request, handler):
        if request.method == "OPTIONS":
            resp = web.Response()
        else:
            try:
                resp = await handler(request)
            except InvalidURLError:
                return web.Response(status=400, text="bad request")
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, X-Bigtree-Key, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp

    # ---------- Boot / Stop ----------
    async def start(self):
        self._load_modules()
        self._wire_routes()
        host, port = self._cfg["host"], self._cfg["port"]
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()
        log.info(f"[web] listening on {host}:{port} (base_url={self._cfg['base_url']})")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner, self._site = None, None
        log.info("[web] stopped")

    # ---------- Loader ----------
    def _load_modules(self):
        try:
            import bigtree.webmods as pkg
        except Exception:
            log.warning("bigtree.webmods package not found; create bigtree/webmods/__init__.py")
            return
        base = pkg.__name__
        for modinfo in pkgutil.iter_modules(pkg.__path__):
            fullname = f"{base}.{modinfo.name}"
            importlib.import_module(fullname)
            log.info(f"[web] loaded module {fullname}")

    def _wire_routes(self):
        for r in _registry:
            if r.method == "WS":
                async def ws_handler(request, __fn=r.handler, __self=self):
                    ws = web.WebSocketResponse()
                    await ws.prepare(request)
                    __self.ws_active.add(ws)
                    try:
                        async for msg in ws:
                            if msg.type == WSMsgType.TEXT:
                                await __fn(request, ws, msg.data)
                    finally:
                        __self.ws_active.discard(ws)
                    return ws
                self._attach(r, ws_handler)
            else:
                async def http_handler(request, __fn=r.handler):
                    return await __fn(request)
                self._attach(r, http_handler)



    # ---------- Utilities ----------
    async def broadcast(self, payload: Dict[str, Any]):
        for ws in list(self.ws_active):
            try: await ws.send_json(payload)
            except Exception: self.ws_active.discard(ws)

_server: Optional[DynamicWebServer] = None

async def ensure_webserver() -> DynamicWebServer:
    global _server
    if _server: return _server
    _server = DynamicWebServer()
    await _server.start()
    return _server

def get_server() -> Optional[DynamicWebServer]:
    return _server
