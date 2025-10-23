# bigtree/cmds/permissions_cmd.py
# Admin-only /permissions manager for BigTree.
# - No decorator-based group (prevents stale signatures)
# - Builds a fresh app_commands.Group at runtime
# - Persists to bigtree.workingdir/permissions.json
# - Keeps bigtree.operator_role_ids / operator_user_ids in sync
# - Registers after ready; purges stale guild/global copies before re-adding

import os
import json
import discord
from discord import app_commands
from discord.ext import commands

import bigtree
from bigtree.inc.logging import logger

# ---------- storage ----------
_PERMS_PATH = os.path.join(bigtree.workingdir, "permissions.json")

def _load_state():
    if not os.path.exists(_PERMS_PATH):
        return {"role_ids": [], "user_ids": []}
    try:
        with open(_PERMS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "role_ids": sorted({int(x) for x in data.get("role_ids", [])}),
                "user_ids": sorted({int(x) for x in data.get("user_ids", [])}),
            }
    except Exception as e:
        logger.error(f"Failed to read {_PERMS_PATH}: {e}", exc_info=True)
        return {"role_ids": [], "user_ids": []}

def _save_state(state):
    try:
        os.makedirs(os.path.dirname(_PERMS_PATH), exist_ok=True)
        with open(_PERMS_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "role_ids": sorted({int(x) for x in state.get("role_ids", [])}),
                    "user_ids": sorted({int(x) for x in state.get("user_ids", [])}),
                },
                f,
                indent=2,
            )
    except Exception as e:
        logger.error(f"Failed to write {_PERMS_PATH}: {e}", exc_info=True)

def _sync_globals(state):
    bigtree.operator_role_ids = sorted({int(x) for x in state.get("role_ids", [])})
    bigtree.operator_user_ids = sorted({int(x) for x in state.get("user_ids", [])})
    logger.info("Permissions synced: roles=%s users=%s",
                bigtree.operator_role_ids, bigtree.operator_user_ids)

# initialize globals on import
_sync_globals(_load_state())

