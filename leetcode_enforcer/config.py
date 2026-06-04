"""App paths, directory bootstrap, and config load/save.

All user-specific state lives in ``~/.leetcode-enforcer/`` — outside the repo so
nothing sensitive is ever committed. The LeetCode session cookie is NOT stored
here; it goes in the macOS Keychain (see issue #2).
"""

import json
import os
from pathlib import Path

APP_DIR = Path(os.path.expanduser("~/.leetcode-enforcer"))
CONFIG_PATH = APP_DIR / "config.json"
STATE_PATH = APP_DIR / "state.json"

DEFAULT_CONFIG = {
    # daily quota of accepted solutions before the day is "met"
    "daily_quota": 2,
    # scheduler: only nag during waking hours; escalate as the day runs out (#8)
    "active_start_hour": 8,
    "active_end_hour": 23,
    "nag_interval_minutes": 90,
    # curated banks to draw problems from (issue #15); free-tier only (issue #14)
    "banks": ["neetcode150", "blind75"],
    # submission languages the user may pick (issue #16)
    "languages": ["python3", "cpp", "rust"],
    # local Ollama (qwen) for the Socratic helper (issue #7), reusing memento's setup
    "llm_base_url": "http://localhost:11434/v1",
    "llm_model": "qwen3:8b",
    "llm_timeout_seconds": 120,
}


def ensure_app_dir() -> Path:
    """Create the app dir (private perms) and a default config if missing."""
    APP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    return APP_DIR


def load_config() -> dict:
    """Load config, falling back to defaults for any missing keys."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    APP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
