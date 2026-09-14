"""Pure state machine for Verdant Conclave.

The engine deliberately knows nothing about Discord or Dalamud.  That keeps
secret-role rules testable and lets Discord, the web API and Forest share one
source of truth.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import random
import secrets
from typing import Any, Dict, Iterable, List, Optional, Tuple

MODULE = "conclave"
VERSION = 1
MIN_PLAYERS = 5
MAX_PLAYERS = 15
TEST_PLAYER_ID_BASE = -900000
FOREST_NAME_REROLL_LIMIT = 3
TEST_PLAYER_NAMES = (
    "Fern", "Moss", "Willow", "Bramble", "Clover", "Juniper", "Rowan",
    "Hazel", "Thistle", "Laurel", "Sorrel", "Ivy", "Alder", "Reed", "Sage",
)
FOREST_NAMES = (
    "Ashleaf", "Alder", "Bramble", "Clover", "Fern", "Hazel", "Juniper",
    "Laurel", "Moss", "Rowan", "Sage", "Silverfern", "Sorrel", "Thistle",
    "Willow", "Yarrow", "Moonfern", "Oakshade", "Reed", "Ivy", "Dewleaf",
    "Pine", "Birch", "Hawthorn", "Foxglove", "Nettle", "Mallow", "Sloe",
    "Elder", "Heather", "Linden", "Elm", "Beech", "Larch", "Holly", "Wren",
)
FOREST_RESERVED_NAMES = {
    "everyone", "here", "admin", "moderator", "host", "thebigtree", "the big tree",
    "concord", "thornbound", "living circle", "lost in the forest", "the tree",
}

PHASE_LOBBY = "lobby"
PHASE_NIGHT = "night"
PHASE_DAY = "day"
PHASE_NOMINATION = "nomination"
PHASE_TRIAL = "trial"
PHASE_JUDGEMENT = "judgement"
PHASE_ENDED = "ended"

FACTION_CONCORD = "concord"
FACTION_THORNBOUND = "thornbound"

ROLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "grovewarden": {
        "name": "Grovewarden",
        "faction": FACTION_CONCORD,
        "action": None,
        "description": "A sworn guardian of the Conclave. Read the room, vote carefully, and expose the Thornbound.",
    },
    "starseer": {
        "name": "Starseer",
        "faction": FACTION_CONCORD,
        "action": "inspect",
        "description": "Each night, read one living elf's aura and learn whether they are Concord or Thornbound.",
    },
    "chirurgeon": {
        "name": "Chirurgeon",
        "faction": FACTION_CONCORD,
        "action": "protect",
        "description": "Each night, ward one living elf against the Thornbound attack. You may ward yourself.",
    },
    "wayfinder": {
        "name": "Wayfinder",
        "faction": FACTION_CONCORD,
        "action": "track",
        "description": "Each night, follow one living elf and privately learn whom they visited, if anyone.",
    },
    "boughwatcher": {
        "name": "Boughwatcher",
        "faction": FACTION_CONCORD,
        "action": "watch",
        "description": "Each night, keep watch over one living elf and privately learn who visited them.",
    },
    "thornweaver": {
        "name": "Thornweaver",
        "faction": FACTION_THORNBOUND,
        "action": "block",
        "description": "Each night, ensnare one Concord elf and prevent their night gift from taking effect.",
    },
    "thornblade": {
        "name": "Thornblade",
        "faction": FACTION_THORNBOUND,
        "action": "attack",
        "description": "At night, choose a Concord target. Thornbound votes combine into one faction attack.",
    },
}


class GameError(ValueError):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_state(
    game_id: str,
    *,
    title: str,
    guild_id: int,
    channel_id: int,
    host_user_id: int,
    dedicated_channel: bool,
) -> Dict[str, Any]:
    return {
        "version": VERSION,
        "game_id": str(game_id),
        "title": (title or "Verdant Conclave").strip()[:100],
        "guild_id": int(guild_id),
        "channel_id": int(channel_id),
        "host_user_id": int(host_user_id),
        "dedicated_channel": bool(dedicated_channel),
        "panel_message_id": None,
        "living_thread_id": None,
        "lost_thread_id": None,
        "rooms": {},
        "identity": {
            "aliases_enabled": True,
            "mode": "immersive",
            "choice": "both",
        },
        "relay": {
            "channel_id": None,
            "webhook_id": None,
        },
        "test_mode": False,
        "phase": PHASE_LOBBY,
        "night": 0,
        "day": 0,
        "players": {},
        "night_actions": {},
        "nomination_votes": {},
        "judgement_votes": {},
        "on_trial": None,
        "winner": None,
        "ended_reason": None,
        "public_events": [],
        "rules": {
            "min_players": MIN_PLAYERS,
            "max_players": MAX_PLAYERS,
            "reveal_roles_on_death": True,
            "reveal_last_will_on_death": True,
        },
        "created_at": _now(),
        "updated_at": _now(),
    }


def clone(state: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(state)


def _players(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    players = state.setdefault("players", {})
    if not isinstance(players, dict):
        raise GameError("Corrupt Conclave player state.", "corrupt")
    return players


def player(state: Dict[str, Any], user_id: int | str) -> Optional[Dict[str, Any]]:
    return _players(state).get(str(user_id))


def living_players(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in _players(state).values() if bool(p.get("alive", True))]


def add_player(state: Dict[str, Any], user_id: int, display_name: str) -> Dict[str, Any]:
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("The Conclave has already begun.", "started")
    players = _players(state)
    key = str(int(user_id))
    if key in players:
        players[key]["display_name"] = (display_name or players[key].get("display_name") or key)[:80]
        state["updated_at"] = _now()
        return state
    limit = int((state.get("rules") or {}).get("max_players") or MAX_PLAYERS)
    if len(players) >= limit:
        raise GameError(f"The Conclave is full ({limit} players).", "full")
    players[key] = {
        "user_id": int(user_id),
        "display_name": (display_name or f"Elf {user_id}")[:80],
        "forest_name": None,
        "forest_name_rerolls": 0,
        "forest_name_spoken": False,
        "dm_delivery": None,
        "alive": True,
        "role": None,
        "faction": None,
        "joined_at": _now(),
        "private_notes": [],
        "last_will": "",
    }
    state["updated_at"] = _now()
    return state


def set_forest_name(state: Dict[str, Any], user_id: int, forest_name: str) -> Dict[str, Any]:
    """Persist one game-local public identity without changing Discord identity."""
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("Forest names can only be changed while the Conclave is gathering.", "started")
    player_obj = player(state, user_id)
    if player_obj is None:
        raise GameError("Join the Conclave before choosing a Forest name.", "not_joined")
    name = " ".join(str(forest_name or "").strip().split())
    existing = str(player_obj.get("forest_name") or "").strip()
    if player_obj.get("forest_name_spoken") and existing and existing.casefold() != name.casefold():
        raise GameError("That Forest name has already been heard in the circle.", "forest_name_locked")
    if len(name) < 2 or len(name) > 32 or not any(ch.isalpha() for ch in name):
        raise GameError("Forest names must be between 2 and 32 characters.", "bad_forest_name")
    if any(ch in name for ch in "@#`<>\\"):
        raise GameError("That Forest name contains characters the Conclave does not accept.", "bad_forest_name")
    folded = name.casefold()
    reserved = set(FOREST_RESERVED_NAMES)
    reserved.update(
        str(definition.get("name") or "").strip().casefold()
        for definition in ROLE_DEFINITIONS.values()
    )
    if folded in reserved:
        raise GameError("That Forest name is reserved by the Conclave.", "forest_name_reserved")
    for other in _players(state).values():
        if int(other.get("user_id") or 0) == int(user_id):
            continue
        if str(other.get("forest_name") or "").strip().casefold() == folded:
            raise GameError("That Forest name already belongs to another elf in this Conclave.", "forest_name_taken")
    player_obj["forest_name"] = name
    state["updated_at"] = _now()
    return state


def generate_forest_name(
    state: Dict[str, Any],
    *,
    rng: Optional[random.Random] = None,
) -> str:
    """Choose a short, memorable game-local name that is not already assigned."""
    used = {
        str(p.get("forest_name") or "").strip().casefold()
        for p in _players(state).values()
        if str(p.get("forest_name") or "").strip()
    }
    available = [name for name in FOREST_NAMES if name.casefold() not in used]
    if not available:
        raise GameError("The Forest has run out of unique names for this Conclave.", "forest_names_exhausted")
    chooser = rng if rng is not None else secrets.SystemRandom()
    return str(chooser.choice(available))


def ensure_forest_name(
    state: Dict[str, Any],
    user_id: int,
    *,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    player_obj = player(state, user_id)
    if player_obj is None:
        raise GameError("Join the Conclave before receiving a Forest name.", "not_joined")
    if player_obj.get("synthetic") or str(player_obj.get("forest_name") or "").strip():
        return state
    player_obj["forest_name"] = generate_forest_name(state, rng=rng)
    state["updated_at"] = _now()
    return state


def reroll_forest_name(
    state: Dict[str, Any],
    user_id: int,
    *,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("Forest names settle when the Conclave begins.", "started")
    identity = state.get("identity") or {}
    if not bool(identity.get("aliases_enabled", False)):
        raise GameError("This Conclave knows you by your usual name.", "aliases_disabled")
    if str(identity.get("choice") or "both") not in {"generated", "both"}:
        raise GameError("This Conclave asks each elf to choose their own Forest name.", "custom_name_only")
    player_obj = player(state, user_id)
    if player_obj is None:
        raise GameError("Join the Conclave before receiving another Forest name.", "not_joined")
    if player_obj.get("forest_name_spoken"):
        raise GameError("Your Forest name has already been heard in the circle.", "forest_name_locked")
    count = int(player_obj.get("forest_name_rerolls") or 0)
    if count >= FOREST_NAME_REROLL_LIMIT:
        raise GameError("The Forest has offered all of your names for this gathering.", "forest_name_rerolls_exhausted")
    player_obj["forest_name"] = generate_forest_name(state, rng=rng)
    player_obj["forest_name_rerolls"] = count + 1
    state["updated_at"] = _now()
    return state


def mark_forest_name_spoken(state: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    player_obj = player(state, user_id)
    if player_obj is not None and not player_obj.get("synthetic"):
        player_obj["forest_name_spoken"] = True
        state["updated_at"] = _now()
    return state


def set_dm_preference(state: Dict[str, Any], user_id: int, enabled: bool) -> Dict[str, Any]:
    player_obj = player(state, user_id)
    if player_obj is None:
        raise GameError("You are not part of this Conclave.", "not_player")
    policy = str((state.get("server_policy") or {}).get("dm_delivery") or "optional")
    if policy != "optional":
        raise GameError("Private-message delivery is fixed for this Conclave.", "dm_delivery_fixed")
    player_obj["dm_delivery"] = bool(enabled)
    state["updated_at"] = _now()
    return state


def wants_dm_delivery(state: Dict[str, Any], user_id: int) -> bool:
    policy = str((state.get("server_policy") or {}).get("dm_delivery") or "optional")
    if policy == "on":
        return True
    if policy == "off":
        return False
    player_obj = player(state, user_id)
    return bool(player_obj and player_obj.get("dm_delivery") is True)


def public_player_name(player_obj: Optional[Dict[str, Any]]) -> str:
    """Return the game-facing name while retaining the Discord name internally."""
    obj = player_obj or {}
    return str(obj.get("forest_name") or obj.get("display_name") or f"Elf {obj.get('user_id') or '?'}")


def game_player_name(state: Dict[str, Any], player_obj: Optional[Dict[str, Any]]) -> str:
    """Name allowed to appear in game-facing text for this session."""
    obj = player_obj or {}
    if obj.get("synthetic"):
        name = str(obj.get("display_name") or "Elf")
        if "·" in name:
            name = name.split("·", 1)[1].strip()
        return name or "Elf"
    aliases = bool((state.get("identity") or {}).get("aliases_enabled", False))
    if aliases:
        return str(obj.get("forest_name") or "Unnamed elf")
    return str(obj.get("display_name") or f"Elf {obj.get('user_id') or '?'}")


def register_room(
    state: Dict[str, Any],
    room_key: str,
    channel_id: int,
    *,
    purpose: str,
    lifecycle: str = "game",
    private: bool = True,
) -> Dict[str, Any]:
    """Register a Discord space owned by this game."""
    key = str(room_key or "").strip().lower()
    if not key:
        raise GameError("Room key is required.", "bad_room")
    rooms = state.setdefault("rooms", {})
    if not isinstance(rooms, dict):
        rooms = {}
        state["rooms"] = rooms
    rooms[key] = {
        "channel_id": int(channel_id),
        "purpose": str(purpose or key)[:80],
        "lifecycle": str(lifecycle or "game")[:24],
        "private": bool(private),
        "registered_at": _now(),
    }
    state["updated_at"] = _now()
    return state


def unregister_room(state: Dict[str, Any], room_key: str) -> Dict[str, Any]:
    rooms = state.setdefault("rooms", {})
    if isinstance(rooms, dict):
        rooms.pop(str(room_key or "").strip().lower(), None)
    state["updated_at"] = _now()
    return state


def remove_player(state: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("You cannot leave after the Conclave has begun.", "started")
    _players(state).pop(str(int(user_id)), None)
    state["test_mode"] = any(bool(p.get("synthetic")) for p in _players(state).values())
    state["updated_at"] = _now()
    return state


def is_test_player(player_obj: Optional[Dict[str, Any]]) -> bool:
    return bool((player_obj or {}).get("synthetic"))


def test_players(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in _players(state).values() if is_test_player(p)]


def add_test_players(
    state: Dict[str, Any],
    count: int = 1,
    *,
    target_total: Optional[int] = None,
) -> Dict[str, Any]:
    """Add unmistakably synthetic lobby players for operator testing.

    Synthetic players live only inside the Conclave game payload in PostgreSQL;
    no Discord users or persistent BigTree identities are created for them.
    """
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("Test players can only be changed while the Conclave is gathering.", "started")
    players = _players(state)
    limit = int((state.get("rules") or {}).get("max_players") or MAX_PLAYERS)
    if target_total is not None:
        desired = max(0, min(int(target_total), limit))
        count = max(0, desired - len(players))
    count = max(0, min(int(count or 0), limit - len(players)))
    if count <= 0:
        return state

    existing_ids = {int(p.get("user_id") or 0) for p in players.values()}
    synthetic_index = len(test_players(state))
    added = 0
    candidate = TEST_PLAYER_ID_BASE
    while added < count:
        user_id = candidate
        candidate -= 1
        if user_id in existing_ids:
            continue
        name = TEST_PLAYER_NAMES[synthetic_index % len(TEST_PLAYER_NAMES)]
        add_player(state, user_id, f"Test Elf · {name}")
        player_obj = player(state, user_id)
        if player_obj is not None:
            player_obj["synthetic"] = True
            player_obj["test_index"] = synthetic_index + 1
        existing_ids.add(user_id)
        synthetic_index += 1
        added += 1

    state["test_mode"] = bool(test_players(state))
    state["updated_at"] = _now()
    return state


def remove_test_players(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("Test players can only be removed while the Conclave is gathering.", "started")
    players = _players(state)
    for key in [key for key, value in players.items() if is_test_player(value)]:
        players.pop(key, None)
    state["test_mode"] = False
    state["updated_at"] = _now()
    return state


def _prefer_test_targets(targets: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        list(targets),
        key=lambda p: (0 if is_test_player(p) else 1, str(p.get("display_name") or "").lower(), int(p.get("user_id") or 0)),
    )


def simulate_test_players(state: Dict[str, Any]) -> Dict[str, Any]:
    """Submit phase-appropriate choices for synthetic players only.

    This never acts on behalf of a real Discord member. In mixed tests fake
    players prefer other fake players as targets, and they abstain rather than
    automatically condemn a real player during judgement.
    """
    phase = state.get("phase")
    bots = [p for p in living_players(state) if is_test_player(p)]
    acted = 0

    if phase == PHASE_NIGHT:
        actions = state.setdefault("night_actions", {})
        for bot in bots:
            uid = int(bot["user_id"])
            if str(uid) in actions:
                continue
            action = role_definition(bot.get("role")).get("action")
            if not action:
                continue
            targets = _prefer_test_targets(valid_night_targets(state, uid))
            if targets:
                submit_night_action(state, uid, int(targets[0]["user_id"]))
            else:
                submit_night_pass(state, uid)
            acted += 1

    elif phase == PHASE_NOMINATION:
        votes = state.setdefault("nomination_votes", {})
        synthetic_targets = _prefer_test_targets([p for p in living_players(state) if is_test_player(p)])
        preferred_target = synthetic_targets[0] if synthetic_targets else None
        for bot in list(bots):
            if state.get("phase") != PHASE_NOMINATION:
                break
            uid = int(bot["user_id"])
            if str(uid) in votes:
                continue
            target = preferred_target
            if target is None or int(target["user_id"]) == uid or not target.get("alive", True):
                candidates = _prefer_test_targets(valid_nomination_targets(state, uid))
                target = candidates[0] if candidates else None
            if target is not None:
                submit_nomination(state, uid, int(target["user_id"]))
            else:
                submit_nomination_pass(state, uid)
            acted += 1

    elif phase == PHASE_JUDGEMENT:
        votes = state.setdefault("judgement_votes", {})
        accused = player(state, int(state.get("on_trial") or 0))
        verdict = "guilty" if is_test_player(accused) else "abstain"
        for bot in bots:
            uid = int(bot["user_id"])
            if uid == int(state.get("on_trial") or 0) or str(uid) in votes:
                continue
            submit_judgement(state, uid, verdict)
            acted += 1

    state["test_mode"] = bool(test_players(state))
    state["test_last_simulation"] = {"phase": phase, "acted": acted, "at": _now()}
    state["updated_at"] = _now()
    return state


def _role_deck(count: int) -> List[str]:
    if count < MIN_PLAYERS:
        raise GameError(f"At least {MIN_PLAYERS} players are required.", "too_few_players")
    thorn_count = max(1, count // 4)
    # Keep the hostile faction below parity at game start.
    thorn_count = min(thorn_count, max(1, (count - 1) // 2))
    # Keep at least one faction killer. Larger games add a disruptive
    # Thornweaver before adding another Thornblade, producing more varied
    # information instead of simply scaling night kills.
    deck = ["thornblade"]
    for hostile_index in range(1, thorn_count):
        deck.append("thornweaver" if hostile_index == 1 else "thornblade")

    deck.append("starseer")
    if len(deck) < count:
        deck.append("chirurgeon")
    if count >= 7 and len(deck) < count:
        deck.append("wayfinder")
    if count >= 9 and len(deck) < count:
        deck.append("boughwatcher")
    deck.extend(["grovewarden"] * (count - len(deck)))
    return deck


def role_roster(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the public role composition without revealing assignments."""
    players = list(_players(state).values())
    role_ids: List[str]
    if state.get("phase") == PHASE_LOBBY:
        if len(players) < int((state.get("rules") or {}).get("min_players") or MIN_PLAYERS):
            return []
        role_ids = _role_deck(len(players))
    else:
        role_ids = [str(p.get("role") or "") for p in players if p.get("role")]
    counts = Counter(role_ids)
    out: List[Dict[str, Any]] = []
    for role_id, count in sorted(
        counts.items(),
        key=lambda item: (role_definition(item[0]).get("faction") == FACTION_THORNBOUND, role_definition(item[0]).get("name", item[0])),
    ):
        definition = role_definition(role_id)
        out.append({
            "role_id": role_id,
            "name": definition.get("name") or role_id,
            "faction": definition.get("faction"),
            "count": int(count),
        })
    return out


