#!/usr/bin/env python3
"""
Pegas → BigTree HMAC signing helper.
Used by Pegas (me) to authenticate with the bigtree bot API.

Usage:
  from bigtree_pegas_client import pegas_get, pegas_post, pegas_delete
  
  resp = pegas_get("/discord/channels")
  resp = pegas_post("/admin/gpose/start", {"theme": "Sunset", "duration_days": 7})
"""

import hashlib
import hmac
import os
import time
import json
import urllib.request
import urllib.error

SECRET_PATH = os.path.expanduser("~/.openclaw/credentials/bigtree_pegas_secret")
BASE_URL = os.getenv("BIGTREE_BASE_URL", "http://192.168.0.132:8443")
TIMESTAMP_TTL = 300  # 5 minutes


def _load_secret() -> str:
    with open(SECRET_PATH) as f:
        return f.read().strip()


def _sign(timestamp: str, method: str, path: str, body: str) -> str:
    secret = _load_secret()
    payload = f"{timestamp}{method.upper()}{path}{body}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _headers() -> dict:
    timestamp = str(int(time.time()))
    # body="" for GET/DELETE (no body)
    signature = _sign(timestamp, "GET", "/admin/pegas/status", "")
    # We need method+path per call — use a closure approach instead
    return {
        "X-Pegas-Identity": "pegas",
        "X-Pegas-Timestamp": timestamp,
    }


def _do(method: str, path: str, body: str = "") -> dict:
    timestamp = str(int(time.time()))
    # Sign only the path portion (no query string) — server uses request.path
    path_only = path.split("?")[0]
    signature = _sign(timestamp, method, path_only, body)
    headers = {
        "X-Pegas-Identity": "pegas",
        "X-Pegas-Timestamp": timestamp,
        "X-Pegas-Signature": signature,
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}{path}"
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def pegas_get(path: str) -> dict:
    return _do("GET", path)


def pegas_post(path: str, payload: dict) -> dict:
    body = json.dumps(payload)
    return _do("POST", path, body)


def pegas_delete(path: str) -> dict:
    return _do("DELETE", path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: bigtree_pegas_client.py <GET|POST|DELETE> <path> [body_json]")
        sys.exit(1)
    method = sys.argv[1].upper()
    path = sys.argv[2]
    body = sys.argv[3] if len(sys.argv) > 3 else ""
    result = _do(method, path, body)
    print(json.dumps(result, indent=2))