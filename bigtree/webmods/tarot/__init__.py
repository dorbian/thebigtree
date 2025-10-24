from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional
from aiohttp import web
try:
    import bigtree
except Exception:
    bigtree = None
def _settings_get(section: str, key: str, default=None):
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(section, {}).get(key, default)
    except Exception: pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        return cfg.get(section, {}).get(key, default)
    except Exception: pass
    return default
def _data_dir() -> Path:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", ".")
    p = Path(base) / "tarot"; (p / "sessions").mkdir(parents=True, exist_ok=True); return p
DECK = _data_dir()/ "deck.json"; SESS = _data_dir()/ "sessions"
def _load_json(p: Path, default):
    if not p.exists(): return default
    try: return json.loads(p.read_text("utf-8"))
    except Exception: return default
def _save_json(p: Path, data: Any): p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
def _find_session_by_token(token: str, kind: str) -> Optional[dict]:
    for fp in SESS.glob("*.json"):
        doc = _load_json(fp, {}); 
        if doc.get(f"{kind}_token") == token: return doc
    return None
async def tarot_client_page(request: web.Request): return web.FileResponse(Path(__file__).parent / "templates" / "client.html")
async def tarot_admin_page(request: web.Request): return web.FileResponse(Path(__file__).parent / "templates" / "admin.html")
async def api_get_session_client(request: web.Request):
    token = request.match_info["public_token"]; doc = _find_session_by_token(token, "public")
    if not doc: return web.json_response({"error":"not_found"}, status=404)
    return web.json_response({"id":doc["id"],"subject":doc["subject"],"spread":doc["spread"],"cards":doc.get("cards",[]),"closed":doc.get("closed",False)})
async def api_get_session_admin(request: web.Request):
    token = request.match_info["admin_token"]; doc = _find_session_by_token(token, "admin")
    if not doc: return web.json_response({"error":"not_found"}, status=404)
    return web.json_response(doc)
async def api_admin_add_card(request: web.Request):
    token = request.match_info["admin_token"]; doc = _find_session_by_token(token, "admin")
    if not doc: return web.json_response({"error":"not_found"}, status=404)
    body = await request.json(); title = str(body.get("title","")).strip()
    if not title: return web.json_response({"error":"bad_request","detail":"title required"}, status=400)
    doc.setdefault("cards", []).append(title); _save_json(SESS / f"{doc['id']}.json", doc)
    return web.json_response({"ok":True,"cards":doc["cards"]})
async def api_admin_set_notes(request: web.Request):
    token = request.match_info["admin_token"]; doc = _find_session_by_token(token, "admin")
    if not doc: return web.json_response({"error":"not_found"}, status=404)
    body = await request.json(); doc["notes"]=str(body.get("notes","")); _save_json(SESS / f"{doc['id']}.json", doc)
    return web.json_response({"ok":True})
async def api_admin_draw_random(request: web.Request):
    import random
    token = request.match_info["admin_token"]; doc = _find_session_by_token(token, "admin")
    if not doc: return web.json_response({"error":"not_found"}, status=404)
    deck = _load_json(DECK, []); 
    if not deck: return web.json_response({"error":"empty_deck"}, status=400)
    used=set(doc.get("cards",[])); fresh=[c for c in deck if c.get("title") not in used]
    if not fresh: return web.json_response({"error":"no_more_cards"}, status=400)
    card = random.choice(fresh); doc.setdefault("cards", []).append(card["title"]); _save_json(SESS / f"{doc['id']}.json", doc)
    return web.json_response({"ok":True,"title":card["title"],"cards":doc["cards"]})
def setup(app: web.Application):
    app.router.add_get("/tarot/{public_token}", tarot_client_page)
    app.router.add_get("/tarot/admin/{admin_token}", tarot_admin_page)
    static_path = Path(__file__).parent / "static"; app.router.add_static("/static/tarot", str(static_path), append_version=True)
    app.router.add_get("/api/tarot/session/{public_token}", api_get_session_client)
    app.router.add_get("/api/tarot/admin/{admin_token}", api_get_session_admin)
    app.router.add_post("/api/tarot/admin/{admin_token}/add-card", api_admin_add_card)
    app.router.add_post("/api/tarot/admin/{admin_token}/notes", api_admin_set_notes)
    app.router.add_post("/api/tarot/admin/{admin_token}/draw", api_admin_draw_random)
