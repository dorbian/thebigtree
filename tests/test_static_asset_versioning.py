from __future__ import annotations

import unittest

from bigtree.inc import webserver


class StaticAssetVersioningTests(unittest.TestCase):
    def test_admin_templates_use_current_build_identity(self):
        previous = webserver._ASSET_VERSION
        webserver._ASSET_VERSION = "test-build-a8131c0f"
        try:
            language = webserver.DynamicWebServer.render_template("language.html", {})
            overlay = webserver.DynamicWebServer.render_template(
                "overlay.html",
                {"ADMIN_BACKGROUND": "/static/images/admin_background.webp?v=legacy"},
            )
        finally:
            webserver._ASSET_VERSION = previous

        self.assertIn(
            "/static/language/language.js?v=test-build-a8131c0f",
            language,
        )
        self.assertIn(
            "/static/language/language.css?v=test-build-a8131c0f",
            language,
        )
        self.assertIn(
            "/static/overlay/overlay.js?v=test-build-a8131c0f",
            overlay,
        )
        self.assertIn(
            "/static/overlay/overlay.css?v=test-build-a8131c0f",
            overlay,
        )
        self.assertIn(
            "/static/images/admin_background.webp?v=test-build-a8131c0f",
            overlay,
        )
        self.assertNotIn("language.js?v=20260913b", language)
        self.assertNotIn("overlay.js?v=20260913a", overlay)


if __name__ == "__main__":
    unittest.main()
