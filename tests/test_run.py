"""Tests for the Run button (interpret against test cases). HTTP mocked."""

import pytest

from leetcode_enforcer import credentials, leetcode
from leetcode_enforcer.blocker import BlockerApi
from leetcode_enforcer.leetcode import Problem, RunResult

CREDS = {"session": "s", "csrf": "c"}


def _problem():
    return Problem(internal_id="1", number=1, title="Two Sum", slug="two-sum",
                   difficulty="Easy", paid=False, topics=[], content_html="",
                   snippets={}, sample_testcase="[2,7,11,15]\n9")


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise leetcode.requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


def test_run_and_wait_correct(monkeypatch):
    monkeypatch.setattr(leetcode.requests, "post",
                        lambda *a, **k: FakeResp({"interpret_id": "i1"}))
    polls = iter([
        {"state": "PENDING"},
        {"state": "SUCCESS", "status_msg": "Finished", "correct_answer": True,
         "code_answer": ["[0,1]"], "expected_code_answer": ["[0,1]"]},
    ])
    monkeypatch.setattr(leetcode.requests, "get", lambda *a, **k: FakeResp(next(polls)))
    r = leetcode.run_and_wait(_problem(), "python3", "code", "[2,7,11,15]\n9", CREDS,
                              sleep=lambda _s: None)
    assert isinstance(r, RunResult)
    assert r.ok is True
    assert r.output == ["[0,1]"]


def test_run_and_wait_runtime_error(monkeypatch):
    monkeypatch.setattr(leetcode.requests, "post",
                        lambda *a, **k: FakeResp({"interpret_id": "i2"}))
    monkeypatch.setattr(leetcode.requests, "get", lambda *a, **k: FakeResp(
        {"state": "SUCCESS", "status_msg": "Runtime Error",
         "runtime_error": "IndexError", "correct_answer": False}))
    r = leetcode.run_and_wait(_problem(), "python3", "bad", "x", CREDS,
                              sleep=lambda _s: None)
    assert r.ok is False
    assert r.error == "IndexError"


def test_run_missing_interpret_id_raises(monkeypatch):
    monkeypatch.setattr(leetcode.requests, "post", lambda *a, **k: FakeResp({}))
    with pytest.raises(leetcode.LeetCodeError):
        leetcode.run_code(_problem(), "python3", "code", "x", CREDS)


def test_blocker_run_no_creds(monkeypatch):
    monkeypatch.setattr(credentials, "load_credentials", lambda: None)
    api = BlockerApi(_problem())
    r = api.run("python3", "code", "x")
    assert r["ok"] is False and "credentials" in r["error"]


def test_blocker_run_correct(monkeypatch):
    monkeypatch.setattr(credentials, "load_credentials", lambda: CREDS)
    monkeypatch.setattr(leetcode, "run_and_wait",
                        lambda *a, **k: RunResult(ok=True, status="Finished",
                                                  output=["[0,1]"], expected=["[0,1]"]))
    api = BlockerApi(_problem())
    r = api.run("python3", "code", "x")
    assert r["ok"] is True and r["correct"] is True and r["output"] == ["[0,1]"]
