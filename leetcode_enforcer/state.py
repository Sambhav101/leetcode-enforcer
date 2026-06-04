"""Persistent state: solved history + derived progress (issue #9).

Single JSON file at ``~/.leetcode-enforcer/state.json`` is the source of truth.
Each Accepted submission appends a record; everything else (today's count, unique
total, per-day counts, recent slugs) is derived from that log. Kept deliberately
simple/readable so memento can consume the same data for its dashboard (#27) and
the downshift loop can read recent solved slugs (#22).

Schema::

    {"solved": [
        {"slug": "two-sum", "number": 1, "title": "Two Sum",
         "difficulty": "Easy", "lang": "python3", "at": "2026-06-04T13:00:00"},
        ...
    ]}
"""

import datetime
import json

from . import config

DEFAULT_STATE = {"solved": []}


def _state_path():
    return config.APP_DIR / "state.json"


def load_state() -> dict:
    config.ensure_app_dir()
    path = _state_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            data.setdefault("solved", [])
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"solved": []}


def save_state(state: dict) -> None:
    config.ensure_app_dir()
    _state_path().write_text(json.dumps(state, indent=2))


def record_solved(problem, lang: str, now: datetime.datetime | None = None) -> dict:
    """Append an Accepted-submission record and persist it."""
    now = now or datetime.datetime.now()
    entry = {
        "slug": problem.slug,
        "number": problem.number,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "lang": lang,
        "at": now.isoformat(timespec="seconds"),
    }
    state = load_state()
    state["solved"].append(entry)
    save_state(state)
    return entry


# ── derived views ────────────────────────────────────────────────────────────

def _entries() -> list:
    return load_state()["solved"]


def solved_slugs() -> list[str]:
    """All solved slugs in chronological order (may contain repeats)."""
    return [e["slug"] for e in _entries()]


def recent_unique_slugs(n: int) -> list[str]:
    """The n most recently solved *distinct* problems (most recent last)."""
    seen, ordered = set(), []
    for slug in reversed(solved_slugs()):       # newest first
        if slug not in seen:
            seen.add(slug)
            ordered.append(slug)
        if len(ordered) >= n:
            break
    return list(reversed(ordered))               # back to chronological


def unique_count() -> int:
    return len(set(solved_slugs()))


def count_by_day() -> dict[str, int]:
    """Map of date (YYYY-MM-DD) -> number of accepted submissions that day (#27)."""
    counts: dict[str, int] = {}
    for e in _entries():
        day = e["at"][:10]
        counts[day] = counts.get(day, 0) + 1
    return counts


def solved_today(now: datetime.datetime | None = None) -> int:
    today = (now or datetime.datetime.now()).date().isoformat()
    return count_by_day().get(today, 0)


def quota_remaining(quota: int, now: datetime.datetime | None = None) -> int:
    return max(0, quota - solved_today(now))


def quota_met(quota: int, now: datetime.datetime | None = None) -> bool:
    return quota_remaining(quota, now) == 0
