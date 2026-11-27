#!/usr/bin/env python3
"""Gate (unnumbered) -- the merge evidence audit records every verdict by code,
and only watches (specs/125-merge-evidence-audit).

Drives .github/scripts/fixtures/merge-evidence/ through the pure half of
wc_merge_evidence.py (one fixture per branch), fails a copy of the reused
condition code (FR-008 "one home"), checks the ledger rules and the ledger
download's error handling with a stubbed `gh`, checks the workflow's shape,
and replays the SC-003 corpus (fixtures/merge-evidence/sc003/) against an
expected file written by hand, without this code. Each check is shown to fail by mutating a copy of its subject in memory.
"""
import ast
import copy
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wc_merge_evidence as me  # noqa: E402
from board_item_marker import render_bump_verification  # noqa: E402
from wc_lifecycle_review_marker import write_marker  # noqa: E402
import wc_shared_review  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures", "merge-evidence")
MODULE = os.path.join(HERE, "wc_merge_evidence.py")
NOW = "2026-11-20T05:41:00Z"

# Names the reused homes own; a def of one in wc_merge_evidence.py is a copy.
# A parameter, never mutated at module level (Gate 124).
REUSED_RULE_NAMES = ("_checks_green", "_gate_suite_green", "checks_green", "gate_suite_green",
                     "_no_unresolved_human_review", "no_unresolved_human_review", "snapshot_complete",
                     "verification_run_confirms", "latest_record_at_head", "bump_records",
                     "eligible_fix_class", "last_converged_review_head", "verification_passed_at_head",
                     # wc_shared_review's: the round record's parse, its run's
                     # read and its confirmation have one home there.
                     "parse_records", "confirm_record", "latest_round_for_commit", "fetch_run_facts",
                     "confirmed_from_github")
# Terminal-state literals the "checks green" rules own.
# '"lifecycle-review-gate"' is lifecycle_readiness.OWN_STATUS_CONTEXT's
# (#1173 round 5, finding 3).
FORBIDDEN_LITERALS = ('"SUCCESS"', '"NEUTRAL"', '"SKIPPED"', '"lint"', "'SUCCESS'", "'lint'",
                      '"lifecycle-review-gate"', "'lifecycle-review-gate'")
# FR-017: a write to a PR, a commit's checks, labels, reviews, or the repository.
WRITE_VERBS = (r"gh\s+pr\s+(merge|review|edit|comment|close)", r"gh\s+issue\s+(comment|edit|close)",
               r"gh\s+label", r"gh\s+workflow\s+run", r"git\s+push",
               r"-X\s*(POST|PUT|PATCH|DELETE)", r"--method\s*(POST|PUT|PATCH|DELETE)",
               r"check-runs", r"statuses/")
NO_READER_FILES = (".github/scripts/board_merge.py", ".github/scripts/lifecycle_merge_preconditions.py",
                   ".github/workflows/board-loop.yml", ".github/workflows/lifecycle-review-gate.yml")
WORKFLOW = ".github/workflows/wing-commander-merge-evidence.yml"
# Finding 8 (round 3): the refusal and the pause test have one home, this
# composite, whose pause test calls wc_board_status._switch_on.
GUARD_USES = "./.github/actions/wing-commander-watch-guard"
GUARD_ACTION = ".github/actions/wing-commander-watch-guard/action.yml"
CHECKOUT_REF = "${{ github.event.repository.default_branch }}"
# The proof list uses the guard too, with its dispatch-only refusal
# (#1173 round 5, finding 7); no workflow keeps a shell copy of the test.
PROOF_LIST_WORKFLOW = ".github/workflows/wing-commander-proof-list.yml"
# SC-003 (tasks.md T029): the replay supplies its own window (FR-012; the
# report never does), spec 124's SC-001 window, and the 48 merges in it.
SC003_DIR = os.path.join(FIXTURES, "sc003")
SC003_WINDOW = {"start": "2026-10-15T00:00:00Z", "end": "2026-11-17T00:00:00Z"}
SC003_MERGES = 48


