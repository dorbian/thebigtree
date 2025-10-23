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
