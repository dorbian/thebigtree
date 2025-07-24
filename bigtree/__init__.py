# -------
# Imports
# -------
import discord
import os
import sys
import threading
import random
import asyncio
# -------
# From imports
# -------
from pathlib import Path
from tinydb import TinyDB, Query
from discord.ext import commands
from bigtree import Arguments
from bigtree import tree
import bigtree.inc.logging as loch
import bigtree.inc.Config as Config
import bigtree.inc.core as core
import bigtree.modules.partake as partake
import bigtree.modules.contest as contesta
import bigtree.modules.event as event
# predefine boolean
__initialized__ = False
# predefined lists
options = args = messages = contestid = []
config_path = workingdir = config = contest_dir = guildid = bot = None
# predefined strings
token = ''
# Threading
thread_lock = threading.Lock()
threading.current_thread().name = 'BigTree'

# bot = tree.TheBigTree()
# Initialize module
def initialize():
    with thread_lock:
        
        global __initialized__, options, args, contestid, token, config_path, workingdir, config, bot, guildid, tree, view_dir

        workingdir = Path(__file__).parent
        view_dir = workingdir / "cmds"
        config_path = os.path.join(os.getenv("HOME"), os.path.join('.config', 'bigtree.ini'))

        # Load the argument parser
        Arguments.optsargs()
        # Read in the config file
        config = Config.ConfigCheck()
        config.config_validate()

        contest_dir = config.config["BOT"]["contest_dir"]
        guildid = config.config["BOT"]["guildid"]
        token = config.config["BOT"]["token"]
        adminid = config.config["BOT"]["adminid"]
        # Get server stuff
        # Write the config back to file to make sure any changes to the format are also stored.
        config.config_write

        # Load contests
        for file in os.listdir(contest_dir):
            if file.endswith(".json"):
                contestid.append(int(Path(file).stem))
        # Proud and firm
        bot = tree.TheBigTree()

        import bigtree.inc.banner
        for cmd_file in view_dir.glob("*.py"):
            if cmd_file.name != "__init__.py":
                asyncio.run(bot.load_extension(f"bigtree.cmds.{cmd_file.name[:-3]}"))
        # load commands
        import bigtree.modules.commands
    return True