# leetcode-enforcer

A macOS forcing-function for interview prep. On a schedule it throws up a
full-screen blocker with a LeetCode problem and **won't let you back to your
machine until you submit an Accepted solution**. A built-in Socratic helper
(local Ollama / qwen) gives hints, never the full answer, so you actually learn
it instead of copy-pasting your way out.

## Why

I open LeetCode, do one problem, feel like a genius, and never come back. The only
thing that ever worked for me was removing the choice. So this removes it.

## How it works

- A scheduler surfaces a problem in a full-screen, hard-to-dismiss window.
- The blocker only clears once you have an **Accepted** submission.
- The hint helper runs a local model (Ollama/qwen) tuned to nudge, not solve: it
  asks questions and points at the approach rather than handing over the answer.

## Roadmap

- **Phase 1** — Python prototype to validate the habit loop (does the forcing
  function actually stick, or do I just rage-quit it on day two?).
- **Phase 2** — Swift rewrite with real OS-level enforcement, only if Phase 1
  proves it works.

## Status

Design complete, prototype not started — so right now it's a design and a lot of
optimism. See [DESIGN.md](DESIGN.md).
