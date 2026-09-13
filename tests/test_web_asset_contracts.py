from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "bigtree" / "web" / "static"
TEMPLATES = ROOT / "bigtree" / "web" / "templates"


class WebAssetContractTests(unittest.TestCase):
    def test_builtin_backgrounds_use_compact_webp_variants(self):
        for stem in ("adminlogin", "admin_background", "walletimg", "pathbg"):
            png = STATIC / "images" / f"{stem}.png"
            webp = STATIC / "images" / f"{stem}.webp"
            self.assertTrue(png.exists(), stem)
            self.assertTrue(webp.exists(), stem)
            self.assertLess(webp.stat().st_size, png.stat().st_size // 4, stem)

    def test_overlay_prefers_thumbnail_and_preview_derivatives(self):
        js = (STATIC / "overlay" / "overlay.js").read_text("utf-8")
        self.assertIn("item.thumb_url || item.thumbnail_url || item.url", js)
        self.assertIn("currentMediaEdit.preview_url || currentMediaEdit.url", js)
        self.assertIn("requestIdleCallback", js)
        self.assertIn("mediaRenderGeneration", js)

    def test_overlay_has_channel_bound_conclave_host_panel(self):
        html = (TEMPLATES / "overlay.html").read_text("utf-8")
        self.assertIn('id="conclavePanel"', html)
        self.assertIn('id="conclaveOpenDiscord"', html)
        self.assertIn("Secret roles and private actions stay in Discord", html)

    def test_overlay_does_not_regress_to_large_builtin_png_backgrounds(self):
        html = (TEMPLATES / "overlay.html").read_text("utf-8")
        css = (STATIC / "overlay" / "overlay.css").read_text("utf-8")
        for value in ("adminlogin.png", "admin_background.png", "walletimg.png"):
            self.assertNotIn(value, html)
            self.assertNotIn(value, css)

    def test_overlay_template_ids_are_unique(self):
        html = (TEMPLATES / "overlay.html").read_text("utf-8")
        ids = re.findall(r'\bid="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
