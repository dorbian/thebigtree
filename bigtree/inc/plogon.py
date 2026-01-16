from __future__ import annotations

import os
import threading
import time
from typing import Optional

import bigtree
import requests
from bigtree.inc.logging import logger

DEFAULT_PLOGON_URL = "https://raw.githubusercontent.com/dorbian/forest_repo/main/plogonmaster.json"
_LAST_FETCH = 0.0
_REFRESH_THREAD_STARTED = False


def _resolve_data_dir() -> str:
    base = None
    try:
        settings = getattr(bigtree, "settings", None)
        if settings:
            base = settings.get("BOT.DATA_DIR") or settings.get("BOT.DATA_DIR", "")
    except Exception:
        base = None
    if not base:
        base = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
    if not base:
        base = os.getenv("BIGTREE_WORKDIR")
    if not base:
        base = os.path.join(os.getcwd(), ".bigtree")
    os.makedirs(base, exist_ok=True)
    return base


def get_plogon_json_path() -> str:
    return os.path.join(_resolve_data_dir(), "plogon.json")


def get_with_leaf_path() -> str:
    return os.path.join(_resolve_data_dir(), "with.leaf")


def _get_plogon_url() -> str:
    settings = getattr(bigtree, "settings", None)
    if settings:
        candidate = settings.get("PLOGON.url", "").strip()
        if candidate:
            return candidate
    return DEFAULT_PLOGON_URL


def _get_refresh_interval() -> float:
    settings = getattr(bigtree, "settings", None)
    if settings:
        interval = settings.get("PLOGON.refresh_seconds", 3600, cast=float)
        try:
            return float(interval)
        except Exception:
            return 3600.0
    return 3600.0


def ensure_plogon_file(force: bool = False) -> Optional[str]:
    global _LAST_FETCH
    url = _get_plogon_url()
    if not url:
        return None
    refresh_interval = _get_refresh_interval()
    target_path = get_with_leaf_path()
    if not force and os.path.exists(target_path):
        modified = os.path.getmtime(target_path)
        if (time.time() - modified) < refresh_interval:
            return target_path
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("[plogon] download failed (%s): %s", url, exc)
        return target_path if os.path.exists(target_path) else None
    try:
        tmp_path = f"{target_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(resp.text)
        os.replace(tmp_path, target_path)
        _LAST_FETCH = time.time()
        logger.info("[plogon] refreshed %s", target_path)
    except Exception as exc:
        logger.warning("[plogon] failed to write %s: %s", target_path, exc)
    return target_path


def start_plogon_refresh_loop() -> None:
    global _REFRESH_THREAD_STARTED
    if _REFRESH_THREAD_STARTED:
        return

    def _loop():
        while True:
            ensure_plogon_file(force=True)
            time.sleep(_get_refresh_interval())

    thread = threading.Thread(target=_loop, daemon=True, name="plogon-refresh")
    thread.start()
    _REFRESH_THREAD_STARTED = True
