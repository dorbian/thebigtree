# bigtree/cmds/bingo_cmd.py
import os
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from urllib.parse import quote

import bigtree
from bigtree.inc.logging import logger
from bigtree.modules.permissions import is_bigtree_operator
from bigtree.modules import bingo as bingo

bot = bigtree.bot

def _api_base() -> Optional[str]:
    """
    Return the public base URL for the web UI, as configured during initialize().
    Falls back to None (no links) if not configured.
    """
    base = getattr(getattr(bigtree, "webapi", None), "public_url", "") or ""
    base = base.strip().rstrip("/")
    return base or None

def _resolve_game_id(maybe_game_id: str, channel_id: int) -> str:
    """If game_id is empty, use active game for this channel."""
    if maybe_game_id:
        return maybe_game_id
    gid = bingo.get_active_for_channel(channel_id)
    return gid or ""

class BingoSetupModal(discord.ui.Modal, title="Create Bingo Game"):
    title_input: discord.ui.TextInput = discord.ui.TextInput(label="Title (header text at top of page)", max_length=100, placeholder="Elfoween Bingo!")
    header_input: discord.ui.TextInput = discord.ui.TextInput(label="Column header (4 letters)", required=False, placeholder="LUCK")
    price_input: discord.ui.TextInput = discord.ui.TextInput(label="Price per card (integer)", placeholder="1000")
    currency_input: discord.ui.TextInput = discord.ui.TextInput(label="Currency name", placeholder="gil")
    max_cards_input: discord.ui.TextInput = discord.ui.TextInput(label="Max cards per player", placeholder="10")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
            max_cards = int(self.max_cards_input.value or "10")
        except Exception:
            return await interaction.response.send_message("Price and Max cards must be integers.", ephemeral=True)

        game = bingo.create_game(
            channel_id=interaction.channel_id,
            title=str(self.title_input.value or "Bingo"),
            price=price,
            currency=str(self.currency_input.value or "gil"),
            max_cards_per_player=max_cards,
            created_by=interaction.user.id,
            header_text=str(self.header_input.value or "BING"),
        )

        embed = discord.Embed(
            title=f"🎲 {game['title']}",
            description=(
                f"**Game ID:** `{game['game_id']}`\n"
                f"**Price:** {game['price']} {game['currency']}\n"
                f"**Max cards/player:** {game['max_cards_per_player']}\n"
                f"**Pot:** {game['pot']} {game['currency']}\n\n"
                f"Buy a card with `/buycard name:<FFXIV name>` (or include `game_id:`)."
            ),
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(
            f"✅ Bingo created. **Game ID:** `{game['game_id']}`",
            ephemeral=True,
        )
        await interaction.channel.send(embed=embed)

class BuyCardsModal(discord.ui.Modal, title="Buy Bingo Cards"):
    name_input: discord.ui.TextInput = discord.ui.TextInput(label="FFXIV Name", placeholder="Your character name")
    qty_input: discord.ui.TextInput = discord.ui.TextInput(label="How many cards? (1–10)", placeholder="1")

    def __init__(self, game_id: str):
        super().__init__()
        self.game_id = game_id

    async def on_submit(self, interaction: discord.Interaction):
        gid = self.game_id or bingo.get_active_for_channel(interaction.channel_id) or ""
        if not gid:
            return await interaction.response.send_message("No active game in this channel.", ephemeral=True)
        try:
            qty = max(1, min(10, int(self.qty_input.value or "1")))
        except Exception:
            return await interaction.response.send_message("Quantity must be an integer from 1 to 10.", ephemeral=True)

        cards, err = bingo.buy_cards(
            gid,
            owner_name=str(self.name_input.value),
            count=qty,
            owner_user_id=interaction.user.id,
        )
        if err:
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)

        base = _api_base()
        msg = f"✅ Bought **{len(cards)}** card(s) for **{self.name_input.value}**.\n• Game: `{gid}`"
        if base:
            msg += f"\n• View all: {base}/bingo/owner?game={gid}&owner={quote(str(self.name_input.value))}"
        await interaction.response.send_message(msg, ephemeral=True)

