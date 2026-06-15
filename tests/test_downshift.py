"""Tests for the downshift escape loop (#22): serve N fallback problems, release
only after all are Accepted."""

import pytest

from leetcode_enforcer import banks, blocker
from leetcode_enforcer.blocker import BlockerApi
from leetcode_enforcer.leetcode import Problem


def _mk(slug, difficulty="Easy", paid=False):
    return Problem(internal_id="1", number=1, title=slug.title(), slug=slug,
                   difficulty=difficulty, paid=paid, topics=[], content_html="",
                   snippets={})


class _NoShuffle:
    """rng stand-in: keeps candidate order deterministic for tests."""
    @staticmethod
    def shuffle(seq):
        pass


# ── banks.select_easy_problems ───────────────────────────────────────────────

def test_select_easy_problems_skips_paid_and_non_easy():
    # difficulty/paid keyed by slug; everything else is a plain free Easy problem
    hard = "3sum"
    paid = "best-time-to-buy-and-sell-stock"

    def fake_fetch(slug):
        if slug == hard:
            return _mk(slug, difficulty="Hard")
        if slug == paid:
            return _mk(slug, paid=True)
        return _mk(slug)

    out = banks.select_easy_problems(["blind75"], [], 3,
                                     fetch=fake_fetch, rng=_NoShuffle())
    assert len(out) == 3
    assert all(p.difficulty == "Easy" and not p.paid for p in out)
    assert hard not in [p.slug for p in out]
    assert paid not in [p.slug for p in out]


# ── blocker.resolve_fallback ─────────────────────────────────────────────────

def test_resolve_fallback_resolve_mode_refetches_recent_slugs():
    fallback = {"mode": "resolve", "slugs": ["two-sum", "3sum", "valid-anagram"]}
    fetched = []

    def fake_fetch(slug):
        fetched.append(slug)
        return _mk(slug)

    out = blocker.resolve_fallback(fallback, ["blind75"], [], fetch=fake_fetch)
    assert [p.slug for p in out] == ["two-sum", "3sum", "valid-anagram"]
    assert fetched == ["two-sum", "3sum", "valid-anagram"]


def test_resolve_fallback_easy_mode_delegates_to_banks(monkeypatch):
    fallback = {"mode": "easy", "count": 3}
    sentinel = [_mk("a"), _mk("b"), _mk("c")]
    captured = {}

    def fake_select_easy(banks_enabled, solved, n, **kw):
        captured.update(banks=banks_enabled, n=n)
        return sentinel

    monkeypatch.setattr(banks, "select_easy_problems", fake_select_easy)
    out = blocker.resolve_fallback(fallback, ["blind75"], [], fetch=lambda s: _mk(s))
    assert out is sentinel
    assert captured == {"banks": ["blind75"], "n": 3}


# ── BlockerApi downshift queue ───────────────────────────────────────────────

@pytest.fixture
def downshift_env(monkeypatch):
    """Stub config + history so start_downshift runs without network/disk."""
    from leetcode_enforcer import config, state
    monkeypatch.setattr(state, "solved_slugs", lambda: [])
    monkeypatch.setattr(config, "load_config",
                        lambda: {"banks": ["blind75"], "languages": ["python3"]})


def _started_api(monkeypatch, queue):
    monkeypatch.setattr(blocker, "resolve_fallback", lambda *a, **k: queue)
    api = BlockerApi(_mk("orig"), languages=["python3"])
    return api, api.start_downshift()


def test_start_downshift_loads_queue_and_switches_to_first(downshift_env, monkeypatch):
    api, r = _started_api(monkeypatch, [_mk("a"), _mk("b"), _mk("c")])
    assert r["ok"] is True
    assert (r["index"], r["total"]) == (1, 3)
    assert r["problem"]["title"] == "A"
    assert api.state()["title"] == "A"   # current problem is now the first fallback


def test_start_downshift_error_lets_caller_fall_back(downshift_env, monkeypatch):
    def boom(*a, **k):
        raise blocker.leetcode.LeetCodeError("network down")
    monkeypatch.setattr(blocker, "resolve_fallback", boom)
    r = BlockerApi(_mk("orig")).start_downshift()
    assert r["ok"] is False and "network down" in r["error"]


def test_start_downshift_empty_queue_returns_error(downshift_env, monkeypatch):
    _api, r = _started_api(monkeypatch, [])
    assert r["ok"] is False


def test_advance_downshift_walks_queue_then_reports_done(downshift_env, monkeypatch):
    api, _ = _started_api(monkeypatch, [_mk("a"), _mk("b"), _mk("c")])
    r1 = api.advance_downshift()
    assert r1["done"] is False and (r1["index"], r1["total"]) == (2, 3)
    assert r1["problem"]["title"] == "B"
    r2 = api.advance_downshift()
    assert r2["problem"]["title"] == "C" and r2["index"] == 3 and r2["done"] is False
    r3 = api.advance_downshift()
    assert r3["done"] is True   # all fallback problems cleared -> release
