"""Socratic hint helper backed by a local LLM (issue #7).

Runs entirely on the user's local Ollama (qwen) via its OpenAI-compatible HTTP API
— private, free, offline (reuses the memento pattern). The system prompt constrains
the model to *progressive hints*: nudge toward the idea, name the relevant concept,
ask a guiding question — but never hand over the full solution (DESIGN.md §2).
"""

import re

import requests

from . import config

HINT_SYSTEM = (
    "You are a Socratic coding mentor helping someone solve a LeetCode problem. "
    "Give a SHORT, progressive hint: nudge toward the right idea, name the relevant "
    "concept or data structure, or ask a guiding question that unblocks them. "
    "NEVER write the full solution or complete working code — at most a tiny 1-2 line "
    "illustrative fragment if essential. Keep it under ~120 words. Encourage; don't "
    "condescend or lecture."
)


class LLMError(RuntimeError):
    """Raised when the local model is unreachable or returns nothing usable."""


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks so reasoning models output clean hints."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _strip_html(html: str) -> str:
    """Crude tag-strip so the prompt carries readable problem text, not markup."""
    return re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ").strip()


def build_hint_prompt(problem, code: str = "", question: str = "", level: int = 1) -> str:
    parts = [
        f"PROBLEM #{problem.number}: {problem.title} ({problem.difficulty})",
        f"Topics: {', '.join(problem.topics) or 'n/a'}",
        "",
        _strip_html(problem.content_html)[:1500],
        "",
        f"My current code:\n{code.strip() or '(empty)'}",
        "",
        question.strip() or "Give me a hint to move forward.",
        f"(This is hint #{level} — make it slightly more revealing than the previous "
        f"hint, but still never the full solution.)",
    ]
    return "\n".join(parts)


def run_local_llm(system: str, user: str, cfg: dict | None = None) -> str:
    cfg = cfg or config.load_config()
    url = cfg["llm_base_url"].rstrip("/") + "/chat/completions"
    try:
        resp = requests.post(
            url,
            json={
                "model": cfg["llm_model"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.7,
                "stream": False,
            },
            timeout=cfg.get("llm_timeout_seconds", 120),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except requests.RequestException as e:
        raise LLMError(
            f"Couldn't reach your local model at {cfg['llm_base_url']}. "
            f"Is Ollama running? (ollama serve)  [{e}]"
        )
    except (KeyError, IndexError, ValueError):
        raise LLMError("Local model replied in an unexpected format.")
    return _strip_think(content)


def get_hint(problem, code: str = "", question: str = "", level: int = 1,
             cfg: dict | None = None) -> str:
    return run_local_llm(HINT_SYSTEM, build_hint_prompt(problem, code, question, level), cfg)
