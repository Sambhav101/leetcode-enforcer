"""Client for LeetCode's (unofficial) GraphQL API.

Fetching problem data is unauthenticated — see DESIGN.md §4a. Submitting (issue #4)
will need the Keychain credentials; this module only handles fetch.

The parsed ``Problem`` carries everything downstream features need: the frontend
number (#13), topic tags (#12), the ``isPaidOnly`` flag (#14), and per-language
starter snippets (#16).
"""

import time
from dataclasses import dataclass, field

import requests

BASE = "https://leetcode.com"
GRAPHQL_URL = f"{BASE}/graphql"
DEFAULT_TIMEOUT = 15

# LeetCode langSlug values for the languages we support (issue #16).
SUPPORTED_LANGS = ("python3", "cpp", "rust")

_QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    difficulty
    isPaidOnly
    topicTags { name }
    content
    codeSnippets { langSlug code }
    sampleTestCase
  }
}
"""


class LeetCodeError(RuntimeError):
    """Raised when the LeetCode API errors or returns no usable data."""


@dataclass
class Problem:
    internal_id: str         # LeetCode's internal questionId — needed to submit (#4)
    number: int              # questionFrontendId — the human-facing problem number (#13)
    title: str
    slug: str
    difficulty: str          # "Easy" | "Medium" | "Hard"
    paid: bool               # premium-locked? (filtered out per #14)
    topics: list[str]        # topic tags, for same-pattern selection (#12)
    content_html: str        # problem statement (HTML)
    snippets: dict[str, str]  # langSlug -> starter code (#16)
    sample_testcase: str = ""  # default test input for the Run button (#34)

    @property
    def url(self) -> str:
        """Web link to the problem (#13)."""
        return f"{BASE}/problems/{self.slug}/"

    def starter_code(self, lang_slug: str) -> str | None:
        return self.snippets.get(lang_slug)


def _graphql(query: str, variables: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Content-Type": "application/json",
            "Referer": BASE,
            "User-Agent": "leetcode-enforcer",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise LeetCodeError(str(payload["errors"]))
    return payload.get("data") or {}


def _parse_problem(q: dict) -> Problem:
    return Problem(
        internal_id=str(q["questionId"]),
        number=int(q["questionFrontendId"]),
        title=q["title"],
        slug=q["titleSlug"],
        difficulty=q["difficulty"],
        paid=bool(q.get("isPaidOnly")),
        topics=[t["name"] for t in (q.get("topicTags") or [])],
        content_html=q.get("content") or "",
        snippets={s["langSlug"]: s["code"] for s in (q.get("codeSnippets") or [])},
        sample_testcase=q.get("sampleTestCase") or "",
    )


def fetch_problem(slug: str, timeout: int = DEFAULT_TIMEOUT) -> Problem:
    """Fetch a single problem by its title slug (e.g. 'two-sum')."""
    data = _graphql(_QUESTION_QUERY, {"titleSlug": slug}, timeout)
    question = data.get("question")
    if not question:
        raise LeetCodeError(f"No problem found for slug {slug!r}")
    return _parse_problem(question)


# ── submission (authenticated — needs Keychain creds, see issue #2) ──────────

POLL_INTERVAL = 1.0   # seconds between verdict polls
MAX_WAIT = 90.0       # give up waiting for a verdict after this long


@dataclass
class Verdict:
    accepted: bool
    status: str                      # "Accepted", "Wrong Answer", "Runtime Error", ...
    total_correct: int | None = None
    total_testcases: int | None = None
    raw: dict = field(default_factory=dict)


def _auth(creds: dict) -> tuple[dict, dict]:
    """Build the (cookies, headers) needed for authenticated requests."""
    cookies = {"LEETCODE_SESSION": creds["session"], "csrftoken": creds["csrf"]}
    headers = {"X-CSRFToken": creds["csrf"], "User-Agent": "leetcode-enforcer"}
    return cookies, headers


def submit(problem: Problem, lang: str, code: str, creds: dict,
           timeout: int = DEFAULT_TIMEOUT) -> int:
    """Submit a solution; return the submission_id. Raises on auth/API failure."""
    cookies, headers = _auth(creds)
    headers["Referer"] = problem.url
    resp = requests.post(
        f"{BASE}/problems/{problem.slug}/submit/",
        json={"lang": lang, "question_id": problem.internal_id, "typed_code": code},
        cookies=cookies, headers=headers, timeout=timeout,
    )
    if resp.status_code in (401, 403):
        raise LeetCodeError("Not authenticated — LeetCode session expired? Re-paste the cookie.")
    resp.raise_for_status()
    submission_id = resp.json().get("submission_id")
    if not submission_id:
        raise LeetCodeError(f"Submit returned no submission_id: {resp.json()!r}")
    return int(submission_id)


def check_submission(submission_id: int, creds: dict,
                     timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Poll a submission's status once; returns the raw check payload."""
    cookies, headers = _auth(creds)
    resp = requests.get(
        f"{BASE}/submissions/detail/{submission_id}/check/",
        cookies=cookies, headers=headers, timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


@dataclass
class RunResult:
    ok: bool                         # ran without compile/runtime error AND correct
    status: str                      # status_msg from LeetCode
    output: list | None = None       # the code's answers for the input(s)
    expected: list | None = None     # expected answers (when available)
    runtime: str | None = None
    error: str | None = None         # compile/runtime error text, if any
    raw: dict = field(default_factory=dict)


def run_code(problem: Problem, lang: str, code: str, data_input: str, creds: dict,
             timeout: int = DEFAULT_TIMEOUT) -> int:
    """Run (not submit) against ``data_input``; return the interpret id to poll."""
    cookies, headers = _auth(creds)
    headers["Referer"] = problem.url
    resp = requests.post(
        f"{BASE}/problems/{problem.slug}/interpret_solution/",
        json={"lang": lang, "question_id": problem.internal_id,
              "typed_code": code, "data_input": data_input},
        cookies=cookies, headers=headers, timeout=timeout,
    )
    if resp.status_code in (401, 403):
        raise LeetCodeError("Not authenticated — LeetCode session expired? Re-paste the cookie.")
    resp.raise_for_status()
    interpret_id = resp.json().get("interpret_id")
    if not interpret_id:
        raise LeetCodeError(f"Run returned no interpret_id: {resp.json()!r}")
    return interpret_id


def run_and_wait(problem: Problem, lang: str, code: str, data_input: str, creds: dict,
                 poll_interval: float = POLL_INTERVAL, max_wait: float = MAX_WAIT,
                 timeout: int = DEFAULT_TIMEOUT, sleep=time.sleep,
                 now=time.monotonic) -> RunResult:
    """Run against custom/sample input and wait for the result (the 'Run' button, #34)."""
    interpret_id = run_code(problem, lang, code, data_input, creds, timeout)
    deadline = now() + max_wait
    while now() < deadline:
        data = check_submission(interpret_id, creds, timeout)
        if data.get("state") == "SUCCESS":
            error = (data.get("compile_error") or data.get("runtime_error") or None)
            correct = bool(data.get("correct_answer")) and not error
            return RunResult(
                ok=correct,
                status=data.get("status_msg", "Unknown"),
                output=data.get("code_answer"),
                expected=data.get("expected_code_answer"),
                runtime=data.get("status_runtime"),
                error=error,
                raw=data,
            )
        sleep(poll_interval)
    raise LeetCodeError("Timed out waiting for the run result.")


def submit_and_wait(problem: Problem, lang: str, code: str, creds: dict,
                    poll_interval: float = POLL_INTERVAL, max_wait: float = MAX_WAIT,
                    timeout: int = DEFAULT_TIMEOUT, sleep=time.sleep,
                    now=time.monotonic) -> Verdict:
    """Submit and poll until LeetCode finishes judging; return the Verdict.

    The blocker releases only when ``verdict.accepted`` is True (DESIGN.md §4a).
    """
    submission_id = submit(problem, lang, code, creds, timeout)
    deadline = now() + max_wait
    while now() < deadline:
        data = check_submission(submission_id, creds, timeout)
        if data.get("state") == "SUCCESS":
            status = data.get("status_msg", "Unknown")
            return Verdict(
                accepted=(status == "Accepted"),
                status=status,
                total_correct=data.get("total_correct"),
                total_testcases=data.get("total_testcases"),
                raw=data,
            )
        sleep(poll_interval)
    raise LeetCodeError("Timed out waiting for LeetCode to judge the submission.")
