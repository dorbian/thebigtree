"""
Content Request management commands for BigTree.
Allows Dorbian to propose contests (via bot) and review/approve requests from Discord.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

import bigtree
from bigtree.modules.permissions import is_bigtree_operator
from bigtree.modules.content_requests import (
    propose_art_contest,
    propose_rp_competition,
    propose_screenshot_challenge,
    list_requests,
    pending_requests,
    get_request,
    approve_request,
    reject_request,
)

bot = getattr(bigtree, "bot", None)


class ContentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- Propose commands (Pegas/Dorbian initiate proposals) ----

    @is_bigtree_operator()
    @app_commands.command(name="propose-art", description="Propose an art contest announcement")
    @app_commands.describe(
        theme="Contest theme/title",
        description="Full announcement text",
        duration_days="How many days (default: 7)",
        channel_id="Target channel ID (optional — uses elf-art if omitted)",
    )
    async def propose_art(self, interaction: discord.Interaction, theme: str, description: str,
                          duration_days: int = 7, channel_id: str = ""):
        """Propose an art contest for review."""
        cid = int(channel_id) if channel_id else None
        ch_name = ""
        if cid:
            ch = self.bot.get_channel(cid)
            if ch:
                ch_name = ch.name

        result = propose_art_contest(
            theme=theme,
            description=description,
            duration_days=duration_days,
            target_channel_id=cid,
            target_channel_name=ch_name,
        )

        if not result.get("ok"):
            return await interaction.response.send_message(f"❌ {result.get('error')}", ephemeral=True)

        req = get_request(result["id"])
        embed = discord.Embed(
            title=f"✅ Art Contest proposed (ID: {result['id']})",
            description=f"**Theme:** {theme}\n**Duration:** {duration_days} days\n**Status:** Pending review",
            color=0x9B59B6,
        )
        embed.add_field(name="Announcement", value=req["body"][:300] + ("..." if len(req["body"]) > 300 else ""), inline=False)
        embed.add_field(name="Target channel", value=ch_name or f"ID: {channel_id}", inline=True)
        embed.set_footer(text="Use /requests review to see pending requests")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @is_bigtree_operator()
    @app_commands.command(name="propose-rp", description="Propose an RP/story competition")
    @app_commands.describe(
        prompt="The writing prompt",
        duration_days="Days (default: 7)",
        word_limit="Max words (default: 500)",
        channel_id="Target channel ID",
    )
    async def propose_rp(self, interaction: discord.Interaction, prompt: str,
                         duration_days: int = 7, word_limit: int = 500, channel_id: str = ""):
        """Propose an RP competition for review."""
        cid = int(channel_id) if channel_id else None
        ch_name = ""
        if cid:
            ch = self.bot.get_channel(cid)
            if ch:
                ch_name = ch.name

        result = propose_rp_competition(
            prompt=prompt,
            duration_days=duration_days,
            word_limit=word_limit,
            target_channel_id=cid,
            target_channel_name=ch_name,
        )

        if not result.get("ok"):
            return await interaction.response.send_message(f"❌ {result.get('error')}", ephemeral=True)

        req = get_request(result["id"])
        embed = discord.Embed(
            title=f"✅ RP Competition proposed (ID: {result['id']})",
            description=f"**Prompt:** {prompt[:60]}...\n**Word limit:** {word_limit}\n**Duration:** {duration_days} days\n**Status:** Pending review",
            color=0x2ECC71,
        )
        embed.set_footer(text="Use /requests review to see pending requests")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @is_bigtree_operator()
    @app_commands.command(name="propose-screenshot", description="Propose a screenshot challenge")
    @app_commands.describe(
        theme="Challenge title",
        subject="What to photograph",
        duration_days="Days (default: 7)",
        channel_id="Target channel ID",
    )
    async def propose_screenshot(self, interaction: discord.Interaction, theme: str, subject: str,
                                 duration_days: int = 7, channel_id: str = ""):
        """Propose a screenshot challenge for review."""
        cid = int(channel_id) if channel_id else None
        ch_name = ""
        if cid:
            ch = self.bot.get_channel(cid)
            if ch:
                ch_name = ch.name

        result = propose_screenshot_challenge(
            theme=theme,
            subject=subject,
            duration_days=duration_days,
            target_channel_id=cid,
            target_channel_name=ch_name,
        )

        if not result.get("ok"):
            return await interaction.response.send_message(f"❌ {result.get('error')}", ephemeral=True)

        req = get_request(result["id"])
        embed = discord.Embed(
            title=f"✅ Screenshot Challenge proposed (ID: {result['id']})",
            description=f"**Theme:** {theme}\n**Subject:** {subject}\n**Duration:** {duration_days} days\n**Status:** Pending review",
            color=0x3498DB,
        )
        embed.set_footer(text="Use /requests review to see pending requests")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---- Review commands ----

    @is_bigtree_operator()
    @app_commands.command(name="requests-pending", description="Show all pending content requests")
    async def requests_pending(self, interaction: discord.Interaction):
        """Show all requests awaiting review."""
        pending = pending_requests()

        if not pending:
            return await interaction.response.send_message("No pending requests. 🍀", ephemeral=True)

        embed = discord.Embed(
            title=f"📋 Pending Requests ({len(pending)})",
            color=0xF39C12,
        )

        for req in pending[:10]:
            req_id = req.get("id")
            rtype = req.get("request_type", "?")
            title = req.get("title", "?")
            created = str(req.get("created_at", ""))[:16]
            ch_name = req.get("target_channel_name") or f"channel {req.get('target_channel_id', '?')}"
            embed.add_field(
                name=f"#{req_id} [{rtype}] → {ch_name}",
                value=f"**{title}**\nCreated: {created}\nUse `/requests review {req_id}` to see full content",
                inline=False,
            )

        if len(pending) > 10:
            embed.set_footer(text=f"And {len(pending) - 10} more...")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @is_bigtree_operator()
    @app_commands.command(name="requests-review", description="Review a specific content request by ID")
    @app_commands.describe(request_id="The request ID to review")
    async def requests_review(self, interaction: discord.Interaction, request_id: str):
        """Show full details of a request, with approve/reject buttons."""
        try:
            rid = int(request_id)
        except Exception:
            return await interaction.response.send_message("Invalid request ID", ephemeral=True)

        req = get_request(rid)
        if not req:
            return await interaction.response.send_message(f"Request #{rid} not found.", ephemeral=True)

        status_color = {
            "pending": 0xF39C12,
            "approved": 0x2ECC71,
            "rejected": 0xE74C3C,
            "posted": 0x9B59B6,
            "draft": 0x95A5A6,
        }.get(req.get("status", ""), 0x95A5A6)

        embed = discord.Embed(
            title=f"📝 Request #{rid}: {req.get('title', '')}",
            description=req.get("body", ""),
            color=status_color,
        )
        embed.add_field(name="Type", value=req.get("request_type", "?"), inline=True)
        embed.add_field(name="Status", value=req.get("status", "?"), inline=True)
        embed.add_field(name="Target", value=req.get("target_channel_name") or f"ID: {req.get('target_channel_id')}", inline=True)
        embed.add_field(name="Proposed", value=str(req.get("created_at", ""))[:16], inline=True)

        if req.get("review_notes"):
            embed.add_field(name="Review notes", value=req.get("review_notes"), inline=False)

        # Add action buttons via view
        view = RequestReviewView(request_id=rid)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RequestReviewView(discord.ui.View):
    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.request_id = request_id

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success, custom_id=f"req_approve_{self.request_id}")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bigtree.modules.content_requests import approve_request
        approve_request(self.request_id, reviewed_by=interaction.user.id, notes="Approved via Discord")
        await interaction.response.edit_message(
            content=f"✅ Request #{self.request_id} approved!",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id=f"req_reject_{self.request_id}")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bigtree.modules.content_requests import reject_request
        reject_request(self.request_id, reviewed_by=interaction.user.id, notes="Rejected via Discord")
        await interaction.response.edit_message(
            content=f"❌ Request #{self.request_id} rejected.",
            embed=None,
            view=None,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ContentCog(bot))