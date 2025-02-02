import bigtree
import datetime
import discord
from discord.ext import commands

class CommuneThread():
    def __init__(self):
        self.embed = ''
        self.channel = ''
        self.bot = bigtree.bot

communion = CommuneThread()

@commands.group()
async def commune(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send(f"Please do some subcommands :) ")

@commune.command()
async def title(ctx, *titles):
    communion.embed = discord.Embed(title=' '.join(titles), colour=discord.Colour.green())
    communion.embed.set_footer(text=f"TheBigTree Manifesto")
    await ctx.send('Title Registered')

@commune.command()
async def channel(ctx, *channels):
    communion.channel = ''.join(channels)
    await ctx.send('Channel Registered')

@commune.command()
async def message(ctx, title, *messages):
    communion.embed.add_field(name=title, value=' '.join(messages), inline=False)
    await ctx.send('Message Registered')

@commune.command()
async def draft(ctx):
    communion.embed.timestamp = datetime.datetime.utcnow()
    await ctx.send(embed=communion.embed)

@commune.command()
async def post(ctx):
    guild = bigtree.bot.guilds[0]
    channelID = int(communion.channel)
    channel = communion.bot.get_channel(channelID)
    communion.embed.timestamp = datetime.datetime.utcnow()
    await channel.send(embed=communion.embed)
    communion.embed = ''

@commune.command()
async def delete(ctx):
    communion.embed = ''
    await ctx.send('Message deleted')

async def setup(bot):
    bot.add_command(commune)