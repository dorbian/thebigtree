# bigtree/modules/webapi.py
# Web API for the BigTree Discord bot (with JWT support + Bingo admin endpoints)
#
# - Non-blocking aiohttp server tied to the bot lifecycle
# - Uses bigtree.webapi.* set during initialize() for config:
#     scheme, host, port, public_url, cors_origin, api_token (legacy), api_jwt (new)
# - All logging via bigtree.loch.logger

import os
import time
import asyncio
from typing import Optional, Dict, Any, List, Tuple, Callable

from aiohttp import web
from tinydb import TinyDB, Query

import bigtree
from bigtree.inc.logging import logger
from bigtree.modules import bingo as bingo
from bigtree.web.bingo_pages import BINGO_CARD_HTML, BINGO_OWNER_HTML

# Optional JWT (PyJWT)
try:
    import jwt  # type: ignore
    from jwt import InvalidTokenError  # type: ignore
except Exception:  # pragma: no cover
    jwt = None
    InvalidTokenError = Exception  # fallback to allow import

# ----------------- Small utils -----------------
def _has_value(s: Optional[str]) -> bool:
    return bool(s and s.strip())

def _log_auth_fail(request: web.Request, reason: str):
    hdrs = request.headers
    logger.warning(
        "Unauthorized (%s) %s %s  from=%s  hdr={X-API-Key:%s, Authorization:%s}",
        reason,
        request.method, request.path,
        request.remote,
        "present" if _has_value(hdrs.get("X-API-Key")) else "missing",
        "present" if _has_value(hdrs.get("Authorization")) else "missing",
    )

# ----------------- Config (single source of truth) -----------------
def _cfg():
    webapi = getattr(bigtree, "webapi", None)
    scheme = getattr(webapi, "scheme", "http")
    host = getattr(webapi, "host", "0.0.0.0")
    port = int(getattr(webapi, "port", 8080))
    public_url = getattr(webapi, "public_url", f"{scheme}://{host}:{port}").rstrip("/")
    cors = getattr(webapi, "cors_origin", "*")
    api_token = getattr(webapi, "api_token", "")  # legacy header X-API-Key
    api_jwt = getattr(webapi, "api_jwt", "")      # new: JWT *secret* for verifying Bearer tokens
    return scheme, host, port, public_url, cors, api_token, api_jwt

SCHEME, HOST, PORT, PUBLIC_URL, CORS_ALLOW_ORIGIN, API_TOKEN, API_JWT = _cfg()

# ----------------- TinyDB helpers -----------------
def _contest_db_path(channel_id: int) -> Optional[str]:
    path = os.path.join(bigtree.contest_dir, f"{channel_id}.json")
    return path if os.path.exists(path) else None

_ADMIN_DB_PATH = os.path.join(getattr(bigtree, "contest_dir", "/data/contest"), "admin_clients.json")

def _admin_db() -> TinyDB:
    os.makedirs(os.path.dirname(_ADMIN_DB_PATH), exist_ok=True)
    return TinyDB(_ADMIN_DB_PATH)

def _read_contest(channel_id: int) -> Dict[str, Any]:
    path = _contest_db_path(channel_id)
    if not path:
        return {"exists": False}
    db = TinyDB(path)
    docs = db.all()
    meta = None
    entries: List[Dict[str, Any]] = []
    for d in docs:
        if d.get("_type") == "meta":
            meta = d
        else:
            entries.append(d)
    return {
        "exists": True,
        "channel_id": channel_id,
        "meta": meta,
        "entries": entries,
        "counts": {"entries": len(entries)},
    }

def _extract_bearer(auth_header: Optional[str]) -> str:
    if not auth_header:
        return ""
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return ""

def _supports(func_name: str) -> bool:
    return hasattr(bingo, func_name) and callable(getattr(bingo, func_name))

