"""Tests for the Socratic hint helper. The LLM HTTP call is mocked."""

import pytest

from leetcode_enforcer import helper
from leetcode_enforcer.blocker import BlockerApi
from leetcode_enforcer.leetcode import Problem

CFG = {"llm_base_url": "http://localhost:11434/v1", "llm_model": "qwen3:8b",
       "llm_timeout_seconds": 30}


def _problem():
    return Problem(internal_id="1", number=1, title="Two Sum", slug="two-sum",
                   difficulty="Easy", paid=False, topics=["Array", "Hash Table"],
                   content_html="<p>Given an array of <b>integers</b>...</p>", snippets={})


class FakeResp:
    def __init__(self, payload, ok=True):
        self._payload, self._ok = payload, ok

    def raise_for_status(self):
        if not self._ok:
            raise helper.requests.HTTPError("boom")

    def json(self):
        return self._payload


def _chat(content):
    return {"choices": [{"message": {"content": content}}]}


def test_strip_think():
    assert helper._strip_think("<think>reasoning</think>Use a hash map.") == "Use a hash map."


def test_strip_html():
    assert "integers" in helper._strip_html("<p>Given an array of <b>integers</b></p>")
    assert "<" not in helper._strip_html("<p>x</p>")


def test_build_prompt_includes_problem_and_code():
    p = helper.build_hint_prompt(_problem(), code="def f(): pass", level=2)
    assert "Two Sum" in p and "def f(): pass" in p
    assert "hint #2" in p


def test_get_hint_strips_think(monkeypatch):
    monkeypatch.setattr(helper.requests, "post",
                        lambda *a, **k: FakeResp(_chat("<think>x</think>Try a dict.")))
    assert helper.get_hint(_problem(), code="", cfg=CFG) == "Try a dict."


def test_get_hint_connection_error_raises(monkeypatch):
    def boom(*a, **k):
        raise helper.requests.ConnectionError("refused")
    monkeypatch.setattr(helper.requests, "post", boom)
    with pytest.raises(helper.LLMError, match="Ollama"):
        helper.get_hint(_problem(), cfg=CFG)


def test_blocker_hint_progressive_level(monkeypatch):
    monkeypatch.setattr(helper.requests, "post",
                        lambda *a, **k: FakeResp(_chat("hint text")))
    api = BlockerApi(_problem())
    r1 = api.hint("code")
    r2 = api.hint("code")
    assert r1["level"] == 1 and r2["level"] == 2  # escalates each call


def test_blocker_hint_error_does_not_advance_level(monkeypatch):
    def boom(*a, **k):
        raise helper.requests.ConnectionError("refused")
    monkeypatch.setattr(helper.requests, "post", boom)
    api = BlockerApi(_problem())
    r = api.hint("code")
    assert r["ok"] is False
    # a failed hint must not consume a level
    assert api._hint_level == 0
