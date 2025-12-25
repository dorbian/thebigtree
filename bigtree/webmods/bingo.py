# bigtree/webmods/bingo.py
from __future__ import annotations
from aiohttp import web
import os
import random
from typing import Any, Dict, Optional
import bigtree
import discord
from bigtree.inc.logging import logger
from bigtree.inc.webserver import route, get_server, DynamicWebServer
from bigtree.modules import bingo as bingo

# ---------- Helpers ----------
def _supports(func_name: str) -> bool:
    return hasattr(bingo, func_name) and callable(getattr(bingo, func_name))

def _list_games():
    try:
        if _supports("list_games"):
            return True, bingo.list_games()
        if _supports("get_all_games"):
            return True, bingo.get_all_games()
        if hasattr(bingo, "games"):
            return True, getattr(bingo, "games")
        return False, "list_games not implemented in bingo module"
    except Exception as e:
        return False, str(e)

def _update_game(game_id: str, fields: Dict[str, Any]):
    try:
        if _supports("update_game"):
            return True, bingo.update_game(game_id, **fields)
        return False, "update_game not implemented in bingo module"
    except Exception as e:
        return False, str(e)

def _delete_game(game_id: str):
    try:
        if _supports("delete_game"):
            return True, bingo.delete_game(game_id)
        return False, "delete_game not implemented in bingo module"
    except Exception as e:
        return False, str(e)

def _call_random(game_id: str):
    try:
        if _supports("call_random_number"):
            res = bingo.call_random_number(game_id)
            if isinstance(res, tuple) and len(res) == 2:
                game, err = res
                if err:
                    return False, err
                return True, game
            return True, res
        if _supports("call_number"):
            return False, "Random rolling not supported by bingo module"
        return False, "Random rolling not supported by bingo module"
    except Exception as e:
        return False, str(e)

