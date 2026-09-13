from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOGGING_PATH = ROOT / "bigtree" / "inc" / "logging.py"


class LoggingResilienceTests(unittest.TestCase):
    def test_rotating_handler_recovers_from_ebadf(self):
        previous_bigtree = sys.modules.get("bigtree")
        old_env = {key: os.environ.get(key) for key in ("BIGTREE_LOG_MODE", "BIGTREE_LOG_PATH")}
        try:
            fake = types.ModuleType("bigtree")
            fake.settings = None
            sys.modules["bigtree"] = fake
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "discord.log"
                os.environ["BIGTREE_LOG_MODE"] = "files"
                os.environ["BIGTREE_LOG_PATH"] = str(path)
                spec = importlib.util.spec_from_file_location("_bt_logging_resilience", LOGGING_PATH)
                module = importlib.util.module_from_spec(spec)
                assert spec and spec.loader
                spec.loader.exec_module(module)
                try:
                    module.logger.info("before invalidation")
                    handler = module.handler
                    self.assertIsNotNone(handler)
                    self.assertIsNotNone(handler.stream)
                    os.close(handler.stream.fileno())
                    module.logger.info("after invalidation")
                finally:
                    module.shutdown_logging()
                text = path.read_text(encoding="utf-8")
                self.assertIn("before invalidation", text)
                self.assertIn("after invalidation", text)
        finally:
            if previous_bigtree is None:
                sys.modules.pop("bigtree", None)
            else:
                sys.modules["bigtree"] = previous_bigtree
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
