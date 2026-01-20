from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import bigtree
except Exception:
    bigtree = None

try:
    from bigtree.inc.database import get_database
except Exception:
    get_database = None  # type: ignore

TOKEN_TTL_SECONDS = 24 * 60 * 60


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


def _token_path() -> Path:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", ".")
    return Path(base) / "web_tokens.json"


def _load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def _save_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def _purge_expired(tokens: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = int(time.time())
    return [t for t in tokens if int(t.get("expires_at") or 0) > now]


def load_tokens() -> List[Dict[str, Any]]:
    data = _load_json(_token_path(), {"tokens": []})
    tokens = data.get("tokens") if isinstance(data, dict) else []
    tokens = _purge_expired(tokens if isinstance(tokens, list) else [])
    return tokens


def save_tokens(tokens: List[Dict[str, Any]]) -> None:
    tokens = _purge_expired(tokens)
    _save_json(_token_path(), {"tokens": tokens})


def _db_available() -> bool:
    if not get_database:
        return False
    try:
        db = get_database()
        db.initialize()
        return True
    except Exception:
        return False


def issue_token(
    user_id: int,
    scopes: Optional[List[str]] = None,
    ttl_seconds: int = TOKEN_TTL_SECONDS,
    user_name: Optional[str] = None,
    user_icon: Optional[str] = None,
) -> Dict[str, Any]:
    """Issue a web token. DB-first; falls back to web_tokens.json."""
    scopes = scopes or ["*"]
    if _db_available():
        try:
            db = get_database()
            return db.issue_web_token(
                user_id=int(user_id),
                scopes=scopes,
                ttl_seconds=int(ttl_seconds),
                user_name=user_name,
                user_icon=user_icon,
            )
        except Exception:
            pass

    token = secrets.token_urlsafe(32)
    now = int(time.time())
    doc = {
        "token": token,
        "user_id": int(user_id),
        "scopes": scopes,
        "created_at": now,
        "expires_at": now + int(ttl_seconds),
    }
    if user_name:
        doc["user_name"] = str(user_name)
    if user_icon:
        doc["user_icon"] = str(user_icon)
    tokens = load_tokens()
    tokens.append(doc)
    save_tokens(tokens)
    return doc


def validate_token(token: str, needed_scopes: Set[str]) -> bool:
    if not token:
        return False
    if _db_available():
        try:
            db = get_database()
            doc = db.find_web_token(token)
            if doc:
                scopes = set(doc.get("scopes") or [])
                if "*" in scopes:
                    return True
                if not needed_scopes:
                    return True
                return any(scope in scopes for scope in needed_scopes)
        except Exception:
            pass

    for t in load_tokens():
        if t.get("token") != token:
            continue
        scopes = set(t.get("scopes") or [])
        if "*" in scopes:
            return True
        if not needed_scopes:
            return True
        return any(scope in scopes for scope in needed_scopes)
    return False


def find_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    if _db_available():
        try:
            db = get_database()
            doc = db.find_web_token(token)
            if doc:
                return doc
        except Exception:
            pass
    for doc in load_tokens():
        if doc.get("token") == token:
            return doc
    return None
