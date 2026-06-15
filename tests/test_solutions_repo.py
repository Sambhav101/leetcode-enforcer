"""Tests for archiving Accepted solutions to a private git repo (#25).

Decisions: commit locally then auto-push (push failures are swallowed so they
never block the release), and one solution per problem (skip duplicates).
"""

import subprocess

import pytest

from leetcode_enforcer import config, solutions_repo
from leetcode_enforcer.leetcode import Problem


@pytest.fixture
def repo(tmp_path, monkeypatch):
    path = tmp_path / "leetcode-solutions"
    monkeypatch.setattr(config, "load_config",
                        lambda: {"solutions_repo_path": str(path),
                                 "solutions_repo_enabled": True})
    return path


def _problem(slug="two-sum", number=1, difficulty="Easy"):
    return Problem(internal_id="1", number=number, title=slug.replace("-", " ").title(),
                   slug=slug, difficulty=difficulty, paid=False, topics=[],
                   content_html="", snippets={})


class _Run:
    """Records git commands; optionally fails on a given subcommand."""
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, args):
        self.calls.append(args)
        if self.fail_on and self.fail_on in args:
            raise subprocess.CalledProcessError(1, args)

    def ran(self, sub):
        return [c for c in self.calls if sub in c]


def test_archive_writes_file_and_commits(repo):
    run = _Run()
    r = solutions_repo.archive_solution(_problem(), "python3", "print('hi')", run=run)
    assert r["archived"] is True
    written = repo / "easy" / "1-two-sum.py"
    assert written.read_text() == "print('hi')"
    assert run.ran("add") and run.ran("commit")


def test_archive_auto_pushes(repo):
    run = _Run()
    solutions_repo.archive_solution(_problem(), "python3", "x=1", run=run)
    assert run.ran("push")            # auto-push per the locked decision


def test_archive_skips_duplicate_same_problem_any_language(repo):
    run1 = _Run()
    solutions_repo.archive_solution(_problem(), "python3", "py code", run=run1)
    run2 = _Run()
    r = solutions_repo.archive_solution(_problem(), "rust", "rust code", run=run2)
    assert r["archived"] is False and r["reason"] == "duplicate"
    assert not run2.ran("commit")     # nothing committed the second time
    assert not (repo / "easy" / "1-two-sum.rs").exists()   # no second file


def test_push_failure_is_swallowed_and_solution_still_archived(repo):
    run = _Run(fail_on="push")
    r = solutions_repo.archive_solution(_problem(), "python3", "x=1", run=run)
    assert r["archived"] is True      # commit succeeded
    assert r["pushed"] is False       # push failed but did not raise


def test_inits_repo_when_missing(repo):
    run = _Run()
    solutions_repo.archive_solution(_problem(), "python3", "x=1", run=run)
    assert run.ran("init")            # git init on a fresh repo dir
