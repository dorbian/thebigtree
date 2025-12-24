# bigtree/webmods/overlay.py
from aiohttp import web
from bigtree.inc.webserver import route, get_server, DynamicWebServer


@route("GET", "/overlay", allow_public=True)
async def overlay_page(_req: web.Request):
    srv: DynamicWebServer | None = get_server()
    upload_base = ""
    if srv:
        upload_base = str(getattr(srv, "_cfg", {}).get("upload_base_url") or "")
    html = srv.render_template("overlay.html", {"UPLOAD_BASE": upload_base}) if srv else "<h1>Overlay</h1>"
    return web.Response(text=html, content_type="text/html")
