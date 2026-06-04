"""End-to-end entry point (issue #10).

Ties the pieces together: the scheduler decides whether a session is due; if so we
select a free-tier problem from the curated banks and launch the full-screen blocker.
On an Accepted submission the blocker records the solve (state) and releases.

Usage:
    python -m leetcode_enforcer            # run one scheduler-gated check
    python -m leetcode_enforcer --force    # force a session now (ignore schedule)
    python -m leetcode_enforcer --preview  # windowed (non-fullscreen) session
"""

import sys

from . import banks, config, scheduler, state


def run_session(fullscreen: bool = True) -> None:
    """Select a problem and launch the blocker (blocks until released)."""
    from .blocker import run_blocker
    cfg = config.load_config()
    problem = banks.select_problem(cfg["banks"], state.solved_slugs())
    run_blocker(problem, cfg["languages"], fullscreen=fullscreen)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    force = "--force" in argv
    preview = "--preview" in argv

    if not force:
        decision = scheduler.decide_now()
        if decision.action != "nag":
            print(f"No session: {decision.action}"
                  + (f" — {decision.message}" if decision.message else ""))
            return 0
        print(decision.message)

    run_session(fullscreen=not preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
