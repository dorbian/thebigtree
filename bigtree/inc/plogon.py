from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Optional

import requests

import bigtree
from bigtree.inc.logging import logger

DEFAULT_PLOGON_URL = "https://raw.githubusercontent.com/dorbian/forest_repo/main/plogonmaster.json"
_LAST_FETCH = 0.0
_LAST_ETAG: Optional[str] = None
_LAST_MODIFIED: Optional[str] = None
_REFRESH_THREAD: Optional[threading.Thread] = None
_REFRESH_STOP = threading.Event()
_STATE_LOCK = threading.RLock()


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
            return max(60.0, float(interval))
        except Exception:
            return 3600.0
    return 3600.0


def _same_content(path: str, content: bytes) -> bool:
    try:
        with open(path, "rb") as fh:
            current = fh.read()
        return hashlib.sha256(current).digest() == hashlib.sha256(content).digest()
    except OSError:
        return False


def ensure_plogon_file(force: bool = False) -> Optional[str]:
    """Ensure the shared Forest metadata file exists and is reasonably fresh.

    Conditional HTTP avoids downloading/writing the same file every hour.  A
    content hash is retained as a fallback for servers that do not send ETags.
    """
    global _LAST_FETCH, _LAST_ETAG, _LAST_MODIFIED
    url = _get_plogon_url()
    if not url:
        return None
    refresh_interval = _get_refresh_interval()
    target_path = get_with_leaf_path()
    now = time.time()

    with _STATE_LOCK:
        if not force and os.path.exists(target_path):
            last_check = _LAST_FETCH or os.path.getmtime(target_path)
            if (now - last_check) < refresh_interval:
                return target_path
        headers = {}
        if _LAST_ETAG:
            headers["If-None-Match"] = _LAST_ETAG
        if _LAST_MODIFIED:
            headers["If-Modified-Since"] = _LAST_MODIFIED

    try:
        resp = requests.get(url, timeout=10, headers=headers)
        if resp.status_code == 304:
            with _STATE_LOCK:
                _LAST_FETCH = now
            logger.debug("[plogon] unchanged (304) %s", target_path)
            return target_path if os.path.exists(target_path) else None
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("[plogon] download failed (%s): %s", url, exc)
        return target_path if os.path.exists(target_path) else None

    content = resp.content
    with _STATE_LOCK:
        _LAST_ETAG = resp.headers.get("ETag") or _LAST_ETAG
        _LAST_MODIFIED = resp.headers.get("Last-Modified") or _LAST_MODIFIED
        _LAST_FETCH = now

    if os.path.exists(target_path) and _same_content(target_path, content):
        logger.debug("[plogon] unchanged (content) %s", target_path)
        return target_path

    tmp_path = f"{target_path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "wb") as fh:
            fh.write(content)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError as exc:
                # Some network-backed filesystems do not expose fsync. The
                # same-directory atomic replace is still safer than in-place
                # truncation, so do not fail a metadata refresh for that.
                logger.debug("[plogon] fsync unavailable for %s: %s", tmp_path, exc)
        os.replace(tmp_path, target_path)
        logger.info("[plogon] refreshed %s", target_path)
    except Exception as exc:
        logger.warning("[plogon] failed to write %s: %s", target_path, exc)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return target_path


def start_plogon_refresh_loop() -> None:
    global _REFRESH_THREAD
    if _REFRESH_THREAD and _REFRESH_THREAD.is_alive():
        return
    _REFRESH_STOP.clear()

    def _loop() -> None:
        while not _REFRESH_STOP.wait(_get_refresh_interval()):
            ensure_plogon_file(force=True)

    _REFRESH_THREAD = threading.Thread(
        target=_loop, daemon=True, name="plogon-refresh"
    )
    _REFRESH_THREAD.start()


def stop_plogon_refresh_loop(timeout: float = 2.0) -> None:
    global _REFRESH_THREAD
    _REFRESH_STOP.set()
    thread = _REFRESH_THREAD
    if thread and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=max(0.0, timeout))
    _REFRESH_THREAD = None
