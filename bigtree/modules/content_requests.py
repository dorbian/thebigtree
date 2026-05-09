"""
Content Request system for BigTree.
Manages creative contest proposals and community content requests.
Pegas proposes content → Dorbian reviews → posts to target channels.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

try:
    from bigtree.inc.database import get_database
    from bigtree.inc.logging import logger
except Exception:
    get_database = None
    logger = print


class RequestStatus(Enum):
    DRAFT = "draft"        # Pegas is drafting
    NEEDS_REVISION = "needs_revision"  # Flagged as needing work
    PENDING = "pending"    # Sent for review, awaiting Dorbian
    APPROVED = "approved"  # Dorbian approved, ready to post
    REJECTED = "rejected"  # Dorbian rejected
    POSTED = "posted"      # Actually posted to target channel
    CANCELLED = "cancelled"


@dataclass
class ContentRequest:
    id: Optional[int] = None
    request_type: str = ""          # "art_contest", "rp_competition", "screenshot_challenge", etc.
    title: str = ""
    body: str = ""                 # The full announcement/description text
    target_channel_id: Optional[int] = None
    target_channel_name: str = ""
    status: str = "draft"
    proposed_by: str = "pegas"
    reviewed_by: Optional[int] = None   # Discord user ID who reviewed
    review_notes: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    posted_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ---- Database operations ----

def _table_exists(db, table: str) -> bool:
    row = db._fetchone(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,)
    )
    return bool(row)


def _ensure_table():
    if not get_database:
        return False
    db = get_database()
    if not _table_exists(db, "content_requests"):
        db._execute("""
            CREATE TABLE IF NOT EXISTS content_requests (
                id SERIAL PRIMARY KEY,
                request_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                target_channel_id BIGINT,
                target_channel_name TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                proposed_by TEXT NOT NULL DEFAULT 'pegas',
                reviewed_by BIGINT,
                review_notes TEXT DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                posted_at TIMESTAMPTZ,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """)
        logger.info("[content_requests] table created")
    return True


def _now() -> str:
    return datetime.utcnow().isoformat()


# ---- CRUD operations ----

def create_request(
    request_type: str,
    title: str,
    body: str,
    target_channel_id: Optional[int] = None,
    target_channel_name: str = "",
    metadata: dict = None,
) -> dict:
    """Create a new content request (status=pending)."""
    if not _ensure_table():
        return {"ok": False, "error": "database unavailable"}

    db = get_database()
    metadata_json = json.dumps(metadata or {})

    def _do():
        result = db._execute(
            """
            INSERT INTO content_requests (request_type, title, body, target_channel_id, target_channel_name, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (request_type, title, body, target_channel_id, target_channel_name, RequestStatus.PENDING.value, metadata_json),
            fetch=True,
        )
        row = result[0] if result else None
        if not row:
            return {"ok": False, "error": "insert failed"}
        return {"ok": True, "id": row["id"], "created_at": str(row["created_at"])}

    return db._with_retry(_do)()


def list_requests(
    status: Optional[str] = None,
    request_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List content requests, optionally filtered."""
    if not _ensure_table():
        return []

    db = get_database()
    where = ["1=1"]
    params = []

    if status:
        where.append("status = %s")
        params.append(status)
    if request_type:
        where.append("request_type = %s")
        params.append(request_type)

    where_clause = " AND ".join(where)
    params.append(limit)

    rows = db._fetchall(
        f"SELECT * FROM content_requests WHERE {where_clause} ORDER BY created_at DESC LIMIT %s",
        tuple(params),
    )
    return [_row(r) for r in rows]


def get_request(request_id: int) -> Optional[dict]:
    """Get a single request by ID."""
    if not _ensure_table():
        return None
    db = get_database()
    row = db._fetchone("SELECT * FROM content_requests WHERE id = %s", (request_id,))
    return _row(row) if row else None


def update_request_status(
    request_id: int,
    status: str,
    reviewed_by: Optional[int] = None,
    review_notes: str = "",
) -> dict:
    """Update status of a request (approve, reject, etc.)."""
    if not _ensure_table():
        return {"ok": False, "error": "database unavailable"}

    db = get_database()

    def _do():
        result = db._execute(
            """
            UPDATE content_requests
            SET status = %s, reviewed_by = %s, review_notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, status
            """,
            (status, reviewed_by, review_notes, request_id),
            fetch=True,
        )
        row = result[0] if result else None
        return {"ok": bool(row), "id": request_id, "status": status}

    return db._with_retry(_do)()


def mark_posted(request_id: int) -> dict:
    """Mark a request as posted to target channel."""
    if not _ensure_table():
        return {"ok": False, "error": "database unavailable"}

    db = get_database()

    def _do():
        result = db._execute(
            """
            UPDATE content_requests
            SET status = %s, posted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
            """,
            (RequestStatus.POSTED.value, request_id),
            fetch=True,
        )
        row = result[0] if result else None
        return {"ok": bool(row), "id": request_id}

    return db._with_retry(_do)()


def delete_request(request_id: int) -> dict:
    """Delete a request (draft/cancelled only)."""
    if not _ensure_table():
        return {"ok": False, "error": "database unavailable"}
    db = get_database()
    result = db._execute(
        "DELETE FROM content_requests WHERE id = %s AND status IN ('draft', 'cancelled') RETURNING id",
        (request_id,),
        fetch=True,
    )
    return {"ok": bool(result), "id": request_id}


def pending_requests() -> list[dict]:
    """Return all requests awaiting review (pending status)."""
    if not _ensure_table():
        return []
    db = get_database()
    rows = db._fetchall(
        "SELECT * FROM content_requests WHERE status = %s ORDER BY created_at ASC",
        (RequestStatus.PENDING.value,),
    )
    return [_row(r) for r in rows]


def _row(raw: dict) -> dict:
    """Convert DB row to plain dict."""
    if not raw:
        return {}
    out = dict(raw)
    if "metadata" in out and isinstance(out["metadata"], str):
        try:
            out["metadata"] = json.loads(out["metadata"])
        except Exception:
            out["metadata"] = {}
    return out


# ---- High-level operations ----

def propose_art_contest(theme: str, description: str, duration_days: int = 7, target_channel_id: int = None, target_channel_name: str = "") -> dict:
    """Propose an art contest announcement."""
    title = f"🎨 Art Contest: {theme}"
    body = f"""**{theme}**

{description}

📅 **Duration:** {duration_days} days
🏆 **Prize:** Winner gets the Weekly Champion role + your entry pinned in #elf-gallery!

**How to enter:**
1. Create your artwork
2. Post it in this channel
3. React with 📸 to register

Good luck! 🍀"""

    metadata = {"theme": theme, "duration_days": duration_days, "entry_count": 0}
    return create_request(
        request_type="art_contest",
        title=title,
        body=body,
        target_channel_id=target_channel_id,
        target_channel_name=target_channel_name,
        metadata=metadata,
    )


def propose_rp_competition(prompt: str, duration_days: int = 7, word_limit: int = 500, target_channel_id: int = None, target_channel_name: str = "") -> dict:
    """Propose an RP/story competition announcement."""
    title = f"✍️ Story Grove: {prompt[:50]}..."
    body = f"""**Writing Prompt: {prompt}**

📝 **Word limit:** {word_limit}
📅 **Duration:** {duration_days} days

**Rules:**
- Write a scene or short piece responding to the prompt above
- {word_limit} words max
- Stay in-character for your Forest character
- Post your entry as a reply to this message

🏆 Winner gets featured in #elf-gallery!

Good writing! ✨"""

    metadata = {"prompt": prompt, "duration_days": duration_days, "word_limit": word_limit}
    return create_request(
        request_type="rp_competition",
        title=title,
        body=body,
        target_channel_id=target_channel_id,
        target_channel_name=target_channel_name,
        metadata=metadata,
    )


def propose_screenshot_challenge(theme: str, subject: str, duration_days: int = 7, target_channel_id: int = None, target_channel_name: str = "") -> dict:
    """Propose a screenshot/photography challenge."""
    title = f"📷 Screenshot Challenge: {theme}"
    body = f"""**📷 {theme}**

**Subject:** {subject}

📅 **Duration:** {duration_days} days

**How to participate:**
1. Capture your best screenshot featuring **{subject}**
2. Post it in this channel
3. React with 👍 to enter

Most creative interpretation wins! Good luck! 📸"""

    metadata = {"theme": theme, "subject": subject, "duration_days": duration_days}
    return create_request(
        request_type="screenshot_challenge",
        title=title,
        body=body,
        target_channel_id=target_channel_id,
        target_channel_name=target_channel_name,
        metadata=metadata,
    )


def approve_request(request_id: int, reviewed_by: int, notes: str = "") -> dict:
    """Approve a content request for posting."""
    return update_request_status(
        request_id,
        RequestStatus.APPROVED.value,
        reviewed_by=reviewed_by,
        review_notes=notes,
    )


def reject_request(request_id: int, reviewed_by: int, notes: str = "") -> dict:
    """Reject a content request."""
    return update_request_status(
        request_id,
        RequestStatus.REJECTED.value,
        reviewed_by=reviewed_by,
        review_notes=notes,
    )


def cancel_request(request_id: int) -> dict:
    """Cancel a draft request."""
    return update_request_status(request_id, RequestStatus.CANCELLED.value)


# Alias for compatibility
from datetime import datetime