from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional, Callable
import discord
from discord import app_commands
from discord.ext import commands
try:
    import bigtree
except Exception:
    bigtree = None
def _ai_generate_short(prompt: str, max_chars: int = 150) -> str:
    try:
        ai = getattr(bigtree, "ai", None)
        if ai and hasattr(ai, "generate_short"):
            out = str(ai.generate_short(prompt, max_chars=max_chars))
            return _finalize_length(out, max_chars)
    except Exception:
        pass
    text = (prompt or "").strip()
    if not text:
        return "A quick update from the Tree: all is calm, all is cozy. 🌲"
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+|, ", text)
    buf = ""
    for p in parts:
        if not p: continue
        nxt = (buf + (" " if buf else "") + p).strip()
        if len(nxt) > max_chars:
            if not buf:
                buf = p[: max_chars - 1].rstrip() + "…"
            break
        buf = nxt
    if not buf.endswith(('.', '!', '?', '…')):
        buf += "."
    return _finalize_length(buf, max_chars)
def _finalize_length(s: str, max_chars: int) -> str:
    import re as _re
    s = s.replace("\n", " ").strip()
    s = _re.sub(r"\s+", " ", s)
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s
@dataclass
class SessionState:
    user_id: int
    channel_id: int
    prompt: str
    max_chars: int
    draft: str
class ApproveRetryView(discord.ui.View):
    def __init__(self, state: SessionState, regenerate: Callable[[str, int], str], *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout); self.state = state; self.regenerate = regenerate
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.state.user_id:
            await interaction.response.send_message("Only the requester can use these controls.", ephemeral=True); return False
        return True
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.client.get_channel(self.state.channel_id)  # type: ignore
        try:
            if channel is None:
                channel = await interaction.client.fetch_channel(self.state.channel_id)  # type: ignore
            await channel.send(self.state.draft)  # type: ignore
            await interaction.response.edit_message(content="Posted ✅", view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"Could not post: {e}", view=None)
    @discord.ui.button(label="Retry", style=discord.ButtonStyle.secondary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.draft = self.regenerate(self.state.prompt, self.state.max_chars)
        await interaction.response.edit_message(content=f"**Draft ({self.state.max_chars} chars):**\n{self.state.draft}\n\nApprove to post, or Retry for another.", view=self)
    @discord.ui.button(label="Revoke", style=discord.ButtonStyle.danger)
    async def revoke(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled. ❌", view=None); self.stop()
class QuickPostCog(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot = bot
    @app_commands.command(name="quickpost", description="Create a short bot post with AI assistance.")
    async def quickpost(self, interaction: discord.Interaction):
        class PromptModal(discord.ui.Modal, title="Quick Post"):
            topic = discord.ui.TextInput(label="What should it be about?", style=discord.TextStyle.paragraph, max_length=600, placeholder="E.g., Cozy autumn vibes, new event, community reminder…")
            length = discord.ui.TextInput(label="Desired length (characters)", placeholder="150", required=False, max_length=4)
            async def on_submit(self, inner: discord.Interaction) -> None:
                prompt_text = str(self.topic.value or "").strip()
                try:
                    max_chars = int(str(self.length.value or "150").strip()); max_chars = 50 if max_chars < 50 else (300 if max_chars > 300 else max_chars)
                except Exception:
                    max_chars = 150
                draft = _ai_generate_short(prompt_text, max_chars=max_chars)
                state = SessionState(user_id=inner.user.id, channel_id=inner.channel_id, prompt=prompt_text, max_chars=max_chars, draft=draft)  # type: ignore
                view = ApproveRetryView(state, regenerate=lambda p, m: _ai_generate_short(p, m))
                await inner.response.send_message(f"**Draft ({max_chars} chars):**\n{draft}\n\nApprove to post, or Retry for another.", ephemeral=True, view=view)
        await interaction.response.send_modal(PromptModal())
async def setup(bot: commands.Bot): await bot.add_cog(QuickPostCog(bot))