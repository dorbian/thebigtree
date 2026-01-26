# bigtree/modules/slots.py
"""Slot machine management module."""
from __future__ import annotations
import logging
from psycopg2.extras import Json
from bigtree.inc.database import get_database

log = logging.getLogger("bigtree.modules.slots")


def create_slot_machine(machine_id: str, name: str = None, reel_count: int = 3, metadata: dict = None, symbols: list = None, paylines: list = None) -> dict:
    """Create a new slot machine."""
    db = get_database()
    if metadata is None:
        metadata = {}
    if symbols is None:
        symbols = []
    if paylines is None:
        paylines = []
    
    payload = {
        "symbols": symbols,
        "paylines": paylines,
        "theme": metadata.get("theme", "standard"),
        "purpose": metadata.get("purpose", "generic"),
    }
    
    query = """
        INSERT INTO slot_machines (machine_id, name, reel_count, metadata, payload)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (machine_id) DO UPDATE
        SET name = EXCLUDED.name, reel_count = EXCLUDED.reel_count, metadata = EXCLUDED.metadata, payload = EXCLUDED.payload, updated_at = CURRENT_TIMESTAMP
        RETURNING machine_id, name, reel_count, metadata, payload
    """
    row = db._fetchone(query, (machine_id, name or machine_id, reel_count, Json(metadata), Json(payload)))
    if not row:
        return None
    return {
        "machine_id": row[0],
        "name": row[1],
        "reel_count": row[2],
        "metadata": row[3] or {},
        "payload": row[4] or {},
    }


def get_slot_machine(machine_id: str) -> dict | None:
    """Get a slot machine by ID."""
    db = get_database()
    query = "SELECT machine_id, name, reel_count, metadata, payload FROM slot_machines WHERE machine_id = %s"
    row = db._fetchone(query, (machine_id,))
    if not row:
        return None
    return {
        "machine_id": row[0],
        "name": row[1],
        "reel_count": row[2],
        "metadata": row[3] or {},
        "payload": row[4] or {},
    }


def list_slot_machines() -> list[dict]:
    """List all slot machines."""
    db = get_database()
    query = "SELECT machine_id, name, reel_count, metadata FROM slot_machines ORDER BY name"
    rows = db._execute(query, fetch=True) or []
    result = []
    for row in rows:
        result.append({
            "machine_id": row[0],
            "name": row[1],
            "reel_count": row[2],
            "metadata": row[3] or {},
        })
    return result


def update_slot_machine(machine_id: str, name: str = None, reel_count: int = None, metadata: dict = None, payload: dict = None) -> dict | None:
    """Update a slot machine."""
    db = get_database()
    current = get_slot_machine(machine_id)
    if not current:
        return None
    
    if name is not None:
        current["name"] = name
    if reel_count is not None:
        current["reel_count"] = reel_count
    if metadata is not None:
        current["metadata"] = metadata
    if payload is not None:
        current["payload"] = payload
    
    query = """
        UPDATE slot_machines
        SET name = %s, reel_count = %s, metadata = %s, payload = %s, updated_at = CURRENT_TIMESTAMP
        WHERE machine_id = %s
        RETURNING machine_id, name, reel_count, metadata, payload
    """
    row = db._fetchone(query, (current["name"], current["reel_count"], Json(current["metadata"]), Json(current["payload"]), machine_id))
    if not row:
        return None
    return {
        "machine_id": row[0],
        "name": row[1],
        "reel_count": row[2],
        "metadata": row[3] or {},
        "payload": row[4] or {},
    }


def delete_slot_machine(machine_id: str) -> bool:
    """Delete a slot machine."""
    db = get_database()
    query = "DELETE FROM slot_machines WHERE machine_id = %s"
    db._execute(query, (machine_id,))
    return True


def list_symbols(machine_id: str) -> list[dict]:
    """List all symbols for a slot machine."""
    machine = get_slot_machine(machine_id)
    if not machine:
        return []
    payload = machine.get("payload", {})
    return payload.get("symbols", [])


def update_symbols(machine_id: str, symbols: list[dict]) -> dict | None:
    """Update symbols for a slot machine."""
    machine = get_slot_machine(machine_id)
    if not machine:
        return None
    
    payload = machine.get("payload", {})
    payload["symbols"] = symbols
    
    return update_slot_machine(machine_id, payload=payload)


def list_paylines(machine_id: str) -> list[dict]:
    """List all paylines for a slot machine."""
    machine = get_slot_machine(machine_id)
    if not machine:
        return []
    payload = machine.get("payload", {})
    return payload.get("paylines", [])


def update_paylines(machine_id: str, paylines: list[dict]) -> dict | None:
    """Update paylines for a slot machine."""
    machine = get_slot_machine(machine_id)
    if not machine:
        return None
    
    payload = machine.get("payload", {})
    payload["paylines"] = paylines
    
    return update_slot_machine(machine_id, payload=payload)
