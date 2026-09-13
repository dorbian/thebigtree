import importlib.util
from pathlib import Path
import random
import unittest

# Load the pure engine without importing bigtree/__init__.py so these rules can
# be tested even on a development machine that does not have discord.py.
_ENGINE_PATH = Path(__file__).parents[1] / "bigtree" / "games" / "conclave" / "engine.py"
_SPEC = importlib.util.spec_from_file_location("bigtree_conclave_engine", _ENGINE_PATH)
assert _SPEC and _SPEC.loader
engine = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(engine)


class ConclaveEngineTests(unittest.TestCase):
    def make_lobby(self, count=6):
        state = engine.new_state(
            "conclave-test",
            title="Test Conclave",
            guild_id=1,
            channel_id=2,
            host_user_id=99,
            dedicated_channel=True,
        )
        for idx in range(1, count + 1):
            engine.add_player(state, idx, f"Elf {idx}")
        return state

    def test_start_requires_minimum_players(self):
        state = self.make_lobby(4)
        with self.assertRaises(engine.GameError):
            engine.start_game(state, rng=random.Random(1))

    def test_start_assigns_secret_roles_and_night(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(7))
        self.assertEqual(engine.PHASE_NIGHT, state["phase"])
        self.assertEqual(1, state["night"])
        roles = [p["role"] for p in state["players"].values()]
        self.assertIn("thornblade", roles)
        self.assertIn("starseer", roles)
        self.assertIn("chirurgeon", roles)
        public = engine.public_state(state)
        self.assertTrue(all("role" not in p for p in public["players"]))

    def test_thornbound_cannot_attack_ally(self):
        state = self.make_lobby(8)
        engine.start_game(state, rng=random.Random(3))
        thorns = [p for p in state["players"].values() if p["faction"] == engine.FACTION_THORNBOUND]
        self.assertGreaterEqual(len(thorns), 2)
        actor, ally = thorns[:2]
        targets = engine.valid_night_targets(state, actor["user_id"])
        self.assertNotIn(ally["user_id"], {p["user_id"] for p in targets})
        with self.assertRaises(engine.GameError):
            engine.submit_night_action(state, actor["user_id"], ally["user_id"])

    def test_protection_prevents_faction_kill(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(11))
        thorn = next(p for p in state["players"].values() if p["role"] == "thornblade")
        doctor = next(p for p in state["players"].values() if p["role"] == "chirurgeon")
        target = next(
            p for p in state["players"].values()
            if p["faction"] == engine.FACTION_CONCORD and p["user_id"] != doctor["user_id"]
        )
        engine.submit_night_action(state, thorn["user_id"], target["user_id"])
        engine.submit_night_action(state, doctor["user_id"], target["user_id"])
        engine.advance_phase(state)
        self.assertTrue(engine.player(state, target["user_id"])["alive"])
        self.assertEqual(engine.PHASE_DAY, state["phase"])
        self.assertTrue(any("ward" in text.lower() for text in state["public_events"]))

    def test_starseer_result_is_private(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(17))
        seer = next(p for p in state["players"].values() if p["role"] == "starseer")
        thorn = next(p for p in state["players"].values() if p["faction"] == engine.FACTION_THORNBOUND)
        engine.submit_night_action(state, seer["user_id"], thorn["user_id"])
        engine.advance_phase(state)
        private = engine.private_player_state(state, seer["user_id"])
        self.assertTrue(any("Thornbound" in note["text"] for note in private["notes"]))
        self.assertFalse(any("Thornbound aura" in text for text in state["public_events"]))


    def test_larger_games_add_information_and_disruption_roles(self):
        state = self.make_lobby(9)
        engine.start_game(state, rng=random.Random(37))
        roles = {p["role"] for p in state["players"].values()}
        self.assertIn("thornweaver", roles)
        self.assertIn("wayfinder", roles)
        self.assertIn("boughwatcher", roles)

    def test_thornweaver_can_block_a_protection(self):
        state = self.make_lobby(8)
        engine.start_game(state, rng=random.Random(41))
        blade = next(p for p in state["players"].values() if p["role"] == "thornblade")
        weaver = next(p for p in state["players"].values() if p["role"] == "thornweaver")
        doctor = next(p for p in state["players"].values() if p["role"] == "chirurgeon")
        target = next(
            p for p in state["players"].values()
            if p["faction"] == engine.FACTION_CONCORD and p["user_id"] != doctor["user_id"]
        )
        engine.submit_night_action(state, blade["user_id"], target["user_id"])
        engine.submit_night_action(state, doctor["user_id"], target["user_id"])
        engine.submit_night_action(state, weaver["user_id"], doctor["user_id"])
        engine.advance_phase(state)
        self.assertFalse(engine.player(state, target["user_id"])["alive"])
        private = engine.private_player_state(state, doctor["user_id"])
        self.assertTrue(any("tangled in thorns" in note["text"] for note in private["notes"]))

    def test_wayfinder_and_boughwatcher_observe_visits_privately(self):
        state = self.make_lobby(9)
        engine.start_game(state, rng=random.Random(43))
        blade = next(p for p in state["players"].values() if p["role"] == "thornblade")
        tracker = next(p for p in state["players"].values() if p["role"] == "wayfinder")
        watcher = next(p for p in state["players"].values() if p["role"] == "boughwatcher")
        target = next(
            p for p in state["players"].values()
            if p["faction"] == engine.FACTION_CONCORD
            and p["user_id"] not in {tracker["user_id"], watcher["user_id"]}
        )
        engine.submit_night_action(state, blade["user_id"], target["user_id"])
        engine.submit_night_action(state, tracker["user_id"], blade["user_id"])
        engine.submit_night_action(state, watcher["user_id"], target["user_id"])
        engine.advance_phase(state)
        tracker_notes = engine.private_player_state(state, tracker["user_id"])["notes"]
        watcher_notes = engine.private_player_state(state, watcher["user_id"])["notes"]
        self.assertTrue(any(target["display_name"] in note["text"] for note in tracker_notes))
        self.assertTrue(any(blade["display_name"] in note["text"] for note in watcher_notes))

    def test_boughwatcher_tolerates_other_players_passing(self):
        state = self.make_lobby(9)
        engine.start_game(state, rng=random.Random(44))
        watcher = next(p for p in state["players"].values() if p["role"] == "boughwatcher")
        passer = next(
            p for p in state["players"].values()
            if p["user_id"] != watcher["user_id"]
            and engine.role_definition(p["role"]).get("action")
        )
        target = next(
            p for p in state["players"].values()
            if p["alive"] and p["user_id"] not in {watcher["user_id"], passer["user_id"]}
        )

        engine.submit_night_pass(state, passer["user_id"])
        engine.submit_night_action(state, watcher["user_id"], target["user_id"])

        # The pass is a recorded choice but not a visit, so night resolution
        # must complete and the watcher should simply observe nobody.
        engine.advance_phase(state)
        notes = engine.private_player_state(state, watcher["user_id"])["notes"]
        self.assertTrue(any("no one" in note["text"] for note in notes))

    def test_intentional_night_pass_counts_as_ready(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(47))
        actor = next(p for p in state["players"].values() if engine.role_definition(p["role"]).get("action"))
        before = engine.night_readiness(state)
        engine.submit_night_pass(state, actor["user_id"])
        after = engine.night_readiness(state)
        self.assertEqual(before[0] + 1, after[0])
        self.assertIsNone(state["night_actions"][str(actor["user_id"])])

    def test_nomination_pass_counts_as_ready_without_creating_trial(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(49))
        engine.advance_phase(state)
        engine.advance_phase(state)
        living = engine.living_players(state)
        for voter in living:
            engine.submit_nomination_pass(state, voter["user_id"])
        self.assertEqual((len(living), len(living)), engine.nomination_readiness(state))
        self.assertEqual(engine.PHASE_NOMINATION, state["phase"])
        self.assertIsNone(state["on_trial"])

    def test_last_will_is_private_until_death_then_revealed(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(53))
        victim = next(p for p in state["players"].values() if p["faction"] == engine.FACTION_CONCORD)
        engine.set_last_will(state, victim["user_id"], "Trust the lantern keeper.")
        public = engine.public_state(state)
        self.assertNotIn("Trust the lantern keeper", str(public))
        event = engine._kill(state, victim, "beneath the old boughs")
        self.assertIn("Trust the lantern keeper", event)
        self.assertFalse(victim["alive"])

    def test_majority_nomination_moves_to_trial(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(19))
        engine.advance_phase(state)  # night -> day
        engine.advance_phase(state)  # day -> nominations
        living = engine.living_players(state)
        target = living[-1]
        voters = [p for p in living if p["user_id"] != target["user_id"]]
        threshold = len(living) // 2 + 1
        for voter in voters[:threshold]:
            engine.submit_nomination(state, voter["user_id"], target["user_id"])
        self.assertEqual(engine.PHASE_TRIAL, state["phase"])
        self.assertEqual(target["user_id"], state["on_trial"])

    def test_guilty_judgement_executes_accused(self):
        state = self.make_lobby(6)
        engine.start_game(state, rng=random.Random(23))
        engine.advance_phase(state)
        engine.advance_phase(state)
        living = engine.living_players(state)
        target = living[-1]
        voters = [p for p in living if p["user_id"] != target["user_id"]]
        threshold = len(living) // 2 + 1
        for voter in voters[:threshold]:
            engine.submit_nomination(state, voter["user_id"], target["user_id"])
        engine.advance_phase(state)  # trial -> judgement
        for voter in voters:
            engine.submit_judgement(state, voter["user_id"], "guilty")
        engine.advance_phase(state)
        self.assertFalse(engine.player(state, target["user_id"])["alive"])
        self.assertIn(state["phase"], {engine.PHASE_NIGHT, engine.PHASE_ENDED})


    def test_synthetic_players_fill_lobby_without_creating_discord_identities(self):
        state = self.make_lobby(1)
        engine.add_test_players(state, target_total=engine.MIN_PLAYERS)
        self.assertEqual(engine.MIN_PLAYERS, len(state["players"]))
        synthetic = engine.test_players(state)
        self.assertEqual(engine.MIN_PLAYERS - 1, len(synthetic))
        self.assertTrue(state["test_mode"])
        self.assertTrue(all(int(p["user_id"]) < 0 for p in synthetic))
        public = engine.public_state(state)
        self.assertEqual(len(synthetic), public["test_player_count"])
        self.assertTrue(any(p.get("synthetic") for p in public["players"]))

    def test_synthetic_players_can_drive_private_phases_for_host_testing(self):
        state = engine.new_state(
            "conclave-fakes",
            title="Synthetic Test",
            guild_id=1,
            channel_id=2,
            host_user_id=99,
            dedicated_channel=False,
        )
        engine.add_test_players(state, target_total=6)
        engine.start_game(state, rng=random.Random(61))
        engine.simulate_test_players(state)
        ready, required = engine.night_readiness(state)
        self.assertEqual(required, ready)
        engine.advance_phase(state)
        self.assertIn(state["phase"], {engine.PHASE_DAY, engine.PHASE_ENDED})
        if state["phase"] == engine.PHASE_DAY:
            engine.advance_phase(state)
            self.assertEqual(engine.PHASE_NOMINATION, state["phase"])
            engine.simulate_test_players(state)
            self.assertIn(state["phase"], {engine.PHASE_NOMINATION, engine.PHASE_TRIAL})
            self.assertGreaterEqual(int((state.get("test_last_simulation") or {}).get("acted") or 0), 1)

    def test_synthetic_players_are_removable_only_before_start(self):
        state = self.make_lobby(1)
        engine.add_test_players(state, 2)
        self.assertEqual(2, len(engine.test_players(state)))
        engine.remove_test_players(state)
        self.assertEqual(0, len(engine.test_players(state)))
        self.assertFalse(state["test_mode"])
        engine.add_test_players(state, target_total=5)
        engine.start_game(state, rng=random.Random(67))
        with self.assertRaises(engine.GameError):
            engine.remove_test_players(state)

    def test_end_game_is_terminal_and_public(self):
        state = self.make_lobby(5)
        engine.start_game(state, rng=random.Random(31))
        engine.end_game(state)
        self.assertEqual(engine.PHASE_ENDED, state["phase"])
        self.assertTrue(any("closed" in x.lower() for x in state["public_events"]))
        public = engine.public_state(state)
        self.assertTrue(all(p.get("role") for p in public["players"]))


if __name__ == "__main__":
    unittest.main()
