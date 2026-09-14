from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ROOT / "bigtree" / "webmods" / "legal.py"
TERMS = ROOT / "bigtree" / "web" / "templates" / "legal_terms.html"
PRIVACY = ROOT / "bigtree" / "web" / "templates" / "legal_privacy.html"
SPEC = ROOT / "bigtree" / "inc" / "spec.ini"

class LegalPageContractTests(unittest.TestCase):
    def test_discord_legal_pages_are_public_and_stable(self):
        source = LEGAL.read_text("utf-8")
        for route in ("/terms", "/terms-of-service", "/privacy", "/privacy-policy"):
            self.assertIn(f'@route("GET", "{route}", allow_public=True)', source)

    def test_operator_contact_is_deployment_configurable(self):
        spec = SPEC.read_text("utf-8")
        for key in ("legal_operator_name", "legal_contact", "legal_jurisdiction"):
            self.assertIn(f"{key}=string(default=)", spec)

    def test_terms_and_privacy_cover_discord_app_requirements(self):
        terms = TERMS.read_text("utf-8")
        privacy = PRIVACY.read_text("utf-8")
        self.assertIn("Fair play and acceptable conduct", terms)
        self.assertIn("Language and AI features", terms)
        for required in ("Discord identity and context", "immersive Forest-name relay", "Language Services", "OpenAI or MiniMax", "Retention", "does not sell personal data", "Your choices and rights"):
            self.assertIn(required, privacy)

if __name__ == "__main__":
    unittest.main()