def _call_label(game: Dict[str, Any], number: int) -> str:
    header = (game.get("header") or "BING").ljust(4)
    try:
        col_index = max(0, min(3, (int(number) - 1) // 10))
    except Exception:
        col_index = 0
    col_char = header[col_index].strip()
    return f"{col_char}{number}" if col_char else str(number)

async def _announce_call(game: Dict[str, Any], number: Optional[int]):
    if number is None:
        return
    channel_id = int(game.get("channel_id") or 0)
    if not channel_id:
        logger.warning("[bingo] call announce skipped: missing channel_id")
        return
    bot = getattr(bigtree, "bot", None)
    if not bot:
        logger.warning("[bingo] call announce skipped: bot not ready")
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as exc:
            logger.warning("[bingo] call announce skipped: channel %s not found (%s)", channel_id, exc)
            return
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        logger.warning("[bingo] call announce skipped: channel %s not text", channel_id)
        return
    call = _call_label(game, int(number))
    title = game.get("title") or "Bingo"
    templates = [
        "The forest whispers... {call}.",
        "Roots rustle and point to {call}.",
        "A leaf lands on {call}.",
        "Canopy echoes: {call}.",
        "The grove chooses {call}.",
        "Sapling scouts found {call}.",
        "Mossy drums roll: {call}.",
        "Hollow log hums {call}.",
        "Branchlight falls on {call}.",
    ]
    msg = random.choice(templates).format(call=call, number=number, title=title)
    try:
        await channel.send(msg)
        logger.info("[bingo] call announce sent to channel %s: %s", channel_id, msg)
    except Exception as exc:
        logger.warning("[bingo] call announce failed for channel %s: %s", channel_id, exc)

# ---------- Public JSON ----------
@route("GET", "/bingo/{game_id}", allow_public=True)
async def bingo_state(req: web.Request):
    game_id = req.match_info["game_id"]
    return web.json_response(bingo.get_public_state(game_id))

@route("GET", "/bingo/{game_id}/card/{card_id}", allow_public=True)
async def bingo_card(req: web.Request):
    g = req.match_info["game_id"]; c = req.match_info["card_id"]
    card = bingo.get_card(g, c)
    if not card:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    return web.json_response({"ok": True, "card": {
        "card_id": card["card_id"],
        "numbers": card["numbers"],
        "marks": card["marks"],
        "owner_name": card["owner_name"],
    }})

@route("GET", "/bingo/{game_id}/owner/{owner}/cards", allow_public=True)
async def bingo_owner_cards(req: web.Request):
    g = req.match_info["game_id"]; owner = req.match_info["owner"]
    cards = bingo.get_owner_cards(g, owner_name=owner)
    st = bingo.get_public_state(g)
    return web.json_response({
        "ok": True,
        "game": st.get("game", {"game_id": g, "called": []}),
        "owner": owner,
        "cards": [{"card_id": c["card_id"], "numbers": c["numbers"], "marks": c["marks"]} for c in cards],
    })

@route("GET", "/bingo/owner-token/{token}", allow_public=True)
async def bingo_owner_token_cards(req: web.Request):
    token = req.match_info["token"]
    info = bingo.resolve_owner_token(token)
    if not info:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    g = info.get("game_id") or ""
    owner = info.get("owner_name") or ""
    cards = bingo.get_owner_cards(g, owner_name=owner)
    st = bingo.get_public_state(g)
    return web.json_response({
        "ok": True,
        "game": st.get("game", {"game_id": g, "called": []}),
        "owner": owner,
        "cards": [{"card_id": c["card_id"], "numbers": c["numbers"], "marks": c["marks"]} for c in cards],
    })

# ---------- Admin JSON (key+scope auth) ----------
# Require WEB.api_keys[] and WEB.api_key_scopes["YOURKEY"]="bingo:admin" (or leave scopes map empty = full power)
@route("POST", "/bingo/create", scopes=["bingo:admin"])
async def bingo_create(req: web.Request):
    body = await req.json()
    bot = getattr(bigtree, "bot", None)
    game = bingo.create_game(
        channel_id=int(body.get("channel_id") or 0),
        title=str(body.get("title") or "Bingo"),
        price=int(body.get("price") or 0),
        currency=str(body.get("currency") or "gil"),
        max_cards_per_player=int(body.get("max_cards_per_player") or 10),
        created_by=int(body.get("created_by") or 0),
        header_text=str(body.get("header_text") or body.get("header") or "BING"),
        theme_color=str(body.get("theme_color") or "").strip() or None,
        **{k: v for k, v in {
            "size": body.get("size"),
            "free_center": body.get("free_center"),
            "max_number": body.get("max_number"),
        }.items() if v is not None}
    )
    channel_id = int(game.get("channel_id") or 0)
    if channel_id and bot:
        try:
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return web.json_response({"ok": False, "error": "Channel is not a text channel."}, status=400)
        except Exception:
            return web.json_response({"ok": False, "error": "Channel not found or not accessible by bot."}, status=400)
    return web.json_response({"ok": True, "game": game})

@route("POST", "/bingo/buy", scopes=["bingo:admin"])
async def bingo_buy(req: web.Request):
    body = await req.json()
    game_id = str(body.get("game_id"))
    owner_name = str(body.get("owner_name") or "")
    owner_user_id = body.get("owner_user_id")
    qty = int(body.get("quantity") or body.get("count") or 1)
    cards = []
    for _ in range(max(1, qty)):
        card, err = bingo.buy_card(game_id=game_id, owner_name=owner_name, owner_user_id=owner_user_id)
        if err:
            return web.json_response({"ok": False, "error": err}, status=400)
        cards.append({"card_id": card["card_id"], "numbers": card["numbers"]})
    return web.json_response({"ok": True, "cards": cards})

@route("POST", "/bingo/call", scopes=["bingo:admin"])
async def bingo_call(req: web.Request):
    body = await req.json()
    g = str(body.get("game_id"))
    num = body.get("number")
    if num is None:
        ok, val = _call_random(g)
        if not ok: return web.json_response({"ok": False, "error": val}, status=501)
        try:
            last_called = val.get("last_called") if isinstance(val, dict) else None
            await _announce_call(val, last_called)
        except Exception:
            pass
        return web.json_response({"ok": True, "called": getattr(val, "get", lambda _k, _d=None: None)("called", val)})
    game, err = bingo.call_number(g, int(num))
    if err and err != "Number already called.":
        return web.json_response({"ok": False, "error": err}, status=400)
    await _announce_call(game, int(num))
    return web.json_response({"ok": True, "called": game["called"]})

@route("POST", "/bingo/roll", scopes=["bingo:admin"])
async def bingo_roll(req: web.Request):
    body = await req.json()
    g = str(body.get("game_id"))
    ok, val = _call_random(g)
    if not ok:
        return web.json_response({"ok": False, "error": val}, status=501)
    try:
        last_called = val.get("last_called") if isinstance(val, dict) else None
        await _announce_call(val, last_called)
    except Exception:
        pass
    return web.json_response({"ok": True, "called": getattr(val, "get", lambda _k, _d=None: None)("called", val)})

@route("POST", "/bingo/start", scopes=["bingo:admin"])
async def bingo_start(req: web.Request):
    body = await req.json()
    g = str(body.get("game_id") or "")
    ok, msg = bingo.start_game(g)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/bingo/mark", scopes=["bingo:admin"])
async def bingo_mark(req: web.Request):
    b = await req.json()
    ok, msg = bingo.mark_card(str(b.get("game_id")), str(b.get("card_id")), int(b.get("row")), int(b.get("col")))
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

@route("POST", "/bingo/claim", scopes=["bingo:admin"])
async def bingo_claim(req: web.Request):
    b = await req.json()
    ok, msg = bingo.claim_bingo(str(b.get("game_id")), str(b.get("card_id")))
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

@route("POST", "/bingo/claim-approve", scopes=["bingo:admin"])
async def bingo_claim_approve(req: web.Request):
    b = await req.json()
    ok, msg = bingo.approve_public_claim(str(b.get("game_id")), str(b.get("card_id")))
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

@route("POST", "/bingo/claim-deny", scopes=["bingo:admin"])
async def bingo_claim_deny(req: web.Request):
    b = await req.json()
    ok, msg = bingo.deny_public_claim(str(b.get("game_id")), str(b.get("card_id")))
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)


@route("POST", "/bingo/claim-public", allow_public=True)
async def bingo_claim_public(req: web.Request):
    b = await req.json()
    ok, msg = bingo.public_claim(
        str(b.get("game_id")),
        str(b.get("card_id")),
        str(b.get("owner_name") or ""),
    )
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

@route("GET", "/bingo/games", scopes=["bingo:admin"])
async def bingo_list_games(_req: web.Request):
    ok, value = _list_games()
    if not ok: return web.json_response({"ok": False, "error": value}, status=501)
    return web.json_response({"ok": True, "games": value})


@route("GET", "/bingo/{game_id}/owners", scopes=["bingo:admin"])
async def bingo_list_owners(req: web.Request):
    game_id = req.match_info["game_id"]
    try:
        owners = bingo.list_owners(game_id)
        for o in owners:
            name = o.get("owner_name") or ""
            if not name:
                continue
            try:
                o["token"] = bingo.get_owner_token(game_id, name)
            except Exception:
                pass
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "owners": owners})

