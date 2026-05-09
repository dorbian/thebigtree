"""
G-Pose Leaderboard Module for BigTree.

Monitors the submissions channel for treeheart reactions and publishes
a live leaderboard to the public leaderboard channel.
"""

from __future__ import annotations
import os
import time
import json
from typing import Dict, List, Any, Optional

try:
    import bigtree
    from bigtree.inc.logging import logger
except Exception:
    bigtree = None
    logger = print

# ---- Config ----
_SUBMISSIONS_CHANNEL_KEY = "GPOSE_SUBMISSIONS_CHANNEL_ID"
_LEADERBOARD_CHANNEL_KEY = "GPOSE_LEADERBOARD_CHANNEL_ID"
_LEADERBOARD_MESSAGE_KEY = "GPOSE_LEADERBOARD_MESSAGE_ID"
_TREEHEART_EMOJI = "<:treeheart:1321831300088463452>"
_UPDATE_INTERVAL_MINUTES = 5

# ---- Persistence for leaderboard message ID ----
def _config_path() -> str:
    base = getattr(bigtree, "contest_dir", "/data/contest") if bigtree else "/data/contest"
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "leaderboard_config.json")


def _load_lb_config() -> Dict[str, Any]:
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_lb_config(cfg: Dict[str, Any]) -> None:
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _get_config(key: str, default: Any = None) -> Any:
    try:
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(f"GPOSE.{key}", default)
    except Exception:
        pass
    return os.getenv(f"BIGTREE__GPOSE__{key}", default)


# ---- Leaderboard computation ----
async def fetch_treehearts(
    bot,
    submissions_channel_id: str,
    treeheart_emoji: str = _TREEHEART_EMOJI,
) -> List[Dict[str, Any]]:
    """
    Scan all messages in the submissions channel.
    For each message with an image attachment, count treeheart reactions.
    Returns sorted list: [{message_id, author_id, author_name, score, jump_url, image_url}, ...]
    """
    bot_client = getattr(bigtree, "bot", None) or bot
    channel = bot_client.get_channel(int(submissions_channel_id))
    if not channel:
        logger.warning(f"[leaderboard] submissions channel {submissions_channel_id} not found")
        return []

    entries: List[Dict[str, Any]] = []

    try:
        # Fetch last 200 messages (reasonable window for active contest)
        async for message in channel.history(limit=200):
            if not message.attachments:
                continue

            # Count treeheart reactions
            total = 0
            for reaction in message.reactions:
                em = reaction.emoji
                if isinstance(em, str):
                    if em == treeheart_emoji or em.strip(":") == "treeheart":
                        total += reaction.count
                else:
                    # Custom emoji — match by name
                    name = getattr(em, "name", "") or ""
                    if "treeheart" in name.lower():
                        total += reaction.count

            author = message.author
            image_url = None
            for att in message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    image_url = att.url
                    break
            if image_url is None and message.attachments:
                image_url = message.attachments[0].url

            entries.append({
                "message_id": str(message.id),
                "author_id": author.id,
                "author_name": str(author.display_name),
                "score": total,
                "jump_url": message.jump_url,
                "image_url": image_url,
                "posted_at": message.created_at.isoformat() if hasattr(message, "created_at") else None,
            })

    except Exception as e:
        logger.warning(f"[leaderboard] failed to scan submissions channel: {e}")

    # Sort by score descending, then by earliest post for ties
    entries.sort(key=lambda x: (-x["score"], x.get("posted_at", "")))
    return entries


