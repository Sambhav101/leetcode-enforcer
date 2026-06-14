"""The "I can't solve this" flow (issue #6).

The blocker must never trap the user (DESIGN.md §7), but quitting outright is the
*last* resort. The flow, in order:

1. **Downshift** — instead of the current problem, solve at least 3 *previously
   solved* problems (or 3 Easy ones if there's no history). Clearing them releases
   the user. (UI loop wired with the state store / scheduler — see #22.)
2. **Give up** — type the phrase "I GIVE UP". Releases now, but the app re-triggers
   after a 1-hour cooldown (#23). Every give-up is logged for self-accountability.

This module holds the pure, testable policy: phrase check, fallback selection, and
recording a give-up + its cooldown. It touches only local disk, so it works even if
LeetCode / the LLM are down.
"""

import datetime

from . import config, runtime

REQUIRED_PHRASE = "I GIVE UP"
GIVEUP_COOLDOWN_SECONDS = 3600   # re-trigger 1 hour after a give-up (#23)
FALLBACK_COUNT = 3               # how many downshift problems to require


def verify_phrase(typed: str) -> bool:
    """True if the user typed the confirmation phrase (case/space-insensitive)."""
    return (typed or "").strip().upper() == REQUIRED_PHRASE


def choose_fallback(solved_slugs) -> dict:
    """Decide the downshift challenge offered before a give-up is allowed.

    If the user has solved >= FALLBACK_COUNT problems before, re-serve the most
    recent ones; otherwise fall back to N Easy problems.
    """
    solved = list(dict.fromkeys(solved_slugs or []))  # dedupe, keep order
    if len(solved) >= FALLBACK_COUNT:
        return {"mode": "resolve", "slugs": solved[-FALLBACK_COUNT:]}
    return {"mode": "easy", "count": FALLBACK_COUNT}


def _log_path():
    return config.APP_DIR / "escapes.log"


def log_escape(problem_number, problem_title, reason: str = "") -> str:
    """Append a timestamped record of the bypass; return the written line."""
    config.ensure_app_dir()
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"{ts}\t#{problem_number} {problem_title}\t{reason}\n"
    with open(_log_path(), "a") as f:
        f.write(line)
    return line


def record_giveup(problem_number, problem_title, now=None) -> datetime.datetime:
    """Log a give-up, persist the cooldown, and return the re-trigger time (1h, #23).

    The cooldown is written to runtime state so the next one-shot scheduler tick
    (launchd/cron) sees it and skips the session until it expires.
    """
    now = now or datetime.datetime.now()
    log_escape(problem_number, problem_title, reason="gave up")
    next_trigger = now + datetime.timedelta(seconds=GIVEUP_COOLDOWN_SECONDS)
    runtime.set_cooldown_until(next_trigger)
    return next_trigger