def start_game(state: Dict[str, Any], *, rng: Optional[random.Random] = None) -> Dict[str, Any]:
    if state.get("phase") != PHASE_LOBBY:
        raise GameError("The Conclave is not in its lobby.", "wrong_phase")
    players = list(_players(state).values())
    if len(players) < int((state.get("rules") or {}).get("min_players") or MIN_PLAYERS):
        raise GameError(f"At least {MIN_PLAYERS} players are required.", "too_few_players")
    identity = state.get("identity") or {}
    if bool(identity.get("aliases_enabled", False)):
        missing = [
            p for p in players
            if not p.get("synthetic") and not str(p.get("forest_name") or "").strip()
        ]
        if str(identity.get("choice") or "both") == "custom" and missing:
            raise GameError(
                "Every elf must choose a Forest name before the Conclave begins.",
                "forest_name_required",
            )
        for p in missing:
            ensure_forest_name(state, int(p["user_id"]))
    deck = _role_deck(len(players))
    shuffler = rng if rng is not None else secrets.SystemRandom()
    shuffler.shuffle(deck)
    shuffler.shuffle(players)
    for p, role_id in zip(players, deck):
        role = ROLE_DEFINITIONS[role_id]
        p["role"] = role_id
        p["faction"] = role["faction"]
        p["alive"] = True
        p["private_notes"] = []
    state["phase"] = PHASE_NIGHT
    state["night"] = 1
    state["day"] = 0
    state["night_actions"] = {}
    state["nomination_votes"] = {}
    state["judgement_votes"] = {}
    state["on_trial"] = None
    state["public_events"] = ["The Verdant Conclave has begun. Night settles over the boughs."]
    state["updated_at"] = _now()
    return state