# ----------------- Middlewares -----------------
@web.middleware
async def auth_middleware(request: web.Request, handler: Callable):
    if request.method == "OPTIONS":
        return web.Response()

    p = request.path

    # Always public:
    if p == "/health":
        return await handler(request)

    # Public bingo assets and simple pages:
    if p.startswith("/bingo/assets/") or p in ("/bingo/owner", "/bingo/play"):
        return await handler(request)

    # Public GETs for bingo state & cards (read-only):
    is_public_bingo_get = (
        request.method == "GET"
        and p.startswith("/bingo/")
        and not any(
            p.startswith(x)
            for x in [
                "/bingo/upload-bg",
                "/bingo/create",
                "/bingo/buy",
                "/bingo/call",
                "/bingo/roll",
                "/bingo/delete",
            ]
        )
    )
    if is_public_bingo_get:
        return await handler(request)

    # Otherwise require JWT or legacy token (if configured)
    need_auth = bool(_has_value(API_TOKEN) or _has_value(API_JWT))
    if need_auth:
        supplied_api_key = request.headers.get("X-API-Key") or request.query.get("token")
        supplied_bearer = _extract_bearer(request.headers.get("Authorization", ""))

        ok = False

        # Accept legacy API key if configured & matches
        if _has_value(API_TOKEN) and supplied_api_key == API_TOKEN:
            ok = True

        # Accept JWT Bearer if configured; verify signature using shared secret
        if not ok and _has_value(API_JWT) and _has_value(supplied_bearer):
            if jwt is None:
                _log_auth_fail(request, "PyJWT missing")
                return web.json_response({"error": "Unauthorized"}, status=401)
            try:
                # We don't enforce audience/issuer here; feel free to add if you need.
                jwt.decode(
                    supplied_bearer,
                    API_JWT,
                    algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                ok = True
            except InvalidTokenError:
                ok = False

        if not ok:
            _log_auth_fail(request, "API-Key/JWT")
            return web.json_response({"error": "Unauthorized"}, status=401)

    return await handler(request)

@web.middleware
async def cors_middleware(request: web.Request, handler: Callable):
    def _apply(resp: web.StreamResponse) -> web.StreamResponse:
        resp.headers["Access-Control-Allow-Origin"] = CORS_ALLOW_ORIGIN
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp

    if request.method == "OPTIONS":
        return _apply(web.Response())

    resp = await handler(request)
    if isinstance(resp, web.StreamResponse):
        return _apply(resp)
    return resp

# ----------------- Basic endpoints -----------------
async def health(_req: web.Request):
    return web.json_response({"ok": True})

async def bot_info(_req: web.Request):
    bot = bigtree.bot
    guild = bot.get_guild(bigtree.guildid)
    return web.json_response(
        {
            "user": str(bot.user) if bot.user else None,
            "latency_sec": getattr(bot, "latency", None),
            "guild": {
                "id": bigtree.guildid,
                "name": getattr(guild, "name", None),
                "member_count": getattr(guild, "member_count", None),
            },
            "contest_channels": list(map(int, getattr(bigtree, "contestid", []) or [])),
            "public_url": PUBLIC_URL,
        }
    )

async def list_contests(_req: web.Request):
    channels = list(map(int, getattr(bigtree, "contestid", []) or []))
    return web.json_response({"channels": channels})

async def get_contest(req: web.Request):
    try:
        channel_id = int(req.match_info["channel_id"])
    except ValueError:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)
    return web.json_response(_read_contest(channel_id))

async def list_entries(req: web.Request):
    try:
        channel_id = int(req.match_info["channel_id"])
    except ValueError:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)
    data = _read_contest(channel_id)
    if not data.get("exists"):
        return web.json_response({"error": "contest not found"}, status=404)
    return web.json_response({"channel_id": channel_id, "entries": data["entries"]})

async def send_message(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)

    channel_id = body.get("channel_id")
    content = body.get("content")
    if not channel_id or not content:
        return web.json_response({"error": "channel_id and content are required"}, status=400)

    try:
        channel_id = int(channel_id)
    except Exception:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)

    chan = bigtree.bot.get_channel(channel_id)
    if not chan:
        logger.warning(f"send_message: channel {channel_id} not found or uncached")
        return web.json_response({"error": "channel not found or not cached"}, status=404)

    await chan.send(content)
    logger.info(f"Message sent to channel {channel_id} via API")
    return web.json_response({"ok": True})

# ----------------- Bingo helpers (admin fallbacks) -----------------
def _list_games() -> Tuple[bool, Any]:
    """Try to list all games. Returns (ok, value_or_msg)."""
    try:
        if _supports("list_games"):
            return True, bingo.list_games()
        if _supports("get_all_games"):
            return True, bingo.get_all_games()
        if hasattr(bingo, "games"):
            return True, getattr(bingo, "games")
        return False, "list_games not implemented in bingo module"
    except Exception as e:
        logger.exception("list_games failed")
        return False, str(e)

