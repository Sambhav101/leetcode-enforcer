"""Client for LeetCode's (unofficial) GraphQL API.

Fetching problem data is unauthenticated — see DESIGN.md §4a. Submitting (issue #4)
will need the Keychain credentials; this module only handles fetch.

The parsed ``Problem`` carries everything downstream features need: the frontend
number (#13), topic tags (#12), the ``isPaidOnly`` flag (#14), and per-language
starter snippets (#16).
"""

from dataclasses import dataclass

import requests

BASE = "https://leetcode.com"
GRAPHQL_URL = f"{BASE}/graphql"
DEFAULT_TIMEOUT = 15

# LeetCode langSlug values for the languages we support (issue #16).
SUPPORTED_LANGS = ("python3", "cpp", "rust")

_QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    title
    titleSlug
    difficulty
    isPaidOnly
    topicTags { name }
    content
    codeSnippets { langSlug code }
  }
}
"""


class LeetCodeError(RuntimeError):
    """Raised when the LeetCode API errors or returns no usable data."""


@dataclass
class Problem:
    number: int
    title: str
    slug: str
    difficulty: str          # "Easy" | "Medium" | "Hard"
    paid: bool               # premium-locked? (filtered out per #14)
    topics: list[str]        # topic tags, for same-pattern selection (#12)
    content_html: str        # problem statement (HTML)
    snippets: dict[str, str]  # langSlug -> starter code (#16)

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
        number=int(q["questionFrontendId"]),
        title=q["title"],
        slug=q["titleSlug"],
        difficulty=q["difficulty"],
        paid=bool(q.get("isPaidOnly")),
        topics=[t["name"] for t in (q.get("topicTags") or [])],
        content_html=q.get("content") or "",
        snippets={s["langSlug"]: s["code"] for s in (q.get("codeSnippets") or [])},
    )


def fetch_problem(slug: str, timeout: int = DEFAULT_TIMEOUT) -> Problem:
    """Fetch a single problem by its title slug (e.g. 'two-sum')."""
    data = _graphql(_QUESTION_QUERY, {"titleSlug": slug}, timeout)
    question = data.get("question")
    if not question:
        raise LeetCodeError(f"No problem found for slug {slug!r}")
    return _parse_problem(question)
