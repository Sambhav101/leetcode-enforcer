"""Tests for the escape hatch: phrase verification, logging, and blocker wiring."""

import pytest

from leetcode_enforcer import config, escape
from leetcode_enforcer.blocker import BlockerApi
from leetcode_enforcer.leetcode import Problem


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    d = tmp_path / ".leetcode-enforcer"
    monkeypatch.setattr(config, "APP_DIR", d)
    monkeypatch.setattr(config, "CONFIG_PATH", d / "config.json")
    return d


def _problem():
    return Problem(internal_id="1", number=1, title="Two Sum", slug="two-sum",
                   difficulty="Easy", paid=False, topics=[], content_html="", snippets={})


@pytest.mark.parametrize("typed,ok", [
    ("I GIVE UP", True),
    ("  i give up  ", True),   # case/space-insensitive
    ("i give", False),
    ("", False),
    (None, False),
])
def test_verify_phrase(typed, ok):
    assert escape.verify_phrase(typed) is ok


def test_log_escape_writes_line(app_dir):
    escape.log_escape(1, "Two Sum", reason="emergency")
    log = app_dir / "escapes.log"
    assert log.exists()
    contents = log.read_text()
    assert "#1 Two Sum" in contents
    assert "emergency" in contents


@pytest.mark.parametrize("solved,expected_mode", [
    (["a", "b", "c", "d"], "resolve"),   # enough history -> re-solve recent 3
    (["a", "b"], "easy"),                # too few -> easy fallback
    ([], "easy"),
])
def test_choose_fallback(solved, expected_mode):
    out = escape.choose_fallback(solved)
    assert out["mode"] == expected_mode
    if expected_mode == "resolve":
        assert out["slugs"] == solved[-escape.FALLBACK_COUNT:]
        assert len(out["slugs"]) == escape.FALLBACK_COUNT
    else:
        assert out["count"] == escape.FALLBACK_COUNT


def test_record_giveup_logs_and_returns_cooldown(app_dir):
    import datetime
    now = datetime.datetime(2026, 6, 4, 12, 0, 0)
    nxt = escape.record_giveup(1, "Two Sum", now=now)
    assert (nxt - now).total_seconds() == escape.GIVEUP_COOLDOWN_SECONDS
    assert "gave up" in (app_dir / "escapes.log").read_text()


def test_record_giveup_persists_cooldown_for_scheduler(app_dir):
    import datetime
    from leetcode_enforcer import runtime
    now = datetime.datetime(2026, 6, 4, 12, 0, 0)
    nxt = escape.record_giveup(1, "Two Sum", now=now)
    assert runtime.get_cooldown_until() == nxt   # next launchd tick honors it (#23)


def test_blocker_escape_wrong_phrase_does_not_release(app_dir, monkeypatch):
    api = BlockerApi(_problem())
    released = {"v": False}
    monkeypatch.setattr(api, "_release", lambda: released.__setitem__("v", True))
    r = api.escape("nope")
    assert r["ok"] is False
    assert released["v"] is False
    assert not (app_dir / "escapes.log").exists()  # nothing logged on failed attempt


def test_blocker_escape_correct_phrase_logs_releases_and_sets_cooldown(app_dir, monkeypatch):
    api = BlockerApi(_problem())
    released = {"v": False}
    monkeypatch.setattr(api, "_release", lambda: released.__setitem__("v", True))
    r = api.escape("I GIVE UP")
    assert r["ok"] is True
    assert released["v"] is True
    assert "next_trigger" in r  # 1h re-trigger time returned
    assert (app_dir / "escapes.log").read_text().count("Two Sum") == 1
