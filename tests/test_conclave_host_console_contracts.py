from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "bigtree" / "web" / "templates" / "overlay.html"
SCRIPT = ROOT / "bigtree" / "web" / "static" / "overlay" / "overlay.js"
WEBMOD = ROOT / "bigtree" / "webmods" / "conclave.py"


class ConclaveHostConsoleContracts(unittest.TestCase):
    def test_verdant_settings_remain_inside_elfministration(self):
        overlay = OVERLAY.read_text("utf-8")
        script = SCRIPT.read_text("utf-8")
        self.assertIn('id="menuVerdantSettings"', overlay)
        self.assertIn('id="dashboardVerdantSettings"', overlay)
        self.assertNotIn('href="/admin/verdant" target="_blank"', overlay)
        self.assertIn('verdantSettings: "Verdant settings"', script)
        self.assertIn('iframe.src = "/admin/verdant"', script)

    def test_active_conclave_selection_is_persistent_and_immediate(self):
        script = SCRIPT.read_text("utf-8")
        self.assertIn('const CONCLAVE_SELECTED_KEY = "bt_conclave_selected"', script)
        self.assertIn("if (cached) renderConclaveDetail(cached)", script)
        self.assertIn("storage.setItem(CONCLAVE_SELECTED_KEY", script)
        self.assertIn('button.setAttribute("aria-pressed"', script)

    def test_fake_game_autoplay_is_operator_controlled(self):
        overlay = OVERLAY.read_text("utf-8")
        script = SCRIPT.read_text("utf-8")
        webmod = WEBMOD.read_text("utf-8")
        self.assertIn('id="conclaveTestRun"', overlay)
        self.assertIn('id="conclaveTestStop"', overlay)
        self.assertIn("async function conclaveRunFakeGame()", script)
        self.assertIn("/test-step", script)
        self.assertIn('"/admin/conclave/{game_id}/test-step"', webmod)
        self.assertIn("_sync_discord_gameplay", webmod)


if __name__ == "__main__":
    unittest.main()
