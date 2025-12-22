import asyncio
import bigtree
from bigtree.inc.webserver import ensure_webserver, get_server
from bigtree.modules import honse_presence
import discord
from discord.ext import commands
# -------
# Base bot class
# -------

class TheBigTree(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.members = True  
        intents.message_content = True

        description = '''TheBigTree Manifest'''

        super().__init__(command_prefix=commands.when_mentioned_or('/'), intents=intents)
        
    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="listening to elves"))
        bigtree.loch.logger.info(f'Logged in as {self.user} (ID: {bigtree.bot.user.id})')
        guild = discord.Object(id=bigtree.guildid)
        # Add awesomeies to the server
        synced = await self.tree.sync(guild=guild)
        # add near your other imports
        if getattr(bigtree.bot, "_web_started", False):
                return
        srv = await ensure_webserver()
        bigtree.bot._web_started = True
        host = srv._cfg["host"]
        port = srv._cfg["port"]
        base = srv._cfg["base_url"]
        bigtree.loch.logger.info(f"[web] started on {host}:{port} (base_url={base})")

        if not getattr(bigtree.bot, "_presence_task", None):
            bigtree.bot._presence_task = asyncio.create_task(self._presence_loop())

    async def _presence_loop(self):
        while True:
            try:
                count = await asyncio.to_thread(honse_presence.get_online_count)
                if count is not None and count > 0:
                    label = f"Channeling {count} Elf" if count == 1 else f"Channeling {count} Elves"
                else:
                    label = "listening to elves"
                await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=label))
            except Exception as e:
                bigtree.loch.logger.warning(f"[presence] update failed: {e}")
            await asyncio.sleep(honse_presence.HONSE_REFRESH_SECONDS)
