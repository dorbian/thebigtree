# bigtree/modules/slots.py
"""Slot machine management module."""
from __future__ import annotations
import logging
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
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)
        ON CONFLICT (machine_id) DO UPDATE
        SET name = EXCLUDED.name, reel_count = EXCLUDED.reel_count, metadata = EXCLUDED.metadata, payload = EXCLUDED.payload, updated_at = CURRENT_TIMESTAMP
        RETURNING machine_id, name, reel_count, metadata, payload
    """
    row = db.fetchone(query, machine_id, name or machine_id, reel_count, metadata, payload)
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
    query = "SELECT machine_id, name, reel_count, metadata, payload FROM slot_machines WHERE machine_id = $1"
    row = db.fetchone(query, machine_id)
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
    rows = db.fetchall(query)
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
        SET name = $2, reel_count = $3, metadata = $4::jsonb, payload = $5::jsonb, updated_at = CURRENT_TIMESTAMP
        WHERE machine_id = $1
        RETURNING machine_id, name, reel_count, metadata, payload
    """
    row = db.fetchone(query, machine_id, current["name"], current["reel_count"], current["metadata"], current["payload"])
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
    query = "DELETE FROM slot_machines WHERE machine_id = $1"
    db.execute(query, machine_id)
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
