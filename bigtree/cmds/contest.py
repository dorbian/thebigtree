import bigtree
import discord
from discord.ext import commands

@commands.command(name="contest", description="Turn this channel into a contest channel", guild=discord.Object(bigtree.guildid))
@commands.is_owner()
async def contest(message,* , description: str):
    bigtree.contesta.contest_management(message.channel.id, "testing", command="add")
    embedVar = discord.Embed(title=description, description="\nWelcome Elf!\nTo this amazing contest for the **Best ElfMass Poster** for 2024!\n\n**How to enter:**\nUpload a selfmade GPose or Pic that depicts ElfMass for you!\n\nWinner will get 2 million Gil\n\nAfter uploading, I will remove and judge your entry\n Afterwards, it will be posted here by me.\n\n**To Vote:**\n Please use <:TreeCone:1226115623323701341> to cast A vote on your favorite entry\nVote on as many as you like\n\nThe winner will me made known at the 21th of Elfcember\n", color=0x00ff00)
    await message.channel.send(embed=embedVar)

async def setup(bot):
    bot.add_command(contest)