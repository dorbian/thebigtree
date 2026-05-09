"""
Content Submission and Review via Discord Modal.
Dorbian drafts with Pegas → submits → bot posts to review channel → Review button opens a modal to edit/confirm → post.

Flow:
  /submit-content (modal) → review channel (simple card + "Review" button)
  "Review" button → Review modal → edit content + notes → "Post It" / "Needs Work" / "Reject"
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
)

REVIEW_CHANNEL_ID = 1224486271557173318  # bot-logs

bot = getattr(bigtree, "bot", None)


# ─────────────────────────────────────────────────────────────────────────────
# Submission Modal (Step 1)
# ─────────────────────────────────────────────────────────────────────────────

class ContentSubmitModal(discord.ui.Modal, title="📝 Submit Content for Review"):

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
        placeholder="Leave blank for elf-art (1232148205773394021)",
        required=False,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        rtype = self.request_type_input.value or "art_contest"
        body = self.body_input.value or ""
        title = self.title_input.value or "Content Submission"
        target_cid_str = self.target_channel_id_input.value or ""

        target_cid = None
        target_ch = None
        if target_cid_str.strip():
            try:
                target_cid = int(target_cid_str.strip())
                target_ch = interaction.client.get_channel(target_cid)
            except ValueError:
                pass

        if not target_ch:
            target_cid = 1232148205773394021  # elf-art default
            target_ch = interaction.client.get_channel(target_cid)

        ch_name = target_ch.name if target_ch else str(target_cid)

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

        embed = discord.Embed(
            title=f"📋 Content Review | #{request_id}",
            description=body[:4096],
            color=0xF39C12,
        )
        embed.add_field(name="Type", value=rtype, inline=True)
        embed.add_field(name="Target", value=f"#{ch_name} ({target_cid})", inline=True)
        embed.add_field(name="Status", value="⏳ Pending Review", inline=True)
        embed.set_footer(text=f"Request #{request_id} | Click Review to open editor")

        review_ch = interaction.client.get_channel(REVIEW_CHANNEL_ID)
        if not review_ch:
            return await interaction.response.send_message(
                f"❌ Could not find review channel <#{REVIEW_CHANNEL_ID}>", ephemeral=True,
            )

        view = ReviewEntryView(request_id=request_id, target_channel_id=target_cid)
        review_msg = await review_ch.send(embed=embed, view=view)

        # Attach review message metadata to the request
        try:
            from bigtree.modules.content_requests import get_database
            if get_database:
                db = get_database()
                meta_patch = json.dumps({
                    "review_message_id": str(review_msg.id),
                    "review_channel_id": REVIEW_CHANNEL_ID,
                })
                db._execute(
                    "UPDATE content_requests SET metadata = metadata || %s WHERE id = %s",
                    (meta_patch, request_id),
                )
        except Exception:
            pass

        await interaction.response.send_message(
            f"✅ Submitted! Review request #{request_id} posted to <#{REVIEW_CHANNEL_ID}>",
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Review Channel Card View (Step 2 — simple entry point)
# ─────────────────────────────────────────────────────────────────────────────

class ReviewEntryView(discord.ui.View):
    """Shown in the review channel. Review button opens editor modal.
    OK and Needs Work are also buttons on the card for quick actions."""

    def __init__(self, request_id: int, target_channel_id: int):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.target_channel_id = target_channel_id
        self._set_custom_ids()

    def _set_custom_ids(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                label = child.label or ""
                if "Review" in label or "🔍" in label:
                    child.custom_id = f"cr_review_{self.request_id}"
                elif "Post" in label or "✅" in label:
                    child.custom_id = f"cr_post_{self.request_id}"
                elif "Needs Work" in label or "🔧" in label:
                    child.custom_id = f"cr_needswork_{self.request_id}"
                elif "Reject" in label or "❌" in label:
                    child.custom_id = f"cr_reject_{self.request_id}"

    @discord.ui.button(label="🔍 Review / Edit", style=discord.ButtonStyle.primary)
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        req = get_request(self.request_id)
        if not req:
            return await interaction.response.send_message("❌ Request not found.", ephemeral=True)
        modal = ContentReviewModal(
            request_id=self.request_id,
            target_channel_id=self.target_channel_id,
            initial_title=req.get("title", ""),
            initial_body=req.get("body", ""),
            initial_type=req.get("request_type", "art_contest"),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ Post Now", style=discord.ButtonStyle.success)
    async def post_now_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Quick-post: grabs current content and sends straight to target."""
        req = get_request(self.request_id)
        if not req:
            return await interaction.response.send_message("❌ Request not found.", ephemeral=True)
        target_ch = interaction.client.get_channel(self.target_channel_id)
        if not target_ch:
            return await interaction.response.send_message(
                f"❌ Target channel <#{self.target_channel_id}> not found.", ephemeral=True,
            )
        try:
            msg = await target_ch.send(req.get("body", ""))
            jump = f"[Jump]({msg.jump_url})"
        except Exception as e:
            return await interaction.response.send_message(f"❌ Failed to post: {e}", ephemeral=True)
        approve_request(self.request_id, reviewed_by=interaction.user.id, notes="Quick-posted via button")
        mark_posted(self.request_id)
        embed = discord.Embed(title=f"✅ Posted | #{self.request_id}", color=0x2ECC71)
        embed.add_field(name="Target", value=f"<#{self.target_channel_id}>", inline=True)
        embed.add_field(name="Jump", value=jump, inline=True)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔧 Needs Work", style=discord.ButtonStyle.secondary)
    async def needswork_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ContentNeedsWorkModal(request_id=self.request_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        reject_request(self.request_id, reviewed_by=interaction.user.id, notes="Rejected via button")
        embed = discord.Embed(title=f"❌ Rejected | #{self.request_id}", color=0xE74C3C)
        embed.add_field(name="Status", value="❌ Rejected", inline=True)
        embed.add_field(name="Reviewed by", value=f"<@{interaction.user.id}>", inline=True)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"❌ Request #{self.request_id} rejected.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Review Modal (Step 3 — full edit + confirm)
# ─────────────────────────────────────────────────────────────────────────────

class ContentReviewModal(discord.ui.Modal, title="🔍 Review Content"):

    def __init__(
        self,
        request_id: int,
        target_channel_id: int,
        initial_title: str = "",
        initial_body: str = "",
        initial_type: str = "art_contest",
    ):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.target_channel_id = target_channel_id

        self.title_field = discord.ui.TextInput(
            label="Title",
            default=initial_title,
            max_length=200,
            required=True,
        )
        self.body_field = discord.ui.TextInput(
            label="Content",
            default=initial_body,
            style=discord.TextStyle.long,
            max_length=2000,
            required=True,
        )
        self.notes_field = discord.ui.TextInput(
            label="Review Notes (optional)",
            placeholder="Any adjustments needed before posting...",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False,
        )

        self.add_item(self.title_field)
        self.add_item(self.body_field)
        self.add_item(self.notes_field)

    async def on_submit(self, interaction: discord.Interaction):
        updated_body = self.body_field.value or ""
        updated_title = self.title_field.value or ""
        notes = self.notes_field.value or ""

        bot = interaction.client
        target_ch = bot.get_channel(self.target_channel_id)

        if not target_ch:
            return await interaction.response.send_message(
                f"❌ Target channel <#{self.target_channel_id}> not found.", ephemeral=True,
            )

        # Post to target channel
        try:
            msg = await target_ch.send(updated_body)
            jump = f"[Jump]({msg.jump_url})"
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Failed to post: {e}", ephemeral=True,
            )

        # Mark as approved and posted
        approve_request(
            self.request_id,
            reviewed_by=interaction.user.id,
            notes=f"Approved via review modal. Notes: {notes}",
        )
        mark_posted(self.request_id)

        # Acknowledge in the review channel
        posted_embed = discord.Embed(
            title=f"✅ Posted | #{self.request_id}",
            description=f"**{updated_title}**\n\n{updated_body[:1024]}",
            color=0x2ECC71,
        )
        posted_embed.add_field(name="Target", value=f"<#{self.target_channel_id}>", inline=True)
        posted_embed.add_field(name="Jump", value=jump, inline=True)
        if notes:
            posted_embed.add_field(name="Review notes", value=notes, inline=False)

        await interaction.response.send_message(
            embed=posted_embed,
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Review needs-work modal (re-use same modal but with different button label)
# ─────────────────────────────────────────────────────────────────────────────

class ContentNeedsWorkModal(discord.ui.Modal, title="🔧 Needs Work — Add Notes"):

    def __init__(self, request_id: int):
        super().__init__(timeout=None)
        self.request_id = request_id

        self.notes_field = discord.ui.TextInput(
            label="What needs to change?",
            placeholder="Describe what adjustments are needed...",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True,
        )
        self.add_item(self.notes_field)

    async def on_submit(self, interaction: discord.Interaction):
        notes = self.notes_field.value or "Flagged as needing revision"

        update_request_status(
            self.request_id,
            status="needs_revision",
            reviewed_by=interaction.user.id,
            review_notes=notes,
        )

        await interaction.response.send_message(
            f"🔧 Request #{self.request_id} marked as needing work.\n"
            f"Notes: {notes}",
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────────────

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
        # Restore persistent views on restart so button callbacks survive restart
        review_ch = self.bot.get_channel(REVIEW_CHANNEL_ID)
        if not review_ch:
            return

        async for msg in review_ch.history(limit=100):
            if msg.author.id != self.bot.user.id:
                continue
            if not msg.embeds:
                continue
            embed = msg.embeds[0]
            if not (embed.title and "Content Review" in embed.title):
                continue
            try:
                rid = int(embed.title.split("#")[-1])
            except Exception:
                continue

            # Try to get target_channel_id from content field
            target_cid = 1232148205773394021
            for field in (embed.fields or []):
                if field.name == "Target":
                    import re
                    m = re.search(r"\((\d+)\)", field.value)
                    if m:
                        target_cid = int(m.group(1))

            self.bot.add_view(
                ReviewEntryView(request_id=rid, target_channel_id=target_cid),
                message_id=msg.id,
            )


import json  # needed for meta patch in on_submit


async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewCog(bot))