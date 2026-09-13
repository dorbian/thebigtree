from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupMigrationContractTests(unittest.TestCase):
    def setUp(self):
        self.database = (ROOT / "bigtree" / "inc" / "database.py").read_text("utf-8")

    def test_startup_import_completion_is_persisted_in_postgres(self):
        self.assertIn("CREATE TABLE IF NOT EXISTS startup_migrations", self.database)
        self.assertIn("def is_startup_migration_complete", self.database)
        self.assertIn("def mark_startup_migration", self.database)
        self.assertIn('"tarot_deck_seed_v1"', self.database)
        self.assertIn('"media_import_v1"', self.database)
        self.assertIn('"game_json_import_v1"', self.database)
        self.assertIn('"legacy_state_import_v1"', self.database)
        self.assertIn('"legacy_contest_import_v1"', self.database)

    def test_normal_restart_skips_completed_importers(self):
        init_start = self.database.index("    def initialize(self):")
        init_end = self.database.index("    # ---------------- connection helpers ----------------", init_start)
        initialize = self.database[init_start:init_end]

        self.assertIn("self._run_startup_import", initialize)
        self.assertNotIn("self._sync_tarot_decks()", initialize)
        self.assertNotIn("self._migrate_media_items()", initialize)
        self.assertNotIn("self._migrate_json_backups()", initialize)
        self.assertNotIn("self._migrate_legacy_state_files()", initialize)
        self.assertNotIn("self._migrate_legacy_contests()", initialize)

    def test_existing_installations_can_adopt_database_state_without_rescan(self):
        self.assertIn('adopt_if=lambda: self._count_rows("deck_files") > 0', self.database)
        self.assertIn('adopt_if=lambda: self._count_rows("media_items") > 0', self.database)
        self.assertIn("adopt_if=self._has_imported_games", self.database)
        self.assertIn('"adopted_existing": True', self.database)

    def test_maintenance_reconciliation_requires_explicit_opt_in(self):
        self.assertIn("BIGTREE_FORCE_STARTUP_IMPORTS", self.database)
        self.assertIn("BIGTREE_RECONCILE_MEDIA_ON_START", self.database)
        self.assertIn("BIGTREE_STARTUP_IMPORT_REPORT", self.database)

    def test_schema_bootstrap_uses_one_transaction_for_statement_batch(self):
        schema_start = self.database.index("    def _ensure_tables(self):")
        schema_end = self.database.index("    def _count_rows", schema_start)
        schema = self.database[schema_start:schema_end]
        self.assertIn("with self.transaction() as cur:", schema)
        self.assertIn("for stmt in statements:", schema)
        self.assertIn("cur.execute(stmt)", schema)
        self.assertNotIn("self._execute(stmt)", schema)

    def test_startup_logs_step_timings(self):
        self.assertIn("def _timed_startup_step", self.database)
        self.assertIn("initialization complete in %.1f ms", self.database)
        self.assertIn("startup import %s complete in %.1f ms", self.database)


if __name__ == "__main__":
    unittest.main()
