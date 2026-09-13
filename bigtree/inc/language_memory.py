from __future__ import annotations

from typing import Any, Dict, List, Optional

from bigtree.inc.database import get_database

_MAX_CONTENT = 4000
_DEFAULT_RECENT_MESSAGES = 12
_MAX_RECENT_MESSAGES = 40


def _clean_content(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > _MAX_CONTENT:
        text = text[:_MAX_CONTENT].rstrip() + "…"
    return text


def _row_to_dict(row: Any) -> Dict[str, Any]:
    data = dict(row or {})
    for key in ("created_at", "updated_at"):
        value = data.get(key)
        if value is not None and hasattr(value, "isoformat"):
            data[key] = value.isoformat()
    return data


def add_memory(
    *,
    content: str,
    scope_type: str = "global",
    scope_id: str = "",
    kind: str = "note",
    role: str = "system",
    source: str = "operator",
    pinned: bool = True,
) -> Dict[str, Any]:
    text = _clean_content(content)
    if not text:
        raise ValueError("memory content is required")

    scope_type = (scope_type or "global").strip().lower()
    if scope_type not in {"global", "user"}:
        raise ValueError("scope_type must be global or user")
    scope_id = str(scope_id or "").strip()
    if scope_type == "user" and not scope_id:
        raise ValueError("scope_id is required for user memory")

    kind = (kind or "note").strip().lower()[:40]
    role = (role or "system").strip().lower()
    if role not in {"system", "user", "assistant"}:
        role = "system"
    source = (source or "operator").strip()[:80]

    db = get_database()
    with db.transaction() as cur:
        cur.execute(
            """
            INSERT INTO language_memories
                (scope_type, scope_id, kind, role, content, source, pinned)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, scope_type, scope_id, kind, role, content, source,
                      pinned, created_at
            """,
            (scope_type, scope_id, kind, role, text, source, bool(pinned)),
        )
        return _row_to_dict(cur.fetchone())


def list_memories(
    *,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if scope_type:
        clauses.append("scope_type = %s")
        params.append(str(scope_type).lower())
    if scope_id is not None:
        clauses.append("scope_id = %s")
        params.append(str(scope_id))
    if kind:
        clauses.append("kind = %s")
        params.append(str(kind).lower())

    try:
        limit = max(1, min(int(limit), 500))
    except Exception:
        limit = 100

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"""
        SELECT id, scope_type, scope_id, kind, role, content, source,
               pinned, created_at
        FROM language_memories
        {where}
        ORDER BY pinned DESC, created_at DESC
        LIMIT %s
    """
    params.append(limit)
    db = get_database()
    with db.transaction() as cur:
        cur.execute(sql, tuple(params))
        return [_row_to_dict(row) for row in (cur.fetchall() or [])]


def delete_memory(memory_id: int) -> bool:
    db = get_database()
    with db.transaction() as cur:
        cur.execute("DELETE FROM language_memories WHERE id = %s", (int(memory_id),))
        return cur.rowcount > 0


def clear_conversation_memory(user_id: Optional[int] = None) -> int:
    db = get_database()
    with db.transaction() as cur:
        if user_id is None:
            cur.execute(
                "DELETE FROM language_memories WHERE kind = 'conversation' AND pinned = FALSE"
            )
        else:
            cur.execute(
                """
                DELETE FROM language_memories
                WHERE kind = 'conversation' AND pinned = FALSE
                  AND scope_type = 'user' AND scope_id = %s
                """,
                (str(user_id),),
            )
        return max(0, int(cur.rowcount or 0))


def record_exchange(user_id: int, prompt: str, reply: str, keep_messages: int = _DEFAULT_RECENT_MESSAGES) -> None:
    prompt = _clean_content(prompt)
    reply = _clean_content(reply)
    if not prompt and not reply:
        return
    try:
        keep_messages = max(2, min(int(keep_messages), _MAX_RECENT_MESSAGES))
    except Exception:
        keep_messages = _DEFAULT_RECENT_MESSAGES

    sid = str(user_id)
    db = get_database()
    with db.transaction() as cur:
        if prompt:
            cur.execute(
                """
                INSERT INTO language_memories
                    (scope_type, scope_id, kind, role, content, source, pinned)
                VALUES ('user', %s, 'conversation', 'user', %s, 'priest_chat', FALSE)
                """,
                (sid, prompt),
            )
        if reply:
            cur.execute(
                """
                INSERT INTO language_memories
                    (scope_type, scope_id, kind, role, content, source, pinned)
                VALUES ('user', %s, 'conversation', 'assistant', %s, 'priest_chat', FALSE)
                """,
                (sid, reply),
            )
        # Bound raw conversation memory per user. Pinned memories are never
        # pruned by this maintenance path.
        cur.execute(
            """
            DELETE FROM language_memories
            WHERE id IN (
                SELECT id
                FROM language_memories
                WHERE scope_type = 'user' AND scope_id = %s
                  AND kind = 'conversation' AND pinned = FALSE
                ORDER BY created_at DESC, id DESC
                OFFSET %s
            )
            """,
            (sid, keep_messages),
        )


def recent_history(user_id: int, limit: int = _DEFAULT_RECENT_MESSAGES) -> List[Dict[str, str]]:
    try:
        limit = max(2, min(int(limit), _MAX_RECENT_MESSAGES))
    except Exception:
        limit = _DEFAULT_RECENT_MESSAGES
    db = get_database()
    with db.transaction() as cur:
        cur.execute(
            """
            SELECT role, content
            FROM (
                SELECT id, role, content, created_at
                FROM language_memories
                WHERE scope_type = 'user' AND scope_id = %s
                  AND kind = 'conversation'
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            ) recent
            ORDER BY created_at ASC, id ASC
            """,
            (str(user_id), limit),
        )
        rows = cur.fetchall() or []
    return [
        {"role": str(row.get("role") or "user"), "content": str(row.get("content") or "")}
        for row in rows
        if row.get("content")
    ]


def pinned_context(user_id: int, limit: int = 12) -> List[str]:
    try:
        limit = max(1, min(int(limit), 50))
    except Exception:
        limit = 12
    db = get_database()
    with db.transaction() as cur:
        cur.execute(
            """
            SELECT content
            FROM language_memories
            WHERE pinned = TRUE
              AND (
                    scope_type = 'global'
                    OR (scope_type = 'user' AND scope_id = %s)
                  )
            ORDER BY CASE WHEN scope_type = 'user' THEN 0 ELSE 1 END,
                     created_at DESC, id DESC
            LIMIT %s
            """,
            (str(user_id), limit),
        )
        rows = cur.fetchall() or []
    return [str(row.get("content") or "") for row in rows if row.get("content")]


def memory_stats() -> Dict[str, int]:
    db = get_database()
    with db.transaction() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*)::int AS total,
              COUNT(*) FILTER (WHERE pinned = TRUE)::int AS pinned,
              COUNT(*) FILTER (WHERE kind = 'conversation')::int AS conversation,
              COUNT(DISTINCT scope_id) FILTER (WHERE scope_type = 'user')::int AS users
            FROM language_memories
            """
        )
        row = cur.fetchone() or {}
    return {
        "total": int(row.get("total") or 0),
        "pinned": int(row.get("pinned") or 0),
        "conversation": int(row.get("conversation") or 0),
        "users": int(row.get("users") or 0),
    }
