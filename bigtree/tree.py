import bigtree
import discord
from discord.ext import commands

# -------
# Base bot class
# -------

class TheBigTree(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  
        intents.message_content = True

        description = '''TheBigTree Manifest'''

        super().__init__(command_prefix=commands.when_mentioned_or('/'), intents=intents)
        
    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="elves"))
        bigtree.loch.logger.info(f'Logged in as {self.user} (ID: {bigtree.bot.user.id})')