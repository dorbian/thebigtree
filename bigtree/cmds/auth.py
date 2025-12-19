# bigtree/cmds/auth.py
from __future__ import annotations
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands
import bigtree
from bigtree.inc import web_tokens

bot = bigtree.bot


def _is_elfministrator(member: discord.Member) -> bool:
    cfg = bigtree.config.config.get("BOT", {}) if hasattr(bigtree, "config") else {}
    role_ids = cfg.get("elfministrator_role_ids", []) or []
    try:
        allowed = {int(r) for r in role_ids}
    except Exception:
        allowed = set()
        for r in role_ids:
            try:
                allowed.add(int(r))
            except Exception:
                continue
    roles = {r.id for r in getattr(member, "roles", [])}
    return bool(allowed & roles)


class AuthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @bot.tree.command(
        name="auth",
        description="Generate a 24h web API token for the overlay client.",
        guild=discord.Object(id=bigtree.guildid),
    )
    async def auth(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        if not member or not _is_elfministrator(member):
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return
        doc = web_tokens.issue_token(user_id=member.id)
        expires_at = datetime.fromtimestamp(doc["expires_at"], tz=timezone.utc)
        await interaction.response.send_message(
            f"Here is your 24h web token (keep it private):\n`{doc['token']}`\n"
            f"Expires: {expires_at.isoformat()}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AuthCog(bot))
