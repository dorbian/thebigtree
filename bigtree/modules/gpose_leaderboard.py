"""
Laureates Leaderboard Module for BigTree.

Monitors multiple submissions channels for treeheart reactions and publishes
a live aggregated leaderboard to the public leaderboard channel.
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
_SUBMISSION_CHANNELS_KEY = "LAUREATES_SUBMISSION_CHANNEL_IDS"  # JSON list of channel IDs
_LEADERBOARD_CHANNEL_KEY = "LAUREATES_LEADERBOARD_CHANNEL_ID"
_LEADERBOARD_MESSAGE_KEY = "LAUREATES_LEADERBOARD_MESSAGE_ID"
_TREEHEART_EMOJI = "<:treeheart:1321831300088463452>"

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
            return bigtree.settings.get(f"LAUREATES.{key}", default)
    except Exception:
        pass
    return os.getenv(f"BIGTREE__LAUREATES__{key}", default)

def _get_submission_channels() -> List[str]:
    """Returns list of submission channel IDs from config."""
    raw = _get_config(_SUBMISSION_CHANNELS_KEY)
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(c) for c in raw]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(c) for c in parsed]
    except Exception:
        pass
    return [str(raw)]

async def fetch_treehearts(
    bot,
    submissions_channel_ids: List[str],
    treeheart_emoji: str = _TREEHEART_EMOJI,
) -> List[Dict[str, Any]]:
    """
    Scan all messages in all submissions channels.
    For each message with an image attachment, count treeheart reactions.
    Aggregates by author across all channels.
    """
    bot_client = getattr(bigtree, "bot", None) or bot
    entries: List[Dict[str, Any]] = []

    for channel_id in submissions_channel_ids:
        channel = bot_client.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"[leaderboard] submissions channel {channel_id} not found")
            continue

        try:
            async for message in channel.history(limit=200):
                if not message.attachments:
                    continue

                total = 0
                for reaction in message.reactions:
                    em = reaction.emoji
                    if isinstance(em, str):
                        if em == treeheart_emoji or em.strip(":") == "treeheart":
                            total += reaction.count
                    else:
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
                    "channel_id": channel_id,
                    "posted_at": message.created_at.isoformat() if hasattr(message, "created_at") else None,
                })
        except Exception as e:
            logger.warning(f"[leaderboard] failed to scan channel {channel_id}: {e}")

    # Aggregate by author — sum scores across all channels
    author_scores: Dict[int, Dict[str, Any]] = {}
    for e in entries:
        aid = e["author_id"]
        if aid not in author_scores:
            author_scores[aid] = {
                "author_id": aid,
                "author_name": e["author_name"],
                "score": 0,
                "entries": 0,
            }
        author_scores[aid]["score"] += e["score"]
        author_scores[aid]["entries"] += 1

    sorted_authors = sorted(author_scores.values(), key=lambda x: (-x["score"], x.get("posted_at", "")))

    result = []
    for a in sorted_authors:
        result.append({
            "author_id": a["author_id"],
            "author_name": a["author_name"],
            "score": a["score"],
            "entries": a["entries"],
        })
    return result

def _make_leaderboard_embed(entries: List[Dict[str, Any]], total_channels: int, limit: int = 30) -> Dict[str, Any]:
    """Build a rich embed showing the current leaderboard."""
    import discord

    if not entries:
        return {
            "title": "🏆 Laureates Leaderboard",
            "description": "No submissions yet! Post your photos in any submissions channel to enter.",
            "color": 0x2ECC71,
            "fields": [],
        }

    medals = {0: "🏆", 1: "🥈", 2: "🥉"}

    top = entries[:limit]
    lines = []
    for i, e in enumerate(top):
        medal = medals.get(i, f"  {i+1}.")
        lines.append(f"{medal} **{e['author_name']}** — {e['score']} ❤️ ({e.get('entries', 1)} entries)")

    description = "\n".join(lines)
    if len(entries) > limit:
        description += f"\n\n_...and {len(entries) - limit} more participants_"

    embed = {
        "title": f"🏆 Laureates Leaderboard — {len(entries)} participants",
        "description": description,
        "color": 0x2ECC71,
        "footer": {
            "text": f"Last updated: {time.strftime('%H:%M:%S')} | {total_channels} submission channels",
        },
    }
    return embed

async def update_leaderboard_message(bot) -> Dict[str, Any]:
    """
    Main entry point: fetch scores across all submission channels and update the leaderboard message.
    """
    submission_channel_ids = _get_submission_channels()
    leaderboard_channel_id = _get_config(_LEADERBOARD_CHANNEL_KEY)

    if not submission_channel_ids:
        return {"ok": False, "error": "no submission channels configured (LAUREATES_SUBMISSION_CHANNEL_IDS)"}
    if not leaderboard_channel_id:
        return {"ok": False, "error": "leaderboard channel not configured (LAUREATES_LEADERBOARD_CHANNEL_ID)"}

    bot_client = getattr(bigtree, "bot", None) or bot
    lb_channel = bot_client.get_channel(int(leaderboard_channel_id))
    if not lb_channel:
        return {"ok": False, "error": f"leaderboard channel {leaderboard_channel_id} not found"}

    entries = await fetch_treehearts(bot_client, submission_channel_ids)
    embed_data = _make_leaderboard_embed(entries, len(submission_channel_ids))

    import discord
    embed = discord.Embed(
        title=embed_data["title"],
        description=embed_data["description"],
        color=embed_data.get("color", 0x2ECC71),
    )
    if embed_data.get("footer"):
        embed.set_footer(text=embed_data["footer"]["text"])

    if len(entries) >= 1:
        podium_lines = []
        for i in range(min(3, len(entries))):
            e = entries[i]
            medal = ["🏆", "🥈", "🥉"][i]
            podium_lines.append(f"{medal} {e['author_name']} — **{e['score']}** ❤️ ({e.get('entries', 1)} posts)")
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
            msg_id = None

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

async def run_leaderboard_check(bot=None):
    """Called periodically. Updates the leaderboard across all submission channels."""
    return await update_leaderboard_message(bot)