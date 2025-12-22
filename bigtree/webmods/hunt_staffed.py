# bigtree/webmods/hunt_staffed.py
from __future__ import annotations
from aiohttp import web
from bigtree.inc.webserver import route
from bigtree.modules import hunt_staffed as hunt

@route("POST", "/hunts", scopes=["hunt:admin"])
async def hunt_create(req: web.Request):
    body = await req.json()
    h = hunt.create_hunt(
        title=str(body.get("title") or "Scavenger Hunt"),
        territory_id=int(body.get("territory_id") or 0),
        created_by=int(body.get("created_by") or 0),
        description=str(body.get("description") or "") or None,
        rules=str(body.get("rules") or "") or None,
        allow_implicit_groups=bool(body.get("allow_implicit_groups", True)),
    )
    return web.json_response({"ok": True, "hunt": h})

@route("GET", "/hunts", scopes=["hunt:admin"])
async def hunt_list(_req: web.Request):
    return web.json_response({"ok": True, "hunts": hunt.list_hunts()})

@route("GET", "/hunts/{hunt_id}/state", scopes=["hunt:admin"])
async def hunt_state(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    state = hunt.get_state(hunt_id)
    if not state.get("ok"):
        return web.json_response(state, status=404)
    return web.json_response(state)

@route("POST", "/hunts/{hunt_id}/start", scopes=["hunt:admin"])
async def hunt_start(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    ok, msg = hunt.start_hunt(hunt_id)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/hunts/{hunt_id}/end", scopes=["hunt:admin"])
async def hunt_end(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    ok, msg = hunt.end_hunt(hunt_id)
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True})

@route("POST", "/hunts/{hunt_id}/checkpoints", scopes=["hunt:admin"])
async def hunt_add_checkpoint(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    body = await req.json()
    try:
        cp = hunt.add_checkpoint(
            hunt_id=hunt_id,
            label=str(body.get("label") or "Checkpoint"),
            territory_id=int(body.get("territory_id") or 0),
            pos=body.get("pos") or {},
            radius_m=float(body.get("radius_m") or body.get("radius") or 15),
        )
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "checkpoint": cp})

@route("POST", "/hunts/{hunt_id}/groups", scopes=["hunt:admin"])
async def hunt_create_group(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    body = await req.json()
    g = hunt.create_group(
        hunt_id=hunt_id,
        group_id=str(body.get("group_id") or "") or None,
        name=str(body.get("name") or "") or None,
        captain_name=str(body.get("captain_name") or "") or None,
    )
    return web.json_response({"ok": True, "group": g})

@route("POST", "/hunts/{hunt_id}/staff/join", scopes=["hunt:admin"])
async def hunt_staff_join(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    body = await req.json()
    try:
        staff = hunt.staff_join(
            hunt_id=hunt_id,
            staff_name=str(body.get("staff_name") or "Staff"),
            staff_id=str(body.get("staff_id") or "") or None,
        )
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)
    return web.json_response({"ok": True, "staff": staff})

@route("POST", "/hunts/{hunt_id}/staff/claim-checkpoint", scopes=["hunt:admin"])
async def hunt_staff_claim(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    body = await req.json()
    ok, msg = hunt.claim_checkpoint(
        hunt_id=hunt_id,
        staff_id=str(body.get("staff_id") or ""),
        checkpoint_id=str(body.get("checkpoint_id") or ""),
    )
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 400)

@route("POST", "/hunts/{hunt_id}/checkins", scopes=["hunt:admin"])
async def hunt_checkin(req: web.Request):
    hunt_id = req.match_info["hunt_id"]
    body = await req.json()
    ok, msg, checkin = hunt.record_checkin(
        hunt_id=hunt_id,
        group_id=str(body.get("group_id") or ""),
        checkpoint_id=str(body.get("checkpoint_id") or ""),
        staff_id=str(body.get("staff_id") or ""),
        evidence=body.get("evidence") or {},
    )
    if not ok:
        return web.json_response({"ok": False, "error": msg}, status=400)
    return web.json_response({"ok": True, "checkin": checkin})

@route("POST", "/hunts/join", scopes=["hunt:admin"])
async def hunt_join_by_code(req: web.Request):
    body = await req.json()
    code = str(body.get("join_code") or "").strip()
    hunt_id = hunt.resolve_join_code(code)
    if not hunt_id:
        return web.json_response({"ok": False, "error": "invalid join code"}, status=404)
    staff = hunt.staff_join(
        hunt_id=hunt_id,
        staff_name=str(body.get("staff_name") or "Staff"),
        staff_id=str(body.get("staff_id") or "") or None,
    )
    state = hunt.get_state(hunt_id)
    return web.json_response({"ok": True, "hunt_id": hunt_id, "staff_id": staff.get("staff_id"), "state": state})