def load(*parts):
    with open(os.path.join(FIXTURES, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def build_snapshot(base_doc, case):
    snap = copy.deepcopy(base_doc["bases"][case["base"]])
    patch = copy.deepcopy(case.get("patch") or {})
    verdict_head = patch.pop("verdict_head", None)
    bump_comment = patch.pop("bump_comment", None)
    gate_marker = patch.pop("gate_marker", None)
    shared_review = patch.pop("shared_review", None)
    shared_runs = patch.pop("shared_review_runs", None)
    snap.update(patch)
    bot = {"login": base_doc["bot_login"], "type": "Bot"}
    if shared_review is not None:
        snap["comments"], runs = shared_review_comments(shared_review, shared_runs, bot)
        snap["counts"]["comments"] = len(snap["comments"])
        if shared_runs is not None:
            snap["shared_review_runs"] = runs
    if verdict_head:
        snap["issue_comments"] = [{"id": 1, "created_at": "2026-11-10T09:00:00Z", "user": bot,
                                   # The whole comment the review job posts: board_item_marker
                                   # reads a converged verdict only in that shape (#889).
                                   "body": ("Review round 1 converged -- zero open in-scope findings on PR #{0} "
                                            "(head {1}). Proceeding to readiness.\n\n"
                                            "<!-- wing-commander-board-item: {{\"step\": \"readiness\"}} -->").format(
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


SHARED_REVIEWER_COMMIT = "c" * 40


def shared_review_run(run_id, record_head, override):
    """The facts of a shared-reviewer run that confirms its record, with the
    case's `override` keys replaced."""
    run = {"id": int(run_id), "path": wc_shared_review.WRAPPER_PATH, "head_branch": "main", "repository": "o/r",
           "status": "completed", "conclusion": "success", "head_sha": SHARED_REVIEWER_COMMIT,
           "referenced_workflows": ["o/r/{0}@refs/heads/main".format(wc_shared_review.WORKFLOW_PATH)],
           "artifacts": [wc_shared_review.ARTIFACT_PREFIX + record_head]}
    run.update(override or {})
    return run


def shared_review_comments(rounds, runs, bot):
    """A case's `shared_review` rounds as the comments the reviewer posts, and
    its `shared_review_runs` ({run id: override, or null for a run that does
    not exist}) as run facts. A run id the case leaves out was not read."""
    comments, facts = [], {}
    for i, rnd in enumerate(rounds):
        record = {"round": rnd["round"], "head_sha": rnd["head_sha"], "verdict": rnd["verdict"],
                  "run_id": rnd["run_id"], "reviewer_commit": SHARED_REVIEWER_COMMIT, "findings": [],
                  "open_set": []}
        user = bot if rnd.get("author") != "owner" else {"login": "owner", "type": "User"}
        comments.append({"id": 100 + i, "created_at": "2026-11-10T09:{0:02d}:00Z".format(i), "user": user,
                         "body": wc_shared_review.build_record(record)})
        if runs is not None and rnd["run_id"] in runs:
            override = runs[rnd["run_id"]]
            facts[rnd["run_id"]] = None if override is None else shared_review_run(rnd["run_id"], rnd["head_sha"],
                                                                                   override)
    return comments, facts


def _without_maintainer_comments(snap, bot_login):
    """The same snapshot with every comment not by the App taken out."""
    out = copy.deepcopy(snap)
    for field in ("comments", "issue_comments"):
        if out.get(field) is not None:
            out[field] = [c for c in out[field] if (c.get("user") or {}).get("login") == bot_login
                          and (c.get("user") or {}).get("type") == "Bot"]
    if isinstance(out.get("counts"), dict) and out.get("comments") is not None:
        out["counts"] = dict(out["counts"], comments=len(out["comments"]))
    return out


def case_dirs(prefix):
    return sorted(d for d in os.listdir(FIXTURES) if d.startswith(prefix)
                  and os.path.isdir(os.path.join(FIXTURES, d)))


def check_verdicts(base_doc, evaluate=None):
    evaluate = evaluate or me.evaluate
    problems = []
    for name in case_dirs("verdict-"):
        case = load(name, "case.json")
        exp = case["expect"]
        snap = build_snapshot(base_doc, case)
        rec = evaluate(snap, base_doc["bot_login"], NOW)
        try:
            me.validate_record(rec)
        except me.RecordError as exc:
            problems.append("{0}: the verdict breaks the VerdictRecord type: {1}".format(name, exc))
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
        # FR-009: a reported record never makes a condition met. Without
        # every maintainer-account comment, each condition reads the same.
        if rec["reported"]:
            bare = evaluate(_without_maintainer_comments(snap, base_doc["bot_login"]), base_doc["bot_login"], NOW)
            if [c["result"] for c in bare["conditions"]] != [c["result"] for c in rec["conditions"]]:
                problems.append("{0}: a maintainer-account record counted as evidence".format(name))
        reported_by_name = {c["name"]: c for c in rec.get("reported_conditions") or []}
        for cname, result in (exp.get("reported_result_of") or {}).items():
            if reported_by_name.get(cname, {}).get("result") != result:
                problems.append("{0}: reported condition {1} is not {2}".format(name, cname, result))
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
    # Finding 6 (round 3): the watching period ends 30 days after the
    # ledger's first write, carried forward, never after a record's time.
    first = me.empty_ledger()
    if "first_written_at" not in first:
        problems.append("ledger: an empty ledger has no first_written_at")
    stamp = getattr(me, "stamp_ledger", None)
    if stamp is None:
        problems.append("ledger: no stamp_ledger() sets first_written_at")
    else:
        stamp(first, "2026-11-01T07:07:00Z", "1")
        stamp(first, "2026-11-12T07:07:00Z", "2")
        if (first.get("first_written_at"), first.get("written_at"), first.get("written_by_run")) != (
                "2026-11-01T07:07:00Z", "2026-11-12T07:07:00Z", "2"):
            problems.append("ledger: a later write did not carry first_written_at forward: {0}".format(first))
    first["first_written_at"] = "2026-11-01T07:07:00Z"
    me.replace_record(first, {"pr": 9, "head": "h", "computed_at": "2026-11-12T07:07:00Z"})
    ends = me.build_section([], [], [], me.window_bounds(NOW), NOW, first)["watching_ends"]
    if ends != "2026-12-01":
        problems.append("ledger: the watching period ends {0}, not 30 days after the first write (2026-12-01)".format(ends))
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


def check_review_round2():
    """Review gate round 2: each fix fails this check without it."""
    problems = []
    src = read(".github/scripts/wc_merge_evidence.py")
    ext = src[src.index("def _extend_with_evidence"):src.index("def collect")]
    call = ext.find("_assign_once(") if "_assign_once(" in ext else ext.find("assign_kind(")
    if call < 0 or ext.index('snap["cross_repository"]') > call:
        problems.append("kind: assign_kind runs before cross_repository is set")
    if '"--limit", "20"' in src:
        problems.append("ledger: the run lookback is still 20 runs")
    if "search/issues" in src:
        problems.append("audit: merged PRs are found through the capped search API")
    if '(entry["merged_commit"] or "unknown")[:12]' not in src:
        problems.append("line: a null merge commit is not handled")
    if '--paginate' not in src[src.index("def _rest_rollup"):src.index("def _merged_snapshot")].split("/status")[1]:
        problems.append("rollup: commit statuses are read without pagination")
    cut = me.cut_snapshot({"statusCheckRollup": [
        {"name": "c", "startedAt": "2026-11-01T00:00:00Z", "completedAt": None},
        {"name": "d", "startedAt": "2026-11-03T00:00:00Z"}]}, "2026-11-02T00:00:00Z")
    if [e["name"] for e in cut["statusCheckRollup"]] != ["c"]:
        problems.append("cut: a check is cut on its completion time, not its start")
    return problems


class _Patched:
    """Swaps module attributes for in-process fakes and puts them back."""

    def __init__(self, **swaps):
        self.swaps = swaps
        self.saved = {}

    def __enter__(self):
        for dotted, value in self.swaps.items():
            owner, name = self._owner(dotted)
            self.saved[dotted] = getattr(owner, name)
            setattr(owner, name, value)
        return self

    def __exit__(self, *exc):
        for dotted, value in self.saved.items():
            owner, name = self._owner(dotted)
            setattr(owner, name, value)

    @staticmethod
    def _owner(dotted):
        if dotted.startswith("board_merge__"):
            return me.board_merge, dotted[len("board_merge__"):]
        return me, dotted


def check_review_round3_rollup():
    """Finding 3 (round 3): the merged head's statuses come from their full
    history and its check runs from every attempt, so cut_rollup() can pick
    what stood at the merge."""
    problems = []
    calls = []

    def fake_gh_ok(args):
        url = args[1]
        calls.append(url)
        if "/actions/runs?" in url:
            return json.dumps({"check_suite_id": 7, "name": "lint · workflows"}) + "\n"
        if "/check-runs" in url:
            return json.dumps({"name": "lint", "status": "completed", "conclusion": "success",
                               "started_at": "2026-11-10T09:00:00Z", "completed_at": "2026-11-10T09:30:00Z",
                               "details_url": "https://github.com/o/r/actions/runs/42/job/9",
                               "check_suite": {"id": 7}}) + "\n"
        if "/statuses" in url and "--jq" in args and args[args.index("--jq") + 1].startswith(".[]"):
            return "\n".join(json.dumps({"context": "ci/x", "state": s, "created_at": t})
                             for s, t in (("failure", "2026-11-10T13:00:00Z"), ("success", "2026-11-10T11:00:00Z"))) + "\n"
        raise subprocess.CalledProcessError(1, args, "", "unexpected call {0}".format(args))

    with _Patched(_gh_ok=fake_gh_ok):
        try:
            rollup = me._rest_rollup("o/r", "abc")
        except subprocess.CalledProcessError as exc:
            return ["rollup: {0}".format(exc.stderr)]
    if not any("/check-runs?" in u and "filter=all" in u for u in calls):
        problems.append("rollup: check runs are read without filter=all, so a re-run hides the attempt at the merge")
    if not any("/statuses?" in u for u in calls):
        problems.append("rollup: commit statuses come from the combined status, not their history")
    if len([e for e in rollup if e.get("context") == "ci/x"]) != 2:
        problems.append("rollup: not every status in the history is kept for the cut")
    # Live readiness keys a check run by the run id in its detailsUrl
    # (board_readiness._check_key); the audit must read it too (#889, found
    # by the code review of #1226).
    if [me.board_readiness._check_key(e) for e in rollup if e.get("name") == "lint"] != [
            ("check", "lint · workflows", "42", "lint")]:
        problems.append("rollup: a check run's details_url is not carried, so it has no run id to be keyed by")
    cut, _left = me.cut_rollup(rollup, "2026-11-10T12:00:00Z")
    if [e.get("state") for e in cut if e.get("context") == "ci/x"] != ["SUCCESS"]:
        problems.append("cut: the status as of the merge is not the latest set at or before it")
    return problems


def check_cancelled_superseded_reason():
    """#889 (found by the code review of #1196): an unmet checks condition
    names a check by its newest result. A lint run cancelled and then re-run
    (the same workflow run, a later attempt) on the same head is not why
    the merge was unmet when another check really failed."""
    rollup = [
        {"name": "lint", "workflowName": "lint · workflows", "status": "COMPLETED",
         "detailsUrl": "https://github.com/o/r/actions/runs/100/job/1",
         "conclusion": "CANCELLED", "startedAt": "2026-11-25T02:46:46Z"},
        {"name": "lint", "workflowName": "lint · workflows", "status": "COMPLETED",
         "detailsUrl": "https://github.com/o/r/actions/runs/100/job/2",
         "conclusion": "SUCCESS", "startedAt": "2026-11-25T02:52:57Z"},
        {"name": "harness tests", "workflowName": "lint · workflows", "status": "COMPLETED",
         "detailsUrl": "https://github.com/o/r/actions/runs/100/job/3",
         "conclusion": "FAILURE", "startedAt": "2026-11-25T02:52:57Z"},
    ]
    problems = []
    for rule in (me.RULE_ALL, me.RULE_NO_GATE):
        got = me._checks_condition(rollup, rule)
        if got.get("result") != "unmet" or got.get("reason") != "harness tests is FAILURE":
            problems.append("cancelled-superseded reason ({0}): expected the failing check, "
                            "got {1!r}".format(rule, got))
    return problems


def check_review_round3_kind():
    """Finding 1 (round 3): the runtime half assigns each PR's kind once, with
    the run's prefixes and base branch, and evaluate() reuses it, so a
    custom-prefix final PR gets its lifecycle issue read."""
    problems = []
    reads = []

    def fake_items(url):
        return [{"filename": "a.py"}] if "/files" in url else []

    def fake_comments(repo, number):
        reads.append(number)
        return []

    def fake_gh_ok(args):
        if args[:2] == ["pr", "view"]:
            return json.dumps({"reviews": [], "isCrossRepository": False})
        if args[0] == "api" and "/issues/" in args[1]:
            return json.dumps({"labels": []})
        raise subprocess.CalledProcessError(1, args, "", "unexpected call")

    pull = {"number": 40, "head": {"sha": "h" * 40, "ref": "feature/125-thing", "repo": {"full_name": "o/r"}},
            "base": {"ref": "trunk"}, "body": "Closes #5", "user": {"login": "wc[bot]", "type": "Bot"},
            "changed_files": 1, "commits": 0, "comments": 0}
    prefixes = {"final_prefix": "feature/", "spec_prefix": "draft/", "base_branch": "trunk"}
    with _Patched(board_merge__gh_items=fake_items, _issue_comments=fake_comments, _gh_ok=fake_gh_ok,
                  _rest_rollup=lambda repo, sha: []):
        try:
            merged = me._merged_snapshot("o/r", pull, "wc[bot]", None, **prefixes)
            opened = {"number": 41, "headRefOid": "h" * 40, "headRefName": "feature/125-thing", "baseRefName": "trunk",
                      "body": "Closes #6", "author": {"login": "app/wc", "is_bot": True}}
            me._extend_with_evidence("o/r", opened, "wc[bot]", [], **prefixes)
        except (TypeError, subprocess.CalledProcessError) as exc:
            return ["kind: the runtime half cannot take the run's prefixes and base branch: {0}".format(exc)]
    if not (5 in reads and 6 in reads):  # 40 is the merged PR's own thread
        problems.append("kind: a custom-prefix final PR's lifecycle issue was not read (read {0})".format(reads))
    for label, snap in (("merged", merged), ("open", opened)):
        if any("no evidence issue" in n for n in snap.get("not_read") or []):
            problems.append("kind: the {0} snapshot says no evidence issue is linked".format(label))
        # Called with the default prefixes: the kind assigned while reading wins.
        if me.evaluate(snap, "wc[bot]", NOW)["kind"] != "final":
            problems.append("kind: evaluate() did not reuse the kind the {0} snapshot was read with".format(label))
    return problems


def check_review_round3_linked_issue():
    """Finding 7 (round 3): a final PR's evidence issue is finalize.yml's
    "Lifecycle issue: #N" line, else a GitHub closing keyword; an earlier
    mention ("Refs #N", "for #N") never picks it."""
    problems = []
    with open(os.path.join(REPO, ".github", "workflows", "finalize.yml"), encoding="utf-8") as fh:
        if 'echo "Lifecycle issue: #$ISSUE"' not in fh.read():
            problems.append("linked issue: finalize.yml no longer writes the `Lifecycle issue: #N` line this reads")
    cases = (("Refs #900, done for #901.\n\nCloses #1143", 1143),
             ("- Fold (2026-11-22, review by a reviewer, #1143) 98196176: folded.\nSee #77.\n\nLifecycle issue: #1143\r\n",
              1143),
             ("Refs #900\nLifecycle issue: #1143", 1143),
             ("fixed #8", 8), ("Resolves: #9", 9), ("close #10", 10),
             ("for #901, refs #902, ref #903", None), ("Lifecycle issue: #12 and more", None))
    for body, want in cases:
        got = me.linked_issue("final", {"body": body}, "o/r")
        if got != want:
            problems.append("linked issue: {0!r} links #{1}, expected {2}".format(body, got, want))
    # The closing-keyword forms CLOSING_RE reads, not only a bare #N; another
    # repository's issue links nothing.
    for body, want in (("Closes o/r#21", 21), ("Fixes https://github.com/o/r/issues/22", 22),
                       ("resolves GH-23", 23), ("Closes other/repo#24", None)):
        got = me.linked_issue("final", {"body": body}, "o/r")
        if got != want:
            problems.append("linked issue: {0!r} links #{1}, expected {2}".format(body, got, want))
    return problems


def check_review_round3_open():
    """Finding 4 (round 3): an open PR whose state cannot be read stays in
    the report, marked incomplete and naming what was not read (FR-005)."""
    problems = []
    recs = {"1@h1": {"pr": 1, "head": "h1", "kind": "maintainer", "computed_at": NOW, "complete": True,
                     "not_read": [], "first_unmet": "review_round_record"},
            "2@h2": {"pr": 2, "head": "h2", "kind": "maintainer", "computed_at": NOW, "complete": True,
                     "not_read": [], "first_unmet": "review_round_record"},
            "3@h3": {"pr": 3, "head": "h3", "kind": "maintainer", "computed_at": NOW, "complete": True,
                     "not_read": [], "first_unmet": None}}
    ledger = {"records": copy.deepcopy(recs)}
    states = {1: True, 2: None, 3: False}
    got = me.open_verdicts_latest("o/r", ledger, lambda repo, r: states[r["pr"]])
    by_pr = {r["pr"]: r for r in got}
    if sorted(by_pr) != [1, 2]:
        problems.append("open verdicts: a PR whose state could not be read was dropped, or a closed one kept: {0}".format(
            sorted(by_pr)))
    elif by_pr[2].get("complete") is not False or not any("still open" in n for n in by_pr[2].get("not_read") or []):
        problems.append("open verdicts: an unread PR state is not marked incomplete and named")
    if ledger["records"] != recs:
        problems.append("open verdicts: marking an unread state changed the ledger's own record")
    # #1173 review R2: _is_open itself says "not read" (None) on a read error.
    for label, fake, want in (("a failed read", lambda args: (_ for _ in ()).throw(
                                  subprocess.CalledProcessError(1, args, "", "gh: Bad Gateway (HTTP 502)")), None),
                              ("unparseable output", lambda args: "not json", None),
                              ("an open PR", lambda args: json.dumps({"state": "open"}), True),
                              ("a merged PR", lambda args: json.dumps({"state": "closed", "merged_at": NOW}), False)):
        with _Patched(_gh_ok=fake):
            got_state = me._is_open("o/r", {"pr": 2})
        if got_state is not want:
            problems.append("open verdicts: _is_open on {0} returned {1!r}, expected {2!r}".format(label, got_state, want))
    if 2 in by_pr:
        section = me.build_section([], [], got, me.window_bounds(NOW), NOW, me.empty_ledger())
        if "#2" not in section["full"] or "INCOMPLETE" not in section["full"] or "#2" not in section["names_only"]:
            problems.append("open verdicts: the rendered section does not name the unread PR as incomplete")
    return problems


class _Done:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _ledger_gh(mode, downloads):
    """A fake `_run` for download_ledger(): `mode` shapes the artifact
    listing; 150 newer runs upload no ledger (a pause of about six days),
    and only run 5 still holds one. `downloads` records the runs fetched."""
    def artifact(rid, created, branch="main", expired=False):
        return {"name": me.LEDGER_ARTIFACT, "expired": expired, "created_at": created,
                "workflow_run": {"id": rid, "head_branch": branch}}
    listing = {"artifacts": [artifact(8, "2026-11-19T07:07:00Z", expired=True),
                             artifact(7, "2026-11-19T06:07:00Z", branch="topic"),
                             artifact(6, "2026-11-19T05:07:00Z"),
                             artifact(5, "2026-11-13T07:07:00Z"),
                             artifact(4, "2026-11-12T07:07:00Z")]}
    paths = {6: ".github/workflows/other.yml"}
    # #1173 review R1: a pull_request run and a fork's run (head branch
    # `main`, same path) both upload a newer forged ledger; neither counts.
    listing["artifacts"][2:2] = [artifact(11, "2026-11-19T04:07:00Z"), artifact(12, "2026-11-19T03:07:00Z")]
    runs_extra = {11: {"event": "pull_request"}, 12: {"head_repository": {"full_name": "fork/r"}}}

    def fake(args):
        text = " ".join(args)
        if args[:3] == ["gh", "run", "list"]:
            return _Done(stdout=json.dumps([{"databaseId": 1000 + i} for i in range(150)]))
        if "actions/artifacts?" in text and "name={0}".format(me.LEDGER_ARTIFACT) in text:
            if mode in ("404", "502"):
                return _Done(1, "", "gh: {0} (HTTP {1})".format("Not Found" if mode == "404" else "Bad Gateway", mode))
            return _Done(stdout=json.dumps({"artifacts": []} if mode == "empty" else listing))
        match = re.search(r"actions/runs/(\d+)$", text)
        if args[:2] == ["gh", "api"] and match:
            rid = int(match.group(1))
            run = {"id": rid, "path": paths.get(rid, ".github/workflows/" + me.WORKFLOW_FILE), "event": "schedule",
                   "head_branch": "main", "head_repository": {"full_name": "o/r"}}
            run.update(runs_extra.get(rid, {}))
            return _Done(stdout=json.dumps(run))
        if args[:3] == ["gh", "run", "download"]:
            downloads.append(int(args[3]))
            if mode == "download-502":
                return _Done(1, "", "gh: Bad Gateway (HTTP 502)")
            if mode == "all-missing":
                return _Done(1, "", "no valid artifacts found to download")
            if int(args[3]) in (5, 11, 12):
                return _Done()
            return _Done(1, "", "no valid artifacts found to download")
        return _Done(1, "", "unexpected call: " + text)
    return fake


def check_download_errors():
    """The ledger is found by artifact name (finding 5, round 3); a 404 or an
    empty listing starts empty, any other failure fails the run. In-process,
    so it runs wherever the gate does."""
    problems = []
    # "all-missing" (#1173 round 5, finding 5): ledgers exist and none downloads,
    # so the run must fail rather than start an empty ledger over them.
    for mode, expect in (("404", None), ("empty", None), ("502", "raise"), ("download-502", "raise"),
                         ("all-missing", "raise"),
                         ("found", 5)):
        downloads = []
        with _Patched(_run=_ledger_gh(mode, downloads)):
            try:
                got = me.download_ledger("o/r", "main", "dir")
            except (subprocess.CalledProcessError, me.LedgerError):
                if expect != "raise":
                    problems.append("download: mode {0} failed instead of {1}".format(mode, expect))
                continue
        if expect == "raise":
            problems.append("download: mode {0} did not fail".format(mode))
        elif expect is None and got is not None:
            problems.append("download: mode {0} returned {1}".format(mode, got))
        elif expect == 5 and (got != os.path.join("dir", me.LEDGER_FILE) or downloads != [5]):
            problems.append("download: after 150 runs with no ledger, the newest unexpired default-branch "
                            "ledger of this workflow was not the one fetched (got {0}, fetched {1})".format(
                                got, downloads))
    return problems


# #1173 final review F1: comparing the review gate's marker fields is the
# lifecycle merge preconditions' job; a copy of it fails.
MARKER_COMPARISON_RE = re.compile(r"""\.get\(\s*["'](?:head_sha|outcome|findings_open)["']\s*\)\s*[!=]=""")


def check_single_home(source, exempt=()):
    """FR-008: no def of a reused rule, no terminal-state literal, no
    re-typed comparison of the review gate's marker."""
    problems = []
    for match in MARKER_COMPARISON_RE.finditer(source):
        problems.append("wc_merge_evidence.py compares a review-gate marker field ({0}); call "
                        "lifecycle_merge_preconditions.evaluate_from_snapshot".format(match.group(0)))
    # #1173 review R1: run provenance has one home, wc_board_status.
    if "wc_board_status.trusted_watcher_run(" not in source or '"workflow_dispatch"' in source:
        problems.append("wc_merge_evidence.py does not take run provenance from wc_board_status.trusted_watcher_run")
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
    # Finding 2 (round 3): the App's login has a default, set once for every
    # job, so an unset variable does not make every verdict incomplete.
    login = ((doc.get("env") or {}).get("BOT_LOGIN") or "")
    if not re.fullmatch(r"\$\{\{ vars\.WING_COMMANDER_BOT_LOGIN \|\| '[a-z0-9-]+\[bot\]' \}\}", login):
        problems.append("BOT_LOGIN is not set once at workflow level with a `<slug>[bot]` default: {0!r}".format(login))
    if re.search(r"^\s+BOT_LOGIN:", text.split("\njobs:", 1)[-1], re.M):
        problems.append("a job or step sets BOT_LOGIN again, past the workflow-level default")
    perms = doc.get("permissions") or {}
    writes = [k for k, v in perms.items() if v != "read"] if isinstance(perms, dict) else ["(not a mapping)"]
    if writes:
        problems.append("permissions are not all read-only: {0}".format(writes))
    for name, job in (doc.get("jobs") or {}).items():
        if job.get("permissions") not in (None, {}):
            problems.append("job {0} sets its own permissions".format(name))
        steps = job.get("steps") or []
        # Finding 8 (round 3): checkout, then the guard composite, before any
        # step that reads GitHub (FR-021).
        if len(steps) < 2 or not str(steps[0].get("uses") or "").startswith("actions/checkout@") \
                or steps[0].get("if") or steps[1].get("uses") != GUARD_USES:
            problems.append("job {0}: the steps do not open with checkout, then {1}, the refusal".format(
                name, GUARD_USES))
        # FR-021 (owner's session, 2026-11-22): the checkout is pinned to the
        # default branch, so a refused dispatch never runs another ref's code.
        elif (steps[0].get("with") or {}).get("ref") != CHECKOUT_REF \
                or (steps[0].get("with") or {}).get("persist-credentials") is not False:
            problems.append("job {0}: the checkout is not pinned to {1} with persist-credentials: false".format(
                name, CHECKOUT_REF))
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


def _run_blocks(doc):
    for job in ((doc or {}).get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("run"):
                yield step["run"]
    for step in (((doc or {}).get("runs") or {}).get("steps") or []):
        if step.get("run"):
            yield step["run"]


_PAUSE_SHELL_RE = re.compile(r"tr\s+'\[:upper:\]'\s+'\[:lower:\]'[^\n]*xargs")


def check_guard_single_home(workflow_text, action_text, workflows=None, copies_left=()):
    """Finding 8 (round 3), CLAUDE.md "Shared logic has exactly one home":
    the merge-evidence workflow pastes neither the refusal nor the pause
    test; the guard's pause test calls wc_board_status._switch_on rather
    than re-implementing it in shell; and no other workflow grows a shell
    copy of that test."""
    import yaml
    problems = []
    doc = yaml.safe_load(workflow_text) or {}
    for block in _run_blocks(doc):
        if "refs/heads/" in block or "paused=" in block or _PAUSE_SHELL_RE.search(block):
            problems.append("{0}: a run block re-pastes the refusal or the pause test; use {1}".format(
                WORKFLOW, GUARD_USES))
    if workflow_text.count("uses: " + GUARD_USES) != len(doc.get("jobs") or {}):
        problems.append("{0}: not every job uses {1}".format(WORKFLOW, GUARD_USES))
    if not action_text:
        return problems + ["{0} is missing".format(GUARD_ACTION)]
    blocks = list(_run_blocks(yaml.safe_load(action_text)))
    if not any("bs._switch_on(" in b for b in blocks) or any(_PAUSE_SHELL_RE.search(b) for b in blocks):
        problems.append("{0}: the pause test does not call wc_board_status._switch_on".format(GUARD_ACTION))
    if workflows is None:
        wf_dir = os.path.join(REPO, ".github", "workflows")
        workflows = {".github/workflows/" + n: read(".github/workflows/" + n)
                     for n in sorted(os.listdir(wf_dir)) if n.endswith((".yml", ".yaml"))}
    for rel, other in workflows.items():
        if rel in copies_left:
            continue
        try:
            other_doc = yaml.safe_load(other)
        except Exception:
            continue
        if any(_PAUSE_SHELL_RE.search(b) and "paused=" in b for b in _run_blocks(other_doc)):
            problems.append("{0}: a shell copy of the pause test; call {1} or wc_board_status._switch_on".format(
                rel, GUARD_USES))
    return problems


def check_proof_list_guard(text):
    """Round 5, finding 7: the proof list opens with a pinned checkout, then
    the guard with its dispatch-only refusal and its own switch."""
    import yaml
    steps = next(iter(((yaml.safe_load(text) or {}).get("jobs") or {}).values()), {}).get("steps") or []
    guard = steps[1] if len(steps) > 1 else {}
    with_ = guard.get("with") or {}
    if not steps or not str(steps[0].get("uses") or "").startswith("actions/checkout@") or steps[0].get("if") \
            or (steps[0].get("with") or {}).get("ref") != CHECKOUT_REF:
        return ["{0}: the job does not open with a checkout pinned to the default branch".format(PROOF_LIST_WORKFLOW)]
    if guard.get("uses") != GUARD_USES or guard.get("id") != "pause" or with_.get("refuse-on") != "dispatch" \
            or with_.get("event") != "${{ github.event_name }}" \
            or "WING_COMMANDER_PROOF_LIST_PAUSED" not in str(with_.get("switch-value")):
        return ["{0}: the second step is not {1} (id pause, refuse-on: dispatch, the proof list's switch)".format(
            PROOF_LIST_WORKFLOW, GUARD_USES)]
    return []


def check_guard_refusal_modes(action_text):
    """The guard's refusal, run as the runner would: `every-run` refuses any
    run off the default branch, `dispatch` only a dispatch, and another
    mode fails."""
    import yaml
    step = next((st for st in yaml.safe_load(action_text)["runs"]["steps"] if "REFUSE_ON" in str(st.get("env"))), None)
    if step is None:
        return ["{0}: the refusal step takes no refuse-on mode".format(GUARD_ACTION)]
    problems = []
    for mode, event, ref, want in (("every-run", "schedule", "refs/heads/topic", 1),
                                   ("every-run", "schedule", "refs/heads/main", 0),
                                   ("dispatch", "schedule", "refs/heads/topic", 0),
                                   ("dispatch", "workflow_dispatch", "refs/heads/topic", 1),
                                   ("dispatch", "workflow_dispatch", "refs/heads/main", 0),
                                   ("dispatch", "", "refs/heads/main", 1),
                                   ("sometimes", "schedule", "refs/heads/main", 1)):
        env = dict(os.environ, REF=ref, EVENT=event, DEFAULT_BRANCH="main", WHAT="x runs", REFUSE_ON=mode)
        got = subprocess.run(["bash", "-c", step["run"]], capture_output=True, text=True, env=env).returncode
        if (got != 0) != bool(want):
            problems.append("{0}: refuse-on {1}, {2} on {3} exits {4}".format(GUARD_ACTION, mode, event, ref, got))
    return problems


def check_guard_agreement(action_text):
    """The guard's pause step, run as the runner would, agrees with
    wc_board_status._switch_on on padded and mixed-case values."""
    import yaml
    import wc_board_status as bs
    step = next((st for st in yaml.safe_load(action_text)["runs"]["steps"] if st.get("id") == "pause"), None)
    if step is None:
        return ["{0}: no step with id pause".format(GUARD_ACTION)]
    problems = []
    for value in ("true", "TRUE", "  True  ", "\ttrue\n", "false", "", "yes", "truee", "1"):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "output")
            open(out, "w").close()
            env = dict(os.environ, SWITCH_VALUE=value, SWITCH_NAME="X", GITHUB_OUTPUT=out, SCRIPTS=HERE)
            run = subprocess.run(["bash", "-c", step["run"]], capture_output=True, text=True, env=env)
            with open(out, encoding="utf-8") as fh:
                got = fh.read().split()
        if run.returncode != 0 or got not in (["paused=true"], ["paused=false"]):
            problems.append("{0}: the pause step failed on {1!r}: {2}".format(GUARD_ACTION, value, run.stderr.strip()))
        elif (got == ["paused=true"]) != bs._switch_on(value):
            problems.append("{0}: the pause step disagrees with _switch_on on {1!r}".format(GUARD_ACTION, value))
    return problems


def check_guard_negatives(text, action):
    """Shown to fail: a re-pasted pause step, a shell pause test in the
    guard, and a shell copy in another workflow are each noticed."""
    problems = []
    pasted = text.replace("      - name: Record the verdicts\n",
                          "      - name: Pause again\n        shell: bash\n        run: |\n"
                          "          echo \"paused=true\" >> \"$GITHUB_OUTPUT\"\n\n"
                          "      - name: Record the verdicts\n", 1)
    shell_guard = action.replace("bs._switch_on(", "bs.other(", 1)
    other = {".github/workflows/x.yml": "jobs:\n  a:\n    steps:\n      - run: |\n"
             "          value=$(printf '%s' \"$P\" | tr '[:upper:]' '[:lower:]' | xargs)\n"
             "          echo \"paused=true\" >> \"$GITHUB_OUTPUT\"\n"}
    for label, args in (("a re-pasted pause step", (pasted, action, {})),
                        ("a guard that no longer calls _switch_on", (text, shell_guard, {})),
                        ("a shell copy in another workflow", (text, action, other))):
        if args[0] == text and args[1] == action and not args[2]:
            problems.append("self-check: the {0} mutation changed nothing".format(label))
        elif not check_guard_single_home(*args):
            problems.append("self-check: the single-home check did not notice {0}".format(label))
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
        "no refusal first": text.replace("uses: " + GUARD_USES, "uses: ./.github/actions/something-else", 1),
        "no login default": text.replace(" || 'wing-commander-bot[bot]'", "", 1),
        "unpinned checkout": text.replace("          ref: " + CHECKOUT_REF + "\n", "", 1),
    }
    for label, mutated in broken.items():
        if mutated == text or not check_shape(mutated):
            problems.append("self-check: the shape check did not notice: {0}".format(label))
    reader = {r: read(r) for r in NO_READER_FILES}
    reader[NO_READER_FILES[0]] += "\n# reads merge-evidence-ledger\n"
    if not check_no_reader(reader):
        problems.append("self-check: the no-reader check did not notice a reference")
    return problems


SC003_CLASSES = ("pipeline-record", "session-record", "pass-pushed-after", "neither")


def sc003_totals(expected):
    """The expected file's totals agree with its own rows, and each row is
    whole: met exactly when no condition is named as first unmet."""
    rows = expected.get("pulls") or []
    problems = []
    for row in rows:
        pr = row.get("pr")
        if row.get("kind") not in me.KINDS or row.get("class") not in SC003_CLASSES \
                or row.get("result") not in ("met", "unmet"):
            problems.append("SC-003 #{0}: the expected row has an unknown kind, class or result".format(pr))
        met = row.get("result") == "met"
        if met != (row.get("first_unmet") is None) or met != (row.get("first_unmet_state") is None) \
                or row.get("first_unmet_state") not in (None, "unmet", "not-read"):
            problems.append("SC-003 #{0}: the expected row's result, first_unmet and first_unmet_state "
                            "disagree".format(pr))
    totals = expected.get("totals") or {}
    want = {"merges": len(rows),
            "kinds": {k: sum(1 for r in rows if r.get("kind") == k) for k in me.KINDS},
            "met": sum(1 for r in rows if r.get("result") == "met"),
            "classes": {c: sum(1 for r in rows if r.get("class") == c) for c in SC003_CLASSES}}
    for key, value in want.items():
        if totals.get(key) != value:
            problems.append("SC-003: the expected file's totals give {0} {1}, its rows give {2}".format(
                key, totals.get(key), value))
    return problems


def sc003_replay(corpus, expected, window=SC003_WINDOW, merges=SC003_MERGES, evaluate=None):
    """SC-003: every captured merge judged as of its merge -- cut_snapshot(),
    then evaluate() (which assigns the kind itself; the corpus keeps none)
    at the corpus's capture time, never the clock -- against the independent
    hand lookup. Uses no gh and no git. Names every PR that differs."""
    evaluate = evaluate or me.evaluate
    problems = []
    for label, doc in (("corpus", corpus), ("expected file", expected)):
        if doc.get("window") != window:
            problems.append("SC-003: the {0}'s window is {1}, not the replay's {2}".format(label, doc.get("window"), window))
    rows, captured = {}, {}
    for row in expected.get("pulls") or []:
        if row.get("pr") in rows:
            problems.append("SC-003 #{0}: listed twice in the expected file".format(row.get("pr")))
        rows[row.get("pr")] = row
    for item in corpus.get("merges") or []:
        merge = item["merge"]
        if merge["pr"] in captured:
            problems.append("SC-003 #{0}: captured twice".format(merge["pr"]))
        captured[merge["pr"]] = item
        if not window["start"] <= (merge.get("merged_at") or "") < window["end"]:
            problems.append("SC-003 #{0}: merged at {1}, outside the window".format(merge["pr"], merge.get("merged_at")))
    for pr in sorted(set(rows) - set(captured), key=str):
        problems.append("SC-003 #{0}: in the expected file but not in the corpus".format(pr))
    for pr in sorted(set(captured) - set(rows), key=str):
        problems.append("SC-003 #{0}: in the corpus but not in the expected file".format(pr))
    if len(captured) != merges:
        problems.append("SC-003: the corpus holds {0} merges, not {1}".format(len(captured), merges))
    problems += sc003_totals(expected)
    now = corpus.get("captured_at")
    if not now:
        return problems + ["SC-003: the corpus has no captured_at to pin the replay's time to"]
    for pr in sorted(set(rows) & set(captured)):
        merge, row = captured[pr]["merge"], rows[pr]
        snap = copy.deepcopy(captured[pr]["snapshot"])
        if snap.pop("assigned_kind", None) is not None:
            problems.append("SC-003 #{0}: the corpus keeps the captured kind; the replay must assign it".format(pr))
        for field, have in (("head", merge["last_head"]), ("merged_at", merge["merged_at"])):
            if row.get(field) != have:
                problems.append("SC-003 #{0}: the hand lookup's {1} is {2}, the corpus's {3}".format(
                    pr, field, row.get(field), have))
        verdict = evaluate(me.cut_snapshot(snap, merge["merged_at"]), corpus.get("bot_login"), now,
                           base_branch="main")
        first = verdict["first_unmet"]
        state = next((c["result"] for c in verdict["conditions"] if c["name"] == first), None) if first else None
        got = {"kind": verdict["kind"], "result": me.result_of(verdict), "first_unmet": first,
               "first_unmet_state": state}
        for key, value in got.items():
            if row.get(key) != value:
                problems.append("SC-003 #{0}: {1} is {2!r}; the hand lookup says {3!r}".format(pr, key, value, row.get(key)))
        urls = {r["url"] for r in verdict["reported"]}
        for url in row.get("reported") or []:
            if url not in urls:
                problems.append("SC-003 #{0}: the hand lookup's reported record {1} is not among the audit's "
                                "reported records".format(pr, url))
    return problems


# T029: pass-report forms the SC-003 replay found unlisted, each a title, and
# titles that must stay unlisted. (label, body, expected reported kind)
PASS_REPORT_TITLES = (
    ("independent review heading", "<!-- independent-review -->\n## Independent review: PR #7\n\nNo findings.",
     "pass-report"),
    ("confirming pass heading", "<!-- review-until-clean confirming 2 -->\n## review-until-clean confirming pass 2: "
     "PR #7\n\nClean.", "pass-report"),
    ("post-split pass heading", "<!-- review-until-clean post-split pass 5 -->\n## review-until-clean: post-split "
     "pass 5, PR #7\n\nCLEAN.", "pass-report"),
    ("pre-merge run report", "**Pre-merge run of this branch's wrapper:** [run 123](https://github.com/o/r/actions/"
     "runs/123) on `abc`.\n\nThe change does what it says.", "pass-report"),
    ("bold lead naming no review", "**Owner decision (2026-10-21):** post-split pass 2 stands.", None),
    ("prose that mentions a review", "Please finish this PR before review; lint is red.", None),
    ("heading naming no review", "## Local finish: lint made green", None),
)


def check_pass_report_titles(cases=PASS_REPORT_TITLES):
    problems = []
    for label, body, want in cases:
        got = me.reported_kind({"body": body, "user": {"login": "owner", "type": "User"}}, "wc[bot]")
        if got != want:
            problems.append("reported: {0} is listed as {1}, expected {2}".format(label, got, want))
    return problems


def check_pass_report_titles_noticed():
    """The title rule is shown to be needed: without it the forms go unlisted."""
    with _Patched(_titled_pass_report=lambda body: False):
        if not check_pass_report_titles():
            return ["self-check: the pass-report title cases pass without the title rule"]
    return []


def load_sc003(directory=None):
    """-> ({name: document}, problems): both files, or why the replay has nothing to read."""
    directory = directory or SC003_DIR
    docs, problems = {}, []
    for name in ("corpus.json", "expected.json"):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            problems.append("sc003/{0} is missing: the SC-003 replay has nothing to read (T029)".format(name))
            continue
        with open(path, encoding="utf-8") as fh:
            docs[name] = json.load(fh)
    return docs, problems


def check_sc003_noticed(corpus, expected):
    """The replay is shown to fail: each broken subject below must be noticed,
    and the replay must run cut_snapshot() and assign_kind() for every merge."""
    problems = []

    def always_met(snap, bot, now, **kw):
        rec = me.evaluate(snap, bot, now, **kw)
        return dict(rec, first_unmet=None, complete=True,
                    conditions=[dict(c, result="met", reason="") for c in rec["conditions"]])

    def other_kind(snap, bot, now, **kw):
        rec = me.evaluate(snap, bot, now, **kw)
        return dict(rec, kind=me.KINDS[(me.KINDS.index(rec["kind"]) + 1) % len(me.KINDS)])

    def mutated(doc, change):
        doc = copy.deepcopy(doc)
        change(doc)
        return doc

    rows = expected.get("pulls") or []
    first_reported = next((i for i, r in enumerate(rows) if r.get("reported")), None)
    broken = [("an evaluate that always reports met", corpus, expected, always_met),
              ("an evaluate that names another kind", corpus, expected, other_kind),
              ("an expected row's first unmet condition changed", corpus,
               mutated(expected, lambda d: d["pulls"][0].update(first_unmet="no_such_condition")), None),
              ("an expected row dropped", corpus, mutated(expected, lambda d: d["pulls"].pop()), None),
              ("the expected totals changed", corpus,
               mutated(expected, lambda d: d["totals"].update(met=(d["totals"].get("met") or 0) + 1)), None),
              ("a corpus that keeps the captured kind",
               mutated(corpus, lambda d: d["merges"][0]["snapshot"].update(assigned_kind=["maintainer", {}])),
               expected, None),
              ("another window", mutated(corpus, lambda d: d.update(window=dict(d["window"], end="2026-11-16T00:00:00Z"))),
               expected, None)]
    if first_reported is not None:
        broken.append(("a reported URL the audit never lists", corpus, mutated(
            expected, lambda d: d["pulls"][first_reported]["reported"].append("https://example.invalid/x")), None))
    for label, c, e, evaluate in broken:
        if not sc003_replay(c, e, evaluate=evaluate):
            problems.append("self-check: the SC-003 replay did not notice {0}".format(label))
    calls = {"cut_snapshot": 0, "assign_kind": 0}

    def counting(name):
        real = getattr(me, name)

        def wrapper(*a, **k):
            calls[name] += 1
            return real(*a, **k)
        return wrapper
    with _Patched(cut_snapshot=counting("cut_snapshot"), assign_kind=counting("assign_kind")):
        sc003_replay(corpus, expected)
    merges = len(corpus.get("merges") or [])
    if calls["cut_snapshot"] < merges or calls["assign_kind"] < merges:
        problems.append("self-check: the SC-003 replay ran cut_snapshot {0} and assign_kind {1} times for {2} "
                        "merges".format(calls["cut_snapshot"], calls["assign_kind"], merges))
    return problems


def check_sc003(directory=None):
    """SC-003 (T029): the corpus and the expected file exist, the replay
    agrees with the expected file, and the replay is shown to fail."""
    docs, problems = load_sc003(directory)
    if problems:
        return problems
    corpus, expected = docs["corpus.json"], docs["expected.json"]
    return sc003_replay(corpus, expected) + check_sc003_noticed(corpus, expected)


def check_review_round4():
    """Round 4 findings of #1173's review, each shown to fail without its fix."""
    problems = []
    # A failed PR lookup is could-not-be-checked, never a direct push.
    real = me._gh_ok

    def boom(args, *a, **k):
        raise subprocess.CalledProcessError(1, "gh", "", "HTTP 502")
    me._gh_ok = boom
    try:
        if me._belongs_to_merged_pr("o/r", "abc") is not None:
            problems.append("round4: a failed commit-to-PR lookup must read as None, not as a direct push")
    finally:
        me._gh_ok = real
    # The closed-PR read stops at the window start.
    pages = []

    def read(page):
        pages.append(page)
        return [{"updated_at": "2026-01-01T00:00:00Z"} for _ in range(100)]
    me._closed_pulls_since("o/r", "main", "2026-06-01T00:00:00Z", read=read)
    if pages != [1]:
        problems.append("round4: the closed-PR read paged past the window start: {0}".format(pages))
    # A queued check run with no time is kept as not finished.
    cut, left = me.cut_rollup([{"name": "x", "workflowName": "w", "status": "QUEUED", "conclusion": ""}],
                              "2026-11-01T00:00:00Z")
    if left != 0 or len(cut) != 1 or cut[0].get("status") == "COMPLETED":
        problems.append("round4: an unstamped queued check run was dropped by cut_rollup")
    # A read error keeps the kind the PR list shows.
    saved = me.board_merge.fetch_snapshot
    saved_items = me.board_merge.gh_items

    def fail(*a, **k):
        raise subprocess.CalledProcessError(1, "gh", "", "HTTP 502")
    me.board_merge.fetch_snapshot = fail
    me.board_merge.gh_items = lambda path, *a, **k: [{
        "number": 7, "head": {"sha": "a" * 40, "ref": "spec/001-thing", "repo": {"full_name": "o/r"}},
        "user": {"login": "someone", "type": "User"}, "body": ""}]
    try:
        snap = me.collect("o/r", "bot", None, "main")[0]
    finally:
        me.board_merge.fetch_snapshot = saved
        me.board_merge.gh_items = saved_items
    if (snap.get("assigned_kind") or [None])[0] != "final":
        problems.append("round4: a read-error snapshot was not given the kind the PR list shows")
    return problems


def check_round5_base_branch(base_doc):
    """Round 5, finding 1: bump and board-fix PRs are told by the same base
    branch as final and spec PRs, the run's default branch."""
    problems = []
    for base_name in ("board-fix", "bump"):
        snap = copy.deepcopy(base_doc["bases"][base_name])
        want = base_name
        on_trunk = dict(snap, baseRefName="trunk")
        got = me.assign_kind(on_trunk, base_doc["bot_login"], base_branch="trunk")[0]
        if got != want:
            problems.append("kind: a {0} PR into the default branch `trunk` is {1}".format(base_name, got))
        got = me.assign_kind(snap, base_doc["bot_login"], base_branch="trunk")[0]
        if got != "maintainer":
            problems.append("kind: a {0}-shaped PR into `main`, not the default `trunk`, is {1}".format(base_name, got))
    return problems

def check_round5_truncated_comments():
    """Round 5, finding 2: a comment read shorter than its count stays
    incomplete after the as-of-merge cut."""
    head = "abc"
    snap = {"headRefOid": head, "files": [{"path": "a"}], "commits": [{"sha": head}],
            "comments": [{"created_at": "2026-11-01T00:00:00Z"}],
            "counts": {"files": 1, "commits": 1, "comments": 3, "head_sha": head}}
    cut = me.cut_snapshot(snap, "2026-11-02T00:00:00Z")
    if me.board_merge.snapshot_complete(cut):
        return ["cut: a truncated comment read (1 of 3) reads complete after the cut"]
    return []

def check_round5_login_seen(base_doc):
    """Round 5, finding 4: a kind that needs the App's records, with none by
    the configured login, names the login among what was not read."""
    problems = []
    # A wrong login also turns a bump or board-fix PR into a maintainer PR
    # (their kind needs the App as author), so only a final PR, told by its
    # branch, can show it here.
    for name in ("verdict-final-clean",):
        if not os.path.isdir(os.path.join(FIXTURES, name)):
            continue
        snap = build_snapshot(base_doc, load(name, "case.json"))
        rec = me.evaluate(snap, "someone-else[bot]", NOW)
        if rec["complete"] or not any("someone-else[bot]" in n for n in rec["not_read"]):
            problems.append("login: {0} under a wrong App login does not say no record is by it".format(name))
        if any("App login" in n for n in me.evaluate(snap, base_doc["bot_login"], NOW)["not_read"]):
            problems.append("login: {0} under the right App login says no record is by it".format(name))
    maintainer = build_snapshot(base_doc, {"base": "maintainer"})
    if any("App login" in n for n in me.evaluate(maintainer, "someone-else[bot]", NOW)["not_read"]):
        problems.append("login: a maintainer PR, which needs no App record, names the App login")
    return problems

def check_round5_record_time():
    """Round 5, finding 6: each record is stamped when its own snapshot was
    read, after the read, not with the run's start."""
    problems = []
    clock = iter("2026-11-20T05:{0:02d}:00Z".format(m) for m in range(0, 60))
    reads = []

    def fake_fetch(repo, number, bot_login, token):
        reads.append(number)
        return {"number": number, "headRefOid": "h%d" % number, "headRefName": "feature/x", "baseRefName": "main",
                "author": {"login": "owner", "is_bot": False}, "body": "", "statusCheckRollup": []}

    def fake_extend(repo, snap, *args, **kwargs):
        snap["evidence_read_at_clock"] = next(clock)
        return snap

    with _Patched(_now=lambda: next(clock), board_merge__gh_items=lambda url: [{"number": 1}, {"number": 2}],
                  board_merge__fetch_snapshot=fake_fetch, _extend_with_evidence=fake_extend,
                  check_rate_limit=lambda: 5000, download_ledger=lambda *a: None,
                  _pr_state=lambda repo, n: {"state": "open", "at": None}):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                ledger = me.run_verdicts("o/r", "wc[bot]", "main", os.path.join(tmp, "l.json"), "spec/", "spec-draft/")
            except Exception as exc:  # the old code reads the clock once, before every snapshot
                return ["record time: run_verdicts failed under the fake clock: {0!r}".format(exc)]
    times = {r["pr"]: r["computed_at"] for r in ledger["records"].values()}
    if len(set(times.values())) != 2:
        problems.append("record time: both records carry one time ({0}), not their own read times".format(times))
    elif not times[1] < times[2]:
        problems.append("record time: the later read has the earlier time: {0}".format(times))
    first_evidence = "2026-11-20T05:00:00Z"
    if any(t <= first_evidence for t in times.values()):
        problems.append("record time: a record is stamped before its own evidence was read: {0}".format(times))
    return problems

def check_final_review_markers(base_doc):
    """#1173 final review F1: the reviewer's five markers give the same three
    review-gate results through lifecycle_merge_preconditions as before, and
    a re-typed marker comparison in _final_conditions fails the gate."""
    problems = []
    head = base_doc["head"]
    other = "b" * 40
    cases = (({"round": 1, "head_sha": head, "outcome": "clean", "findings_open": 0}, ("met", "met", "met")),
             ({"round": 1, "head_sha": other, "outcome": "clean", "findings_open": 0}, ("unmet", "unmet", "unmet")),
             ({"round": 3, "head_sha": head, "outcome": "budget-exhausted", "findings_open": 3},
              ("met", "unmet", "unmet")),
             ({"round": 2, "head_sha": head, "outcome": "clean", "findings_open": 1}, ("met", "met", "unmet")),
             (None, ("unmet", "unmet", "unmet")))
    for marker, want in cases:
        case = {"base": "final", "patch": {"gate_marker": marker} if marker else {}}
        snap = build_snapshot(base_doc, case)
        conds = {c["name"]: c["result"] for c in me._final_conditions(snap, base_doc["bot_login"])}
        got = tuple(conds[n] for n in ("gate_round_at_head", "round_clean", "zero_open_in_scope"))
        if got != want:
            problems.append("final conditions: marker {0} gives {1}, expected {2}".format(marker, got, want))
    src = read(".github/scripts/wc_merge_evidence.py")
    mutated = src.replace('at_head and pre["round_clean"]', 'at_head and marker.get("outcome") == "clean"', 1)
    if mutated == src or not check_single_home(mutated):
        problems.append("self-check: a re-typed marker comparison in _final_conditions was not noticed")
    return problems

def check_final_review_links():
    """#1173 final review F2: a reported record of an open PR's own comment,
    read as board_merge.fetch_snapshot shapes it (no html_url), links to it."""
    problems = []
    comment = {"id": 77, "created_at": "2026-11-20T01:00:00Z", "body": "Review pass 2: clean.",
               "user": {"login": "owner", "type": "User"}}

    def fake_fetch(repo, number, bot_login, token):
        return {"number": number, "headRefOid": "h" * 40, "headRefName": "feature/x", "baseRefName": "main",
                "author": {"login": "owner", "is_bot": False}, "body": "", "statusCheckRollup": [],
                "comments": [dict(comment)]}

    with _Patched(board_merge__gh_items=lambda url: [{"number": 13}], board_merge__fetch_snapshot=fake_fetch,
                  _extend_with_evidence=lambda repo, snap, *a, **k: snap):
        snaps = me.collect("o/r", "wc[bot]")
    rec = me.evaluate(snaps[0], "wc[bot]", NOW)
    urls = [r["url"] for r in rec["reported"]]
    if urls != ["https://github.com/o/r/pull/13#issuecomment-77"]:
        problems.append("reported: an open PR's own pass report links {0}, not its comment".format(urls))
    if [r.get("id") for r in rec["reported"]] != [77]:
        problems.append("reported: the record does not keep the comment id")
    return problems

def _clean_shared_review_record(base_doc):
    case = load("verdict-maintainer-shared-clean", "case.json")
    return me.evaluate(build_snapshot(base_doc, case), base_doc["bot_login"], NOW)


def _mutate(record, change):
    out = copy.deepcopy(record)
    change(out)
    return out


def _set_cond(record, field, index, **kw):
    record[field][index].update(kw)


RECORD_MUTATIONS = (
    ("a missing conditions list", lambda r: r.pop("conditions")),
    ("a boolean pr", lambda r: r.update(pr=True)),
    ("an empty head", lambda r: r.update(head="")),
    ("an unknown kind", lambda r: r.update(kind="other")),
    ("an unknown rule", lambda r: r.update(rule_applied="some-statuses")),
    ("a computed_at that is no UTC time", lambda r: r.update(computed_at="2026-11-20 05:41")),
    ("conditions that do not open with the checks", lambda r: r["conditions"].reverse()),
    ("an unknown condition result", lambda r: _set_cond(r, "conditions", 0, result="maybe")),
    ("a met condition with a reason", lambda r: _set_cond(r, "conditions", 0, reason="why")),
    ("an unmet condition with no reason", lambda r: _set_cond(r, "conditions", 1, result="unmet", reason="")),
    ("a condition with an extra key", lambda r: _set_cond(r, "conditions", 1, extra=1)),
    ("a first_unmet that is not the first unmet", lambda r: r.update(first_unmet="review_round_record")),
    ("complete with something not read", lambda r: r.update(not_read=["x"])),
    ("incomplete with a condition past the checks met", lambda r: r.update(complete=False, not_read=["x"])),
    ("a reported record of no known kind", lambda r: r["reported"].append({"kind": "note"})),
    ("a repeated reported condition", lambda r: r["reported_conditions"].append(dict(r["reported_conditions"][0]))),
    ("a malformed reported condition", lambda r: _set_cond(r, "reported_conditions", 0, result="unmet", reason="")),
)


def check_record_type(base_doc, validate=None):
    """The gate decision is a type: the clean fixture's record passes, and
    each mutation of it is refused."""
    validate = validate or me.validate_record
    problems = []
    good = _clean_shared_review_record(base_doc)
    try:
        validate(good)
    except me.RecordError as exc:
        return ["record type: a well-formed verdict record is refused: {0}".format(exc)]
    for label, change in RECORD_MUTATIONS:
        try:
            validate(_mutate(good, change))
        except me.RecordError:
            continue
        problems.append("record type: {0} is accepted".format(label))
    return problems


def check_shared_review_noticed(base_doc):
    """The shared-reviewer fixtures are shown to need the code they test."""
    problems = []
    old = lambda snap, bot, base_branch=None: [me._cond("review_round_record", "unmet", me.NO_ROUND_RECORD_REASON)]
    with _Patched(_review_round_conditions=old):
        if not check_verdicts(base_doc):
            problems.append("self-check: a maintainer verdict that never reads the shared reviewer was not noticed")
    saved = wc_shared_review.confirm_record
    wc_shared_review.confirm_record = lambda *a, **k: True
    try:
        if not check_verdicts(base_doc):
            problems.append("self-check: a shared-reviewer record counted without its run's confirmation "
                            "was not noticed")
    finally:
        wc_shared_review.confirm_record = saved
    with _Patched(_ci_definition_condition=lambda snap: me._cond(me.CI_DEFINITION_CONDITION, "met")):
        if not check_verdicts(base_doc):
            problems.append("self-check: a pull request changing .github/ reported as CI from the default "
                            "branch was not noticed")
    if not check_record_type(base_doc, validate=lambda record: record):
        problems.append("self-check: a record type that accepts anything was not noticed")
    return problems


def main():
    base_doc = load("_base.json")
    problems = check_verdicts(base_doc) + check_audits(base_doc) + check_ledger() + check_download_errors() \
        + check_review_round1() + check_review_round2() + check_review_round3_rollup() \
        + check_review_round3_open() + check_review_round3_kind() + check_review_round3_linked_issue()
    problems += check_cancelled_superseded_reason()
    problems += check_single_home(read(".github/scripts/wc_merge_evidence.py"))
    problems += check_review_round4() + check_pass_report_titles() + check_pass_report_titles_noticed() + check_sc003()
    problems += check_final_review_links()
    problems += check_final_review_markers(base_doc)
    problems += check_round5_record_time()
    problems += check_round5_login_seen(base_doc)
    problems += check_round5_truncated_comments()
    problems += check_round5_base_branch(base_doc)
    problems += check_record_type(base_doc) + check_shared_review_noticed(base_doc)
    if not check_sc003(directory=os.path.join(FIXTURES, "_none_")):
        problems.append("self-check: a missing SC-003 corpus and expected file were not noticed")
    wf = os.path.join(REPO, WORKFLOW)
    if os.path.exists(wf):
        text = read(WORKFLOW)
        problems += check_workflow(text) + check_shape(text) + check_no_reader() + check_negatives(text)
        action = read(GUARD_ACTION) if os.path.exists(os.path.join(REPO, GUARD_ACTION)) else ""
        problems += check_guard_single_home(text, action)
        if action:
            problems += check_guard_refusal_modes(action)
        proof_list = read(PROOF_LIST_WORKFLOW)
        problems += check_proof_list_guard(proof_list)
        for label, mutated in (("the dispatch-only input dropped", proof_list.replace("          refuse-on: dispatch\n", "")),
                               ("the guard swapped out", proof_list.replace("uses: " + GUARD_USES, "uses: ./x", 1))):
            if mutated == proof_list or not check_proof_list_guard(mutated):
                problems.append("self-check: the proof-list guard check did not notice {0}".format(label))
        if action:
            problems += check_guard_agreement(action) + check_guard_negatives(text, action)
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
          "SC-003 replay of {2} merges agrees with the hand lookup".format(
              len(case_dirs("verdict-")), len(case_dirs("audit-")), SC003_MERGES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
