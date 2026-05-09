"""
G-Pose Contest Module for BigTree.

A weekly contest with optional monthly and yearly meta-championships.
No role creation — roles are configured as IDs in settings.
"""

from __future__ import annotations

import os
import time
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

try:
    import bigtree
    from bigtree.inc.logging import logger
except Exception:
    bigtree = None
    logger = print


# ---- Config keys ----
_ROLE_WEEKLY   = "GPOSE_WEEKLY_ROLE_ID"
_ROLE_MONTHLY  = "GPOSE_MONTHLY_ROLE_ID"
_ROLE_YEARLY   = "GPOSE_YEARLY_ROLE_ID"
_ROLE_SUBMITTER = "GPOSE_SUBMITTER_ROLE_ID"
_CHAN_SUBMISSIONS = "GPOSE_SUBMISSIONS_CHANNEL_ID"
_CHAN_ANNOUNCEMENTS = "GPOSE_ANNOUNCEMENTS_CHANNEL_ID"
_CHAN_POSERS_HALL = "GPOSE_POSERS_HALL_CHANNEL_ID"
_CHAN_LEADERBOARD = "GPOSE_LEADERBOARD_CHANNEL_ID"
_CHAN_PLANNING = "GPOSE_PLANNING_CHANNEL_ID"

# ---- State file ----
def _state_path() -> str:
    base = getattr(bigtree, "contest_dir", "/data/contest") if bigtree else "/data/contest"
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "gpose_contest.json")


def _now_ts() -> float:
    return time.time()


# ---- Dataclasses ----
@dataclass
class WeekEntry:
    message_id: str
    user_id: int
    user_name: str
    submitted_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": str(self.message_id),
            "user_id": int(self.user_id),
            "user_name": str(self.user_name),
            "submitted_at": float(self.submitted_at),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WeekEntry":
        return cls(
            message_id=str(d.get("message_id", "")),
            user_id=int(d.get("user_id", 0)),
            user_name=str(d.get("user_name", "")),
            submitted_at=float(d.get("submitted_at", 0)),
        )


@dataclass
class ContestWeek:
    week: int          # 1-4
    year: int
    month: int
    theme: str
    start_ts: float
    end_ts: float
    status: str = "open"   # open | voting | closed
    entries: List[Dict[str, Any]] = field(default_factory=list)
    winner_user_id: Optional[int] = None
    winner_message_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "week": int(self.week),
            "year": int(self.year),
            "month": int(self.month),
            "theme": str(self.theme),
            "start_ts": float(self.start_ts),
            "end_ts": float(self.end_ts),
            "status": str(self.status),
            "entries": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.entries],
            "winner_user_id": int(self.winner_user_id) if self.winner_user_id else None,
            "winner_message_id": str(self.winner_message_id) if self.winner_message_id else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ContestWeek":
        entries = [WeekEntry.from_dict(e) if isinstance(e, dict) else e for e in d.get("entries", [])]
        w = cls(
            week=int(d.get("week", 1)),
            year=int(d.get("year", datetime.now().year)),
            month=int(d.get("month", 1)),
            theme=str(d.get("theme", "")),
            start_ts=float(d.get("start_ts", 0)),
            end_ts=float(d.get("end_ts", 0)),
            status=str(d.get("status", "open")),
            entries=entries,
            winner_user_id=int(d["winner_user_id"]) if d.get("winner_user_id") else None,
            winner_message_id=str(d["winner_message_id"]) if d.get("winner_message_id") else None,
        )
        return w


@dataclass
class ContestState:
    current_week: Optional[Dict[str, Any]] = None
    weekly_winners: List[Dict[str, Any]] = field(default_factory=list)
    monthly_winners: List[Dict[str, Any]] = field(default_factory=list)
    yearly_winners: List[Dict[str, Any]] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_week": self.current_week,
            "weekly_winners": self.weekly_winners,
            "monthly_winners": self.monthly_winners,
            "yearly_winners": self.yearly_winners,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ContestState":
        return cls(
            current_week=d.get("current_week"),
            weekly_winners=d.get("weekly_winners", []),
            monthly_winners=d.get("monthly_winners", []),
            yearly_winners=d.get("yearly_winners", []),
            config=d.get("config", {}),
        )


# ---- State persistence ----
def _load_state() -> ContestState:
    path = _state_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return ContestState.from_dict(json.load(f))
        except Exception:
            pass
    return ContestState()


