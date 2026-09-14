from __future__ import annotations
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLAYER_FILES = (
    ROOT / "bigtree" / "cmds" / "conclave.py",
    ROOT / "bigtree" / "games" / "conclave" / "engine.py",
)
USE_WORD_EXEMPTIONS: set[str] = set()

def strings_without_docstrings(path: Path):
    tree = ast.parse(path.read_text("utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.value

class ConclaveCopyStyleTests(unittest.TestCase):
    def test_standalone_use_word_requires_explicit_exemption(self):
        offenders = []
        for path in PLAYER_FILES:
            for text in strings_without_docstrings(path):
                if re.search(r"\buse\b", text, flags=re.IGNORECASE) and text not in USE_WORD_EXEMPTIONS:
                    offenders.append((path.name, text))
        self.assertEqual([], offenders)

    def test_guide_begins_with_game_information(self):
        source = (ROOT / "bigtree" / "cmds" / "conclave.py").read_text("utf-8")
        self.assertIn("The Concord hunts for the Thornbound hidden among the gathering", source)
        self.assertNotIn("Use this guide whenever", source)
        self.assertNotIn("Use the selector below", source)

if __name__ == "__main__":
    unittest.main()
