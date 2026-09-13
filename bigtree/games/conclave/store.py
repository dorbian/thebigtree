"""PostgreSQL persistence for Verdant Conclave."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import secrets
from typing import Any, Callable, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json

from bigtree.inc.database import get_database
from . import engine, server_config

Mutator = Callable[[Dict[str, Any]], Dict[str, Any] | None]


class ConclaveStore:
    def __init__(self):
        self.db = get_database()

    @staticmethod
    def _new_id() -> str:
        return f"conclave-{secrets.token_hex(4)}"

    def create(
        self,
        *,
        title: str,
        guild_id: int,
        channel_id: int,
        host_user_id: int,
        dedicated_channel: bool,
    ) -> Dict[str, Any]:
        config = server_config.get_config(self.db)
        if not config.get("enabled", True):
            raise engine.GameError(
                "Verdant Conclave is disabled for this server.",
                "disabled",
            )
        existing = self.get_active_by_channel(channel_id)
        if existing:
            raise engine.GameError("This channel already has an active Conclave.", "channel_busy")

        active_for_guild = sum(
            1
            for current in self.list_active(500)
            if int(current.get("guild_id") or 0) == int(guild_id)
        )
        max_games = int(config.get("max_concurrent_games") or 4)
        if active_for_guild >= max_games:
            raise engine.GameError(
                f"This server already has {active_for_guild} active Conclave(s); "
                f"the configured limit is {max_games}.",
                "concurrent_limit",
            )

        game_id = self._new_id()
        state = engine.new_state(
            game_id,
            title=title,
            guild_id=guild_id,
            channel_id=channel_id,
            host_user_id=host_user_id,
            dedicated_channel=dedicated_channel,
        )
        server_config.apply_to_state(state, config)
        try:
            self.db.upsert_game(
                game_id=game_id,
                module=engine.MODULE,
                payload=state,
                title=state["title"],
                channel_id=channel_id,
                created_by=host_user_id,
                status=state["phase"],
                active=True,
                metadata={"discord_game": True, "dedicated_channel": bool(dedicated_channel)},
                run_source="discord",
            )
        except psycopg2.IntegrityError as exc:
            # The schema has a partial unique index for active Conclaves per
            # channel. Convert a concurrent-create race into a useful game error.
            raise engine.GameError(
                "This channel already has an active Conclave.", "channel_busy"
            ) from exc
        return state

    def _row_to_state(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        payload = row.get("payload") or {}
        return deepcopy(payload) if isinstance(payload, dict) else None

    def get(self, game_id: str) -> Optional[Dict[str, Any]]:
        row = self.db._fetchone(
            "SELECT payload FROM games WHERE game_id = %s AND module = %s",
            (str(game_id), engine.MODULE),
        )
        return self._row_to_state(row)

    def get_active_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        row = self.db._fetchone(
            """
            SELECT payload
            FROM games
            WHERE module = %s AND channel_id = %s AND active = TRUE
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (engine.MODULE, int(channel_id)),
        )
        return self._row_to_state(row)

    def list_active(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.db._fetchall(
            """
            SELECT payload
            FROM games
            WHERE module = %s AND active = TRUE
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT %s
            """,
            (engine.MODULE, max(1, min(int(limit), 500))),
        )
        out = []
        for row in rows:
            state = self._row_to_state(row)
            if state:
                out.append(state)
        return out

    def set_panel_message(self, game_id: str, message_id: int) -> Optional[Dict[str, Any]]:
        return self.mutate(game_id, lambda state: state.__setitem__("panel_message_id", int(message_id)))

    def mutate(self, game_id: str, mutator: Mutator) -> Dict[str, Any]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT payload
                FROM games
                WHERE game_id = %s AND module = %s
                FOR UPDATE
                """,
                (str(game_id), engine.MODULE),
            )
            row = cur.fetchone()
            if not row:
                raise engine.GameError("Conclave session not found.", "not_found")
            state = deepcopy(row.get("payload") or {})
            result = mutator(state)
            if isinstance(result, dict):
                state = result
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            active = state.get("phase") != engine.PHASE_ENDED
            cur.execute(
                """
                UPDATE games
                SET payload = %s,
                    title = %s,
                    channel_id = %s,
                    status = %s,
                    active = %s,
                    ended_at = CASE WHEN %s THEN ended_at ELSE COALESCE(ended_at, CURRENT_TIMESTAMP) END
                WHERE game_id = %s
                """,
                (
                    Json(state),
                    state.get("title"),
                    int(state.get("channel_id")),
                    state.get("phase"),
                    active,
                    active,
                    str(game_id),
                ),
            )
            return deepcopy(state)

    def mutate_active_channel(self, channel_id: int, mutator: Mutator) -> Dict[str, Any]:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT game_id, payload
                FROM games
                WHERE module = %s AND channel_id = %s AND active = TRUE
                ORDER BY created_at DESC NULLS LAST, id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (engine.MODULE, int(channel_id)),
            )
            row = cur.fetchone()
            if not row:
                raise engine.GameError("There is no active Conclave in this channel.", "not_found")
            state = deepcopy(row.get("payload") or {})
            result = mutator(state)
            if isinstance(result, dict):
                state = result
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            active = state.get("phase") != engine.PHASE_ENDED
            cur.execute(
                """
                UPDATE games
                SET payload = %s,
                    status = %s,
                    active = %s,
                    ended_at = CASE WHEN %s THEN ended_at ELSE COALESCE(ended_at, CURRENT_TIMESTAMP) END
                WHERE game_id = %s
                """,
                (Json(state), state.get("phase"), active, active, row.get("game_id")),
            )
            return deepcopy(state)
