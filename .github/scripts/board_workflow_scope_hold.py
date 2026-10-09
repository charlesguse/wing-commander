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

    python3 board_workflow_scope_hold.py --site fix --issue N \\
        --add-label "board:stalled" --can-push-workflows "$CAN_PUSH_WORKFLOWS" \\
        --diff-base SHA [--pr N] [--branch B --base-sha S]

Fix and review-fixup pass `--diff-base`: the held paths are the ones
changed from it to HEAD, listed by board_route_backstop.diff_name_list()
(NUL-separated, never C-quoted, renames as a delete and an add), and the
same real diff is checked for a published-contract change, which the
comment names -- a held change is never pushed, so route_final_diff()
never sees it (found by the code review of #953). Route passes
`--route-decision board-route-decision.json` instead: the held paths are
its decision's, and any whose drafted diff could not be applied are named
in the comment as contract-unchecked.

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
from board_route_backstop import (_is_wc_composite_action_path,  # noqa: E402
                                  _is_workflow_path, contract_widened, diff_name_list,
                                  read_base_contents, read_worktree_contents,
                                  workflow_push_blocked_paths)

SITES = ("route", "fix", "review-fixup")

# The paths are agent-drafted (route) or agent-written (fix, review-fixup):
# only a plain path charset is rendered, inside a code span.
RENDERABLE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
CONTRACT_BLOCKS = ("a workflow's `on: workflow_call:` block, or a composite's "
                   "`inputs:`/`outputs:`")


def render_paths(paths, fallback="a file under `.github/workflows/`"):
    shown = ["`{0}`".format(p) for p in paths if RENDERABLE_PATH_RE.match(p)]
    return ", ".join(shown) or fallback


def hold_comment(site, paths, pr=None, contract_unknown=None, contract_changed=None):
    """The human-legible half of the hold comment for `site`; the stalled
    marker follows it. `contract_unknown`: the paths in the held change
    whose contract effect could not be checked -- for route, those whose
    drafted diff could not be applied to main (drafted_contract_widened()),
    a composite as well as a workflow. `contract_changed`: fix and
    review-fixup only, the paths whose published contract the real diff
    changes (contract_widened()), or [] when it changes none. A held change
    is never pushed, so route_final_diff() never sees it: the comment is
    the only place its contract effect is reported."""
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
    contract = ""
    if contract_unknown:
        why = ("Route could not apply its drafted diff for {0} to main" if site == "route"
               else "The contract check of the real diff could not run for {0}")
        contract = (" " + why + ", so whether the change touches a published contract ({1}) "
                    "is unchecked: a contract change is spec-shaped, not a fix "
                    "(FR-019).").format(render_paths(contract_unknown, "a file it changed"),
                                        CONTRACT_BLOCKS)
    elif contract_changed:
        contract = (" The change also edits the published contract of {0} ({1}): a contract "
                    "change is spec-shaped, not a fix (FR-019), so it belongs in a spec "
                    "proposal rather than a push.").format(
                        render_paths(contract_changed, "a file it changed"), CONTRACT_BLOCKS)
    elif contract_changed is not None:
        contract = (" Its real diff changes no published contract ({0}).").format(CONTRACT_BLOCKS)
    return ("{0}{1} Held for a maintainer: {2} from a session whose token has the `workflow` "
            "scope, or grant the App Workflows (read and write) and set "
            "`WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` to `true`. Removing board:stalled is "
            "the sole re-eligibility condition.").format(lead, contract, action)


def real_diff_contract(base_sha, changed):
    """(contract_changed, contract_unknown) for the real diff from
    `base_sha` to the checkout: contract_widened() against both sides, the
    same comparison route_final_diff() makes after a push. A check that
    cannot run names every workflow and composite path as unknown."""
    try:
        return contract_widened(changed, "", read_worktree_contents(changed),
                                read_base_contents(base_sha, changed)), []
    except Exception as exc:  # report it in the comment, never lose the hold
        print("board_workflow_scope_hold: contract check failed: {0}".format(exc),
              file=sys.stderr)
        return [], [p for p in changed if _is_workflow_path(p) or _is_wc_composite_action_path(p)]


def read_route_decision(path):
    """route's held paths and contract-unchecked paths from its decision
    file. Raises ValueError naming why when the file cannot be read or is
    not the decision route's decide step writes."""
    import json
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError(str(exc))
    decision = doc.get("decision") if isinstance(doc, dict) else None
    measured = decision.get("measured") if isinstance(decision, dict) else None
    if not isinstance(measured, dict):
        raise ValueError("no decision.measured object")
    paths = measured.get("workflow_paths") or []
    unknown = measured.get("contract_unknown_paths") or []
    if not isinstance(paths, list) or not isinstance(unknown, list):
        raise ValueError("decision.measured.workflow_paths/contract_unknown_paths is not a list")
    return ([p for p in paths if isinstance(p, str)],
            [p for p in unknown if isinstance(p, str)])


def hold(site, issue, label, paths, pr=None, branch=None, base_sha=None, run=None,
         contract_unknown=None, contract_changed=None):
    """Stalls `issue` for the workflow-scope `paths`. True once the comment
    has posted; False, with an `::error::` on stderr, when it could not."""
    where = "board-loop {0} (workflow-scope hold)".format(site)
    if not add_stalled_label(issue, label, run=run):
        print("::error::{0}: board:stalled could not be added to issue #{1} -- no stalled "
              "marker is posted (#604).".format(where, issue), file=sys.stderr)
        return False
    marker = write_marker(STALLED_STEP, 0, None, branch, base_sha)
    run = run or subprocess.run
    body = "{0}\n\n{1}".format(hold_comment(site, paths, pr, contract_unknown, contract_changed), marker)
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


def main(argv=None, run=None):
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
    parser.add_argument("--diff-base", default=None,
                        help="fix and review-fixup: the commit the change is measured from; "
                             "the held paths and the contract check are its diff to HEAD")
    parser.add_argument("--route-decision", default=None,
                        help="route only: board-route-decision.json, read for the held paths "
                             "(measured.workflow_paths) and contract_unknown_paths")
    args = parser.parse_args(argv)
    from board_eligibility import STALLED_LABEL
    if args.add_label != STALLED_LABEL:
        parser.error("--add-label must be {0} (#604)".format(STALLED_LABEL))
    if args.site == "review-fixup" and args.pr is None:
        parser.error("--site review-fixup needs --pr N")
    if (args.site == "route") != (args.route_decision is not None):
        parser.error("--route-decision goes with --site route, and only with it")
    if (args.site == "route") == (args.diff_base is not None):
        parser.error("--diff-base goes with --site fix or review-fixup, and only with them")
    where = "board-loop {0} (workflow-scope hold)".format(args.site)
    contract_unknown, contract_changed = [], None
    if args.route_decision:
        try:
            changed, contract_unknown = read_route_decision(args.route_decision)
        except ValueError as exc:
            print("::error::{0}: cannot read route's decision {1} ({2}) -- issue #{3} was not "
                  "held.".format(where, args.route_decision, exc, args.issue), file=sys.stderr)
            return 1
    else:
        try:
            changed = diff_name_list(args.diff_base)
        except (OSError, subprocess.CalledProcessError) as exc:
            print("::error::{0}: cannot list the paths changed since {1} ({2}) -- issue #{3} "
                  "was not checked or held.".format(where, args.diff_base, exc, args.issue),
                  file=sys.stderr)
            return 1
    blocked = workflow_push_blocked_paths(changed, args.can_push_workflows == "true")
    if not blocked:
        print("clear")
        return 0
    if args.diff_base:
        contract_changed, contract_unknown = real_diff_contract(args.diff_base, changed)
    if not hold(args.site, args.issue, args.add_label, blocked, pr=args.pr,
                branch=args.branch, base_sha=args.base_sha, run=run,
                contract_unknown=contract_unknown, contract_changed=contract_changed):
        return 1
    print("held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
