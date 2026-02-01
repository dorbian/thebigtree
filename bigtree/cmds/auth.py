# bigtree/cmds/auth.py
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.parse
import discord
from discord import app_commands
from discord.ext import commands
import bigtree
from bigtree.inc import web_tokens
from bigtree.inc.database import get_database
from bigtree.inc.logging import auth_logger

bot = bigtree.bot

OVERLAY_LOGIN_CHANNEL_ID = 1467111868391751700
OVERLAY_PANEL_STATE_FILE = "overlay_login_panel.json"
OVERLAY_PANEL_MESSAGE = (
    "Click the button below to log into the overlay. "
    "It will set a secure login cookie in your browser."
)


def _settings_get(section: str, key: str, default=None):
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            sec = bigtree.settings.section(section)
            if isinstance(sec, dict):
                return sec.get(key, default)
            return bigtree.settings.get(f"{section}.{key}", default)
    except Exception:
        pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        return cfg.get(section, {}).get(key, default)
    except Exception:
        pass
    return default


def _is_elfministrator(member: discord.Member) -> bool:
    role_ids = _settings_get("BOT", "elfministrator_role_ids", []) or []
    allowed = set()
    if isinstance(role_ids, (str, int)):
        role_ids = [role_ids]
    for r in role_ids:
        try:
            allowed.add(int(r))
        except Exception:
            continue
    roles = {r.id for r in getattr(member, "roles", [])}
    if allowed and (allowed & roles):
        return True
    # Fallback: allow by role name if IDs not configured
    for r in getattr(member, "roles", []):
        if str(r.name or "").strip().lower() == "elfministrator":
            return True
    return False


def _parse_scope_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        val = raw.strip()
        if not val:
            return []
        if val.startswith("[") or val.startswith("{"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
                if isinstance(parsed, dict):
                    return [str(x).strip() for x in parsed.keys() if str(x).strip()]
            except Exception:
                pass
        return [x.strip() for x in val.split(",") if x.strip()]
    return []


def _get_role_scope_map() -> tuple[dict[int, list[str]], bool]:
    # Highest priority: config setting override
    raw = _settings_get("BOT", "auth_role_scopes", None)

    # Next: DB (source of truth)
    if raw is None:
        try:
            db = get_database()
            raw = db.get_auth_roles()
        except Exception:
            raw = None

    # Finally: legacy file fallback
    if raw is None:
        raw = _load_auth_roles_file()
        if raw is None:
            return {}, False

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            try:
                db = get_database()
                raw = db.get_auth_roles()
            except Exception:
                raw = _load_auth_roles_file()
        try:
            raw = json.loads(raw)
        except Exception:
            pass

    if not isinstance(raw, dict):
        raw = _load_auth_roles_file()
        if raw is None:
            return {}, True

    mapping: dict[int, list[str]] = {}
    for rid, scopes in raw.items():
        try:
            role_id = int(rid)
        except Exception:
            continue
        scope_list = _parse_scope_list(scopes)
        if "*" in scope_list:
            scope_list = ["*"]
        mapping[role_id] = scope_list
    return mapping, True

def _auth_roles_path() -> Path | None:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", None)
    if not base:
        return None
    return Path(base) / "auth_roles.json"


def _load_auth_roles_file() -> dict | None:
    path = _auth_roles_path()
    if not path or not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except Exception:
        return None
    if isinstance(data, dict) and "role_scopes" in data and isinstance(data["role_scopes"], dict):
        return data["role_scopes"]
    if isinstance(data, dict):
        return data
    return None


def _build_overlay_url(token: str) -> str:
    if not token:
        return ""
    base = _settings_get("WEB", "base_url", "http://localhost:8443") or "http://localhost:8443"
    base = base.rstrip("/")
    return f"{base}/overlay?token={token}"


def _build_overlay_cookie_url(token: str, redirect: str = "/overlay") -> str:
    if not token:
        return ""
    base = _settings_get("WEB", "base_url", "http://localhost:8443") or "http://localhost:8443"
    base = base.rstrip("/")
    if not redirect.startswith("/"):
        redirect = "/overlay"
    redirect_q = urllib.parse.quote(redirect, safe="/")
    return f"{base}/auth/discord?token={token}&redirect={redirect_q}"


def _get_scopes_for_member(member: discord.Member) -> list[str]:
    role_map, configured = _get_role_scope_map()
    roles = {r.id for r in getattr(member, "roles", [])}
    if configured:
        scopes = set()
        for role_id in roles:
            for scope in role_map.get(role_id, []):
                if scope:
                    scopes.add(str(scope))
        if "*" in scopes:
            return ["*"]
        return sorted(scopes)
    if _is_elfministrator(member):
        return ["*"]
    return []


def _panel_state_path() -> Path | None:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", None)
    if not base:
        return None
    return Path(base) / OVERLAY_PANEL_STATE_FILE


def _load_panel_state() -> dict:
    path = _panel_state_path()
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


def _save_panel_state(channel_id: int, message_id: int) -> None:
    path = _panel_state_path()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"channel_id": str(channel_id), "message_id": str(message_id)}
    path.write_text(json.dumps(payload, indent=2), "utf-8")


