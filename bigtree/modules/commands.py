import bigtree
bot = bigtree.bot

@bot.command()
@commands.is_owner()
async def commune(message,* , description: str):
    if message.author.id == bot.user.id:
        return
    
    await message.channel.send(embed=description)