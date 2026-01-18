# bigtree/webmods/overlay.py
from aiohttp import web
from bigtree.inc.webserver import route, get_server, DynamicWebServer
from bigtree.inc.database import get_database


@route("GET", "/overlay", allow_public=True)
async def overlay_page(_req: web.Request):
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
    html = srv.render_template("overlay.html", {"ADMIN_BACKGROUND": admin_background}) if srv else "<h1>Overlay</h1>"
    return web.Response(text=html, content_type="text/html")
