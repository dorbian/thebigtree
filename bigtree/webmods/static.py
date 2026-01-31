from __future__ import annotations
from aiohttp import web
from pathlib import Path
from bigtree.inc.webserver import frontend_route


def _static_root() -> Path:
    return Path(__file__).resolve().parents[1] / "web" / "static"


@frontend_route("GET", "/static/{path:.*}", allow_public=True)
async def static_file(req: web.Request):
    rel = req.match_info["path"]
    if not rel or rel.endswith("/"):
        return web.Response(status=404)
    base = _static_root()
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return web.Response(status=404)
    if not target.exists() or not target.is_file():
        return web.Response(status=404)
    resp = web.FileResponse(target)
    resp.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return resp
