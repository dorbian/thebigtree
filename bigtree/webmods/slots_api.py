# bigtree/webmods/slots_api.py
"""Slot machine API endpoints."""
from __future__ import annotations
import logging
from aiohttp import web
from bigtree.inc.webserver import route
from bigtree.modules import slots as slots_mod

log = logging.getLogger("bigtree.webmods.slots_api")


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


@route("POST", "/api/slots/machines", scopes=["slots:admin", "cardgames:admin"])
async def create_slot_machine(req: web.Request):
    """Create a new slot machine."""
    body = await req.json()
    machine_id = str(body.get("machine_id") or body.get("id") or "slot-standard")
    name = body.get("name")
    reel_count = body.get("reel_count", 3)
    metadata = body.get("metadata", {})
    symbols = body.get("symbols", [])
    paylines = body.get("paylines", [])
    
    machine = slots_mod.create_slot_machine(machine_id, name=name, reel_count=reel_count, metadata=metadata, symbols=symbols, paylines=paylines)
    return web.json_response({"ok": True, "machine": machine})


@route("GET", "/api/slots/machines", scopes=["slots:admin", "cardgames:admin"])
async def list_slot_machines(req: web.Request):
    """List all slot machines."""
    machines = slots_mod.list_slot_machines()
    return web.json_response({"ok": True, "machines": machines})


@route("GET", "/api/slots/machines/{machine_id}", scopes=["slots:admin", "cardgames:admin"])
async def get_slot_machine(req: web.Request):
    """Get a slot machine by ID."""
    machine_id = req.match_info["machine_id"]
    machine = slots_mod.get_slot_machine(machine_id)
    if not machine:
        return _json_error("not found", status=404)
    symbols = slots_mod.list_symbols(machine_id)
    paylines = slots_mod.list_paylines(machine_id)
    return web.json_response({"ok": True, "machine": machine, "symbols": symbols, "paylines": paylines})


@route("DELETE", "/api/slots/machines/{machine_id}", scopes=["slots:admin"])
async def delete_slot_machine(req: web.Request):
    """Delete a slot machine."""
    machine_id = req.match_info["machine_id"]
    ok = slots_mod.delete_slot_machine(machine_id)
    if not ok:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True})


@route("PUT", "/api/slots/machines/{machine_id}", scopes=["slots:admin"])
async def update_slot_machine(req: web.Request):
    """Update a slot machine."""
    machine_id = req.match_info["machine_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    
    name = body.get("name")
    reel_count = body.get("reel_count")
    metadata = body.get("metadata")
    payload = body.get("payload")
    
    machine = slots_mod.update_slot_machine(machine_id, name=name, reel_count=reel_count, metadata=metadata, payload=payload)
    if not machine:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "machine": machine})


@route("PUT", "/api/slots/machines/{machine_id}/symbols", scopes=["slots:admin"])
async def update_symbols(req: web.Request):
    """Update symbols for a slot machine."""
    machine_id = req.match_info["machine_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    
    symbols = body.get("symbols", [])
    machine = slots_mod.update_symbols(machine_id, symbols)
    if not machine:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "machine": machine, "symbols": symbols})


@route("PUT", "/api/slots/machines/{machine_id}/paylines", scopes=["slots:admin"])
async def update_paylines(req: web.Request):
    """Update paylines for a slot machine."""
    machine_id = req.match_info["machine_id"]
    try:
        body = await req.json()
    except Exception:
        body = {}
    
    paylines = body.get("paylines", [])
    machine = slots_mod.update_paylines(machine_id, paylines)
    if not machine:
        return _json_error("not found", status=404)
    return web.json_response({"ok": True, "machine": machine, "paylines": paylines})


@route("GET", "/api/slots/machines/{machine_id}/public", allow_public=True)
async def get_slot_machine_public(req: web.Request):
    """Get a slot machine (public endpoint)."""
    machine_id = req.match_info["machine_id"]
    machine = slots_mod.get_slot_machine(machine_id)
    if not machine:
        return _json_error("not found", status=404)
    symbols = slots_mod.list_symbols(machine_id)
    paylines = slots_mod.list_paylines(machine_id)
    return web.json_response({"ok": True, "machine": machine, "symbols": symbols, "paylines": paylines})


@route("GET", "/api/slots/machines/public", allow_public=True)
async def list_slot_machines_public(_req: web.Request):
    """List all slot machines (public endpoint)."""
    machines = slots_mod.list_slot_machines()
    return web.json_response({"ok": True, "machines": machines})
