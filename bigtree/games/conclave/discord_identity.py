"""Discord-facing Forest identity relay helpers for Verdant Conclave."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

import discord

from . import engine


def room_key_for_channel(state: Dict[str, Any], channel_id: int) -> Optional[str]:
    wanted = int(channel_id)
    if wanted == int(state.get("living_thread_id") or 0):
        return "living"
    if wanted == int(state.get("lost_thread_id") or 0):
        return "lost"
    for key, metadata in (state.get("rooms") or {}).items():
        if isinstance(metadata, dict) and int(metadata.get("channel_id") or 0) == wanted:
            return str(key)
    return None


def player_can_speak_in_room(
    state: Dict[str, Any],
    player_obj: Optional[Dict[str, Any]],
    room_key: Optional[str],
) -> bool:
    if not player_obj or player_obj.get("synthetic"):
        return False
    if room_key == "living":
        return bool(player_obj.get("alive", True))
    if room_key == "lost":
        return not bool(player_obj.get("alive", True))
    return False


def sanitise_content(
    state: Dict[str, Any],
    content: str,
    raw_user_mentions: Iterable[int] = (),
) -> str:
    """Remove Discord-user identity handles while keeping conversational intent."""
    text = str(content or "")
    mention_ids = {int(value) for value in raw_user_mentions}
    mention_ids.update(int(value) for value in re.findall(r"<@!?(\d+)>", text))
    for raw_id in mention_ids:
        target = engine.player(state, raw_id)
        replacement = (
            f"@{engine.game_player_name(state, target)}"
            if target is not None
            else "@someone outside the Conclave"
        )
        text = re.sub(rf"<@!?{raw_id}>", replacement, text)
    text = text.replace("@everyone", "everyone").replace("@here", "here")
    return text


async def _attachment_files(message: discord.Message) -> list[discord.File]:
    files: list[discord.File] = []
    for attachment in list(message.attachments)[:10]:
        files.append(await attachment.to_file(use_cached=True))
    return files


def _reply_prefix(reply_to: Optional[str]) -> str:
    if not str(reply_to or "").strip():
        return ""
    name = discord.utils.escape_markdown(str(reply_to).strip())[:80]
    return f"↪ **Replying to {name}**\n"


async def relay_message(
    webhook: discord.Webhook,
    thread: discord.Thread,
    state: Dict[str, Any],
    player_obj: Dict[str, Any],
    message: discord.Message,
    *,
    reply_to: Optional[str] = None,
) -> Optional[discord.WebhookMessage]:
    """Repost one ordinary Discord message under its game-local Forest name."""
    content = sanitise_content(state, message.content, message.raw_mentions)
    files = await _attachment_files(message)
    if not content and not files and message.stickers:
        sticker = str(message.stickers[0].name or "sticker")[:80]
        content = f"🖼️ *Sticker: {discord.utils.escape_markdown(sticker)}*"
    if not content and not files:
        return None
    content = _reply_prefix(reply_to) + content if reply_to else content
    kwargs: Dict[str, Any] = {
        "content": content or None,
        "username": engine.game_player_name(state, player_obj)[:80],
        "thread": thread,
        "allowed_mentions": discord.AllowedMentions.none(),
        "wait": True,
    }
    if files:
        kwargs["files"] = files
    # Deliberately do not forward the Discord avatar: it is identifying data.
    return await webhook.send(**kwargs)


async def relay_text(
    webhook: discord.Webhook,
    thread: discord.Thread,
    state: Dict[str, Any],
    player_obj: Dict[str, Any],
    content: str,
) -> Optional[discord.WebhookMessage]:
    text = sanitise_content(state, content)
    if not text.strip():
        return None
    return await webhook.send(
        content=text,
        username=engine.game_player_name(state, player_obj)[:80],
        thread=thread,
        allowed_mentions=discord.AllowedMentions.none(),
        wait=True,
    )
