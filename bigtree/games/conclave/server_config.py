"""Persistent server policy for Verdant Conclave.

This module is deliberately Discord-free so the engine/store, Discord cog and
Elfministration web surface can share one source of truth.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from bigtree.inc.database import get_database

CONFIG_KEY = "conclave"
WEBHOOK_NAME = "TheBigTree · Verdant"

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "parent_channel_id": None,
    "aliases_enabled": True,
    "alias_mode": "immersive",
    "alias_choice": "both",
    "dm_delivery": "optional",
    "max_concurrent_games": 4,
    "auto_manage_webhook": True,
    "webhook_id": None,
}


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def get_config(db=None) -> Dict[str, Any]:
    database = db or get_database()
    raw = database.get_system_config(CONFIG_KEY) or {}
    config = dict(DEFAULTS)
    if isinstance(raw, dict):
        config.update(raw)
    # A Discord webhook token is a credential. Verdant never persists one in
    # system configuration; the bot rediscovers webhooks through Discord.
    config.pop("webhook_token", None)
    config["enabled"] = as_bool(config.get("enabled"), True)
    config["aliases_enabled"] = as_bool(config.get("aliases_enabled"), True)
    config["auto_manage_webhook"] = as_bool(config.get("auto_manage_webhook"), True)
    config["max_concurrent_games"] = bounded_int(
        config.get("max_concurrent_games"), 4, 1, 20
    )
    mode = str(config.get("alias_mode") or "immersive").strip().lower()
    config["alias_mode"] = mode if mode in {"immersive", "sealed"} else "immersive"
    choice = str(config.get("alias_choice") or "both").strip().lower()
    config["alias_choice"] = choice if choice in {"generated", "custom", "both"} else "both"
    delivery = str(config.get("dm_delivery") or "optional").strip().lower()
    config["dm_delivery"] = delivery if delivery in {"off", "optional", "on"} else "optional"
    channel = config.get("parent_channel_id")
    try:
        config["parent_channel_id"] = int(channel) if channel else None
    except Exception:
        config["parent_channel_id"] = None
    try:
        config["webhook_id"] = int(config.get("webhook_id")) if config.get("webhook_id") else None
    except Exception:
        config["webhook_id"] = None
    return config


def save_config(config: Dict[str, Any], db=None) -> Dict[str, Any]:
    database = db or get_database()
    safe = dict(config or {})
    safe.pop("webhook_token", None)
    merged = dict(DEFAULTS)
    merged.update(safe)
    # Normalize through the same rules without writing a temporary row.
    merged["enabled"] = as_bool(merged.get("enabled"), True)
    merged["aliases_enabled"] = as_bool(merged.get("aliases_enabled"), True)
    merged["auto_manage_webhook"] = as_bool(merged.get("auto_manage_webhook"), True)
    merged["max_concurrent_games"] = bounded_int(
        merged.get("max_concurrent_games"), 4, 1, 20
    )
    mode = str(merged.get("alias_mode") or "immersive").strip().lower()
    if mode not in {"immersive", "sealed"}:
        mode = "immersive"
    merged["alias_mode"] = mode
    choice = str(merged.get("alias_choice") or "both").strip().lower()
    if choice not in {"generated", "custom", "both"}:
        choice = "both"
    merged["alias_choice"] = choice
    delivery = str(merged.get("dm_delivery") or "optional").strip().lower()
    if delivery not in {"off", "optional", "on"}:
        delivery = "optional"
    merged["dm_delivery"] = delivery
    database.update_system_config(CONFIG_KEY, merged)
    return merged


def apply_to_state(
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    *,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Snapshot server-level product policy into one game.

    New games use ``overwrite=True``. Recovery of legacy payloads uses
    ``overwrite=False`` so an operator changing server defaults never mutates
    the rules of an already-running game.
    """
    cfg = dict(config or get_config())
    identity = state.setdefault("identity", {})
    if not isinstance(identity, dict):
        identity = {}
        state["identity"] = identity
    if overwrite or "aliases_enabled" not in identity:
        identity["aliases_enabled"] = as_bool(cfg.get("aliases_enabled"), True)
    if overwrite or "mode" not in identity:
        identity["mode"] = str(cfg.get("alias_mode") or "immersive")
    if overwrite or "choice" not in identity:
        identity["choice"] = str(cfg.get("alias_choice") or "both")

    policy = state.setdefault("server_policy", {})
    if not isinstance(policy, dict):
        policy = {}
        state["server_policy"] = policy
    if overwrite or "dm_delivery" not in policy:
        policy["dm_delivery"] = str(cfg.get("dm_delivery") or "optional")
    if overwrite or "auto_manage_webhook" not in policy:
        policy["auto_manage_webhook"] = as_bool(
            cfg.get("auto_manage_webhook"), True
        )
    return state