def role_definition(role_id: Optional[str]) -> Dict[str, Any]:
    return ROLE_DEFINITIONS.get(str(role_id or ""), {})


def actionable_player_ids(state: Dict[str, Any]) -> List[str]:
    if state.get("phase") != PHASE_NIGHT:
        return []
    out = []
    for p in living_players(state):
        role = role_definition(p.get("role"))
        if role.get("action"):
            out.append(str(p["user_id"]))
    return out


def night_readiness(state: Dict[str, Any]) -> Tuple[int, int]:
    required = actionable_player_ids(state)
    actions = state.get("night_actions") or {}
    ready = sum(1 for uid in required if uid in actions)
    return ready, len(required)


def valid_night_targets(state: Dict[str, Any], actor_id: int) -> List[Dict[str, Any]]:
    actor = player(state, actor_id)
    if not actor or not actor.get("alive"):
        return []
    action = role_definition(actor.get("role")).get("action")
    if not action:
        return []
    out = []
    for target in living_players(state):
        if action in {"inspect", "track", "watch", "block"} and target["user_id"] == actor["user_id"]:
            continue
        if action in {"attack", "block"} and target.get("faction") == FACTION_THORNBOUND:
            continue
        out.append(target)
    return out


def submit_night_action(state: Dict[str, Any], actor_id: int, target_id: int) -> Dict[str, Any]:
    if state.get("phase") != PHASE_NIGHT:
        raise GameError("Night actions are only available during Night.", "wrong_phase")
    actor = player(state, actor_id)
    target = player(state, target_id)
    if not actor or not actor.get("alive"):
        raise GameError("You are not a living player in this Conclave.", "not_player")
    if not target or not target.get("alive"):
        raise GameError("That target is not available.", "bad_target")
    action = role_definition(actor.get("role")).get("action")
    if not action:
        raise GameError("Your role has no night action.", "no_action")
    valid = {int(p["user_id"]) for p in valid_night_targets(state, actor_id)}
    if int(target_id) not in valid:
        raise GameError("Your role cannot target that elf.", "bad_target")
    state.setdefault("night_actions", {})[str(int(actor_id))] = int(target_id)
    state["updated_at"] = _now()
    return state


