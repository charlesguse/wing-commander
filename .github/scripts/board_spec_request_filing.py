#!/usr/bin/env python3
"""Bounded, idempotent spec-request filing (specs/092-bounded-spec-request-filing,
research.md D1/D6, contracts/spec-request-existence-check.md,
contracts/spec-request-attempt-bound.md).

Single home for two decisions every one of board-loop.yml's four
spec-request filing call sites (route's spec verdict, the fix job's
post-push breach, and readiness's two backstop-breach entries) must make
the same way, never a second, parallel copy (FR-017, FR-018):

  lookup          -- does a spec-request already exist for this
                     originating issue (find_existing(), reopened_since())?
                     FR-001-FR-004, FR-007.
  record-attempt  -- has this issue's filing attempt count crossed the
                     configured budget (record_attempt())? FR-008-FR-016.

Both are pure decisions over already-fetched data; the CLI subcommands
below are the thin `gh`-calling shell each site's own workflow step runs,
per Constitution IX (a durable decision is deterministic code, never an
agent's judgment).
"""
import argparse
import sys


def find_existing(issues_json, bot_login, footer):
    """The `html_url` of the oldest issue in `issues_json` (each a dict
    with at least `html_url`, `created_at`, `body`, `user`) whose `user`
    is `bot_login` (`user.type == "Bot" and user.login == bot_login`) and
    whose `body` contains `footer` as a whole line (CR-normalized) -- or
    None when no such issue exists. Never a PR reference, never title
    text (FR-002, FR-003, FR-004; research.md D2)."""
    raise NotImplementedError


def reopened_since(events_json, created_at):
    """The `created_at` of the last item in `events_json` whose `event`
    is `"reopened"`, or `created_at` (the issue's own) when no such item
    exists (FR-003; research.md D3)."""
    raise NotImplementedError


def record_attempt(attempts_before, budget):
    """{"attempts": attempts_before + 1, "stall": attempts_before + 1 >=
    budget} -- a pure function, no I/O (FR-018; research.md D6;
    contracts/spec-request-attempt-bound.md)."""
    raise NotImplementedError


def _cmd_lookup(args):
    raise NotImplementedError


def _cmd_record_attempt(args):
    raise NotImplementedError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    lookup_parser = subparsers.add_parser(
        "lookup", help="Look for a spec-request already filed for an issue")
    lookup_parser.add_argument("--issue", type=int, required=True)
    lookup_parser.add_argument("--bot-login", required=True)
    lookup_parser.set_defaults(func=_cmd_lookup)

    record_attempt_parser = subparsers.add_parser(
        "record-attempt", help="Decide the outcome of a failed filing attempt")
    record_attempt_parser.add_argument("--attempts", type=int, required=True)
    record_attempt_parser.add_argument("--budget", type=int, required=True)
    record_attempt_parser.set_defaults(func=_cmd_record_attempt)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
