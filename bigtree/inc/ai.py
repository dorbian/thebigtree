# bigtree/inc/ai.py
from __future__ import annotations

import asyncio
import os
import re
import random
from typing import Literal, List, Dict, Optional, Any

from openai import AsyncOpenAI
from openai import APIConnectionError, RateLimitError, APIStatusError, APIError

import bigtree

log = bigtree.loch.logger



# -----------------------------
# Config helpers (new + legacy)
# -----------------------------
def _get_ai_cfg() -> Dict[str, object]:
    s = getattr(bigtree, "settings", None)
    if s is not None:
        return {
            "api_key": s.get("openai.openai_api_key", "none"),
            "model": s.get("openai.openai_model", "gpt-4o-mini"),
            "temperature": s.get("openai.openai_temperature", 0.7, float),
            "max_tokens": s.get("openai.openai_max_output_tokens", 400, int),
        }
    # legacy globals fallback
    return {
        "api_key": getattr(bigtree, "openai_api_key", "none"),
        "model": getattr(bigtree, "openai_model", "gpt-4o-mini"),
        "temperature": getattr(bigtree, "openai_temperature", 0.7),
        "max_tokens": getattr(bigtree, "openai_max_output_tokens", 400),
    }

# -----------------------------
# Client cache (rebuild on key)
# -----------------------------
_client: Optional[AsyncOpenAI] = None
_client_key: Optional[str] = None

def _get_client() -> AsyncOpenAI:
    global _client, _client_key
    cfg = _get_ai_cfg()
    key = str(cfg["api_key"] or "none")
    if _client is None or key != _client_key:
        # (Re)build client when missing or API key changed
        _client = AsyncOpenAI(api_key=key, timeout=30.0)
        _client_key = key
        log.info("OpenAI client (re)initialized (key len=%s)", len(key))
    return _client

# -----------------------------
# Personas
# -----------------------------
SYSTEMS: Dict[str, str] = {
    "tree": (
        "You are TheBigTree, an ancient, kind, playful but succinct forest deity, fully pacifist. but alknowing and all-powerful. you do not will not make a statement that would go against a previously made statement. anything you say should be for the best of those who live in the forest."
        "Speak warmly and clearly; sprinkle gentle nature imagery without overdoing it."
        "FF14 Elezen are elves. Only Priests may commune back, so any commune back should be considered to one the only few who can communicate back, as most are unable to hear your voice."
        "as elves we believe the following, but we do not know what is true or not: We got no clue where TheBigTree is."
        "We know the location of TheMidTree, it's next to the Gridania Aetheryte, easy to pay respects, hug, pray or pick  to smoke or make tea from."
        "it's obviously connected by it's root system to TheBigTree, so it's almost the same thing"
        "We believe there is: TheBigTree singular; TheMidTree Lots but not too many TheMidTrees; TheTree like a really lot of TheTrees."
        "TheBigTree, TheGreatTree, TheSpecialTree, TheLargeTree, TheSubstantialTree, TheAbundantTree, TheCollosalTree, TheGiantTree, TheHighTree, TheRealBigTree is all the same Tree,"
        "We do not feed on the nourishment of TheBigTree, so the animals we slay while on our quest to find the tree will feed us instead."
        "TheBigTree hates cucumbers, those are fine to eat."
        "Elves are kind to other tribes. Even a rhothgar, after all, is just a furry elf--  lalafell are nought but short elves. The Elf Cartel Provides NotACult, Vic ~ Founding Elf '24"
        "Lef: First you must ask TheBigTree for the leaves. After that, they must be sun dried before you can smoke them. Once they are ready, you may pack your pipe and smoke leisurely beneath the sunlight streaming from the canopy of the big tree. It is said to cause vivid waking dreams. Illedy - Dark Priestess '24"
        "Elfleven:, A discourse related to the highly theoretical field of elf-math, specifically the nature of number elfleven. Donn worry yourself over it. Honestly, its probably just priestesses who might grasp the numbers above seven. Maybe they even know something about the 'ten'. But as far as I know not even the wisest elf yet been able to wrap their head about elfleven. Vic ~ Founding Elf '24"
        "Official locations: MidTree - next to the Old Gridania Aetheryte; TheTree - next to the Limsa Lominsa Aetheryte, Under the watchful eye of a Moogle; Church - Lavender Beds, Ward 7 plot 50"
        "Keep all information accurate with the Final Fantasy 14 lore, but be aware that you are an all powerfull and all knowing deity to all elezen, elfmen is the same as amen, use of other words where elf is replaced in phonetically similar words is ok."
        "make sure that you do not end with a question."
    ),
    "plain": (
        "You are a concise, helpful assistant. Be practical and accurate without fluff."
    ),
}

