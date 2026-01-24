from __future__ import annotations

import json
import os
import secrets
import string
import threading
import time
from datetime import datetime, timedelta, date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from tinydb import TinyDB

import bigtree
from bigtree.inc.logging import logger

_DB_INSTANCE: Optional["Database"] = None


def ensure_database() -> "Database":
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        _DB_INSTANCE = Database()
        _DB_INSTANCE.initialize()
    return _DB_INSTANCE


def get_database() -> "Database":
    return ensure_database()


class Database:
    def __init__(self):
        self._settings = getattr(bigtree, "settings", None)
        conn_info, retries, delay = self._build_connection_info()
        self._conn_info = conn_info
        self._connect_retries = retries
        self._connect_delay = delay

        # internal state
        self._lock = threading.RLock()
        self._initialized = False
        self._json_imported = False
        self._decks_synced = False
        self._configs_seeded = False

    # ---------------- json helpers ----------------
    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Convert common DB-native types to JSON-serializable values."""
        if isinstance(value, (datetime, date)):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return value

    @classmethod
    def _json_safe_dict(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in (row or {}).items():
            out[k] = cls._json_safe(v)
        return out

    def initialize(self):
        with self._lock:
            if self._initialized:
                return
            self._ensure_tables()
            self._import_ini_configs()
            self._sync_tarot_decks()
            self._migrate_media_items()
            self._migrate_json_backups()
            self._migrate_legacy_state_files()
            self._migrate_legacy_contests()
            self._report_legacy_import_sources()
            self._initialized = True

    # ---------------- connection helpers ----------------
    def _build_connection_info(self) -> Tuple[Dict[str, Any], int, float]:
        defaults = {
            "host": "127.0.0.1",
            "port": 5432,
            "user": "bigtree",
            "password": "",
            "dbname": "bigtree",
            "sslmode": "prefer",
            "connect_timeout": 5,
        }
        data = {}
        for key, default in defaults.items():
            dotted = f"DATABASE.{key}"
            cast = None
            if isinstance(default, int):
                cast = int
            elif isinstance(default, float):
                cast = float
            val = self._settings.get(dotted, default, cast=cast) if self._settings else default
            if val is None:
                val = default
            data[key] = val
        retries = (
            self._settings.get("DATABASE.connect_retries", 10, cast=int)
            if self._settings
            else 10
        )
        delay = (
            self._settings.get("DATABASE.connect_delay", 1.0, cast=float)
            if self._settings
            else 1.0
        )
        return data, int(retries), float(delay)

    def _connect(self):
        attempts = getattr(self, "_connect_retries", 5)
        delay = getattr(self, "_connect_delay", 1.0)
        for attempt in range(1, attempts + 1):
            try:
                return psycopg2.connect(**self._conn_info)
            except psycopg2.OperationalError as exc:
                if attempt >= attempts:
                    raise
                logger.warning("[database] Postgres unavailable (%s), retrying (%s/%s)", exc, attempt, attempts)
                time.sleep(delay)

    def _execute(self, sql: str, params: Optional[Sequence] = None, fetch: bool = False):
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or ())
                if fetch:
                    return cur.fetchall()
                return cur.rowcount

    def _fetchone(self, sql: str, params: Optional[Sequence] = None) -> Optional[Dict[str, Any]]:
        rows = self._execute(sql, params, fetch=True)
        return rows[0] if rows else None

    def _ensure_column(self, conn: psycopg2.extensions.connection, table: str, column: str, definition: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                (table, column),
            )
            if cur.fetchone():
                return False
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True

    # ---------------- schema ----------------
    def _ensure_tables(self):
        logger.debug("[database] ensuring schema exists")
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                xiv_username TEXT UNIQUE NOT NULL,
                xiv_id TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS discord_users (
                discord_id BIGINT PRIMARY KEY,
                name TEXT,
                display_name TEXT,
                global_name TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY,
                game_id TEXT UNIQUE NOT NULL,
                module TEXT NOT NULL,
                title TEXT,
                channel_id BIGINT,
                created_by BIGINT,
                created_at TIMESTAMPTZ,
                ended_at TIMESTAMPTZ,
                status TEXT,
                active BOOLEAN NOT NULL DEFAULT FALSE,
                payload JSONB NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                run_source TEXT NOT NULL DEFAULT 'api',
                claimed_by INTEGER REFERENCES users(id),
                claimed_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cardgame_sessions (
                session_id TEXT PRIMARY KEY,
                join_code TEXT UNIQUE NOT NULL,
                priestess_token TEXT,
                player_token TEXT,
                game_id TEXT NOT NULL,
                deck_id TEXT,
                background_url TEXT,
                background_artist_id TEXT,
                background_artist_name TEXT,
                currency TEXT,
                status TEXT NOT NULL DEFAULT 'created',
                pot BIGINT NOT NULL DEFAULT 0,
                winnings BIGINT NOT NULL DEFAULT 0,
                state JSONB DEFAULT '{}'::jsonb,
                is_single_player BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cardgame_events (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES cardgame_sessions(session_id) ON DELETE CASCADE,
                ts TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                data JSONB DEFAULT '{}'::jsonb
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_cardgame_sessions_join_code ON cardgame_sessions(join_code)",
            "CREATE INDEX IF NOT EXISTS idx_cardgame_sessions_game_id ON cardgame_sessions(game_id)",
            "CREATE INDEX IF NOT EXISTS idx_cardgame_sessions_status ON cardgame_sessions(status)",
            "CREATE INDEX IF NOT EXISTS idx_cardgame_events_session ON cardgame_events(session_id, id)",
            """
            CREATE TABLE IF NOT EXISTS venues (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                currency_name TEXT,
                minimal_spend BIGINT,
                background_image TEXT,
                deck_id TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                event_code TEXT UNIQUE NOT NULL,
                title TEXT,
                venue_id INTEGER REFERENCES venues(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'active',
                currency_name TEXT,
                wallet_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS event_players (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'player',
                metadata JSONB DEFAULT '{}'::jsonb,
                joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS event_wallets (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                balance BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS event_wallet_history (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                delta BIGINT NOT NULL,
                balance BIGINT NOT NULL,
                reason TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS venue_members (
                id SERIAL PRIMARY KEY,
                venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'member',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS venue_admins (
                id SERIAL PRIMARY KEY,
                venue_id INTEGER NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
                discord_id BIGINT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'admin',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS game_players (
                id SERIAL PRIMARY KEY,
                game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                role TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_id, name, role)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_games (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
                role TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, game_id, role)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS deck_files (
                id SERIAL PRIMARY KEY,
                deck_id TEXT UNIQUE NOT NULL,
                name TEXT,
                module TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS system_configs (
                name TEXT PRIMARY KEY,
                data JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS legacy_imports (
                source_key TEXT PRIMARY KEY,
                imported_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gallery_hidden (
                item_id TEXT PRIMARY KEY,
                hidden BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gallery_reactions (
                item_id TEXT PRIMARY KEY,
                counts JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gallery_calendar (
                month INTEGER PRIMARY KEY,
                image TEXT,
                title TEXT,
                artist_id TEXT,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS temp_links (
                token TEXT PRIMARY KEY,
                scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
                role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_by TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMPTZ,
                max_uses INTEGER NOT NULL DEFAULT 1,
                used_count INTEGER NOT NULL DEFAULT 0,
                used_at TIMESTAMPTZ,
                used_by TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS web_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
                user_name TEXT,
                user_icon TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMPTZ,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS media_items (
                id SERIAL PRIMARY KEY,
                media_id TEXT UNIQUE NOT NULL,
                filename TEXT,
                title TEXT,
                artist_name TEXT,
                artist_links JSONB NOT NULL DEFAULT '{}'::jsonb,
                inspiration_text TEXT,
                origin_type TEXT,
                origin_label TEXT,
                url TEXT,
                thumb_url TEXT,
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                hidden BOOLEAN NOT NULL DEFAULT FALSE,
                kind TEXT NOT NULL DEFAULT 'image',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]
        for stmt in statements:
            self._execute(stmt)
        with self._connect() as conn:
            self._ensure_column(conn, "discord_users", "name", "TEXT")
            self._ensure_column(conn, "discord_users", "display_name", "TEXT")
            self._ensure_column(conn, "discord_users", "global_name", "TEXT")
            self._ensure_column(conn, "discord_users", "metadata", "JSONB DEFAULT '{}'::jsonb")
            self._ensure_column(conn, "discord_users", "created_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP")
            self._ensure_column(conn, "discord_users", "updated_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP")
            self._ensure_column(conn, "games", "run_source", "TEXT DEFAULT 'api'")
            self._ensure_column(conn, "games", "claimed_by", "INTEGER")
            self._ensure_column(conn, "games", "claimed_at", "TIMESTAMPTZ")
            self._ensure_column(conn, "games", "venue_id", "INTEGER")
            self._ensure_column(conn, "games", "event_id", "INTEGER")
            self._ensure_column(conn, "venues", "deck_id", "TEXT")
        logger.debug("[database] schema ready")

    def _count_rows(self, table: str) -> int:
        if not table:
            return 0
        row = self._fetchone(f"SELECT COUNT(*) AS value FROM {table}")
        try:
            return int(row.get("value") if row else 0)
        except Exception:
            return 0

    def _read_ini_section(self, section: str) -> Dict[str, Any]:
        if not section:
            return {}
        settings = getattr(bigtree, "settings", None)
        if settings:
            try:
                sec = settings.section(section)
                if isinstance(sec, dict):
                    return dict(sec)
            except Exception:
                pass
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        sec = cfg.get(section) or {}
        if isinstance(sec, dict):
            return dict(sec)
        return {}

    def _import_ini_configs(self) -> None:
        if self._configs_seeded:
            return
        self._configs_seeded = True
        rows = []
        try:
            rows = self._execute("SELECT name FROM system_configs", fetch=True) or []
        except Exception:
            rows = []
        existing = {row.get("name") for row in rows if row and row.get("name")}
        for key, section in (("xivauth", "XIVAUTH"), ("openai", "OPENAI")):
            if key in existing:
                continue
            data = self._read_ini_section(section)
            if not data:
                continue
            self.update_system_config(key, data)

# ---------------- public helpers ----------------
    def get_system_config(self, name: str) -> Dict[str, Any]:
        if not name:
            return {}
        row = self._fetchone("SELECT data FROM system_configs WHERE name = %s", (name.lower(),))
        data = row.get("data") if row else None
        return data or {}

    def update_system_config(self, name: str, data: Optional[Dict[str, Any]]) -> bool:
        if not name:
            return False
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return False
        cleaned = {str(k): v for k, v in data.items()}
        self._execute(
            """
            INSERT INTO system_configs (name, data)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE
              SET data = EXCLUDED.data,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (name.lower(), Json(cleaned)),
        )
        return True
    def upsert_user(self, xiv_username: str, xiv_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        metadata.setdefault("last_seen", datetime.utcnow().isoformat())
        sql = """
        INSERT INTO users (xiv_username, xiv_id, metadata)
        VALUES (%s, %s, %s)
        ON CONFLICT (xiv_username) DO UPDATE
          SET xiv_id = COALESCE(EXCLUDED.xiv_id, users.xiv_id),
              metadata = users.metadata || EXCLUDED.metadata,
              updated_at = CURRENT_TIMESTAMP
        RETURNING id, xiv_username, xiv_id, metadata, created_at, updated_at
        """
        row = self._fetchone(sql, (xiv_username, xiv_id, Json(metadata)))
        return row or {}

    def create_user_session(self, user_id: int, expires_in: int = 86400) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        self._execute(
            "INSERT INTO user_sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at),
        )
        return token

    def get_user_by_session(self, token: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT u.id, u.xiv_username, u.xiv_id, u.metadata, s.expires_at
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = %s AND s.expires_at > CURRENT_TIMESTAMP
        """
        return self._fetchone(sql, (token,))

    def link_user_to_matches(self, user_id: int, name: str):
        if not name:
            return
        normalized = name.strip().lower()
        if not normalized:
            return
        rows = self._execute(
            """
            SELECT game_id, name, role
            FROM game_players
            WHERE lower(name) = %s OR lower(name) LIKE %s
            """,
            (normalized, f"%{normalized}%"),
            fetch=True,
        )
        if not rows:
            return
        for row in rows:
            self._execute(
                """
                INSERT INTO user_games (user_id, game_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, row["game_id"], row.get("role")),
            )

    def list_user_games(self, user_id: int, only_active: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
        sql = """
        SELECT g.*, claimant.xiv_username AS claimed_username,
               v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
        FROM games g
        JOIN user_games ug ON ug.game_id = g.game_id
        LEFT JOIN users claimant ON claimant.id = g.claimed_by
        LEFT JOIN venues v ON v.id = g.venue_id
        WHERE ug.user_id = %s
        """
        params: List[Any] = [user_id]
        if only_active:
            sql += " AND g.active = TRUE"
        sql += " ORDER BY g.created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(sql, tuple(params), fetch=True)
        games = [self._format_game_row(row) for row in rows] if rows else []
        if not games:
            return []
        game_ids = [game.get("game_id") for game in games if game.get("game_id")]
        players = self._fetch_game_players(game_ids)
        indexed: Dict[str, List[Dict[str, Any]]] = {}
        for player in players:
            indexed.setdefault(player["game_id"], []).append(
                {"name": player["name"], "role": player.get("role"), "metadata": player.get("metadata")}
            )
        for row in games:
            row["players"] = indexed.get(row.get("game_id"), [])
            self._attach_game_summary(row)
        return games

    def list_api_games(self, include_inactive: bool = True, limit: int = 200) -> List[Dict[str, Any]]:
        sql = """
        SELECT g.*, claimant.xiv_username AS claimed_username,
               v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
        FROM games g
        LEFT JOIN users claimant ON claimant.id = g.claimed_by
        LEFT JOIN venues v ON v.id = g.venue_id
        WHERE g.run_source = %s
        """
        params: List[Any] = ["api"]
        if not include_inactive:
            sql += " AND g.active = TRUE"
        sql += " ORDER BY g.created_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(sql, tuple(params), fetch=True)
        games = [self._format_game_row(row) for row in rows] if rows else []
        for row in games:
            self._attach_game_summary(row)
        return games

    def upsert_discord_user(
        self,
        discord_id: int,
        name: Optional[str] = None,
        display_name: Optional[str] = None,
        global_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            discord_id = int(discord_id)
        except Exception:
            return False
        if not discord_id:
            return False
        payload = metadata or {}
        self._execute(
            """
            INSERT INTO discord_users (discord_id, name, display_name, global_name, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (discord_id) DO UPDATE
              SET name = COALESCE(EXCLUDED.name, discord_users.name),
                  display_name = COALESCE(EXCLUDED.display_name, discord_users.display_name),
                  global_name = COALESCE(EXCLUDED.global_name, discord_users.global_name),
                  metadata = discord_users.metadata || EXCLUDED.metadata,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (discord_id, name, display_name, global_name, Json(payload)),
        )
        return True

    def list_discord_users(self, limit: int = 2000) -> List[Dict[str, Any]]:
        try:
            limit = int(limit)
        except Exception:
            limit = 2000
        if limit < 1:
            limit = 1
        if limit > 10000:
            limit = 10000
        rows = self._execute(
            """
            SELECT discord_id, name, display_name, global_name, metadata, created_at, updated_at
            FROM discord_users
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
            fetch=True,
        )
        return [self._json_safe_dict(dict(r)) for r in (rows or [])]

    def list_users(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """List registered users/characters.

        The world/server is typically stored in users.metadata["world"] when
        coming from XivAuth.
        """
        try:
            limit = int(limit)
        except Exception:
            limit = 1000
        if limit < 1:
            limit = 1
        if limit > 5000:
            limit = 5000
        rows = self._execute(
            """
            SELECT id, xiv_username, xiv_id, metadata, created_at, updated_at
            FROM users
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
            fetch=True,
        )
        users: List[Dict[str, Any]] = []
        for row in rows or []:
            meta = row.get("metadata") or {}
            world = None
            try:
                world = meta.get("world")
            except Exception:
                world = None
            users.append(
                {
                    "id": row.get("id"),
                    "xiv_username": row.get("xiv_username"),
                    "xiv_id": row.get("xiv_id"),
                    "world": world,
                    "last_seen": (meta.get("last_seen") if isinstance(meta, dict) else None),
                    "created_at": self._json_safe(row.get("created_at")),
                    "updated_at": self._json_safe(row.get("updated_at")),
                }
            )
        return users

    def list_games(
        self,
        *,
        q: Optional[str] = None,
        module: Optional[str] = None,
        player: Optional[str] = None,
        venue_id: Optional[int] = None,
        include_inactive: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """List games with basic filtering and pagination (admin dashboard)."""
        try:
            page = int(page)
        except Exception:
            page = 1
        if page < 1:
            page = 1
        try:
            page_size = int(page_size)
        except Exception:
            page_size = 50
        if page_size < 5:
            page_size = 5
        if page_size > 200:
            page_size = 200

        where: List[str] = []
        params: List[Any] = []

        if not include_inactive:
            where.append("g.active = TRUE")

        if module:
            where.append("lower(g.module) = %s")
            params.append(str(module).strip().lower())

        if venue_id:
            where.append("g.venue_id = %s")
            params.append(int(venue_id))

        if q:
            qv = f"%{str(q).strip().lower()}%"
            where.append(
                "(lower(g.game_id) LIKE %s "
                "OR lower(COALESCE(g.title,'')) LIKE %s "
                "OR lower(COALESCE(g.payload->>'join_code','')) LIKE %s "
                "OR lower(COALESCE(g.payload->>'joinCode','')) LIKE %s "
                "OR lower(COALESCE(g.payload->>'join','')) LIKE %s)"
            )
            params.extend([qv, qv, qv, qv, qv])

        if player:
            pv = f"%{str(player).strip().lower()}%"
            where.append(
                "(EXISTS (SELECT 1 FROM game_players gp WHERE gp.game_id = g.game_id AND lower(gp.name) LIKE %s) "
                "OR EXISTS (SELECT 1 FROM user_games ug JOIN users u ON u.id = ug.user_id WHERE ug.game_id = g.game_id AND lower(u.xiv_username) LIKE %s))"
            )
            params.extend([pv, pv])

        where_sql = " WHERE " + " AND ".join(where) if where else ""

        # total
        total_row = self._fetchone(
            "SELECT COUNT(*) AS value FROM games g" + where_sql,
            tuple(params),
        )
        try:
            total = int(total_row.get("value") if total_row else 0)
        except Exception:
            total = 0

        offset = (page - 1) * page_size
        sql = (
            """
            SELECT g.*, claimant.xiv_username AS claimed_username,
                   v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
            FROM games g
            LEFT JOIN users claimant ON claimant.id = g.claimed_by
            LEFT JOIN venues v ON v.id = g.venue_id
            """
            + where_sql
            + " ORDER BY g.created_at DESC LIMIT %s OFFSET %s"
        )
        rows = self._execute(sql, tuple(params + [page_size, offset]), fetch=True)
        games = [self._format_game_row(row) for row in rows] if rows else []
        if games:
            game_ids = [g.get("game_id") for g in games if g.get("game_id")]
            players_rows = self._fetch_game_players(game_ids)
            indexed: Dict[str, List[Dict[str, Any]]] = {}
            for pr in players_rows:
                indexed.setdefault(pr["game_id"], []).append({"name": pr["name"], "role": pr.get("role")})
            for g in games:
                gid = g.get("game_id")
                players = indexed.get(gid, [])
                if not players:
                    # Fallback: some legacy payloads only store players in JSON.
                    players = [{"name": p, "role": "player"} for p in self._extract_players_from_payload(g.get("payload"))]
                g["players"] = players
                self._attach_game_summary(g)

        return {"total": total, "page": page, "page_size": page_size, "games": games}

    def get_game_by_join_code(self, join_code: str) -> Optional[Dict[str, Any]]:
        code = (join_code or "").strip()
        if not code:
            return None
        row = self._fetchone(
            """
            SELECT g.*, claimant.xiv_username AS claimed_username,
                   v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
            FROM games g
            LEFT JOIN users claimant ON claimant.id = g.claimed_by
            LEFT JOIN venues v ON v.id = g.venue_id
            WHERE lower(g.game_id) = lower(%s)
               OR lower(g.payload->>'join_code') = lower(%s)
               OR lower(g.payload->>'joinCode') = lower(%s)
               OR lower(g.payload->>'join') = lower(%s)
            LIMIT 1
            """,
            (code, code, code, code),
        )
        if not row:
            return None
        game = self._format_game_row(row)
        self._attach_game_summary(game)
        return game

    # ---------------- venues ----------------
    def list_venues(self) -> List[Dict[str, Any]]:
        rows = self._execute(
            """
            SELECT id, name, currency_name, minimal_spend, background_image, deck_id, metadata, created_at, updated_at
            FROM venues
            ORDER BY name ASC
            """,
            fetch=True,
        )
        return [self._json_safe_dict(dict(r)) for r in (rows or [])]

    def delete_venue(self, venue_id: int) -> bool:
        """Delete a venue by id.

        Related games/events keep their history via ON DELETE SET NULL, and
        venue hosts in user_venues are removed via ON DELETE CASCADE.
        """
        try:
            venue_id = int(venue_id)
        except Exception:
            return False
        if venue_id <= 0:
            return False
        count = self._execute(
            "DELETE FROM venues WHERE id = %s",
            (venue_id,),
        )
        return bool(count)

    def upsert_venue(
        self,
        name: str,
        currency_name: Optional[str] = None,
        minimal_spend: Optional[int] = None,
        background_image: Optional[str] = None,
        deck_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        metadata = metadata or {}
        row = self._fetchone(
            """
            INSERT INTO venues (name, currency_name, minimal_spend, background_image, deck_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE
              SET currency_name = COALESCE(EXCLUDED.currency_name, venues.currency_name),
                  minimal_spend = COALESCE(EXCLUDED.minimal_spend, venues.minimal_spend),
                  background_image = COALESCE(EXCLUDED.background_image, venues.background_image),
                  deck_id = COALESCE(EXCLUDED.deck_id, venues.deck_id),
                  metadata = venues.metadata || EXCLUDED.metadata,
                  updated_at = CURRENT_TIMESTAMP
            RETURNING id, name, currency_name, minimal_spend, background_image, deck_id, metadata, created_at, updated_at
            """,
            (name.strip(), currency_name, minimal_spend, background_image, deck_id, Json(metadata)),
        )
        return self._json_safe_dict(dict(row)) if row else None

    def get_venue(self, venue_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            """
            SELECT id, name, currency_name, minimal_spend, background_image, deck_id, metadata, created_at, updated_at
            FROM venues
            WHERE id = %s
            """,
            (venue_id,),
        )
        return self._json_safe_dict(dict(row)) if row else None

    def update_venue(
        self,
        venue_id: int,
        *,
        currency_name: Optional[str] = None,
        minimal_spend: Optional[int] = None,
        background_image: Optional[str] = None,
        deck_id: Optional[str] = None,
    ) -> bool:
        if not venue_id:
            return False
        count = self._execute(
            """
            UPDATE venues
            SET currency_name = COALESCE(%s, currency_name),
                minimal_spend = COALESCE(%s, minimal_spend),
                background_image = COALESCE(%s, background_image),
                deck_id = COALESCE(%s, deck_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (currency_name, minimal_spend, background_image, deck_id, venue_id),
        )
        return bool(count)

    # ---------------- events ----------------

    def _generate_event_code(self, length: int = 8) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def create_event(
        self,
        *,
        title: Optional[str],
        venue_id: Optional[int] = None,
        currency_name: Optional[str] = None,
        wallet_enabled: bool = False,
        created_by: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        metadata = metadata or {}
        # Make a few attempts at generating a unique code.
        for _ in range(10):
            code = self._generate_event_code(8)
            row = self._fetchone(
                """
                INSERT INTO events (event_code, title, venue_id, currency_name, wallet_enabled, metadata, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_code) DO NOTHING
                RETURNING id, event_code, title, venue_id, status, currency_name, wallet_enabled, metadata, created_by, created_at, ended_at
                """,
                (code, title, venue_id, currency_name, bool(wallet_enabled), Json(metadata), created_by),
            )
            if row:
                return self._json_safe_dict(dict(row))
        return None

    def upsert_event(
        self,
        *,
        event_id: Optional[int] = None,
        event_code: Optional[str] = None,
        title: Optional[str] = None,
        venue_id: Optional[int] = None,
        currency_name: Optional[str] = None,
        wallet_enabled: Optional[bool] = None,
        created_by: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        metadata = metadata or {}
        if event_id:
            row = self._fetchone(
                """
                UPDATE events
                SET title = COALESCE(%s, title),
                    venue_id = COALESCE(%s, venue_id),
                    currency_name = COALESCE(%s, currency_name),
                    wallet_enabled = COALESCE(%s, wallet_enabled),
                    metadata = events.metadata || %s
                WHERE id = %s
                RETURNING id, event_code, title, venue_id, status, currency_name, wallet_enabled, metadata, created_by, created_at, ended_at
                """,
                (title, venue_id, currency_name, wallet_enabled, Json(metadata), int(event_id)),
            )
            return self._json_safe_dict(dict(row)) if row else None
        if event_code:
            row = self._fetchone(
                """
                UPDATE events
                SET title = COALESCE(%s, title),
                    venue_id = COALESCE(%s, venue_id),
                    currency_name = COALESCE(%s, currency_name),
                    wallet_enabled = COALESCE(%s, wallet_enabled),
                    metadata = events.metadata || %s
                WHERE lower(event_code) = lower(%s)
                RETURNING id, event_code, title, venue_id, status, currency_name, wallet_enabled, metadata, created_by, created_at, ended_at
                """,
                (title, venue_id, currency_name, wallet_enabled, Json(metadata), event_code),
            )
            return self._json_safe_dict(dict(row)) if row else None
        # Create new if neither id nor code is provided.
        return self.create_event(
            title=title,
            venue_id=venue_id,
            currency_name=currency_name,
            wallet_enabled=bool(wallet_enabled),
            created_by=created_by,
            metadata=metadata,
        )

    def list_events(
        self,
        *,
        q: Optional[str] = None,
        venue_id: Optional[int] = None,
        include_ended: bool = True,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        params: List[Any] = []
        where = []
        if q:
            where.append("(lower(e.event_code) LIKE lower(%s) OR lower(e.title) LIKE lower(%s))")
            params.extend([f"%{q}%", f"%{q}%"])
        if venue_id:
            where.append("e.venue_id = %s")
            params.append(int(venue_id))
        if not include_ended:
            where.append("e.status = 'active'")

        sql = """
        SELECT e.id, e.event_code, e.title, e.venue_id, e.status, e.currency_name, e.wallet_enabled,
               e.metadata, e.created_by, e.created_at, e.ended_at,
               v.name AS venue_name
        FROM events e
        LEFT JOIN venues v ON v.id = e.venue_id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY e.created_at DESC LIMIT %s"
        params.append(int(limit))
        rows = self._execute(sql, tuple(params), fetch=True) or []
        return [self._json_safe_dict(dict(r)) for r in rows]

    def get_event_by_code(self, event_code: str) -> Optional[Dict[str, Any]]:
        code = (event_code or "").strip()
        if not code:
            return None
        row = self._fetchone(
            """
            SELECT e.id, e.event_code, e.title, e.venue_id, e.status, e.currency_name, e.wallet_enabled,
                   e.metadata, e.created_by, e.created_at, e.ended_at,
                   v.name AS venue_name
            FROM events e
            LEFT JOIN venues v ON v.id = e.venue_id
            WHERE lower(e.event_code) = lower(%s)
            LIMIT 1
            """,
            (code,),
        )
        return self._json_safe_dict(dict(row)) if row else None

    def end_event(self, event_id: int) -> bool:
        if not event_id:
            return False
        count = self._execute(
            """
            UPDATE events
            SET status = 'ended',
                ended_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status != 'ended'
            """,
            (int(event_id),),
        )
        return bool(count)

    def join_event(self, event_id: int, user_id: int) -> bool:
        if not event_id or not user_id:
            return False
        self._execute(
            """
            INSERT INTO event_players (event_id, user_id, role)
            VALUES (%s, %s, 'player')
            ON CONFLICT DO NOTHING
            """,
            (int(event_id), int(user_id)),
        )
        # Ensure wallet row exists for wallet-enabled events.
        try:
            ev = self._fetchone("SELECT wallet_enabled FROM events WHERE id = %s", (int(event_id),))
            if ev and bool(ev.get("wallet_enabled")):
                self._execute(
                    """
                    INSERT INTO event_wallets (event_id, user_id, balance)
                    VALUES (%s, %s, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    (int(event_id), int(user_id)),
                )
        except Exception:
            pass
        return True

    def get_event_players(self, event_id: int, limit: int = 5000) -> List[Dict[str, Any]]:
        if not event_id:
            return []
        try:
            limit = int(limit)
        except Exception:
            limit = 5000
        if limit < 1:
            limit = 1
        if limit > 10000:
            limit = 10000
        rows = self._execute(
            """
            SELECT u.id AS user_id, u.xiv_username, ep.role, ep.joined_at
            FROM event_players ep
            JOIN users u ON u.id = ep.user_id
            WHERE ep.event_id = %s
            ORDER BY ep.joined_at ASC
            LIMIT %s
            """,
            (int(event_id), int(limit)),
            fetch=True,
        ) or []
        return [self._json_safe_dict(dict(r)) for r in rows]

    def set_event_wallet_balance(self, event_id: int, user_id: int, balance: int) -> bool:
        try:
            event_id = int(event_id)
            user_id = int(user_id)
            balance = int(balance)
        except Exception:
            return False
        if event_id <= 0 or user_id <= 0:
            return False
        prev = self.get_event_wallet_balance(event_id, user_id)
        # Ensure wallet row exists.
        self._execute(
            """
            INSERT INTO event_wallets (event_id, user_id, balance)
            VALUES (%s, %s, %s)
            ON CONFLICT (event_id, user_id) DO UPDATE
              SET balance = EXCLUDED.balance,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (event_id, user_id, balance),
        )
        delta = balance - int(prev or 0)
        self._record_event_wallet_history(
            event_id=event_id,
            user_id=user_id,
            delta=delta,
            balance=balance,
            reason="admin_set",
            metadata={"source": "admin", "previous": int(prev or 0)},
            created_by=None,
        )
        return True

    def add_event_wallet_balance(
        self,
        event_id: int,
        user_id: int,
        delta: int,
        *,
        host_name: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Tuple[bool, int, str]:
        try:
            delta = int(delta)
        except Exception:
            return False, 0, "invalid"
        meta = {}
        if host_name:
            meta["host_name"] = str(host_name)
        if comment:
            meta["comment"] = str(comment)
        return self.apply_game_wallet_delta(
            event_id=int(event_id),
            user_id=int(user_id),
            delta=delta,
            reason="admin_add",
            metadata=meta,
            allow_negative=True,
        )

    def get_event_wallet_balance(self, event_id: int, user_id: int) -> int:
        try:
            event_id = int(event_id)
            user_id = int(user_id)
        except Exception:
            return 0
        if event_id <= 0 or user_id <= 0:
            return 0
        row = self._fetchone(
            "SELECT balance FROM event_wallets WHERE event_id = %s AND user_id = %s",
            (event_id, user_id),
        )
        try:
            return int(row.get("balance") or 0) if row else 0
        except Exception:
            return 0

    def _record_event_wallet_history(
        self,
        *,
        event_id: int,
        user_id: int,
        delta: int,
        balance: int,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: Optional[int] = None,
    ) -> None:
        self._execute(
            """
            INSERT INTO event_wallet_history (event_id, user_id, delta, balance, reason, metadata, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(event_id),
                int(user_id),
                int(delta),
                int(balance),
                reason,
                Json(metadata or {}),
                created_by,
            ),
        )

    def list_event_wallet_history(self, event_id: int, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        try:
            event_id = int(event_id)
            user_id = int(user_id)
            limit = int(limit)
        except Exception:
            return []
        if event_id <= 0 or user_id <= 0:
            return []
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000
        rows = self._execute(
            """
            SELECT delta, balance, reason, metadata, created_by, created_at
            FROM event_wallet_history
            WHERE event_id = %s AND user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (event_id, user_id, limit),
            fetch=True,
        ) or []
        return [self._json_safe_dict(dict(r)) for r in rows]

    @staticmethod
    def _normalize_currency(value: Optional[str]) -> str:
        return str(value or "").strip().lower()

    def _wallet_usable(self, event_status: Optional[str], event_metadata: Optional[Dict[str, Any]]) -> bool:
        status = str(event_status or "").strip().lower()
        meta = event_metadata or {}
        carry_over = bool(meta.get("carry_over") or meta.get("carryover"))
        return status == "active" or carry_over

    def get_game_wallet_context(self, *, join_code: Optional[str] = None, game_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        code = (join_code or "").strip()
        gid = (game_id or "").strip()
        if not code and not gid:
            return None
        row = self._fetchone(
            """
            SELECT g.game_id, g.event_id, g.payload, g.metadata,
                   e.status AS event_status, e.wallet_enabled, e.currency_name, e.metadata AS event_metadata
            FROM games g
            LEFT JOIN events e ON e.id = g.event_id
            WHERE (%s != '' AND lower(g.game_id) = lower(%s))
               OR (%s != '' AND (lower(g.payload->>'join_code') = lower(%s)
                                OR lower(g.payload->>'joinCode') = lower(%s)
                                OR lower(g.payload->>'join') = lower(%s)))
            LIMIT 1
            """,
            (gid, gid, code, code, code, code),
        )
        if not row:
            return None
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        metadata = row.get("metadata") or {}
        currency = metadata.get("currency") or payload.get("currency") or row.get("currency_name")
        pot = metadata.get("pot") or payload.get("pot") or 0
        winnings = payload.get("winnings") or payload.get("payout") or payload.get("result") or 0
        try:
            pot = int(float(pot or 0))
        except Exception:
            pot = 0
        try:
            winnings = int(float(winnings or 0))
        except Exception:
            winnings = 0
        return {
            "game_id": row.get("game_id"),
            "event_id": row.get("event_id"),
            "currency": currency,
            "pot": pot,
            "winnings": winnings,
            "wallet_enabled": bool(row.get("wallet_enabled")),
            "wallet_usable": self._wallet_usable(row.get("event_status"), row.get("event_metadata")),
        }

    def apply_game_wallet_delta(
        self,
        *,
        event_id: int,
        user_id: int,
        delta: int,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        allow_negative: bool = False,
    ) -> Tuple[bool, int, str]:
        try:
            event_id = int(event_id)
            user_id = int(user_id)
            delta = int(delta)
        except Exception:
            return False, 0, "invalid"
        if event_id <= 0 or user_id <= 0:
            return False, 0, "invalid"
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT balance
                    FROM event_wallets
                    WHERE event_id = %s AND user_id = %s
                    FOR UPDATE
                    """,
                    (event_id, user_id),
                )
                row = cur.fetchone()
                balance = int(row.get("balance") or 0) if row else 0
                next_balance = balance + delta
                if not allow_negative and next_balance < 0:
                    return False, balance, "insufficient"
                cur.execute(
                    """
                    INSERT INTO event_wallets (event_id, user_id, balance)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (event_id, user_id) DO UPDATE
                      SET balance = EXCLUDED.balance,
                          updated_at = CURRENT_TIMESTAMP
                    """,
                    (event_id, user_id, next_balance),
                )
                cur.execute(
                    """
                    INSERT INTO event_wallet_history (event_id, user_id, delta, balance, reason, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (event_id, user_id, delta, next_balance, reason, Json(metadata or {})),
                )
                return True, next_balance, "ok"

    def has_wallet_history_entry(self, *, event_id: int, user_id: int, reason: str, game_id: Optional[str]) -> bool:
        try:
            event_id = int(event_id)
            user_id = int(user_id)
        except Exception:
            return False
        if not event_id or not user_id or not reason or not game_id:
            return False
        row = self._fetchone(
            """
            SELECT 1 AS ok
            FROM event_wallet_history
            WHERE event_id = %s
              AND user_id = %s
              AND reason = %s
              AND metadata->>'game_id' = %s
            LIMIT 1
            """,
            (event_id, user_id, reason, str(game_id)),
        )
        return bool(row)

    def get_event_house_total(self, event_id: int) -> Dict[str, int]:
        try:
            event_id = int(event_id)
        except Exception:
            return {"total_pot": 0, "total_winnings": 0, "net": 0}
        if event_id <= 0:
            return {"total_pot": 0, "total_winnings": 0, "net": 0}
        rows = self._execute(
            "SELECT payload, metadata FROM games WHERE event_id = %s",
            (event_id,),
            fetch=True,
        ) or []
        total_pot = 0
        total_winnings = 0
        for r in rows:
            payload = r.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            metadata = r.get("metadata") or {}
            currency = metadata.get("currency") or payload.get("currency")
            if self._normalize_currency(currency) == "gil":
                continue
            pot = metadata.get("pot") or payload.get("pot") or 0
            winnings = payload.get("winnings") or payload.get("payout") or payload.get("result") or 0
            try:
                pot_val = int(float(pot or 0))
            except Exception:
                pot_val = 0
            try:
                winnings_val = int(float(winnings or 0))
            except Exception:
                winnings_val = 0
            total_pot += pot_val
            total_winnings += winnings_val
        return {"total_pot": total_pot, "total_winnings": total_winnings, "net": total_pot - total_winnings}

    def _find_active_event_id_for_venue(self, venue_id: int) -> Optional[int]:
        if not venue_id:
            return None
        row = self._fetchone(
            """
            SELECT id
            FROM events
            WHERE venue_id = %s AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (int(venue_id),),
        )
        try:
            return int(row.get("id")) if row and row.get("id") else None
        except Exception:
            return None

    def list_user_events(self, user_id: int, include_ended: bool = True, limit: int = 200) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        try:
            limit = int(limit)
        except Exception:
            limit = 200
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000
        sql = """
        SELECT e.id, e.event_code, e.title, e.venue_id, e.status, e.currency_name, e.wallet_enabled,
               e.metadata, e.created_by, e.created_at, e.ended_at,
               v.name AS venue_name,
               ep.joined_at,
               ew.balance AS wallet_balance
        FROM event_players ep
        JOIN events e ON e.id = ep.event_id
        LEFT JOIN venues v ON v.id = e.venue_id
        LEFT JOIN event_wallets ew ON ew.event_id = e.id AND ew.user_id = ep.user_id
        WHERE ep.user_id = %s
        """
        params: List[Any] = [int(user_id)]
        if not include_ended:
            sql += " AND e.status = 'active'"
        sql += " ORDER BY e.created_at DESC LIMIT %s"
        params.append(int(limit))
        events = [self._json_safe_dict(dict(r)) for r in (self._execute(sql, tuple(params), fetch=True) or [])]
        if not events:
            return []

        # Enrich with games_count + net_winnings (best-effort).
        user_row = self._fetchone("SELECT xiv_username FROM users WHERE id = %s", (int(user_id),))
        xiv_username = (user_row.get("xiv_username") if isinstance(user_row, dict) else "") or ""
        event_ids = [int(e.get("id")) for e in events if e and e.get("id")]

        counts: Dict[int, int] = {}
        if event_ids and xiv_username:
            rows = self._execute(
                """
                SELECT g.event_id, COUNT(DISTINCT g.game_id) AS value
                FROM games g
                LEFT JOIN game_players gp ON gp.game_id = g.game_id
                WHERE g.event_id = ANY(%s)
                  AND (g.claimed_by = %s OR lower(gp.name) = lower(%s))
                GROUP BY g.event_id
                """,
                (event_ids, int(user_id), str(xiv_username)),
                fetch=True,
            ) or []
            for r in rows:
                try:
                    counts[int(r.get("event_id"))] = int(r.get("value") or 0)
                except Exception:
                    continue

        winnings_by_event: Dict[int, int] = {}
        if event_ids:
            rows = self._execute(
                """
                SELECT event_id, payload
                FROM games
                WHERE claimed_by = %s AND event_id = ANY(%s)
                """,
                (int(user_id), event_ids),
                fetch=True,
            ) or []
            for r in rows:
                try:
                    eid = int(r.get("event_id") or 0)
                except Exception:
                    continue
                payload = r.get("payload") or {}
                if not isinstance(payload, dict):
                    payload = {}
                val = payload.get("winnings") or payload.get("payout") or payload.get("result")
                try:
                    amount = int(float(val)) if val not in (None, "") else 0
                except Exception:
                    amount = 0
                winnings_by_event[eid] = winnings_by_event.get(eid, 0) + amount

        for ev in events:
            meta = ev.get("metadata") or {}
            carry_over = False
            try:
                carry_over = bool(meta.get("carry_over") or meta.get("carryover"))
            except Exception:
                carry_over = False
            ev["games_count"] = counts.get(int(ev.get("id") or 0), 0)
            ev["net_winnings"] = winnings_by_event.get(int(ev.get("id") or 0), 0)
            ev["carry_over"] = carry_over
            ev["wallet_usable"] = bool(ev.get("wallet_enabled")) and (ev.get("status") == "active" or carry_over)
        return events

    def get_user_event_detail(self, user_id: int, event_code: str) -> Optional[Dict[str, Any]]:
        if not user_id or not event_code:
            return None
        ev = self.get_event_by_code(event_code)
        if not ev:
            return None
        # Must be joined to view details.
        joined = self._fetchone(
            "SELECT joined_at FROM event_players WHERE event_id = %s AND user_id = %s",
            (int(ev["id"]), int(user_id)),
        )
        if not joined:
            return None
        user_row = self._fetchone("SELECT xiv_username FROM users WHERE id = %s", (int(user_id),))
        xiv_username = (user_row.get("xiv_username") if isinstance(user_row, dict) else "") or ""

        wallet_balance = None
        if ev.get("wallet_enabled"):
            w = self._fetchone(
                "SELECT balance FROM event_wallets WHERE event_id = %s AND user_id = %s",
                (int(ev["id"]), int(user_id)),
            )
            if w:
                try:
                    wallet_balance = int(w.get("balance") or 0)
                except Exception:
                    wallet_balance = 0

        # Games played in this event by the user (claimed, or named in players list).
        rows = self._execute(
            """
            SELECT DISTINCT g.*, claimant.xiv_username AS claimed_username,
                   v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
            FROM games g
            LEFT JOIN users claimant ON claimant.id = g.claimed_by
            LEFT JOIN venues v ON v.id = g.venue_id
            LEFT JOIN game_players gp ON gp.game_id = g.game_id
            WHERE g.event_id = %s AND (g.claimed_by = %s OR lower(gp.name) = lower(%s))
            ORDER BY g.created_at DESC
            LIMIT 500
            """,
            (int(ev["id"]), int(user_id), str(xiv_username)),
            fetch=True,
        ) or []
        games = [self._format_game_row(r) for r in rows]
        if games:
            game_ids = [g.get("game_id") for g in games if g.get("game_id")]
            players_rows = self._fetch_game_players(game_ids)
            indexed: Dict[str, List[Dict[str, Any]]] = {}
            for pr in players_rows:
                indexed.setdefault(pr["game_id"], []).append({"name": pr["name"], "role": pr.get("role")})
            for g in games:
                g["players"] = indexed.get(g.get("game_id"), [])
                self._attach_game_summary(g)

        meta = ev.get("metadata") or {}
        carry_over = False
        try:
            carry_over = bool(meta.get("carry_over") or meta.get("carryover"))
        except Exception:
            carry_over = False

        wallet_history = []
        if ev.get("wallet_enabled"):
            wallet_history = self.list_event_wallet_history(int(ev["id"]), int(user_id), limit=200)

        return {
            "event": ev,
            "joined_at": self._json_safe(joined.get("joined_at") if isinstance(joined, dict) else None),
            "wallet_balance": wallet_balance,
            "wallet_usable": bool(ev.get("wallet_enabled")) and (ev.get("status") == "active" or carry_over),
            "carry_over": carry_over,
            "games": games,
            "wallet_history": wallet_history,
        }

    def get_user_venue(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        row = self._fetchone(
            """
            SELECT vm.venue_id, vm.role, vm.metadata AS membership_metadata,
                   v.id AS id, v.name, v.currency_name, v.minimal_spend, v.background_image, v.deck_id, v.metadata,
                   v.created_at, v.updated_at
            FROM venue_members vm
            JOIN venues v ON v.id = vm.venue_id
            WHERE vm.user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        return dict(row) if row else None

    def set_user_venue(self, user_id: int, venue_id: int, role: str = "member") -> bool:
        if not user_id or not venue_id:
            return False
        role = (role or "member").strip() or "member"
        self._execute(
            """
            INSERT INTO venue_members (venue_id, user_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET venue_id = EXCLUDED.venue_id,
                  role = COALESCE(venue_members.role, EXCLUDED.role),
                  updated_at = CURRENT_TIMESTAMP
            """,
            (venue_id, user_id, role),
        )
        return True

    def get_discord_venue(self, discord_id: int) -> Optional[Dict[str, Any]]:
        if not discord_id:
            return None
        row = self._fetchone(
            """
            SELECT va.venue_id, va.role, va.metadata AS membership_metadata,
                   v.id AS id, v.name, v.currency_name, v.minimal_spend, v.background_image, v.deck_id, v.metadata,
                   v.created_at, v.updated_at
            FROM venue_admins va
            JOIN venues v ON v.id = va.venue_id
            WHERE va.discord_id = %s
            LIMIT 1
            """,
            (int(discord_id),),
        )
        return dict(row) if row else None

    def set_discord_venue(self, discord_id: int, venue_id: int, role: str = "admin") -> bool:
        if not discord_id or not venue_id:
            return False
        role = (role or "admin").strip() or "admin"
        self._execute(
            """
            INSERT INTO venue_admins (venue_id, discord_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (discord_id) DO UPDATE
              SET venue_id = EXCLUDED.venue_id,
                  role = COALESCE(venue_admins.role, EXCLUDED.role),
                  updated_at = CURRENT_TIMESTAMP
            """,
            (venue_id, int(discord_id), role),
        )
        return True

    def set_user_venue_role(self, user_id: int, venue_id: int, role: str) -> bool:
        if not user_id or not venue_id:
            return False
        role = (role or "member").strip() or "member"
        self._execute(
            """
            INSERT INTO venue_members (venue_id, user_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
              SET venue_id = EXCLUDED.venue_id,
                  role = EXCLUDED.role,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (venue_id, user_id, role),
        )
        return True

    def find_user_id_by_xiv_username(self, xiv_username: str) -> Optional[int]:
        name = (xiv_username or "").strip()
        if not name:
            return None
        row = self._fetchone("SELECT id FROM users WHERE lower(xiv_username) = lower(%s) LIMIT 1", (name,))
        if not row:
            return None
        try:
            return int(row.get("id"))
        except Exception:
            return None

    def list_venue_games(self, venue_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        if not venue_id:
            return []
        rows = self._execute(
            """
            SELECT g.*, claimant.xiv_username AS claimed_username,
                   v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
            FROM games g
            LEFT JOIN users claimant ON claimant.id = g.claimed_by
            LEFT JOIN venues v ON v.id = g.venue_id
            WHERE g.venue_id = %s
            ORDER BY g.created_at DESC
            LIMIT %s
            """,
            (venue_id, limit),
            fetch=True,
        )
        games = [self._format_game_row(r) for r in (rows or [])]
        for g in games:
            self._attach_game_summary(g)
        return games

    def claim_game_for_user(self, game_id: str, user_id: int) -> bool:
        if not game_id or not user_id:
            return False
        count = self._execute(
            """
            UPDATE games
            SET claimed_by = %s, claimed_at = CURRENT_TIMESTAMP
            WHERE game_id = %s AND run_source = %s
            """,
            (user_id, game_id, "api"),
        )
        return bool(count)

    def claim_game_by_join_code(self, join_code: str, user_id: int) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        code = (join_code or "").strip()
        if not code or not user_id:
            return False, None, "join code required"
        row = self._fetchone(
            """
            SELECT g.*, claimant.xiv_username AS claimed_username
            FROM games g
            LEFT JOIN users claimant ON claimant.id = g.claimed_by
            WHERE lower(g.game_id) = lower(%s)
               OR lower(g.payload->>'join_code') = lower(%s)
               OR lower(g.payload->>'joinCode') = lower(%s)
               OR lower(g.payload->>'join') = lower(%s)
            LIMIT 1
            """,
            (code, code, code, code),
        )
        if not row:
            return False, None, "join code not found"
        game = self._format_game_row(row)
        self._attach_game_summary(game)
        # If the claimant belongs to a venue, tag the game with that venue
        venue_id = None
        try:
            venue_row = self.get_user_venue(int(user_id))
            venue_id = int(venue_row.get("venue_id")) if venue_row and venue_row.get("venue_id") else None
        except Exception:
            venue_id = None

        claimed_by = row.get("claimed_by")
        if claimed_by and int(claimed_by) != int(user_id):
            return False, game, "already claimed"
        if claimed_by and int(claimed_by) == int(user_id):
            self._link_user_game(user_id, game.get("game_id"))
            if venue_id:
                self._execute(
                    "UPDATE games SET venue_id = COALESCE(venue_id, %s) WHERE game_id = %s",
                    (venue_id, row.get("game_id")),
                )
            return True, game, "already claimed"
        updated = self._execute(
            """
            UPDATE games
            SET claimed_by = %s,
                claimed_at = CURRENT_TIMESTAMP,
                venue_id = COALESCE(venue_id, %s)
            WHERE game_id = %s
            """,
            (user_id, venue_id, row.get("game_id")),
        )
        if updated:
            self._link_user_game(user_id, row.get("game_id"))
            game["claimed_by"] = user_id
            game["claimed_username"] = game.get("claimed_username")
            return True, game, "claimed"
        return False, game, "claim failed"

    def upsert_game(
        self,
        game_id: str,
        module: str,
        payload: Dict[str, Any],
        title: Optional[str] = None,
        channel_id: Optional[int] = None,
        created_by: Optional[int] = None,
        venue_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        status: Optional[str] = None,
        active: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
        run_source: str = "api",
        players: Optional[Iterable[str]] = None,
    ) -> bool:
        if not game_id or not module or payload is None:
            return False
        self._store_game(
            game_id=game_id,
            module=module,
            payload=payload,
            title=title,
            channel_id=channel_id,
            created_by=created_by,
            venue_id=venue_id,
            created_at=created_at,
            ended_at=ended_at,
            status=status,
            active=bool(active),
            metadata=metadata or {},
            run_source=run_source,
        )
        if players:
            for player in players:
                if player:
                    self._store_game_player(game_id, str(player).strip(), role="player")
        return True

    def _link_user_game(self, user_id: int, game_id: Optional[str]) -> None:
        if not user_id or not game_id:
            return
        self._execute(
            """
            INSERT INTO user_games (user_id, game_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (user_id, game_id),
        )

    def add_user_game(self, user_id: int, game_id: str, role: Optional[str] = None) -> bool:
        if not user_id or not game_id:
            return False
        self._execute(
            """
            INSERT INTO user_games (user_id, game_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (int(user_id), str(game_id), role),
        )
        return True

    def get_primary_game_user(self, game_id: str, role: Optional[str] = "player") -> Optional[int]:
        gid = str(game_id or "").strip()
        if not gid:
            return None
        row = self._fetchone(
            """
            SELECT user_id
            FROM user_games
            WHERE game_id = %s AND (%s IS NULL OR role = %s)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (gid, role, role),
        )
        try:
            return int(row.get("user_id")) if row else None
        except Exception:
            return None

    def _fetch_game_players(self, game_ids: Iterable[str]) -> List[Dict[str, Any]]:
        if not game_ids:
            return []
        sql = """
        SELECT game_id, name, role, metadata
        FROM game_players
        WHERE game_id = ANY(%s)
        """
        return self._execute(sql, (list(game_ids),), fetch=True)

    def _format_game_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not row:
            return {}
        data = dict(row)
        data["metadata"] = data.get("metadata") or {}
        # venue fields (joined when available)
        data["venue_id"] = data.get("venue_id")
        data["venue_name"] = data.get("venue_name")
        data["venue_currency_name"] = data.get("venue_currency_name")
        data["created_at"] = self._format_dt(data.get("created_at"))
        data["ended_at"] = self._format_dt(data.get("ended_at"))
        data["claimed_at"] = self._format_dt(data.get("claimed_at"))
        data["claimed_username"] = data.get("claimed_username")
        return data

    def _attach_game_summary(self, row: Dict[str, Any]) -> None:
        if not row:
            return
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        metadata = row.get("metadata") or {}
        currency = metadata.get("currency") or payload.get("currency")
        pot = metadata.get("pot") or payload.get("pot")
        winnings = payload.get("winnings") or payload.get("payout") or payload.get("result")
        status = row.get("status") or payload.get("status")
        join_code = metadata.get("join_code") or payload.get("join_code") or payload.get("joinCode") or payload.get("join")
        outcome = "active" if row.get("active") else (status or "ended")
        if winnings not in (None, ""):
            outcome = f"{outcome} (winnings {winnings})"
        row["currency"] = currency
        row["pot"] = pot
        row["winnings"] = winnings
        row["outcome"] = outcome
        row["join_code"] = join_code

    def set_game_join_code(self, game_id: str, join_code: str) -> bool:
        gid = str(game_id or "").strip()
        code = str(join_code or "").strip()
        if not gid or not code:
            return False
        self._execute(
            """
            UPDATE games
            SET metadata = games.metadata || %s
            WHERE game_id = %s
            """,
            (Json({"join_code": code}), gid),
        )
        return True

    def list_event_games(self, event_id: int, include_inactive: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
        try:
            event_id = int(event_id)
            limit = int(limit)
        except Exception:
            return []
        if event_id <= 0:
            return []
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000
        sql = """
        SELECT g.*, claimant.xiv_username AS claimed_username,
               v.id AS venue_id, v.name AS venue_name, v.currency_name AS venue_currency_name
        FROM games g
        LEFT JOIN users claimant ON claimant.id = g.claimed_by
        LEFT JOIN venues v ON v.id = g.venue_id
        WHERE g.event_id = %s
        """
        params: List[Any] = [int(event_id)]
        if not include_inactive:
            sql += " AND g.active = TRUE"
        sql += " ORDER BY g.created_at DESC LIMIT %s"
        params.append(int(limit))
        rows = self._execute(sql, tuple(params), fetch=True) or []
        games = [self._format_game_row(r) for r in rows]
        for g in games:
            self._attach_game_summary(g)
        return games

    def _format_dt(self, value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()

    def upsert_deck(self, deck_id: str, payload: Dict[str, Any], module: str = "tarot", metadata: Optional[Dict[str, Any]] = None):
        metadata = metadata or {}
        metadata.setdefault("source", "filesystem")
        metadata.setdefault("deck_id", deck_id)
        sql = """
        INSERT INTO deck_files (deck_id, name, module, metadata, payload)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (deck_id) DO UPDATE
          SET name = COALESCE(EXCLUDED.name, deck_files.name),
              module = EXCLUDED.module,
              metadata = deck_files.metadata || EXCLUDED.metadata,
              payload = EXCLUDED.payload,
              updated_at = CURRENT_TIMESTAMP
        """
        self._execute(
            sql,
            (deck_id, payload.get("name") or deck_id, module, Json(metadata), Json(payload)),
        )

    def list_deck_files(self, module: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Return deck rows from Postgres. Payload is returned as a dict."""
        limit = int(limit) if str(limit).isdigit() else 500
        if limit < 1:
            limit = 1
        if limit > 2000:
            limit = 2000
        sql = "SELECT deck_id, name, module, metadata, payload, updated_at FROM deck_files"
        params: List[Any] = []
        if module:
            sql += " WHERE module = %s"
            params.append(module)
        sql += " ORDER BY updated_at DESC LIMIT %s"
        params.append(limit)
        rows = self._execute(sql, tuple(params), fetch=True) or []
        return [self._json_safe_dict(r) for r in rows]

    def get_deck_file(self, deck_id: str) -> Optional[Dict[str, Any]]:
        deck_id = (deck_id or "").strip()
        if not deck_id:
            return None
        row = self._fetchone(
            "SELECT deck_id, name, module, metadata, payload, updated_at FROM deck_files WHERE deck_id = %s",
            (deck_id,),
        )
        return self._json_safe_dict(row) if row else None

    def upsert_media_item(
        self,
        media_id: str,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        artist_name: Optional[str] = None,
        artist_links: Optional[Dict[str, Any]] = None,
        inspiration_text: Optional[str] = None,
        origin_type: Optional[str] = None,
        origin_label: Optional[str] = None,
        url: Optional[str] = None,
        thumb_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
        hidden: bool = False,
        kind: str = "image",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert/update a media item."""
        if not media_id:
            return
        metadata = metadata or {}
        artist_links = artist_links or {}
        tags = tags or []
        sql = """
        INSERT INTO media_items (
            media_id, filename, title, artist_name, artist_links, inspiration_text,
            origin_type, origin_label, url, thumb_url, tags, hidden, kind, metadata
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (media_id) DO UPDATE
          SET filename = COALESCE(EXCLUDED.filename, media_items.filename),
              title = COALESCE(NULLIF(EXCLUDED.title, ''), media_items.title),
              artist_name = COALESCE(NULLIF(EXCLUDED.artist_name, ''), media_items.artist_name),
              artist_links = media_items.artist_links || EXCLUDED.artist_links,
              inspiration_text = COALESCE(NULLIF(EXCLUDED.inspiration_text, ''), media_items.inspiration_text),
              origin_type = COALESCE(NULLIF(EXCLUDED.origin_type, ''), media_items.origin_type),
              origin_label = COALESCE(NULLIF(EXCLUDED.origin_label, ''), media_items.origin_label),
              url = COALESCE(NULLIF(EXCLUDED.url, ''), media_items.url),
              thumb_url = COALESCE(NULLIF(EXCLUDED.thumb_url, ''), media_items.thumb_url),
              tags = CASE WHEN jsonb_array_length(EXCLUDED.tags) > 0 THEN EXCLUDED.tags ELSE media_items.tags END,
              hidden = EXCLUDED.hidden,
              kind = EXCLUDED.kind,
              metadata = media_items.metadata || EXCLUDED.metadata,
              updated_at = CURRENT_TIMESTAMP
        """
        self._execute(
            sql,
            (
                media_id,
                filename,
                title or "",
                artist_name or "",
                Json(artist_links),
                inspiration_text or "",
                origin_type or "",
                origin_label or "",
                url or "",
                thumb_url or "",
                Json(tags),
                bool(hidden),
                (kind or "image"),
                Json(metadata),
            ),
        )

    def list_media_items(
        self,
        limit: int = 200,
        offset: int = 0,
        include_hidden: bool = False,
        media_type: Optional[str] = None,
        venue_id: Optional[int] = None,
        origin_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        limit = int(limit)
        offset = int(offset)
        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500
        if offset < 0:
            offset = 0
        sql = "SELECT * FROM media_items"
        params: List[Any] = []
        filters: List[str] = []
        if not include_hidden:
            filters.append("hidden = FALSE")
        if media_type:
            filters.append("LOWER(COALESCE(metadata->>'media_type', '')) = %s")
            params.append(str(media_type).strip().lower())
        if venue_id:
            filters.append("metadata->>'venue_id' = %s")
            params.append(str(venue_id))
        if origin_type:
            filters.append("origin_type = %s")
            params.append(str(origin_type).strip())
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        sql += " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        rows = self._execute(sql, tuple(params), fetch=True) or []
        return [self._json_safe_dict(r) for r in rows]

    def count_media_items(self, include_hidden: bool = False) -> int:
        if include_hidden:
            row = self._fetchone("SELECT COUNT(*) AS value FROM media_items")
        else:
            row = self._fetchone("SELECT COUNT(*) AS value FROM media_items WHERE hidden = FALSE")
        try:
            return int(row.get("value") if row else 0)
        except Exception:
            return 0

    def set_media_hidden(self, media_id: str, hidden: bool) -> bool:
        media_id = (media_id or "").strip()
        if not media_id:
            return False
        self._execute(
            "UPDATE media_items SET hidden = %s, updated_at = CURRENT_TIMESTAMP WHERE media_id = %s",
            (bool(hidden), media_id),
        )
        return True

    def delete_media_item(self, filename: str) -> bool:
        name = (filename or "").strip()
        if not name:
            return False
        self._execute(
            """
            DELETE FROM media_items
            WHERE filename = %s OR media_id = %s OR media_id = %s
            """,
            (name, name, f"media:{name}"),
        )
        return True

    def _migrate_media_items(self) -> None:
        """Import legacy TinyDB media.json + filesystem-only files into Postgres.

        TinyDB is kept only as a legacy import source.
        """
        try:
            from bigtree.modules import media as media_mod
        except Exception:
            return
        try:
            from bigtree.modules import gallery as gallery_mod
        except Exception:
            gallery_mod = None

        # Only run once per process start.
        if getattr(self, "_media_migrated", False) and self.count_media_items(include_hidden=True) > 0:
            return
        self._media_migrated = True

        hidden_set: set[str] = set()
        try:
            if gallery_mod:
                hidden_set = set(gallery_mod.get_hidden_set() or [])
        except Exception:
            hidden_set = set()

        media_dir = media_mod.get_media_dir()
        # 1) Import legacy TinyDB rows
        try:
            legacy = list(media_mod.list_media() or [])
        except Exception:
            legacy = []

        imported = 0
        for entry in legacy:
            filename = str(entry.get("filename") or "").strip()
            if not filename:
                continue
            item_id = f"media:{filename}"
            hidden = item_id in hidden_set
            discord_url = (entry.get("discord_url") or "").strip()
            url = discord_url or f"/media/{filename}"
            thumb_url = f"/media/thumbs/{filename}"
            artist_name = ""
            artist_links: Dict[str, Any] = {}
            # Keep artist_id mapping as metadata for now.
            meta = {"legacy": True}
            if entry.get("artist_id"):
                meta["artist_id"] = entry.get("artist_id")
            # Ensure thumbs exist for disk-backed images.
            try:
                _ = media_mod.ensure_thumb(filename)
            except Exception:
                pass
            self.upsert_media_item(
                media_id=filename,
                filename=filename,
                title=str(entry.get("title") or entry.get("original_name") or filename),
                artist_name=artist_name,
                artist_links=artist_links,
                inspiration_text=str(entry.get("inspiration_text") or ""),
                origin_type=str(entry.get("origin_type") or ""),
                origin_label=str(entry.get("origin_label") or ""),
                url=url,
                thumb_url=thumb_url,
                tags=entry.get("tags") if isinstance(entry.get("tags"), list) else [],
                hidden=hidden,
                kind="image",
                metadata=meta,
            )
            imported += 1

        # 2) Import filesystem-only images (present on disk but no DB row).
        try:
            names = sorted(os.listdir(media_dir))
        except Exception:
            names = []
        for name in names:
            if name in ("media.json", "thumbs"):
                continue
            path = os.path.join(media_dir, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
                continue
            # Upsert is idempotent; it will not overwrite existing richer rows.
            item_id = f"media:{name}"
            hidden = item_id in hidden_set
            try:
                _ = media_mod.ensure_thumb(name)
            except Exception:
                pass
            self.upsert_media_item(
                media_id=name,
                filename=name,
                title=name,
                url=f"/media/{name}",
                thumb_url=f"/media/thumbs/{name}",
                hidden=hidden,
                kind="image",
                metadata={"filesystem_only": True},
            )
        logger.info("[database] media migration complete (legacy_rows=%s, total=%s)", imported, self.count_media_items(include_hidden=True))

    
    # ---------------- legacy import tracking ----------------
    def is_legacy_imported(self, source_key: str) -> bool:
        key = str(source_key or "").strip()
        if not key:
            return False
        row = self._fetchone("SELECT source_key FROM legacy_imports WHERE source_key = %s", (key,))
        return bool(row)

    def mark_legacy_imported(self, source_key: str) -> None:
        key = str(source_key or "").strip()
        if not key:
            return
        self._execute(
            """
            INSERT INTO legacy_imports (source_key)
            VALUES (%s)
            ON CONFLICT (source_key) DO UPDATE SET imported_at = CURRENT_TIMESTAMP
            """,
            (key,),
        )

    def get_legacy_imports(self) -> List[str]:
        rows = self._execute("SELECT source_key FROM legacy_imports ORDER BY imported_at DESC", fetch=True) or []
        out: List[str] = []
        for r in rows:
            if r and r.get("source_key"):
                out.append(str(r.get("source_key")))
        return out

    # ---------------- system config ----------------
    def get_auth_roles(self) -> Dict[str, List[str]]:
        payload = self.get_system_config("auth_roles") or {}
        roles = payload.get("role_scopes") if isinstance(payload.get("role_scopes"), dict) else payload
        if not isinstance(roles, dict):
            return {}
        out: Dict[str, List[str]] = {}
        for role, scopes in roles.items():
            if not role:
                continue
            if isinstance(scopes, list):
                out[str(role)] = [str(s) for s in scopes if str(s)]
            else:
                out[str(role)] = []
        return out

    def update_auth_roles(self, role_scopes: Dict[str, List[str]]) -> None:
        role_scopes = role_scopes if isinstance(role_scopes, dict) else {}
        clean: Dict[str, List[str]] = {}
        for role, scopes in role_scopes.items():
            if not role:
                continue
            if isinstance(scopes, list):
                clean[str(role)] = [str(s) for s in scopes if str(s)]
            else:
                clean[str(role)] = []
        self.update_system_config("auth_roles", {"role_scopes": clean})

    def get_gallery_settings(self) -> Dict[str, Any]:
        payload = self.get_system_config("gallery_settings") or {}
        return payload if isinstance(payload, dict) else {}

    def update_gallery_settings(self, settings: Dict[str, Any]) -> None:
        settings = settings if isinstance(settings, dict) else {}
        self.update_system_config("gallery_settings", settings)

    # ---------------- gallery hidden ----------------
    def get_gallery_hidden_set(self) -> set[str]:
        rows = self._execute("SELECT item_id FROM gallery_hidden WHERE hidden = TRUE", fetch=True) or []
        return {str(r.get("item_id")) for r in rows if r and r.get("item_id")}

    def is_gallery_hidden(self, item_id: str) -> bool:
        key = str(item_id or "").strip()
        if not key:
            return False
        row = self._fetchone("SELECT hidden FROM gallery_hidden WHERE item_id = %s", (key,))
        return bool(row and row.get("hidden") is True)

    def set_gallery_hidden(self, item_id: str, hidden: bool) -> None:
        key = str(item_id or "").strip()
        if not key:
            return
        self._execute(
            """
            INSERT INTO gallery_hidden (item_id, hidden)
            VALUES (%s, %s)
            ON CONFLICT (item_id) DO UPDATE
              SET hidden = EXCLUDED.hidden,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (key, bool(hidden)),
        )
        # Keep media_items.hidden in sync for media:* items.
        if key.startswith("media:"):
            filename = key.split("media:", 1)[1]
            if filename:
                self.set_media_hidden(filename, bool(hidden))

    # ---------------- gallery reactions ----------------
    def get_gallery_reactions_bulk(self, item_ids: List[str]) -> Dict[str, Dict[str, int]]:
        if not item_ids:
            return {}
        keys = [str(i).strip() for i in item_ids if str(i).strip()]
        if not keys:
            return {}
        rows = self._execute(
            "SELECT item_id, counts FROM gallery_reactions WHERE item_id = ANY(%s)",
            (keys,),
            fetch=True,
        ) or []
        out: Dict[str, Dict[str, int]] = {}
        for r in rows:
            iid = str(r.get("item_id") or "")
            counts = r.get("counts") or {}
            if not isinstance(counts, dict):
                counts = {}
            out[iid] = {str(k): int(v or 0) for k, v in counts.items()}
        # ensure every key present
        for k in keys:
            out.setdefault(k, {})
        return out

    def increment_gallery_reaction(self, item_id: str, reaction_id: str, amount: int = 1) -> Dict[str, int]:
        iid = str(item_id or "").strip()
        rid = str(reaction_id or "").strip().lower()
        if not iid or not rid:
            return {}
        amount = max(1, int(amount or 1))
        row = self._fetchone("SELECT counts FROM gallery_reactions WHERE item_id = %s", (iid,))
        counts = row.get("counts") if row else {}
        if not isinstance(counts, dict):
            counts = {}
        counts[rid] = int(counts.get(rid) or 0) + amount
        self._execute(
            """
            INSERT INTO gallery_reactions (item_id, counts)
            VALUES (%s, %s)
            ON CONFLICT (item_id) DO UPDATE
              SET counts = EXCLUDED.counts,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (iid, Json(counts)),
        )
        return {str(k): int(v or 0) for k, v in counts.items()}

    # ---------------- gallery calendar ----------------
    def list_gallery_calendar(self) -> List[Dict[str, Any]]:
        rows = self._execute("SELECT month, image, title, artist_id, updated_at FROM gallery_calendar ORDER BY month ASC", fetch=True) or []
        return [self._json_safe_dict(r) for r in rows]

    def upsert_gallery_month(self, month: int, image: Optional[str], title: str = "", artist_id: Optional[str] = None) -> None:
        try:
            month = int(month)
        except Exception:
            return
        if month < 1 or month > 12:
            return
        self._execute(
            """
            INSERT INTO gallery_calendar (month, image, title, artist_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (month) DO UPDATE
              SET image = EXCLUDED.image,
                  title = EXCLUDED.title,
                  artist_id = EXCLUDED.artist_id,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (month, image, title or "", artist_id),
        )

    def clear_gallery_month(self, month: int) -> None:
        try:
            month = int(month)
        except Exception:
            return
        if month < 1 or month > 12:
            return
        self._execute("DELETE FROM gallery_calendar WHERE month = %s", (month,))

    # ---------------- temp links ----------------
    def issue_temp_link(
        self,
        scopes: List[str],
        ttl_seconds: int,
        role_ids: Optional[List[str]] = None,
        created_by: Optional[str] = None,
        max_uses: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        token = secrets.token_urlsafe(24)
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=int(ttl_seconds))
        role_ids = role_ids or []
        max_uses = max(1, int(max_uses or 1))
        metadata = metadata or {}
        self._execute(
            """
            INSERT INTO temp_links (token, scopes, role_ids, created_by, created_at, expires_at, max_uses, used_count, metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s)
            """,
            (token, Json(scopes or []), Json(role_ids), created_by, now, expires_at, max_uses, Json(metadata)),
        )
        return {
            "token": token,
            "scopes": scopes or [],
            "role_ids": role_ids,
            "created_by": created_by,
            "created_at": int(now.timestamp()),
            "expires_at": int(expires_at.timestamp()),
            "max_uses": max_uses,
            "used_count": 0,
        }

    def consume_temp_link(self, token: str, user_name: str) -> Optional[Dict[str, Any]]:
        tok = str(token or "").strip()
        if not tok:
            return None
        row = self._fetchone(
            "SELECT token, scopes, role_ids, created_by, created_at, expires_at, max_uses, used_count FROM temp_links WHERE token = %s",
            (tok,),
        )
        if not row:
            return None
        expires_at = row.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at <= datetime.utcnow():
            return None
        used_count = int(row.get("used_count") or 0)
        max_uses = int(row.get("max_uses") or 1)
        if used_count >= max_uses:
            return None
        used_count += 1
        self._execute(
            "UPDATE temp_links SET used_count=%s, used_at=CURRENT_TIMESTAMP, used_by=%s WHERE token=%s",
            (used_count, user_name, tok),
        )
        return self._json_safe_dict(row)

    def purge_expired_temp_links(self) -> int:
        return int(self._execute("DELETE FROM temp_links WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP") or 0)

    # ---------------- web tokens ----------------
    def issue_web_token(
        self,
        user_id: int,
        scopes: Optional[List[str]] = None,
        ttl_seconds: int = 24 * 60 * 60,
        user_name: Optional[str] = None,
        user_icon: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=int(ttl_seconds))
        scopes = scopes or ["*"]
        metadata = metadata or {}
        self._execute(
            """
            INSERT INTO web_tokens (token, user_id, scopes, user_name, user_icon, created_at, expires_at, metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (token, int(user_id), Json(scopes), user_name, user_icon, now, expires_at, Json(metadata)),
        )
        return {
            "token": token,
            "user_id": int(user_id),
            "scopes": scopes,
            "user_name": user_name,
            "user_icon": user_icon,
            "created_at": int(now.timestamp()),
            "expires_at": int(expires_at.timestamp()),
        }

    def find_web_token(self, token: str) -> Optional[Dict[str, Any]]:
        tok = str(token or "").strip()
        if not tok:
            return None
        row = self._fetchone(
            "SELECT token, user_id, scopes, user_name, user_icon, created_at, expires_at FROM web_tokens WHERE token = %s",
            (tok,),
        )
        if not row:
            return None
        expires_at = row.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at <= datetime.utcnow():
            return None
        return self._json_safe_dict(row)

    def purge_expired_web_tokens(self) -> int:
        return int(self._execute("DELETE FROM web_tokens WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP") or 0)

    # ---------------- legacy migrations & reporting ----------------
    def _data_dir(self) -> str:
        base = None
        try:
            if self._settings:
                base = self._settings.get("BOT.DATA_DIR", None)
        except Exception:
            base = None
        if not base:
            base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
        if not base:
            base = os.getenv("BIGTREE_WORKDIR") or os.path.join(os.getcwd(), ".bigtree")
        os.makedirs(base, exist_ok=True)
        return base

    def _migrate_legacy_state_files(self) -> None:
        base = self._data_dir()
        sources = {
            "auth_roles.json": os.path.join(base, "auth_roles.json"),
            "gallery_settings.json": os.path.join(base, "gallery_settings.json"),
            "gallery_hidden.json": os.path.join(base, "gallery_hidden.json"),
            "gallery_reactions.json": os.path.join(base, "gallery_reactions.json"),
            "gallery_calendar.json": os.path.join(base, "gallery_calendar.json"),
            "temp_links.json": os.path.join(base, "temp_links.json"),
            "web_tokens.json": os.path.join(base, "web_tokens.json"),
        }

        # auth_roles.json
        if os.path.exists(sources["auth_roles.json"]) and not self.is_legacy_imported("auth_roles.json"):
            try:
                raw = json.loads(open(sources["auth_roles.json"], "r", encoding="utf-8").read())
                if isinstance(raw, dict):
                    self.update_auth_roles(raw if all(isinstance(v, list) for v in raw.values()) else (raw.get("role_scopes") or {}))
                    self.mark_legacy_imported("auth_roles.json")
            except Exception:
                pass

        # gallery_settings.json (TinyDB style)
        if os.path.exists(sources["gallery_settings.json"]) and not self.is_legacy_imported("gallery_settings.json"):
            try:
                raw = json.loads(open(sources["gallery_settings.json"], "r", encoding="utf-8").read())
                settings_payload: Dict[str, Any] = {}
                if isinstance(raw, dict) and "_default" in raw:
                    table = raw.get("_default") or {}
                    for _, row in (table.items() if isinstance(table, dict) else []):
                        if isinstance(row, dict) and row.get("_type") == "settings":
                            settings_payload = {k: v for k, v in row.items() if k not in ("_type", "updated_at")}
                            break
                elif isinstance(raw, dict):
                    settings_payload = raw
                if isinstance(settings_payload, dict) and settings_payload:
                    self.update_gallery_settings(settings_payload)
                    self.mark_legacy_imported("gallery_settings.json")
            except Exception:
                pass

        # gallery_hidden.json (TinyDB style)
        if os.path.exists(sources["gallery_hidden.json"]) and not self.is_legacy_imported("gallery_hidden.json"):
            try:
                raw = json.loads(open(sources["gallery_hidden.json"], "r", encoding="utf-8").read())
                if isinstance(raw, dict) and "_default" in raw:
                    table = raw.get("_default") or {}
                    for _, row in (table.items() if isinstance(table, dict) else []):
                        if not isinstance(row, dict):
                            continue
                        if row.get("_type") == "hidden" and row.get("item_id"):
                            self.set_gallery_hidden(str(row.get("item_id")), bool(row.get("hidden") is True))
                self.mark_legacy_imported("gallery_hidden.json")
            except Exception:
                pass

        # gallery_reactions.json (TinyDB style)
        if os.path.exists(sources["gallery_reactions.json"]) and not self.is_legacy_imported("gallery_reactions.json"):
            try:
                raw = json.loads(open(sources["gallery_reactions.json"], "r", encoding="utf-8").read())
                if isinstance(raw, dict) and "_default" in raw:
                    table = raw.get("_default") or {}
                    for _, row in (table.items() if isinstance(table, dict) else []):
                        if not isinstance(row, dict):
                            continue
                        if row.get("_type") == "reaction" and row.get("item_id"):
                            counts = row.get("counts") or {}
                            if isinstance(counts, dict):
                                iid = str(row.get("item_id"))
                                self._execute(
                                    """
                                    INSERT INTO gallery_reactions (item_id, counts)
                                    VALUES (%s, %s)
                                    ON CONFLICT (item_id) DO UPDATE SET counts = EXCLUDED.counts, updated_at=CURRENT_TIMESTAMP
                                    """,
                                    (iid, Json(counts)),
                                )
                self.mark_legacy_imported("gallery_reactions.json")
            except Exception:
                pass

        # gallery_calendar.json (TinyDB style)
        if os.path.exists(sources["gallery_calendar.json"]) and not self.is_legacy_imported("gallery_calendar.json"):
            try:
                raw = json.loads(open(sources["gallery_calendar.json"], "r", encoding="utf-8").read())
                if isinstance(raw, dict) and "_default" in raw:
                    table = raw.get("_default") or {}
                    for _, row in (table.items() if isinstance(table, dict) else []):
                        if not isinstance(row, dict):
                            continue
                        if row.get("_type") == "month":
                            m = row.get("month")
                            try:
                                m = int(m)
                            except Exception:
                                continue
                            self.upsert_gallery_month(m, row.get("image"), row.get("title") or "", row.get("artist_id"))
                self.mark_legacy_imported("gallery_calendar.json")
            except Exception:
                pass

        # temp_links.json
        if os.path.exists(sources["temp_links.json"]) and not self.is_legacy_imported("temp_links.json"):
            try:
                raw = json.loads(open(sources["temp_links.json"], "r", encoding="utf-8").read())
                links = raw.get("links") if isinstance(raw, dict) else []
                if isinstance(links, list):
                    for link in links:
                        if not isinstance(link, dict):
                            continue
                        tok = str(link.get("token") or "").strip()
                        if not tok:
                            continue
                        expires_at = datetime.utcfromtimestamp(int(link.get("expires_at") or 0)) if link.get("expires_at") else None
                        created_at = datetime.utcfromtimestamp(int(link.get("created_at") or 0)) if link.get("created_at") else datetime.utcnow()
                        self._execute(
                            """
                            INSERT INTO temp_links (token, scopes, role_ids, created_by, created_at, expires_at, max_uses, used_count, used_at, used_by, metadata)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (token) DO NOTHING
                            """,
                            (
                                tok,
                                Json(link.get("scopes") or []),
                                Json(link.get("role_ids") or []),
                                link.get("created_by"),
                                created_at,
                                expires_at,
                                int(link.get("max_uses") or 1),
                                int(link.get("used_count") or 0),
                                datetime.utcfromtimestamp(int(link.get("used_at") or 0)) if link.get("used_at") else None,
                                link.get("used_by"),
                                Json({"legacy": True}),
                            ),
                        )
                self.mark_legacy_imported("temp_links.json")
            except Exception:
                pass

        # web_tokens.json
        if os.path.exists(sources["web_tokens.json"]) and not self.is_legacy_imported("web_tokens.json"):
            try:
                raw = json.loads(open(sources["web_tokens.json"], "r", encoding="utf-8").read())
                tokens = raw.get("tokens") if isinstance(raw, dict) else []
                if isinstance(tokens, list):
                    for t in tokens:
                        if not isinstance(t, dict):
                            continue
                        tok = str(t.get("token") or "").strip()
                        if not tok:
                            continue
                        expires_at = datetime.utcfromtimestamp(int(t.get("expires_at") or 0)) if t.get("expires_at") else None
                        created_at = datetime.utcfromtimestamp(int(t.get("created_at") or 0)) if t.get("created_at") else datetime.utcnow()
                        self._execute(
                            """
                            INSERT INTO web_tokens (token, user_id, scopes, user_name, user_icon, created_at, expires_at, metadata)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (token) DO NOTHING
                            """,
                            (
                                tok,
                                int(t.get("user_id") or 0),
                                Json(t.get("scopes") or []),
                                t.get("user_name"),
                                t.get("user_icon"),
                                created_at,
                                expires_at,
                                Json({"legacy": True}),
                            ),
                        )
                self.mark_legacy_imported("web_tokens.json")
            except Exception:
                pass

    def _contest_dir(self) -> str:
        try:
            import bigtree as _bt
        except Exception:
            _bt = None
        if _bt and getattr(_bt, "contest_dir", None):
            return str(getattr(_bt, "contest_dir"))
        try:
            if self._settings:
                v = self._settings.get("BOT.contest_dir", None)
                if v:
                    return str(v)
        except Exception:
            pass
        base = self._data_dir()
        # default to sibling "contest" next to data dir
        return os.path.abspath(os.path.join(base, "..", "contest"))

    def _migrate_legacy_contests(self) -> None:
        contest_dir = self._contest_dir()
        if not os.path.isdir(contest_dir):
            return
        try:
            from bigtree.modules import media as media_mod
        except Exception:
            return
        media_dir = media_mod.get_media_dir()
        imported_any = 0
        for name in os.listdir(contest_dir):
            if not name.endswith(".json"):
                continue
            if name == "admin_clients.json":
                continue
            channel_id = os.path.splitext(name)[0]
            key = f"contest:{channel_id}"
            if self.is_legacy_imported(key):
                continue
            path = os.path.join(contest_dir, name)
            try:
                raw = json.loads(open(path, "r", encoding="utf-8").read())
            except Exception:
                continue
            entries = []
            if isinstance(raw, dict) and "_default" in raw and isinstance(raw["_default"], dict):
                entries = list(raw["_default"].values())
            elif isinstance(raw, dict) and "entries" in raw and isinstance(raw["entries"], list):
                entries = raw["entries"]
            if not entries:
                self.mark_legacy_imported(key)
                continue
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                img = entry.get("filename") or entry.get("image") or entry.get("file") or entry.get("path")
                img = str(img or "").strip()
                if not img:
                    continue
                src = os.path.join(contest_dir, img)
                if not os.path.exists(src):
                    # maybe stored as url-like
                    src = os.path.join(contest_dir, os.path.basename(img))
                if not os.path.exists(src):
                    continue
                ext = os.path.splitext(src)[1].lower() or ".png"
                new_name = f"contest_{channel_id}_{secrets.token_hex(8)}{ext}"
                dst = os.path.join(media_dir, new_name)
                try:
                    import shutil
                    shutil.copy2(src, dst)
                except Exception:
                    continue
                try:
                    from bigtree.modules import media as _mm
                    try:
                        _ = _mm.ensure_thumb(new_name)
                    except Exception:
                        pass
                except Exception:
                    pass
                title = str(entry.get("title") or entry.get("name") or entry.get("caption") or f"Contest {channel_id} Entry {idx+1}")
                meta = {"legacy_contest": True, "contest_channel_id": channel_id, "legacy_entry": entry}
                self.upsert_media_item(
                    media_id=new_name,
                    filename=new_name,
                    title=title,
                    origin_type="contest",
                    origin_label=str(channel_id),
                    url=f"/media/{new_name}",
                    thumb_url=f"/media/thumbs/{new_name}",
                    hidden=False,
                    kind="image",
                    metadata=meta,
                )
                imported_any += 1
            self.mark_legacy_imported(key)
        if imported_any:
            logger.info("[database] migrated contest entries into media storage (%s)", imported_any)

    def _report_legacy_import_sources(self) -> None:
        base = self._data_dir()
        files = [
            "auth_roles.json",
            "gallery_calendar.json",
            "gallery_hidden.json",
            "gallery_reactions.json",
            "gallery_settings.json",
            "temp_links.json",
            "web_tokens.json",
        ]
        logger.info("[database] legacy import report:")
        for f in files:
            path = os.path.join(base, f)
            imported = self.is_legacy_imported(f)
            exists = os.path.exists(path)
            if imported:
                logger.info("  - %s: IMPORTED%s (safe to delete)", f, "" if exists else " (missing on disk)")
            else:
                logger.info("  - %s: PENDING%s", f, "" if exists else " (missing on disk)")
        # contests
        cdir = self._contest_dir()
        if os.path.isdir(cdir):
            for name in sorted(os.listdir(cdir)):
                if not name.endswith(".json") or name == "admin_clients.json":
                    continue
                cid = os.path.splitext(name)[0]
                key = f"contest:{cid}"
                if self.is_legacy_imported(key):
                    logger.info("  - contest/%s: IMPORTED (safe to delete after verifying media)", name)
                else:
                    logger.info("  - contest/%s: PENDING", name)

# ---------------- migrations ----------------
    def _migrate_json_backups(self):
        if self._json_imported and self._count_rows("games") > 0:
            return
        self._json_imported = True
        try:
            self._migrate_bingo_games()
        except Exception as exc:  # pragma: no cover
            logger.warning("[database] bingo migration failed: %s", exc)
        try:
            self._migrate_tarot_sessions()
        except Exception as exc:  # pragma: no cover
            logger.warning("[database] tarot migration failed: %s", exc)
        try:
            self._migrate_cardgames()
        except Exception as exc:  # pragma: no cover
            logger.warning("[database] cardgames migration failed: %s", exc)
        logger.info("[database] json migration complete (games=%s)", self._count_rows("games"))

    def _sync_tarot_decks(self):
        if self._decks_synced and self._count_rows("deck_files") > 0:
            return
        self._decks_synced = True
        decks_dir = self._resolve_tarot_dir()
        decks_dir = os.path.join(decks_dir, "decks")
        imported = 0
        if not os.path.isdir(decks_dir):
            logger.info("[database] tarot decks directory missing: %s", decks_dir)
        else:
            logger.info("[database] syncing tarot decks from %s", decks_dir)
            for name in sorted(os.listdir(decks_dir)):
                if not name.lower().endswith(".json"):
                    continue
                path = os.path.join(decks_dir, name)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        payload = json.load(fh)
                except Exception as exc:  # pragma: no cover
                    logger.warning("[database] failed to load deck %s: %s", path, exc)
                    continue
                deck_id = str(payload.get("deck_id") or payload.get("id") or os.path.splitext(name)[0]).strip()
                if not deck_id:
                    deck_id = os.path.splitext(name)[0]
                self.upsert_deck(deck_id, payload, module="tarot", metadata={"filename": name})
                imported += 1
        if imported == 0:
            try:
                from bigtree.modules import tarot as tarot_mod
                decks = tarot_mod.list_decks()
                if decks:
                    logger.info("[database] syncing tarot decks from tarot module (%s)", len(decks))
                for deck in decks or []:
                    deck_id = str(deck.get("deck_id") or deck.get("id") or deck.get("name") or "").strip()
                    if not deck_id:
                        continue
                    self.upsert_deck(deck_id, deck, module="tarot", metadata={"source": "module"})
                    imported += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("[database] tarot module deck sync failed: %s", exc)
        logger.info("[database] tarot deck sync complete (imported=%s)", imported)

    def _migrate_media_items(self):
        """Migrate media.json (TinyDB) and filesystem-only uploads into Postgres media_items.

        TinyDB remains supported only as an import source.
        """
        # Always attempt a light sync; it's idempotent.
        try:
            from bigtree.modules import media as media_mod
        except Exception:
            return
        try:
            from bigtree.modules import artists as artist_mod
        except Exception:
            artist_mod = None

        imported = 0
        media_dir = None
        try:
            media_dir = media_mod.get_media_dir()
        except Exception:
            media_dir = None

        # 1) Import TinyDB records if the file exists.
        try:
            from tinydb import TinyDB, Query
            path = os.path.join(media_dir, "media.json") if media_dir else None
            if path and os.path.isfile(path):
                db = TinyDB(path)
                q = Query()
                rows = db.search(q._type == "media")
                for r in rows or []:
                    filename = str(r.get("filename") or "").strip()
                    if not filename:
                        continue
                    media_id = f"media:{filename}"
                    title = str(r.get("title") or "").strip()
                    origin_type = str(r.get("origin_type") or "").strip()
                    origin_label = str(r.get("origin_label") or "").strip()
                    artist_id = str(r.get("artist_id") or "").strip() or None
                    artist_name = ""
                    artist_links: Dict[str, Any] = {}
                    if artist_id and artist_mod:
                        try:
                            artist = artist_mod.get_artist(artist_id)
                        except Exception:
                            artist = None
                        if artist:
                            artist_name = str(artist.get("name") or "").strip()
                            links = artist.get("links") if isinstance(artist.get("links"), dict) else {}
                            if links:
                                artist_links = links
                    # URLs are served from /media and /media/thumbs.
                    url = f"/media/{filename}"
                    thumb_url = f"/media/thumbs/{filename}"
                    self.upsert_media_item(
                        media_id=media_id,
                        filename=filename,
                        title=title,
                        artist_name=artist_name,
                        artist_links=artist_links,
                        origin_type=origin_type,
                        origin_label=origin_label,
                        url=url,
                        thumb_url=thumb_url,
                        metadata={"source": "tinydb", "artist_id": artist_id} if artist_id else {"source": "tinydb"},
                    )
                    imported += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("[database] media tinydb import failed: %s", exc)

        # 2) Import filesystem-only images as DB rows (so they stop being 'invisible').
        if media_dir and os.path.isdir(media_dir):
            try:
                existing = set()
                rows = self._execute("SELECT filename FROM media_items WHERE filename IS NOT NULL", fetch=True) or []
                for row in rows:
                    fn = (row or {}).get("filename")
                    if fn:
                        existing.add(fn)
                for name in sorted(os.listdir(media_dir)):
                    if name in ("media.json", "thumbs"):
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
                        continue
                    if name in existing:
                        continue
                    media_id = f"media:{name}"
                    url = f"/media/{name}"
                    thumb_url = f"/media/thumbs/{name}"
                    self.upsert_media_item(
                        media_id=media_id,
                        filename=name,
                        title=os.path.splitext(name)[0],
                        url=url,
                        thumb_url=thumb_url,
                        metadata={"source": "filesystem"},
                    )
                    imported += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("[database] media filesystem import failed: %s", exc)

        if imported:
            logger.info("[database] media import complete (upserted=%s)", imported)

    def _migrate_bingo_games(self):
        bingo_dir = self._resolve_bingo_dir()
        db_dir = os.path.join(bingo_dir, "db")
        if not os.path.isdir(db_dir):
            logger.info("[database] bingo db dir missing: %s", db_dir)
            return
        logger.info("[database] importing bingo games from %s", db_dir)
        for name in sorted(os.listdir(db_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(db_dir, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            default = data.get("_default") or {}
            game_doc = next((entry for entry in default.values() if entry.get("_type") == "game"), None)
            if not game_doc:
                continue
            game_id = game_doc.get("game_id") or name[:-5]
            active = bool(game_doc.get("active"))
            created_at = self._as_datetime(game_doc.get("created_at"))
            ended_at = self._as_datetime(game_doc.get("ended_at"))
            metadata = {
                "currency": game_doc.get("currency"),
                "stage": game_doc.get("stage"),
                "price": game_doc.get("price"),
                "pot": game_doc.get("pot"),
            }
            self._store_game(
                game_id=game_id,
                module="bingo",
                payload=data,
                title=game_doc.get("title"),
                channel_id=self._force_int(game_doc.get("channel_id")),
                created_by=self._force_int(game_doc.get("created_by")),
                created_at=created_at,
                ended_at=ended_at,
                status="active" if active else "ended",
                active=active,
                metadata=metadata,
                run_source="import",
            )
            owners: Dict[str, Tuple[str, Optional[int]]] = {}
            for entry in default.values():
                if entry.get("_type") != "card":
                    continue
                owner = str(entry.get("owner_name") or "").strip()
                if not owner:
                    continue
                owners.setdefault(owner, (owner, self._force_int(entry.get("owner_user_id"))))
            for owner_name, (name_val, owner_id) in owners.items():
                self._store_game_player(game_id, owner_name, metadata={"owner_user_id": owner_id}, role="player")

    def _migrate_tarot_sessions(self):
        tarot_dir = self._resolve_tarot_dir()
        path = os.path.join(tarot_dir, "tarot_sessions.json")
        if not os.path.exists(path):
            logger.info("[database] tarot sessions file missing: %s", path)
            return
        logger.info("[database] importing tarot sessions from %s", path)
        db = TinyDB(path)
        for entry in db.all():
            if entry.get("_type") != "session":
                continue
            session_id = entry.get("session_id") or entry.get("id") or entry.get("sessionId")
            active = bool(entry.get("active")) or entry.get("status") in ("active", "running")
            status = entry.get("status") or ("active" if active else "ended")
            created_at = self._as_datetime(entry.get("created_at") or entry.get("started_at"))
            ended_at = self._as_datetime(entry.get("ended_at"))
            metadata = {
                "deck_id": entry.get("deck_id"),
                "stage": entry.get("stage"),
                "status": status,
            }
            if not session_id:
                continue
            self._store_game(
                game_id=session_id,
                module="tarot",
                payload=entry,
                title=entry.get("title") or entry.get("name") or "Tarot",
                channel_id=self._force_int(entry.get("channel_id")),
                created_by=self._force_int(entry.get("created_by")),
                created_at=created_at,
                ended_at=ended_at,
                status=status,
                active=active,
                metadata=metadata,
                run_source="import",
            )
            for player in self._extract_tarot_players(entry):
                self._store_game_player(session_id, player, role="player")

    def _migrate_cardgames(self):
        logger.info("[database] cardgames migration skipped (Postgres-only mode)")

    # ---------------- helpers ----------------
    def _store_game(
        self,
        *,
        game_id: str,
        module: str,
        payload: Any,
        title: Optional[str] = None,
        channel_id: Optional[int] = None,
        created_by: Optional[int] = None,
        venue_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        status: Optional[str] = None,
        active: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        run_source: str = "api",
    ):
        metadata = metadata or {}
        metadata.setdefault("run_source", run_source)
        if venue_id is None and created_by:
            venue_id = self._find_venue_for_discord_admin(int(created_by))

        # Optional event link. If payload carries an event_code, attach event_id.
        event_id = None
        try:
            event_code = None
            if isinstance(payload, dict):
                event_code = payload.get("event_code") or payload.get("eventCode") or payload.get("event")
            if not event_code and isinstance(metadata, dict):
                event_code = metadata.get("event_code") or metadata.get("event")
            if event_code:
                ev = self.get_event_by_code(str(event_code))
                if ev and ev.get("status") != "ended":
                    event_id = int(ev.get("id"))
        except Exception:
            event_id = None
        if event_id is None and venue_id:
            event_id = self._find_active_event_id_for_venue(int(venue_id))

        sql = """
        INSERT INTO games (game_id, module, title, channel_id, created_by, venue_id, event_id, created_at, ended_at, status, active, payload, metadata, run_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (game_id) DO UPDATE
          SET module = EXCLUDED.module,
              title = COALESCE(EXCLUDED.title, games.title),
              channel_id = COALESCE(EXCLUDED.channel_id, games.channel_id),
              created_by = COALESCE(EXCLUDED.created_by, games.created_by),
              venue_id = COALESCE(EXCLUDED.venue_id, games.venue_id),
              event_id = COALESCE(EXCLUDED.event_id, games.event_id),
              created_at = COALESCE(EXCLUDED.created_at, games.created_at),
              ended_at = COALESCE(EXCLUDED.ended_at, games.ended_at),
              status = COALESCE(EXCLUDED.status, games.status),
              active = EXCLUDED.active,
              payload = EXCLUDED.payload,
              metadata = games.metadata || EXCLUDED.metadata,
              run_source = COALESCE(EXCLUDED.run_source, games.run_source)
        """
        self._execute(
            sql,
            (
                game_id,
                module,
                title,
                channel_id,
                created_by,
                venue_id,
                event_id,
                created_at,
                ended_at,
                status,
                active,
                Json(payload),
                Json(metadata),
                run_source,
            ),
        )

    def _find_venue_for_discord_admin(self, discord_id: int) -> Optional[int]:
        """Resolve a default venue for a Discord admin.

        Venues store a list of Discord IDs in venues.metadata.admin_discord_ids.
        If a game is created without an explicit venue_id, we attach the venue
        based on created_by.
        """
        if not discord_id:
            return None
        try:
            member = self.get_discord_venue(int(discord_id))
            if member and member.get("venue_id"):
                return int(member.get("venue_id"))
        except Exception:
            pass
        try:
            did = str(int(discord_id))
        except Exception:
            did = str(discord_id)
        rows = self._execute("SELECT id, metadata FROM venues", fetch=True) or []
        for r in rows:
            md = r.get("metadata") or {}
            ids = md.get("admin_discord_ids")
            if isinstance(ids, str):
                ids = [x.strip() for x in ids.split(",") if x.strip()]
            if isinstance(ids, list) and did in {str(x) for x in ids}:
                try:
                    return int(r.get("id"))
                except Exception:
                    return None
        return None

    def _store_game_player(self, game_id: str, name: str, role: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        if not name:
            return
        metadata = metadata or {}
        self._execute(
            """
            INSERT INTO game_players (game_id, name, role, metadata)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (game_id, name, role) DO UPDATE
              SET metadata = game_players.metadata || EXCLUDED.metadata
            """,
            (game_id, name, role, Json(metadata)),
        )

    def _resolve_bot_base(self) -> str:
        base = None
        if self._settings:
            base = self._settings.get("BOT.DATA_DIR")
        if not base:
            base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
        if not base:
            base = os.getenv("BIGTREE_WORKDIR")
        if not base:
            base = os.path.join(os.getcwd(), ".bigtree")
        return base

    def _resolve_tarot_dir(self) -> str:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        tarot_db = cfg.get("BOT", {}).get("tarot_db")
        if tarot_db:
            return os.path.dirname(tarot_db)
        base = self._resolve_bot_base()
        path = os.path.join(base, "tarot")
        os.makedirs(path, exist_ok=True)
        return path

    def _resolve_bingo_dir(self) -> str:
        base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
        if base:
            path = os.path.join(base, "bingo")
        else:
            env = os.getenv("BIGTREE_WORKDIR")
            if env:
                path = os.path.join(env, "bingo")
            else:
                path = os.path.join(os.getcwd(), ".bigtree", "bingo")
        os.makedirs(path, exist_ok=True)
        return path

    def _resolve_cardgames_dir(self) -> str:
        base = os.getenv("BIGTREE_CARDGAMES_DB_DIR")
        if base:
            path = base
        else:
            base = self._resolve_bot_base()
            path = os.path.join(base, "cardgames")
        os.makedirs(path, exist_ok=True)
        return path

    def _as_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.utcfromtimestamp(float(value))
        except Exception:
            return None

    def _force_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _extract_tarot_players(self, session: Dict[str, Any]) -> List[str]:
        players: List[str] = []
        candidates = session.get("players") or session.get("roster") or session.get("participants") or []
        if isinstance(candidates, dict):
            candidates = list(candidates.values())
        if isinstance(candidates, list):
            for entry in candidates:
                name = None
                if isinstance(entry, str):
                    name = entry
                elif isinstance(entry, dict):
                    name = entry.get("name") or entry.get("player_name")
                if name:
                    players.append(str(name).strip())
        primary = session.get("player_name") or session.get("priestess_name")
        if primary:
            players.append(str(primary).strip())
        return [p for p in dict.fromkeys(players) if p]

    def _extract_cardgame_players(self, payload: Dict[str, Any]) -> List[str]:
        candidates = []
        parsed = payload.get("state_json_parsed") or {}
        if isinstance(parsed, dict):
            for key in ("players", "seats", "roster"):
                raw = parsed.get(key)
                if isinstance(raw, dict):
                    candidates.extend(raw.values())
                elif isinstance(raw, list):
                    candidates.extend(raw)
        names = []
        for entry in candidates:
            if isinstance(entry, str):
                names.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("player_name")
                if name:
                    names.append(name)
        fallback = payload.get("player_name")
        if fallback:
            names.append(fallback)
        return [str(n).strip() for n in dict.fromkeys(names) if str(n).strip()]

    def _extract_players_from_payload(self, payload: Any) -> List[str]:
        """Best-effort player extraction from arbitrary game payloads.

        Used for legacy games where we didn't persist game_players rows.
        """
        if not payload:
            return []
        if not isinstance(payload, dict):
            return []

        names: List[str] = []
        # Common keys
        for key in ("players", "owners", "roster", "participants"):
            raw = payload.get(key)
            if isinstance(raw, dict):
                raw = list(raw.values())
            if isinstance(raw, list):
                for entry in raw:
                    if isinstance(entry, str):
                        names.append(entry)
                    elif isinstance(entry, dict):
                        nm = entry.get("name") or entry.get("owner_name") or entry.get("player") or entry.get("player_name")
                        if nm:
                            names.append(nm)

        # Bingo state JSON (often nested)
        state = payload.get("state")
        if isinstance(state, dict):
            owners = state.get("owners") or state.get("players")
            if isinstance(owners, list):
                for entry in owners:
                    if isinstance(entry, dict) and entry.get("owner_name"):
                        names.append(entry.get("owner_name"))

        # Cardgames embedded state
        try:
            names.extend(self._extract_cardgame_players(payload))
        except Exception:
            pass

        return [str(n).strip() for n in dict.fromkeys(names) if str(n).strip()]