def _update_game(game_id: str, fields: Dict[str, Any]) -> Tuple[bool, Any]:
    try:
        if _supports("update_game"):
            return True, bingo.update_game(game_id, **fields)
        return False, "update_game not implemented in bingo module"
    except Exception as e:
        logger.exception("update_game failed")
        return False, str(e)

def _delete_game(game_id: str) -> Tuple[bool, Any]:
    try:
        if _supports("delete_game"):
            return True, bingo.delete_game(game_id)
        return False, "delete_game not implemented in bingo module"
    except Exception as e:
        logger.exception("delete_game failed")
        return False, str(e)

def _call_random(game_id: str) -> Tuple[bool, Any]:
    try:
        if _supports("call_random_number"):
            return True, bingo.call_random_number(game_id)
        if _supports("call_number"):
            try:
                return True, bingo.call_number(game_id, None)  # type: ignore[arg-type]
            except Exception:
                return True, bingo.call_number(game_id, -1)    # type: ignore[arg-type]
        return False, "Random rolling not supported by bingo module"
    except Exception as e:
        logger.exception("call_random failed")
        return False, str(e)

# ----------------- Admin: client announce -----------------
async def admin_announce(req: web.Request):
    """
    Admin-only: the FFXIV client announces itself.
    Body:
      {
        "client_id": "stable-guid-or-id",
        "app": "forest_client",
        "version": "1.2.3",
        "character": "Alice Lala",
        "world": "Phoenix",
        "region": "EU",
        "extra": { ... }
      }
    """
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    client_id = str(body.get("client_id") or "").strip()
    if not client_id:
        return web.json_response({"ok": False, "error": "client_id required"}, status=400)

    ip = req.headers.get("X-Forwarded-For") or req.remote
    ua = req.headers.get("User-Agent", "")
    now_ms = int(time.time() * 1000)

    doc = {
        "client_id": client_id,
        "app": str(body.get("app") or "unknown"),
        "version": str(body.get("version") or ""),
        "character": str(body.get("character") or ""),
        "world": str(body.get("world") or ""),
        "region": str(body.get("region") or ""),
        "extra": body.get("extra") or {},
        "ip": ip,
        "user_agent": ua,
        "ts": now_ms,
        "last_seen": now_ms,
    }

    db = _admin_db()
    q = Query()
    existing = db.get(q.client_id == client_id)
    if existing:
        doc["ts"] = existing.get("ts") or now_ms
        db.update(doc, q.client_id == client_id)
    else:
        db.insert(doc)

    logger.info(
        "[announce] client_id=%s app=%s ver=%s char=%s world=%s ip=%s",
        client_id, doc["app"], doc["version"], doc["character"], doc["world"], ip
    )
    return web.json_response({"ok": True, "client_id": client_id})

# ----------------- Bingo JSON endpoints (game_id based) -----------------
async def bingo_create(req: web.Request):
    body = await req.json()
    game = bingo.create_game(
        channel_id=int(body.get("channel_id") or 0),
        title=str(body.get("title") or "Bingo"),
        price=int(body.get("price") or 0),
        currency=str(body.get("currency") or "gil"),
        max_cards_per_player=int(body.get("max_cards_per_player") or 10),
        created_by=int(body.get("created_by") or 0),
        # Optional sizing/settings (only if your bingo module supports them)
        **{k: v for k, v in {
            "size": body.get("size"),
            "free_center": body.get("free_center"),
            "max_number": body.get("max_number"),
        }.items() if v is not None}
    )
    return web.json_response({"ok": True, "game": game})

async def bingo_state(req: web.Request):
    game_id = req.match_info["game_id"]
    return web.json_response(bingo.get_public_state(game_id))

async def bingo_buy(req: web.Request):
    body = await req.json()
    game_id = str(body.get("game_id"))
    owner_name = str(body.get("owner_name") or "")
    owner_user_id = body.get("owner_user_id")
    qty = int(body.get("quantity") or body.get("count") or 1)

    cards = []
    for _ in range(max(1, qty)):
        card, err = bingo.buy_card(
            game_id=game_id,
            owner_name=owner_name,
            owner_user_id=owner_user_id,
        )
        if err:
            return web.json_response({"ok": False, "error": err}, status=400)
        cards.append({"card_id": card["card_id"], "numbers": card["numbers"]})

    return web.json_response({"ok": True, "cards": cards})