def submit_night_pass(state: Dict[str, Any], actor_id: int) -> Dict[str, Any]:
    """Record an intentional no-action choice for a night role.

    Readiness is based on the presence of a choice, not whether the choice has
    a target. This lets the host distinguish an intentional pass from a player
    who has not responded yet.
    """
    if state.get("phase") != PHASE_NIGHT:
        raise GameError("Night choices are only available during Night.", "wrong_phase")
    actor = player(state, actor_id)
    if not actor or not actor.get("alive"):
        raise GameError("You are not a living player in this Conclave.", "not_player")
    action = role_definition(actor.get("role")).get("action")
    if not action:
        raise GameError("Your role has no night action to pass.", "no_action")
    state.setdefault("night_actions", {})[str(int(actor_id))] = None
    state["updated_at"] = _now()
    return state


def set_last_will(state: Dict[str, Any], user_id: int, text: str) -> Dict[str, Any]:
    p = player(state, user_id)
    if not p:
        raise GameError("You are not part of this Conclave.", "not_player")
    if not p.get("alive", True):
        raise GameError("A fallen elf can no longer change their last will.", "dead")
    cleaned = " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())
    if len(cleaned) > 500:
        raise GameError("Last wills are limited to 500 characters.", "too_long")
    p["last_will"] = cleaned
    state["updated_at"] = _now()
    return state


