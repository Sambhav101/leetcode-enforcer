"""Curated problem banks + free-tier-aware selection (#15, #14).

LeetCode has no "Blind 75 / NeetCode" API, so the lists are bundled as slug sets
(DESIGN.md §4a). Selection prefers problems not yet solved and skips any that turn
out to be premium-locked (``isPaidOnly``), so the user is never handed a problem
they can't open or submit.
"""

import random

from .leetcode import fetch_problem

# Curated banks as title-slug lists. Premium-locked entries are filtered at
# selection time via the isPaidOnly flag, so they can safely remain in the list.
BANKS = {
    "blind75": [
        "two-sum", "best-time-to-buy-and-sell-stock", "contains-duplicate",
        "product-of-array-except-self", "maximum-subarray", "maximum-product-subarray",
        "find-minimum-in-rotated-sorted-array", "search-in-rotated-sorted-array",
        "3sum", "container-with-most-water", "sum-of-two-integers", "number-of-1-bits",
        "counting-bits", "missing-number", "reverse-bits", "climbing-stairs",
        "coin-change", "longest-increasing-subsequence", "longest-common-subsequence",
        "word-break", "combination-sum", "house-robber", "house-robber-ii",
        "decode-ways", "unique-paths", "jump-game", "clone-graph", "course-schedule",
        "pacific-atlantic-water-flow", "number-of-islands", "longest-consecutive-sequence",
        "insert-interval", "merge-intervals", "non-overlapping-intervals",
        "reverse-linked-list", "linked-list-cycle", "merge-two-sorted-lists",
        "merge-k-sorted-lists", "remove-nth-node-from-end-of-list", "reorder-list",
        "set-matrix-zeroes", "spiral-matrix", "rotate-image", "word-search",
        "longest-substring-without-repeating-characters",
        "longest-repeating-character-replacement", "minimum-window-substring",
        "valid-anagram", "group-anagrams", "valid-parentheses", "valid-palindrome",
        "longest-palindromic-substring", "palindromic-substrings",
        "maximum-depth-of-binary-tree", "same-tree", "invert-binary-tree",
        "binary-tree-maximum-path-sum", "binary-tree-level-order-traversal",
        "serialize-and-deserialize-binary-tree", "subtree-of-another-tree",
        "construct-binary-tree-from-preorder-and-inorder-traversal",
        "validate-binary-search-tree", "kth-smallest-element-in-a-bst",
        "lowest-common-ancestor-of-a-binary-search-tree", "implement-trie-prefix-tree",
        "design-add-and-search-words-data-structure", "word-search-ii",
        "top-k-frequent-elements", "find-median-from-data-stream",
    ],
}


class NoProblemAvailable(RuntimeError):
    pass


def candidate_slugs(enabled_banks, solved_slugs) -> list[str]:
    """Slugs from the enabled banks, preferring those not yet solved."""
    pool, seen = [], set()
    for name in enabled_banks:
        for slug in BANKS.get(name, []):
            if slug not in seen:
                seen.add(slug)
                pool.append(slug)
    unsolved = [s for s in pool if s not in set(solved_slugs)]
    return unsolved or pool   # if everything's solved, allow repeats


def select_problem(enabled_banks, solved_slugs, *, prefer_topics=None,
                   fetch=fetch_problem, rng=random, max_tries: int = 8):
    """Pick a free-tier problem from the enabled banks (skips premium-locked).

    When ``prefer_topics`` is given (#12), prefer a free problem sharing one of those
    topics; if none turns up within ``max_tries``, fall back to the first free problem
    seen rather than failing — the user should always get a next problem.
    """
    candidates = candidate_slugs(enabled_banks, solved_slugs)
    if not candidates:
        raise NoProblemAvailable("No problems configured — check enabled banks.")
    order = list(candidates)
    rng.shuffle(order)
    want = set(prefer_topics or [])
    fallback = None
    for slug in order[:max_tries]:
        problem = fetch(slug)
        if problem.paid:              # free-tier only (#14)
            continue
        if not want or (want & set(problem.topics)):
            return problem
        if fallback is None:
            fallback = problem        # first free problem, used if no topic match
    if fallback is not None:
        return fallback
    raise NoProblemAvailable("Couldn't find a free-tier problem to serve.")


def select_easy_problems(enabled_banks, solved_slugs, n=3, *, fetch=fetch_problem,
                         rng=random, max_tries: int = 24) -> list:
    """Pick up to ``n`` free-tier *Easy* problems for the downshift loop (#22).

    Used when the user has no solved history to re-serve. Skips premium-locked and
    non-Easy problems; returns however many it found (caller handles a short list).
    """
    candidates = candidate_slugs(enabled_banks, solved_slugs)
    order = list(candidates)
    rng.shuffle(order)
    out = []
    for slug in order[:max_tries]:
        problem = fetch(slug)
        if not problem.paid and problem.difficulty == "Easy":
            out.append(problem)
            if len(out) >= n:
                break
    return out