@route("GET", "/bingo/{game_id}/owner/{owner}/token", scopes=["bingo:admin"])
async def bingo_owner_token(req: web.Request):
    game_id = req.match_info["game_id"]
    owner = req.match_info["owner"]
    try:
        token = bingo.get_owner_token(game_id, owner)
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "token": token, "game_id": game_id, "owner": owner})

@route("PATCH", "/bingo/{game_id}", scopes=["bingo:admin"])
async def bingo_update(req: web.Request):
    game_id = req.match_info["game_id"]
    try:
        body = await req.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)
    fields = {}
    for key in ["title","price","currency","max_cards_per_player","free_center","size","max_number","status","background_path","stage","active","header"]:
        if key in body: fields[key] = body[key]
    ok, value = _update_game(game_id, fields)
    if not ok: return web.json_response({"ok": False, "error": value}, status=501)
    return web.json_response({"ok": True, "game": value})

@route("DELETE", "/bingo/{game_id}", scopes=["bingo:admin"])
async def bingo_delete(req: web.Request):
    game_id = req.match_info["game_id"]
    ok, value = _delete_game(game_id)
    if not ok: return web.json_response({"ok": False, "error": value}, status=501)
    return web.json_response({"ok": True, "deleted": game_id})


@route("POST", "/bingo/stage", scopes=["bingo:admin"])
async def bingo_set_stage(req: web.Request):
    body = await req.json()
    g = str(body.get("game_id") or "")
    stage = str(body.get("stage") or "")
    ok, msg = bingo.set_stage(g, stage)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/bingo/advance-stage", scopes=["bingo:admin"])
