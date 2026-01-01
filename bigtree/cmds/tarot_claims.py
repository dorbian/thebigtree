# bigtree/cmds/tarot_claims.py
from __future__ import annotations
import math
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from bigtree.modules import tarot as tar

_PAGE_SIZE = 25

def _status_line(card: dict) -> str:
    name = card.get("name") or card.get("card_id") or "Unknown"
    status = card.get("claim_status") or ""
    if status == "done":
        who = card.get("filled_by_name") or "someone"
        return f"DONE - {name} ({who})"
    if status == "claimed":
        who = card.get("claimed_by_name") or "someone"
        return f"CLAIMED - {name} ({who})"
    return f"OPEN - {name}"

def _build_embed(deck_id: str, page: int) -> discord.Embed:
    cards = tar.list_cards(deck_id)
    total = len(cards)
    pages = max(1, math.ceil(total / _PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    start = page * _PAGE_SIZE
    end = start + _PAGE_SIZE
    slice_cards = cards[start:end]

    counts = {"open": 0, "claimed": 0, "done": 0}
    for card in cards:
        status = card.get("claim_status") or ""
        if status == "done":
            counts["done"] += 1
        elif status == "claimed":
            counts["claimed"] += 1
        else:
            counts["open"] += 1

    title = f"Tarot Deck Claims - {deck_id}"
    desc_lines = [f"Page {page + 1}/{pages}", f"OPEN {counts['open']} | CLAIMED {counts['claimed']} | DONE {counts['done']}", ""]
    for card in slice_cards:
        desc_lines.append(_status_line(card))
    description = "\n".join(desc_lines)
    return discord.Embed(title=title, description=description, colour=discord.Colour.dark_teal())

class CardSelect(discord.ui.Select):
    def __init__(self, deck_id: str, page: int):
        self.deck_id = deck_id
        self.page = page
        cards = tar.list_cards(deck_id)
        start = page * _PAGE_SIZE
        end = start + _PAGE_SIZE
        options = []
        for card in cards[start:end]:
            name = card.get("name") or card.get("card_id") or "Unknown"
            status = card.get("claim_status") or "open"
            label = f"{status.upper()} - {name}"
            options.append(discord.SelectOption(label=label[:100], value=card.get("card_id") or name))
        if not options:
            options = [discord.SelectOption(label="No cards", value="__none__")]
        super().__init__(placeholder="Pick a card...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.values:
            await interaction.response.send_message("Pick a card first.", ephemeral=True)
            return
        card_id = self.values[0]
        if card_id == "__none__":
            await interaction.response.send_message("No cards on this page.", ephemeral=True)
            return
        view = self.view
        if isinstance(view, TarotClaimsView):
            view.set_selection(interaction.user.id, card_id)
        await interaction.response.send_message(f"Selected card: `{card_id}`", ephemeral=True)

class TarotClaimsView(discord.ui.View):
    def __init__(self, deck_id: str, claim_limit: int = 2):
        super().__init__(timeout=None)
        self.deck_id = deck_id
        self.page = 0
        self.claim_limit = max(1, int(claim_limit))
        self._selection: dict[int, str] = {}
        self.refresh_items()

    def set_selection(self, user_id: int, card_id: str) -> None:
        self._selection[user_id] = card_id

    def get_selection(self, user_id: int) -> Optional[str]:
        return self._selection.get(user_id)

    def refresh_items(self) -> None:
        self.clear_items()
        self.add_item(CardSelect(self.deck_id, self.page))
        self.add_item(PrevPageButton())
        self.add_item(NextPageButton())
        self.add_item(ClaimButton())
        self.add_item(UnclaimButton())
        self.add_item(DoneButton())
        self.add_item(RefreshButton())

    async def update_message(self, interaction: discord.Interaction) -> None:
        embed = _build_embed(self.deck_id, self.page)
        self.refresh_items()
        await interaction.response.edit_message(embed=embed, view=self)

class PrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Prev", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TarotClaimsView):
            return
        view.page = max(0, view.page - 1)
        await view.update_message(interaction)

class NextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Next", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TarotClaimsView):
            return
        cards = tar.list_cards(view.deck_id)
        pages = max(1, math.ceil(len(cards) / _PAGE_SIZE))
        view.page = min(pages - 1, view.page + 1)
        await view.update_message(interaction)

class ClaimButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Claim", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TarotClaimsView):
            return
        card_id = view.get_selection(interaction.user.id)
        if not card_id:
            await interaction.response.send_message("Select a card first.", ephemeral=True)
            return
        ok, msg = tar.claim_card(view.deck_id, card_id, interaction.user.id, interaction.user.display_name, limit=view.claim_limit)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        embed = _build_embed(view.deck_id, view.page)
        view.refresh_items()
        await interaction.response.edit_message(embed=embed, view=view)

class UnclaimButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Unclaim", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TarotClaimsView):
            return
        card_id = view.get_selection(interaction.user.id)
        if not card_id:
            await interaction.response.send_message("Select a card first.", ephemeral=True)
            return
        force = tar.user_is_priestish(interaction.user)
        ok, msg = tar.unclaim_card(view.deck_id, card_id, interaction.user.id, force=force)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        embed = _build_embed(view.deck_id, view.page)
        view.refresh_items()
        await interaction.response.edit_message(embed=embed, view=view)

class DoneButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Done", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TarotClaimsView):
            return
        card_id = view.get_selection(interaction.user.id)
        if not card_id:
            await interaction.response.send_message("Select a card first.", ephemeral=True)
            return
        force = tar.user_is_priestish(interaction.user)
        ok, msg = tar.mark_card_done(view.deck_id, card_id, interaction.user.id, interaction.user.display_name, force=force)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return
        embed = _build_embed(view.deck_id, view.page)
        view.refresh_items()
        await interaction.response.edit_message(embed=embed, view=view)

class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Refresh", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, TarotClaimsView):
            return
        await view.update_message(interaction)

async def post_claim_board(channel: discord.TextChannel, deck_id: str, claim_limit: int = 2) -> discord.Message:
    view = TarotClaimsView(deck_id, claim_limit=claim_limit)
    embed = _build_embed(deck_id, view.page)
    return await channel.send(embed=embed, view=view)

async def _deck_autocomplete(interaction: discord.Interaction, current: str):
    decks = tar.list_decks()
    choices = []
    for d in decks:
        deck_id = d.get("deck_id") or ""
        if current.lower() in deck_id.lower():
            choices.append(app_commands.Choice(name=deck_id, value=deck_id))
    return choices[:25]

class TarotClaims(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="tarot_template_init", description="Create or refresh the tarot template deck.")
    async def tarot_template_init(self, interaction: discord.Interaction):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return
        deck = tar.ensure_template_deck()
        await interaction.response.send_message(f"Template deck ready: `{deck.get('deck_id')}`", ephemeral=True)

    @app_commands.command(name="tarot_deck_from_template", description="Seed a deck with the standard tarot template.")
    @app_commands.describe(deck_id="Deck id to seed")
    @app_commands.autocomplete(deck_id=_deck_autocomplete)
    async def tarot_deck_from_template(self, interaction: discord.Interaction, deck_id: str):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return
        deck_id = (deck_id or "").strip()
        if not deck_id:
            await interaction.response.send_message("Deck id is required.", ephemeral=True)
            return
        tar.seed_deck_from_template(deck_id)
        await interaction.response.send_message(f"Deck `{deck_id}` seeded from template.", ephemeral=True)

    @app_commands.command(name="tarot_claims_post", description="Post a tarot deck claim board in a channel.")
    @app_commands.describe(deck_id="Deck to staff with artists", channel="Channel to post the claim board", claim_limit="Max claims per user (default 2)")
    @app_commands.autocomplete(deck_id=_deck_autocomplete)
    async def tarot_claims_post(
        self,
        interaction: discord.Interaction,
        deck_id: str,
        channel: Optional[discord.TextChannel] = None,
        claim_limit: int = 2,
    ):
        if not tar.user_is_priestish(interaction.user):
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return
        deck_id = (deck_id or "").strip()
        if not deck_id:
            await interaction.response.send_message("Deck id is required.", ephemeral=True)
            return
        if not tar.get_deck(deck_id):
            tar.seed_deck_from_template(deck_id)
        dest = channel or interaction.channel
        if not isinstance(dest, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True)
            return
        view = TarotClaimsView(deck_id, claim_limit=claim_limit)
        embed = _build_embed(deck_id, view.page)
        await dest.send(embed=embed, view=view)
        await interaction.response.send_message(f"Claim board posted in {dest.mention}.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TarotClaims(bot))