def _append_private(player_obj: Dict[str, Any], text: str) -> None:
    notes = player_obj.setdefault("private_notes", [])
    notes.append({"at": _now(), "text": text})
    del notes[:-20]


def _kill(state: Dict[str, Any], target: Dict[str, Any], cause: str) -> str:
    target["alive"] = False
    role = role_definition(target.get("role"))
    reveal = bool((state.get("rules") or {}).get("reveal_roles_on_death", True))
    role_text = f" They were a **{role.get('name', 'Unknown')}**." if reveal else ""
    result = f"{game_player_name(state, target)} fell {cause}.{role_text}"
    reveal_will = bool((state.get("rules") or {}).get("reveal_last_will_on_death", True))
    last_will = str(target.get("last_will") or "").strip()
    if reveal_will and last_will:
        result += f"\n📜 Last will: {last_will[:500]}"
    return result


def _check_winner(state: Dict[str, Any]) -> Optional[str]:
    living = living_players(state)
    thorn = [p for p in living if p.get("faction") == FACTION_THORNBOUND]
    concord = [p for p in living if p.get("faction") == FACTION_CONCORD]
    if not thorn:
        return FACTION_CONCORD
    if len(thorn) >= len(concord):
        return FACTION_THORNBOUND
    return None


def _finish_if_won(state: Dict[str, Any]) -> bool:
    winner = _check_winner(state)
    if not winner:
        return False
    state["winner"] = winner
    state["phase"] = PHASE_ENDED
    state["ended_reason"] = "victory"
    label = "The Concord" if winner == FACTION_CONCORD else "The Thornbound"
    state.setdefault("public_events", []).append(f"**{label} claim victory.**")
    state["updated_at"] = _now()
    return True


