# bigtree/cmds/contest.py
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional  # <-- Python 3.9 friendly
import bigtree
# bigtree/cmds/contest.py
from discord import ui, Interaction

# -----------------------------
# Contest submission caption UI
# -----------------------------
class CaptionModal(ui.Modal, title="Add Caption"):
    caption = ui.TextInput(
        label="Your caption or comment",
        style=discord.TextStyle.paragraph,
        placeholder="Write something creative to go with your image...",
        max_length=400,
        required=True
    )

    def __init__(self, target_message_id: int, owner_id: int):
        super().__init__()
        self.target_message_id = target_message_id
        self.owner_id = owner_id

    async def on_submit(self, interaction: Interaction):
        try:
            channel = interaction.channel
            msg = await channel.fetch_message(self.target_message_id)
            new_embed = discord.Embed(
                title=f"{interaction.user.display_name}'s entry",
                description=self.caption.value,
                color=discord.Color.blurple(),
            )
            if msg.attachments:
                new_embed.set_image(url=msg.attachments[0].url)
            await msg.edit(embed=new_embed)
            await interaction.response.send_message("✅ Caption added!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to add caption: {e}", ephemeral=True)

# -----------------------------
# Function called from commands.py
# -----------------------------
def add_caption_button_to_view(view: discord.ui.View, target_message_id: int, owner_id: int):
    """
    Adds an "Add Caption" button to the contest submission view.
    Called from modules/commands.py after posting an image.
    """

    class AddCaptionButton(ui.Button):
        def __init__(self):
            super().__init__(label="✏️ Add Caption", style=discord.ButtonStyle.primary)

        async def callback(self, interaction: Interaction):
            # Only the owner or admins can use the button
            if interaction.user.id != owner_id and not interaction.user.guild_permissions.manage_messages:
                await interaction.response.send_message("You can't modify someone else's entry.", ephemeral=True)
                return
            await interaction.response.send_modal(CaptionModal(target_message_id, owner_id))

    # Prevent multiple caption buttons stacking
    for c in view.children:
        if isinstance(c, ui.Button) and c.label == "✏️ Add Caption":
            return view

    view.add_item(AddCaptionButton())
    return view


# ---- compat: modules/commands.py imports this symbol
def add_caption_button_to_view(view: discord.ui.View) -> None:
    """
    Compatibility shim. If your old code used this to augment a View,
    implement the real button here. For now, it's a no-op so imports don't fail.
    """
    return None

def _read_ids_from_settings(key: str) -> set[int]:
    ids: set[int] = set()
    s = getattr(bigtree, "settings", None)
    if s is not None:
        # Prefer JSON list: [123, 456]; also accept comma-separated "123,456"
        raw = s.get(f"BOT.{key}", [], cast="json")
        if isinstance(raw, list):
            ids = {int(x) for x in raw if str(x).isdigit()}
        elif isinstance(raw, str):
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            ids = {int(p) for p in parts if p.isdigit()}
    else:
        # Legacy fallback
        cfg = getattr(bigtree, "config", None)
        if cfg and getattr(cfg, "config", None):
            raw = (cfg.config.get("BOT", {}) or {}).get(key, [])
            if isinstance(raw, list):
                ids = {int(x) for x in raw if str(x).isdigit()}
            elif isinstance(raw, str):
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                ids = {int(p) for p in parts if p.isdigit()}
    return ids

def is_elfmin(user: discord.abc.User) -> bool:
    """Return True if the user has priest or elfministrator roles (or admin)."""
    # If it's not a Member (e.g., DM), we can't check roles.
    if not isinstance(user, discord.Member):
        return False
    role_ids = _read_ids_from_settings("elfministrator_role_ids") | _read_ids_from_settings("priest_role_ids")
    user_role_ids = {r.id for r in getattr(user, "roles", [])}
    return bool(user_role_ids & role_ids) or user.guild_permissions.administrator

class ContestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="contest", description="Contest utilities and info")
    @app_commands.describe(
        action="What to do (status/start/stop/list)",
        target="Optional target or id"
    )
    async def contest_slash(
        self,
        interaction: discord.Interaction,
        action: str = "status",
        target: Optional[str] = None,  # <-- Optional[str] instead of str | None
    ):
        # Guarded actions
        if not is_elfmin(interaction.user) and action in {"start", "stop"}:
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return

        # Replace with your real logic as needed
        if action == "status":
            await interaction.response.send_message("Contest status: 🌲 ready.", ephemeral=True)
        elif action == "list":
            await interaction.response.send_message("No contests listed (placeholder).", ephemeral=True)
        elif action == "start":
            await interaction.response.send_message("Contest started (placeholder).", ephemeral=True)
        elif action == "stop":
            await interaction.response.send_message("Contest stopped (placeholder).", ephemeral=True)
        else:
            await interaction.response.send_message(f"Unknown action: {action}", ephemeral=True)

async def setup(bot: commands.Bot):
    # Prevent duplicate registration if this extension reloads
    existing = bot.tree.get_command("contest")
    if existing:
        bot.tree.remove_command("contest", type=discord.AppCommandType.chat_input)
    await bot.add_cog(ContestCog(bot))
