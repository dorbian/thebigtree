from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATIC_PATH = ROOT / "bigtree" / "webmods" / "static.py"


def _load_accepts_gzip():
    tree = ast.parse(STATIC_PATH.read_text("utf-8"), filename=str(STATIC_PATH))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_accepts_gzip")
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(STATIC_PATH), "exec"), namespace)
    return namespace["_accepts_gzip"]


class StaticNegotiationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accepts = staticmethod(_load_accepts_gzip())

    def test_explicit_gzip_denial_beats_wildcard(self):
        self.assertFalse(self.accepts("gzip;q=0, *;q=1"))

    def test_wildcard_allows_gzip_when_not_explicitly_named(self):
        self.assertTrue(self.accepts("br;q=1, *;q=.5"))

    def test_positive_gzip_quality_is_accepted(self):
        self.assertTrue(self.accepts("br, gzip;q=0.8"))

    def test_missing_header_does_not_force_compression(self):
        self.assertFalse(self.accepts(""))


if __name__ == "__main__":
    unittest.main()
