from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

_PRECOMPRESS_PATH = ROOT / "tools" / "precompress_static.py"
_SPEC = importlib.util.spec_from_file_location("bigtree_precompress_static", _PRECOMPRESS_PATH)
assert _SPEC and _SPEC.loader
precompress_static = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(precompress_static)


class RuntimeContractTests(unittest.TestCase):
    def test_container_uses_slim_runtime_stage(self):
        text = (ROOT / "Containerfile").read_text("utf-8")
        self.assertIn("FROM python:3.11-slim-bookworm AS builder", text)
        self.assertIn("FROM python:3.11-slim-bookworm AS runtime", text)
        runtime = text.split("FROM python:3.11-slim-bookworm AS runtime", 1)[1]
        self.assertNotIn("build-essential", runtime)
        self.assertNotIn("libpq-dev", runtime)
        self.assertIn("libwebp7", runtime)
        # The build may invoke the checked-in helper or keep the tiny gzip
        # implementation inline so tools/ can stay outside the image context.
        # Assert the behavior we need rather than one implementation detail.
        uses_helper = "python tools/precompress_static.py" in runtime
        uses_inline_gzip = all(
            marker in runtime
            for marker in (
                'Path("/opt/thebigtree/bigtree/web/static")',
                "gzip.compress",
                "mtime=0",
                'path.name + ".gz"',
            )
        )
        self.assertTrue(
            uses_helper or uses_inline_gzip,
            "runtime stage must reproducibly precompress cacheable static assets",
        )
        self.assertIn("urllib.request.urlopen", runtime)

    def test_static_precompression_is_reproducible_and_effective(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bundle.js"
            source.write_text(("const forest = 'verdant';\n" * 4000), "utf-8")

            count, before, after = precompress_static.precompress(root)
            sidecar = root / "bundle.js.gz"
            first = sidecar.read_bytes()

            self.assertEqual(1, count)
            self.assertGreater(before, after)
            self.assertTrue(sidecar.exists())
            self.assertLess(len(first), source.stat().st_size // 4)

            precompress_static.precompress(root)
            self.assertEqual(first, sidecar.read_bytes())

    def test_overlay_keeps_bulk_css_and_handlers_out_of_html(self):
        html = (ROOT / "bigtree" / "web" / "templates" / "overlay.html").read_text("utf-8")
        css = (ROOT / "bigtree" / "web" / "static" / "overlay" / "overlay.css").read_text("utf-8")
        js = (ROOT / "bigtree" / "web" / "static" / "overlay" / "overlay.js").read_text("utf-8")

        # Only the runtime background CSS variables need to stay inline.
        head_style = html.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn("--admin-login-bg-url", head_style)
        self.assertNotIn(".dashboard-kpis-row", head_style)
        self.assertIn(".dashboard-kpis-row", css)
        self.assertNotIn('document.addEventListener("DOMContentLoaded"', html)
        self.assertIn('on("updatePlogonmasterBtn", "click"', js)


if __name__ == "__main__":
    unittest.main()
