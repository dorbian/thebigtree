"""
Utilities for accessing configuration settings with fallback patterns.
Centralizes the repeated try/except/env pattern used throughout the codebase.
"""

import os
from typing import Optional, Any
import bigtree


def get_data_dir() -> str:
    """
    Resolve the BigTree data directory from multiple sources.
    
    Priority:
    1. Environment variable BIGTREE__BOT__DATA_DIR
    2. Environment variable BIGTREE_DATA_DIR
    3. Settings BOT.DATA_DIR
    4. Environment variable BIGTREE_WORKDIR
    5. Current working directory + .bigtree
    
    Returns:
        str: Path to the data directory (created if necessary)
    """
    # Check direct env vars first (highest priority)
    env_data = os.getenv("BIGTREE__BOT__DATA_DIR") or os.getenv("BIGTREE_DATA_DIR")
    if env_data:
        os.makedirs(env_data, exist_ok=True)
        return env_data
    
    # Check bigtree.settings
    try:
        settings = getattr(bigtree, "settings", None)
        if settings:
            base = settings.get("BOT.DATA_DIR", None, str)
            if base:
                os.makedirs(base, exist_ok=True)
                return base
    except Exception:
        pass
    
    # Fallback to env or workdir
    env_workdir = os.getenv("BIGTREE_WORKDIR")
    if env_workdir:
        os.makedirs(env_workdir, exist_ok=True)
        return env_workdir
    
    # Last resort
    default = os.path.join(os.getcwd(), ".bigtree")
    os.makedirs(default, exist_ok=True)
    return default


def get_setting(section_key: str, default: Any = None, cast: type = str) -> Any:
    """
    Get a setting from bigtree.settings with type casting.
    
    Args:
        section_key: Setting key in "SECTION.KEY" format
        default: Value to return if setting not found
        cast: Type to cast the value to (str, int, bool, float)
    
    Returns:
        The setting value or default if not found
    """
    try:
        settings = getattr(bigtree, "settings", None)
        if settings:
            return settings.get(section_key, default, cast)
    except Exception:
        pass
    return default


def resolve_log_path(base_name: str = "discord.log") -> str:
    """
    Resolve a log file path, preferring environment overrides.
    
    Args:
        base_name: The log filename (e.g., "discord.log", "upload.log")
    
    Returns:
        str: Full path to log file (directory created if necessary)
    """
    env_key = f"BIGTREE_{base_name.upper().replace('.', '_')}_PATH"
    override = os.getenv(env_key)
    if override:
        log_dir = os.path.dirname(override)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        return override
    
    data_dir = get_data_dir()
    log_path = os.path.join(data_dir, base_name)
    return log_path