def _make_leaderboard_embed(entries: List[Dict[str, Any]], limit: int = 30) -> Dict[str, Any]:
    """Build a rich embed showing the current leaderboard."""
    import discord

    if not entries:
        return {
            "title": "📊 G-Pose Leaderboard",
            "description": "No submissions yet! Post your G-Pose screenshots in 📷︱gpose-submissions to enter.",
            "color": 0x2ECC71,
            "fields": [],
        }

    # Top entry gets 🏆, 2nd 🥈, 3rd 🥉
    medals = {0: "🏆", 1: "🥈", 2: "🥉"}

    top = entries[:limit]
    lines = []
    for i, e in enumerate(top):
        medal = medals.get(i, f"  {i+1}.")
        lines.append(f"{medal} **{e['author_name']}** — {e['score']} ❤️")

    description = "\n".join(lines)
    if len(entries) > limit:
        description += f"\n\n_...and {len(entries) - limit} more participants_"

    embed = {
        "title": f"📊 G-Pose Leaderboard — {len(entries)} entries",
        "description": description,
        "color": 0x2ECC71,
        "footer": {
            "text": f"Last updated: {time.strftime('%H:%M:%S')} | React with ❤️ to vote!",
        },
    }
    return embed


async def update_leaderboard_message(bot) -> Dict[str, Any]:
    """
    Main entry point: fetch scores and update (or create) the leaderboard message.
    Returns a status dict.
    """
    submissions_channel_id = _get_config(_SUBMISSIONS_CHANNEL_KEY)
    leaderboard_channel_id = _get_config(_LEADERBOARD_CHANNEL_KEY)

    if not submissions_channel_id or not leaderboard_channel_id:
        return {"ok": False, "error": "submissions_channel_id or leaderboard_channel_id not configured"}

    bot_client = getattr(bigtree, "bot", None) or bot
    lb_channel = bot_client.get_channel(int(leaderboard_channel_id))
    if not lb_channel:
        return {"ok": False, "error": f"leaderboard channel {leaderboard_channel_id} not found"}

    # Fetch scores
    entries = await fetch_treehearts(bot_client, submissions_channel_id)
    embed_data = _make_leaderboard_embed(entries)

    # Build a Discord embed object
    import discord
    embed = discord.Embed(
        title=embed_data["title"],
        description=embed_data["description"],
        color=embed_data.get("color", 0x2ECC71),
    )
    if embed_data.get("footer"):
        embed.set_footer(text=embed_data["footer"]["text"])

    # Also add a top-3 podium section if we have entries
    if len(entries) >= 1:
        podium_lines = []
        for i in range(min(3, len(entries))):
            e = entries[i]
            medal = ["🏆", "🥈", "🥉"][i]
            podium_lines.append(f"{medal} {e['author_name']} — **{e['score']}** ❤️")
        embed.add_field(name="🏅 Top 3", value="\n".join(podium_lines), inline=False)

    if len(entries) >= 4:
        gap_lines = []
        for i in range(3, min(8, len(entries))):
            e = entries[i]
            prev = entries[i-1]
            gap = prev["score"] - e["score"]
            gap_str = f"(−{gap})" if gap > 0 else "(tied)"
            gap_lines.append(f"{i+1}. {e['author_name']} {gap_str}")
        embed.add_field(name="📈 Positions 4–7", value="\n".join(gap_lines), inline=False)

    # Get or create the leaderboard message
    lb_cfg = _load_lb_config()
    msg_id = lb_cfg.get("leaderboard_message_id")

    edited = False
    if msg_id:
        try:
            msg = await lb_channel.fetch_message(int(msg_id))
            await msg.edit(embed=embed)
            edited = True
            logger.info(f"[leaderboard] updated existing message {msg_id}")
        except Exception:
            msg_id = None  # message deleted or not found, create new

    if not edited:
        sent_msg = await lb_channel.send(embed=embed)
        msg_id = str(sent_msg.id)
        lb_cfg["leaderboard_message_id"] = msg_id
        _save_lb_config(lb_cfg)
        logger.info(f"[leaderboard] posted new leaderboard message {msg_id}")

    return {
        "ok": True,
        "entries": len(entries),
        "message_id": msg_id,
        "top_score": entries[0]["score"] if entries else 0,
    }


# ---- Standalone check (called by cron or manual trigger) ----
async def run_leaderboard_check(bot=None):
    """Called periodically. Updates the leaderboard."""
    return await update_leaderboard_message(bot)