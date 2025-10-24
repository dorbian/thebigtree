from __future__ import annotations
import json, secrets
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands
try:
    import bigtree
except Exception:
    bigtree = None
def _settings_get(section: str, key: str, default=None):
    try:
        if hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(section, {}).get(key, default)
    except Exception: pass
    try:
        cfg = getattr(getattr(bigtree, "config", None), "config", None) or {}
        return cfg.get(section, {}).get(key, default)
    except Exception: pass
    return default
def _data_dir() -> Path:
    base = _settings_get("BOT", "DATA_DIR", None) or getattr(bigtree, "datadir", ".")
    p = Path(base) / "tarot"; (p / "sessions").mkdir(parents=True, exist_ok=True); return p
DECK_PATH = _data_dir()/ "deck.json"
SESS_DIR  = _data_dir()/ "sessions"
def _load_json(p: Path, default):
    if not p.exists(): return default
    try: return json.loads(p.read_text("utf-8"))
    except Exception: return default
def _save_json(p: Path, data: Any):
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
def _load_deck() -> List[Dict[str,str]]:
    if not DECK_PATH.exists(): _save_json(DECK_PATH, []); return []
    return _load_json(DECK_PATH, [])
def _save_deck(deck: List[Dict[str,str]]): _save_json(DECK_PATH, deck)
def _new_session(subject: str, spread: str) -> Dict[str, Any]:
    sid = secrets.token_urlsafe(10); admin_token=secrets.token_urlsafe(16); public_token=secrets.token_urlsafe(16)
    doc = {"id":sid,"created":datetime.now(timezone.utc).isoformat(),"subject":subject,"spread":spread,
           "admin_token":admin_token,"public_token":public_token,"cards":[],"notes":"","closed":False}
    _save_json(SESS_DIR / f"{sid}.json", doc); return doc
class TarotAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot = bot
    @app_commands.command(name="tarot_addcard", description="Add a tarot card to the deck (Title + private fields).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tarot_addcard(self, interaction: discord.Interaction):
        class AddCardModal(discord.ui.Modal, title="Add Tarot Card"):
            title = discord.ui.TextInput(label="Title", max_length=100, placeholder="The Wanderer")
            description = discord.ui.TextInput(label="Description (private)", style=discord.TextStyle.paragraph, required=False)
            flair = discord.ui.TextInput(label="Flair text (private)", style=discord.TextStyle.paragraph, required=False)
            async def on_submit(self, inner: discord.Interaction) -> None:
                deck = _load_deck(); deck.append({"title":str(self.title.value).strip(),
                "description":str(self.description.value or "").strip(),"flair_text":str(self.flair.value or "").strip()})
                _save_deck(deck); await inner.response.send_message(f"Added **{self.title.value}** to the deck. ✅", ephemeral=True)
        await interaction.response.send_modal(AddCardModal())
    @app_commands.command(name="tarot_session", description="Create a tarot reading session.")
    async def tarot_session(self, interaction: discord.Interaction):
        class NewSession(discord.ui.Modal, title="New Tarot Session"):
            subject = discord.ui.TextInput(label="Subject (who/what)", max_length=100, placeholder="Dorbian")
            spread = discord.ui.TextInput(label="Spread", required=False, placeholder="single/three/five/custom")
            async def on_submit(self, inner: discord.Interaction) -> None:
                doc = _new_session(str(self.subject.value).strip(), str(self.spread.value or 'single').strip() or "single")
                base = _settings_get("WEB", "BASE_URL", "http://localhost:8080").rstrip("/")
                client_url = f"{base}/tarot/{doc['public_token']}"; admin_url = f"{base}/tarot/admin/{doc['admin_token']}"
                await inner.response.send_message(f"Session created! 🔮\n**Client:** {client_url}\n**Admin:** {admin_url}", ephemeral=True)
        await interaction.response.send_modal(NewSession)
async def setup(bot: commands.Bot): await bot.add_cog(TarotAdminCog(bot))