def _save_state(state: ContestState) -> None:
    path = _state_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2)


# ---- Config helpers ----
def _get_config(key: str, default: Any = None) -> Any:
    try:
        if bigtree and hasattr(bigtree, "settings") and bigtree.settings:
            return bigtree.settings.get(f"GPOSE.{key}", default)
    except Exception:
        pass
    return os.getenv(f"BIGTREE__GPOSE__{key}", default)


def _config_role(key: str) -> Optional[int]:
    val = _get_config(key)
    if val:
        try:
            return int(val)
        except Exception:
            pass
    return None


# ---- Public API ----
def get_state() -> Dict[str, Any]:
    """Return full contest state as a dict."""
    return _load_state().to_dict()


def get_current_week() -> Optional[ContestWeek]:
    """Return the active contest week if any."""
    state = _load_state()
    if state.current_week:
        return ContestWeek.from_dict(state.current_week)
    return None


def get_config() -> Dict[str, Any]:
    """Return current config (role IDs, channel IDs)."""
    state = _load_state()
    return {
        "weekly_role_id": _config_role(_ROLE_WEEKLY),
        "monthly_role_id": _config_role(_ROLE_MONTHLY),
        "yearly_role_id": _config_role(_ROLE_YEARLY),
        "submitter_role_id": _config_role(_ROLE_SUBMITTER),
        "submissions_channel_id": _get_config(_CHAN_SUBMISSIONS),
        "announcements_channel_id": _get_config(_CHAN_ANNOUNCEMENTS),
        "posers_hall_channel_id": _get_config(_CHAN_POSERS_HALL),
        "planning_channel_id": _get_config(_CHAN_PLANNING),
        "voting_emoji": _get_config("VOTING_EMOJI", "📸"),
        "submission_open": state.current_week is not None and state.current_week.get("status") == "open",
        "leaderboard_channel_id": _get_config(_CHAN_LEADERBOARD),
    }


def set_config(**kwargs) -> Dict[str, Any]:
    """Update config values. Persisted in state file."""
    state = _load_state()
    if not state.config:
        state.config = {}
    for key, val in kwargs.items():
        state.config[key] = val
    _save_state(state)
    return get_config()