# ---------- check ----------
async def _admin_only_predicate(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    if perms and perms.administrator:
        return True
    raise app_commands.CheckFailure("Only server administrators can use this command.")

# ---------- Cog ----------
class PermissionsCog(commands.Cog):
    """Holds the logic. Commands are attached programmatically to a fresh Group at runtime."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- handlers (plain methods; no decorators) ----
    async def cmd_list(self, interaction: discord.Interaction):
        state = _load_state()
        role_ids = state.get("role_ids", [])
        user_ids = state.get("user_ids", [])

        guild = interaction.guild
        role_mentions = []
        for rid in role_ids:
            role = guild.get_role(int(rid)) if guild else None
            role_mentions.append(role.mention if role else f"`{rid}` (missing)")

        user_mentions = []
        for uid in user_ids:
            member = guild.get_member(int(uid)) if guild else None
            user_mentions.append(member.mention if member else f"`{uid}` (missing)")

        text = (
            "**Allowed roles:** "
            + (", ".join(role_mentions) if role_mentions else "_none_")
            + "\n"
            "**Allowed users:** "
            + (", ".join(user_mentions) if user_mentions else "_none_")
        )
        await interaction.response.send_message(text, ephemeral=True)

    async def cmd_add_role(self, interaction: discord.Interaction, role: discord.Role):
        state = _load_state()
        role_ids = set(state.get("role_ids", []))
        role_ids.add(int(role.id))
        state["role_ids"] = sorted(role_ids)
        _save_state(state); _sync_globals(state)
        await interaction.response.send_message(
            f"✅ Added role {role.mention} to allowed list.", ephemeral=True
        )

    async def cmd_remove_role(self, interaction: discord.Interaction, role: discord.Role):
        state = _load_state()
        role_ids = set(state.get("role_ids", []))
        removed = int(role.id) in role_ids
        role_ids.discard(int(role.id))
        state["role_ids"] = sorted(role_ids)
        _save_state(state); _sync_globals(state)
        msg = f"🗑️ Removed role {role.mention}." if removed else f"ℹ️ {role.mention} wasn’t on the list."
        await interaction.response.send_message(msg, ephemeral=True)

    async def cmd_add_user(self, interaction: discord.Interaction, user: discord.Member):
        state = _load_state()
        user_ids = set(state.get("user_ids", []))
        user_ids.add(int(user.id))
        state["user_ids"] = sorted(user_ids)
        _save_state(state); _sync_globals(state)
        await interaction.response.send_message(
            f"✅ Added {user.mention} to allowed list.", ephemeral=True
        )

    async def cmd_remove_user(self, interaction: discord.Interaction, user: discord.Member):
        state = _load_state()
        user_ids = set(state.get("user_ids", []))
        removed = int(user.id) in user_ids
        user_ids.discard(int(user.id))
        state["user_ids"] = sorted(user_ids)
        _save_state(state); _sync_globals(state)
        msg = f"🗑️ Removed {user.mention}." if removed else f"ℹ️ {user.mention} wasn’t on the list."
        await interaction.response.send_message(msg, ephemeral=True)

    async def cmd_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await register_permissions_group(self.bot, interaction.guild_id, hard_purge=True)
        await interaction.followup.send("✅ Purged & re-synced /permissions for this server.", ephemeral=True)

# ---------- dynamic group builder ----------
def build_permissions_group(cog: PermissionsCog) -> app_commands.Group:
    group = app_commands.Group(
        name="permissions",
        description="Manage who can use BigTree privileged commands",
    )

    # Use the plain predicate, not a decorator
    admin_check = _admin_only_predicate

    list_cmd = app_commands.Command(
        name="list",
        description="Show allowed roles and users",
        callback=cog.cmd_list,
    )
    list_cmd.checks.append(admin_check)

    add_role_cmd = app_commands.Command(
        name="add-role",
        description="Allow a role to use BigTree commands",
        callback=cog.cmd_add_role,   # (interaction, role: discord.Role)
    )
    add_role_cmd.checks.append(admin_check)

    remove_role_cmd = app_commands.Command(
        name="remove-role",
        description="Remove a role from allowed list",
        callback=cog.cmd_remove_role,
    )
    remove_role_cmd.checks.append(admin_check)

    add_user_cmd = app_commands.Command(
        name="add-user",
        description="Allow a user to use BigTree commands",
        callback=cog.cmd_add_user,   # (interaction, user: discord.Member)
    )
    add_user_cmd.checks.append(admin_check)

    remove_user_cmd = app_commands.Command(
        name="remove-user",
        description="Remove a user from allowed list",
        callback=cog.cmd_remove_user,
    )
    remove_user_cmd.checks.append(admin_check)

    refresh_cmd = app_commands.Command(
        name="refresh",
        description="Force-purge and re-sync the /permissions commands for this server",
        callback=cog.cmd_refresh,
    )
    refresh_cmd.checks.append(admin_check)

    group.add_command(list_cmd)
    group.add_command(add_role_cmd)
    group.add_command(remove_role_cmd)
    group.add_command(add_user_cmd)
    group.add_command(remove_user_cmd)
    group.add_command(refresh_cmd)
    return group

# ---------- registration helpers ----------
async def register_permissions_group(bot: commands.Bot, guild_id: int, hard_purge: bool = False):
    """Remove stale copies, add fresh group, and sync. If hard_purge, clear guild commands first."""
    guild_obj = discord.Object(id=guild_id)

    # remove any stale guild copy
    try:
        bot.tree.remove_command("permissions", type=discord.AppCommandType.chat_input, guild=guild_obj)
    except Exception:
        pass

    # also remove any global copy (from earlier experiments)
    try:
        bot.tree.remove_command("permissions", type=discord.AppCommandType.chat_input, guild=None)
    except Exception:
        pass

    # (optional) nuke guild commands before re-adding to ensure fresh schema
    if hard_purge:
        try:
            bot.tree.clear_commands(guild=guild_obj)
            await bot.tree.sync(guild=guild_obj)  # push the clear
        except Exception:
            pass

    # add a brand-new group object built from the live cog
    cog: PermissionsCog = bot.get_cog("PermissionsCog")  # added in setup()
    group = build_permissions_group(cog)
    bot.tree.add_command(group, guild=guild_obj, override=True)

    # sync guild; then (optionally) sync global to flush global removal
    await bot.tree.sync(guild=guild_obj)
    try:
        await bot.tree.sync()
    except Exception:
        pass

    logger.info("Registered & synced /permissions for guild %s (hard_purge=%s)", guild_id, hard_purge)

# ---------- extension setup ----------
async def setup(bot: commands.Bot):
    await bot.add_cog(PermissionsCog(bot))

    # register after ready; no loop access
    if not getattr(bot, "_bigtree_perms_ready_hook_installed", False):
        bot._bigtree_perms_ready_hook_installed = True

        async def _on_ready_once():
            if getattr(bot, "_bigtree_perms_registered", False):
                return
            try:
                await register_permissions_group(bot, bigtree.guildid, hard_purge=False)
                bot._bigtree_perms_registered = True
            except Exception as e:
                logger.error("Failed to register /permissions: %s", e, exc_info=True)

        bot.add_listener(_on_ready_once, name="on_ready")
