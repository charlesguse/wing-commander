#!/usr/bin/env python3
"""Gate — lifecycle_merge_preconditions.py's evaluate_from_snapshot()
resolves every FR-026/FR-027/data-model.md §5 branch correctly
(specs/062-lifecycle-review-gate, contracts/readiness-and-merge.md).

WHY THIS EXISTS
---------------
Auto-merge is the one thing this feature does that a human action has to
undo. Eight conditions stand between a lifecycle PR and a squash merge,
and each one has to fail for its OWN stated reason: a round that was clean
at a DIFFERENT head SHA, a round that came back with findings, and a
maintainer's standing CHANGES_REQUESTED are three different refusals, and
FR-027 requires the gate to say which. This pins all four documented
branches (mirroring verify-lifecycle-readiness.py's own EXPECTED_CASES
shape).

It also pins the job ORDERING that lets production reach those states
(T082): every lifecycle-review-gate.yml job that reads the review_gate
marker (`wc_lifecycle_review_marker.py read`) and is not itself upstream
of the marker's writer (`... write`, `report`) must depend on that writer,
directly or transitively, and require its success in its own `if:`. A
fixture that asserts "clean round at this head merges" means nothing if
`merge` can read the marker before this round's value lands.

And it pins how every marker reader gets its comments (#826). The
reader's author predicate (board_item_marker.is_loop_marker_author())
needs REST's `user: {login, type}`; `gh issue view --json comments`
returns `author: {login}` only, so a reader fed from it sees no marker,
ever, and every round looks like the first -- the round budget and the
unmoved-head skip never engage. Three checks:
  - reader-shape (lifecycle-review-gate.yml): every step that runs
    `wc_lifecycle_review_marker.py read` gets its comments from `gh api
    "repos/$GITHUB_REPOSITORY/issues/$N/comments" --paginate --jq '.[]' |
    jq -s '.'` (the pages merged into one array), as the condition of an
    `if ! var="$(...)"; then` whose branch emits ::error:: and exits 1 --
    a failed read is not "no round yet". select, review, disposition and
    merge must each carry one.
  - json-comments-feeds-author-predicate (every workflow and composite):
    no step both reads `gh issue|pr view ... --json ...comments` and runs
    a reader built on is_loop_marker_author().
  - executed: disposition's and merge's "Read the current review_gate
    marker" steps run against a stub gh that serves REST pages (two, the
    newest marker on the second) and, for `gh issue view --json
    comments`, the GraphQL shape. The step must output the newest bot
    marker, ignore a forged one, and fail with ::error:: and no output
    when the fetch fails.

Fixtures, each a checked-in snapshot under
.github/scripts/tests/lifecycle-merge-preconditions/<case>/case.json.
Fails loudly, not vacuously, if any fixture file is missing.

    python3 .github/scripts/verify-lifecycle-merge-preconditions.py
    python3 .github/scripts/verify-lifecycle-merge-preconditions.py --self-test
"""
import copy
import glob
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lifecycle_merge_preconditions import (  # noqa: E402
    CONDITIONS, evaluate_from_snapshot)
from wc_shell_harness import ensure_jq, resolve_bash, run_step  # noqa: E402

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests",
    "lifecycle-merge-preconditions")

WORKFLOW = os.path.join(".github", "workflows", "lifecycle-review-gate.yml")
MARKER_SCRIPT = "wc_lifecycle_review_marker.py"


def _needs(job):
    needs = (job or {}).get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _ancestors(jobs, job_id):
    seen, stack = set(), list(_needs(jobs.get(job_id)))
    while stack:
        dep = stack.pop()
        if dep not in seen:
            seen.add(dep)
            stack.extend(_needs(jobs.get(dep)))
    return seen


def _marker_jobs(jobs, verb):
    pattern = re.compile(re.escape(MARKER_SCRIPT) + r"\s+" + verb + r"\b")
    return sorted(
        job_id for job_id, job in jobs.items()
        if any(pattern.search(str((step or {}).get("run") or ""))
               for step in (job or {}).get("steps") or []))


