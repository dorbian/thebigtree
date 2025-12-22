# bigtree/cmds/tarot.py
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import bigtree
from bigtree.modules import tarot as tar
from bigtree.inc.webserver import ensure_webserver

class AddCardModal(discord.ui.Modal, title="Add Tarrot Card"):
    deck = discord.ui.TextInput(label="Deck", placeholder="elf-classic")
    title_field = discord.ui.TextInput(label="Card Title", placeholder="The Heartwood")
    meaning = discord.ui.TextInput(label="Meaning", style=discord.TextStyle.paragraph, max_length=1500)
    image = discord.ui.TextInput(label="Image URL (optional)", required=False, placeholder="https://...")

    async def on_submit(self, interaction: discord.Interaction):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True); return
        tar.add_card(str(self.deck), str(self.title_field), str(self.meaning), str(self.image))
        await interaction.response.send_message("Card added ?.", ephemeral=True)

class Tarot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="tarot_start", description="Start a Tarrot reading session")
    @app_commands.describe(follower="Target whose fortune is read", deck="Deck name", spread="Spread name")
    async def tarot_start(self, interaction: discord.Interaction, follower: discord.Member, deck: str="elf-classic", spread: str="single"):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("You need Priest/ess or Elfministrator role.", ephemeral=True); return
        s = tar.create_session(interaction.user.id, deck, spread)
        cfg = bigtree.config.config.get("WEB", {})
        base = (cfg.get("base_url") or "http://localhost:8765").rstrip("/")
        join_code = s["join_code"]
        token = s["priestess_token"]
        priest_url = f"{base}/tarot/session/{join_code}?view=priestess&token={token}"
        follower_url = f"{base}/tarot/session/{join_code}?view=player"
        overlay_url = f"{base}/overlay/session/{join_code}"
        await ensure_webserver()
        await interaction.response.send_message(
            f"Session **{s['session_id']}**\n**Priestess:** {priest_url}\n**Player:** {follower_url}\n**Overlay:** {overlay_url}",
            ephemeral=True
        )

    @app_commands.command(name="tarot_draw", description="Draw N cards into the current session")
    async def tarot_draw(self, interaction: discord.Interaction, session_id: str, count: Optional[int]=1):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True); return
        s = tar.get_session_by_id(session_id)
        if not s:
            await interaction.response.send_message("Session not found.", ephemeral=True); return
        tar.draw_cards(session_id, s.get("priestess_token", ""), count or 1)
        await interaction.response.send_message("Card(s) drawn.", ephemeral=True)

    @app_commands.command(name="tarot_flip", description="Flip a card by index (0-based)")
    async def tarot_flip(self, interaction: discord.Interaction, session_id: str, index: int):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True); return
        s = tar.get_session_by_id(session_id)
        if not s:
            await interaction.response.send_message("Session not found.", ephemeral=True); return
        if index < 0 or index >= len(s.get("draw", [])):
            await interaction.response.send_message("Index out of range.", ephemeral=True); return
        position_id = s["draw"][index]["position_id"]
        tar.reveal(session_id, s.get("priestess_token", ""), mode="position", position_id=position_id)
        await interaction.response.send_message(f"Flipped card #{index}.", ephemeral=True)

    @app_commands.command(name="tarot_end", description="End a session")
    async def tarot_end(self, interaction: discord.Interaction, session_id: str):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True); return
        s = tar.get_session_by_id(session_id)
        if not s:
            await interaction.response.send_message("Session not found.", ephemeral=True); return
        tar.finish_session(session_id, s.get("priestess_token", ""))
        await interaction.response.send_message("Session ended.", ephemeral=True)

    @app_commands.command(name="tarot_add_card", description="Add a new card to a deck")
    async def tarot_add_card(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AddCardModal())

    @app_commands.command(name="tarot_stream", description="Toggle streaming presence for reading")
    async def tarot_stream(self, interaction: discord.Interaction, enable: bool=True, title: str="Reading under TheBigTree"):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True); return
        if enable:
            await bigtree.bot.change_presence(activity=discord.Streaming(name=title, url="https://twitch.tv/"))
        else:
            await bigtree.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="elves"))
        await interaction.response.send_message(f"Stream {'enabled' if enable else 'disabled'}.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tarot(bot))
