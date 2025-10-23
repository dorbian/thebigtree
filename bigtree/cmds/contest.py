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
    "2) Attach an image with your entry\n"
    "3) Keep it cozy (server rules apply)\n"
    "4) Captions allowed if enabled\n"
    "5) Voting uses :TreeCone: reactions\n"
    "6) Most :TreeCone: by the deadline wins"
)

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

def _ensure_global_contestid_container():
    if bigtree is None:
        return
    if not hasattr(bigtree, "contestid") or bigtree.contestid is None:
        bigtree.contestid = []  # list for compatibility

def _set_channel_enabled(channel_id: int, enabled: bool) -> None:
    state = _load_channel_state(channel_id)
    state["enabled"] = bool(enabled)
    _save_channel_state(channel_id, state)
    if bigtree is None:
        return
    _ensure_global_contestid_container()
    try:
        cid_list: list = bigtree.contestid
        if enabled and channel_id not in cid_list:
            cid_list.append(channel_id)
        if not enabled and channel_id in cid_list:
            cid_list.remove(channel_id)
    except Exception:
        pass

def is_elfmin(user: discord.abc.User | discord.Member) -> bool:
    owner_ids = set(_settings_get("PERMISSIONS", "OWNERS", []) or [])
    admin_role_ids = set(_settings_get("PERMISSIONS", "ADMINS", []) or [])
    try:
        if int(getattr(user, "id", 0)) in owner_ids:
            return True
        if hasattr(user, "roles"):
            for r in user.roles:  # type: ignore[attr-defined]
                if getattr(r, "id", None) in admin_role_ids:
                    return True
    except Exception:
        pass
    if isinstance(user, discord.Member):
        if user.guild and user.guild.owner_id == user.id:
            return True
    return False

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

def _resolve_vote_emoji(guild: Optional[discord.Guild]):
    desired = _settings_get("CONTEST", "VOTE_EMOJI", ":TreeCone:") or ":TreeCone:"
    if isinstance(desired, str):
        name = desired.strip(":")
        if guild:
            for e in getattr(guild, "emojis", []):
                if str(e.name) == name:
                    return e
        if name.lower() in {"treecone","tree_cone"}:
            return "👍"
        if len(desired) <= 3 and not desired.startswith(":"):
            return desired
        return "👍"
    return "👍"

class ContestSetupModal(discord.ui.Modal, title="Create a Contest"):
    contest_title = discord.ui.TextInput(label="Title", max_length=100, placeholder="Elfoween Costume Contest")
    description = discord.ui.TextInput(label="Short description", style=discord.TextStyle.paragraph, max_length=400, placeholder="Post your entry as an attachment. Most :TreeCone: wins!")
    rules = discord.ui.TextInput(label="Rules (leave empty for defaults)", style=discord.TextStyle.paragraph, required=False)
    deadline = discord.ui.TextInput(label="Deadline (YYYY-MM-DD HH:MM, server time)", required=False, placeholder="2025-10-31 23:59")
    allow_captions = discord.ui.TextInput(label="Allow caption button? (yes/no)", required=False, placeholder="yes")

    def __init__(self, interaction: discord.Interaction, cog: "ContestCog"):
        super().__init__()
        self._interaction = interaction
        self._cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        title = str(self.contest_title.value).strip()
        desc = str(self.description.value).strip()
        rules_text = (str(self.rules.value).strip() if self.rules.value else "") or DEFAULT_RULES
        deadline_str = str(self.deadline.value).strip() if self.deadline.value else ""
        allow_captions = (str(self.allow_captions.value).strip().lower() or "yes") in {"y","yes","true","1"}

        dl_dt: Optional[datetime] = None
        if deadline_str:
            from datetime import datetime as _dt
            try:
                dl_dt = _dt.strptime(deadline_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    dl_dt = _dt.strptime(deadline_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    pass

        vote_emoji = _resolve_vote_emoji(interaction.guild)

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

        view = discord.ui.View(timeout=None)
        msg = await interaction.channel.send(embed=embed, view=view)  # type: ignore
        try:
            await msg.pin()
        except Exception:
            pass

        if allow_captions:
            add_caption_button_to_view(view, msg.id, interaction.user.id)

        _set_channel_enabled(interaction.channel_id, True)  # type: ignore

        state = _load_channel_state(interaction.channel_id)  # type: ignore
        state.update({
            "message_id": msg.id,
            "owner_id": interaction.user.id,
            "title": title,
            "description": desc,
            "rules": rules_text,
            "deadline": dl_dt.isoformat() if dl_dt else None,
            "allow_captions": allow_captions,
            "vote_emoji": str(vote_emoji),
            "enabled": True,
        })
        _save_channel_state(interaction.channel_id, state)  # type: ignore

        await interaction.response.send_message("Contest created! I’ve posted the rules, pinned them, and enabled contest processing for this channel. ✅", ephemeral=True)

class CaptionModal(discord.ui.Modal, title="Add a Caption"):
    caption = discord.ui.TextInput(label="Your caption", style=discord.TextStyle.paragraph, max_length=300)

    def __init__(self, target_message_id: int, owner_id: int):
        super().__init__()
        self.target_message_id = target_message_id
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id and not is_elfmin(interaction.user):
            await interaction.response.send_message("Only the entry owner or staff can add a caption.", ephemeral=True)
            return
        try:
            channel: discord.TextChannel = interaction.channel  # type: ignore
            msg = await channel.fetch_message(self.target_message_id)  # may raise if deleted
        except Exception:
            await interaction.response.send_message("Original contest message not found (it might have been deleted).", ephemeral=True)
            return

        content = f"**Caption by {interaction.user.mention}:** {self.caption.value}"
        try:
            thread = msg.thread or await msg.create_thread(name="Contest captions", auto_archive_duration=10080)
            await thread.send(content)
        except Exception:
            await interaction.channel.send(content, reference=msg)  # type: ignore

        await interaction.response.send_message("Caption added ✔️", ephemeral=True)

def add_caption_button_to_view(view: discord.ui.View, target_message_id: int, owner_id: int) -> None:
    class _Btn(discord.ui.Button):
        def __init__(self):
            super().__init__(style=discord.ButtonStyle.primary, label="✏️ Add Caption")
        async def callback(self, interaction: discord.Interaction):
            await interaction.response.send_modal(CaptionModal(target_message_id, owner_id))
    view.add_item(_Btn())

class ContestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="contest", description="Create a contest in this channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def contest_slash(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ContestSetupModal(interaction, self))

    @app_commands.command(name="contest_stop", description="Disable contest processing in this channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def contest_stop(self, interaction: discord.Interaction):
        _set_channel_enabled(interaction.channel_id, False)  # type: ignore
        await interaction.response.send_message("Contest processing disabled for this channel. 📴", ephemeral=True)

    @contest_slash.error
    @contest_stop.error
    async def contest_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("You need **Manage Server** to run this.", ephemeral=True)
            return
        await interaction.response.send_message(f"Something went wrong: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ContestCog(bot))

