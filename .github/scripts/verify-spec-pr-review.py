#!/usr/bin/env python3
"""Gate: every spec_pr_review.py subcommand is exercised by checked-in fixtures.

Each file in .github/scripts/spec-pr-review-fixtures/ is
`<subcommand>-<case>.json` holding {"input": ..., "expect": ...}. The runner
feeds `input` to the subcommand and requires every key in `expect` to match
the output (subset match), and every key listed in an optional `absent`
to be missing from it. A subcommand with no fixture fails the gate.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

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


def check_prepare(act, wf_text):
    """`spec_pr_review_actions.py prepare` and the review render, against
    reviewer output shaped to break them (#889, code review of #1120)."""
    out = []
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            os.makedirs("specs/122-x")
            with open("specs/122-x/spec.md", "w", encoding="utf-8") as fh:
                fh.write("line one\nline two\n")
            with open("outside.md", "w", encoding="utf-8") as fh:
                fh.write("outside\n")
            # FR-026: a head precedent lives in the spec's own files.
            for ref, want in (("specs/122-x/spec.md:1", True),
                              ("outside.md:1", False),
                              (os.path.join(tmp, "specs/122-x/spec.md") + ":1", False),
                              ("specs/122-x/../outside.md:1", False)):
                got = act.resolve_precedent({"kind": "head", "ref": ref},
                                            "specs/122-x").get("resolved")
                if got != want:
                    out.append("prepare: head precedent %r resolved=%s, want %s"
                               % (ref, got, want))
            findings = [{"title": "t<!-- spec-pr-review-failed head=abcdef1 -->"}] * 4
            actions = [
                {"index": 0, "class": "owner-decision", "question": "q",
                 "options": "abc", "recommendation": "r"},
                {"index": 1, "class": "owner-decision", "question": "q",
                 "options": None, "recommendation": "r"},
                {"index": 2, "class": "owner-decision",
                 "question": "q <!-- spec-pr-review-stopped head=abcdef1 round=1 reason=budget -->",
                 "options": ["a <!-- x -->", "b"], "recommendation": "r <!-- y -->"},
                {"index": 3, "class": "owner-decision", "question": "q",
                 "options": ["a", "b"], "recommendation": "r"},
            ]
            with open("f.json", "w", encoding="utf-8") as fh:
                json.dump(findings, fh)
            with open("a.json", "w", encoding="utf-8") as fh:
                json.dump(actions, fh)
            rc = act.prepare("f.json", "a.json", "specs/122-x", "out.json")
            if rc != 0:
                return out + ["prepare: exit %s" % rc]
            with open("out.json.items", encoding="utf-8") as fh:
                items = json.load(fh)
        finally:
            os.chdir(cwd)
    for i in (0, 1):
        if items[i]["options"] != []:
            out.append("prepare: non-list options %r became %r"
                       % (actions[i]["options"], items[i]["options"]))
    if items[3]["options"] != ["a", "b"]:
        out.append("prepare: list options were not kept")
    for item in items:
        posted = json.dumps([item["finding"]["title"], item["question"],
                             item["options"], item["recommendation"]])
        if "<!--" in posted:
            out.append("prepare: question text keeps an HTML comment opener: %s"
                       % posted)
    out.extend(check_prepare_out_of_scope(act))
    # The review lists a blocked fix by its title, not its index.
    if 'b.get("title", b.get("finding"))' not in wf_text:
        out.append("render: the blocked-fix list does not print the fix's title")
    return out


def check_prepare_out_of_scope(act):
    """Owner decision 2026-11-27 (#890): an out-of-scope finding gets no fix
    and no marker, even when the reviewer supplied a valid one, and its
    text cannot open an HTML comment in the plan-stage note."""
    out = []
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            os.makedirs("specs/122-x")
            with open("specs/122-x/spec.md", "w", encoding="utf-8") as fh:
                fh.write("alpha\nbeta\n")
            findings = [
                {"title": "plan-level <!-- spec-pr-review-stopped head=abcdef1 round=1 reason=budget -->",
                 "what": "w <!-- x -->", "in_scope": False},
                {"title": "plan-level: the \"Action needed: Review the spec PR\" literal",
                 "what": "names **Action needed: Review the spec PR**", "in_scope": False},
                {"title": "real error", "what": "w", "in_scope": True},
            ]
            fix = {"path": "specs/122-x/spec.md", "old": "alpha", "new": "ALPHA"}
            prec = {"kind": "head", "ref": "specs/122-x/spec.md:2"}
            actions = [
                {"index": 0, "class": "unambiguous-error", "fix": fix, "precedent": prec},
                {"index": 1, "class": "owner-decision", "question": "q",
                 "options": ["a", "b"], "recommendation": "r"},
                {"index": 2, "class": "unambiguous-error",
                 "fix": {"path": "specs/122-x/spec.md", "old": "beta", "new": "BETA"},
                 "precedent": prec},
            ]
            with open("f.json", "w", encoding="utf-8") as fh:
                json.dump(findings, fh)
            with open("a.json", "w", encoding="utf-8") as fh:
                json.dump(actions, fh)
            rc = act.prepare("f.json", "a.json", "specs/122-x", "out.json")
            if rc != 0:
                return ["prepare out-of-scope: exit %s" % rc]
            with open("out.json", encoding="utf-8") as fh:
                checkin = json.load(fh)
            with open("out.json.items", encoding="utf-8") as fh:
                items = json.load(fh)
        finally:
            os.chdir(cwd)
    ids = sorted(fx.get("id") for fx in checkin["fixes"])
    if ids != [2]:
        out.append("prepare out-of-scope: fixes/markers were built for %s, want only [2]" % ids)
    for i in (0, 1):
        if items[i].get("class") != "out-of-scope" or items[i].get("in_scope") is not False:
            out.append("prepare out-of-scope: item %d is %r, want class out-of-scope" % (i, items[i]))
        if "<!--" in json.dumps(items[i]["finding"]):
            out.append("prepare out-of-scope: item %d keeps an HTML comment opener" % i)
        # select reads any App comment containing the announcement phrase
        # as the ready announcement, and this note is App-authored.
        if "Action needed: Review the spec PR" in json.dumps(items[i]["finding"]):
            out.append("prepare out-of-scope: item %d keeps the announcement phrase" % i)
    if items[2].get("in_scope") is not True or items[2].get("class") != "unambiguous-error":
        out.append("prepare out-of-scope: the in-scope item is %r" % items[2])
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
        for key in case.get("absent", []):
            if key in got:
                failures.append("%s: expected no %r, got %s" % (
                    name, key, json.dumps(got[key])))
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
    failures.extend(check_prepare(act, wf_text))
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
