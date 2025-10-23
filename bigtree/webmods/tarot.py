# bigtree/webmods/tarot.py
from aiohttp import web
from bigtree.inc.webserver import route, get_server, ensure_webserver, DynamicWebServer
from bigtree.modules import tarot as tar

@route("GET", "/api/tarot/session/{sid}", allow_public=True)
async def get_state(request: web.Request):
    sid = request.match_info["sid"]
    s = tar.get_session(sid)
    return web.json_response({"ok": True, "session": s})

@route("GET", "/tarot/session/{sid}", allow_public=True)
async def viewer(request: web.Request):
    sid = request.match_info["sid"]
    view = request.query.get("view","follower")
    srv: DynamicWebServer | None = get_server()
    html = (srv.render_template("tarot.html", {"SID": sid, "VIEW": view}) if srv
            else "<h1>Tarrot</h1><p>Server not initialized</p>")
    return web.Response(text=html, content_type="text/html")

@route("WS", "/ws/tarot/{sid}", allow_public=True)
async def ws_handler(_request: web.Request, _ws, _msg_text: str):
    # viewer sockets don't send control; Discord commands drive updates
    return

@route("POST", "/api/tarot/push/{sid}", scopes=["tarot:control"])
async def push_state(request: web.Request):
    sid = request.match_info["sid"]
    s = tar.get_session(sid)
    if not s: return web.json_response({"ok": False, "error": "not found"}, status=404)
    srv = get_server()
    if srv: await srv.broadcast({"type":"tarot_state","sid":sid,"state": s["state"]})
    return web.json_response({"ok": True})
