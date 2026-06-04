"""Tests for the LeetCode GraphQL fetch client.

The HTTP call is mocked so these run offline and don't hit LeetCode.
"""

import pytest

from leetcode_enforcer import leetcode


class FakeResponse:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise leetcode.requests.HTTPError("boom")

    def json(self):
        return self._payload


def _question_payload():
    return {
        "data": {
            "question": {
                "questionFrontendId": "1",
                "title": "Two Sum",
                "titleSlug": "two-sum",
                "difficulty": "Easy",
                "isPaidOnly": False,
                "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
                "content": "<p>Given an array...</p>",
                "codeSnippets": [
                    {"langSlug": "python3", "code": "class Solution:\n    pass"},
                    {"langSlug": "rust", "code": "impl Solution {}"},
                ],
            }
        }
    }


@pytest.fixture
def mock_post(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse(captured.get("_payload", _question_payload()))

    monkeypatch.setattr(leetcode.requests, "post", fake_post)
    return captured


def test_fetch_problem_parses_fields(mock_post):
    p = leetcode.fetch_problem("two-sum")
    assert p.number == 1
    assert p.title == "Two Sum"
    assert p.slug == "two-sum"
    assert p.difficulty == "Easy"
    assert p.paid is False
    assert p.topics == ["Array", "Hash Table"]
    assert p.url == "https://leetcode.com/problems/two-sum/"
    assert p.starter_code("python3").startswith("class Solution")
    assert p.starter_code("cpp") is None  # not provided in this payload


def test_fetch_sends_slug_variable(mock_post):
    leetcode.fetch_problem("add-two-numbers")
    assert mock_post["json"]["variables"] == {"titleSlug": "add-two-numbers"}


def test_missing_question_raises(monkeypatch, mock_post):
    mock_post["_payload"] = {"data": {"question": None}}
    with pytest.raises(leetcode.LeetCodeError):
        leetcode.fetch_problem("does-not-exist")


def test_graphql_errors_raise(monkeypatch, mock_post):
    mock_post["_payload"] = {"errors": [{"message": "rate limited"}]}
    with pytest.raises(leetcode.LeetCodeError):
        leetcode.fetch_problem("two-sum")
