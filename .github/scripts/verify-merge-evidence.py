#!/usr/bin/env python3
"""Gate (unnumbered) -- the merge evidence audit records every verdict by code,
and only watches (specs/125-merge-evidence-audit).

Drives .github/scripts/fixtures/merge-evidence/ through the pure half of
wc_merge_evidence.py (one fixture per branch), fails a copy of the reused
condition code (FR-008 "one home"), checks the ledger rules and the ledger
download's error handling with a stubbed `gh`, and checks the workflow's shape.
Each check is shown to fail by mutating a copy of its subject in memory.
"""
import ast
import copy
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wc_merge_evidence as me  # noqa: E402
from board_item_marker import render_bump_verification  # noqa: E402
from wc_lifecycle_review_marker import write_marker  # noqa: E402
from wc_shell_harness import gh_error_stub_arm  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures", "merge-evidence")
MODULE = os.path.join(HERE, "wc_merge_evidence.py")
NOW = "2026-11-20T05:41:00Z"

# Names the reused homes own; a def of one in wc_merge_evidence.py is a copy.
# A parameter, never mutated at module level (Gate 124).
REUSED_RULE_NAMES = ("_checks_green", "_gate_suite_green", "checks_green", "gate_suite_green",
                     "_no_unresolved_human_review", "no_unresolved_human_review", "snapshot_complete",
                     "verification_run_confirms", "latest_record_at_head", "bump_records",
                     "eligible_fix_class", "last_converged_review_head", "verification_passed_at_head")
# Terminal-state literals the "checks green" rules own.
FORBIDDEN_LITERALS = ('"SUCCESS"', '"NEUTRAL"', '"SKIPPED"', '"lint"', "'SUCCESS'", "'lint'")
# FR-017: a write to a PR, a commit's checks, labels, reviews, or the repository.
WRITE_VERBS = (r"gh\s+pr\s+(merge|review|edit|comment|close)", r"gh\s+issue\s+(comment|edit|close)",
               r"gh\s+label", r"gh\s+workflow\s+run", r"git\s+push",
               r"-X\s*(POST|PUT|PATCH|DELETE)", r"--method\s*(POST|PUT|PATCH|DELETE)",
               r"check-runs", r"statuses/")
NO_READER_FILES = (".github/scripts/board_merge.py", ".github/scripts/lifecycle_merge_preconditions.py",
                   ".github/workflows/board-loop.yml", ".github/workflows/lifecycle-review-gate.yml")
WORKFLOW = ".github/workflows/wing-commander-merge-evidence.yml"
# SC-003 replay corpus: pending the maintainer capture (tasks.md T029). Tracked
# by the Maintenance backlog, #889 (gate 124 reads this entry; the final PR
# closes #1143, so it cannot be the tracker); delete it when sc003/ lands.
EXEMPT_SC003_PENDING = {
    "sc003-replay": dict(reason="the corpus is captured from the saved 2026-11-16 lookup by the maintainer",
                         issue=(889,)),
}


