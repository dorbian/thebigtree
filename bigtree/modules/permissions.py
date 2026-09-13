# bigtree/modules/permissions.py
from __future__ import annotations

import discord
from discord import app_commands

from bigtree.inc import access_control


def _member_from_interaction(interaction: discord.Interaction):
    member = interaction.user
    if isinstance(member, discord.Member):
        return member
    guild = getattr(interaction, "guild", None)
    if guild and getattr(member, "id", None):
        try:
            return guild.get_member(member.id) or member
        except Exception:
            pass
    return member


def requires_capability(
    capability: str,
    *,
    resource_type: str = "",
    resource_id_getter=None,
):
    """Discord slash-command check backed by BigTree Identity & Access.

    Existing Discord administrator/operator/Elfministrator/Priest behaviour is
    preserved by access_control's compatibility bridge while commands migrate
    from broad historical checks to explicit capabilities.
    """
    required = access_control.normalize_capability(capability)

    async def predicate(interaction: discord.Interaction) -> bool:
        member = _member_from_interaction(interaction)
        resource_id = ""
        if callable(resource_id_getter):
            try:
                resource_id = resource_id_getter(interaction)
            except Exception:
                resource_id = ""
        decision = access_control.evaluate_discord_member(
            member,
            required,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if decision.allowed:
            return True
        raise app_commands.CheckFailure(
            f"You don’t have permission to use this command ({required})."
        )

    return app_commands.check(predicate)


def is_bigtree_operator():
    """Compatibility wrapper for commands not yet assigned a precise capability."""
    return requires_capability("legacy.operator")


def is_elfministrator():
    """Compatibility wrapper for commands not yet assigned a precise capability."""
    return requires_capability("legacy.elfministrator")
