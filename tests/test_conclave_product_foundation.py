from pathlib import Path
import unittest

from bigtree.games.conclave import engine, server_config


ROOT = Path(__file__).resolve().parents[1]


class _FakeConfigDB:
    def __init__(self, config=None):
        self.config = dict(config or {})

    def get_system_config(self, key):
        self.last_read = key
        return dict(self.config)

    def update_system_config(self, key, value):
        self.last_write = key
        self.config = dict(value)


class ConclaveProductFoundationTests(unittest.TestCase):
    def state(self):
        return engine.new_state(
            "foundation-test",
            title="Foundation",
            guild_id=1,
            channel_id=2,
            host_user_id=3,
            dedicated_channel=False,
        )

    def test_game_state_has_identity_relay_and_room_registry(self):
        state = self.state()
        self.assertEqual({}, state["rooms"])
        self.assertTrue(state["identity"]["aliases_enabled"])
        self.assertEqual("immersive", state["identity"]["mode"])
        self.assertEqual("both", state["identity"]["choice"])
        self.assertIsNone(state["relay"]["webhook_id"])

    def test_forest_name_is_game_local_and_unique(self):
        state = self.state()
        engine.add_player(state, 10, "Discord One")
        engine.add_player(state, 11, "Discord Two")
        engine.set_forest_name(state, 10, "Ashleaf")
        self.assertEqual("Discord One", engine.player(state, 10)["display_name"])
        self.assertEqual("Ashleaf", engine.public_player_name(engine.player(state, 10)))
        with self.assertRaises(engine.GameError) as ctx:
            engine.set_forest_name(state, 11, "ashleaf")
        self.assertEqual("forest_name_taken", ctx.exception.code)

    def test_room_registry_is_generic(self):
        state = self.state()
        engine.register_room(state, "living", 100, purpose="Living Circle")
        engine.register_room(
            state,
            "sanctuary:10",
            101,
            purpose="High Priest Sanctuary",
            lifecycle="night",
        )
        self.assertEqual(100, state["rooms"]["living"]["channel_id"])
        self.assertEqual("night", state["rooms"]["sanctuary:10"]["lifecycle"])
        engine.unregister_room(state, "sanctuary:10")
        self.assertNotIn("sanctuary:10", state["rooms"])

    def test_server_config_normalizes_without_persisting_webhook_token(self):
        db = _FakeConfigDB({
            "aliases_enabled": "yes",
            "alias_mode": "sealed",
            "max_concurrent_games": "7",
            "webhook_token": "never-store-this",
        })
        config = server_config.get_config(db)
        self.assertTrue(config["aliases_enabled"])
        self.assertEqual("sealed", config["alias_mode"])
        self.assertEqual(7, config["max_concurrent_games"])
        self.assertNotIn("webhook_token", config)

        server_config.save_config({**config, "webhook_token": "still-no"}, db)
        self.assertNotIn("webhook_token", db.config)

    def test_server_policy_snapshots_into_game_without_secrets(self):
        state = self.state()
        server_config.apply_to_state(state, {
            "aliases_enabled": True,
            "alias_mode": "sealed",
            "alias_choice": "generated",
            "dm_delivery": "off",
            "auto_manage_webhook": False,
        })
        self.assertEqual("sealed", state["identity"]["mode"])
        self.assertEqual("generated", state["identity"]["choice"])
        self.assertEqual("off", state["server_policy"]["dm_delivery"])
        self.assertFalse(state["server_policy"]["auto_manage_webhook"])
        self.assertNotIn("webhook_token", state)

    def test_server_policy_snapshot_is_not_overwritten_during_recovery(self):
        state = self.state()
        server_config.apply_to_state(state, {
            "aliases_enabled": True,
            "alias_mode": "immersive",
            "alias_choice": "custom",
            "dm_delivery": "optional",
            "auto_manage_webhook": True,
        })
        server_config.apply_to_state(
            state,
            {
                "aliases_enabled": False,
                "alias_mode": "sealed",
                "alias_choice": "generated",
                "dm_delivery": "off",
                "auto_manage_webhook": False,
            },
            overwrite=False,
        )
        self.assertTrue(state["identity"]["aliases_enabled"])
        self.assertEqual("immersive", state["identity"]["mode"])
        self.assertEqual("custom", state["identity"]["choice"])
        self.assertEqual("optional", state["server_policy"]["dm_delivery"])
        self.assertTrue(state["server_policy"]["auto_manage_webhook"])

    def test_elfministration_routes_do_not_collide_with_game_id_route(self):
        webmod = (ROOT / "bigtree" / "webmods" / "conclave_settings.py").read_text("utf-8")
        template = (ROOT / "bigtree" / "web" / "templates" / "conclave_settings.html").read_text("utf-8")
        overlay = (ROOT / "bigtree" / "web" / "templates" / "overlay.html").read_text("utf-8")
        self.assertIn('"/admin/verdant"', webmod)
        self.assertIn('"/admin/verdant/status"', webmod)
        self.assertNotIn('"/admin/conclave/settings"', webmod)
        self.assertIn("/admin/verdant", template)
        self.assertIn("/admin/verdant", overlay)

    def test_store_enforces_server_enable_and_concurrency_policy(self):
        source = (ROOT / "bigtree" / "games" / "conclave" / "store.py").read_text("utf-8")
        self.assertIn("server_config.get_config", source)
        self.assertIn('"concurrent_limit"', source)
        self.assertIn("max_concurrent_games", source)
        self.assertIn("server_config.apply_to_state", source)

    def test_discord_foundation_owns_per_game_webhook_and_room_repair(self):
        source = (ROOT / "bigtree" / "cmds" / "conclave.py").read_text("utf-8")
        self.assertIn("ensure_game_webhook", source)
        self.assertIn("ensure_game_foundation", source)
        self.assertIn("inspect_game_health", source)
        self.assertIn("repair_game_foundation", source)
        self.assertIn("engine.register_room", source)
        self.assertIn("manage_webhooks=True", source)
        self.assertIn("manage_messages=True", source)

    def test_moderator_identity_resolution_is_admin_only_and_role_free(self):
        source = (ROOT / "bigtree" / "webmods" / "conclave_settings.py").read_text("utf-8")
        marker = '@route("GET", "/admin/verdant/games/{game_id}/identities", scopes=["admin:web"])'
        self.assertIn(marker, source)
        section = source.split(marker, 1)[1]
        self.assertIn('"discord_user_id"', section)
        self.assertIn('"forest_name"', section)
        self.assertNotIn('"role"', section)
        self.assertIn("moderator identity map viewed", source)

    def test_diagnostics_cover_required_discord_permissions(self):
        webmod = (ROOT / "bigtree" / "webmods" / "conclave_settings.py").read_text("utf-8")
        for permission in (
            "view_channel",
            "send_messages",
            "read_message_history",
            "manage_messages",
            "manage_webhooks",
            "create_private_threads",
            "manage_threads",
        ):
            self.assertIn(permission, webmod)
        self.assertIn("message_content", webmod)


if __name__ == "__main__":
    unittest.main()
