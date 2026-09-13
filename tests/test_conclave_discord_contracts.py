from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "bigtree" / "cmds" / "conclave.py"
API = ROOT / "bigtree" / "webmods" / "conclave.py"
ENGINE = ROOT / "bigtree" / "games" / "conclave" / "engine.py"
IDENTITY = ROOT / "bigtree" / "games" / "conclave" / "discord_identity.py"
AUTH = ROOT / "bigtree" / "inc" / "auth.py"
OVERLAY = ROOT / "bigtree" / "web" / "static" / "overlay" / "overlay.js"
HTML = ROOT / "bigtree" / "web" / "templates" / "overlay.html"
SPEC = ROOT / "bigtree" / "inc" / "spec.ini"
ACCESS = ROOT / "bigtree" / "inc" / "access_control.py"


class ConclaveDiscordContractTests(unittest.TestCase):
    def test_real_players_use_private_living_and_lost_spaces(self):
        source = CMD.read_text("utf-8")
        engine = ENGINE.read_text("utf-8")
        self.assertIn("discord.ChannelType.private_thread", source)
        self.assertIn("Living Circle", source)
        self.assertIn("Lost in the Forest", source)
        self.assertIn("thread.add_user(member)", source)
        self.assertIn("thread.remove_user(member)", source)
        self.assertIn('"living_thread_id": None', engine)
        self.assertIn('"lost_thread_id": None', engine)

    def test_lost_priest_access_is_explicitly_configured(self):
        source = CMD.read_text("utf-8")
        spec = SPEC.read_text("utf-8")
        access = ACCESS.read_text("utf-8")
        self.assertIn('game.conclave.lost_witness', access)
        self.assertIn('conclave_lost_priest', access)
        self.assertIn('conclave_lost_priest_role_ids', source)
        self.assertIn('conclave_lost_priest_role_ids=string_list(default=list())', spec)
        self.assertNotIn('_configured_role_ids("priest_role_ids")', source)

    def test_discord_guide_is_ephemeral_and_pageable(self):
        source = CMD.read_text("utf-8")
        self.assertIn('custom_id="conclave:guide"', source)
        self.assertIn('class _GuideSelect', source)
        self.assertIn('ephemeral=True', source)
        self.assertIn('Lost in the Forest', source)

    def test_elfministration_can_join_authenticated_discord_self(self):
        api = API.read_text("utf-8")
        auth = AUTH.read_text("utf-8")
        html = HTML.read_text("utf-8")
        js = OVERLAY.read_text("utf-8")
        self.assertIn('/admin/conclave/{game_id}/join-self', api)
        self.assertIn('request["bt_auth"]', auth)
        self.assertIn('id="conclaveJoinSelf"', html)
        self.assertIn('conclaveJoinSelf()', js)

    def test_forest_identity_is_native_player_experience(self):
        source = CMD.read_text("utf-8")
        engine = ENGINE.read_text("utf-8")
        self.assertIn('class _ForestNameModal', source)
        self.assertIn('custom_id="conclave:name"', source)
        self.assertIn('custom_id="conclave:speak"', source)
        self.assertIn('engine.generate_forest_name', source)
        self.assertIn('engine.game_player_name', source)
        self.assertIn('"forest_name": p.get("forest_name")', engine)

    def test_immersive_relay_hides_discord_mentions_and_avatar(self):
        source = CMD.read_text("utf-8")
        relay = IDENTITY.read_text("utf-8")
        self.assertIn('async def on_message', source)
        self.assertIn('message.webhook_id is not None', source)
        self.assertIn('discord_identity.relay_message', source)
        self.assertIn('discord.AllowedMentions.none()', relay)
        self.assertIn('@someone outside the Conclave', relay)
        self.assertNotIn('avatar_url=', relay)

    def test_sealed_mode_uses_speak_modal_and_pinned_guidance(self):
        source = CMD.read_text("utf-8")
        self.assertIn('class _SpeakModal', source)
        self.assertIn('if mode == "sealed"', source)
        self.assertIn('await message.delete()', source)
        self.assertIn('await intro.pin(', source)
        self.assertIn('brief original-message relay window', source)

    def test_forced_dm_delivery_sends_identity_and_role_without_being_required(self):
        source = CMD.read_text("utf-8")
        self.assertIn('maybe_send_identity_dm', source)
        self.assertIn('deliver_role_dms', source)
        self.assertIn('!= "on"', source)
        self.assertIn('except (discord.Forbidden, discord.HTTPException)', source)


if __name__ == "__main__":
    unittest.main()