def _resolve_night(state: Dict[str, Any]) -> List[str]:
    actions = state.get("night_actions") or {}
    players = _players(state)
    protected: set[int] = set()
    blocked: set[int] = set()
    attacks: List[int] = []
    public: List[str] = []

    # Disruption resolves first. Only currently-living actors with a valid
    # recorded target can affect the night. A block is itself a visit, which
    # Boughwatchers may observe.
    for actor_id, target_id in list(actions.items()):
        actor = players.get(str(actor_id))
        target = players.get(str(target_id))
        if not actor or not actor.get("alive") or not target or not target.get("alive"):
            continue
        if role_definition(actor.get("role")).get("action") == "block":
            if target.get("faction") != FACTION_THORNBOUND:
                blocked.add(int(target_id))

    # Protection and faction attacks establish the public night outcome.
    for actor_id, target_id in list(actions.items()):
        actor = players.get(str(actor_id))
        target = players.get(str(target_id))
        if not actor or not actor.get("alive") or not target or not target.get("alive"):
            continue
        if int(actor_id) in blocked:
            continue
        action = role_definition(actor.get("role")).get("action")
        if action == "protect":
            protected.add(int(target_id))
        elif action == "attack" and target.get("faction") != FACTION_THORNBOUND:
            attacks.append(int(target_id))

    # Information roles resolve against the final visit map. Their results are
    # private notes only and therefore never leak into the public game panel.
    for actor_id, target_id in list(actions.items()):
        actor = players.get(str(actor_id))
        target = players.get(str(target_id))
        if not actor or not actor.get("alive") or not target or not target.get("alive"):
            continue
        action = role_definition(actor.get("role")).get("action")
        if int(actor_id) in blocked:
            _append_private(actor, f"Night {state.get('night')}: your night gift was tangled in thorns.")
            continue
        if action == "inspect":
            faction = target.get("faction")
            aura = "Thornbound" if faction == FACTION_THORNBOUND else "Concord"
            _append_private(actor, f"Night {state.get('night')}: {game_player_name(state, target)} carries a **{aura}** aura.")
        elif action == "track":
            target_action = actions.get(str(int(target_id)))
            if int(target_id) in blocked or target_action is None:
                detail = "visited no one"
            else:
                visited = players.get(str(target_action))
                detail = f"visited **{game_player_name(state, visited)}**" if visited else "vanished beyond your trail"
            _append_private(actor, f"Night {state.get('night')}: {game_player_name(state, target)} {detail}.")
        elif action == "watch":
            visitors: List[str] = []
            for visitor_id, visited_id in actions.items():
                # ``None`` is an intentional pass.  Treat it as "no visit"
                # rather than trying to coerce it to an integer.  Without
                # this guard a Boughwatcher resolving on a night where any
                # other actionable role deliberately passed could crash the
                # entire night resolution with ``TypeError: int(None)``.
                if visited_id is None:
                    continue
                try:
                    visited_int = int(visited_id)
                    visitor_int = int(visitor_id)
                except (TypeError, ValueError):
                    continue
                if visited_int != int(target_id) or visitor_int in blocked:
                    continue
                visitor = players.get(str(visitor_id))
                if visitor and visitor.get("alive") and visitor_int != int(actor_id):
                    visitors.append(game_player_name(state, visitor))
            visitors = sorted(set(visitors), key=str.lower)
            detail = ", ".join(f"**{name}**" for name in visitors) if visitors else "no one"
            _append_private(actor, f"Night {state.get('night')}: you saw {detail} visit {game_player_name(state, target)}.")

    if attacks:
        counts = Counter(attacks)
        high = max(counts.values())
        candidates = sorted(uid for uid, votes in counts.items() if votes == high)
        # Deterministic tie-breaker keeps state recovery/replays predictable.
        victim_id = candidates[0]
        victim = players.get(str(victim_id))
        if victim:
            if victim_id in protected:
                public.append("A Thornbound strike was turned aside by a hidden ward.")
            else:
                public.append(_kill(state, victim, "beneath the night's thorns"))
    else:
        public.append("The canopy stirs, but dawn finds no new victim.")

    state["night_actions"] = {}
    state["public_events"] = public
    return public


