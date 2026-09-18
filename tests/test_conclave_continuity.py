from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "bigtree" / "games" / "conclave" / "engine.py"
CMD = ROOT / "bigtree" / "cmds" / "conclave.py"
IDENTITY = ROOT / "bigtree" / "games" / "conclave" / "discord_identity.py"

SPEC = importlib.util.spec_from_file_location("bigtree_conclave_continuity_engine", ENGINE_PATH)
assert SPEC and SPEC.loader
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)


class ConclaveContinuityTests(unittest.TestCase):
    def state(self):
        return engine.new_state(
            "continuity",
            title="Continuity",
            guild_id=1,
            channel_id=2,
            host_user_id=99,
            dedicated_channel=True,
        )

    def test_relay_index_is_bounded_persistent_metadata_without_content(self):
        state = self.state()
        for index in range(engine.MAX_RELAY_HISTORY + 5):
            engine.record_relay_message(
                state,
                1000 + index,
                10 + index,
                "living",
                f"Leaf {index}",
            )
        self.assertEqual(engine.MAX_RELAY_HISTORY, len(state["relay_history"]))
        self.assertIsNone(engine.relay_message_record(state, 1000))
        newest = engine.relay_message_record(state, 1000 + engine.MAX_RELAY_HISTORY + 4)
        self.assertEqual("living", newest["room_key"])
        self.assertNotIn("content", newest)
        engine.forget_relay_message(state, newest["message_id"])
        self.assertIsNone(engine.relay_message_record(state, newest["message_id"]))

    def test_room_registration_keeps_guidance_id_for_same_thread_only(self):
        state = self.state()
        engine.register_room(state, "living", 50, purpose="Living Circle")
        state["rooms"]["living"]["guidance_message_id"] = 77
        engine.register_room(state, "living", 50, purpose="Living Circle")
        self.assertEqual(77, state["rooms"]["living"]["guidance_message_id"])
        engine.register_room(state, "living", 51, purpose="Living Circle")
        self.assertNotIn("guidance_message_id", state["rooms"]["living"])

    def test_discord_relay_supports_forest_replies_and_returns_message_ids(self):
        source = IDENTITY.read_text("utf-8")
        self.assertIn("reply_to: Optional[str] = None", source)
        self.assertIn("↪ **Replying to {name}**", source)
        self.assertIn("Optional[discord.WebhookMessage]", source)
        self.assertIn("return await webhook.send", source)
        self.assertIn("Sticker:", source)

    def test_discord_persists_relay_ownership_and_exposes_message_removal(self):
        source = CMD.read_text("utf-8")
        self.assertIn('name="Verdant: remove message"', source)
        self.assertIn("engine.record_relay_message", source)
        self.assertIn("engine.relay_message_record", source)
        self.assertIn("engine.forget_relay_message", source)
        self.assertIn("Only the elf who spoke those words or the host can remove them.", source)
        self.assertIn("reference_id", source)

    def test_existing_room_guidance_is_adopted_and_repaired(self):
        source = CMD.read_text("utf-8")
        self.assertIn("guidance_message_id", source)
        self.assertIn("await thread.pins()", source)
        self.assertIn("await guidance.edit(content=desired)", source)
        self.assertIn('self._ensure_room_guidance(state, "living", living)', source)
        self.assertIn('self._ensure_room_guidance(state, "lost", lost)', source)


if __name__ == "__main__":
    unittest.main()
