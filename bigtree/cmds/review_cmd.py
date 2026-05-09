"""
Content Submission and Review via Discord Modal.
Dorbian drafts with Pegas → submits → bot posts to review channel → buttons handle approve/needswork/reject → posted to target.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import bigtree
from bigtree.modules.permissions import is_bigtree_operator
from bigtree.modules.content_requests import (
    create_request,
    get_request,
    mark_posted,
    approve_request,
    reject_request,
    update_request_status,
    RequestStatus,
)

REVIEW_CHANNEL_ID = 1224486271557173318  # bot-logs

bot = getattr(bigtree, "bot", None)


class ContentSubmitModal(discord.ui.Modal, title="📝 Submit Content for Review"):
    """Modal presented to Dorbian to enter content details before submission."""

    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="e.g. 🎨 Art Contest: Open Theme",
        max_length=200,
        required=True,
    )
    body_input = discord.ui.TextInput(
        label="Content",
        placeholder="Paste the full announcement text here...",
        style=discord.TextStyle.long,
        max_length=2000,
        required=True,
    )
    request_type_input = discord.ui.TextInput(
        label="Type (art_contest / rp_competition / screenshot)",
        placeholder="art_contest",
        default="art_contest",
        max_length=50,
        required=True,
    )
    target_channel_id_input = discord.ui.TextInput(
        label="Target Channel ID (optional)",
        placeholder="Leave blank to post to elf-art (1232148205773394021)",
        required=False,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        rtype = self.title_input.value or "art_contest"
        body = self.body_input.value or ""
        title = self.title_input.value or "Content Submission"
        target_cid_str = self.target_channel_id_input.value or ""

        # Resolve target channel
        target_cid = None
        target_ch = None
        if target_cid_str.strip():
            try:
                target_cid = int(target_cid_str.strip())
                target_ch = interaction.client.get_channel(target_cid)
            except ValueError:
                pass

        if not target_ch:
            # Default to elf-art
            target_cid = 1232148205773394021
            target_ch = interaction.client.get_channel(target_cid)

        ch_name = target_ch.name if target_ch else str(target_cid)

        # Create the content request
        result = create_request(
            request_type=rtype.strip(),
            title=title,
            body=body,
            target_channel_id=target_cid,
            target_channel_name=ch_name,
        )

        if not result.get("ok"):
            return await interaction.response.send_message(
                f"❌ Failed to create request: {result.get('error')}", ephemeral=True,
            )

        request_id = result["id"]

        # Build the review embed
        status_color = 0xF39C12  # orange = pending
        embed = discord.Embed(
            title=f"📋 Content Review | #{request_id}",
            description=body[:4096],
            color=status_color,
        )
        embed.add_field(name="Type", value=rtype, inline=True)
        embed.add_field(name="Target", value=f"#{ch_name} ({target_cid})", inline=True)
        embed.add_field(name="Status", value="⏳ Pending Review", inline=True)
        embed.set_footer(text=f"Request #{request_id} | Use buttons below to act")

        # Send to review channel with action buttons
        review_ch = interaction.client.get_channel(REVIEW_CHANNEL_ID)
        if not review_ch:
            return await interaction.response.send_message(
                f"❌ Could not find review channel <#{REVIEW_CHANNEL_ID}>", ephemeral=True,
            )

        view = ContentReviewView(request_id=request_id, target_channel_id=target_cid)
        review_msg = await review_ch.send(embed=embed, view=view)

        # Store the review message ID on the request
        from bigtree.modules.content_requests import get_database
        if get_database:
            db = get_database()
            db._execute(
                "UPDATE content_requests SET metadata = metadata || %s WHERE id = %s",
                (f'{{"review_message_id": "{review_msg.id}", "review_channel_id": {REVIEW_CHANNEL_ID}}}',
                 request_id),
            )

        await interaction.response.send_message(
            f"✅ Submitted! Review request #{request_id} posted to <#{REVIEW_CHANNEL_ID}>",
            ephemeral=True,
        )


class ContentReviewView(discord.ui.View):
    """
    Persistent view shown in the review channel.
    Three buttons:
      OK       → post to target, mark approved+posted
      Needs Work → mark needs_revision, notify
      NO        → mark rejected
    """

    def __init__(self, request_id: int, target_channel_id: int):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.target_channel_id = target_channel_id

    @discord.ui.button(label="✅ OK — Post It", style=discord.ButtonStyle.success, custom_id=f"cr_ok_{request_id}")
    async def ok_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        req = get_request(self.request_id)
        if not req:
            return await interaction.response.send_message("❌ Request not found.", ephemeral=True)

        # Post to target channel
        bot = interaction.client
        target_ch = bot.get_channel(self.target_channel_id)
        if not target_ch:
            return await interaction.response.send_message(
                f"❌ Target channel <#{self.target_channel_id}> not found.",
                ephemeral=True,
            )

        body = req.get("body", "")
        try:
            msg = await target_ch.send(body)
            jump = f"[Jump]({msg.jump_url})"
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Failed to post: {e}", ephemeral=True,
            )

        # Mark as approved + posted
        approve_request(self.request_id, reviewed_by=interaction.user.id, notes="Approved via review button")
        mark_posted(self.request_id)

        # Update the review message
        approve_embed = discord.Embed(
            title=f"✅ Posted | #{self.request_id}",
            description=body[:4096],
            color=0x2ECC71,
        )
        approve_embed.add_field(name="Status", value="✅ Posted to target", inline=True)
        approve_embed.add_field(name="Target", value=f"<#{self.target_channel_id}>", inline=True)
        approve_embed.add_field(name="Jump", value=jump, inline=True)

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=approve_embed, view=self)
        await interaction.followup.send(
            f"✅ Content #{self.request_id} posted to <#{self.target_channel_id}>!",
            ephemeral=True,
        )

    @discord.ui.button(label="🔧 Needs Work", style=discord.ButtonStyle.secondary, custom_id=f"cr_needswork_{request_id}")
    async def needswork_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        update_request_status(
            self.request_id,
            status="needs_revision",
            reviewed_by=interaction.user.id,
            review_notes="Flagged as needing revision",
        )

        needswork_embed = discord.Embed(
            title=f"🔧 Needs Revision | #{self.request_id}",
            color=0xE67E22,
        )
        needswork_embed.add_field(
            name="What to do",
            value="Revise the content and submit a new request with the improved version.",
            inline=False,
        )
        needswork_embed.add_field(name="Reviewed by", value=f"<@{interaction.user.id}>", inline=True)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=needswork_embed, view=self)
        await interaction.followup.send(
            f"🔧 Request #{self.request_id} marked as needing revision.",
            ephemeral=True,
        )

    @discord.ui.button(label="❌ NO — Reject", style=discord.ButtonStyle.danger, custom_id=f"cr_no_{request_id}")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        reject_request(self.request_id, reviewed_by=interaction.user.id, notes="Rejected via review button")

        reject_embed = discord.Embed(
            title=f"❌ Rejected | #{self.request_id}",
            color=0xE74C3C,
        )
        reject_embed.add_field(name="Status", value="❌ Rejected", inline=True)
        reject_embed.add_field(name="Reviewed by", value=f"<@{interaction.user.id}>", inline=True)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=reject_embed, view=self)
        await interaction.followup.send(
            f"❌ Request #{self.request_id} rejected.",
            ephemeral=True,
        )


class ReviewCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @is_bigtree_operator()
    @app_commands.command(
        name="submit-content",
        description="Draft content for review — opens a modal to enter title, body, and target",
    )
    async def submit_content(self, interaction: discord.Interaction):
        """Open the content submission modal."""
        await interaction.response.send_modal(ContentSubmitModal())

    async def cog_load(self):
        # Re-attach persistent views after bot restart so button callbacks still fire
        review_ch = self.bot.get_channel(REVIEW_CHANNEL_ID)
        if review_ch:
            async for msg in review_ch.history(limit=50):
                if msg.author.id == self.bot.user.id and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title and "Content Review" in embed.title:
                        # Extract request_id from title like "📋 Content Review | #123"
                        try:
                            rid = int(embed.title.split("#")[-1])
                            self.bot.add_view(ContentReviewView(request_id=rid, target_channel_id=0), message_id=msg.id)
                        except Exception:
                            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewCog(bot))