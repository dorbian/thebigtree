from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

# cardgames.py only needs psycopg2.extras.Json for persistence wrappers.  Stub
# that tiny dependency so the pure reducers remain testable on development
# machines where the production PostgreSQL driver is intentionally absent.
_psycopg2 = types.ModuleType("psycopg2")
_extras = types.ModuleType("psycopg2.extras")
_extras.Json = lambda value: value
_psycopg2.extras = _extras
sys.modules.setdefault("psycopg2", _psycopg2)
sys.modules.setdefault("psycopg2.extras", _extras)

_CARDGAMES_PATH = Path(__file__).parents[1] / "bigtree" / "modules" / "cardgames.py"
_SPEC = importlib.util.spec_from_file_location("bigtree_cardgames_engine", _CARDGAMES_PATH)
assert _SPEC and _SPEC.loader
cardgames = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cardgames)


def card(rank: str, suit: str = "spades"):
    return {"rank": rank, "suit": suit, "code": f"{rank}{suit[0].upper()}"}


class CardgameReducerTests(unittest.TestCase):
    def test_blackjack_stand_advances_to_second_split_hand(self):
        state = {
            "deck": [],
            "player_hand": [card("8"), card("8", "hearts")],
            "player_hands": [
                [card("8"), card("3")],
                [card("8", "hearts"), card("4")],
            ],
            "hand_multipliers": [1, 1],
            "hand_results": [None, None],
            "active_hand": 0,
            "dealer_hand": [card("10"), card("7")],
            "status": "live",
            "result": None,
        }

        updated, error = cardgames._apply_blackjack_action(state, "stand")

        self.assertIsNone(error)
        self.assertEqual(1, updated["active_hand"])
        self.assertEqual(updated["player_hands"][1], updated["player_hand"])
        self.assertEqual("pending", updated["hand_results"][0])
        self.assertEqual("live", updated["status"])

    def test_blackjack_bust_advances_to_second_split_hand(self):
        state = {
            "deck": [card("5")],
            "player_hand": [card("K"), card("Q")],
            "player_hands": [
                [card("K"), card("Q")],
                [card("4"), card("5")],
            ],
            "hand_multipliers": [1, 1],
            "hand_results": [None, None],
            "active_hand": 0,
            "dealer_hand": [card("10"), card("7")],
            "status": "live",
            "result": None,
        }

        updated, error = cardgames._apply_blackjack_action(state, "hit")

        self.assertIsNone(error)
        self.assertEqual("bust", updated["hand_results"][0])
        self.assertEqual(1, updated["active_hand"])
        self.assertEqual(updated["player_hands"][1], updated["player_hand"])
        self.assertEqual("live", updated["status"])

    def test_blackjack_double_advances_to_second_split_hand(self):
        state = {
            "deck": [card("2")],
            "player_hand": [card("8"), card("3")],
            "player_hands": [
                [card("8"), card("3")],
                [card("8", "hearts"), card("4")],
            ],
            "hand_multipliers": [1, 1],
            "hand_results": [None, None],
            "active_hand": 0,
            "dealer_hand": [card("10"), card("7")],
            "status": "live",
            "result": None,
        }

        updated, error = cardgames._apply_blackjack_action(state, "double")

        self.assertIsNone(error)
        self.assertEqual(2, updated["hand_multipliers"][0])
        self.assertEqual("pending", updated["hand_results"][0])
        self.assertEqual(1, updated["active_hand"])
        self.assertEqual(updated["player_hands"][1], updated["player_hand"])

    def test_craps_round_cannot_be_rolled_twice(self):
        session = {
            "session_id": "s1",
            "priestess_token": "host-secret",
            "game_id": "crapslite",
            "status": "live",
            "state": {
                "status": "live",
                "round": 3,
                "betting_open": False,
                "players": {},
                "last_resolution": {"round": 3, "roll_total": 8},
            },
        }
        old_get = cardgames.get_session_by_id
        try:
            cardgames.get_session_by_id = lambda _sid: session
            host_action_reducer = cardgames.host_action.__wrapped__.__wrapped__
            with self.assertRaisesRegex(ValueError, "already rolled this round"):
                host_action_reducer("s1", "host-secret", "roll")
        finally:
            cardgames.get_session_by_id = old_get

    def test_poll_events_returns_liveness_and_events_from_one_query(self):
        calls = []

        class FakeDb:
            def _execute(self, sql, params, fetch=False):
                calls.append((sql, params, fetch))
                return [
                    {"id": 7, "ts": 12.5, "type": "STATE_UPDATED", "data": {"action": "hit"}},
                    {"id": 8, "ts": 13.5, "type": "STATE_UPDATED", "data": '{"action":"stand"}'},
                ]

        old_db = cardgames._db
        try:
            cardgames._db = lambda: FakeDb()
            alive, events = cardgames.poll_events("session-1", 6)
        finally:
            cardgames._db = old_db

        self.assertTrue(alive)
        self.assertEqual([7, 8], [event["seq"] for event in events])
        self.assertEqual("stand", events[1]["data"]["action"])
        self.assertEqual(1, len(calls))
        self.assertTrue(calls[0][2])

    def test_finished_session_cleanup_is_throttled_and_uses_cascade(self):
        calls = []

        class FakeDb:
            def _execute(self, sql, params=None, fetch=False):
                calls.append((" ".join(sql.split()), params, fetch))
                return 0

        old_db = cardgames._db
        old_now = cardgames._now
        old_last = cardgames._LAST_CLEANUP
        try:
            cardgames._db = lambda: FakeDb()
            cardgames._LAST_CLEANUP = 0.0
            cardgames._now = lambda: 100.0
            cardgames._cleanup_finished()
            cardgames._cleanup_finished()
            self.assertEqual(1, len(calls))
            self.assertIn("DELETE FROM cardgame_sessions", calls[0][0])
            self.assertNotIn("cardgame_events", calls[0][0])

            cardgames._now = lambda: 131.0
            cardgames._cleanup_finished()
            self.assertEqual(2, len(calls))
        finally:
            cardgames._db = old_db
            cardgames._now = old_now
            cardgames._LAST_CLEANUP = old_last

    def test_poll_events_marks_missing_or_finished_session_gone(self):
        class FakeDb:
            def _execute(self, _sql, _params, fetch=False):
                return []

        old_db = cardgames._db
        try:
            cardgames._db = lambda: FakeDb()
            alive, events = cardgames.poll_events("gone", 0)
        finally:
            cardgames._db = old_db

        self.assertFalse(alive)
        self.assertEqual([], events)


if __name__ == "__main__":
    unittest.main()
