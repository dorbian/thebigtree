# bigtree/webmods/dice_api.py
"""Dice set API endpoints."""
from __future__ import annotations
import logging
from aiohttp import web
from bigtree.inc.webserver import route
from bigtree.modules import dice as dice_mod

log = logging.getLogger("bigtree.webmods.dice_api")


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


@route("POST", "/api/dice/sets", scopes=["dice:admin", "cardgames:admin"])
async def create_dice_set(req: web.Request):
    """Create a new dice set."""
    body = await req.json()
    dice_id = str(body.get("dice_id") or body.get("id") or "d6-standard")
    name = body.get("name")
    sides = body.get("sides", 6)
    metadata = body.get("metadata", {})
    faces = body.get("faces", [])
    
    dice_set = dice_mod.create_dice_set(dice_id, name=name, sides=sides, metadata=metadata, faces=faces)
    return web.json_response({"ok": True, "dice_set": dice_set})


@route("GET", "/api/dice/sets", scopes=["dice:admin", "cardgames:admin"])
async def list_dice_sets(req: web.Request):
    """List all dice sets."""
    dice_sets = dice_mod.list_dice_sets()
    return web.json_response({"ok": True, "dice_sets": dice_sets})


@route("GET", "/api/dice/sets/{dice_id}", scopes=["dice:admin", "cardgames:admin"])
async def get_dice_set(req: web.Request):
    """Get a dice set by ID."""
    dice_id = req.match_info["dice_id"]
    dice_set = dice_mod.get_dice_set(dice_id)
    if not dice_set:
        return _json_error("not found", status=404)
    faces = dice_mod.list_faces(dice_id)
    return web.json_response({"ok": True, "dice_set": dice_set, "faces": faces})


@route("DELETE", "/api/dice/sets/{dice_id}", scopes=["dice:admin"])
async def delete_dice_set(req: web.Request):
    """Delete a dice set."""
    dice_id = req.match_info["dice_id"]
    ok = dice_mod.delete_dice_set(dice_id)
    if not ok:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True})


@route("PUT", "/api/dice/sets/{dice_id}", scopes=["dice:admin"])
async def update_dice_set(req: web.Request):
    """Update a dice set."""
    dice_id = req.match_info["dice_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    
    name = body.get("name")
    sides = body.get("sides")
    metadata = body.get("metadata")
    payload = body.get("payload")
    
    dice_set = dice_mod.update_dice_set(dice_id, name=name, sides=sides, metadata=metadata, payload=payload)
    if not dice_set:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "dice_set": dice_set})


@route("PUT", "/api/dice/sets/{dice_id}/faces", scopes=["dice:admin"])
async def update_faces(req: web.Request):
    """Update faces for a dice set."""
    dice_id = req.match_info["dice_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    
    faces = body.get("faces", [])
    dice_set = dice_mod.update_faces(dice_id, faces)
    if not dice_set:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "dice_set": dice_set, "faces": faces})


@route("GET", "/api/dice/sets/{dice_id}/public", allow_public=True)
async def get_dice_set_public(req: web.Request):
    """Get a dice set (public endpoint)."""
    dice_id = req.match_info["dice_id"]
    dice_set = dice_mod.get_dice_set(dice_id)
    if not dice_set:
        return _json_error("not found", status=404)
    faces = dice_mod.list_faces(dice_id)
    return web.json_response({"ok": True, "dice_set": dice_set, "faces": faces})


@route("GET", "/api/dice/sets/public", allow_public=True)
async def list_dice_sets_public(_req: web.Request):
    """List all dice sets (public endpoint)."""
    dice_sets = dice_mod.list_dice_sets()
    return web.json_response({"ok": True, "dice_sets": dice_sets})
