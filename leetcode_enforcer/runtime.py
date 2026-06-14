"""Persistent transient scheduler state (issue #23).

Some scheduler state outlives a single one-shot ``python -m leetcode_enforcer``
invocation but is *not* solved-history: chiefly the give-up cooldown, the time
before which the blocker must not re-trigger. It lives in its own JSON file
(``~/.leetcode-enforcer/runtime.json``) so it stays separate from the durable
solved log in ``state.json`` and can be cleared without touching history.

Schema::

    {"cooldown_until": "2026-06-14T13:00:00"}   # ISO, or key absent / null
"""

import datetime
import json

from . import config

_RUNTIME_FILE = "runtime.json"


def _path():
    return config.APP_DIR / _RUNTIME_FILE


def load_runtime() -> dict:
    config.ensure_app_dir()
    path = _path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_runtime(data: dict) -> None:
    config.ensure_app_dir()
    _path().write_text(json.dumps(data, indent=2))


def get_cooldown_until() -> datetime.datetime | None:
    """The time before which the blocker must not re-trigger (or None)."""
    raw = load_runtime().get("cooldown_until")
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None


def set_cooldown_until(dt: datetime.datetime | None) -> None:
    """Persist (or clear, with None) the give-up cooldown deadline."""
    data = load_runtime()
    if dt is None:
        data.pop("cooldown_until", None)
    else:
        data["cooldown_until"] = dt.isoformat(timespec="seconds")
    save_runtime(data)
