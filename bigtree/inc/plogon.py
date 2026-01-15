from __future__ import annotations

import os
from typing import Optional

import bigtree
import requests
from bigtree.inc.logging import logger

DEFAULT_PLOGON_URL = "https://raw.githubusercontent.com/dorbian/forest_repo/main/plogonmaster.json"


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


def ensure_plogon_file() -> None:
    url = _get_plogon_url()
    if not url:
        return
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("[plogon] download failed (%s): %s", url, exc)
        return
    json_path = get_plogon_json_path()
    leaf_path = get_with_leaf_path()
    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            fh.write(resp.text)
        os.replace(json_path, leaf_path)
        logger.info("[plogon] refreshed %s", leaf_path)
    except Exception as exc:
        logger.warning("[plogon] failed to write %s: %s", leaf_path, exc)
