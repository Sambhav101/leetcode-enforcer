"""Smoke tests: the package imports and config bootstrap works.

Uses monkeypatched paths so tests never touch the real ~/.leetcode-enforcer.
"""

import json

import leetcode_enforcer
from leetcode_enforcer import config


def test_package_imports():
    assert leetcode_enforcer.__version__


def test_ensure_app_dir_and_default_config(tmp_path, monkeypatch):
    app_dir = tmp_path / ".leetcode-enforcer"
    monkeypatch.setattr(config, "APP_DIR", app_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", app_dir / "config.json")

    config.ensure_app_dir()

    assert app_dir.is_dir()
    assert (app_dir / "config.json").exists()
    cfg = config.load_config()
    # defaults present
    assert cfg["daily_quota"] == 2
    assert "python3" in cfg["languages"]
    assert cfg["llm_model"] == "qwen3:8b"


def test_load_config_merges_defaults(tmp_path, monkeypatch):
    app_dir = tmp_path / ".leetcode-enforcer"
    cfg_path = app_dir / "config.json"
    monkeypatch.setattr(config, "APP_DIR", app_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    app_dir.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"daily_quota": 5}))

    cfg = config.load_config()
    assert cfg["daily_quota"] == 5          # override respected
    assert cfg["llm_model"] == "qwen3:8b"   # default filled in
