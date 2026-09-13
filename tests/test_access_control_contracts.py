from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "bigtree_access_control",
    ROOT / "bigtree" / "inc" / "access_control.py",
)
assert _SPEC and _SPEC.loader
access_control = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = access_control
_SPEC.loader.exec_module(access_control)


class AccessControlContractTests(unittest.TestCase):
    def test_legacy_scopes_and_namespace_wildcards_use_one_matcher(self):
        self.assertEqual("admin.web", access_control.normalize_capability("admin:web"))
        self.assertEqual("game.conclave.host", access_control.normalize_capability("conclave:admin"))
        self.assertTrue(access_control.capability_grants("admin:*", "admin:web"))
        self.assertTrue(access_control.capability_grants("game.*", "game.conclave.host"))
        self.assertFalse(access_control.capability_grants("event.host", "language.manage"))
        # Discord/BigTree superuser authority must not silently turn someone
        # into a Priest; the historical speaker gate remains explicit.
        self.assertFalse(access_control.capability_grants("*", "tree.address"))
        self.assertTrue(access_control.capability_grants("tree.address", "tree.address"))
        self.assertTrue(
            access_control.any_capability_granted(
                {"admin:web", "system.permissions"}, {"admin:*"}
            )
        )

    def test_tree_address_and_tree_commune_are_distinct_capabilities(self):
        priest = set(access_control.BUILTIN_ROLES["priest"]["capabilities"])
        operator = set(access_control.BUILTIN_ROLES["operator"]["capabilities"])
        self.assertIn("tree.address", priest)
        self.assertNotIn("tree.commune", priest)
        self.assertIn("tree.commune", operator)
        self.assertNotIn("tree.address", operator)

    def test_postgres_schema_is_identity_role_capability_based(self):
        db = (ROOT / "bigtree" / "inc" / "database.py").read_text("utf-8")
        for table in (
            "access_principals",
            "access_identities",
            "access_roles",
            "access_capabilities",
            "access_role_capabilities",
            "access_principal_roles",
            "access_external_role_bindings",
            "access_audit",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", db)
        self.assertIn('self._timed_startup_step("access catalog", self._ensure_access_catalog)', db)
        self.assertIn("access_control.seed_builtin_catalog(self)", db)
        self.assertIn("user_id BIGINT NOT NULL", db)
        self.assertIn('self._ensure_bigint_column(conn, "web_tokens", "user_id")', db)

    def test_discord_permissions_use_central_capability_evaluator(self):
        permissions = (ROOT / "bigtree" / "modules" / "permissions.py").read_text("utf-8")
        commune = (ROOT / "bigtree" / "cmds" / "commune.py").read_text("utf-8")
        commands = (ROOT / "bigtree" / "modules" / "commands.py").read_text("utf-8")
        self.assertIn("def requires_capability", permissions)
        self.assertIn("access_control.evaluate_discord_member", permissions)
        self.assertIn('@requires_capability("tree.commune")', commune)
        self.assertIn('evaluate_discord_member(member, "tree.address")', commands)
        self.assertNotIn("@is_bigtree_operator()\nasync def commune_slash", commune)


    def test_discord_web_tokens_are_linked_to_durable_principals(self):
        auth_cmd = (ROOT / "bigtree" / "cmds" / "auth.py").read_text("utf-8")
        self.assertIn("access_control.ensure_discord_principal(member)", auth_cmd)
        self.assertIn('token_meta["principal_id"]', auth_cmd)
        self.assertIn('"discord_id": int(member.id)', auth_cmd)

    def test_web_scope_matching_uses_same_capability_engine(self):
        auth = (ROOT / "bigtree" / "inc" / "auth.py").read_text("utf-8")
        tokens = (ROOT / "bigtree" / "inc" / "web_tokens.py").read_text("utf-8")
        links = (ROOT / "bigtree" / "webmods" / "auth_links.py").read_text("utf-8")
        self.assertIn("access_control.any_capability_granted(needed, granted)", auth)
        self.assertIn("access_control.any_capability_granted(needed_scopes, scopes)", tokens)
        self.assertIn("access_control.all_capabilities_granted(requested, caller_scopes)", links)

    def test_conclave_uses_precise_capability_and_resource_host_assignment(self):
        source = (ROOT / "bigtree" / "cmds" / "conclave.py").read_text("utf-8")
        api = (ROOT / "bigtree" / "webmods" / "conclave.py").read_text("utf-8")
        overlay = (ROOT / "bigtree" / "web" / "static" / "overlay" / "overlay.js").read_text("utf-8")
        self.assertIn('@requires_capability("game.conclave.host")', source)
        self.assertIn('"conclave_host"', source)
        self.assertIn('resource_type="game"', source)
        self.assertIn('channel: Optional[discord.TextChannel] = None', source)
        self.assertNotIn('emoji="↻"', source)
        self.assertIn('scopes=["game.conclave.host"]', api)
        self.assertIn('/admin/conclave/{game_id}/test-players', api)
        self.assertIn('/admin/conclave/{game_id}/test-act', api)
        self.assertIn('/admin/conclave/{game_id}/panel', api)
        self.assertIn('normalizeClientCapability', overlay)
        self.assertIn('hasScope("game.conclave.host")', overlay)

    def test_access_control_state_is_database_first_not_container_files(self):
        source = (ROOT / "bigtree" / "inc" / "access_control.py").read_text("utf-8")
        self.assertIn('"persistent_backend": "PostgreSQL"', source)
        self.assertNotIn("Path(", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("write_text", source)
        self.assertNotIn("json.dump", source)

    def test_access_inspector_api_is_read_only_in_foundation_pass(self):
        api = (ROOT / "bigtree" / "webmods" / "access.py").read_text("utf-8")
        self.assertIn('"/admin/access/catalog"', api)
        self.assertIn('"/admin/access/evaluate"', api)
        self.assertNotIn('@route("DELETE"', api)
        self.assertNotIn('@route("PUT"', api)
        self.assertNotIn('@route("PATCH"', api)
        self.assertNotIn("bind_external_role(", api)
        self.assertNotIn("assign_role(", api)


if __name__ == "__main__":
    unittest.main()