async def bingo_call(req: web.Request):
    """
    If body includes {"number": N}, call that number.
    If not, try to roll randomly (if backend supports it).
    """
    body = await req.json()
    game_id = str(body.get("game_id"))
    num = body.get("number")

    if num is None:
        ok, val = _call_random(game_id)
        if not ok:
            return web.json_response({"ok": False, "error": val}, status=501)
        return web.json_response({"ok": True, "called": getattr(val, "get", lambda _k, _d=None: None)("called", val)})

    game, err = bingo.call_number(game_id, int(num))
    if err and err != "Number already called.":
        return web.json_response({"ok": False, "error": err}, status=400)
    return web.json_response({"ok": True, "called": game["called"]})

async def bingo_roll(req: web.Request):
    """Explicit random roll endpoint (admin)."""
    body = await req.json()
    game_id = str(body.get("game_id"))
    ok, val = _call_random(game_id)
    if not ok:
        return web.json_response({"ok": False, "error": val}, status=501)
    return web.json_response({"ok": True, "called": getattr(val, "get", lambda _k, _d=None: None)("called", val)})

async def bingo_card(req: web.Request):
    game_id = req.match_info["game_id"]
    card_id = req.match_info["card_id"]
    card = bingo.get_card(game_id, card_id)
    if not card:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    return web.json_response(
        {
            "ok": True,
            "card": {
                "card_id": card["card_id"],
                "numbers": card["numbers"],
                "marks": card["marks"],
                "owner_name": card["owner_name"],
            },
        }
    )

async def bingo_mark(req: web.Request):
    body = await req.json()
    ok, msg = bingo.mark_card(
        str(body.get("game_id")),
        str(body.get("card_id")),
        int(body.get("row")),
        int(body.get("col")),
    )
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

async def bingo_owner_cards(req: web.Request):
    game_id = req.match_info["game_id"]
    owner = req.match_info["owner"]  # URL-decoded by aiohttp
    cards = bingo.get_owner_cards(game_id, owner_name=owner)
    st = bingo.get_public_state(game_id)
    return web.json_response(
        {
            "ok": True,
            "game": st.get("game", {"game_id": game_id, "called": []}),
            "owner": owner,
            "cards": [{"card_id": c["card_id"], "numbers": c["numbers"], "marks": c["marks"]} for c in cards],
        }
    )

async def bingo_claim(req: web.Request):
    body = await req.json()
    ok, msg = bingo.claim_bingo(str(body.get("game_id")), str(body.get("card_id")))
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

# ----------------- Bingo Admin endpoints -----------------
async def bingo_list_games(_req: web.Request):
    ok, value = _list_games()
    if not ok:
        return web.json_response({"ok": False, "error": value}, status=501)
    return web.json_response({"ok": True, "games": value})

async def bingo_update(req: web.Request):
    game_id = req.match_info["game_id"]
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    fields: Dict[str, Any] = {}
    for key in [
        "title",
        "price",
        "currency",
        "max_cards_per_player",
        "free_center",
        "size",
        "max_number",
        "status",  # if your backend supports pausing/closing games
        "background_path",
    ]:
        if key in body:
            fields[key] = body[key]

    ok, value = _update_game(game_id, fields)
    if not ok:
        return web.json_response({"ok": False, "error": value}, status=501)
    return web.json_response({"ok": True, "game": value})

async def bingo_delete(req: web.Request):
    game_id = req.match_info["game_id"]
    ok, value = _delete_game(game_id)
    if not ok:
        return web.json_response({"ok": False, "error": value}, status=501)
    return web.json_response({"ok": True, "deleted": game_id})

# ----------------- Bingo HTML pages -----------------
async def bingo_page(_req: web.Request):
    # /bingo/play?game=<id>&card=<uuid>
    return web.Response(text=BINGO_CARD_HTML, content_type="text/html")

async def bingo_owner_page(_req: web.Request):
    # /bingo/owner?game=<id>&owner=<url-encoded name>
    return web.Response(text=BINGO_OWNER_HTML, content_type="text/html")

