import asyncio
from pathlib import Path

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
        
    async def setup_hook(self):
        """Load extensions and the HTTP service on the bot's real event loop.

        The old startup path called asyncio.run() once per extension before
        Bot.run(), which created short-lived event loops. Persistent Discord
        views and background-aware cogs are safer when registered here.
        """
        view_dir = Path(getattr(bigtree, "view_dir", Path(__file__).parent / "cmds"))
        skipped = {"__init__.py", "gpose_cmd.py", "content_cmd.py", "review_cmd.py"}
        for cmd_file in sorted(view_dir.glob("*.py")):
            if cmd_file.name in skipped:
                continue
            await self.load_extension(f"bigtree.cmds.{cmd_file.stem}")

        # These historically load after the general command set. Preserve that
        # ordering while keeping all setup on the same event loop.
        for extension in (
            "bigtree.cmds.gpose_cmd",
            "bigtree.cmds.content_cmd",
            "bigtree.cmds.review_cmd",
        ):
            await self.load_extension(extension)

        srv = await ensure_webserver()
        self._web_started = True
        bigtree.loch.logger.info(
            "[web] started on %s:%s (base_url=%s)",
            srv._cfg["host"],
            srv._cfg["port"],
            srv._cfg["base_url"],
        )

    async def on_ready(self):
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening, name="listening to elves"
            )
        )
        bigtree.loch.logger.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else None)

        if not getattr(self, "_commands_synced", False):
            await self.tree.sync()
            guild = discord.Object(id=bigtree.guildid)
            await self.tree.sync(guild=guild)
            self._commands_synced = True
            bigtree.loch.logger.info("[discord] application commands synchronized")

        if not getattr(self, "_presence_task", None):
            self._presence_task = asyncio.create_task(
                self._presence_loop(), name="bigtree-presence"
            )
        if not getattr(self, "_presence_warm", False):
            self._presence_warm = True
            asyncio.create_task(self._presence_once(), name="bigtree-presence-warm")

    async def close(self):
        """Gracefully release resources before Podman replaces the container."""
        task = getattr(self, "_presence_task", None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        try:
            srv = get_server()
            if srv is not None:
                await srv.stop()
        except Exception as exc:
            bigtree.loch.logger.warning("[shutdown] web stop failed: %s", exc)

        try:
            from bigtree.inc.plogon import stop_plogon_refresh_loop
            stop_plogon_refresh_loop()
        except Exception as exc:
            bigtree.loch.logger.warning("[shutdown] plogon stop failed: %s", exc)

        try:
            from bigtree.inc.database import close_database
            close_database()
        except Exception as exc:
            bigtree.loch.logger.warning("[shutdown] database close failed: %s", exc)

        bigtree.loch.logger.info("[shutdown] BigTree resources released")
        await super().close()
        try:
            bigtree.loch.shutdown_logging()
        except Exception:
            pass

    async def _presence_once(self):
        try:
            count = await asyncio.to_thread(honse_presence.get_online_count)
            if count is not None and count > 0:
                label = f"Communing with {count} elf" if count == 1 else f"Communing with {count} elves"
            else:
                label = "listening to elves"
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=label))
        except Exception as e:
            bigtree.loch.logger.warning(f"[presence] immediate update failed: {e}")

    async def _presence_loop(self):
        while True:
            try:
                count = await asyncio.to_thread(honse_presence.get_online_count)
                if count is not None and count > 0:
                    label = f"Communing with {count} elf" if count == 1 else f"Communing with {count} elves"
                else:
                    label = "listening to elves"
                await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=label))
            except Exception as e:
                bigtree.loch.logger.warning(f"[presence] update failed: {e}")
            await asyncio.sleep(honse_presence.HONSE_REFRESH_SECONDS)
