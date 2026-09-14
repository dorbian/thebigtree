from __future__ import annotations

from html import escape
from aiohttp import web
import bigtree
from bigtree.inc.webserver import get_server, route

_EFFECTIVE_DATE = "14 September 2026"
_PROJECT_URL = "https://github.com/dorbian/thebigtree"


def _setting(name: str, default: str = "") -> str:
    settings = getattr(bigtree, "settings", None)
    if settings is not None:
        try:
            return str(settings.get(f"WEB.{name}", default) or default).strip()
        except Exception:
            pass
    config = getattr(getattr(bigtree, "config", None), "config", None) or {}
    return str((config.get("WEB", {}) or {}).get(name, default) or default).strip()


def _mapping() -> dict[str, str]:
    return {
        "OPERATOR": escape(_setting("legal_operator_name") or "TheBigTree deployment operator"),
        "CONTACT": escape(_setting("legal_contact") or "the support contact published with this Discord application"),
        "JURISDICTION": escape(_setting("legal_jurisdiction") or "the jurisdiction where the operator is established"),
        "EFFECTIVE_DATE": _EFFECTIVE_DATE,
        "PROJECT_URL": _PROJECT_URL,
    }


def _page(template: str, fallback_title: str) -> web.Response:
    server = get_server()
    html = server.render_template(template, _mapping()) if server else ""
    if not html:
        html = f"<!doctype html><html><body><h1>{escape(fallback_title)}</h1><p>Document unavailable.</p></body></html>"
    return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "public, max-age=3600"})


@route("GET", "/terms", allow_public=True)
@route("GET", "/terms-of-service", allow_public=True)
async def terms_of_service(_req: web.Request) -> web.Response:
    return _page("legal_terms.html", "TheBigTree Terms of Service")


@route("GET", "/privacy", allow_public=True)
@route("GET", "/privacy-policy", allow_public=True)
async def privacy_policy(_req: web.Request) -> web.Response:
    return _page("legal_privacy.html", "TheBigTree Privacy Policy")
