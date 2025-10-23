from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import json
import discord
from discord import app_commands
from discord.ext import commands

try:
    import bigtree
except Exception:
    bigtree = None

DEFAULT_RULES = (
    "1) One entry per person\n"
    "2) Attach an image or video with your entry\n"
    "3) Keep it cozy (server rules apply)\n"
    "4) Voting uses :TreeCone: reactions\n"
    "5) Most :TreeCone: by the deadline wins"
)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}

def _settings_get(section: str, key: str, default=None):
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(section, {}).get(key, default)
    except Exception:
        pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        return cfg.get(section, {}).get(key, default)
    except Exception:
        pass
    return default

def _data_dir() -> Path:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", ".")
    p = Path(base) / "contest"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _channel_db_path(channel_id: int) -> Path:
    return _data_dir() / f"{channel_id}.json"

def _load_channel_state(channel_id: int) -> Dict[str, Any]:
    p = _channel_db_path(channel_id)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return {}
    return {}

def _save_channel_state(channel_id: int, data: Dict[str, Any]) -> None:
    p = _channel_db_path(channel_id)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")

def _ensure_global_contestid_container():
    if bigtree is None:
        return
    if not hasattr(bigtree, "contestid") or bigtree.contestid is None:
        bigtree.contestid = []

def _set_channel_enabled(channel_id: int, enabled: bool) -> None:
    st = _load_channel_state(channel_id)
    st["enabled"] = bool(enabled)
    _save_channel_state(channel_id, st)
    if bigtree is None:
        return
    _ensure_global_contestid_container()
    lst: list = bigtree.contestid  # type: ignore
    if enabled and channel_id not in lst:
        lst.append(channel_id)
    if not enabled and channel_id in lst:
        lst.remove(channel_id)

def _resolve_vote_emoji(guild: Optional[discord.Guild]):
    desired = _settings_get("CONTEST", "VOTE_EMOJI", ":TreeCone:") or ":TreeCone:"
    if isinstance(desired, str):
        name = desired.strip(":")
        if guild:
            for e in getattr(guild, "emojis", []):
                if str(e.name) == name:
                    return e
        # Fallbacks
        if name.lower() in {"treecone","tree_cone"}:
            return "👍"
        if len(desired) <= 3 and not desired.startswith(":"):
            return desired
        return "👍"
    return "👍"

class ContestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="contest", description="Create a contest in this channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def contest_slash(self, interaction: discord.Interaction):
        class ContestSetupModal(discord.ui.Modal, title="Create a Contest"):
            contest_title = discord.ui.TextInput(label="Title", max_length=100, placeholder="Elfoween Costume Contest")
            description = discord.ui.TextInput(label="Short description", style=discord.TextStyle.paragraph, max_length=400, placeholder="Post your entry as an attachment. Most :TreeCone: wins!")
            rules = discord.ui.TextInput(label="Rules (leave empty for defaults)", style=discord.TextStyle.paragraph, required=False)
            deadline = discord.ui.TextInput(label="Deadline (YYYY-MM-DD HH:MM, server time)", required=False, placeholder="2025-10-31 23:59")

            async def on_submit(self, inner: discord.Interaction) -> None:
                title = str(self.contest_title.value).strip()
                desc = str(self.description.value).strip()
                rules_text = (str(self.rules.value).strip() if self.rules.value else "") or DEFAULT_RULES
                deadline_str = str(self.deadline.value).strip() if self.deadline.value else ""

                dl_dt = None
                if deadline_str:
                    from datetime import datetime as _dt
                    try:
                        dl_dt = _dt.strptime(deadline_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                    except ValueError:
                        try:
                            dl_dt = _dt.strptime(deadline_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        except Exception:
                            pass

                vote_emoji = _resolve_vote_emoji(inner.guild)

                embed = discord.Embed(
                    title=f"🎉 {title}",
                    description=desc,
                    color=discord.Color.blurple(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="Rules", value=rules_text, inline=False)
                if dl_dt:
                    embed.add_field(name="Deadline", value=f"{dl_dt:%Y-%m-%d %H:%M} UTC", inline=False)
                embed.add_field(name="Voting", value=f"React with {vote_emoji} on entries you like.", inline=False)

                msg = await inner.channel.send(embed=embed)  # type: ignore
                try:
                    await msg.pin()
                except Exception:
                    pass

                state = _load_channel_state(inner.channel_id)  # type: ignore
                state.update({
                    "message_id": msg.id,
                    "owner_id": inner.user.id,
                    "title": title,
                    "description": desc,
                    "rules": rules_text,
                    "deadline": dl_dt.isoformat() if dl_dt else None,
                    "vote_emoji": str(vote_emoji),
                    "enabled": True,
                })
                _save_channel_state(inner.channel_id, state)  # type: ignore
                _set_channel_enabled(inner.channel_id, True)  # type: ignore

                await inner.response.send_message("Contest created, rules posted and pinned. Voting emoji configured. ✅", ephemeral=True)

        await interaction.response.send_modal(ContestSetupModal())

    @app_commands.command(name="contest_stop", description="Disable contest processing in this channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def contest_stop(self, interaction: discord.Interaction):
        _set_channel_enabled(interaction.channel_id, False)  # type: ignore
        await interaction.response.send_message("Contest processing disabled for this channel. 📴", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        ch = message.channel
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return
        channel_id = ch.id if isinstance(ch, discord.TextChannel) else ch.parent_id
        if channel_id is None:
            return
        state = _load_channel_state(channel_id)
        if not state.get("enabled"):
            return
        if not message.attachments:
            try:
                await message.delete()
            except Exception:
                pass
            return

        # pick first media
        att = message.attachments[0]
        name_lower = (att.filename or "").lower()
        ext = "." + name_lower.split(".")[-1] if "." in name_lower else ""

        vote_emoji = state.get("vote_emoji") or _resolve_vote_emoji(message.guild)

        # Anonymous embed (no author)
        embed = discord.Embed(
            description=(message.content or "").strip(),
            color=discord.Color.dark_teal(),
            timestamp=datetime.now(timezone.utc),  # keep timestamp for ordering; remove if you prefer
        )
        if ext in IMAGE_EXTS:
            embed.set_image(url=att.url)
        else:
            embed.add_field(name="Attachment", value=f"[{att.filename}]({att.url})", inline=False)

        dest = ch if isinstance(ch, discord.TextChannel) else ch.parent
        try:
            posted = await dest.send(embed=embed)  # type: ignore
            try:
                await posted.add_reaction(vote_emoji)
            except Exception:
                try:
                    await posted.add_reaction("👍")
                except Exception:
                    pass
        finally:
            try:
                await message.delete()
            except Exception:
                pass

    @contest_slash.error
    @contest_stop.error
    async def contest_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You need **Manage Server** to run this.", ephemeral=True)
            return
        await interaction.response.send_message(f"Something went wrong: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ContestCog(bot))