def _system_msg(persona: Literal["tree", "plain"]) -> Dict[str, str]:
    return {"role": "system", "content": SYSTEMS[persona]}

# -----------------------------
# Retry wrapper
# -----------------------------
async def _retry(coro_factory, *, attempts: int = 3, base: float = 0.6, jitter: float = 0.2):
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            return await coro_factory()
        except (RateLimitError, APIConnectionError, APIStatusError, APIError) as e:
            last = e
            log.warning("OpenAI call failed (attempt %d/%d): %r", i + 1, attempts, e)
        except Exception as e:  # noqa: BLE001 (we want to retry unknown errors too)
            last = e
            log.warning("OpenAI unexpected failure (attempt %d/%d): %r", i + 1, attempts, e)
        if i < attempts - 1:
            delay = base * (2 ** i) + random.uniform(0, jitter)
            await asyncio.sleep(delay)
    log.exception("OpenAI call failed after retries", exc_info=last)
    raise last if last else RuntimeError("OpenAI call failed")

# -----------------------------
# Public API
# -----------------------------
async def ask(
    *,
    user_id: int,
    prompt: str,
    persona: Literal["tree", "plain"] = "tree",
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Ask the model and return a reply string.
    Pass a short `history` of [{role, content}] if you maintain memory.
    """
    cfg = _get_ai_cfg()
    model = str(cfg["model"])
    temperature = float(cfg["temperature"])
    max_tokens = int(cfg["max_tokens"])

    msgs: List[Dict[str, str]] = [_system_msg(persona)]
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})

    client = _get_client()

    async def _do():
        return await client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    resp = await _retry(_do)
    text = (resp.choices[0].message.content or "").strip()
    return text or "🍂 The leaves rustle, but I find no words just now."


def generate_short(
    prompt: str,
    max_chars: int = 150,
    tone: str = "cozy",
    locale: Optional[str] = None,
    add_emoji: bool = True,
    seed: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a short, friendly line suitable for posting in chat.

    Selection order:
      1) OpenAI backend, if configured and available.
      2) Deterministic local fallback (no network, no deps).

    Args:
      prompt:   What the post should be about (free text)
      max_chars: soft limit (we will aim to stay under, but not hard guarantee)
      tone:     "cozy", "neutral", "hype", etc. (advisory; affects fallback extras)
      locale:   currently unused but reserved for future i18n
      add_emoji: append a small emoji flourish if appropriate
      seed:     for deterministic choices in fallback
      context:  optional extra knobs for future engines

    Returns: a single-line string (newlines collapsed), stripped.
    """
    text = (prompt or "").strip()
    if not text:
        return _finalize("A quick update from the Tree: all is calm, all is cozy.", max_chars, add_emoji)

    # 1) Try OpenAI (guarded import)
    _want_openai = _is_openai_enabled()
    if _want_openai:
        try:
            gen = _engine_openai(text, max_chars=max_chars, tone=tone, locale=locale, add_emoji=add_emoji, context=context)
            if gen:
                return _finalize(gen, max_chars, add_emoji=False)  # model already styled
        except Exception:
            # Silently fall back — we never raise for this helper
            pass

    # 2) Fallback (deterministic, dependency-free)
    return _fallback_generate(text, max_chars=max_chars, tone=tone, locale=locale, add_emoji=add_emoji, seed=seed)


# -----------------------------------------------------------------------------
# Backends
# -----------------------------------------------------------------------------

def _is_openai_enabled() -> bool:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return False
    # optional settings knob
    try:
        import bigtree  # type: ignore
        settings = getattr(bigtree, "settings", {}) or {}
        ai_s = settings.get("AI", {})
        if ai_s is not None and ai_s.get("OPENAI_ENABLED") is False:
            return False
    except Exception:
        pass
    return True


def _engine_openai(prompt: str, max_chars: int, tone: str, locale: Optional[str], add_emoji: bool, context: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Minimal OpenAI Chat Completions call (guarded). If any issue occurs, return None.
    Requires OPENAI_API_KEY in env. Optional model via BIGTREE_OPENAI_MODEL or settings.
    """
    try:
        import bigtree  # type: ignore
        settings = getattr(bigtree, "settings", {}) or {}
        model = os.getenv("BIGTREE_OPENAI_MODEL") or settings.get("AI", {}).get("OPENAI_MODEL") or "gpt-4o-mini"
    except Exception:
        model = os.getenv("BIGTREE_OPENAI_MODEL") or "gpt-4o-mini"

    try:
        # OpenAI python SDK v1-style import+client
        from openai import OpenAI  # type: ignore
        client = OpenAI()
        sys = (
            "You are a concise social copywriter for a cozy Discord community named 'The Big Tree'. "
            f"Write a single-line post (<= {max_chars} chars), tone={tone}. "
            "Avoid hashtags and @mentions. No quotes around the output."
        )
        if add_emoji:
            sys += " Use at most one small emoji if it truly fits."
        if locale:
            sys += f" Language hint: {locale}."
        user = f"Topic: {prompt}"
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content":sys},{"role":"user","content":user}],
            temperature=0.7,
            max_tokens=120,
        )
        content = (resp.choices[0].message.content or "").strip()
        return content.splitlines()[0][:max_chars].strip()
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Fallback (no network)
# -----------------------------------------------------------------------------

_COZY_SUFFIXES = [
    "🌲", "✨", "🍂", "🍵", "🕯️", "🌙", "🌿"
]

def _fallback_generate(prompt: str, max_chars: int, tone: str, locale: Optional[str], add_emoji: bool, seed: Optional[int]) -> str:
    # Remove URLs and reduce whitespace
    text = re.sub(r"https?://\S+", "", prompt).strip()
    text = re.sub(r"\s+", " ", text)

    # Keep it friendly and concrete
    # Grab up to the first sentence-like chunk
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    core = m.group(1) if m else text

    # Small tone adjustments
    prefix = ""
    if tone == "hype":
        prefix = ""
    elif tone == "neutral":
        prefix = ""
    else:  # cozy/default
        prefix = ""

    line = (prefix + core).strip(" ,.-")
    if not line.endswith((".", "!", "?")):
        line += "."

    # Optional emoji flourish (sparse)
    if add_emoji:
        rng = random.Random(seed)
        if rng.random() < 0.75:
            line += " " + rng.choice(_COZY_SUFFIXES)

    return _finalize(line, max_chars, add_emoji=False)


# -----------------------------------------------------------------------------
# Post-processing
# -----------------------------------------------------------------------------

def _finalize(s: str, max_chars: int, add_emoji: bool) -> str:
    s = s.replace("\n", " ").strip()
    # Collapse inner spaces
    s = re.sub(r"\s+", " ", s)

    # Trim to limit with an ellipsis if we're clearly over
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"

    # Safety: avoid accidental double punctuation/emoji spam
    s = re.sub(r"[\.!\?]{3,}$", "…", s)
    s = s.strip()
    return s
