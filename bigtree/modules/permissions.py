# bigtree/permissions.py
import bigtree
import discord
from discord import app_commands

# Configure these somewhere at startup (see below)
#   bigtree.operator_role_ids = [1234, 5678]
#   bigtree.operator_user_ids = [1111, 2222]

def is_bigtree_operator():
    """Slash command check: allow Admins, Manage Guild, specific roles, or user IDs."""
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user

        # Admins and Manage Server always allowed
        perms = getattr(member, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True

        # Role allow-list
        role_ids = set(getattr(bigtree, "operator_role_ids", []) or [])
        if role_ids:
            if any(getattr(r, "id", 0) in role_ids for r in getattr(member, "roles", [])):
                return True

        # User allow-list
        user_ids = set(getattr(bigtree, "operator_user_ids", []) or [])
        if user_ids and member.id in user_ids:
            return True

        # No match -> fail
        raise app_commands.CheckFailure("You don’t have permission to use this command.")
    return app_commands.check(predicate)

def is_elfministrator():
    """Slash command check: allow admins or configured elfministrator roles/users."""
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user

        # Admins always allowed
        perms = getattr(member, "guild_permissions", None)
        if perms and perms.administrator:
            return True

        # Configured role IDs (settings or globals)
        role_ids = set(getattr(bigtree, "elfministrator_role_ids", []) or [])
        try:
            settings = getattr(bigtree, "settings", None)
            if settings:
                raw = settings.get("BOT.elfministrator_role_ids", [], cast="json") or []
                if isinstance(raw, (str, int)):
                    raw = [raw]
                for r in raw:
                    try:
                        role_ids.add(int(r))
                    except Exception:
                        pass
        except Exception:
            pass
        if role_ids:
            if any(getattr(r, "id", 0) in role_ids for r in getattr(member, "roles", [])):
                return True

        # Configured user IDs (optional)
        user_ids = set(getattr(bigtree, "elfministrator_user_ids", []) or [])
        if user_ids and member.id in user_ids:
            return True

        # Fallback by role name
        for r in getattr(member, "roles", []):
            if str(getattr(r, "name", "")).strip().lower() == "elfministrator":
                return True

        raise app_commands.CheckFailure("You do not have permission to use this command.")
    return app_commands.check(predicate)
