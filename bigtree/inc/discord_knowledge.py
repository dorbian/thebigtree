from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "i", "if", "in", "is", "it", "of", "on", "or", "our", "so",
    "that", "the", "their", "this", "to", "was", "we", "were", "what", "when",
    "where", "which", "who", "with", "you", "your",
}


def _tokens(text: str) -> List[str]:
    words = re.findall(r"[\w'-]{2,}", (text or "").lower(), flags=re.UNICODE)
    return [word for word in words if word not in _STOPWORDS][:16]


def score_text(query: str, content: str) -> float:
    haystack = (content or "").lower()
    needle = (query or "").strip().lower()
    if not needle or not haystack:
        return 0.0
    score = 0.0
    if needle in haystack:
        score += 8.0
    tokens = _tokens(needle)
    if not tokens:
        return score
    hits = sum(1 for token in tokens if token in haystack)
    score += float(hits) * 2.0
    if hits == len(tokens):
        score += 3.0
    return score


def _channel_allowed(channel: Any, guild: Any) -> bool:
    if not hasattr(channel, "history"):
        return False
    me = getattr(guild, "me", None)
    if me is None or not hasattr(channel, "permissions_for"):
        return True
    try:
        permissions = channel.permissions_for(me)
        return bool(
            getattr(permissions, "view_channel", True)
            and getattr(permissions, "read_message_history", True)
        )
    except Exception:
        return False




def _iter_searchable_channels(guild: Any):
    seen = set()
    for collection in (getattr(guild, "channels", []) or [], getattr(guild, "threads", []) or []):
        for channel in collection:
            channel_id = str(getattr(channel, "id", ""))
            if not channel_id or channel_id in seen:
                continue
            seen.add(channel_id)
            yield channel

def list_readable_channels(bot: Any) -> List[Dict[str, str]]:
    guild = bot.guilds[0] if getattr(bot, "guilds", None) else None
    if guild is None:
        return []
    result: List[Dict[str, str]] = []
    for channel in _iter_searchable_channels(guild):
        if not _channel_allowed(channel, guild):
            continue
        result.append({
            "id": str(getattr(channel, "id", "")),
            "name": str(getattr(channel, "name", "channel")),
            "category": str(getattr(getattr(channel, "category", None), "name", "") or ""),
        })
    return sorted(result, key=lambda item: (item["category"].lower(), item["name"].lower()))


async def search_discord(
    bot: Any,
    query: str,
    *,
    channel_ids: Optional[Sequence[str]] = None,
    limit: int = 20,
    per_channel: int = 150,
    max_channels: int = 20,
    include_bots: bool = False,
) -> List[Dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    limit = max(1, min(int(limit), 100))
    per_channel = max(20, min(int(per_channel), 500))
    max_channels = max(1, min(int(max_channels), 50))

    guild = bot.guilds[0] if getattr(bot, "guilds", None) else None
    if guild is None:
        return []

    requested = {str(value) for value in (channel_ids or []) if str(value).strip()}
    channels = []
    for channel in _iter_searchable_channels(guild):
        if requested and str(getattr(channel, "id", "")) not in requested:
            continue
        if _channel_allowed(channel, guild):
            channels.append(channel)
        if len(channels) >= max_channels:
            break

    semaphore = asyncio.Semaphore(4)

    async def _scan(channel: Any) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        async with semaphore:
            try:
                async for message in channel.history(limit=per_channel):
                    author = getattr(message, "author", None)
                    if not include_bots and bool(getattr(author, "bot", False)):
                        continue
                    content = str(getattr(message, "content", "") or "").strip()
                    if not content:
                        continue
                    score = score_text(query, content)
                    if score <= 0:
                        continue
                    found.append({
                        "id": str(getattr(message, "id", "")),
                        "channel_id": str(getattr(channel, "id", "")),
                        "channel_name": str(getattr(channel, "name", "channel")),
                        "author_id": str(getattr(author, "id", "")),
                        "author_name": str(getattr(author, "display_name", None) or getattr(author, "name", "unknown")),
                        "content": content[:800],
                        "timestamp": getattr(getattr(message, "created_at", None), "isoformat", lambda: "")(),
                        "jump_url": str(getattr(message, "jump_url", "") or ""),
                        "score": score,
                    })
            except Exception:
                return []
        return found

    batches = await asyncio.gather(*(_scan(channel) for channel in channels))
    merged = [row for batch in batches for row in batch]
    merged.sort(key=lambda row: (float(row.get("score") or 0), str(row.get("timestamp") or "")), reverse=True)
    return merged[:limit]


async def search_context(
    bot: Any,
    query: str,
    channel_ids: Iterable[str],
    *,
    limit: int = 5,
) -> List[str]:
    ids = [str(value) for value in channel_ids if str(value).strip()]
    if not ids:
        return []
    rows = await search_discord(
        bot,
        query,
        channel_ids=ids,
        limit=max(1, min(int(limit), 8)),
        per_channel=160,
        max_channels=min(len(ids), 12),
        include_bots=False,
    )
    return [
        f"#{row['channel_name']} — {row['author_name']}: {row['content']}"
        for row in rows
    ]
