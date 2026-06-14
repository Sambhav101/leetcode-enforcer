"""Tests for persistent transient scheduler state (give-up cooldown, #23)."""

import datetime

import pytest

from leetcode_enforcer import config, runtime


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    d = tmp_path / ".leetcode-enforcer"
    monkeypatch.setattr(config, "APP_DIR", d)
    monkeypatch.setattr(config, "CONFIG_PATH", d / "config.json")
    return d


def test_cooldown_defaults_to_none(app_dir):
    assert runtime.get_cooldown_until() is None


def test_set_and_get_cooldown_round_trips(app_dir):
    dt = datetime.datetime(2026, 6, 14, 13, 0, 0)
    runtime.set_cooldown_until(dt)
    assert runtime.get_cooldown_until() == dt


def test_set_cooldown_none_clears(app_dir):
    runtime.set_cooldown_until(datetime.datetime(2026, 6, 14, 13, 0, 0))
    runtime.set_cooldown_until(None)
    assert runtime.get_cooldown_until() is None
