"""Archive Accepted solutions to a private git repo (issue #25).

On an Accepted submission the solution is written into a separate git repo, committed,
and pushed to its (already-configured) private remote. Two deliberate rules:

- **One solution per problem.** If the problem already has a file, skip — never write a
  duplicate or overwrite an existing solution (also respects the project's data-safety
  rule). The first language that solves a problem wins.
- **Push never blocks the user.** Commit happens locally; the push is best-effort and any
  failure (no remote, offline, auth) is swallowed so the blocker still releases.

The repo lives outside this project at ``solutions_repo_path`` (default
``~/leetcode-solutions``); it's auto-initialised if missing. Commands run through an
injected ``run`` callable so the logic is unit-testable without touching real git.
"""

import os
import subprocess
from pathlib import Path

from . import config

# langSlug -> file extension for the archived solution
EXT = {
    "python3": "py", "python": "py", "cpp": "cpp", "c": "c", "java": "java",
    "rust": "rs", "javascript": "js", "typescript": "ts", "golang": "go",
    "csharp": "cs", "kotlin": "kt", "swift": "swift", "ruby": "rb", "scala": "scala",
    "php": "php", "dart": "dart", "elixir": "ex", "erlang": "erl", "racket": "rkt",
}


def _run(args) -> None:
    subprocess.run(args, check=True, capture_output=True)


def repo_path() -> Path:
    return Path(os.path.expanduser(config.load_config()["solutions_repo_path"]))


def _rel_path(problem, lang: str) -> str:
    ext = EXT.get(lang, "txt")
    return f"{problem.difficulty.lower()}/{problem.number}-{problem.slug}.{ext}"


def already_archived(repo: Path, problem) -> bool:
    """True if any solution file already exists for this problem (one-per-problem)."""
    return any(repo.glob(f"**/{problem.number}-{problem.slug}.*"))


def _commit_message(problem, lang: str) -> str:
    return f"Add #{problem.number} {problem.title} ({problem.difficulty}, {lang})"


def _ensure_repo(repo: Path, run) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        run(["git", "-C", str(repo), "init"])


def _try_push(repo: Path, run) -> bool:
    """Best-effort push; never raises (no remote / offline / auth all return False)."""
    try:
        run(["git", "-C", str(repo), "push"])
        return True
    except Exception:
        return False


def archive_solution(problem, lang: str, code: str, *, run=_run) -> dict:
    """Write, commit, and push an Accepted solution. Returns a small status dict.

    Skips silently (``archived=False``) when this problem is already archived.
    """
    repo = repo_path()
    _ensure_repo(repo, run)
    if already_archived(repo, problem):
        return {"archived": False, "reason": "duplicate"}
    rel = _rel_path(problem, lang)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)
    run(["git", "-C", str(repo), "add", rel])
    run(["git", "-C", str(repo), "commit", "-m", _commit_message(problem, lang)])
    pushed = _try_push(repo, run)
    return {"archived": True, "path": rel, "pushed": pushed}
