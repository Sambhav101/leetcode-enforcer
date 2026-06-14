"""Scheduling policy: when to trigger the blocker and how hard to nag (issue #8).

The decision logic is pure and time-injected so it's fully unit-testable; the actual
daemon loop / launchd agent stays thin (and is finished in #10 / deployment). Honors
a give-up cooldown so the 1h re-trigger (#23) can plug in.
"""

import datetime
from dataclasses import dataclass

from . import config, runtime, state

_UNSET = object()   # distinguishes "not passed" from an explicit None override

NAG_MESSAGES = {
    1: "Time to practice — solve today's problem.",
    2: "Still pending — let's knock out a problem.",
    3: "The day's almost over and your quota isn't met. Solve one now.",
}


@dataclass
class Decision:
    action: str           # "quiet" | "met" | "cooldown" | "waiting" | "nag"
    nag_level: int = 0    # 1..3, only meaningful when action == "nag"
    message: str = ""


def compute_nag_level(now: datetime.datetime, start_hour: int, end_hour: int) -> int:
    """Escalate 1→3 as the active window runs out (more pressure later in the day)."""
    span = max(end_hour - start_hour, 1)
    frac = (now.hour + now.minute / 60 - start_hour) / span
    if frac < 1 / 3:
        return 1
    if frac < 2 / 3:
        return 2
    return 3


def decide(now: datetime.datetime | None = None, *, quota: int, solved_today: int,
           cooldown_until: datetime.datetime | None = None,
           last_nag: datetime.datetime | None = None,
           start_hour: int = 8, end_hour: int = 23,
           nag_interval_min: int = 90) -> Decision:
    """Decide what the scheduler should do right now."""
    now = now or datetime.datetime.now()
    if now.hour < start_hour or now.hour >= end_hour:
        return Decision("quiet")
    if solved_today >= quota:
        return Decision("met")
    if cooldown_until is not None and now < cooldown_until:
        return Decision("cooldown")
    if last_nag is not None and (now - last_nag).total_seconds() < nag_interval_min * 60:
        return Decision("waiting")
    level = compute_nag_level(now, start_hour, end_hour)
    return Decision("nag", nag_level=level, message=NAG_MESSAGES[level])


def decide_now(now: datetime.datetime | None = None,
               cooldown_until=_UNSET,
               last_nag: datetime.datetime | None = None) -> Decision:
    """Convenience: gather live config + state and decide.

    The give-up cooldown (#23) is read from persisted runtime state unless an
    explicit ``cooldown_until`` is supplied (None included, for tests).
    """
    cfg = config.load_config()
    if cooldown_until is _UNSET:
        cooldown_until = runtime.get_cooldown_until()
    return decide(
        now,
        quota=cfg["daily_quota"],
        solved_today=state.solved_today(now),
        cooldown_until=cooldown_until,
        last_nag=last_nag,
        start_hour=cfg["active_start_hour"],
        end_hour=cfg["active_end_hour"],
        nag_interval_min=cfg["nag_interval_minutes"],
    )
