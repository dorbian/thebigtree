# bigtree/modules/dice.py
"""Dice set management module."""
from __future__ import annotations
import logging
from psycopg2.extras import Json
from bigtree.inc.database import get_database

log = logging.getLogger("bigtree.modules.dice")


def create_dice_set(dice_id: str, name: str = None, sides: int = 6, metadata: dict = None, faces: list = None) -> dict:
    """Create a new dice set."""
    db = get_database()
    if metadata is None:
        metadata = {}
    if faces is None:
        faces = []
    
    payload = {
        "faces": faces,
        "theme": metadata.get("theme", "standard"),
        "purpose": metadata.get("purpose", "generic"),
    }
    
    query = """
        INSERT INTO dice_sets (dice_id, name, sides, metadata, payload)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)
        ON CONFLICT (dice_id) DO UPDATE
        SET name = EXCLUDED.name, sides = EXCLUDED.sides, metadata = EXCLUDED.metadata, payload = EXCLUDED.payload, updated_at = CURRENT_TIMESTAMP
        RETURNING dice_id, name, sides, metadata, payload
    """
    row = db._fetchone(query, (dice_id, name or dice_id, sides, Json(metadata), Json(payload)))
    if not row:
        return None
    return {
        "dice_id": row[0],
        "name": row[1],
        "sides": row[2],
        "metadata": row[3] or {},
        "payload": row[4] or {},
    }


def get_dice_set(dice_id: str) -> dict | None:
    """Get a dice set by ID."""
    db = get_database()
    query = "SELECT dice_id, name, sides, metadata, payload FROM dice_sets WHERE dice_id = $1"
    row = db._fetchone(query, (dice_id,))
    if not row:
        return None
    return {
        "dice_id": row[0],
        "name": row[1],
        "sides": row[2],
        "metadata": row[3] or {},
        "payload": row[4] or {},
    }


def list_dice_sets() -> list[dict]:
    """List all dice sets."""
    db = get_database()
    query = "SELECT dice_id, name, sides, metadata FROM dice_sets ORDER BY name"
    rows = db._execute(query, fetch=True) or []
    result = []
    for row in rows:
        result.append({
            "dice_id": row[0],
            "name": row[1],
            "sides": row[2],
            "metadata": row[3] or {},
        })
    return result


def update_dice_set(dice_id: str, name: str = None, sides: int = None, metadata: dict = None, payload: dict = None) -> dict | None:
    """Update a dice set."""
    db = get_database()
    current = get_dice_set(dice_id)
    if not current:
        return None
    
    if name is not None:
        current["name"] = name
    if sides is not None:
        current["sides"] = sides
    if metadata is not None:
        current["metadata"] = metadata
    if payload is not None:
        current["payload"] = payload
    
    query = """
        UPDATE dice_sets
        SET name = $2, sides = $3, metadata = $4::jsonb, payload = $5::jsonb, updated_at = CURRENT_TIMESTAMP
        WHERE dice_id = $1
        RETURNING dice_id, name, sides, metadata, payload
    """
    row = db._fetchone(query, (dice_id, current["name"], current["sides"], Json(current["metadata"]), Json(current["payload"])))
    if not row:
        return None
    return {
        "dice_id": row[0],
        "name": row[1],
        "sides": row[2],
        "metadata": row[3] or {},
        "payload": row[4] or {},
    }


def delete_dice_set(dice_id: str) -> bool:
    """Delete a dice set."""
    db = get_database()
    query = "DELETE FROM dice_sets WHERE dice_id = $1"
    db._execute(query, (dice_id,))
    return True


def list_faces(dice_id: str) -> list[dict]:
    """List all faces for a dice set."""
    dice_set = get_dice_set(dice_id)
    if not dice_set:
        return []
    payload = dice_set.get("payload", {})
    return payload.get("faces", [])


def update_faces(dice_id: str, faces: list[dict]) -> dict | None:
    """Update faces for a dice set."""
    dice_set = get_dice_set(dice_id)
    if not dice_set:
        return None
    
    payload = dice_set.get("payload", {})
    payload["faces"] = faces
    
    return update_dice_set(dice_id, payload=payload)
