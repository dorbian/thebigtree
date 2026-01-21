# bigtree/webmods/overlay.py
from aiohttp import web
from bigtree.inc.webserver import route, get_server, DynamicWebServer
from bigtree.inc.database import get_database


def _render_overlay_page() -> str:
    srv: DynamicWebServer | None = get_server()
    admin_background = ""
    try:
        cfg = get_database().get_system_config("overlay") or {}
        raw = str(cfg.get("admin_background") or cfg.get("adminBackground") or "").strip()
        if raw.startswith(("http://", "https://", "/")):
            admin_background = raw.replace('"', "").replace("'", "").strip()
    except Exception:
        admin_background = ""
    if not admin_background:
        admin_background = "/static/images/admin_background.png"
    return srv.render_template("overlay.html", {"ADMIN_BACKGROUND": admin_background}) if srv else "<h1>Overlay</h1>"


@route("GET", "/elfministration", allow_public=True)
async def elfministration_page(_req: web.Request):
    html = _render_overlay_page()
    return web.Response(text=html, content_type="text/html")


@route("GET", "/overlay", allow_public=True)
async def overlay_page(_req: web.Request):
    raise web.HTTPFound("/elfministration")