class _OverlayLoginView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Login to overlay",
        style=discord.ButtonStyle.primary,
        custom_id="bigtree:overlay_login",
    )
    async def overlay_login(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("This button only works inside the server.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        scopes = _get_scopes_for_member(member) if member else []
        if not member or not scopes:
            auth_logger.warning("[auth] overlay-login denied user=%s", getattr(interaction.user, "id", "unknown"))
            await interaction.response.send_message("Not allowed.", ephemeral=True)
            return
        display_name = member.display_name or member.name
        avatar_url = getattr(member, "display_avatar", None)
        avatar_url = getattr(avatar_url, "url", None)
        doc = web_tokens.issue_token(
            user_id=member.id,
            scopes=scopes,
            user_name=display_name,
            user_icon=avatar_url,
        )
        try:
            get_database().upsert_discord_user(
                member.id,
                name=getattr(member, "name", None),
                display_name=display_name,
                global_name=getattr(member, "global_name", None),
                metadata={"scopes": scopes},
            )
        except Exception:
            pass
        auth_logger.info(
            "[auth] overlay-login issued user=%s scopes=%s",
            member.id,
            ",".join(doc.get("scopes") or []),
        )
        expires_at = datetime.fromtimestamp(doc["expires_at"], tz=timezone.utc)
        overlay_url = _build_overlay_cookie_url(doc["token"])
        view = discord.ui.View()
        if overlay_url:
            view.add_item(discord.ui.Button(label="Open overlay (login)", style=discord.ButtonStyle.link, url=overlay_url))
        await interaction.response.send_message(
            f"Open the overlay to complete login. Token expires: {expires_at.isoformat()}",
            view=view,
            ephemeral=True,
        )


class AuthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not getattr(bot, "_overlay_login_view_added", False):
            bot.add_view(_OverlayLoginView())
            bot._overlay_login_view_added = True

    @commands.Cog.listener()
    async def on_ready(self):
        if getattr(self.bot, "_overlay_login_panel_ready", False):
            return
        self.bot._overlay_login_panel_ready = True
        await self._ensure_overlay_panel()

    async def _ensure_overlay_panel(self) -> None:
        channel_id = int(OVERLAY_LOGIN_CHANNEL_ID or 0)
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        state = _load_panel_state()
        message = None
        if state and str(state.get("channel_id")) == str(channel_id):
            try:
                msg_id = int(state.get("message_id") or 0)
            except Exception:
                msg_id = 0
            if msg_id:
                try:
                    message = await channel.fetch_message(msg_id)
                except Exception:
                    message = None

        view = _OverlayLoginView()
        if message:
            try:
                await message.edit(content=OVERLAY_PANEL_MESSAGE, view=view)
                return
            except Exception:
                pass
        try:
            message = await channel.send(content=OVERLAY_PANEL_MESSAGE, view=view)
            _save_panel_state(channel_id, message.id)
        except Exception:
            return

    class _TokenView(discord.ui.View):
        def __init__(self, token: str, overlay_url: str):
            super().__init__(timeout=300)
            self.token = token
            if overlay_url:
                self.add_item(discord.ui.Button(label="Open overlay", style=discord.ButtonStyle.link, url=overlay_url))

        @discord.ui.button(label="Copy token", style=discord.ButtonStyle.secondary)
        async def copy_token(self, interaction: discord.Interaction, _button: discord.ui.Button):
            await interaction.response.send_message(f"```{self.token}```", ephemeral=True)

    @app_commands.command(
        name="auth",
        description="Generate a 24h web API token for the overlay client."
    )
    async def auth(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            member = interaction.user
            if not isinstance(member, discord.Member):
                member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
            scopes = _get_scopes_for_member(member) if member else []
            if not member or not scopes:
                auth_logger.warning("[auth] denied user=%s", getattr(interaction.user, "id", "unknown"))
                await interaction.followup.send("Not allowed.", ephemeral=True)
                return
            display_name = member.display_name or member.name
            avatar_url = getattr(member, "display_avatar", None)
            avatar_url = getattr(avatar_url, "url", None)
            doc = web_tokens.issue_token(
                user_id=member.id,
                scopes=scopes,
                user_name=display_name,
                user_icon=avatar_url,
            )
            try:
                get_database().upsert_discord_user(
                    member.id,
                    name=getattr(member, "name", None),
                    display_name=display_name,
                    global_name=getattr(member, "global_name", None),
                    metadata={"scopes": scopes},
                )
            except Exception:
                pass
            auth_logger.info(
                "[auth] issued user=%s scopes=%s",
                member.id,
                ",".join(doc.get("scopes") or []),
            )
            expires_at = datetime.fromtimestamp(doc["expires_at"], tz=timezone.utc)
            overlay_url = _build_overlay_url(doc["token"])
            view = self._TokenView(doc["token"], overlay_url)
            await interaction.followup.send(
                f"Here is your 24h web token (keep it private). Copy the password below or click the overlay link to auto-login.\n"
                f"`{doc['token']}`\nExpires: {expires_at.isoformat()}",
                view=view,
                ephemeral=True,
            )
        except Exception as exc:
            auth_logger.exception("[auth] error")
            await interaction.followup.send(f"Auth failed: {exc}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuthCog(bot))
