#!/usr/bin/env python3
"""Gate: every spec_pr_review.py subcommand is exercised by checked-in fixtures.

Each file in .github/scripts/spec-pr-review-fixtures/ is
`<subcommand>-<case>.json` holding {"input": ..., "expect": ...}. The runner
feeds `input` to the subcommand and requires every key in `expect` to match
the output (subset match). A subcommand with no fixture fails the gate.
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "spec-pr-review-fixtures")
MODULE = os.path.join(HERE, "spec_pr_review.py")
SUBCOMMANDS = ("select", "eligible", "verdict", "check-fixes",
               "plan-actions", "failed-cap")


def subset(expect, got):
    if isinstance(expect, dict):
        return (isinstance(got, dict)
                and all(k in got and subset(v, got[k])
                        for k, v in expect.items()))
    return expect == got


INTAKE_LINE = "Closes nothing — lifecycle issue: #"


def check_issue_scan(wf_text):
    """The select step's lifecycle-issue jq program, run as written in the
    workflow, must pick intake's line out of a body that cites other issues
    too (SC-001): spec PR bodies routinely do, and a scan of every "#N"
    skipped them all as multiple-issues."""
    out = []
    intake = os.path.join(HERE, "..", "workflows", "intake.yml")
    with open(intake, encoding="utf-8") as fh:
        intake_text = fh.read()
    if intake_text.count(INTAKE_LINE) < 2:
        out.append("issue-scan: intake.yml no longer writes %r at both PR-body "
                   "sites; re-match the select step's scan" % INTAKE_LINE)
    line = next((l for l in wf_text.splitlines()
                 if "-issues.json" in l and l.strip().startswith("jq -c '")),
                None)
    if line is None:
        return out + ["issue-scan: select step's lifecycle-issue jq not found"]
    program = line.strip()[len("jq -c '"):].split("'", 1)[0]
    body = ("Specification at specs/122-x.\n\nFollows #1078 and #1075; see "
            "#1058, #1057 and PR #1113.\n\n" + INTAKE_LINE + "1094\n")
    single = ("Specification at specs/122-x.\n\n" + INTAKE_LINE + "1094\n")
    none = "Refs #1078 and #1075.\n"
    for name, text, want in (("cites-others", body, [1094]),
                             ("single", single, [1094]),
                             ("no-intake-line", none, [])):
        proc = subprocess.run(["jq", "-c", program],
                              input=json.dumps({"body": text}),
                              capture_output=True, text=True)
        got = json.loads(proc.stdout) if proc.returncode == 0 else proc.stderr
        if got != want:
            out.append("issue-scan %s: expected %s, got %s"
                       % (name, json.dumps(want), json.dumps(got)))
    return out


def main():
    failures, seen = [], set()
    paths = sorted(glob.glob(os.path.join(FIXTURES, "*.json")))
    for path in paths:
        name = os.path.basename(path)[:-5]
        cmd = next((c for c in sorted(SUBCOMMANDS, key=len, reverse=True)
                    if name.startswith(c + "-")), None)
        if cmd is None:
            cmd = "verdict" if name.startswith("replay-") else None
        if cmd is None:
            failures.append("%s: name does not start with a subcommand" % name)
            continue
        with open(path) as fh:
            case = json.load(fh)
        cmd = case.get("subcommand", cmd)
        seen.add(cmd)
        proc = subprocess.run(
            [sys.executable, MODULE, cmd], input=json.dumps(case["input"]),
            capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append("%s: exit %d: %s" % (name, proc.returncode,
                                                 proc.stderr.strip()))
            continue
        got = json.loads(proc.stdout)
        if not subset(case["expect"], got):
            failures.append("%s: expected %s, got %s" % (
                name, json.dumps(case["expect"]), json.dumps(got)))
    sys.path.insert(0, HERE)
    import spec_pr_review_actions as act
    trusted = json.dumps({"author_association": "OWNER",
                          "issue_url": "https://x/issues/7"})
    untrusted = json.dumps({"author_association": "NONE",
                            "issue_url": "https://x/issues/7"})
    # The workflow must hand the verdict step the lifecycle issue; the value
    # the test then uses is the one that expression resolves to.
    wf = os.path.join(HERE, "..", "workflows", "spec-pr-review.yml")
    with open(wf, encoding="utf-8") as fh:
        wf_text = fh.read()
    step = wf_text.split("id: verdict", 1)[-1].split("run: |", 1)[0]
    if "SPEC_LIFECYCLE_ISSUE: ${{ needs.select.outputs.issue }}" not in step:
        failures.append("precedent: the verdict step does not set "
                        "SPEC_LIFECYCLE_ISSUE from needs.select.outputs.issue")
    os.environ.pop("SPEC_LIFECYCLE_ISSUE", None)
    if act._trusted_comment(trusted):
        failures.append("precedent: an unset lifecycle issue did not fail closed")
    os.environ["SPEC_LIFECYCLE_ISSUE"] = ""
    if act._trusted_comment(trusted):
        failures.append("precedent: an empty lifecycle issue did not fail closed")
    os.environ["SPEC_LIFECYCLE_ISSUE"] = "7"
    if act._trusted_comment(untrusted):
        failures.append("precedent: an untrusted author's comment was accepted")
    if act._trusted_comment("not json"):
        failures.append("precedent: unparseable comment was accepted")
    os.environ["SPEC_LIFECYCLE_ISSUE"] = "8"
    if act._trusted_comment(trusted):
        failures.append("precedent: a comment on another issue was accepted")
    os.environ["SPEC_LIFECYCLE_ISSUE"] = "7"
    if not act._trusted_comment(trusted):
        failures.append("precedent: a comment on the lifecycle issue was rejected")
    os.environ.pop("SPEC_LIFECYCLE_ISSUE", None)
    failures.extend(check_issue_scan(wf_text))
    for cmd in SUBCOMMANDS:
        if cmd not in seen:
            failures.append("subcommand %s has no fixture" % cmd)
    if failures:
        print("verify-spec-pr-review: FAIL")
        for f in failures:
            print("  " + f)
        return 1
    print("verify-spec-pr-review: ok (%d fixtures)" % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