class BingoMenu(discord.ui.View):
    def __init__(self, game_id: str):
        super().__init__(timeout=120)
        self.game_id = game_id

    @discord.ui.button(label="Buy cards", style=discord.ButtonStyle.primary)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuyCardsModal(self.game_id))

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary)
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.game_id or bingo.get_active_for_channel(interaction.channel_id) or ""
        if not gid:
            return await interaction.response.send_message("No active game.", ephemeral=True)

        st = bingo.get_public_state(gid)
        g = st["game"]
        pays = g.get("payouts", {})
        desc = (
            f"**Pot:** {g['pot']} {g['currency']}  •  **Stage:** {g.get('stage','single')}\n"
            f"Payouts → 1L: {pays.get('single',0)} • 2L: {pays.get('double',0)} • Full: {pays.get('full',0)} {g['currency']}\n"
            f"**Called:** {', '.join(map(str, g['called'])) or '—'}"
        )
        embed = discord.Embed(
            title=f"🎲 {g['title']} — `{gid}`",
            description=desc,
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class BingoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @bot.tree.command(
        name="bingo",
        description="Create/configure a Bingo game",
        guild=discord.Object(id=bigtree.guildid),
    )
    @is_bigtree_operator()
    async def bingo_root(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BingoSetupModal())

    @bot.tree.command(
        name="buycard",
        description="Buy a bingo card (FFXIV name required)",
        guild=discord.Object(id=bigtree.guildid),
    )
    async def buycard(self, interaction: discord.Interaction, name: str, game_id: str = ""):
        gid = _resolve_game_id(game_id, interaction.channel_id)
        if not gid:
            return await interaction.response.send_message(
                "No active game in this channel. Specify `game_id:`.",
                ephemeral=True,
            )

        card, err = bingo.buy_card(gid, owner_name=name, owner_user_id=interaction.user.id)
        if err:
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)

        base = _api_base()
        if base:
            owner_url = f"{base}/bingo/owner?game={gid}&owner={quote(name)}"
            msg = (
                f"✅ Card bought for **{name}**.\n"
                f"• Game: `{gid}`\n"
                f"• Card ID: `{card['card_id']}`\n"
                f"• View all your cards: {owner_url}\n"
                f"• Or get a single-card URL via `/bingo-url`"
            )
        else:
            msg = (
                f"✅ Card bought for **{name}**.\n"
                f"• Game: `{gid}`\n"
                f"• Card ID: `{card['card_id']}`"
            )
        await interaction.response.send_message(msg, ephemeral=True)

    @bot.tree.command(
        name="bingo-url",
        description="Get your web URL for a specific card",
        guild=discord.Object(id=bigtree.guildid),
    )
    async def bingo_url(self, interaction: discord.Interaction, game_id: str, card_id: str):
        base = _api_base()
        if not base:
            return await interaction.response.send_message(
                "Web UI is not configured by the admin (no public URL).",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"{base}/bingo/play?game={game_id}&card={card_id}",
            ephemeral=True,
        )

    @bot.tree.command(
        name="bingo-menu",
        description="Open the Bingo menu",
        guild=discord.Object(id=bigtree.guildid),
    )
    async def bingo_menu(self, interaction: discord.Interaction, game_id: str = ""):
        gid = game_id or bingo.get_active_for_channel(interaction.channel_id) or ""
        if not gid:
            return await interaction.response.send_message("No active game here.", ephemeral=True)
        await interaction.response.send_message("Bingo menu:", view=BingoMenu(gid), ephemeral=True)

    @bot.tree.command(
        name="bingo-stage",
        description="Set the current Bingo stage (single/double/full)",
        guild=discord.Object(id=bigtree.guildid),
    )
    @is_bigtree_operator()
    @app_commands.describe(
        stage="single, double, or full",
        game_id="Override the active game (optional)",
    )
    @app_commands.choices(stage=[
        app_commands.Choice(name="Single line", value="single"),
        app_commands.Choice(name="Double line", value="double"),
        app_commands.Choice(name="Whole card", value="full"),
    ])
    async def bingo_stage(self, interaction: discord.Interaction, stage: app_commands.Choice[str], game_id: str = ""):
        gid = game_id or bingo.get_active_for_channel(interaction.channel_id) or ""
        if not gid:
            return await interaction.response.send_message("No active game here.", ephemeral=True)
        ok, msg = bingo.set_stage(gid, stage.value)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        await interaction.response.send_message(f"✅ Stage set to **{stage.name}**.", ephemeral=True)

    @bot.tree.command(
        name="bingo-owner-url",
        description="Get a web URL showing all cards for an owner (FFXIV name)",
        guild=discord.Object(id=bigtree.guildid),
    )
    async def bingo_owner_url(self, interaction: discord.Interaction, owner_name: str, game_id: str = ""):
        gid = _resolve_game_id(game_id, interaction.channel_id)
        if not gid:
            return await interaction.response.send_message(
                "No active game in this channel. Specify `game_id:`.",
                ephemeral=True,
            )
        base = _api_base()
        if not base:
            return await interaction.response.send_message(
                "Web UI is not configured by the admin (no public URL).",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"{base}/bingo/owner?game={gid}&owner={quote(owner_name)}",
            ephemeral=True,
        )

    @bot.tree.command(
        name="call",
        description="Call a bingo number (1-80)",
        guild=discord.Object(id=bigtree.guildid),
    )
    @is_bigtree_operator()
    async def call_number(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 80], game_id: str = ""):
        gid = _resolve_game_id(game_id, interaction.channel_id)
        if not gid:
            return await interaction.response.send_message(
                "No active game in this channel. Specify `game_id:`.",
                ephemeral=True,
            )
        game, err = bingo.call_number(gid, number)
        if err and err != "Number already called.":
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        await interaction.response.send_message(f"📣 Called **{number}** (game `{gid}`)", ephemeral=True)
        await interaction.channel.send(f"📣 **{number}**")

    @bot.tree.command(
        name="bingo-status",
        description="Show bingo status",
        guild=discord.Object(id=bigtree.guildid),
    )
    async def bingo_status(self, interaction: discord.Interaction, game_id: str = ""):
        gid = _resolve_game_id(game_id, interaction.channel_id)
        if not gid:
            return await interaction.response.send_message(
                "No active game in this channel. Specify `game_id:`.",
                ephemeral=True,
            )
        st = bingo.get_public_state(gid)
        if not st.get("active"):
            return await interaction.response.send_message("Game not active.", ephemeral=True)
        g = st["game"]
        embed = discord.Embed(
            title=f"🎲 {g['title']} — `{gid}`",
            description=(
                f"**Pot:** {g['pot']} {g['currency']}\n"
                f"**Cards:** {st['stats']['cards']} | **Players:** {st['stats']['players']}\n"
                f"**Called:** {', '.join(map(str, g['called'])) or '—'}"
            ),
            colour=discord.Colour.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="bingo-end",
        description="End a bingo game",
        guild=discord.Object(id=bigtree.guildid),
    )
    @is_bigtree_operator()
    async def bingo_end(self, interaction: discord.Interaction, game_id: str = ""):
        gid = _resolve_game_id(game_id, interaction.channel_id)
        if not gid:
            return await interaction.response.send_message(
                "No active game in this channel. Specify `game_id:`.",
                ephemeral=True,
            )
        ok = bingo.end_game(gid)
        if ok:
            await interaction.response.send_message(f"✅ Game `{gid}` ended.", ephemeral=True)
            await interaction.channel.send("⛔ The current Bingo game has been ended.")
        else:
            await interaction.response.send_message("Game not found.", ephemeral=True)

    @bot.tree.command(
        name="bingo-upload-bg",
        description="Upload a background image for a game",
        guild=discord.Object(id=bigtree.guildid),
    )
    @is_bigtree_operator()
    async def bingo_upload_bg(self, interaction: discord.Interaction, image: discord.Attachment, game_id: str = ""):
        gid = _resolve_game_id(game_id, interaction.channel_id)
        if not gid:
            return await interaction.response.send_message(
                "No active game in this channel. Specify `game_id:`.",
                ephemeral=True,
            )
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            ext = os.path.splitext(image.filename)[1].lower() or ".png"
            tmp = os.path.join(td, f"bg{ext}")
            await image.save(tmp)
            ok, msg = bingo.save_background(gid, tmp)
        if not ok:
            return await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        await interaction.response.send_message(f"✅ Background set for game `{gid}`.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BingoCog(bot))
