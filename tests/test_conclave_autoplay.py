from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "bigtree" / "games" / "conclave" / "engine.py"
SPEC = importlib.util.spec_from_file_location("bigtree_conclave_autoplay_engine", ENGINE_PATH)
assert SPEC and SPEC.loader
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


class ConclaveAutoplayTests(unittest.TestCase):
    def test_fake_only_game_can_run_to_completion(self):
        state = engine.new_state(
            "autoplay",
            title="Autoplay",
            guild_id=1,
            channel_id=2,
            host_user_id=99,
            dedicated_channel=False,
        )
        rng = random.Random(917)
        seen = {engine.PHASE_LOBBY}
        for _ in range(100):
            engine.advance_test_game(state, target_total=8, rng=rng)
            seen.add(state["phase"])
            if state["phase"] == engine.PHASE_ENDED:
                break
        self.assertEqual(engine.PHASE_ENDED, state["phase"])
        self.assertIn(state["winner"], {engine.FACTION_CONCORD, engine.FACTION_THORNBOUND})
        self.assertTrue(all(engine.is_test_player(p) for p in state["players"].values()))
        self.assertTrue(all(str(p.get("forest_name") or "").strip() for p in state["players"].values()))
        self.assertIn(engine.PHASE_NIGHT, seen)
        self.assertIn(engine.PHASE_DAY, seen)
        self.assertIn(engine.PHASE_NOMINATION, seen)
        self.assertIn(engine.PHASE_TRIAL, seen)
        self.assertIn(engine.PHASE_JUDGEMENT, seen)

    def test_autoplay_refuses_real_players(self):
        state = engine.new_state(
            "mixed",
            title="Mixed",
            guild_id=1,
            channel_id=2,
            host_user_id=99,
            dedicated_channel=False,
        )
        engine.add_player(state, 1, "Real Elf")
        with self.assertRaises(engine.GameError) as ctx:
            engine.advance_test_game(state, target_total=8, rng=random.Random(1))
        self.assertEqual("test_has_real_players", ctx.exception.code)


if __name__ == "__main__":
    unittest.main()