def start_contest(
    theme: str,
    week: Optional[int] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    duration_days: float = 7.0,
) -> Dict[str, Any]:
    """
    Open submissions for a new contest week.
    If a contest is already open, returns error.
    """
    state = _load_state()
    if state.current_week and state.current_week.get("status") == "open":
        return {"ok": False, "error": "A contest is already open"}

    now = _now_ts()
    now_dt = datetime.now(timezone.utc)
    week = week or ((now_dt.day - 1) // 7 + 1)
    month = month or now_dt.month
    year = year or now_dt.year

    contest = ContestWeek(
        week=week,
        year=year,
        month=month,
        theme=theme,
        start_ts=now,
        end_ts=now + (duration_days * 86400),
        status="open",
        entries=[],
    )

    state.current_week = contest.to_dict()
    _save_state(state)

    logger.info(f"[gpose] Contest started: week={week} theme={theme}")
    return {
        "ok": True,
        "week": contest.to_dict(),
        "days_remaining": round((contest.end_ts - now) / 86400, 1),
    }


def submit_entry(message_id: str, user_id: int, user_name: str) -> Dict[str, Any]:
    """
    Record a submission for the current open contest.
    """
    state = _load_state()
    if not state.current_week or state.current_week.get("status") != "open":
        return {"ok": False, "error": "No open contest"}

    # Avoid duplicates from same user
    for e in state.current_week.get("entries", []):
        if int(e.get("user_id", 0)) == int(user_id):
            return {"ok": False, "error": "You have already submitted this week"}

    entry = WeekEntry(
        message_id=str(message_id),
        user_id=int(user_id),
        user_name=str(user_name),
        submitted_at=_now_ts(),
    )

    state.current_week.setdefault("entries", []).append(entry.to_dict())
    _save_state(state)

    logger.info(f"[gpose] Submission: user={user_id} message={message_id}")
    return {"ok": True, "entry_count": len(state.current_week["entries"])}


def end_contest(winner_user_id: Optional[int] = None, winner_message_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Close the current contest. If no winner_user_id provided, 
    the contest is left in 'voting' state for manual winner selection.
    """
    state = _load_state()
    if not state.current_week:
        return {"ok": False, "error": "No active contest"}

    week_data = state.current_week
    week_data["status"] = "voting" if winner_user_id is None else "closed"
    week_data["winner_user_id"] = winner_user_id
    week_data["winner_message_id"] = winner_message_id

    if winner_user_id:
        # Archive as weekly winner
        winner_record = {
            "year": week_data.get("year"),
            "month": week_data.get("month"),
            "week": week_data.get("week"),
            "user_id": winner_user_id,
            "message_id": winner_message_id,
            "theme": week_data.get("theme"),
            "won_at": _now_ts(),
        }
        state.weekly_winners.append(winner_record)
        state.current_week = None

    _save_state(state)

    if winner_user_id:
        logger.info(f"[gpose] Contest ended. Winner: user_id={winner_user_id}")
    else:
        logger.info("[gpose] Contest moved to voting state")

    return {
        "ok": True,
        "status": week_data["status"],
        "winner_user_id": winner_user_id,
        "entries_closed": len(week_data.get("entries", [])),
    }


def set_winner(user_id: int, message_id: str) -> Dict[str, Any]:
    """
    Set the winner for the current contest in 'voting' state.
    """
    state = _load_state()
    if not state.current_week:
        return {"ok": False, "error": "No contest in voting state"}

    week_data = state.current_week
    week_data["status"] = "closed"
    week_data["winner_user_id"] = int(user_id)
    week_data["winner_message_id"] = str(message_id)

    # Archive as weekly winner
    winner_record = {
        "year": week_data.get("year"),
        "month": week_data.get("month"),
        "week": week_data.get("week"),
        "user_id": int(user_id),
        "message_id": str(message_id),
        "theme": week_data.get("theme"),
        "won_at": _now_ts(),
    }
    state.weekly_winners.append(winner_record)
    state.current_week = None

    _save_state(state)
    logger.info(f"[gpose] Winner set: user_id={user_id}")
    return {"ok": True, "winner": winner_record}


def get_leaderboard(limit: int = 50) -> Dict[str, Any]:
    """
    Return weekly winners, monthly aggregates, and yearly champions.
    """
    state = _load_state()

    # Build monthly winners from weekly winners
    by_month: Dict[str, List] = {}
    for w in state.weekly_winners:
        key = f"{w.get('year')}-{w.get('month'):02d}"
        by_month.setdefault(key, []).append(w)

    monthly_winners = []
    for key, wins in by_month.items():
        if len(wins) >= 4:  # only months with all 4 weeks
            # Pick winner by... most recent win (or could be tiebreaker)
            last_win = max(wins, key=lambda x: x.get("won_at", 0))
            monthly_winners.append({
                "year": last_win.get("year"),
                "month": last_win.get("month"),
                "user_id": last_win.get("user_id"),
                "user_name": last_win.get("user_name", "unknown"),
                "won_at": last_win.get("won_at"),
            })

    # Build yearly champions
    by_year: Dict[int, Dict[int, int]] = {}
    for w in state.weekly_winners:
        yr = w.get("year")
        uid = w.get("user_id")
        if yr and uid:
            by_year.setdefault(int(yr), {})[int(uid)] = by_year[int(yr)].get(int(uid), 0) + 1

    yearly_winners = []
    for yr, counts in sorted(by_year.items()):
        if counts:
            top = max(counts, key=lambda u: counts[u])
            yearly_winners.append({
                "year": yr,
                "user_id": top,
                "wins": counts[top],
            })

    return {
        "weekly_winners": state.weekly_winners[-limit:],
        "monthly_winners": monthly_winners,
        "yearly_winners": yearly_winners,
    }


def get_submissions() -> List[Dict[str, Any]]:
    """Return current contest entries for voting."""
    state = _load_state()
    if not state.current_week:
        return []
    return state.current_week.get("entries", [])


def get_weekly_winners_for_month(year: int, month: int) -> List[Dict[str, Any]]:
    """Return the 4 weekly winners for a given month."""
    state = _load_state()
    return [
        w for w in state.weekly_winners
        if w.get("year") == year and w.get("month") == month
    ]


def check_submitter_role_configured() -> bool:
    """Return True if all required config values are set."""
    cfg = get_config()
    return bool(cfg.get("submitter_role_id") and cfg.get("submissions_channel_id"))


def reset_state() -> Dict[str, Any]:
    """Clear all contest state. For testing/admin only."""
    state = ContestState()
    _save_state(state)
    return {"ok": True, "message": "State cleared"}