def nomination_readiness(state: Dict[str, Any]) -> Tuple[int, int]:
    living = living_players(state)
    voters = {str(p["user_id"]) for p in living}
    votes = state.get("nomination_votes") or {}
    return sum(1 for uid in voters if uid in votes), len(voters)


def submit_nomination(state: Dict[str, Any], voter_id: int, target_id: int) -> Dict[str, Any]:
    if state.get("phase") != PHASE_NOMINATION:
        raise GameError("Nominations are not open.", "wrong_phase")
    voter = player(state, voter_id)
    target = player(state, target_id)
    if not voter or not voter.get("alive"):
        raise GameError("Only living players may nominate.", "not_player")
    if not target or not target.get("alive"):
        raise GameError("That elf cannot be nominated.", "bad_target")
    if int(voter_id) == int(target_id):
        raise GameError("You cannot nominate yourself.", "bad_target")
    votes = state.setdefault("nomination_votes", {})
    votes[str(int(voter_id))] = int(target_id)
    tally = Counter(int(v) for v in votes.values() if v is not None)
    threshold = (len(living_players(state)) // 2) + 1
    if tally and max(tally.values()) >= threshold:
        target = max(tally.items(), key=lambda item: (item[1], -item[0]))[0]
        state["on_trial"] = int(target)
        state["phase"] = PHASE_TRIAL
        state["judgement_votes"] = {}
        accused = player(state, target)
        state["public_events"] = [f"{game_player_name(state, accused)} has been called before the Conclave for trial."] if accused else []
    state["updated_at"] = _now()
    return state


def submit_nomination_pass(state: Dict[str, Any], voter_id: int) -> Dict[str, Any]:
    if state.get("phase") != PHASE_NOMINATION:
        raise GameError("Nominations are not open.", "wrong_phase")
    voter = player(state, voter_id)
    if not voter or not voter.get("alive"):
        raise GameError("Only living players may pass a nomination.", "not_player")
    state.setdefault("nomination_votes", {})[str(int(voter_id))] = None
    state["updated_at"] = _now()
    return state


def valid_nomination_targets(state: Dict[str, Any], voter_id: int) -> List[Dict[str, Any]]:
    return [p for p in living_players(state) if int(p["user_id"]) != int(voter_id)]


def judgement_readiness(state: Dict[str, Any]) -> Tuple[int, int]:
    accused = state.get("on_trial")
    eligible = [p for p in living_players(state) if int(p["user_id"]) != int(accused or 0)]
    votes = state.get("judgement_votes") or {}
    return sum(1 for p in eligible if str(p["user_id"]) in votes), len(eligible)


def submit_judgement(state: Dict[str, Any], voter_id: int, verdict: str) -> Dict[str, Any]:
    if state.get("phase") != PHASE_JUDGEMENT:
        raise GameError("Judgement is not open.", "wrong_phase")
    voter = player(state, voter_id)
    if not voter or not voter.get("alive"):
        raise GameError("Only living players may judge.", "not_player")
    if int(voter_id) == int(state.get("on_trial") or 0):
        raise GameError("The accused cannot vote on their own judgement.", "accused")
    verdict = str(verdict or "").strip().lower()
    if verdict not in {"guilty", "innocent", "abstain"}:
        raise GameError("Verdict must be guilty, innocent, or abstain.", "bad_verdict")
    state.setdefault("judgement_votes", {})[str(int(voter_id))] = verdict
    state["updated_at"] = _now()
    return state


def _resolve_judgement(state: Dict[str, Any]) -> List[str]:
    accused_id = int(state.get("on_trial") or 0)
    accused = player(state, accused_id)
    votes = state.get("judgement_votes") or {}
    guilty = sum(1 for v in votes.values() if v == "guilty")
    innocent = sum(1 for v in votes.values() if v == "innocent")
    public: List[str] = [f"Judgement: **{guilty} guilty**, **{innocent} innocent**."]
    if accused and accused.get("alive") and guilty > innocent:
        public.append(_kill(state, accused, "by decree of the Conclave"))
    elif accused:
        public.append(f"{game_player_name(state, accused)} is released from trial.")
    state["on_trial"] = None
    state["nomination_votes"] = {}
    state["judgement_votes"] = {}
    state["public_events"] = public
    return public


def advance_phase(state: Dict[str, Any]) -> Dict[str, Any]:
    phase = state.get("phase")
    if phase == PHASE_LOBBY:
        raise GameError("The Conclave must begin before it can continue.", "wrong_phase")
    if phase == PHASE_ENDED:
        raise GameError("This Conclave has ended.", "ended")

    if phase == PHASE_NIGHT:
        _resolve_night(state)
        if not _finish_if_won(state):
            state["phase"] = PHASE_DAY
            state["day"] = int(state.get("day") or 0) + 1
    elif phase == PHASE_DAY:
        state["phase"] = PHASE_NOMINATION
        state["nomination_votes"] = {}
        state["public_events"] = ["Nominations are open. Choose one living elf to call to trial."]
    elif phase == PHASE_NOMINATION:
        # Host may close a nomination round that did not reach majority.
        state["phase"] = PHASE_NIGHT
        state["night"] = int(state.get("night") or 0) + 1
        state["nomination_votes"] = {}
        state["public_events"] = ["No trial was formed before dusk. Night returns."]
    elif phase == PHASE_TRIAL:
        state["phase"] = PHASE_JUDGEMENT
        state["judgement_votes"] = {}
        state["public_events"] = ["The defence is complete. Cast your judgement: guilty or innocent."]
    elif phase == PHASE_JUDGEMENT:
        _resolve_judgement(state)
        if not _finish_if_won(state):
            state["phase"] = PHASE_NIGHT
            state["night"] = int(state.get("night") or 0) + 1
    else:
        raise GameError("Unknown Conclave phase.", "corrupt")
    state["updated_at"] = _now()
    return state


def end_game(state: Dict[str, Any], reason: str = "ended_by_host") -> Dict[str, Any]:
    state["phase"] = PHASE_ENDED
    state["winner"] = state.get("winner")
    state["ended_reason"] = reason
    state.setdefault("public_events", []).append("The host has closed the Verdant Conclave.")
    state["updated_at"] = _now()
    return state


def public_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy safe for Discord public panels and host integrations."""
    data = {
        "version": state.get("version"),
        "game_id": state.get("game_id"),
        "title": state.get("title"),
        "guild_id": state.get("guild_id"),
        "channel_id": state.get("channel_id"),
        "host_user_id": state.get("host_user_id"),
        "panel_message_id": state.get("panel_message_id"),
        "living_thread_id": state.get("living_thread_id"),
        "lost_thread_id": state.get("lost_thread_id"),
        "test_mode": bool(state.get("test_mode") or test_players(state)),
        "test_player_count": len(test_players(state)),
        "phase": state.get("phase"),
        "night": state.get("night"),
        "day": state.get("day"),
        "winner": state.get("winner"),
        "ended_reason": state.get("ended_reason"),
        "on_trial": state.get("on_trial"),
        "public_events": list(state.get("public_events") or []),
        "role_roster": role_roster(state),
        "aliases_enabled": bool((state.get("identity") or {}).get("aliases_enabled", False)),
        "players": [],
    }
    reveal = bool((state.get("rules") or {}).get("reveal_roles_on_death", True))
    reveal_all = state.get("phase") == PHASE_ENDED
    for p in _players(state).values():
        item = {
            "user_id": p.get("user_id"),
            "display_name": game_player_name(state, p),
            "forest_name": p.get("forest_name"),
            "alive": bool(p.get("alive", True)),
            "synthetic": is_test_player(p),
        }
        if reveal_all or (not item["alive"] and reveal):
            item["role"] = role_definition(p.get("role")).get("name")
        data["players"].append(item)
    data["players"].sort(key=lambda p: str(p.get("display_name") or "").casefold())
    if state.get("phase") == PHASE_NIGHT:
        data["readiness"] = dict(zip(("ready", "required"), night_readiness(state)))
    elif state.get("phase") == PHASE_NOMINATION:
        data["readiness"] = dict(zip(("ready", "required"), nomination_readiness(state)))
    elif state.get("phase") == PHASE_JUDGEMENT:
        data["readiness"] = dict(zip(("ready", "required"), judgement_readiness(state)))
    else:
        data["readiness"] = {"ready": 0, "required": 0}
    return data


def private_player_state(state: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    p = player(state, user_id)
    if not p:
        raise GameError("You are not part of this Conclave.", "not_player")
    role = role_definition(p.get("role"))
    allies: List[str] = []
    if p.get("faction") == FACTION_THORNBOUND:
        allies = [
            game_player_name(state, other)
            for other in _players(state).values()
            if other.get("faction") == FACTION_THORNBOUND
            and int(other.get("user_id")) != int(user_id)
        ]
    return {
        "user_id": p.get("user_id"),
        "display_name": game_player_name(state, p),
        "forest_name": p.get("forest_name"),
        "forest_name_rerolls": int(p.get("forest_name_rerolls") or 0),
        "forest_name_rerolls_left": max(0, FOREST_NAME_REROLL_LIMIT - int(p.get("forest_name_rerolls") or 0)),
        "forest_name_spoken": bool(p.get("forest_name_spoken", False)),
        "dm_delivery_enabled": wants_dm_delivery(state, user_id),
        "dm_delivery_policy": str((state.get("server_policy") or {}).get("dm_delivery") or "optional"),
        "alive": bool(p.get("alive", True)),
        "role_id": p.get("role"),
        "role_name": role.get("name") if role else None,
        "faction": p.get("faction"),
        "ability": role.get("action") if role else None,
        "description": role.get("description") if role else "Your calling will be revealed when the Conclave begins.",
        "allies": allies,
        "notes": list(p.get("private_notes") or []),
        "last_will": str(p.get("last_will") or ""),
        "night_choice_recorded": str(int(user_id)) in (state.get("night_actions") or {}),
        "nomination_recorded": str(int(user_id)) in (state.get("nomination_votes") or {}),
        "judgement_recorded": str(int(user_id)) in (state.get("judgement_votes") or {}),
    }
