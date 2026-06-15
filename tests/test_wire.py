"""Integration wiring: an Accepted submission records to the state store."""

import pytest

from leetcode_enforcer import config, leetcode, state
from leetcode_enforcer.blocker import BlockerApi
from leetcode_enforcer.leetcode import Problem, Verdict


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    d = tmp_path / ".leetcode-enforcer"
    monkeypatch.setattr(config, "APP_DIR", d)
    monkeypatch.setattr(config, "CONFIG_PATH", d / "config.json")
    return d


def _problem():
    return Problem(internal_id="1", number=1, title="Two Sum", slug="two-sum",
                   difficulty="Easy", paid=False, topics=[], content_html="", snippets={})


def _api_with_creds(monkeypatch, verdict):
    from leetcode_enforcer import credentials, solutions_repo
    monkeypatch.setattr(credentials, "load_credentials", lambda: {"session": "s", "csrf": "c"})
    monkeypatch.setattr(leetcode, "submit_and_wait", lambda *a, **k: verdict)
    # stub archiving so the test never touches a real solutions repo / git (#25)
    archived = []
    monkeypatch.setattr(solutions_repo, "archive_solution",
                        lambda *a, **k: archived.append(a) or {"archived": True})
    return BlockerApi(_problem()), archived


def test_accepted_submission_records_solved(app_dir, monkeypatch):
    api, archived = _api_with_creds(monkeypatch, Verdict(accepted=True, status="Accepted"))
    r = api.submit("python3", "code")
    assert r["accepted"] is True
    assert state.solved_slugs() == ["two-sum"]   # persisted
    assert state.solved_today() == 1
    assert len(archived) == 1                     # solution archived on accept (#25)


def test_rejected_submission_does_not_record(app_dir, monkeypatch):
    api, archived = _api_with_creds(monkeypatch, Verdict(accepted=False, status="Wrong Answer"))
    r = api.submit("python3", "bad")
    assert r["accepted"] is False
    assert state.solved_slugs() == []            # nothing recorded
    assert archived == []                         # nothing archived on reject (#25)
