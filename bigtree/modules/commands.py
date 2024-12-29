import bigtree
import random
import discord
import os
from pathlib import Path
from discord.ext import commands
import bigtree.modules.contest as contesta

bot = bigtree.bot

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
    
    contesta.contest_management(message.channel.id, "testing", command="add")
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
    if message.channel.id in bigtree.contestid:   
        if str(message.attachments) == "[]":
            await message.delete()
        if not str(message.attachments) == "[]":
            split_v1 = str(message.attachments).split("filename='")[1]
            filetype = Path(str(split_v1).split("' ")[0]).suffix
            savename = message.author.name + str(message.id) + filetype
            await message.attachments[0].save(fp="{}".format(os.path.join(bigtree.contest_dir, savename)))
            await message.delete() # Delete the original message to get to reposting
            file = discord.File(os.path.join(bigtree.contest_dir, "{}".format(savename)), filename=savename)
            entry_data = {
                'name': message.author.name,
                'file': savename,
                'filename': 'fakename.png',
                'votes': [message.author.id]
                }
            entry_id = contesta.contest_management(message.channel.id, entry_data, command="add")
            embed = discord.Embed(title='Entry #{} :'.format(entry_id))
            embed.set_image(url="attachment://{}".format(savename))
            view = bigtree.default_view.default.Contest()
            view.message = message
            view.savename = savename
            await message.channel.send(file=file, embed=embed, view=view)

    # Partake.gg module
    if 'partake.gg' in message.content:
        guild = bigtree.bot.guilds[0]
        url = bigtree.core.find_url(message.content)
        event_source = await bigtree.partake.retrieve_event(bigtree.partake.get_eventid(url))
        await bigtree.event.create_partake_event(guild, event_source, url)
    
    # Random treeheart to images
    if not str(message.attachments) == "[]":
        testvalue = random.randrange(1,3,1)
        if testvalue == 2 :
            emoji = "<:treeheart:1321831300088463452>"
            await message.add_reaction(emoji)