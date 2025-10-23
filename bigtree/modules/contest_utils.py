# bigtree/modules/contest_utils.py
from __future__ import annotations
import os
from typing import Dict, Any, List, Tuple, Optional
from tinydb import TinyDB, Query

import discord

# logger (no prints)
try:
    from bigtree.inc.logging import logger
except Exception:
    import logging
    logger = logging.getLogger("bigtree")

def _db_path(contest_dir: str, channel_id: int) -> Optional[str]:
    path = os.path.join(contest_dir, f"{int(channel_id)}.json")
    return path if os.path.exists(path) else None

async def _count_emoji_on_message(
    channel: discord.TextChannel,
    message_id: int,
    target_emoji: str = ":TreeCone:",
) -> Tuple[int, Optional[discord.Message]]:
    """Fetch the message and count reactions that match target_emoji.
    target_emoji can be:
      - a unicode emoji (e.g. '🍦')
      - a name string to match against custom emoji name (e.g. ':cone:' or 'cone')
    """
    try:
        msg = await channel.fetch_message(int(message_id))
    except Exception as e:
        logger.warning(f"[contest] fetch_message failed for {message_id}: {e}")
        return 0, None

    wanted = target_emoji.strip()
    if wanted.startswith(":") and wanted.endswith(":"):
        wanted = wanted.strip(":")  # ':cone:' -> 'cone'

    total = 0
    for rxn in msg.reactions:
        em = rxn.emoji
        # unicode emoji -> str
        if isinstance(em, str):
            if em == target_emoji or em == wanted:
                total += rxn.count
        else:
            # custom emoji -> PartialEmoji
            name = getattr(em, "name", "") or ""
            if name == wanted:
                total += rxn.count
    return total, msg

async def compute_podium(
    bot: discord.Client,
    contest_dir: str,
    channel_id: int,
    target_emoji: str = ":cone:",
) -> Dict[str, Any]:
    """Return podium summary based on emoji counts.
    Ensures a user can only place once (keeps their highest-scoring entry)."""
    from collections import defaultdict

    path = _db_path(contest_dir, channel_id)
    if not path:
        return {"ok": False, "error": "contest db not found", "entries": []}

    db = TinyDB(path)
    docs = db.all()

    # entries are any doc without _type == 'meta'
    entries = [d for d in docs if d.get("_type") != "meta"]
    logger.info(f"[contest] conclude: found {len(entries)} entries for channel {channel_id}")

    chan = bot.get_channel(int(channel_id))
    if not chan or not isinstance(chan, discord.TextChannel):
        return {"ok": False, "error": "channel not found or not text channel", "entries": []}

    enriched: List[Dict[str, Any]] = []
    for e in entries:
        mid = e.get("message_id") or e.get("msg_id") or e.get("id")
        if not mid:
            continue
        count, msg = await _count_emoji_on_message(chan, int(mid), target_emoji=target_emoji)
        author_id = e.get("author_id") or (getattr(msg, "author", None) and msg.author.id)
        author_name = (e.get("author_name")
                       or (getattr(msg, "author", None) and str(msg.author))
                       or "Unknown")
        att_url = None
        if msg and msg.attachments:
            # pick the first image-ish attachment
            for a in msg.attachments:
                if a.content_type and a.content_type.startswith("image/"):
                    att_url = a.url; break
            if att_url is None and msg.attachments:
                att_url = msg.attachments[0].url
        enriched.append({
            "message_id": int(mid),
            "author_id": int(author_id) if author_id else None,
            "author_name": author_name,
            "score": int(count),
            "created_at": getattr(msg, "created_at", None),
            "jump_url": getattr(msg, "jump_url", None),
            "image_url": att_url,
        })

    if not enriched:
        return {"ok": False, "error": "no valid entries", "entries": []}

    # best entry per author
    best_by_author: Dict[int, Dict[str, Any]] = {}
    for item in enriched:
        aid = item.get("author_id")
        if aid is None:
            continue
        keep = best_by_author.get(aid)
        if not keep:
            best_by_author[aid] = item
        else:
            # prefer higher score; tie-break by earlier timestamp, then by smaller message_id
            if (item["score"], -(item["created_at"].timestamp() if item["created_at"] else 0), -item["message_id"]) > \
               (keep["score"], -(keep["created_at"].timestamp() if keep["created_at"] else 0), -keep["message_id"]):
                best_by_author[aid] = item

    unique_entries = list(best_by_author.values())
    # sort podium
    unique_entries.sort(
        key=lambda x: (x["score"], -(x["created_at"].timestamp() if x["created_at"] else 0), -x["message_id"]),
        reverse=True,
    )

    podium = unique_entries[:3]
    return {
        "ok": True,
        "emoji": target_emoji,
        "entries": enriched,
        "unique": unique_entries,
        "podium": podium,
    }
