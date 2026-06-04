"""Tests for curated-bank selection (free-tier filtering, unsolved preference)."""

import pytest

from leetcode_enforcer import banks
from leetcode_enforcer.leetcode import Problem


def _p(slug, paid=False):
    return Problem(internal_id="1", number=1, title=slug, slug=slug,
                   difficulty="Easy", paid=paid, topics=[], content_html="", snippets={})


class FixedRng:
    """Deterministic 'shuffle' = identity, so test order is the candidate order."""
    @staticmethod
    def shuffle(seq):
        pass


def test_candidate_prefers_unsolved():
    pool = banks.candidate_slugs(["blind75"], solved_slugs=["two-sum"])
    assert "two-sum" not in pool
    assert "3sum" in pool


def test_candidate_allows_repeats_when_all_solved():
    all_slugs = banks.BANKS["blind75"]
    pool = banks.candidate_slugs(["blind75"], solved_slugs=all_slugs)
    assert pool == all_slugs   # fall back to full list rather than empty


def test_select_skips_paid_problems():
    # first candidate is premium, second is free -> should return the free one
    fetched = {}
    def fake_fetch(slug):
        fetched[slug] = True
        return _p(slug, paid=(slug == banks.BANKS["blind75"][0]))
    monkey_banks = ["blind75"]
    p = banks.select_problem(monkey_banks, solved_slugs=[], fetch=fake_fetch, rng=FixedRng)
    assert p.paid is False


def test_select_raises_if_all_paid():
    def all_paid(slug):
        return _p(slug, paid=True)
    with pytest.raises(banks.NoProblemAvailable):
        banks.select_problem(["blind75"], solved_slugs=[], fetch=all_paid,
                             rng=FixedRng, max_tries=3)
