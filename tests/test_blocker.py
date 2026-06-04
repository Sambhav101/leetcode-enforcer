"""Tests for the blocker's pure state-builder (no GUI/webview needed)."""

from leetcode_enforcer.blocker import build_state
from leetcode_enforcer.leetcode import Problem


def _problem():
    return Problem(
        internal_id="1", number=1, title="Two Sum", slug="two-sum",
        difficulty="Easy", paid=False, topics=["Array", "Hash Table"],
        content_html="<p>desc</p>",
        snippets={"python3": "class Solution: pass", "rust": "impl Solution {}"},
    )


def test_build_state_core_fields():
    s = build_state(_problem())
    assert s["number"] == 1
    assert s["title"] == "Two Sum"
    assert s["difficulty"] == "Easy"
    assert s["url"] == "https://leetcode.com/problems/two-sum/"
    assert s["topics"] == ["Array", "Hash Table"]


def test_build_state_languages_and_starters():
    s = build_state(_problem(), languages=("python3", "cpp", "rust"))
    slugs = [l["slug"] for l in s["languages"]]
    assert slugs == ["python3", "cpp", "rust"]
    by_slug = {l["slug"]: l for l in s["languages"]}
    assert by_slug["python3"]["label"] == "Python"
    assert by_slug["python3"]["starter"].startswith("class Solution")
    assert by_slug["cpp"]["starter"] == ""  # not provided -> empty, not crash
