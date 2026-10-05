#!/usr/bin/env python3
"""The board loop's workflow-scope hold, in one home (found by the code
review of #921, on #889).

The wing-commander App holds no Workflows permission (docs/setup.md), so
GitHub refuses a push that changes any file under `.github/workflows/`.
Three board-loop.yml sites meet that refusal before it happens and hold
the item for a maintainer instead: route on the drafted diff (its `hold`
verdict), the fix job's pre-push check on the fixer's real diff, and
review-fixup's on its own follow-up commit. Each used to carry its own copy
of the path check (route called workflow_push_blocked_paths(), fix and
review-fixup a `grep`) and of the hold sequence below. This module is
the one copy of both; verify-board-route-backstop.py fails on a site that
does either inline.

The hold sequence (#604's stall rule, board_item_marker.add_stalled_label()):
board:stalled goes on first and a failed add renders no marker; then the
stalled marker is posted in a comment naming the held paths; then FR-011's
stall summary line, only once that comment has posted.

    <changed paths, one per line> | python3 board_workflow_scope_hold.py \\
        --site fix --issue N --add-label "board:stalled" \\
        --can-push-workflows "$CAN_PUSH_WORKFLOWS" [--pr N] [--branch B --base-sha S]

Route passes `--route-decision board-route-decision.json` instead of
stdin: the held paths are its decision's, and any whose drafted diff
could not be applied are named in the comment as contract-unchecked.

Prints `held` (the item is now stalled; the caller must not push) or
`clear` (nothing this loop cannot push). Exits 1, with an `::error::`
naming the site, when the hold could not be completed.
"""
import argparse
import os
import re
import subprocess
import sys

# `python3 -I` (the pristine-snapshot invocation) leaves the script's own
# directory off sys.path; the snapshot is trusted (Gate 98).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_item_marker import (STALLED_STEP, add_stalled_label,  # noqa: E402
                               record_stall_summary, write_marker)
from board_route_backstop import workflow_push_blocked_paths  # noqa: E402

SITES = ("route", "fix", "review-fixup")

# The paths are agent-drafted (route) or agent-written (fix, review-fixup):
# only a plain path charset is rendered, inside a code span.
RENDERABLE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def render_paths(paths, fallback="a file under `.github/workflows/`"):
    shown = ["`{0}`".format(p) for p in paths if RENDERABLE_PATH_RE.match(p)]
    return ", ".join(shown) or fallback


def hold_comment(site, paths, pr=None, contract_unknown=None):
    """The human-legible half of the hold comment for `site`; the stalled
    marker follows it. `contract_unknown`: the paths in route's held change
    whose drafted diff could not be applied to main
    (drafted_contract_widened()) -- a composite as well as a workflow -- so
    whether they change a published contract was never checked -- a held
    fix is never pushed, so route_final_diff() never sees it."""
    named = render_paths(paths)
    if site == "route":
        lead = ("Route found this fix-shaped, but its change edits {0}, and this loop cannot "
                "push a workflow file (the App holds no Workflows permission).").format(named)
        action = "fix it"
    elif site == "fix":
        lead = ("The fix for this issue changes {0}, which this loop cannot push (the App holds "
                "no Workflows permission). Nothing was pushed; the work is on no "
                "branch.").format(named)
        action = "fix it"
    else:
        lead = ("The review follow-up commit for PR #{0} changes {1}, which this loop cannot "
                "push (the App holds no Workflows permission). Nothing was pushed; the PR is "
                "unchanged.").format(pr, named)
        action = "address the review"
    unchecked = ""
    if contract_unknown:
        unchecked = (" Route could not apply its drafted diff for {0} to main, so whether the "
                     "change touches a published contract (a workflow's `on: workflow_call:` "
                     "block, or a composite's `inputs:`/`outputs:`) is unchecked: a contract "
                     "change is spec-shaped, not a fix (FR-019).").format(
                         render_paths(contract_unknown, "a file it drafted"))
    return ("{0}{1} Held for a maintainer: {2} from a session whose token has the `workflow` "
            "scope, or grant the App Workflows (read and write) and set "
            "`WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` to `true`. Removing board:stalled is "
            "the sole re-eligibility condition.").format(lead, unchecked, action)


def hold(site, issue, label, paths, pr=None, branch=None, base_sha=None, run=None,
         contract_unknown=None):
    """Stalls `issue` for the workflow-scope `paths`. True once the comment
    has posted; False, with an `::error::` on stderr, when it could not."""
    where = "board-loop {0} (workflow-scope hold)".format(site)
    if not add_stalled_label(issue, label, run=run):
        print("::error::{0}: board:stalled could not be added to issue #{1} -- no stalled "
              "marker is posted (#604).".format(where, issue), file=sys.stderr)
        return False
    marker = write_marker(STALLED_STEP, 0, None, branch, base_sha)
    run = run or subprocess.run
    body = "{0}\n\n{1}".format(hold_comment(site, paths, pr, contract_unknown), marker)
    try:
        ok = run(["gh", "issue", "comment", str(issue), "-R", os.environ.get("GITHUB_REPOSITORY", ""),
                  "--body", body], stdout=sys.stderr).returncode == 0
    except OSError as exc:
        print(exc, file=sys.stderr)
        ok = False
    if not ok:
        print("::error::{0}: board:stalled was applied to issue #{1} but the stalled-marker "
              "comment could not be posted.".format(where, issue), file=sys.stderr)
        return False
    record_stall_summary(issue, "{0} (workflow-scope hold)".format(site))
    return True


def main(argv=None, stdin=None, run=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True, choices=SITES)
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--add-label", required=True,
                        help="must be board_eligibility.STALLED_LABEL, named at the call site "
                             "so the label-creation gate sees each job's apply")
    parser.add_argument("--can-push-workflows", required=True, choices=("true", "false"))
    parser.add_argument("--pr", type=int, default=None)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--base-sha", default=None)
    parser.add_argument("--route-decision", default=None,
                        help="route only: board-route-decision.json, read for the held paths "
                             "(measured.workflow_paths) and contract_unknown_paths instead of stdin")
    args = parser.parse_args(argv)
    from board_eligibility import STALLED_LABEL
    if args.add_label != STALLED_LABEL:
        parser.error("--add-label must be {0} (#604)".format(STALLED_LABEL))
    if args.site == "review-fixup" and args.pr is None:
        parser.error("--site review-fixup needs --pr N")
    if (args.site == "route") != (args.route_decision is not None):
        parser.error("--route-decision goes with --site route, and only with it")
    contract_unknown = []
    if args.route_decision:
        import json
        with open(args.route_decision, encoding="utf-8") as fh:
            measured = (json.load(fh).get("decision") or {}).get("measured") or {}
        changed = [p for p in measured.get("workflow_paths") or [] if isinstance(p, str)]
        contract_unknown = [p for p in measured.get("contract_unknown_paths") or []
                            if isinstance(p, str)]
    else:
        changed = [line.strip() for line in (stdin or sys.stdin).read().splitlines()
                   if line.strip()]
    blocked = workflow_push_blocked_paths(changed, args.can_push_workflows == "true")
    if not blocked:
        print("clear")
        return 0
    if not hold(args.site, args.issue, args.add_label, blocked, pr=args.pr,
                branch=args.branch, base_sha=args.base_sha, run=run,
                contract_unknown=contract_unknown):
        return 1
    print("held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