def ordering_problems(doc):
    """T082: every marker reader downstream of the writer waits for it."""
    jobs = (doc or {}).get("jobs") or {}
    writers = _marker_jobs(jobs, "write")
    readers = _marker_jobs(jobs, "read")
    problems = []
    if len(writers) != 1:
        return ["expected exactly one review_gate marker writer job, found "
                "{0!r}".format(writers)]
    if "merge" not in readers:
        problems.append("the merge job no longer reads the review_gate "
                        "marker -- this check has lost its subject")
    writer = writers[0]
    upstream_of_writer = _ancestors(jobs, writer)
    for reader in readers:
        if reader == writer or reader in upstream_of_writer:
            continue  # reads the PRIOR round by design (select/review/...)
        if writer not in _ancestors(jobs, reader):
            problems.append("job {0!r} reads the review_gate marker but does "
                            "not depend on its writer {1!r}".format(
                                reader, writer))
            continue
        cond = str(jobs[reader].get("if") or "")
        if not re.search(r"needs\.{0}\.result\s*==\s*'success'".format(
                re.escape(writer)), cond):
            problems.append("job {0!r} reads the review_gate marker but its "
                            "if: does not require needs.{1}.result == "
                            "'success'".format(reader, writer))
    return problems


def run_ordering():
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    problems = ordering_problems(doc)
    for problem in problems:
        print("::error::verify-lifecycle-merge-preconditions: {0}: {1}".format(
            WORKFLOW, problem))
    if not problems:
        print("[ok] marker-ordering: every downstream review_gate reader "
              "waits for its writer")
    return len(problems)


# --- #826: how every review_gate marker reader gets its comments ---------

# `wc_lifecycle_review_marker.py read`, with or without a closing quote
# between (review's snapshot path is quoted).
MARKER_READ_RE = re.compile(re.escape(MARKER_SCRIPT) + r'"?\s+read\b')
REST_READ_RE = re.compile(
    r'if ! [A-Za-z_][A-Za-z0-9_]*="\$\(gh api '
    r'"repos/\$GITHUB_REPOSITORY/issues/\$[A-Za-z_][A-Za-z0-9_]*/comments" '
    r"--paginate --jq '\.\[\]' \\\n\s*\| jq -s '\.' \\\n")
# `gh issue view` / `gh pr view` whose --json field list names comments,
# across `\`-continued lines.
GH_VIEW_COMMENTS_RE = re.compile(
    r"gh (?:issue|pr) view\b(?:[^\n]|\\\n)*?--json[ =]\S*\bcomments\b")
# A reader whose author check is board_item_marker.is_loop_marker_author().
AUTHOR_READER_RE = re.compile(
    MARKER_READ_RE.pattern + r"|\bboard_item_marker\b|\bboard_stop_check\b"
    r"|\bfind_latest_marker\b|\bis_loop_marker_author\b|\bread_marker\b")
READER_JOBS = ("select", "review", "disposition", "merge")
READ_STEP = "Read the current review_gate marker"
READ_STEP_JOBS = ("disposition", "merge")


