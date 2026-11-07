#!/usr/bin/env python3
"""Lifecycle hold label: the one home of the check and set logic
(specs/119-lifecycle-hold-label, FR-019).

WHY THIS EXISTS
---------------
A lifecycle issue carrying the hold label (default ``lifecycle:held``) must
not be built, dispatched or merged. Every consumer (implement's start check,
fold-dispatch, the stop-comment setters, the fold-analyze decide job) reads
and writes that label through this module, via the
``wing-commander-lifecycle-hold`` composite, so the read-fresh /
fail-closed rule exists once.

CLI
---
``check --issue N [--repo R] [--hold-label L]``
    Fresh ``gh issue view`` of the labels. Prints ``state=clear|held|unreadable``
    (a ``key=value`` line, suitable for ``$GITHUB_OUTPUT``). Any read failure
    is ``unreadable`` -- never ``clear``. Never writes.
``set --issue N --reason TEXT [--repo R] [--hold-label L]``
    Idempotent label add; always posts the reason comment. Prints
    ``set=true`` (label newly added) or ``set=already``.
"""
import argparse
import json
import subprocess
import sys

DEFAULT_HOLD_LABEL = "lifecycle:held"

# FR-004: the single canonical text callers post when the labels could not be
# read. Deliberately distinct from a hold.
UNREADABLE_MESSAGE = (
    "labels could not be read; dispatch implement by hand once readable"
)


def classify_labels(label_names, hold_label=DEFAULT_HOLD_LABEL):
    """Return ``held`` or ``clear`` for a list of label names."""
    # GitHub label names are case-insensitive.
    wanted = hold_label.casefold()
    return "held" if any(str(n).casefold() == wanted
                         for n in (label_names or [])) else "clear"


def parse_labels(raw):
    """Parse ``gh issue view --json labels`` output into a name list.

    Raises ValueError on anything that is not the expected shape, so the
    caller can map it to ``unreadable``.
    """
    try:
        data = json.loads(raw)
        labels = data["labels"]
        return [entry["name"] for entry in labels]
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError(f"unexpected labels payload: {exc}") from exc


def _gh(args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False)


def read_labels(issue, repo=None):
    cmd = ["issue", "view", str(issue), "--json", "labels"]
    if repo:
        cmd += ["-R", repo]
    proc = _gh(cmd)
    if proc.returncode != 0:
        raise ValueError(f"gh issue view failed: {proc.stderr.strip()}")
    return parse_labels(proc.stdout)


def check(issue, repo=None, hold_label=DEFAULT_HOLD_LABEL, reader=read_labels):
    try:
        names = reader(issue, repo)
    except Exception:  # any failure is unreadable, never clear
        return "unreadable"
    return classify_labels(names, hold_label)


def set_hold(issue, reason, repo=None, hold_label=DEFAULT_HOLD_LABEL,
             reader=read_labels, runner=_gh):
    """Add the label (idempotent) and always post ``reason``. Returns
    ``true`` when the label was newly added, ``already`` otherwise."""
    try:
        already = classify_labels(reader(issue, repo), hold_label) == "held"
    except Exception:
        already = False
    repo_args = ["-R", repo] if repo else []
    # An empty reason would make `gh issue comment --body ''` fail after the
    # label is added, so fall back to a fixed line before touching anything.
    reason = (reason or "").strip() or f"Lifecycle held: `{hold_label}` added."
    if not already:
        # Create the label only when missing (no --force): an existing label
        # keeps the adopter's description and colour.
        created = runner(["label", "create", hold_label, *repo_args,
                          "--description", "Lifecycle held: implement stops until released"])
        if created.returncode != 0 and "already exists" not in (
                (created.stderr or "") + (created.stdout or "")).lower():
            raise RuntimeError(f"could not create {hold_label}: {created.stderr.strip()}")
        add = runner(["issue", "edit", str(issue), "--add-label", hold_label, *repo_args])
        if add.returncode != 0:
            raise RuntimeError(f"could not add {hold_label}: {add.stderr.strip()}")
    comment = runner(["issue", "comment", str(issue), "--body", reason, *repo_args])
    if comment.returncode != 0:
        raise RuntimeError(f"could not post the hold reason: {comment.stderr.strip()}")
    return "already" if already else "true"


def release_plan(issue_state, labels, branch_exists, spec_stage, recorded_iteration,
                 spec_dir=""):
    """FR-007: decide whether removing the hold label should dispatch implement.

    Returns ``{due, reason, spec_dir, issue, iteration}``; ``iteration`` is
    ``recorded + 1`` when due, else ``None``.
    """
    labels = labels or []
    reason = ""
    if str(issue_state).lower() != "open":
        reason = "issue-not-open"
    elif "parked" in labels:
        reason = "parked"
    elif "stage:stalled" in labels:
        reason = "stalled"
    elif not branch_exists:
        reason = "no-spec-branch"
    elif spec_stage not in ("tasks", "implement"):
        reason = "stage-not-ready"
    due = reason == ""
    return {
        "due": due,
        "reason": reason or "due",
        "spec_dir": spec_dir,
        "iteration": int(recorded_iteration or 0) + 1 if due else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "set"):
        p = sub.add_parser(name)
        p.add_argument("--issue", required=True)
        p.add_argument("--repo")
        p.add_argument("--hold-label", default=DEFAULT_HOLD_LABEL)
        if name == "set":
            p.add_argument("--reason", required=True)
    rp = sub.add_parser("release-plan")
    rp.add_argument("--issue", required=True)
    rp.add_argument("--issue-state", required=True)
    rp.add_argument("--labels", default="", help="comma-separated label names")
    rp.add_argument("--branch-exists", choices=("true", "false"), required=True)
    rp.add_argument("--spec-stage", default="")
    rp.add_argument("--recorded-iteration", default="0")
    rp.add_argument("--spec-dir", default="")
    args = parser.parse_args(argv)
    if args.cmd == "release-plan":
        plan = release_plan(
            args.issue_state, [x for x in args.labels.split(",") if x],
            args.branch_exists == "true", args.spec_stage,
            args.recorded_iteration, args.spec_dir)
        plan["issue"] = args.issue
        print(json.dumps(plan))
        return 0
    if args.cmd == "check":
        print(f"state={check(args.issue, args.repo, args.hold_label)}")
        return 0
    print(f"set={set_hold(args.issue, args.reason, args.repo, args.hold_label)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
