import bigtree
import random
import discord
import os
from pathlib import Path
from discord.ext import commands
from discord import app_commands
import bigtree.modules.contest as contesta

bot = bigtree.bot

# @bot.tree.command(name="commune", description="Send message as the tree", guild=discord.Object(bigtree.guildid))
# @commands.is_owner()
# async def commune(message,* , description: str):
#     if message.author.id == bot.user.id:
#         return
    
#     await message.channel.send(embed=description)

# Create new contest


# @bot.tree.command(name='commune', guild=discord.Object(id=bigtree.guildid), description="Send a message as the tree, using title, channel, and text, all quoted")
# @commands.is_owner()
# async def commune(message, title, channel, description):
#     embed = discord.Embed(title=title)


#     await interaction.response.send_message(text, ephemeral=True)

# async def commune_2(interaction: discord.Interaction, message: discord.Message, title: title):
#     if not emssage.content:
#         await interaction.response.send_message('Content', ephemeral=True)
#         return
    
#     content = message.content


@bot.command()
async def colour(ctx):
    """Sends a message with our dropdown containing colours"""

    # Create the view containing our dropdown
    view = bigtree.views.commune.DropdownView()

    # Sending a message containing our view
    await ctx.send('Pick your favourite colour:', view=view)

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