# bigtree/webmods/contest.py
from __future__ import annotations
from aiohttp import web
from typing import Dict, Any, List, Optional
from tinydb import TinyDB, Query
import json
from datetime import datetime, timezone
import discord
import os
import bigtree
from bigtree.inc.webserver import route

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
DEFAULT_RULES = (
    "1) One entry per person\n"
    "2) Attach an image or video with your entry\n"
    "3) Keep it cozy (server rules apply)\n"
    "4) Voting uses :TreeCone: reactions\n"
    "5) Most :TreeCone: by the deadline wins"
)

def _settings_get(section: str, key: str, default=None):
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section(section)
            if isinstance(sec, dict):
                return sec.get(key, default)
            return bigtree.settings.get(f"{section}.{key}", default)
    except Exception:
        pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        return cfg.get(section, {}).get(key, default)
    except Exception:
        pass
    return default

def _contest_dir() -> str:
    if getattr(bigtree, "contest_dir", None):
        return str(getattr(bigtree, "contest_dir"))
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", ".")
    return os.path.join(str(base), "contest")

def _ensure_contestid_container() -> None:
    if not hasattr(bigtree, "contestid") or bigtree.contestid is None:
        bigtree.contestid = []

def _resolve_vote_emoji(guild: discord.Guild | None, desired: str | None) -> str:
    pick = (desired or _settings_get("CONTEST", "VOTE_EMOJI", ":TreeCone:") or ":TreeCone:").strip()
    if pick.startswith(":") and pick.endswith(":"):
        name = pick.strip(":")
    else:
        name = pick
    if guild:
        for emoji in getattr(guild, "emojis", []) or []:
            if str(getattr(emoji, "name", "")) == name:
                return str(emoji)
    return pick

def _contest_db_path(channel_id: int) -> Optional[str]:
    path = os.path.join(_contest_dir(), f"{channel_id}.json")
    return path if os.path.exists(path) else None

def _read_contest(channel_id: int) -> Dict[str, Any]:
    path = _contest_db_path(channel_id)
    if not path:
        contest_ids = set(map(int, getattr(bigtree, "contestid", []) or []))
        if channel_id in contest_ids:
            contest_dir = _contest_dir()
            os.makedirs(contest_dir, exist_ok=True)
            path = os.path.join(contest_dir, f"{channel_id}.json")
            db = TinyDB(path)
            db.insert({"_type": "meta", "channel_id": channel_id, "status": "active"})
        else:
            return {"exists": False}
    raw = None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        raw = None
    if isinstance(raw, dict) and "_default" not in raw:
        meta = raw or None
        return {
            "exists": True,
            "channel_id": channel_id,
            "meta": meta,
            "entries": meta.get("entries", []) if isinstance(meta, dict) else [],
            "counts": {"entries": len(meta.get("entries", [])) if isinstance(meta, dict) and isinstance(meta.get("entries"), list) else 0},
        }
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

def _contest_name(meta: Dict[str, Any] | None, channel_id: int) -> str:
    if meta:
        for key in ("name", "title", "contest_name", "label", "channel_name", "channel", "channel_title"):
            value = (meta.get(key) or "").strip()
            if value:
                return value
    try:
        bot = getattr(bigtree, "bot", None)
        if bot:
            channel = bot.get_channel(channel_id)
            if channel and getattr(channel, "name", None):
                return str(channel.name)
    except Exception:
        pass
    return f"Contest {channel_id}"

def _list_contest_entries() -> List[Dict[str, Any]]:
    contest_dir = _contest_dir()
    items: List[Dict[str, Any]] = []
    if not os.path.isdir(contest_dir):
        return items
    for name in os.listdir(contest_dir):
        if not name.endswith(".json"):
            continue
        stem = name[:-5]
        if not stem.isdigit():
            continue
        channel_id = int(stem)
        data = _read_contest(channel_id)
        if not data.get("exists"):
            continue
        meta = data.get("meta")
        contest_name = _contest_name(meta, channel_id)
        for entry in data.get("entries") or []:
            filename = (entry.get("file") or "").strip()
            if not filename:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in _IMG_EXTS:
                continue
            if not os.path.exists(os.path.join(contest_dir, filename)):
                continue
            items.append({
                "title": entry.get("title") or "",
                "contest": contest_name,
                "url": f"/contest/media/{filename}",
                "source": "contest",
                "type": "Contest",
                "artist": {"artist_id": None, "name": "Forest", "links": {}},
            })
    return items

@route("GET", "/contests", allow_public=True)
async def list_contests(_req: web.Request):
    channels = set(map(int, getattr(bigtree, "contestid", []) or []))
    contest_dir = getattr(bigtree, "contest_dir", "/data/contest")
    try:
        for name in os.listdir(contest_dir):
            if not name.endswith(".json"):
                continue
            stem = name[:-5]
            if stem.isdigit():
                channels.add(int(stem))
    except Exception:
        pass
    return web.json_response({"channels": sorted(channels)})

