from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEBSERVER = ROOT / "bigtree" / "inc" / "webserver.py"
LANGUAGE_TEMPLATE = ROOT / "bigtree" / "web" / "templates" / "language.html"
OVERLAY_TEMPLATE = ROOT / "bigtree" / "web" / "templates" / "overlay.html"


def _static_version_pattern(source: str) -> re.Pattern[str]:
    """Read the production regex without importing the BigTree runtime."""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_STATIC_VERSION_RE"
            for target in node.targets
        ):
            continue
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "re"
            and call.func.attr == "compile"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        ):
            return re.compile(call.args[0].value)
    raise AssertionError("_STATIC_VERSION_RE = re.compile(...) not found")


class StaticAssetVersioningTests(unittest.TestCase):
    def test_admin_templates_use_current_build_identity_without_runtime_dependencies(self):
        source = WEBSERVER.read_text("utf-8")
        pattern = _static_version_pattern(source)
        build = "test-build-eb9dfd3b"

        # Keep this validation runnable in the dependency-light CI gate. Importing
        # bigtree.inc.webserver executes bigtree/__init__.py, which requires the
        # Discord runtime package that is intentionally not installed in this job.
        self.assertIn("_STATIC_VERSION_RE.sub(", source)
        self.assertIn('f"{match.group(1)}?v={_ASSET_VERSION}"', source)

        language = LANGUAGE_TEMPLATE.read_text("utf-8")
        overlay = OVERLAY_TEMPLATE.read_text("utf-8").replace(
            "{ADMIN_BACKGROUND}",
            "/static/images/admin_background.webp?v=legacy",
        )
        language = pattern.sub(lambda match: f"{match.group(1)}?v={build}", language)
        overlay = pattern.sub(lambda match: f"{match.group(1)}?v={build}", overlay)

        self.assertIn(f"/static/language/language.js?v={build}", language)
        self.assertIn(f"/static/language/language.css?v={build}", language)
        self.assertIn(f"/static/overlay/overlay.js?v={build}", overlay)
        self.assertIn(f"/static/overlay/overlay.css?v={build}", overlay)
        self.assertIn(f"/static/images/admin_background.webp?v={build}", overlay)
        self.assertNotIn("language.js?v=20260913b", language)
        self.assertNotIn("overlay.js?v=20260913a", overlay)


if __name__ == "__main__":
    unittest.main()
