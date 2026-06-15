"""Tests for #11 (continue with another problem after submitting) and #12
(next problem follows the same topic/pattern)."""

import pytest

from leetcode_enforcer import banks, blocker
from leetcode_enforcer.blocker import BlockerApi
from leetcode_enforcer.leetcode import Problem


def _p(slug, topics=(), paid=False):
    return Problem(internal_id="1", number=1, title=slug.title(), slug=slug,
                   difficulty="Easy", paid=paid, topics=list(topics),
                   content_html="", snippets={})


class _FixedRng:
    @staticmethod
    def shuffle(seq):
        pass


# ── #12: topic-preferred selection ───────────────────────────────────────────

def test_select_problem_prefers_a_topic_match():
    dp_slug = "maximum-subarray"   # within the first max_tries of blind75

    def fake_fetch(slug):
        return _p(slug, topics=(["Dynamic Programming"] if slug == dp_slug else ["Array"]))

    p = banks.select_problem(["blind75"], [], prefer_topics=["Dynamic Programming"],
                             fetch=fake_fetch, rng=_FixedRng)
    assert p.slug == dp_slug


def test_select_problem_falls_back_when_no_topic_match():
    # nothing matches the wanted topic -> return the first free problem, not error
    def fake_fetch(slug):
        return _p(slug, topics=["Array"])

    p = banks.select_problem(["blind75"], [], prefer_topics=["Graph"],
                             fetch=fake_fetch, rng=_FixedRng)
    assert p.slug == banks.BANKS["blind75"][0]


def test_select_problem_without_prefer_topics_is_unchanged():
    def fake_fetch(slug):
        return _p(slug, topics=["Array"])

    p = banks.select_problem(["blind75"], [], fetch=fake_fetch, rng=_FixedRng)
    assert p.slug == banks.BANKS["blind75"][0]


# ── #11: continue to another problem ─────────────────────────────────────────

def test_next_problem_swaps_to_same_topic_and_resets_hints(monkeypatch):
    from leetcode_enforcer import config, state
    monkeypatch.setattr(config, "load_config",
                        lambda: {"banks": ["blind75"], "languages": ["python3"]})
    monkeypatch.setattr(state, "solved_slugs", lambda: ["two-sum"])
    captured = {}

    def fake_select(enabled, solved, *, prefer_topics=None, **kw):
        captured["prefer_topics"] = prefer_topics
        return _p("3sum", topics=["Array"])

    monkeypatch.setattr(banks, "select_problem", fake_select)

    api = BlockerApi(_p("two-sum", topics=["Array", "Hash Table"]), languages=["python3"])
    api._hint_level = 3
    r = api.next_problem()
    assert r["ok"] is True
    assert r["problem"]["title"] == "3Sum"
    assert api.state()["title"] == "3Sum"        # current problem swapped
    assert api._hint_level == 0                   # hints reset for the new problem
    assert captured["prefer_topics"] == ["Array", "Hash Table"]   # same topic (#12)


def test_next_problem_error_is_surfaced(monkeypatch):
    from leetcode_enforcer import config, state
    monkeypatch.setattr(config, "load_config",
                        lambda: {"banks": ["blind75"], "languages": ["python3"]})
    monkeypatch.setattr(state, "solved_slugs", lambda: [])

    def boom(*a, **k):
        raise banks.NoProblemAvailable("nothing left")

    monkeypatch.setattr(banks, "select_problem", boom)
    r = BlockerApi(_p("two-sum")).next_problem()
    assert r["ok"] is False and "nothing left" in r["error"]