@route("GET", "/contests/{channel_id}", allow_public=True)
async def get_contest(req: web.Request):
    try:
        channel_id = int(req.match_info["channel_id"])
    except ValueError:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)
    return web.json_response(_read_contest(channel_id))

@route("GET", "/contests/{channel_id}/entries", allow_public=True)
async def list_entries(req: web.Request):
    try:
        channel_id = int(req.match_info["channel_id"])
    except ValueError:
        return web.json_response({"error": "channel_id must be an integer"}, status=400)
    data = _read_contest(channel_id)
    if not data.get("exists"):
        return web.json_response({"error": "contest not found"}, status=404)
    return web.json_response({"channel_id": channel_id, "entries": data["entries"]})

@route("POST", "/api/contests/create", scopes=["admin:web"])
async def create_contest(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    try:
        channel_id = int(body.get("channel_id") or 0)
    except Exception:
        channel_id = 0
    if not channel_id:
        return web.json_response({"ok": False, "error": "channel_id required"}, status=400)
    title = str(body.get("title") or "").strip() or "Contest"
    description = str(body.get("description") or "").strip() or "Post your entry as an attachment."
    rules_text = str(body.get("rules") or "").strip() or DEFAULT_RULES
    deadline_str = str(body.get("deadline") or "").strip()
    vote_emoji = str(body.get("vote_emoji") or "").strip()

    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)
    channel = bot.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return web.json_response({"ok": False, "error": "channel not found"}, status=404)

    deadline_dt = None
    if deadline_str:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                deadline_dt = datetime.strptime(deadline_str, fmt).replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue

    vote_pick = _resolve_vote_emoji(channel.guild, vote_emoji)
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    if rules_text:
        embed.add_field(name="Rules", value=rules_text, inline=False)
    if deadline_dt:
        embed.add_field(name="Deadline", value=f"{deadline_dt:%Y-%m-%d %H:%M} UTC", inline=False)
    embed.add_field(name="Voting", value=f"React with {vote_pick} on entries you like.", inline=False)

    try:
        msg = await channel.send(embed=embed)
        try:
            await msg.pin()
        except Exception:
            pass
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)

    contest_dir = _contest_dir()
    os.makedirs(contest_dir, exist_ok=True)
    path = os.path.join(contest_dir, f"{channel_id}.json")
    db = TinyDB(path)
    db.remove(Query()._type == "meta")
    db.insert({
        "_type": "meta",
        "channel_id": channel_id,
        "channel_name": getattr(channel, "name", "") or "",
        "title": title,
        "description": description,
        "rules": rules_text,
        "deadline": deadline_dt.isoformat() if deadline_dt else None,
        "vote_emoji": vote_pick,
        "message_id": msg.id,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    _ensure_contestid_container()
    if channel_id not in bigtree.contestid:
        bigtree.contestid.append(channel_id)

    return web.json_response({"ok": True, "channel_id": channel_id, "message_id": msg.id})

@route("POST", "/api/contests/channel", scopes=["admin:web"])
async def create_contest_channel(req: web.Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip()
    try:
        category_id = int(body.get("category_id") or 0)
    except Exception:
        category_id = 0
    try:
        template_channel_id = int(body.get("template_channel_id") or 0)
    except Exception:
        template_channel_id = 0
    if not name:
        return web.json_response({"ok": False, "error": "name required"}, status=400)
    if not category_id:
        return web.json_response({"ok": False, "error": "category_id required"}, status=400)
    bot = getattr(bigtree, "bot", None)
    if not bot:
        return web.json_response({"ok": False, "error": "bot not ready"}, status=503)
    category = bot.get_channel(category_id)
    if not category or not isinstance(category, discord.CategoryChannel):
        return web.json_response({"ok": False, "error": "category not found"}, status=404)
    guild = category.guild
    overwrites = {}
    topic = None
    slowmode_delay = 0
    nsfw = False
    if template_channel_id:
        template = bot.get_channel(template_channel_id)
        if template and isinstance(template, discord.TextChannel):
            overwrites = dict(template.overwrites)
            topic = template.topic
            slowmode_delay = template.slowmode_delay or 0
            nsfw = bool(template.nsfw)
    everyone = guild.default_role
    if everyone not in overwrites:
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    else:
        ow = overwrites[everyone]
        if ow.view_channel is not True:
            ow.view_channel = True
        if ow.send_messages is not True:
            ow.send_messages = True
        if ow.read_message_history is not True:
            ow.read_message_history = True
        overwrites[everyone] = ow
    try:
        channel = await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=topic,
            slowmode_delay=slowmode_delay,
            nsfw=nsfw
        )
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)
    return web.json_response({"ok": True, "channel_id": channel.id, "name": channel.name})
