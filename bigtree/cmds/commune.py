# bigtree/cmds/commune.py
# Interactive /commune builder with buttons + modals
# - Build an embed (title + N sections)
# - Pick a target channel via a ChannelSelect
# - Preview and Post
# - Uses bigtree.loch.logger for logging

import bigtree
import discord
from bigtree.modules.permissions import is_bigtree_operator
from discord import app_commands
from discord.ext import commands
from typing import List, Optional, Dict, Tuple
from bigtree.inc.logging import logger

bot = bigtree.bot

# -------------------------
# Session state per user/guild
# -------------------------
# Keyed by (guild_id, user_id) -> session data
_SESSIONS: Dict[Tuple[int, int], "CommuneSession"] = {}

class CommuneSession:
    def __init__(self, user_id: int, guild_id: int):
        self.user_id = user_id
        self.guild_id = guild_id
        self.title: Optional[str] = None
        self.sections: List[Tuple[str, str]] = []  # (name, value)
        self.target_channel_id: Optional[int] = None
        self.ping_everyone: bool = False

    def to_embed(self) -> discord.Embed:
        emb = discord.Embed(title=self.title or "Untitled", colour=discord.Colour.green())
        for name, value in self.sections:
            emb.add_field(name=name[:256] or "\u200b", value=value[:1024] or "\u200b", inline=False)
        emb.set_footer(text="TheBigTree Manifesto")
        return emb

# -------------------------
# UI: Modals
# -------------------------
class TitleModal(discord.ui.Modal, title="Commune: Set Title"):
    title_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Title",
        placeholder="Announcement title",
        max_length=100
    )

    def __init__(self, session_key: Tuple[int, int]):
        super().__init__()
        self.session_key = session_key

    async def on_submit(self, interaction: discord.Interaction):
        sess = _SESSIONS.get(self.session_key)
        if not sess:
            await interaction.response.send_message("Session expired, please re-open /commune.", ephemeral=True)
            return
        sess.title = str(self.title_input.value).strip()
        await interaction.response.send_message("✅ Title set.", ephemeral=True)

class SectionModal(discord.ui.Modal, title="Commune: Add Section"):
    name_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Section title",
        placeholder="Rules / Context / Details …",
        max_length=256
    )
    value_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Section body",
        style=discord.TextStyle.paragraph,
        placeholder="Write your message here…",
        max_length=1024
    )

    def __init__(self, session_key: Tuple[int, int]):
        super().__init__()
        self.session_key = session_key

    async def on_submit(self, interaction: discord.Interaction):
        sess = _SESSIONS.get(self.session_key)
        if not sess:
            await interaction.response.send_message("Session expired, please re-open /commune.", ephemeral=True)
            return
        sess.sections.append((str(self.name_input.value), str(self.value_input.value)))
        await interaction.response.send_message("➕ Section added.", ephemeral=True)

# -------------------------
# UI: Components (View)
# -------------------------
class ChannelPicker(discord.ui.Select):
    def __init__(self, session_key: Tuple[int, int]):
        self.session_key = session_key
        super().__init__(
            placeholder="Pick a target channel…",
            min_values=1,
            max_values=1,
            options=[]
        )

    async def callback(self, interaction: discord.Interaction):
        # In practice, we'll use ChannelSelect; this fallback keeps structure.
        await interaction.response.defer(ephemeral=True)

class CommuneView(discord.ui.View):
    def __init__(self, session_key: Tuple[int, int]):
        super().__init__(timeout=900)  # 15 min
        self.session_key = session_key

    @discord.ui.button(label="Set title", style=discord.ButtonStyle.primary)
    async def set_title(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.send_modal(TitleModal(self.session_key))

    @discord.ui.button(label="Add section", style=discord.ButtonStyle.secondary)
    async def add_section(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        await interaction.response.send_modal(SectionModal(self.session_key))

    @discord.ui.button(label="Toggle @everyone", style=discord.ButtonStyle.secondary)
    async def toggle_ping(self, interaction: discord.Interaction, _button: discord.ui.Button):
        sess = _SESSIONS.get(self.session_key)
        if not sess or interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        sess.ping_everyone = not sess.ping_everyone
        await interaction.response.send_message(f"@everyone is now **{'ON' if sess.ping_everyone else 'OFF'}**.", ephemeral=True)

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.success)
    async def preview(self, interaction: discord.Interaction, _button: discord.ui.Button):
        sess = _SESSIONS.get(self.session_key)
        if not sess or interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        embed = sess.to_embed()
        await interaction.response.send_message(
            content=("@everyone" if sess.ping_everyone else None),
            embed=embed,
            ephemeral=True
        )

    @discord.ui.button(label="Post", style=discord.ButtonStyle.green)
    async def post(self, interaction: discord.Interaction, _button: discord.ui.Button):
        sess = _SESSIONS.get(self.session_key)
        if not sess or interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        if not sess.title or not sess.sections:
            return await interaction.response.send_message("Please set a title and add at least one section.", ephemeral=True)
        if not sess.target_channel_id:
            return await interaction.response.send_message("Please pick a target channel first.", ephemeral=True)

        channel = bot.get_channel(sess.target_channel_id)
        if not channel:
            return await interaction.response.send_message("Cannot find that channel (cache miss). Try again.", ephemeral=True)

        embed = sess.to_embed()
        content = "@everyone" if sess.ping_everyone else None
        await channel.send(content=content, embed=embed)
        logger.info(f"Commune posted by {interaction.user.id} into channel {sess.target_channel_id}")
        del _SESSIONS[self.session_key]
        await interaction.response.edit_message(content="✅ Posted!", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        if self.session_key in _SESSIONS:
            del _SESSIONS[self.session_key]
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news], placeholder="Choose target channel…", min_values=1, max_values=1)
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        sess = _SESSIONS.get(self.session_key)
        if not sess or interaction.user.id != self.session_key[1]:
            return await interaction.response.send_message("Not your session.", ephemeral=True)
        if not select.values:
            return await interaction.response.send_message("No channel selected.", ephemeral=True)
        sess.target_channel_id = select.values[0].id
        await interaction.response.send_message(f"📌 Target set to <#{sess.target_channel_id}>", ephemeral=True)

# -------------------------
# Slash command
# -------------------------
@bot.tree.command(name="commune", description="Compose and post a message as The Big Tree", guild=discord.Object(id=bigtree.guildid))
@app_commands.default_permissions(send_messages=True)  
@is_bigtree_operator()
async def commune_slash(interaction: discord.Interaction):

    key = (interaction.guild_id, interaction.user.id)
    _SESSIONS[key] = CommuneSession(user_id=interaction.user.id, guild_id=interaction.guild_id)

    view = CommuneView(key)
    await interaction.response.send_message(
        "🌿 **Commune builder** — use the buttons to set a title, add sections, choose a channel, preview, and post.",
        view=view,
        ephemeral=True
    )

async def setup(_bot):
    # slash command is registered via bot.tree; nothing to add here
    pass
