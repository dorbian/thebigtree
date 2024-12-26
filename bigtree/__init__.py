# -------
# Imports
# -------
import discord
import os
import sys
import threading
import random
# -------
# From imports
# -------

from pathlib import Path
from tinydb import TinyDB, Query
from discord.ext import commands
from bigtree import Arguments
import bigtree.inc.logging as loch
import bigtree.inc.core as core
import bigtree.modules.partake as partake

# -------
# Configuration of initial components
# -------

# predefine boolean
__initialized__ = False
# predefined lists
options = args = messages = contestid = []
# predefined strings
token = ''

thread_lock = threading.Lock()
threading.current_thread().name = 'BigTree'

contest_dir = "/data/contest"
guildid = "1224347680776523847"

# -------
# Classless functions
# -------

def contest_management(contest_id, insertdata, command):
    global contestid 
    filepath = os.path.join(contest_dir, '{}.json'.format(contest_id))

    if os.path.exists(filepath):
        contest_list = insertdata

    if not os.path.exists(filepath):
        contest_list = {
            'name': 'tree',
            'file': 'tree',
            'filename': 'fakename.png',
            'votes': ['test']
            }
        # add the new contest in the contestlist
        contestid.append(contest_id)

    contestdb = TinyDB(filepath)

    if command == "update":
        print(contest_list)
        returnval = ""

    if command == "add":
        returnval = contestdb.insert(contest_list)

    return returnval

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
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="saplings"))
        loch.logger.info(f'Logged in as {self.user} (ID: {bot.user.id})')


# -------
# Views to embed
# -------

class Contest(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
        self.message = None
        self.savename = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    # @discord.ui.button(label='Vote', style=discord.ButtonStyle.green)
    # async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     contest_management(self.message.channel.id, insertdata=self.message, command="update")
    #     await interaction.response.send_message('Voting', ephemeral=True)

class MyView(discord.ui.View): 
    @discord.ui.button(label="A button", style=discord.ButtonStyle.primary) 
    async def button_callback(self, button, interaction): 
        button.disabled = True # set button.disabled to True to disable the button 
        button.label = "No more pressing!" # change the button's label to something else 
        await interaction.response.edit_message(view=self) # edit the message's view

bot = TheBigTree()

# -------
# Commands to process
# -------
@bot.command()
@commands.is_owner()
async def commune(message,* , description: str):
    if message.author.id == bot.user.id:
        return
    
    await message.channel.send(embed=description)

# Create new contest
@bot.command()
@commands.is_owner()
async def contest(message,* , description: str):
    if message.author.id == bot.user.id:
        return
    
    contest_management(message.channel.id, "testing", command="add")
    embedVar = discord.Embed(title=description, description="\nWelcome Elf!\nTo this amazing contest for the **Best ElfMass Poster** for 2024!\n\n**How to enter:**\nUpload a selfmade GPose or Pic that depicts ElfMass for you!\n\nWinner will get 2 million Gil\n\nAfter uploading, I will remove and judge your entry\n Afterwards, it will be posted here by me.\n\n**To Vote:**\n Please use <:TreeCone:1226115623323701341> to cast A vote on your favorite entry\nVote on as many as you like\n\nThe winner will me made known at the 21th of Elfcember\n", color=0x00ff00)
    await message.channel.send(embed=embedVar)

# async def create_event(message, *, eventdata):
#         myguild = client.guilds[0]
#         roles = await myguild.fetch_roles()
# -------
# Incomming messages related code
# -------

@bot.listen('on_message')
async def receive(message):
    # Ignore if the bot is the one sending
    if message.author.id == bot.user.id:
        return

    # Is this in a known contest channel, if so, use contest code
    if message.channel.id in contestid:   
        if str(message.attachments) == "[]":
            await message.delete()
        if not str(message.attachments) == "[]":
            split_v1 = str(message.attachments).split("filename='")[1]
            filetype = Path(str(split_v1).split("' ")[0]).suffix
            savename = message.author.name + str(message.id) + filetype
            await message.attachments[0].save(fp="{}".format(os.path.join(contest_dir, savename)))
            await message.delete() # Delete the original message to get to reposting
            file = discord.File(os.path.join(contest_dir, "{}".format(savename)), filename=savename)
            entry_data = {
                'name': message.author.name,
                'file': savename,
                'filename': 'fakename.png',
                'votes': [message.author.id]
                }
            entry_id = contest_management(message.channel.id, entry_data, command="add")
            embed = discord.Embed(title='Entry #{} :'.format(entry_id))
            embed.set_image(url="attachment://{}".format(savename))
            view = Contest()
            view.message = message
            view.savename = savename
            await message.channel.send(file=file, embed=embed, view=view)
    if 'partake.gg' in message.content:
        event_source = await partake.retrieve_event(partake.get_eventid(core.find_url(message.content)))
        # processed_event = converter.partake(event_source)
    
    # Random treeheart to images
    if not str(message.attachments) == "[]":
        testvalue = random.randrange(6)
        if testvalue == 3:
            emoji = "<:treeheart:1321831300088463452>"
            await message.add_reaction(emoji)
#todo:
# delete_contest then adding
# get nr from db

# -------
# Finally run if we are directly executed
# -------

def initialize():
    with thread_lock:
        global __initialized__, options, args, contestid, token

        # Load the argument parser
        Arguments.optsargs()
        
        # Open token file and read it in
        token = open('{}/token'.format(os.getenv("HOME")), 'r').read()
        
        # Load contests
        for file in os.listdir(contest_dir):
            if file.endswith(".json"):
                contestid.append(int(Path(file).stem))
        # Proud and firm
        import bigtree.inc.banner
    return True
