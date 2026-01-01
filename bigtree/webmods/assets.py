from __future__ import annotations
from aiohttp import web
from pathlib import Path
from bigtree.inc.webserver import route


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _icon_path() -> Path:
    return _repo_root() / "icon.png"


@route("GET", "/icon.png", allow_public=True)
async def icon_png(_req: web.Request):
    path = _icon_path()
    if not path.exists():
        return web.Response(status=404)
    return web.FileResponse(path)


@route("GET", "/favicon.ico", allow_public=True)
async def favicon_ico(_req: web.Request):
    path = _icon_path()
    if not path.exists():
        return web.Response(status=404)
    return web.FileResponse(path)
