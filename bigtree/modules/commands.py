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
from bigtree.modules import gallery as gallery_mod
from bigtree.modules import media as media_mod
from bigtree.modules import artists as artist_mod
import re
import asyncio
from collections import defaultdict, deque
import bigtree.inc.ai as ai 

PRIEST_ROLE_NAME = "Priest/ess"

bot = bigtree.bot
_GALLERY_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

# Simple per-user rolling memory (volatile)
_user_hist = defaultdict(lambda: deque(maxlen=8))

def _can_edit_gallery_upload(member, uploader_id: str) -> bool:
    if not member:
        return False
    if str(getattr(member, "id", "")) == str(uploader_id):
        return True
    perms = getattr(member, "guild_permissions", None)
    return bool(perms and (perms.administrator or perms.manage_guild))

class GalleryUploadModal(discord.ui.Modal, title="Gallery: Add Details"):
    def __init__(self, filename: str, artist_id: str, default_title: str, default_name: str):
        super().__init__()
        self.filename = filename
        self.artist_id = artist_id
        self.title_input = discord.ui.TextInput(
            label="Title",
            required=False,
            max_length=120,
            default=default_title or ""
        )
        self.artist_input = discord.ui.TextInput(
            label="Artist name",
            required=False,
            max_length=80,
            default=default_name or ""
        )
        self.add_item(self.title_input)
        self.add_item(self.artist_input)

    async def on_submit(self, interaction: discord.Interaction):
        title = (self.title_input.value or "").strip()
        artist_name = (self.artist_input.value or "").strip()
        if not artist_name:
            artist_name = getattr(interaction.user, "display_name", "") or interaction.user.name
        try:
            artist_mod.upsert_artist(self.artist_id, artist_name, {})
            media_mod.add_media(self.filename, title=title or None, artist_id=self.artist_id)
        except Exception as exc:
            await interaction.response.send_message(f"Could not save details: {exc}", ephemeral=True)
            return
        await interaction.response.send_message("Gallery details saved.", ephemeral=True)

class GalleryUploadView(discord.ui.View):
    def __init__(self, filename: str, artist_id: str):
        super().__init__(timeout=3600)
        self.filename = filename
        self.artist_id = artist_id

    @discord.ui.button(label="Add details", style=discord.ButtonStyle.secondary)
    async def add_details(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not _can_edit_gallery_upload(interaction.user, self.artist_id):
            await interaction.response.send_message("Only the uploader can edit this entry.", ephemeral=True)
            return
        artist = artist_mod.get_artist(self.artist_id) or {}
        media = media_mod.get_media(self.filename) or {}
        default_title = media.get("title") or ""
        default_name = artist.get("name") or getattr(interaction.user, "display_name", "") or interaction.user.name
        await interaction.response.send_modal(
            GalleryUploadModal(self.filename, self.artist_id, default_title, default_name)
        )

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
    # Self-contained demo view to avoid missing bigtree.views.*
    class ColourSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label="Red"),
                discord.SelectOption(label="Green"),
                discord.SelectOption(label="Blue"),
            ]
            super().__init__(placeholder="Pick a colour…", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_message(f"You picked **{self.values[0]}** ✅", ephemeral=True)

    class ColourView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(ColourSelect())

    await ctx.send('Pick your favourite colour:', view=ColourView())

@bot.listen('on_message')

async def receive(message):
    try:
        if message.author.id == bot.user.id:
            return

        upload_channel_id = gallery_mod.get_upload_channel_id()
        if upload_channel_id and message.channel.id == upload_channel_id:
            if message.attachments:
                for idx, attachment in enumerate(message.attachments):
                    filename = attachment.filename or ""
                    ext = Path(filename).suffix.lower()
                    content_type = (attachment.content_type or "").lower()
                    if ext not in _GALLERY_IMG_EXTS and not content_type.startswith("image/"):
                        continue
                    safe_ext = ext if ext in _GALLERY_IMG_EXTS else ".png"
                    author_id = str(message.author.id)
                    save_name = f"gallery_{message.id}_{idx}{safe_ext}"
                    try:
                        await attachment.save(fp=os.path.join(media_mod.get_media_dir(), save_name))
                    except Exception:
                        continue
                    display_name = getattr(message.author, "display_name", None) or message.author.name
                    artist_mod.upsert_artist(author_id, display_name, {})
                    base_title = (message.content or "").strip() or filename
                    title = base_title if idx == 0 else f"{base_title} ({idx + 1})"
                    media_mod.add_media(save_name, original_name=filename, artist_id=author_id, title=title)
                    try:
                        view = GalleryUploadView(save_name, author_id)
                        await message.reply(
                            "Upload saved. Add details if needed.",
                            view=view,
                            mention_author=False
                        )
                    except Exception:
                        pass
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
