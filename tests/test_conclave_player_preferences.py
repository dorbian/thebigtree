import importlib.util
from pathlib import Path
import random
import unittest

ENGINE_PATH = Path(__file__).parents[1] / "bigtree" / "games" / "conclave" / "engine.py"
SPEC = importlib.util.spec_from_file_location("bigtree_conclave_preferences_engine", ENGINE_PATH)
assert SPEC and SPEC.loader
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)

class ConclavePlayerPreferenceTests(unittest.TestCase):
    def lobby(self):
        state = engine.new_state("preferences-test", title="Preferences", guild_id=1, channel_id=2, host_user_id=99, dedicated_channel=True)
        for idx in range(1, 6):
            engine.add_player(state, idx, f"Elf {idx}")
        return state

    def test_optional_dm_delivery_follows_player_choice(self):
        state = self.lobby()
        state.setdefault("server_policy", {})["dm_delivery"] = "optional"
        self.assertFalse(engine.wants_dm_delivery(state, 1))
        engine.set_dm_preference(state, 1, True)
        self.assertTrue(engine.wants_dm_delivery(state, 1))
        state["server_policy"]["dm_delivery"] = "off"
        self.assertFalse(engine.wants_dm_delivery(state, 1))
        state["server_policy"]["dm_delivery"] = "on"
        self.assertTrue(engine.wants_dm_delivery(state, 1))

    def test_generated_name_changes_are_limited_and_lock_after_speech(self):
        state = self.lobby()
        state["identity"] = {"aliases_enabled": True, "mode": "immersive", "choice": "generated"}
        engine.ensure_forest_name(state, 1, rng=random.Random(1))
        for seed in (2, 3, 4):
            engine.reroll_forest_name(state, 1, rng=random.Random(seed))
        with self.assertRaises(engine.GameError) as exhausted:
            engine.reroll_forest_name(state, 1, rng=random.Random(5))
        self.assertEqual("forest_name_rerolls_exhausted", exhausted.exception.code)

        other = self.lobby()
        other["identity"] = {"aliases_enabled": True, "mode": "immersive", "choice": "both"}
        engine.ensure_forest_name(other, 1, rng=random.Random(1))
        engine.mark_forest_name_spoken(other, 1)
        with self.assertRaises(engine.GameError) as locked:
            engine.reroll_forest_name(other, 1, rng=random.Random(2))
        self.assertEqual("forest_name_locked", locked.exception.code)

    def test_custom_only_conclave_requires_names_before_start(self):
        state = self.lobby()
        state["identity"] = {"aliases_enabled": True, "mode": "immersive", "choice": "custom"}
        with self.assertRaises(engine.GameError) as missing:
            engine.start_game(state, rng=random.Random(7))
        self.assertEqual("forest_name_required", missing.exception.code)
        for idx in range(1, 6):
            engine.set_forest_name(state, idx, f"Leaf {idx}")
        engine.start_game(state, rng=random.Random(7))
        self.assertEqual(engine.PHASE_NIGHT, state["phase"])

if __name__ == "__main__":
    unittest.main()
