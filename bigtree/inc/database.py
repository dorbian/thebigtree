from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta
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
        self._lock = threading.RLock()
        self._initialized = False
        self._json_imported = False
        self._decks_synced = False
        self._configs_seeded = False

    def initialize(self):
        with self._lock:
            if self._initialized:
                return
            self._ensure_tables()
            self._import_ini_configs()
            self._sync_tarot_decks()
            self._migrate_json_backups()
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
            CREATE TABLE IF NOT EXISTS venues (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                currency_name TEXT,
                minimal_spend BIGINT,
                background_image TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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
        ]
        for stmt in statements:
            self._execute(stmt)
        with self._connect() as conn:
            self._ensure_column(conn, "games", "run_source", "TEXT DEFAULT 'api'")
            self._ensure_column(conn, "games", "claimed_by", "INTEGER")
            self._ensure_column(conn, "games", "claimed_at", "TIMESTAMPTZ")
            self._ensure_column(conn, "games", "venue_id", "INTEGER")
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
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
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
            where.append("(lower(g.game_id) LIKE %s OR lower(COALESCE(g.title,'')) LIKE %s)")
            params.extend([qv, qv])

        if player:
            pv = f"%{str(player).strip().lower()}%"
            where.append(
                "EXISTS (SELECT 1 FROM game_players gp WHERE gp.game_id = g.game_id AND lower(gp.name) LIKE %s)"
            )
            params.append(pv)

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
                g["players"] = indexed.get(g.get("game_id"), [])
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
            SELECT id, name, currency_name, minimal_spend, background_image, metadata, created_at, updated_at
            FROM venues
            ORDER BY name ASC
            """,
            fetch=True,
        )
        return [dict(r) for r in (rows or [])]

    def upsert_venue(
        self,
        name: str,
        currency_name: Optional[str] = None,
        minimal_spend: Optional[int] = None,
        background_image: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        metadata = metadata or {}
        row = self._fetchone(
            """
            INSERT INTO venues (name, currency_name, minimal_spend, background_image, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE
              SET currency_name = COALESCE(EXCLUDED.currency_name, venues.currency_name),
                  minimal_spend = COALESCE(EXCLUDED.minimal_spend, venues.minimal_spend),
                  background_image = COALESCE(EXCLUDED.background_image, venues.background_image),
                  metadata = venues.metadata || EXCLUDED.metadata,
                  updated_at = CURRENT_TIMESTAMP
            RETURNING id, name, currency_name, minimal_spend, background_image, metadata, created_at, updated_at
            """,
            (name.strip(), currency_name, minimal_spend, background_image, Json(metadata)),
        )
        return dict(row) if row else None

    def get_venue(self, venue_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            """
            SELECT id, name, currency_name, minimal_spend, background_image, metadata, created_at, updated_at
            FROM venues
            WHERE id = %s
            """,
            (venue_id,),
        )
        return dict(row) if row else None

    def update_venue(self, venue_id: int, *, currency_name: Optional[str] = None, minimal_spend: Optional[int] = None, background_image: Optional[str] = None) -> bool:
        if not venue_id:
            return False
        count = self._execute(
            """
            UPDATE venues
            SET currency_name = COALESCE(%s, currency_name),
                minimal_spend = COALESCE(%s, minimal_spend),
                background_image = COALESCE(%s, background_image),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (currency_name, minimal_spend, background_image, venue_id),
        )
        return bool(count)

    def get_user_venue(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        row = self._fetchone(
            """
            SELECT vm.venue_id, vm.role, vm.metadata AS membership_metadata,
                   v.id AS id, v.name, v.currency_name, v.minimal_spend, v.background_image, v.metadata,
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
        join_code = payload.get("join_code") or payload.get("joinCode") or payload.get("join")
        outcome = "active" if row.get("active") else (status or "ended")
        if winnings not in (None, ""):
            outcome = f"{outcome} (winnings {winnings})"
        row["currency"] = currency
        row["pot"] = pot
        row["winnings"] = winnings
        row["outcome"] = outcome
        row["join_code"] = join_code

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
        card_dir = self._resolve_cardgames_dir()
        db_path = os.path.join(card_dir, "cardgames.db")
        if not os.path.exists(db_path):
            logger.info("[database] cardgames db missing: %s", db_path)
            return
        logger.info("[database] importing cardgames sessions from %s", db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute("SELECT * FROM sessions"):
                data = dict(row)
                session_id = data.get("session_id") or data.get("game_id")
                if not session_id:
                    continue
                status = data.get("status") or data.get("stage") or "unknown"
                active = status.lower() not in ("finished", "ended", "complete", "closed")
                created_at = self._as_datetime(data.get("created_at"))
                ended_at = self._as_datetime(data.get("updated_at"))
                payload = dict(row)
                state_json = payload.get("state_json")
                if isinstance(state_json, str):
                    try:
                        payload["state_json_parsed"] = json.loads(state_json)
                    except Exception:
                        pass
                metadata = {
                    "currency": data.get("currency"),
                    "pot": data.get("pot"),
                    "status": status,
                }
                self._store_game(
                    game_id=session_id,
                    module="cardgames",
                    payload=payload,
                    title=payload.get("game_id"),
                    created_at=created_at,
                    ended_at=ended_at,
                    status=status,
                    active=active,
                    metadata=metadata,
                    run_source="import",
                )
                for player in self._extract_cardgame_players(payload):
                    self._store_game_player(session_id, player, role="player")
        finally:
            conn.close()

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
        created_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        status: Optional[str] = None,
        active: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        run_source: str = "api",
    ):
        metadata = metadata or {}
        metadata.setdefault("run_source", run_source)
        sql = """
        INSERT INTO games (game_id, module, title, channel_id, created_by, created_at, ended_at, status, active, payload, metadata, run_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (game_id) DO UPDATE
          SET module = EXCLUDED.module,
              title = COALESCE(EXCLUDED.title, games.title),
              channel_id = COALESCE(EXCLUDED.channel_id, games.channel_id),
              created_by = COALESCE(EXCLUDED.created_by, games.created_by),
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
                created_at,
                ended_at,
                status,
                active,
                Json(payload),
                Json(metadata),
                run_source,
            ),
        )

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
