# bigtree/inc/jsonutil.py

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert possibly-non-JSON-safe objects into JSON-safe types.

    Aiohttp's web.json_response uses json.dumps without a default handler. Some
    of our endpoints return rows containing datetime objects. This helper keeps
    those endpoints robust by converting datetime/date values to ISO8601 strings
    recursively.
    """

    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            # JSON keys must be strings.
            out[str(k)] = to_jsonable(v)
        return out

    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]

    # Fallback: objects that provide isoformat.
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            pass

    return value
