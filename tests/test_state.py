"""Tests for the persistent state store (solved history + derived progress)."""

import datetime

import pytest

from leetcode_enforcer import config, state
from leetcode_enforcer.leetcode import Problem


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    d = tmp_path / ".leetcode-enforcer"
    monkeypatch.setattr(config, "APP_DIR", d)
    monkeypatch.setattr(config, "CONFIG_PATH", d / "config.json")
    return d


def _p(slug, number, difficulty="Easy"):
    return Problem(internal_id=str(number), number=number, title=slug.title(),
                   slug=slug, difficulty=difficulty, paid=False, topics=[],
                   content_html="", snippets={})


def test_empty_state(app_dir):
    assert state.solved_slugs() == []
    assert state.unique_count() == 0
    assert state.solved_today() == 0


def test_record_and_derive(app_dir):
    t = datetime.datetime(2026, 6, 4, 10, 0, 0)
    state.record_solved(_p("two-sum", 1), "python3", now=t)
    state.record_solved(_p("add-two-numbers", 2), "rust", now=t)
    assert state.solved_slugs() == ["two-sum", "add-two-numbers"]
    assert state.unique_count() == 2
    assert state.solved_today(now=t) == 2


def test_unique_count_dedups_resolves(app_dir):
    t = datetime.datetime(2026, 6, 4, 10, 0, 0)
    state.record_solved(_p("two-sum", 1), "python3", now=t)
    state.record_solved(_p("two-sum", 1), "cpp", now=t)   # solved again
    assert len(state.solved_slugs()) == 2   # both recorded
    assert state.unique_count() == 1        # but one unique problem


def test_recent_unique_slugs(app_dir):
    t = datetime.datetime(2026, 6, 4, 10, 0, 0)
    for slug, n in [("a", 1), ("b", 2), ("a", 1), ("c", 3), ("d", 4)]:
        state.record_solved(_p(slug, n), "python3", now=t)
    # a was re-solved (pos 3) so it's more recent than b -> 3 most-recent distinct
    # are a, c, d (returned in chronological order by their latest solve)
    assert state.recent_unique_slugs(3) == ["a", "c", "d"]


def test_count_by_day(app_dir):
    state.record_solved(_p("a", 1), "python3", now=datetime.datetime(2026, 6, 4, 9))
    state.record_solved(_p("b", 2), "python3", now=datetime.datetime(2026, 6, 4, 14))
    state.record_solved(_p("c", 3), "python3", now=datetime.datetime(2026, 6, 5, 9))
    cbd = state.count_by_day()
    assert cbd["2026-06-04"] == 2
    assert cbd["2026-06-05"] == 1


def test_quota(app_dir):
    t = datetime.datetime(2026, 6, 4, 10, 0, 0)
    assert state.quota_remaining(2, now=t) == 2
    state.record_solved(_p("a", 1), "python3", now=t)
    assert state.quota_remaining(2, now=t) == 1
    assert state.quota_met(2, now=t) is False
    state.record_solved(_p("b", 2), "python3", now=t)
    assert state.quota_met(2, now=t) is True
