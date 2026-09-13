from __future__ import annotations
from aiohttp import web
import mimetypes
from pathlib import Path
from bigtree.inc.webserver import frontend_route


def _static_root() -> Path:
    return Path(__file__).resolve().parents[1] / "web" / "static"


def _accepts_gzip(value: str) -> bool:
    """Return True when an Accept-Encoding header permits gzip.

    An explicit gzip quality wins over a wildcard, including ``gzip;q=0``.
    This follows HTTP content-negotiation semantics and avoids serving an
    encoding a client explicitly disabled.
    """
    explicit_gzip = None
    wildcard = None
    for raw in str(value or "").split(","):
        bits = [part.strip() for part in raw.split(";") if part.strip()]
        if not bits:
            continue
        encoding = bits[0].lower()
        quality = 1.0
        for part in bits[1:]:
            if part.lower().startswith("q="):
                try:
                    quality = max(0.0, min(1.0, float(part[2:])))
                except ValueError:
                    quality = 0.0
        if encoding == "gzip":
            explicit_gzip = quality
        elif encoding == "*":
            wildcard = quality
    if explicit_gzip is not None:
        return explicit_gzip > 0
    return bool(wildcard and wildcard > 0)


@frontend_route("GET", "/static/{path:.*}", allow_public=True)
async def static_file(req: web.Request):
    rel = req.match_info["path"]
    if not rel or rel.endswith("/"):
        return web.Response(status=404)
    base = _static_root()
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return web.Response(status=404)
    if not target.exists() or not target.is_file():
        return web.Response(status=404)
    served = target
    precompressed = target.with_name(target.name + ".gz")
    use_gzip = _accepts_gzip(req.headers.get("Accept-Encoding", "")) and precompressed.is_file()
    if use_gzip:
        served = precompressed
    resp = web.FileResponse(served)
    if use_gzip:
        content_type, _encoding = mimetypes.guess_type(str(target))
        if content_type:
            # FileResponse would otherwise identify the sidecar as a generic
            # .gz download instead of the original JavaScript/CSS resource.
            resp.headers["Content-Type"] = content_type
        resp.headers["Content-Encoding"] = "gzip"
    if precompressed.is_file():
        # Both representations must participate in the same cache key.
        resp.headers["Vary"] = "Accept-Encoding"
    # Versioned assets are safe to retain for a year. Unversioned assets keep a
    # shorter lifetime so a deploy can still replace them without stale clients.
    if req.query.get("v"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return resp
