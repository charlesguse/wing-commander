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
import json
import os
import subprocess
import sys


def find_existing(issues_json, bot_login, footer):
    """The `html_url` of the oldest issue in `issues_json` (each a dict
    with at least `html_url`, `created_at`, `body`, `user`) whose `user`
    is `bot_login` (`user.type == "Bot" and user.login == bot_login`) and
    whose `body` contains `footer` as a whole line (CR-normalized, matching
    the #530 jq predicate's `rtrimstr("\\r")` handling) -- or None when no
    such issue exists. Never a PR reference, never title text (FR-002,
    FR-003, FR-004; research.md D2). State (open/closed) is never part of
    the predicate (FR-003); of all matches the earliest `created_at` wins
    (FR-004)."""
    matches = []
    for issue in issues_json or []:
        user = issue.get("user") or {}
        if user.get("type") != "Bot" or user.get("login") != bot_login:
            continue
        body = issue.get("body") or ""
        if not any(line.rstrip("\r") == footer for line in body.split("\n")):
            continue
        matches.append(issue)
    if not matches:
        return None
    return min(matches, key=lambda issue: issue.get("created_at") or "").get("html_url")


def reopened_since(events_json, created_at):
    """The `created_at` of the last item in `events_json` whose `event`
    is `"reopened"`, or `created_at` (the issue's own) when no such item
    exists (FR-003; research.md D3)."""
    since = created_at
    for event in events_json or []:
        if event.get("event") == "reopened":
            since = event.get("created_at") or since
    return since


def record_attempt(attempts_before, budget):
    """{"attempts": attempts_before + 1, "stall": attempts_before + 1 >=
    budget} -- a pure function, no I/O (FR-018; research.md D6;
    contracts/spec-request-attempt-bound.md)."""
    attempts = attempts_before + 1
    return {"attempts": attempts, "stall": attempts >= budget}


def _gh_api_jq_lines(path, extra_args, jq_filter, paginate=True):
    """Runs `gh api PATH [--paginate] [extra_args] --jq JQ_FILTER` and
    returns the list of JSON values it prints, one per line -- or None on
    any failure (network, rate limit, auth), mirroring the #530 lookup's
    own `exit 1` shape (research.md D1; contracts/spec-request-existence-
    check.md "Failure"). Never falls back to "no match found" on error."""
    cmd = ["gh", "api", path]
    if paginate:
        cmd.append("--paginate")
    cmd.extend(extra_args)
    cmd.extend(["--jq", jq_filter])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    items = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except ValueError:
            print("board_spec_request_filing: gh api {0} returned a "
                  "non-JSON line: {1!r}".format(path, line), file=sys.stderr)
            return None
    return items


def _cmd_lookup(args):
    """lookup --issue ISSUE_NUMBER --bot-login LOGIN
    (contracts/spec-request-existence-check.md). Prints
    `existing-spec-url=<url-or-empty>` to $GITHUB_OUTPUT; exits 1 with
    nothing written on any `gh api` failure (FR-007)."""
    repository = os.environ.get("GITHUB_REPOSITORY")
    server_url = os.environ.get("GITHUB_SERVER_URL")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not repository or not server_url or not github_output:
        print("::error::board_spec_request_filing lookup: GITHUB_REPOSITORY, "
              "GITHUB_SERVER_URL and GITHUB_OUTPUT must all be set.", file=sys.stderr)
        return 1

    issue_path = "repos/{0}/issues/{1}".format(repository, args.issue)

    issue_rows = _gh_api_jq_lines(issue_path, [], "{created_at}", paginate=False)
    if not issue_rows:
        print("::error::board_spec_request_filing lookup: could not fetch "
              "issue #{0} itself -- since cannot be resolved (research.md "
              "D3).".format(args.issue), file=sys.stderr)
        return 1
    issue_created_at = issue_rows[0].get("created_at")

    events = _gh_api_jq_lines(issue_path + "/events", [], "{event, created_at}")
    if events is None:
        print("::error::board_spec_request_filing lookup: could not fetch "
              "issue #{0}'s timeline events.".format(args.issue), file=sys.stderr)
        return 1
    since = reopened_since(events, issue_created_at)

    candidates = _gh_api_jq_lines(
        "repos/{0}/issues".format(repository),
        ["-f", "state=all", "-f", "since={0}".format(since),
         "-f", "creator={0}".format(args.bot_login)],
        ".[] | select(.pull_request == null) | "
        "{html_url, created_at, body, user: {login: .user.login, type: .user.type}}")
    if candidates is None:
        print("::error::board_spec_request_filing lookup: could not search "
              "for a spec-request already filed for issue #{0}.".format(
                  args.issue), file=sys.stderr)
        return 1

    footer = "Originating issue: {0}/{1}/issues/{2}".format(
        server_url, repository, args.issue)
    existing = find_existing(candidates, args.bot_login, footer) or ""
    with open(github_output, "a", encoding="utf-8") as fh:
        fh.write("existing-spec-url={0}\n".format(existing))
    return 0


def _cmd_record_attempt(args):
    """record-attempt --attempts N --budget B
    (contracts/spec-request-attempt-bound.md). Prints the result as one
    JSON object to stdout, for the calling step's shell to branch on with
    `jq`."""
    print(json.dumps(record_attempt(args.attempts, args.budget)))
    return 0


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