# ---- Background upload (multipart/form-data) ----
async def bingo_upload_bg(req: web.Request):
    reader = await req.multipart()
    game_id = None
    tmpfile = None
    filename = "bg.png"

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "game_id":
                game_id = (await part.text()).strip()
            elif part.name == "file":
                filename = part.filename or filename
                tmpfile = os.path.join(td, filename)
                with open(tmpfile, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)

        if not game_id or not tmpfile:
            return web.json_response({"ok": False, "error": "game_id and file are required"}, status=400)

        ok, msg = bingo.save_background(game_id, tmpfile)
        if not ok:
            return web.json_response({"ok": False, "error": msg}, status=400)

    return web.json_response({"ok": True})

# ---- Serve assets ----
async def bingo_asset(req: web.Request):
    game_id = req.match_info["game_id"]
    g = bingo.get_game(game_id)
    if not g or not g.get("background_path") or not os.path.exists(g["background_path"]):
        return web.Response(status=404)
    return web.FileResponse(g["background_path"])

# ----------------- App factory -----------------
def _make_app():
    app = web.Application(middlewares=[cors_middleware, auth_middleware])

    # health & bot
    app.router.add_get("/health", health)
    app.router.add_get("/bot", bot_info)

    # contests
    app.router.add_get("/contests", list_contests)
    app.router.add_get("/contests/{channel_id}", get_contest)
    app.router.add_get("/contests/{channel_id}/entries", list_entries)

    # messaging
    app.router.add_post("/message", send_message)

    # ---- Bingo (public + admin) ----
    # JSON (public read)
    app.router.add_get("/bingo/{game_id}", bingo_state)
    app.router.add_get("/bingo/{game_id}/card/{card_id}", bingo_card)
    app.router.add_get("/bingo/{game_id}/owner/{owner}/cards", bingo_owner_cards)

    # JSON (admin write)
    app.router.add_post("/bingo/create", bingo_create)
    app.router.add_post("/bingo/buy", bingo_buy)
    app.router.add_post("/bingo/call", bingo_call)  # supports random when number omitted
    app.router.add_post("/bingo/roll", bingo_roll)  # explicit random roll
    app.router.add_post("/bingo/mark", bingo_mark)
    app.router.add_post("/bingo/claim", bingo_claim)

    # Admin management
    app.router.add_get("/bingo/games", bingo_list_games)
    app.router.add_patch("/bingo/{game_id}", bingo_update)
    app.router.add_delete("/bingo/{game_id}", bingo_delete)

    # bingo HTML & assets
    app.router.add_get("/bingo/play", bingo_page)
    app.router.add_get("/bingo/owner", bingo_owner_page)
    app.router.add_post("/bingo/upload-bg", bingo_upload_bg)
    app.router.add_get("/bingo/assets/{game_id}", bingo_asset)

    # admin announce
    app.router.add_post("/admin/announce", admin_announce)

    # generic OPTIONS
    app.router.add_options("/{tail:.*}", lambda _req: web.Response())
    return app

# ----------------- Lifecycle -----------------
async def _start_site(bot):
    try:
        # Refresh config in case initialize() published after import time
        global SCHEME, HOST, PORT, PUBLIC_URL, CORS_ALLOW_ORIGIN, API_TOKEN, API_JWT
        SCHEME, HOST, PORT, PUBLIC_URL, CORS_ALLOW_ORIGIN, API_TOKEN, API_JWT = _cfg()

        app = _make_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, HOST, PORT)
        await site.start()
        bot._webapi_runner = runner
        logger.info(f"Web API listening on {SCHEME}://{HOST}:{PORT} (public: {PUBLIC_URL})")
    except Exception as e:
        logger.error(f"Failed to start web API: {e}", exc_info=True)

async def _stop_site(bot):
    runner = getattr(bot, "_webapi_runner", None)
    if runner:
        try:
            await runner.cleanup()
        except Exception:
            pass
        bot._webapi_runner = None
        logger.info("Web API stopped")

def install(bot):
    """Attach the non-blocking web API server to the Discord bot lifecycle."""
    if getattr(bot, "_webapi_installed", False):
        return
    bot._webapi_installed = True

    async def _on_ready_once():
        # Run once
        if getattr(bot, "_webapi_started", False):
            return
        bot._webapi_started = True
        await _start_site(bot)  # safe: loop is running now

    bot.add_listener(_on_ready_once, "on_ready")

    # Graceful cleanup on close()
    original_close = bot.close

    async def _close_wrapper():
        try:
            await _stop_site(bot)
        finally:
            await original_close()

    bot.close = _close_wrapper  # type: ignore
