"""Tests for submission + verdict polling. HTTP is mocked; no network, no creds."""

import pytest

from leetcode_enforcer import leetcode
from leetcode_enforcer.leetcode import Problem, Verdict

CREDS = {"session": "sess", "csrf": "tok"}


def _problem():
    return Problem(
        internal_id="1", number=1, title="Two Sum", slug="two-sum",
        difficulty="Easy", paid=False, topics=["Array"],
        content_html="", snippets={"python3": "class Solution: pass"},
    )


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise leetcode.requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


def test_submit_returns_submission_id(monkeypatch):
    captured = {}

    def fake_post(url, json=None, cookies=None, headers=None, timeout=None):
        captured.update(url=url, json=json, cookies=cookies, headers=headers)
        return FakeResp({"submission_id": 42})

    monkeypatch.setattr(leetcode.requests, "post", fake_post)
    sid = leetcode.submit(_problem(), "python3", "code", CREDS)
    assert sid == 42
    assert captured["json"]["question_id"] == "1"
    assert captured["cookies"]["LEETCODE_SESSION"] == "sess"
    assert captured["headers"]["X-CSRFToken"] == "tok"


def test_submit_auth_failure_raises(monkeypatch):
    monkeypatch.setattr(leetcode.requests, "post",
                        lambda *a, **k: FakeResp({}, status=403))
    with pytest.raises(leetcode.LeetCodeError, match="authenticated"):
        leetcode.submit(_problem(), "python3", "code", CREDS)


def test_submit_and_wait_accepted(monkeypatch):
    # submit -> id 7; first poll PENDING, second SUCCESS/Accepted
    monkeypatch.setattr(leetcode.requests, "post",
                        lambda *a, **k: FakeResp({"submission_id": 7}))
    polls = iter([
        {"state": "PENDING"},
        {"state": "SUCCESS", "status_msg": "Accepted",
         "total_correct": 57, "total_testcases": 57},
    ])
    monkeypatch.setattr(leetcode.requests, "get",
                        lambda *a, **k: FakeResp(next(polls)))

    v = leetcode.submit_and_wait(_problem(), "python3", "code", CREDS,
                                 sleep=lambda _s: None)
    assert isinstance(v, Verdict)
    assert v.accepted is True
    assert v.status == "Accepted"
    assert v.total_correct == 57


def test_submit_and_wait_wrong_answer(monkeypatch):
    monkeypatch.setattr(leetcode.requests, "post",
                        lambda *a, **k: FakeResp({"submission_id": 8}))
    monkeypatch.setattr(leetcode.requests, "get",
                        lambda *a, **k: FakeResp(
                            {"state": "SUCCESS", "status_msg": "Wrong Answer",
                             "total_correct": 3, "total_testcases": 57}))
    v = leetcode.submit_and_wait(_problem(), "python3", "bad", CREDS,
                                 sleep=lambda _s: None)
    assert v.accepted is False
    assert v.status == "Wrong Answer"


def test_submit_and_wait_times_out(monkeypatch):
    monkeypatch.setattr(leetcode.requests, "post",
                        lambda *a, **k: FakeResp({"submission_id": 9}))
    monkeypatch.setattr(leetcode.requests, "get",
                        lambda *a, **k: FakeResp({"state": "PENDING"}))
    # fake clock that always exceeds the deadline after first check
    clock = iter([0.0, 0.0, 1000.0, 2000.0, 3000.0])
    with pytest.raises(leetcode.LeetCodeError, match="Timed out"):
        leetcode.submit_and_wait(_problem(), "python3", "code", CREDS,
                                 sleep=lambda _s: None, now=lambda: next(clock))