async def bingo_advance_stage(req: web.Request):
    body = await req.json()
    g = str(body.get("game_id") or "")
    ok, msg, stage, ended = bingo.advance_stage(g)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True, "stage": stage, "ended": ended})


@route("POST", "/bingo/end", scopes=["bingo:admin"])
async def bingo_end(req: web.Request):
    body = await req.json()
    g = str(body.get("game_id") or "")
    ok = bingo.end_game(g)
    if not ok:
        return web.json_response({"ok": False, "error": "not found"}, status=404)
    return web.json_response({"ok": True})

# ---- Background upload (multipart/form-data) ----
@route("POST", "/bingo/upload-bg", scopes=["bingo:admin"])
async def bingo_upload_bg(req: web.Request):
    from bigtree.webmods import uploads as upload_mod
    import tempfile, os
    fields, filename, data = await upload_mod.read_multipart(req)
    game_id = (fields.get("game_id") or "").strip()
    if not game_id or not data:
        return web.json_response({"ok": False, "error": "game_id and file are required"}, status=400)
    with tempfile.TemporaryDirectory() as td:
        tmpfile = os.path.join(td, filename or "bg.png")
        with open(tmpfile, "wb") as f:
            f.write(data)
        ok, msg = bingo.save_background(game_id, tmpfile)
        if not ok: return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/bingo/{game_id}/background-from-library", scopes=["bingo:admin"])
async def bingo_background_from_library(req: web.Request):
    game_id = req.match_info["game_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    source_game = str(body.get("source_game_id") or "")
    if not source_game:
        return web.json_response({"ok": False, "error": "source_game_id required"}, status=400)
    src = bingo.get_game(source_game)
    if not src or not src.get("background_path"):
        return web.json_response({"ok": False, "error": "source background not found"}, status=404)
    ok, msg = bingo.save_background(game_id, src["background_path"])
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/bingo/{game_id}/background-from-media", scopes=["bingo:admin"])
async def bingo_background_from_media(req: web.Request):
    game_id = req.match_info["game_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    url = str(body.get("url") or "")
    if not url:
        return web.json_response({"ok": False, "error": "url required"}, status=400)
    from bigtree.webmods import uploads as upload_mod
    path = upload_mod.resolve_media_path(url)
    if not path or not os.path.exists(path):
        return web.json_response({"ok": False, "error": "media not found"}, status=404)
    ok, msg = bingo.save_background(game_id, path)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

# ---- Serve background asset ----
@route("GET", "/bingo/assets/{game_id}", allow_public=True)
async def bingo_asset(req: web.Request):
    import os
    game_id = req.match_info["game_id"]
    g = bingo.get_game(game_id)
    if not g or not g.get("background_path") or not os.path.exists(g["background_path"]):
        return web.Response(status=404)
    return web.FileResponse(g["background_path"])

# ---------- HTML pages (template-based) ----------
@route("GET", "/bingo/play", allow_public=True)
async def bingo_page(_req: web.Request):
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("bingo_card.html", {}) if srv else "<h1>Bingo</h1>"
    return web.Response(text=html, content_type="text/html")

@route("GET", "/bingo/owner", allow_public=True)
async def bingo_owner_page(_req: web.Request):
    srv: DynamicWebServer | None = get_server()
    html = srv.render_template("bingo_owner.html", {}) if srv else "<h1>Bingo Owner</h1>"
    return web.Response(text=html, content_type="text/html")