def load(*parts):
    with open(os.path.join(FIXTURES, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def build_snapshot(base_doc, case):
    snap = copy.deepcopy(base_doc["bases"][case["base"]])
    patch = copy.deepcopy(case.get("patch") or {})
    verdict_head = patch.pop("verdict_head", None)
    bump_comment = patch.pop("bump_comment", None)
    gate_marker = patch.pop("gate_marker", None)
    snap.update(patch)
    bot = {"login": base_doc["bot_login"], "type": "Bot"}
    if verdict_head:
        snap["issue_comments"] = [{"id": 1, "created_at": "2026-11-10T09:00:00Z", "user": bot,
                                   "body": "Review round 1 converged -- clean on PR #{0} (head {1})".format(
                                       snap["number"], verdict_head)}]
    if bump_comment:
        snap["comments"] = [{"id": 2, "created_at": "2026-11-10T09:00:00Z", "user": bot,
                             "body": render_bump_verification(bump_comment["head_sha"], bump_comment["tier"],
                                                              bump_comment["result"], bump_comment["run_id"])}]
        snap["counts"]["comments"] = 1
    if gate_marker:
        snap["issue_comments"] = [{"id": 3, "created_at": "2026-11-10T09:00:00Z", "user": bot,
                                   "body": "Round {0}\n\n{1}".format(gate_marker["round"], write_marker(
                                       gate_marker["round"], gate_marker["head_sha"], gate_marker["outcome"],
                                       gate_marker["findings_open"], [], [], "2026-11-10T09:00:00Z"))}]
    return snap


def case_dirs(prefix):
    return sorted(d for d in os.listdir(FIXTURES) if d.startswith(prefix)
                  and os.path.isdir(os.path.join(FIXTURES, d)))


def check_verdicts(base_doc, evaluate=None):
    evaluate = evaluate or me.evaluate
    problems = []
    for name in case_dirs("verdict-"):
        case = load(name, "case.json")
        exp = case["expect"]
        rec = evaluate(build_snapshot(base_doc, case), base_doc["bot_login"], NOW)
        got = {"kind": rec["kind"], "first_unmet": rec["first_unmet"], "complete": rec["complete"],
               "rule_applied": rec["rule_applied"]}
        for key in ("kind", "first_unmet", "complete", "rule_applied"):
            if key in exp and got[key] != exp[key]:
                problems.append("{0}: {1} is {2!r}, expected {3!r}".format(name, key, got[key], exp[key]))
        by_name = {c["name"]: c for c in rec["conditions"]}
        for cname, result in (exp.get("result_of") or {}).items():
            if by_name.get(cname, {}).get("result") != result:
                problems.append("{0}: condition {1} is not {2}".format(name, cname, result))
        if "reason_contains" in exp:
            first = by_name.get(rec["first_unmet"] or "", {})
            if exp["reason_contains"] not in first.get("reason", ""):
                problems.append("{0}: reason {1!r} lacks {2!r}".format(name, first.get("reason"), exp["reason_contains"]))
        if "reported_kinds" in exp and [r["kind"] for r in rec["reported"]] != exp["reported_kinds"]:
            problems.append("{0}: reported {1}".format(name, [r["kind"] for r in rec["reported"]]))
        # FR-009: a reported record never makes a condition met.
        if rec["reported"] and rec["kind"] in ("maintainer", "spec") and rec["first_unmet"] is None:
            problems.append("{0}: a maintainer-account record counted as evidence".format(name))
        # FR-005: a verdict from an incomplete snapshot reports nothing met past the checks.
        if not rec["complete"] and any(c["result"] == "met" for c in rec["conditions"][1:]):
            problems.append("{0}: incomplete snapshot reports a condition met".format(name))
        for cond in rec["conditions"]:
            if cond["result"] != "met" and not cond["reason"]:
                problems.append("{0}: condition {1} has no reason".format(name, cond["name"]))
    return problems


def check_audits(base_doc):
    problems = []
    for name in case_dirs("audit-"):
        case = load(name, "case.json")
        exp, merge = case["expect"], case["merge"]
        snap = build_snapshot(base_doc, case)
        info = {"pr": snap["number"], "merged_commit": merge["merged_commit"], "last_head": snap["headRefOid"],
                "merged_at": merge["merged_at"], "merged_by": merge["merged_by"]}
        ledger = me.empty_ledger()
        for rec in case.get("ledger") or []:
            me.replace_record(ledger, rec)
        cut = me.cut_snapshot(snap, merge["merged_at"])
        verdict = me.evaluate(cut, base_doc["bot_login"], NOW)
        entry = me.build_audit_entry(info, verdict, ledger)
        if entry["mark"] != exp["mark"]:
            problems.append("{0}: mark {1}, expected {2}".format(name, entry["mark"], exp["mark"]))
        if "first_unmet" in exp and verdict["first_unmet"] != exp["first_unmet"]:
            problems.append("{0}: first unmet {1}".format(name, verdict["first_unmet"]))
        if "prior_result" in exp and (entry["prior_record_result"] or {}).get("result") != exp["prior_result"]:
            problems.append("{0}: prior record result {1}".format(name, entry["prior_record_result"]))
        if "left_out" in exp and cut["left_out"] != exp["left_out"]:
            problems.append("{0}: {1} records left out, expected {2}".format(name, cut["left_out"], exp["left_out"]))
        if "decision_record" in exp and entry["decision_record"] != exp["decision_record"]:
            problems.append("{0}: decision record {1}".format(name, entry["decision_record"]))
        if "unpaired" in exp:
            got = [c["sha"] for c in me.unpaired_commits(case.get("commits") or [], [info])]
            if got != exp["unpaired"]:
                problems.append("{0}: unpaired {1}".format(name, got))
        if "section_entries" in exp:
            entries = []
            for offset in range(exp["section_entries"]):
                entries.append(me.build_audit_entry(dict(info, pr=info["pr"] + offset), verdict, ledger))
            window = me.window_bounds(case["section_now"])
            section = me.build_section(entries, [], [], window, case["section_now"], ledger)
            if window["start"] != exp["window_start"] or section["counts"]["merged"] != exp["section_entries"]:
                problems.append("{0}: window {1} / {2} entries".format(name, window["start"], section["counts"]))
            if "- #" not in section["names_only"] or section["full"].count("\n- #") != exp["section_entries"]:
                problems.append("{0}: a rendered form drops an entry".format(name))
    return problems


def check_ledger():
    problems = []
    ledger = me.empty_ledger()
    rec = {"pr": 5, "head": "h1", "computed_at": "2026-11-01T00:00:00Z", "first_unmet": "x", "complete": True}
    me.replace_record(ledger, rec)
    me.replace_record(ledger, dict(rec, first_unmet=None))
    if list(ledger["records"]) != ["5@h1"] or ledger["records"]["5@h1"]["first_unmet"] is not None:
        problems.append("ledger: a later run did not replace the (pr, head) entry")
    for pr, state, at, kept in ((1, "merged", "2026-10-25T00:00:00Z", True), (2, "merged", "2026-10-10T00:00:00Z", False),
                                (3, "closed", "2026-11-18T00:00:00Z", True), (4, "closed", "2026-11-10T00:00:00Z", False),
                                (6, "open", None, True)):
        test = me.empty_ledger()
        me.replace_record(test, {"pr": pr, "head": "h", "computed_at": NOW})
        me.prune(test, {pr: {"state": state, "at": at}}, NOW)
        if bool(test["records"]) != kept:
            problems.append("ledger: PR in state {0} at {1} {2}".format(state, at, "dropped" if kept else "kept"))
    unknown = me.empty_ledger()
    me.replace_record(unknown, {"pr": 9, "head": "h", "computed_at": NOW})
    me.prune(unknown, {}, NOW)
    if not unknown["records"]:
        problems.append("ledger: an entry whose PR cannot be found was dropped")
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "ledger.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        try:
            me.load_ledger(bad)
            problems.append("ledger: an unparseable ledger did not fail")
        except me.LedgerError:
            pass
        loaded, found = me.load_ledger(os.path.join(tmp, "absent.json"))
        if found or loaded["records"]:
            problems.append("ledger: an absent ledger did not start empty")
    return problems


def check_review_round1():
    """Review gate round 1: each fix fails this check without it."""
    problems = []
    head = "abc"
    snap = {"headRefOid": head, "files": [{"path": "a"}], "commits": [{"sha": head}],
            "comments": [{"created_at": "2026-11-01T00:00:00Z"}, {"created_at": "2026-11-03T00:00:00Z"}],
            "counts": {"files": 1, "commits": 1, "comments": 2, "head_sha": head}}
    cut = me.cut_snapshot(snap, "2026-11-02T00:00:00Z")
    if len(cut["comments"]) != 1 or not me.board_merge.snapshot_complete(cut):
        problems.append("cut: a post-merge comment left the cut snapshot incomplete")
    recs = [{"pr": 1, "head": "h1", "computed_at": "2026-11-01T00:00:00Z"},
            {"pr": 1, "head": "h2", "computed_at": "2026-11-02T00:00:00Z"},
            {"pr": 2, "head": "h3", "computed_at": "2026-11-01T00:00:00Z"}]
    calls = []
    got = me.open_verdicts_latest("o/r", {"records": {"%s@%s" % (r["pr"], r["head"]): r for r in recs}},
                                  lambda repo, r: calls.append(r["pr"]) or True)
    if [r["head"] for r in got] != ["h2", "h3"] or sorted(calls) != [1, 2]:
        problems.append("open verdicts: not the latest head of each PR, or a PR looked up twice")
    if me.unpaired_commits([{"sha": "x"}, {"sha": "y"}, {"sha": "z"}],
                           [{"merged_commit": "x", "commits": ["y"]}]) != [{"sha": "z"}]:
        problems.append("unpaired: a rebase merge's other commits were listed")
    if me.assign_kind({"headRefName": "spec/001-a", "cross_repository": False, "baseRefName": "trunk"},
                      "bot", base_branch="trunk")[0] != "final":
        problems.append("kind: the default branch parameter is ignored")
    return problems


def _stub_gh(directory, mode):
    list_arm = (gh_error_stub_arm("run list", "404", "Not Found") if mode == "404"
                else gh_error_stub_arm("run list", "502", "Bad Gateway") if mode == "502"
                else '    printf \'[]\'\n    exit 0\n')
    script = "#!/usr/bin/env bash\ncase \"$*\" in\n  \"run list\"*)\n" + list_arm + "    ;;\nesac\nexit 1\n"
    path = os.path.join(directory, "gh")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def check_download_errors():
    problems = []
    old_path = os.environ.get("PATH", "")
    try:
        for mode, expect_raise in (("404", False), ("empty", False), ("502", True)):
            with tempfile.TemporaryDirectory() as tmp:
                _stub_gh(tmp, mode)
                os.environ["PATH"] = tmp + os.pathsep + old_path
                try:
                    got = me.download_ledger("o/r", "main", tmp)
                    if expect_raise:
                        problems.append("download: HTTP 502 did not fail")
                    elif got is not None:
                        problems.append("download: mode {0} returned {1}".format(mode, got))
                except subprocess.CalledProcessError:
                    if not expect_raise:
                        problems.append("download: mode {0} failed instead of starting empty".format(mode))
    finally:
        os.environ["PATH"] = old_path
    return problems


def check_single_home(source, exempt=()):
    """FR-008: no def of a reused rule, no terminal-state literal."""
    problems = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name in REUSED_RULE_NAMES and node.name not in exempt:
            problems.append("wc_merge_evidence.py defines {0}, a copy of a reused condition".format(node.name))
    for literal in FORBIDDEN_LITERALS:
        if literal in source:
            problems.append("wc_merge_evidence.py contains {0}, a terminal-state literal the reused rules own".format(literal))
    return problems


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


def check_workflow(text):
    problems = []
    if not text:
        return ["{0} is missing".format(WORKFLOW)]
    for const, label in ((me.LEDGER_ARTIFACT, "ledger"), (me.SECTION_ARTIFACT, "section")):
        if "name: {0}\n".format(const) not in text:
            problems.append("the workflow uploads no artifact named {0} ({1} constant)".format(const, label))
    for m in re.finditer(r"name:\s*(merge-evidence-[a-z-]+)\s*\n", text):
        if m.group(1) not in (me.LEDGER_ARTIFACT, me.SECTION_ARTIFACT):
            problems.append("the workflow uploads an artifact {0} no constant names".format(m.group(1)))
    return problems


def check_shape(text, write_verbs=WRITE_VERBS):
    """FR-017, FR-020 to FR-023 over the workflow's text."""
    problems = []
    try:
        import yaml
        doc = yaml.safe_load(text)
    except Exception as exc:  # unparseable is a failure of its own
        return ["the workflow does not parse: {0}".format(exc)]
    perms = doc.get("permissions") or {}
    writes = [k for k, v in perms.items() if v != "read"] if isinstance(perms, dict) else ["(not a mapping)"]
    if writes:
        problems.append("permissions are not all read-only: {0}".format(writes))
    for name, job in (doc.get("jobs") or {}).items():
        if job.get("permissions") not in (None, {}):
            problems.append("job {0} sets its own permissions".format(name))
        steps = job.get("steps") or []
        if not steps or "default branch" not in (steps[0].get("name") or ""):
            problems.append("job {0}: the first step does not refuse a non-default ref".format(name))
        if not any(s.get("id") == "pause" and "WING_COMMANDER_MERGE_EVIDENCE_PAUSED" in json.dumps(s) for s in steps):
            problems.append("job {0}: no pause step on WING_COMMANDER_MERGE_EVIDENCE_PAUSED".format(name))
        for s in steps:
            uses = s.get("uses") or ""
            if "claude" in uses.lower() or "anthropic" in uses.lower():
                problems.append("job {0} runs an agent step: {1}".format(name, uses))
    if "always()" in text or "!cancelled()" in text:
        problems.append("the workflow uses always() or !cancelled(): a failed read must stop the upload")
    for verb in write_verbs:
        if re.search(verb, text):
            problems.append("the workflow can write: matches {0}".format(verb))
    return problems


def check_no_reader(files=None):
    """FR-019: no merge job or rule mentions the artifacts or the module."""
    problems = []
    needles = (me.LEDGER_ARTIFACT, me.SECTION_ARTIFACT, "wc_merge_evidence", "merge-evidence")
    for rel, text in (files or {r: read(r) for r in NO_READER_FILES}).items():
        for needle in needles:
            if needle in text:
                problems.append("{0} references {1}: a merge path must read none of this feature".format(rel, needle))
    return problems


def check_negatives(text):
    """Each shape and no-reader check is shown to fail on a broken copy; the
    EXEMPT_* tables are never mutated."""
    problems = []
    broken = {
        "write permission": text.replace("contents: read", "contents: write", 1),
        "always()": text.replace("if: steps.pause.outputs.paused != 'true'", "if: always()", 1),
        "agent step": text.replace("actions/checkout@v5", "anthropics/claude-code-action@v1", 1),
        "merge verb": text + "\n        run: gh pr merge 1\n",
        "no pause step": text.replace("WING_COMMANDER_MERGE_EVIDENCE_PAUSED", "SOMETHING_ELSE"),
        "no refusal first": text.replace("Refuse a run off the default branch", "Something else", 1),
    }
    for label, mutated in broken.items():
        if mutated == text or not check_shape(mutated):
            problems.append("self-check: the shape check did not notice: {0}".format(label))
    reader = {r: read(r) for r in NO_READER_FILES}
    reader[NO_READER_FILES[0]] += "\n# reads merge-evidence-ledger\n"
    if not check_no_reader(reader):
        problems.append("self-check: the no-reader check did not notice a reference")
    return problems


def main():
    base_doc = load("_base.json")
    problems = check_verdicts(base_doc) + check_audits(base_doc) + check_ledger() + check_download_errors() \
        + check_review_round1()
    problems += check_single_home(read(".github/scripts/wc_merge_evidence.py"))
    wf = os.path.join(REPO, WORKFLOW)
    if os.path.exists(wf):
        text = read(WORKFLOW)
        problems += check_workflow(text) + check_shape(text) + check_no_reader() + check_negatives(text)
    # Shown to fail: each check must notice a broken subject.
    notice = check_single_home(read(".github/scripts/wc_merge_evidence.py")
                               + "\ndef _checks_green(rollup):\n    return rollup\n")
    if not notice:
        problems.append("self-check: a copy of a reused rule was not noticed")
    if not check_single_home(read(".github/scripts/wc_merge_evidence.py") + '\nX = "SUCCESS"\n'):
        problems.append("self-check: a terminal-state literal was not noticed")
    broken = check_verdicts(base_doc, evaluate=lambda snap, bot, now: dict(
        me.evaluate(snap, bot, now), first_unmet=None, complete=True))
    if not broken:
        problems.append("self-check: a verdict that always reports met was not noticed")
    for p in problems:
        print("::error::" + p)
    if problems:
        return 1
    print("verify-merge-evidence: {0} verdict and {1} audit fixtures, ledger and download checks pass; "
          "SC-003 replay pending the maintainer capture ({2})".format(
              len(case_dirs("verdict-")), len(case_dirs("audit-")),
              "#{0}".format(EXEMPT_SC003_PENDING["sc003-replay"]["issue"][0])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