def _steps(doc):
    for job_id, job in ((doc or {}).get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            if isinstance(step, dict):
                yield job_id, step


def _code(run):
    """`run` with its whole-line shell comments dropped -- a comment that
    names `--json comments` (to say never use it) is not a read."""
    return "\n".join(line for line in str(run or "").split("\n")
                     if not line.lstrip().startswith("#"))


def reader_shape_problems(doc):
    problems, reader_jobs = [], set()
    for job_id, step in _steps(doc):
        run = _code(step.get("run"))
        reads = len(MARKER_READ_RE.findall(run))
        if not reads:
            continue
        reader_jobs.add(job_id)
        where = "{0}/{1!r}".format(job_id, step.get("name") or step.get("id"))
        if GH_VIEW_COMMENTS_RE.search(run):
            problems.append("{0} reads the lifecycle issue's comments with "
                            "`gh ... view --json comments`, which has no "
                            "user.type -- the marker always reads as {{}} "
                            "(#826)".format(where))
        fetches = list(REST_READ_RE.finditer(run))
        if len(fetches) != reads:
            problems.append("{0} runs the marker reader {1} time(s) but has {2} "
                            "`if ! var=\"$(gh api \"repos/$GITHUB_REPOSITORY/"
                            "issues/$N/comments\" --paginate --jq '.[]' | jq -s "
                            "'.' | ...` read(s) (#826)".format(
                                where, reads, len(fetches)))
        for m in fetches:
            line_start = run.rfind("\n", 0, m.start()) + 1
            indent = run[line_start:m.start()]
            then_at = run.find('"; then\n', m.end())
            fi = (re.compile(r"\n" + re.escape(indent) + r"fi\b").search(run, then_at)
                  if then_at >= 0 else None)
            body = run[then_at:fi.start()] if fi else ""
            if "::error::" not in body or "exit 1" not in body:
                problems.append("{0}: a failed comments read must emit "
                                "::error:: and exit 1, never read as no round "
                                "yet (#826)".format(where))
    missing = [j for j in READER_JOBS if j not in reader_jobs]
    if missing:
        problems.append("no marker read found in job(s) {0!r} -- this check "
                        "has lost its subject".format(missing))
    return problems


def _subject_files(root="."):
    files = sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.yml")))
    files += sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.yaml")))
    files += sorted(glob.glob(os.path.join(root, ".github", "actions", "*", "action.yml")))
    return files


def json_comments_reader_problems(docs):
    """docs: {path: parsed yaml}. A step that reads comments through `gh
    ... view --json comments` must not feed an is_loop_marker_author()
    reader (#826)."""
    problems = []
    for path, doc in sorted(docs.items()):
        steps = list(_steps(doc))
        steps += [("(composite)", s) for s in
                  (((doc or {}).get("runs") or {}).get("steps") or [])
                  if isinstance(s, dict)]
        for job_id, step in steps:
            run = _code(step.get("run"))
            if GH_VIEW_COMMENTS_RE.search(run) and AUTHOR_READER_RE.search(run):
                problems.append(
                    "{0}: {1}/{2!r} feeds `gh ... view --json comments` to a "
                    "marker reader built on is_loop_marker_author(), which "
                    "needs REST's user.type -- read through `gh api "
                    "\"repos/$GITHUB_REPOSITORY/issues/$N/comments\" "
                    "--paginate` instead (#826)".format(
                        path, job_id, step.get("name") or step.get("id")))
    return problems


def _load_subject_docs(root="."):
    docs = {}
    for path in _subject_files(root):
        with open(path, encoding="utf-8") as fh:
            docs[os.path.relpath(path, root)] = yaml.safe_load(fh)
    return docs


BOT = "wing-commander-bot[bot]"


def _marker_comment(round_, created, login=BOT, kind="Bot"):
    from wc_lifecycle_review_marker import write_marker
    body = "round {0}\n\n{1}".format(round_, write_marker(
        round_, "sha{0}".format(round_), "findings", 1, [], [], created))
    return {"id": round_, "created_at": created, "body": body,
            "user": {"login": login, "type": kind}}


# Two REST pages: the newest bot marker is on the second, and a forged
# marker from a human sits on the first with a later timestamp than
# anything else.
REST_PAGES = [
    [_marker_comment(1, "2026-01-01T00:00:00Z"),
     _marker_comment(99, "2026-01-09T00:00:00Z", login="an-outsider", kind="User")],
    [_marker_comment(2, "2026-01-02T00:00:00Z")],
]
EXPECTED_ROUND = 2

STUB_GH = r"""#!/usr/bin/env bash
# REST: `gh api <path> [--paginate] [--jq <expr>]` -- one JSON document per
# page, --jq applied per page, the way gh itself does.
if [ "$1" = "api" ]; then
  if [ -n "${STUB_FAIL:-}" ]; then
    echo '{"message":"Server Error","status":"500"}'
    exit 1
  fi
  path="$2"; shift 2; jqexpr=""; paginate=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --jq) jqexpr="$2"; shift 2 ;;
      --paginate) paginate=1; shift ;;
      *) shift ;;
    esac
  done
  [ "$path" = "repos/example/example/issues/77/comments" ] || exit 1
  for page in "$STUB_DIR"/rest-page-*.json; do
    if [ -n "$jqexpr" ]; then jq -c "$jqexpr" "$page"; else cat "$page"; fi
    [ "$paginate" = 1 ] || break
  done
  exit 0
fi
# GraphQL-backed `gh issue view --json comments`: author{login}, no user.
if [ "$1 $2" = "issue view" ]; then
  jqexpr="."
  while [ $# -gt 0 ]; do
    case "$1" in --jq) jqexpr="$2"; shift 2 ;; *) shift ;; esac
  done
  jq -c "$jqexpr" "$STUB_DIR/graphql.json"
  exit 0
fi
exit 1
"""


def _graphql_view():
    comments = []
    for page in REST_PAGES:
        for c in page:
            comments.append({"body": c["body"], "createdAt": c["created_at"],
                             "author": {"login": c["user"]["login"].replace("[bot]", "")}})
    return {"comments": comments}


def run_read_step(script, fail=False):
    """Runs one "Read the current review_gate marker" `run:` against
    STUB_GH; returns (rc, output, outputs)."""
    ensure_jq()
    here = os.path.dirname(os.path.abspath(__file__))
    tmp = tempfile.mkdtemp(prefix="wc-826-")
    try:
        stub_dir = os.path.join(tmp, "stub")
        bindir = os.path.join(tmp, "bin")
        scripts = os.path.join(tmp, "work", ".wc-pristine-repo", ".github", "scripts")
        runner_temp = os.path.join(tmp, "runner-temp")
        for d in (stub_dir, bindir, scripts, runner_temp):
            os.makedirs(d)
        for name in (MARKER_SCRIPT, "board_item_marker.py"):
            shutil.copyfile(os.path.join(here, name), os.path.join(scripts, name))
        for i, page in enumerate(REST_PAGES, 1):
            with open(os.path.join(stub_dir, "rest-page-{0}.json".format(i)), "w",
                      encoding="utf-8") as fh:
                json.dump(page, fh)
        with open(os.path.join(stub_dir, "graphql.json"), "w", encoding="utf-8") as fh:
            json.dump(_graphql_view(), fh)
        gh = os.path.join(bindir, "gh")
        with open(gh, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(STUB_GH)
        os.chmod(gh, 0o755)
        env = {"GH_TOKEN": "x", "ISSUE": "77", "BOT_LOGIN": BOT,
               "GITHUB_REPOSITORY": "example/example", "STUB_DIR": stub_dir,
               "PATH": bindir + os.pathsep + os.environ["PATH"]}
        if fail:
            env["STUB_FAIL"] = "1"
        rc, out, outputs, _ = run_step(resolve_bash(), script,
                                       os.path.join(tmp, "work"), env, runner_temp)
        return rc, out, outputs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read_step_script(doc, job_id):
    for step in ((doc.get("jobs") or {}).get(job_id) or {}).get("steps") or []:
        if isinstance(step, dict) and step.get("name") == READ_STEP:
            return str(step.get("run") or "")
    return None


def executed_read_problems(doc):
    problems = []
    for job_id in READ_STEP_JOBS:
        script = _read_step_script(doc, job_id)
        if script is None:
            problems.append("{0}: step {1!r} not found".format(job_id, READ_STEP))
            continue
        rc, out, outputs = run_read_step(script)
        try:
            got = json.loads(outputs.get("json") or "null")
        except ValueError:
            got = outputs.get("json")
        if rc != 0 or not isinstance(got, dict) or got.get("round") != EXPECTED_ROUND:
            problems.append("{0}/{1!r}: expected the newest bot marker (round "
                            "{2}) across both REST pages, got rc={3} json={4!r} "
                            "{5}".format(job_id, READ_STEP, EXPECTED_ROUND, rc,
                                         got, out.strip()[-400:]))
        rc, out, outputs = run_read_step(script, fail=True)
        if rc == 0 or "json" in outputs or "::error::" not in out:
            problems.append("{0}/{1!r}: a failed comments fetch must fail the "
                            "step with ::error:: and no json output, got rc={2} "
                            "outputs={3!r}".format(job_id, READ_STEP, rc, outputs))
    return problems


def run_marker_reads():
    with open(WORKFLOW, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    problems = (reader_shape_problems(doc)
                + json_comments_reader_problems(_load_subject_docs())
                + executed_read_problems(doc))
    for problem in problems:
        print("::error::verify-lifecycle-merge-preconditions: {0}".format(problem))
    if not problems:
        print("[ok] marker-reads: every review_gate marker reader reads REST "
              "comments, all pages, and fails loudly on a failed read (#826)")
    return len(problems)


EXPECTED_CASES = {
    "round-not-clean", "unresolved-human-review",
    "head-sha-moved-since-round", "all-clear",
    "clean-round-head-matches-reviewed-sha",
}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run():
    failures = run_ordering() + run_marker_reads()

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-lifecycle-merge-preconditions: fixtures "
              "directory {0} does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(EXPECTED_CASES - cases_found)
    if missing_cases:
        print("::error::verify-lifecycle-merge-preconditions: missing "
              "fixture case(s): {0}".format(", ".join(missing_cases)))
        return 1

    for case in sorted(EXPECTED_CASES):
        case_path = os.path.join(FIXTURES_DIR, case, "case.json")
        if not os.path.isfile(case_path):
            failures += 1
            print("::error::verify-lifecycle-merge-preconditions: {0} is "
                  "missing case.json.".format(case_path))
            continue
        spec = _load(case_path)
        got = evaluate_from_snapshot(
            spec["snapshot"], spec.get("review_gate"),
            spec["kill_switch_paused"], spec.get("reviews") or [],
            spec.get("bot_login") or "")
        expected = spec["expected"]

        ok = (got["may_merge"] == expected["may_merge"]
              and got.get("unmet_reason") == expected.get("unmet_reason"))
        if not ok:
            failures += 1
            print("::error::verify-lifecycle-merge-preconditions: {0}: "
                  "expected {1!r}, got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: may_merge={1!r} unmet_reason={2!r}".format(
                case, got["may_merge"], got.get("unmet_reason")))

    print("verify-lifecycle-merge-preconditions: {0} failure(s).".format(
        failures))
    return 1 if failures else 0


def _clear_snapshot():
    return {"headRefOid": "aaaa111",
            "statusCheckRollup": [
                {"name": "lint", "workflowName": "lint · workflows",
                 "conclusion": "SUCCESS"}],
            "mergeable": "MERGEABLE"}


def _clear_gate():
    return {"round": 1, "head_sha": "aaaa111", "outcome": "clean",
            "findings_open": 0, "folded_fingerprints": [],
            "filed_fingerprints": [], "updated_at": None}


def self_test():
    """The eight conditions are evaluated in order, unmet_reason names only
    the first one that fails (constitution IX's plain lookup, never
    narrated prose), and the merge-only conditions each refuse for their
    own reason."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} {1}".format(name, detail))

    check("eight-conditions", len(CONDITIONS) == 8,
          "got {0!r}".format(CONDITIONS))

    # Every condition fails at once: unmet_reason names only the first.
    got = evaluate_from_snapshot(
        {"headRefOid": "x", "statusCheckRollup": [],
         "mergeable": "CONFLICTING"},
        {"round": 1, "head_sha": "other", "outcome": "findings",
         "findings_open": 3, "folded_fingerprints": [],
         "filed_fingerprints": [], "updated_at": None},
        True,
        [{"author": {"login": "a-maintainer"}, "state": "CHANGES_REQUESTED"}],
        "wing-commander-bot")
    check("first-failing-condition-only", got["unmet_reason"] == "checks_green",
          "got {0!r}".format(got))
    check("not-merging-when-any-condition-fails", got["may_merge"] is False)

    # A review_gate that has never run is not a clean round at this head --
    # never a crash, and never a merge.
    got = evaluate_from_snapshot(_clear_snapshot(), None, False, [], "bot")
    check("null-review-gate-never-merges", got["may_merge"] is False
          and got["unmet_reason"] == "reviewed_at_this_head",
          "got {0!r}".format(got))

    # The bot's own COMMENT review (the one this gate itself posts every
    # round) must never block its own merge -- including when the caller
    # threads the `<slug>[bot]` spelling rather than the bare slug the
    # reviews API reports.
    for caller_spelling in ("wing-commander-bot", "wing-commander-bot[bot]"):
        got = evaluate_from_snapshot(
            _clear_snapshot(), _clear_gate(), False,
            [{"author": {"login": "wing-commander-bot"},
              "state": "CHANGES_REQUESTED"}],
            caller_spelling)
        check("own-bot-review-never-blocks[{0}]".format(caller_spelling),
              got["may_merge"] is True, "got {0!r}".format(got))

    # A human's CHANGES_REQUESTED stands until that same human approves or
    # dismisses it -- a later plain COMMENT from anyone does not clear it.
    got = evaluate_from_snapshot(
        _clear_snapshot(), _clear_gate(), False,
        [{"author": {"login": "a-maintainer"}, "state": "CHANGES_REQUESTED"},
         {"author": {"login": "a-maintainer"}, "state": "COMMENTED"}],
        "wing-commander-bot")
    check("comment-does-not-clear-changes-requested",
          got["unmet_reason"] == "no_unresolved_human_review",
          "got {0!r}".format(got))

    got = evaluate_from_snapshot(
        _clear_snapshot(), _clear_gate(), False,
        [{"author": {"login": "a-maintainer"}, "state": "CHANGES_REQUESTED"},
         {"author": {"login": "a-maintainer"}, "state": "APPROVED"}],
        "wing-commander-bot")
    check("approval-clears-changes-requested", got["may_merge"] is True,
          "got {0!r}".format(got))

    # findings_open is checked independently of outcome (contract condition
    # 7: a finding could be reopened without outcome changing).
    got = evaluate_from_snapshot(
        _clear_snapshot(), dict(_clear_gate(), findings_open=1), False, [],
        "bot")
    check("open-findings-refuse-independently",
          got["unmet_reason"] == "no_open_findings", "got {0!r}".format(got))

    # The kill switch stops a merge mid-round (FR-006/T059's edge case).
    got = evaluate_from_snapshot(
        _clear_snapshot(), _clear_gate(), True, [], "bot")
    check("kill-switch-stops-the-merge",
          got["unmet_reason"] == "kill_switch_clear", "got {0!r}".format(got))

    # T074: review_gate now lives on the lifecycle issue's own marker, never
    # a commit to the reviewed branch -- so `head_sha` is compared directly,
    # with no peel. A head that genuinely moved past the reviewed SHA (a new
    # commit landed, not this gate's own bookkeeping, which no longer
    # exists) must still refuse by name.
    got = evaluate_from_snapshot(
        dict(_clear_snapshot(), headRefOid="a-later-real-commit-sha"),
        _clear_gate(), False, [], "bot")
    check("moved-head-refuses-directly-with-no-peel",
          got["unmet_reason"] == "reviewed_at_this_head", "got {0!r}".format(got))

    # T082: the shipped workflow orders merge after report, and dropping
    # either half of that ordering (the needs: edge, or the success check
    # in the if:) is caught.
    with open(WORKFLOW, encoding="utf-8") as fh:
        shipped = yaml.safe_load(fh)
    check("marker-ordering-shipped-clean", ordering_problems(shipped) == [],
          "got {0!r}".format(ordering_problems(shipped)))

    dropped_edge = copy.deepcopy(shipped)
    dropped_edge["jobs"]["merge"]["needs"] = [
        n for n in _needs(dropped_edge["jobs"]["merge"]) if n != "report"]
    got = ordering_problems(dropped_edge)
    check("marker-ordering-dropped-needs-edge-caught",
          any("does not depend on its writer" in p for p in got),
          "got {0!r}".format(got))

    dropped_if = copy.deepcopy(shipped)
    dropped_if["jobs"]["merge"]["if"] = re.sub(
        r"\s*&&\s*needs\.report\.result\s*==\s*'success'", "",
        str(dropped_if["jobs"]["merge"]["if"]))
    got = ordering_problems(dropped_if)
    check("marker-ordering-dropped-success-check-caught",
          any("does not require needs.report.result" in p for p in got),
          "got {0!r}".format(got))

    # #826: the shipped marker reads are clean, and each way of breaking
    # them is caught.
    check("marker-reads-shipped-clean", reader_shape_problems(shipped) == [],
          "got {0!r}".format(reader_shape_problems(shipped)))
    docs = _load_subject_docs()
    check("json-comments-reader-shipped-clean",
          json_comments_reader_problems(docs) == [],
          "got {0!r}".format(json_comments_reader_problems(docs)))
    check("executed-read-shipped-clean", executed_read_problems(shipped) == [],
          "got {0!r}".format(executed_read_problems(shipped)))

    rest_read = ("gh api \"repos/$GITHUB_REPOSITORY/issues/$ISSUE/comments\" "
                 "--paginate --jq '.[]' \\\n  | jq -s '.' \\\n")
    merge_script = _read_step_script(shipped, "merge")
    check("mutation-harness-finds-merge-read", merge_script is not None
          and merge_script.count(rest_read) == 1,
          "update the #826 mutations to the shipped text")

    def mutate_merge(old, new):
        doc = copy.deepcopy(shipped)
        for step in doc["jobs"]["merge"]["steps"]:
            if isinstance(step, dict) and step.get("name") == READ_STEP:
                step["run"] = str(step["run"]).replace(old, new, 1)
        return doc

    # The pre-#826 read, restored.
    reverted = mutate_merge(
        rest_read,
        "gh issue view \"$ISSUE\" -R \"$GITHUB_REPOSITORY\" --json comments "
        "--jq '.comments' \\\n")
    got = reader_shape_problems(reverted)
    check("mutation-json-comments-read-caught-static",
          any("--json comments" in p for p in got), "got {0!r}".format(got))
    got = executed_read_problems(reverted)
    check("mutation-json-comments-read-caught-executed",
          any("expected the newest bot marker" in p for p in got),
          "got {0!r}".format(got))

    # Only the first page read, or the pages not merged into one array.
    no_paginate = mutate_merge("--paginate ", "")
    got = reader_shape_problems(no_paginate) + executed_read_problems(no_paginate)
    check("mutation-first-page-only-caught",
          any("expected the newest bot marker" in p for p in got)
          and any("time(s) but has 0" in p for p in got), "got {0!r}".format(got))
    unmerged = mutate_merge(" --jq '.[]' \\\n  | jq -s '.' \\\n", " \\\n")
    got = executed_read_problems(unmerged)
    check("mutation-pages-not-merged-caught",
          any("expected the newest bot marker" in p for p in got),
          "got {0!r}".format(got))

    # A bare capture: no `if !`, no ::error::.
    bare = copy.deepcopy(shipped)
    for step in bare["jobs"]["merge"]["steps"]:
        if isinstance(step, dict) and step.get("name") == READ_STEP:
            run = str(step["run"])
            run = run.replace("if ! review_gate_json=", "review_gate_json=", 1)
            run = re.sub(r'"; then\n.*?\nfi\n', '"\n', run, count=1,
                         flags=re.S)
            step["run"] = run
    got = reader_shape_problems(bare)
    check("mutation-bare-capture-caught", any("time(s) but has 0" in p for p in got),
          "got {0!r}".format(got))

    # Anywhere in the repository: a --json comments read feeding a reader.
    synthetic = {".github/workflows/synthetic.yml": {"jobs": {"j": {"steps": [
        {"name": "board", "run": "gh issue view \"$N\" \\\n  --json comments,labels "
         "--jq '.comments' > c.json\npython3 -c 'from board_item_marker import "
         "read_marker'\n"}]}}},
        ".github/actions/synthetic/action.yml": {"runs": {"steps": [
            {"name": "stop", "run": "gh pr view 1 --json comments | python3 "
             "board_stop_check.py\n"}]}},
        ".github/workflows/unrelated.yml": {"jobs": {"j": {"steps": [
            {"name": "body-only", "run": "gh issue view 1 --json comments "
             "--jq '.comments[].body'\n"}]}}}}
    got = json_comments_reader_problems(synthetic)
    check("mutation-json-comments-anywhere-caught",
          len(got) == 2 and not any("unrelated" in p for p in got),
          "got {0!r}".format(got))

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
