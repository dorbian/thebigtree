import bigtree
import discord
from discord.ext import commands

@commands.command(name="contest", description="Turn this channel into a contest channel", guild=discord.Object(bigtree.guildid))
@commands.is_owner()
async def contest(message,* , msg_title: str):
    print(message.channel.id, msg_title)
    bigtree.contesta.contest_management(message.channel.id, "testing", command="add")
    embedVar = discord.Embed(title=msg_title, description="Elfoween carving contest!, Upload your picture, After uploading, I will remove and judge your entry\n Afterwards, it will be posted here by me.\n\n**To Vote:**\n Please use <:TreeCone:1226115623323701341> to cast A vote on your favorite entry\nVote on as many as you like", color=0x00ff00)
    await message.channel.send(embed=embedVar)

async def setup(bot):
    bot.add_command(contest)