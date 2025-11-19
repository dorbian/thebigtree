# -------
# Imports
# -------
import discord
import os
import sys
import threading
import random
import asyncio
import types

# -------
# From imports
# -------
from pathlib import Path
from tinydb import TinyDB, Query
from discord.ext import commands
from types import SimpleNamespace
from bigtree import Arguments
from bigtree import tree
from bigtree.inc.settings import load_settings
import bigtree.inc.logging as loch
import bigtree.inc.Config as Config
import bigtree.inc.core as core
import bigtree.modules.partake as partake
import bigtree.modules.contest as contesta
import bigtree.modules.event as event

# predefine boolean
__initialized__ = False

# predefined lists (use independent lists, not all pointing to the same object)
options, args, messages, contestid = [], [], [], []

# predefined vars
config_path = workingdir = config = contest_dir = guildid = bot = None

# predefined strings
token = openai_api_key = ''

# Threading
thread_lock = threading.Lock()
threading.current_thread().name = 'BigTree'

def _require_keys(cfg, section: str, required: tuple, cfg_path: str):
    if section not in cfg:
        raise RuntimeError(f"Config error: missing [{section}] in {cfg_path}")
    sec = cfg[section]
    # normalize accidental whitespace in key names (e.g., 'openai_api_key ')
    for k in list(sec.keys()):
        nk = k.strip()
        if nk != k:
            sec[nk] = sec.pop(k)
    present = list(sec.keys())
    print(f"[{section}] present keys: {present}  (from {cfg_path})", flush=True)
    missing = [k for k in required if k not in sec]
    if missing:
        raise RuntimeError(
            f"Config error: missing keys in [{section}]: {', '.join(missing)}\n"
            f"Config path: {cfg_path}\nPresent keys: {present}"
        )
    return sec

# Initialize module
def initialize():
    with thread_lock:
        global __initialized__, options, args, contestid, token, config_path, workingdir, config, \
            bot, guildid, tree, view_dir, contest_dir, openai_api_key, openai_model, openai_temperature, \
            openai_max_output_tokens, adminid

        workingdir = Path(__file__).parent
        view_dir = workingdir / "cmds"
        config_path = os.path.join(os.getenv("HOME"), os.path.join('.config', 'bigtree.ini'))

        settings = load_settings()  # env overlays applied automatically
        import bigtree as _bt
        _bt.settings = settings
        # Bot basics
        bot_sec = settings["BOT"]
        contest_dir = bot_sec.get("contest_dir", "/data/contest")
        os.makedirs(contest_dir, exist_ok=True)
        guildid     = int(bot_sec.get("guildid", ""))
        token       = os.getenv("DISCORD_TOKEN") or bot_sec.get("token", "")
        adminid     = bot_sec.get("adminid", "")

        # OpenAI (modules can require these when they actually need them)
        openai_api_key        = settings.get("openai.openai_api_key", "", str) or os.getenv("OPENAI_API_KEY") or "none"
        openai_model          = settings.get("openai.openai_model", "gpt-4o-mini")
        openai_temperature    = settings.get("openai.openai_temperature", 0.7, float)
        openai_max_output     = settings.get("openai.openai_max_output_tokens", 400, int)

        # New web (no schema required)
        web_host   = settings.get("WEB.listen_host", "0.0.0.0")
        web_port   = settings.get("WEB.listen_port", 8443, int)
        base_url   = settings.get("WEB.base_url", f"http://{web_host}:{web_port}")
        api_keys   = settings.get("WEB.api_keys", [], cast="json")   # handles JSON or comma-list via env

        # Example: legacy read
        legacy_jwt = settings.get("webapi.api_jwt", "", str)

        # Load contests list
        contestid.clear()
        for file in os.listdir(contest_dir):
            if file.endswith(".json"):
                try:
                    contestid.append(int(Path(file).stem))
                except ValueError:
                    # ignore non-numeric filenames
                    pass
        # if not os.path.exists(config_path):
        #     config.config_write()
        # Bring up the bot
        bot = tree.TheBigTree()
        import bigtree.inc.banner  # warm welcome banner
        import bigtree.modules.commands  # register CLI-ish commands

        # Start dynamic webserver when the bot becomes ready (exactly once)
        from bigtree.inc.webserver import ensure_webserver

        # Load command extensions (safe to do here; initialize runs before bot loop)
        for cmd_file in view_dir.glob("*.py"):
            if cmd_file.name != "__init__.py":
                asyncio.run(bot.load_extension(f"bigtree.cmds.{cmd_file.name[:-3]}"))

    return True
