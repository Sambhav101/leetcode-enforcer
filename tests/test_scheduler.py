"""Tests for the scheduling decision policy (pure, time-injected)."""

import datetime

import pytest

from leetcode_enforcer import config, runtime, scheduler

D = datetime.datetime


def at(h, m=0):
    return D(2026, 6, 4, h, m)


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    d = tmp_path / ".leetcode-enforcer"
    monkeypatch.setattr(config, "APP_DIR", d)
    monkeypatch.setattr(config, "CONFIG_PATH", d / "config.json")
    return d


def test_decide_now_honors_persisted_cooldown(app_dir):
    runtime.set_cooldown_until(at(10, 30))
    assert scheduler.decide_now(at(10)).action == "cooldown"   # within cooldown
    assert scheduler.decide_now(at(11)).action == "nag"        # past it -> nags


def test_quiet_hours_before_and_after():
    assert scheduler.decide(at(6), quota=2, solved_today=0).action == "quiet"
    assert scheduler.decide(at(23), quota=2, solved_today=0).action == "quiet"


def test_quota_met():
    assert scheduler.decide(at(10), quota=2, solved_today=2).action == "met"
    assert scheduler.decide(at(10), quota=2, solved_today=3).action == "met"


def test_cooldown_blocks_until():
    d = scheduler.decide(at(10), quota=2, solved_today=0,
                         cooldown_until=at(10, 30))
    assert d.action == "cooldown"
    # past the cooldown -> nags again
    d2 = scheduler.decide(at(11), quota=2, solved_today=0, cooldown_until=at(10, 30))
    assert d2.action == "nag"


def test_waiting_within_nag_interval():
    d = scheduler.decide(at(10, 30), quota=2, solved_today=0,
                         last_nag=at(10, 0), nag_interval_min=90)
    assert d.action == "waiting"


def test_nags_after_interval():
    d = scheduler.decide(at(12, 0), quota=2, solved_today=0,
                         last_nag=at(10, 0), nag_interval_min=90)
    assert d.action == "nag"
    assert d.message


@pytest.mark.parametrize("hour,level", [(9, 1), (15, 2), (21, 3)])
def test_nag_level_escalates(hour, level):
    d = scheduler.decide(at(hour), quota=2, solved_today=0,
                         start_hour=8, end_hour=23)
    assert d.action == "nag"
    assert d.nag_level == level
