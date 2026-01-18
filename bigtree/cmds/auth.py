# bigtree/cmds/auth.py
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
import bigtree
from bigtree.inc.database import get_database
from bigtree.inc import web_tokens
from bigtree.inc.logging import auth_logger

bot = bigtree.bot


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
    raw = _settings_get("BOT", "auth_role_scopes", None)
    if raw is None:
        raw = _load_auth_roles_file()
        if raw is None:
            return {}, False
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            raw = _load_auth_roles_file()
            if raw is None:
                return {}, True
        try:
            raw = json.loads(raw)
        except Exception:
            raw = _load_auth_roles_file()
            if raw is None:
                return {}, True
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


class AuthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
                db = get_database()
                db.upsert_discord_user(
                    discord_id=member.id,
                    username=getattr(member, "name", None),
                    display_name=display_name,
                    avatar_url=avatar_url,
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
