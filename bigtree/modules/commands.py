import bigtree
import random
import discord
import os
import importlib
from pathlib import Path
from discord.ext import commands
from discord import app_commands
from discord import Permissions
from bigtree.modules.permissions import is_bigtree_operator
import bigtree.modules.contest as contesta
import re
import asyncio
from collections import defaultdict, deque
import bigtree.inc.ai as ai 
from bigtree.cmds.contest import add_caption_button_to_view 

PRIEST_ROLE_NAME = "Priest/ess"

bot = bigtree.bot

# Simple per-user rolling memory (volatile)
_user_hist = defaultdict(lambda: deque(maxlen=8))

def _resolve_contest_view():
    """
    Find a Contest View class without hard-coding one module.
    Tries a few likely modules; falls back to a minimal View.
    """
    candidates = [
        "bigtree.cmds.contest_ui:Contest",  # if you split UI out
        "bigtree.cmds.contest:Contest",     # common location
        "bigtree.views.default:Contest",    # if you have a views/ package
    ]
    for path in candidates:
        mod, _, attr = path.partition(":")
        try:
            m = importlib.import_module(mod)
            cls = getattr(m, attr, None)
            if cls is not None:
                return cls
        except Exception:
            continue

    # Fallback to a minimal empty view so the bot won’t crash
    class FallbackContest(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)

    return FallbackContest

def _strip_bot_mention(text: str, bot_user) -> str:
    patterns = [
        re.escape(bot_user.mention),           # <@123>
        re.escape(f"<@!{bot_user.id}>"),       # <@!123>
        re.escape(f"<@{bot_user.id}>"),        # <@123>
    ]
    return re.sub("|".join(patterns), "", text).strip()

def _is_priest(member) -> bool:
    if not member or not hasattr(member, "roles"):
        return False
    return any(r.name == PRIEST_ROLE_NAME for r in member.roles)

def _should_handle_public(message, bot):
    if bot.user in message.mentions:
        return True
    if message.reference and message.reference.resolved:
        ref = message.reference.resolved
        return getattr(ref.author, "id", None) == bot.user.id
    return False

async def _ask_tree(user_id: int, prompt: str) -> str:
    # Gather brief history, let the ai module do the rest
    history = list(_user_hist[user_id])
    reply = await ai.ask(
        user_id=user_id,
        prompt=prompt,
        persona="tree",
        history=history
    )
    # update history
    _user_hist[user_id].append({"role": "user", "content": prompt})
    _user_hist[user_id].append({"role": "assistant", "content": reply})
    return reply

@bot.command()
async def colour(ctx):
    view = bigtree.views.commune.DropdownView()
    await ctx.send('Pick your favourite colour:', view=view)

@bot.listen('on_message')
async def receive(message):
    try:
        if message.author.id == bot.user.id:
            return

        # contest channel handling
        if message.channel.id in bigtree.contestid:
            if str(message.attachments) == "[]":
                await message.delete()
            else:
                split_v1 = str(message.attachments).split("filename='")[1]
                filetype = Path(str(split_v1).split("' ")[0]).suffix
                savename = message.author.name + str(message.id) + filetype
                await message.attachments[0].save(fp=os.path.join(bigtree.contest_dir, savename))
                await message.delete()
                file = discord.File(os.path.join(bigtree.contest_dir, savename), filename=savename)
                entry_data = {
                    'name': message.author.name,
                    'file': savename,
                    'filename': 'fakename.png',
                    'votes': [message.author.id]
                }
                entry_id = contesta.contest_management(message.channel.id, entry_data, command="add")
                embed = discord.Embed(title=f'Entry #{entry_id} :')
                embed.set_image(url=f"attachment://{savename}")
                ViewCls = _resolve_contest_view()
                view = ViewCls()
                view.message = message
                view.savename = savename
                sent = await message.channel.send(file=file, embed=embed, view=view)

                add_caption_button_to_view(view, target_message_id=sent.id, owner_id=message.author.id)
                await sent.edit(view=view)

        # partake.gg quick hook
        if 'partake.gg' in message.content:
            guild = bigtree.bot.guilds[0]
            url = bigtree.core.find_url(message.content)
            event_source = await bigtree.partake.retrieve_event(bigtree.partake.get_eventid(url))
            await bigtree.event.create_partake_event(guild, event_source, url)

        # random treeheart for image posts
        if not str(message.attachments) == "[]":
            if random.randrange(1,3,1) == 2:
                await message.add_reaction("<:treeheart:1321831300088463452>")
    except Exception:
        bigtree.loch.logger.exception("Unhandled error in receive()")

@bot.listen('on_message')
async def priest_chat_router(message):
    try:
        if message.author.bot:
            return

        # Let slash commands pass; still allow mention-triggered chats
        if message.content.startswith('/'):
            return

        guild = bot.guilds[0] if bot.guilds else None
        member = guild.get_member(message.author.id) if guild else None

        # Case 1: DMs from Priest
        if isinstance(message.channel, discord.DMChannel):
            if not guild or not member or not _is_priest(member):
                return
            prompt = message.content.strip()
            if not prompt:
                return
            async with message.channel.typing():
                try:
                    reply = await _ask_tree(message.author.id, prompt)
                except Exception:
                    bigtree.loch.logger.exception("Priest DM OpenAI failure")
                    reply = "🍂 The winds falter—my roots feel some trouble reaching the beyond. Try again soon."
                await message.channel.send(reply)
            return

        # Case 2: Public: only if addressing the bot, and author is Priest
        if message.guild and _should_handle_public(message, bot):
            if not member or not _is_priest(member):
                return
            prompt = _strip_bot_mention(message.content, bot.user) or "The Priest seeks guidance."
            async with message.channel.typing():
                try:
                    reply = await _ask_tree(message.author.id, prompt)
                except Exception:
                    bigtree.loch.logger.exception("Priest public OpenAI failure")
                    reply = "🌬️ I hear you, but the spirit channel crackles. Whisper again in a moment."
                await message.reply(reply, mention_author=False)
    except Exception:
        bigtree.loch.logger.exception("Unhandled error in priest_chat_router")
