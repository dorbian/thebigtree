from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "bigtree" / "cmds" / "conclave.py"


class ConclaveGameFeelContractTests(unittest.TestCase):
    def test_public_panel_names_the_current_moment_and_accused(self):
        source = CMD.read_text("utf-8")
        self.assertIn("def _phase_moment_label", source)
        self.assertIn('name="Before the Conclave"', source)
        self.assertIn('engine.PHASE_NIGHT: "Night choices"', source)
        self.assertIn('engine.PHASE_JUDGEMENT: "Judgements cast"', source)

    def test_private_calling_always_explains_the_next_meaningful_step(self):
        source = CMD.read_text("utf-8")
        self.assertIn("def _private_next_step", source)
        self.assertIn('name="What happens now"', source)
        self.assertIn("You stand accused. Make your defence before judgement begins.", source)
        self.assertIn("Your judgement is sealed.", source)

    def test_phase_changes_are_announced_and_optionally_delivered_privately(self):
        source = CMD.read_text("utf-8")
        self.assertIn("def _phase_announcement", source)
        self.assertIn("async def announce_phase_transition", source)
        self.assertGreaterEqual(source.count("await self.cog.announce_phase_transition(state)"), 3)
        self.assertGreaterEqual(source.count("await self.cog.deliver_role_dms(state)"), 3)
        self.assertIn('state.get("phase") != before_phase', source)

    def test_new_game_copy_avoids_interface_explanations(self):
        source = CMD.read_text("utf-8")
        for phrase in ("phase transition", "state machine", "implementation", "debug"):
            self.assertNotIn(phrase, source.lower())


if __name__ == "__main__":
    unittest.main()
