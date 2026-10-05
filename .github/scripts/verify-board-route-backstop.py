#!/usr/bin/env python3
"""Gate — board_route_backstop.py's route()/route_final_diff() and
contract_widened() resolve every FR-064 bullet-3 branch correctly
(specs/057-autonomous-board-loop, contracts/route-backstop.md).

WHY THIS EXISTS
---------------
FR-017 is a one-directional promise: the backstop can only narrow the
route-propose agent's proposal, never widen it. A regression that let a
`spec` proposal get pulled back to `fix`, or that missed a contract-
widening diff because it was small otherwise, is exactly the failure mode
FR-019/FR-021 name explicitly -- this gate pins the four documented
branches, including the one where a diff earns "fix" before the push and
only breaches after (post_push_final_diff_breach).

#534: a `spec` the agent proposed itself, with no backstop condition
firing, records reason `agent_proposed_spec` -- never `under_threshold`,
which board-loop.yml once rendered as "re-routed ... under_threshold,
measured={files:0,lines:0}". When a backstop condition also fired on a
`spec` proposal, that condition's own reason is kept; a default `spec`
standing in for a missing proposal records `no_usable_proposal`, and so
does a category outside fix/spec once normalize_category() has stripped
and lowercased it (#548: "SPEC" once took the fix path). The agent's
rationale reaches issue text only through one_line_rationale(), which
this gate also pins (one line, bounded, no code-span or marker breakout).

Fixtures (FR-064 bullet 3), each a checked-in case.json under
.github/scripts/tests/board-route-backstop/<case>/. Fails loudly, not
vacuously, if any fixture file is missing.
"""
import glob
import json
import os
import re
import subprocess
import sys
import unicodedata

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_route_backstop import (  # noqa: E402
    RATIONALE_MAX_CHARS, contract_widened, diff_name_list, drafted_contract_widened,
    normalize_category, normalize_repo_path, one_line_rationale, read_base_contents,
    read_worktree_contents, route, route_final_diff, workflow_push_blocked_paths)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "board-route-backstop")

EXPECTED_CASES = {
    "under-threshold",
    "over-threshold-files",
    "contract-widening",
    "contract-widening-trailing-comment",
    "post-push-final-diff-breach",
    "agent-proposed-spec",
    "agent-proposed-spec-over-threshold",
    "no-usable-proposal",
    "no-usable-proposal-rate-limited",
    "agent-proposed-spec-rate-limited",
    "fix-rate-limited-stays-fix",
    # #548: the category is normalised in one place (normalize_category())
    # and anything outside fix/spec is no usable proposal -> spec.
    "category-upper-spec",
    "category-padded-spec",
    "category-mixed-case-fix",
    "category-unknown",
    "category-null",
    # Board reset of 2026-10-01: a fix the loop cannot push (a workflow
    # file, the App holding no Workflows permission) is held, never sent
    # to a spec -- unless a spec condition fired on its own.
    "workflow-scope-hold",
    "workflow-scope-agent-spec",
    "workflow-scope-over-threshold",
    "workflow-scope-not-blocked",
}

# (proposal, expected one_line_rationale()) -- #534.
RATIONALE_CASES = [
    ({"category": "spec"}, ""),
    ({"reasoning": None, "rationale": 7}, ""),
    ({"reasoning": "  needs an owner\n trade-off  "}, "needs an owner trade-off"),
    ({"reasoning": "", "rationale": "fallback key"}, "fallback key"),
    ({"reasoning": "use `x` here"}, "use 'x' here"),
    ({"reasoning": "a <!-- wing-commander-board-item: {} --> b"},
     "a  wing-commander-board-item: {}  b"),
    ({"reasoning": "<!<!----- x"}, "- x"),
    ("not a dict", ""),
    ({"reasoning": "ok **Run:** https://github.com/o/r/actions/runs/123456"},
     "ok \u2217\u2217Run:\u2217\u2217 https://github.com/o/r/actions/runs/123456"),
    ({"reasoning": "a\u202eb\u200bc\u2066d"}, "abcd"),
]


BOARD_LOOP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "workflows",
    "board-loop.yml")
EXTRACTED_ASSIGN_RE = re.compile(r"^\s*extracted = (?!False\s*$)(.*)$",
                                 re.MULTILINE)
NORMALIZE_IMPORT = "from board_route_backstop import normalize_category"


def extract_step_problems(workflow_text):
    """#548 review: the route job's extract step must decide `extracted`
    through normalize_category(), the one home route() also reads the
    category through, and import it in that same step. Fails closed when
    the step or its assignment cannot be found."""
    try:
        doc = yaml.safe_load(workflow_text)
        steps = doc["jobs"]["route"]["steps"]
    except (yaml.YAMLError, KeyError, TypeError) as exc:
        return ["board-loop.yml: cannot read jobs.route.steps ({0})".format(exc)]
    runs = [st.get("run", "") for st in steps
            if isinstance(st, dict) and st.get("id") == "extract"]
    if len(runs) != 1:
        return ["board-loop.yml: expected one route step with id extract, "
                "found {0}".format(len(runs))]
    run = runs[0]
    problems = []
    assigns = EXTRACTED_ASSIGN_RE.findall(run)
    if not assigns:
        problems.append("board-loop.yml route extract step: no `extracted = "
                        "...` assignment found")
    for rhs in assigns:
        if "normalize_category(" not in rhs:
            problems.append("board-loop.yml route extract step: `extracted "
                            "= {0}` does not call normalize_category(), so "
                            "it can disagree with route() (#548)".format(rhs))
    if NORMALIZE_IMPORT not in run:
        problems.append("board-loop.yml route extract step does not import "
                        "normalize_category itself")
    return problems


def hold_wiring_problems(workflow_text):
    """Board reset of 2026-10-01: route's decide step passes
    workflow_push_blocked_paths()'s result into route() and the drafted
    diff's own contract check (drafted_contract_widened()) as its
    widened paths, and a `hold` verdict is acted on by a step that stalls
    the issue -- otherwise a hold verdict would fall through every step
    and leave the item silently unrouted. Fails closed when either step
    cannot be found."""
    try:
        doc = yaml.safe_load(workflow_text)
        steps = doc["jobs"]["route"]["steps"]
    except (yaml.YAMLError, KeyError, TypeError) as exc:
        return ["board-loop.yml: cannot read jobs.route.steps ({0})".format(exc)]
    problems = []
    decide = [st for st in steps if isinstance(st, dict) and st.get("id") == "decide"]
    if len(decide) != 1:
        return ["board-loop.yml: expected one route step with id decide, "
                "found {0}".format(len(decide))]
    run = str(decide[0].get("run", ""))
    for needle, why in (
            ("workflow_push_blocked_paths(", "computes the paths this loop cannot push"),
            ("workflow_push_blocked=blocked", "passes them into route()"),
            ("drafted_contract_widened(file_changes, read_text, unknown=contract_unknown)",
             "checks the drafted diff for a contract change"),
            ("contract_unknown_paths=contract_unknown",
             "tells a hold which paths' contract effect went unchecked"),
            ("widened_paths_override=widened", "passes that check into route()"),
            ('agent_rate_limited=os.environ.get("ROUTE_AGENT_VERDICT") == "rate-limited"',
             "defers a rate-limited agent's missing proposal instead of filing a spec")):
        if needle not in run:
            problems.append("board-loop.yml route decide step: `{0}` not found -- it no "
                            "longer {1}".format(needle, why))
    env = decide[0].get("env") or {}
    if str(env.get("ROUTE_AGENT_VERDICT", "")).replace(" ", "") != "${{steps.route-verdict.outputs.verdict}}":
        problems.append("board-loop.yml route decide step: ROUTE_AGENT_VERDICT is not "
                        "the route agent's own verdict (steps.route-verdict.outputs.verdict) "
                        "-- a rate-limited route would default to spec again")
    holds = [st for st in steps if isinstance(st, dict)
             and "steps.decide.outputs.verdict == 'hold'" in str(st.get("if", ""))]
    if len(holds) != 1:
        problems.append("board-loop.yml route job: expected exactly one step gated on "
                        "`steps.decide.outputs.verdict == 'hold'`, found {0}".format(len(holds)))
    return problems + workflow_scope_single_home_problems(doc, workflow_text)


# The three workflow-scope hold sites (found by the code review of #921):
# (job, --site value, step name). board_workflow_scope_hold.py is the one
# home of the path check and the hold sequence; each site calls it.
HOLD_SITES = (
    ("route", "route", "Hold a workflow-file fix for a maintainer"),
    ("fix", "fix", "Push and open the PR"),
    ("review", "review-fixup", "Push the follow-up commit and advance the round"),
)
HOLD_HELPER = "board_workflow_scope_hold.py"
CAN_PUSH_EXPR = "${{ vars.WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS == 'true' }}"
# An inline copy of the check: a shell test of a path against
# .github/workflows/ (grep, case or [[ ]]), anywhere in board-loop.yml.
INLINE_CHECK_RE = re.compile(
    r"^[^#\n]*(?:\bgrep\b|\bcase\b|\[\[)[^#\n]*\.github/workflows/", re.MULTILINE)
# An inline copy of the hold comment's prose.
INLINE_HOLD_PROSE = "which this loop cannot push"


def workflow_scope_single_home_problems(doc, workflow_text):
    """Each hold site calls board_workflow_scope_hold.py with its own
    --site, the board:stalled label named at the call site, and the
    maintainer's CAN_PUSH_WORKFLOWS switch; and board-loop.yml carries no
    second copy of the check or of the hold comment."""
    problems = []
    jobs = (doc or {}).get("jobs") or {}
    for job, site, name in HOLD_SITES:
        steps = [st for st in (jobs.get(job) or {}).get("steps") or []
                 if isinstance(st, dict) and st.get("name") == name]
        if len(steps) != 1:
            problems.append("board-loop.yml {0} job: expected one step named {1!r}, found "
                            "{2}".format(job, name, len(steps)))
            continue
        run = str(steps[0].get("run", ""))
        if not re.search(re.escape(HOLD_HELPER) + r'"? --site ' + re.escape(site) + " ", run):
            problems.append("board-loop.yml {0} job, {1!r}: no `{2} --site {3}` call -- the "
                            "workflow-scope check and hold must go through it".format(
                                job, name, HOLD_HELPER, site))
        for needle in ('--add-label "board:stalled"',
                       '--can-push-workflows "$CAN_PUSH_WORKFLOWS"'):
            if needle not in run:
                problems.append("board-loop.yml {0} job, {1!r}: `{2}` not found -- the "
                                "workflow-scope check and hold must go through {3}".format(
                                    job, name, needle, HOLD_HELPER))
        if site == "route" and "--route-decision " not in run:
            problems.append("board-loop.yml route job, {0!r}: the helper is not given "
                            "--route-decision, so contract-unchecked paths go unnamed".format(name))
        if site != "route" and not re.search(r'--diff-base "\$[A-Z_]+"', run):
            problems.append("board-loop.yml {0} job, {1!r}: the helper is not given "
                            "--diff-base, so it never lists the real diff itself (#889: "
                            "quotePath, renames) nor checks its contract".format(job, name))
        if '[ "$held"' not in run:
            problems.append("board-loop.yml {0} job, {1!r}: the helper's held/clear answer "
                            "is never read".format(job, name))
        env = steps[0].get("env") or {}
        if str(env.get("CAN_PUSH_WORKFLOWS", "")).replace(" ", "") != CAN_PUSH_EXPR.replace(" ", ""):
            problems.append("board-loop.yml {0} job, {1!r}: CAN_PUSH_WORKFLOWS is not "
                            "`{2}`".format(job, name, CAN_PUSH_EXPR))
    for m in INLINE_CHECK_RE.finditer(workflow_text):
        problems.append("board-loop.yml:{0}: an inline `.github/workflows/` path check -- "
                        "use {1}, the check's one home".format(
                            workflow_text.count("\n", 0, m.start()) + 1, HOLD_HELPER))
    if INLINE_HOLD_PROSE in workflow_text:
        problems.append("board-loop.yml: an inline copy of the workflow-scope hold comment "
                        "(`{0}`) -- {1} is its one home".format(INLINE_HOLD_PROSE, HOLD_HELPER))
    return problems + diff_listing_problems(doc, workflow_text)


# A changed-path listing spelled in board-loop.yml (#889): `git diff
# --name-only` C-quotes a non-ASCII path under core.quotePath and detects
# renames, so a `.github/workflows/é.yml` edit, or a workflow_call workflow
# moved out of .github/workflows/, read as no workflow file / no contract
# removed. board_route_backstop.diff_name_list() is the listing's one home.
NAME_LISTING_RE = re.compile(r"^[^#\n]*\bgit\b[^#\n]*\bdiff\b[^#\n]*--name-(?:only|status)",
                             re.MULTILINE)
# (job, step id) of the final-diff checks that read a patch and its paths.
FINAL_DIFF_STEPS = (("fix", "final-diff-backstop"), ("readiness", "final-diff-backstop"))


def diff_listing_problems(doc, workflow_text):
    problems = []
    for m in NAME_LISTING_RE.finditer(workflow_text):
        problems.append("board-loop.yml:{0}: a `git diff --name-only` listing -- use "
                        "board_route_backstop.diff_name_list() (-z, --no-renames), the "
                        "listing's one home (#889)".format(
                            workflow_text.count("\n", 0, m.start()) + 1))
    jobs = (doc or {}).get("jobs") or {}
    for job, step_id in FINAL_DIFF_STEPS:
        steps = [st for st in (jobs.get(job) or {}).get("steps") or []
                 if isinstance(st, dict) and st.get("id") == step_id]
        if len(steps) != 1:
            problems.append("board-loop.yml {0} job: expected one step with id {1}, found "
                            "{2}".format(job, step_id, len(steps)))
            continue
        run = str(steps[0].get("run", ""))
        if "diff_name_list(" not in run:
            problems.append("board-loop.yml {0} job, {1}: its paths are not listed by "
                            "diff_name_list()".format(job, step_id))
        diffs = [line for line in run.splitlines()
                 if re.search(r"\bgit\b.*\bdiff\b", line) and not line.lstrip().startswith("#")]
        if not diffs:
            problems.append("board-loop.yml {0} job, {1}: no `git diff` patch found".format(
                job, step_id))
        for line in diffs:
            if "--no-renames" not in line or "core.quotePath=false" not in line:
                problems.append("board-loop.yml {0} job, {1}: `{2}` lacks --no-renames or "
                                "core.quotePath=false, so its patch disagrees with its "
                                "paths (#889)".format(job, step_id, line.strip()))
    return problems


LABELS_CONTRACT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "specs",
    "057-autonomous-board-loop", "contracts", "labels-and-cross-links.md")
# What the board:stalled row must say of each HOLD_SITES site, in order.
STALLED_ROW_SOURCES = ("route's `hold` verdict", "the fix job's pre-push check",
                       "review-fixup's pre-push check")


def stalled_sources_problems(text=None):
    """Spec 057's labels contract lists every source of board:stalled; each
    workflow-scope hold site is one (review-fixup's, added by #901, was
    missing -- found by the code review of #953)."""
    if text is None:
        try:
            with open(LABELS_CONTRACT, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return ["cannot read {0}: {1}".format(LABELS_CONTRACT, exc)]
    rows = [line for line in text.splitlines() if line.startswith("| `board:stalled` |")]
    if len(rows) != 1:
        return ["labels-and-cross-links.md: expected one `board:stalled` row, found "
                "{0}".format(len(rows))]
    return ["labels-and-cross-links.md: the `board:stalled` row does not name {0!r} as a "
            "source, though board-loop.yml's {1} site holds with it".format(phrase, site[1])
            for phrase, site in zip(STALLED_ROW_SOURCES, HOLD_SITES) if phrase not in rows[0]]


class _Proc:
    def __init__(self, returncode):
        self.returncode = returncode


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t"]
                          + list(args), check=True, capture_output=True).stdout


def _make_repo(tmp, base_files, head_files, renames=()):
    """A git repository at tmp/repo: `base_files` ({path: text}) committed,
    then `renames` ((old, new) `git mv`s) and `head_files` ({path: text, or
    None to delete}) committed on top. Returns (repo, base sha)."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    _git(repo, "init", "-q")

    def write(files):
        for path, text in files.items():
            full = os.path.join(repo, path)
            if text is None:
                _git(repo, "rm", "-q", "--", path)
                continue
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(text)
            _git(repo, "add", "--", path)

    write(dict(base_files or {}, **{"README": "r\n"}))
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").decode().strip()
    for old, new in renames:
        os.makedirs(os.path.dirname(os.path.join(repo, new)), exist_ok=True)
        _git(repo, "mv", old, new)
    write(head_files or {})
    _git(repo, "commit", "-q", "--allow-empty", "-m", "head")
    return repo, base


def _run_hold(argv, head_files=None, fail_on=None, decision=None, decision_text=None,
              base_files=None, renames=()):
    """Runs board_workflow_scope_hold.main() with a recording `gh` stub;
    `fail_on` ("edit" or "comment") makes that gh call fail. Fix and
    review-fixup run in a real repository whose head commit changes
    `head_files` (and `renames`) from `base_files`, passed as --diff-base;
    route reads `decision` (or the raw `decision_text`, "" for a missing
    file). Returns (rc, stdout, gh calls, step-summary text, stderr)."""
    import io
    import tempfile
    from contextlib import redirect_stderr, redirect_stdout
    import board_workflow_scope_hold as hold_mod
    calls = []

    def run(args, **_kwargs):
        calls.append(list(args))
        return _Proc(1 if fail_on and args[:3] == ["gh", "issue", fail_on] else 0)

    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        summary = os.path.join(tmp, "summary")
        open(summary, "w").close()
        decision_path = os.path.join(tmp, "decision.json")
        if decision is not None:
            with open(decision_path, "w", encoding="utf-8") as fh:
                json.dump({"decision": decision}, fh)
        elif decision_text:
            with open(decision_path, "w", encoding="utf-8") as fh:
                fh.write(decision_text)
        if "route" in argv:
            argv = argv + ["--route-decision", decision_path]
        else:
            repo, base = _make_repo(tmp, base_files, head_files, renames)
            argv = argv + ["--diff-base", base]
            os.chdir(repo)
        saved = {k: os.environ.get(k) for k in ("GITHUB_REPOSITORY", "GITHUB_STEP_SUMMARY")}
        os.environ.update(GITHUB_REPOSITORY="o/r", GITHUB_STEP_SUMMARY=summary)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = hold_mod.main(argv, run=run)
        finally:
            os.chdir(cwd)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        with open(summary, encoding="utf-8") as fh:
            return rc, out.getvalue().strip(), calls, fh.read(), err.getvalue()


WC_STAGE = "name: s\non:\n  workflow_call:\n    inputs:\n      a:\n        type: string\njobs: {}\n"


def hold_helper_failures():
    """board_workflow_scope_hold.py, executed: the check and the hold
    sequence every workflow-scope hold site shares (found by the code
    review of #921), and the fix sites' own listing and contract check of
    the real diff (#889)."""
    import board_workflow_scope_hold as hold_mod
    failures = 0
    base = ["--issue", "7", "--add-label", "board:stalled"]
    wf = {".github/workflows/x.yml": "on: push\n", "src/a.py": "a\n"}

    def ck(title, cond, detail=""):
        nonlocal failures
        if cond:
            print("[ok] board_workflow_scope_hold: {0}".format(title))
        else:
            failures += 1
            print("::error::verify-board-route-backstop: board_workflow_scope_hold: {0} -- "
                  "{1}".format(title, detail))

    rc, out, calls, _, _ = _run_hold(
        ["--site", "fix", "--can-push-workflows", "false"] + base,
        {"src/a.py": "a\n", ".github/actions/wing-commander-x/action.yml": "name: x\n"})
    ck("no workflow file -> clear, nothing posted", rc == 0 and out == "clear" and calls == [],
       "rc={0} out={1!r} calls={2!r}".format(rc, out, calls))
    rc, out, calls, _, _ = _run_hold(["--site", "fix", "--can-push-workflows", "true"] + base, wf)
    ck("a workflow file with the App's Workflows permission -> clear",
       rc == 0 and out == "clear" and calls == [], "rc={0} out={1!r}".format(rc, out))
    rc, out, calls, summary, _ = _run_hold(
        ["--site", "fix", "--can-push-workflows", "false", "--branch", "board/fix-7",
         "--base-sha", "abc"] + base, dict(wf, **{".github/workflows/sub/y`z.yml": "on: push\n"}))
    body = calls[1][-1] if len(calls) == 2 else ""
    ck("a workflow file -> label first, then one comment, then the summary line",
       rc == 0 and out == "held" and len(calls) == 2
       and calls[0][:3] == ["gh", "issue", "edit"] and "board:stalled" in calls[0]
       and calls[1][:4] == ["gh", "issue", "comment", "7"]
       and "`.github/workflows/x.yml`" in body and "y`z" not in body
       and "src/a.py" not in body and '"step": "stalled"' in body
       and '"branch": "board/fix-7"' in body
       and "fix (workflow-scope hold)" in summary,
       "rc={0} out={1!r} calls={2!r} summary={3!r}".format(rc, out, calls, summary))
    rc, out, calls, summary, _ = _run_hold(
        ["--site", "review-fixup", "--can-push-workflows", "false", "--pr", "70"] + base, wf)
    ck("review-fixup's comment names its PR",
       rc == 0 and out == "held" and "PR #70" in calls[-1][-1]
       and "review-fixup (workflow-scope hold)" in summary,
       "rc={0} calls={1!r}".format(rc, calls))
    rc, out, calls, summary, _ = _run_hold(
        ["--site", "route", "--can-push-workflows", "false"] + base,
        decision={"measured": {"workflow_paths": ["./.github/workflows/a b.yml"]}})
    ck("an unrenderable path falls back to naming the directory",
       rc == 0 and "a file under `.github/workflows/`" in calls[-1][-1]
       and "a b" not in calls[-1][-1] and "unchecked" not in calls[-1][-1],
       "calls={0!r}".format(calls))
    rc, out, calls, summary, _ = _run_hold(
        ["--site", "route", "--can-push-workflows", "false"] + base,
        decision={"measured": {"workflow_paths": [".github/workflows/x.yml"],
                               "contract_unknown_paths": [".github/actions/wing-commander-m/action.yml"]}})
    body = calls[-1][-1] if calls else ""
    ck("route names a held change's unchecked composite and its inputs:/outputs:",
       rc == 0 and out == "held" and "`.github/actions/wing-commander-m/action.yml`" in body
       and "`inputs:`/`outputs:`" in body, "rc={0} calls={1!r}".format(rc, calls))
    rc, out, calls, summary, _ = _run_hold(
        ["--site", "route", "--can-push-workflows", "false"] + base,
        decision={"measured": {"workflow_paths": [".github/workflows/x.yml", ".github/workflows/y.yml"],
                               "contract_unknown_paths": [".github/workflows/y.yml"]}})
    body = calls[-1][-1] if calls else ""
    ck("route names the paths whose contract effect went unchecked",
       rc == 0 and out == "held" and "for `.github/workflows/y.yml` to main" in body
       and "unchecked" in body and "route (workflow-scope hold)" in summary,
       "rc={0} calls={1!r}".format(rc, calls))
    rc, out, calls, summary, _ = _run_hold(["--site", "fix", "--can-push-workflows", "false"] + base,
                                           wf, fail_on="edit")
    ck("a failed label add posts nothing and fails (#604)",
       rc == 1 and out == "" and len(calls) == 1 and summary == "",
       "rc={0} out={1!r} calls={2!r}".format(rc, out, calls))
    rc, out, calls, summary, _ = _run_hold(["--site", "fix", "--can-push-workflows", "false"] + base,
                                           wf, fail_on="comment")
    ck("a failed comment fails and records no summary line (FR-011)",
       rc == 1 and out == "" and summary == "", "rc={0} out={1!r} summary={2!r}".format(rc, out, summary))

    # #889 (code review of #953): a non-ASCII workflow path, which a plain
    # `git diff --name-only` C-quotes ("\303\251") under core.quotePath.
    rc, out, calls, _, _ = _run_hold(["--site", "fix", "--can-push-workflows", "false"] + base,
                                     {".github/workflows/\u00e9.yml": "on: push\n"})
    ck("a non-ASCII workflow path is held (core.quotePath)",
       rc == 0 and out == "held" and len(calls) == 2, "rc={0} out={1!r}".format(rc, out))
    # #889 (code review of #955): a workflow renamed out of
    # .github/workflows/ still changes a workflow path.
    rc, out, calls, _, _ = _run_hold(
        ["--site", "review-fixup", "--can-push-workflows", "false", "--pr", "70"] + base,
        base_files={".github/workflows/stage.yml": WC_STAGE},
        renames=((".github/workflows/stage.yml", "docs/stage.yml"),))
    body = calls[-1][-1] if calls else ""
    ck("a workflow renamed away is held and its contract removal named",
       rc == 0 and out == "held" and "`.github/workflows/stage.yml`" in body
       and "published contract of `.github/workflows/stage.yml`" in body,
       "rc={0} out={1!r} calls={2!r}".format(rc, out, calls))
    # #889 (code review of #953): route drafted no workflow file, the
    # fixer's real change edits one -- the fix site lists and checks the
    # real diff itself, and says what its contract effect is.
    rc, out, calls, _, _ = _run_hold(
        ["--site", "fix", "--can-push-workflows", "false"] + base,
        {".github/workflows/stage.yml": WC_STAGE.replace("type: string", "type: boolean")},
        base_files={".github/workflows/stage.yml": WC_STAGE})
    body = calls[-1][-1] if calls else ""
    ck("fix's real diff changing a workflow_call input is named as a contract change",
       rc == 0 and out == "held" and "published contract of `.github/workflows/stage.yml`" in body
       and "spec-shaped" in body, "rc={0} calls={1!r}".format(rc, calls))
    rc, out, calls, _, _ = _run_hold(
        ["--site", "fix", "--can-push-workflows", "false"] + base,
        {".github/workflows/stage.yml": WC_STAGE.replace("jobs: {}", "jobs: {} # x")},
        base_files={".github/workflows/stage.yml": WC_STAGE})
    body = calls[-1][-1] if calls else ""
    ck("fix's real diff leaving the contract alone says so",
       rc == 0 and out == "held" and "changes no published contract" in body
       and "spec-shaped" not in body, "rc={0} calls={1!r}".format(rc, calls))
    # #889 (code review of #955): an unreadable or malformed decision is
    # an ::error:: naming the site, never a traceback.
    for title, text in (("missing", ""), ("not JSON", "{"), ("not an object", "[1]"),
                        ("no measured", '{"decision": {"measured": 3}}'),
                        ("paths not a list", '{"decision": {"measured": {"workflow_paths": "x"}}}')):
        try:
            rc, out, calls, _, err = _run_hold(
                ["--site", "route", "--can-push-workflows", "false"] + base, decision_text=text)
        except Exception as exc:  # the defect: a traceback out of main()
            rc, out, calls, err = "raised", "", [], repr(exc)
        ck("route decision {0}: ::error:: naming the site, nothing posted".format(title),
           rc == 1 and out == "" and calls == []
           and "::error::board-loop route (workflow-scope hold): cannot read route's decision" in err,
           "rc={0!r} err={1!r}".format(rc, err))
    # diff_name_list() itself, against real git output.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        repo, sha = _make_repo(tmp, {".github/workflows/stage.yml": WC_STAGE},
                               {".github/workflows/\u00e9.yml": "on: push\n"},
                               renames=((".github/workflows/stage.yml", "docs/stage.yml"),))
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            listed = sorted(diff_name_list(sha))
            widened = contract_widened(listed, "", read_worktree_contents(listed),
                                       read_base_contents(sha, listed))
        finally:
            os.chdir(cwd)
    ck("diff_name_list(): unquoted, a rename as both paths",
       listed == sorted([".github/workflows/\u00e9.yml", ".github/workflows/stage.yml",
                         "docs/stage.yml"]), "listed={0!r}".format(listed))
    ck("the final-diff check sees a workflow_call workflow moved away",
       widened == [".github/workflows/stage.yml"], "widened={0!r}".format(widened))

    # The check is workflow_push_blocked_paths(), not a copy: a helper
    # that never blocks must fail the held case above.
    original = hold_mod.workflow_push_blocked_paths
    hold_mod.workflow_push_blocked_paths = lambda paths, can_push: []
    try:
        rc, out, _, _, _ = _run_hold(["--site", "fix", "--can-push-workflows", "false"] + base, wf)
    finally:
        hold_mod.workflow_push_blocked_paths = original
    ck("mutation caught (the helper's check never blocks)", out != "held")
    # The listing is diff_name_list(): the old quoted, rename-detecting
    # listing must fail the non-ASCII case.
    original = hold_mod.diff_name_list
    hold_mod.diff_name_list = lambda b: subprocess.run(
        ["git", "diff", "--name-only", b, "HEAD"], capture_output=True, text=True,
        check=True).stdout.splitlines()
    try:
        rc, out, _, _, _ = _run_hold(["--site", "fix", "--can-push-workflows", "false"] + base,
                                     {".github/workflows/\u00e9.yml": "on: push\n"})
    finally:
        hold_mod.diff_name_list = original
    ck("mutation caught (a quoted `git diff --name-only` listing)", out != "held")
    return failures


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _measure_from(spec):
    def measure(_file_changes, _max_files, _max_lines):
        return spec["over_threshold"], spec["files"], spec["lines"]
    return measure


def run():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-route-backstop: fixtures directory "
              "{0} does not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(EXPECTED_CASES - cases_found)
    if missing_cases:
        print("::error::verify-board-route-backstop: missing fixture "
              "case(s): {0}".format(", ".join(missing_cases)))
        return 1

    for case in sorted(EXPECTED_CASES - {"post-push-final-diff-breach"}):
        case_path = os.path.join(FIXTURES_DIR, case, "case.json")
        if not os.path.isfile(case_path):
            failures += 1
            print("::error::verify-board-route-backstop: {0} is missing "
                  "case.json.".format(case_path))
            continue
        spec = _load(case_path)
        got = route(
            spec["agent_proposal"], file_changes=None,
            board_max_files=spec["board_max_files"],
            board_max_lines=spec["board_max_lines"],
            measure_backstop=_measure_from(spec["measure"]),
            diff_paths=spec.get("diff_paths"), diff_text=spec.get("diff_text"),
            file_contents=spec.get("file_contents"),
            proposal_extracted=spec.get("proposal_extracted", True),
            workflow_push_blocked=spec.get("workflow_push_blocked"),
            agent_rate_limited=spec.get("agent_rate_limited", False))
        expected = spec["expected"]
        ok = (got["backstop_verdict"] == expected["backstop_verdict"]
              and got["reason"] == expected["reason"])
        if "agent_proposal" in expected:
            ok = ok and got["agent_proposal"] == expected["agent_proposal"]
        if "contract_touched_paths" in expected:
            ok = ok and (got["measured"].get("contract_touched_paths") == expected["contract_touched_paths"])
        if "workflow_paths" in expected:
            ok = ok and (got["measured"].get("workflow_paths") == expected["workflow_paths"])
        if not ok:
            failures += 1
            print("::error::verify-board-route-backstop: {0}: expected {1!r}, "
                  "got {2!r}.".format(case, expected, got))
        else:
            print("[ok] {0}: route() == verdict={1!r} reason={2!r}".format(
                case, got["backstop_verdict"], got["reason"]))

    case = "post-push-final-diff-breach"
    case_path = os.path.join(FIXTURES_DIR, case, "case.json")
    if not os.path.isfile(case_path):
        failures += 1
        print("::error::verify-board-route-backstop: {0} is missing "
              "case.json.".format(case_path))
    else:
        spec = _load(case_path)
        initial = route(
            spec["agent_proposal"], file_changes=None,
            board_max_files=spec["board_max_files"],
            board_max_lines=spec["board_max_lines"],
            measure_backstop=_measure_from(spec["initial_measure"]),
            diff_paths=spec.get("diff_paths"), diff_text=spec.get("diff_text"))
        got = route_final_diff(
            initial, final_diff=None,
            board_max_files=spec["board_max_files"],
            board_max_lines=spec["board_max_lines"],
            measure_backstop=_measure_from(spec["final_measure"]),
            diff_paths=spec.get("diff_paths"), diff_text=spec.get("diff_text"))
        expected = spec["expected"]
        ok = (got["backstop_verdict"] == expected["backstop_verdict"]
              and got["reason"] == expected["reason"])
        if not ok:
            failures += 1
            print("::error::verify-board-route-backstop: {0}: expected "
                  "{1!r}, got {2!r} (initial={3!r}).".format(
                      case, expected, got, initial))
        else:
            print("[ok] {0}: route_final_diff() == verdict={1!r} "
                  "reason={2!r}".format(case, got["backstop_verdict"], got["reason"]))

    for proposal, expected in RATIONALE_CASES:
        got = one_line_rationale(proposal)
        if got != expected:
            failures += 1
            print("::error::verify-board-route-backstop: one_line_rationale("
                  "{0!r}) == {1!r}, expected {2!r}.".format(proposal, got, expected))
    long_text = one_line_rationale({"reasoning": "word " * 200})
    if len(long_text) > RATIONALE_MAX_CHARS or not long_text.endswith("..."):
        failures += 1
        print("::error::verify-board-route-backstop: one_line_rationale() "
              "did not truncate a long rationale to {0} chars with '...' "
              "(got {1} chars).".format(RATIONALE_MAX_CHARS, len(long_text)))
    for proposal, _expected in RATIONALE_CASES:
        got = one_line_rationale(proposal)
        if ("\n" in got or "`" in got or "*" in got or "<!--" in got
                or "-->" in got
                or any(unicodedata.category(c) == "Cf" for c in got)):
            failures += 1
            print("::error::verify-board-route-backstop: one_line_rationale("
                  "{0!r}) left a newline, backtick, `*`, Cf character or "
                  "comment delimiter "
                  "in {1!r}.".format(proposal, got))
    if not failures:
        print("[ok] one_line_rationale(): {0} case(s) + truncation".format(
            len(RATIONALE_CASES)))

    # workflow_push_blocked_paths(): any file under .github/workflows/ is
    # held (GitHub refuses the push for all of them), a composite or script
    # never is, and the maintainer's can-push statement empties the list.
    paths = [".github/workflows/watchdog.yml", "./.github/workflows/x.yaml",
             ".github/actions/wing-commander-context/action.yml",
             ".github/scripts/board_eligibility.py", "docs/setup.md",
             "b/.github/workflows/README.md", "github/workflows/not-it.yml"]
    for can_push, want in ((False, [".github/workflows/watchdog.yml", ".github/workflows/x.yaml",
                                    ".github/workflows/README.md"]),
                           (True, [])):
        got = workflow_push_blocked_paths(paths, can_push)
        if got != want:
            failures += 1
            print("::error::verify-board-route-backstop: workflow_push_blocked_paths("
                  "can_push={0}) == {1!r}, expected {2!r}.".format(can_push, got, want))
        else:
            print("[ok] workflow_push_blocked_paths(can_push={0})".format(can_push))

    for raw, want in (("./.github/workflows/a.yml", ".github/workflows/a.yml"),
                      ("a/.github/actions/x/action.yml", ".github/actions/x/action.yml"),
                      (".\\.github\\workflows\\b.yml", ".github/workflows/b.yml"),
                      ("a/docs/x.md", "a/docs/x.md"), (None, "")):
        got = normalize_repo_path(raw)
        if got != want:
            failures += 1
            print("::error::verify-board-route-backstop: normalize_repo_path({0!r}) == "
                  "{1!r}, expected {2!r}.".format(raw, got, want))

    # drafted_contract_widened(): the pre-push contract check on the route
    # agent's drafted diff, applied to main's file content by the hunks'
    # own lines (never their header numbers), then contract blocks compared.
    stage = ("name: x\n"
             "on:\n"
             "  workflow_call:\n"
             "    inputs:\n"
             "      a:\n"
             "        type: string\n"
             "permissions: {}\n"
             "jobs:\n"
             "  j:\n"
             "    runs-on: ubuntu-latest\n"
             "    steps:\n"
             "      - run: echo one\n"
             "      - run: echo two\n")
    wrapper = ("name: w\non:\n  push:\npermissions: {}\njobs:\n  j:\n    uses: ./x.yml\n")
    composite = ("name: c\ninputs:\n  a:\n    description: d\noutputs:\n  o:\n"
                 "    value: v\nruns:\n  using: composite\n  steps:\n    - run: echo hi\n"
                 "      shell: bash\n")
    bare_composite = "name: d\nruns:\n  using: composite\n  steps: []\n"
    main_files = {".github/workflows/stage.yml": stage,
                  ".github/workflows/wrapper.yml": wrapper,
                  ".github/actions/wing-commander-c/action.yml": composite,
                  ".github/actions/wing-commander-d/action.yml": bare_composite}

    def read_main(path):
        return main_files.get(path)

    add_input = ("@@ -5,2 +5,4 @@\n       a:\n         type: string\n"
                 "+      b:\n+        type: string\n")
    for title, changes, want in (
            ("a run: edit far from on: is not a contract change",
             [{"path": ".github/workflows/stage.yml",
               "diff": "@@ -12,1 +12,1 @@\n-      - run: echo one\n+      - run: echo uno\n"}], []),
            ("adding a workflow_call input is",
             [{"path": ".github/workflows/stage.yml", "diff": add_input}],
             [".github/workflows/stage.yml"]),
            ("wrong hunk line numbers do not hide it (located by content)",
             [{"path": "./.github/workflows/stage.yml", "diff": add_input.replace("@@ -5,2 +5,4 @@", "@@ -40,2 +40,4 @@")}],
             [".github/workflows/stage.yml"]),
            ("removing the workflow_call trigger is",
             [{"path": ".github/workflows/stage.yml",
               "diff": "@@ -2,5 +2,2 @@\n on:\n-  workflow_call:\n-    inputs:\n-      a:\n-        type: string\n+  push:\n"}],
             [".github/workflows/stage.yml"]),
            # #936: an unappliable diff is an unknown, left to the
            # final-diff check, unless its own changed lines name the
            # contract.
            ("an unlocatable run: hunk in a file with a contract is not (#936)",
             [{"path": ".github/workflows/stage.yml", "diff": "@@ -12,1 +12,1 @@\n-      - run: echo nope\n+      - run: echo x\n"}],
             []),
            ("no hunk header at all, likewise",
             [{"path": ".github/workflows/stage.yml", "diff": "-x\n+y\n"}],
             []),
            ("an unlocatable hunk that removes workflow_call is",
             [{"path": ".github/workflows/stage.yml",
               "diff": "@@ -2,2 +2,2 @@\n on:\n-  workflow_call: # gone\n+  push:\n"}],
             [".github/workflows/stage.yml"]),
            ("an unlocatable hunk in a composite that adds an outputs: key is",
             [{"path": ".github/actions/wing-commander-d/action.yml",
               "diff": "@@ -9,1 +9,3 @@\n missing: context\n+outputs:\n+  o:\n"}],
             [".github/actions/wing-commander-d/action.yml"]),
            ("an unlocatable runs: hunk in a composite with a contract is not",
             [{"path": ".github/actions/wing-commander-c/action.yml",
               "diff": "@@ -11,1 +11,1 @@\n-    - run: echo nope\n+    - run: echo x\n"}], []),
            ("a wrapper with no workflow_call and an ordinary edit is not",
             [{"path": ".github/workflows/wrapper.yml",
               "diff": "@@ -7,1 +7,1 @@\n-    uses: ./x.yml\n+    uses: ./y.yml\n"}], []),
            ("an unlocatable hunk in a wrapper with no contract is not",
             [{"path": ".github/workflows/wrapper.yml", "diff": "@@ -1 +1 @@\n-nope\n+x\n"}], []),
            ("adding workflow_call to a wrapper is",
             [{"path": ".github/workflows/wrapper.yml",
               "diff": "@@ -2,2 +2,3 @@\n on:\n+  workflow_call:\n   push:\n"}],
             [".github/workflows/wrapper.yml"]),
            ("a new wing-commander-* composite adds published surface",
             [{"path": ".github/actions/wing-commander-new/action.yml",
               "diff": "@@ -0,0 +1,2 @@\n+name: n\n+runs:\n"}],
             [".github/actions/wing-commander-new/action.yml"]),
            ("a new workflow without workflow_call does not",
             [{"path": ".github/workflows/new.yml", "diff": "@@ -0,0 +1,2 @@\n+name: n\n+on: push\n"}], []),
            ("deleting a composite with no inputs/outputs removes published surface",
             [{"path": ".github/actions/wing-commander-d/action.yml",
               "diff": "@@ -1,4 +0,0 @@\n-name: d\n-runs:\n-  using: composite\n-  steps: []\n"}],
             [".github/actions/wing-commander-d/action.yml"]),
            ("a composite gaining an inputs: block is",
             [{"path": ".github/actions/wing-commander-d/action.yml",
               "diff": "@@ -1,2 +1,5 @@\n name: d\n+inputs:\n+  a:\n+    description: x\n runs:\n"}],
             [".github/actions/wing-commander-d/action.yml"]),
            ("a composite's runs: steps are not its contract",
             [{"path": ".github/actions/wing-commander-c/action.yml",
               "diff": "@@ -11,1 +11,1 @@\n-    - run: echo hi\n+    - run: echo hello\n"}], []),
            ("a composite's outputs: are",
             [{"path": ".github/actions/wing-commander-c/action.yml",
               "diff": "@@ -6,2 +6,2 @@\n   o:\n-    value: v\n+    value: w\n"}],
             [".github/actions/wing-commander-c/action.yml"]),
            ("a script is never a contract change",
             [{"path": ".github/scripts/x.py", "diff": "-a\n+b\n"}], []),
            ("a malformed entry is skipped, not a crash",
             ["not-a-dict", {"path": None}], [])):
        got = drafted_contract_widened(changes, read_main)
        if got != want:
            failures += 1
            print("::error::verify-board-route-backstop: drafted_contract_widened: {0}: "
                  "got {1!r}, expected {2!r}.".format(title, got, want))
        else:
            print("[ok] drafted_contract_widened: {0}".format(title))

    # contract_widened()'s base_contents: the post-push check sees a
    # contract removed, which the new side alone cannot show.
    dropped = stage.replace("  workflow_call:\n    inputs:\n      a:\n        type: string\n", "  push:\n")
    for title, base, new_side, want in (
            ("a dropped workflow_call: is a breach", stage, dropped, [".github/workflows/stage.yml"]),
            ("an unchanged contract block is not", stage, stage.replace("echo one", "echo uno"), [])):
        got = contract_widened([".github/workflows/stage.yml"], "",
                               {".github/workflows/stage.yml": new_side},
                               {".github/workflows/stage.yml": base})
        if got != want:
            failures += 1
            print("::error::verify-board-route-backstop: contract_widened(base_contents): {0}: "
                  "got {1!r}, expected {2!r}.".format(title, got, want))
        else:
            print("[ok] contract_widened(base_contents): {0}".format(title))
    got = contract_widened([".github/actions/wing-commander-d/action.yml"], "", {},
                           {".github/actions/wing-commander-d/action.yml": bare_composite})
    if got != [".github/actions/wing-commander-d/action.yml"]:
        failures += 1
        print("::error::verify-board-route-backstop: contract_widened(base_contents): a deleted "
              "composite is not a breach (got {0!r}).".format(got))
    else:
        print("[ok] contract_widened(base_contents): a deleted composite is a breach")

    # #548: the extract step's `extracted` and route() read the category
    # through the same function, so they agree on every spelling.
    for raw, want in (("SPEC", "spec"), (" spec ", "spec"), ("Fix", "fix"),
                      ("fix", "fix"), ("banana", None), (None, None),
                      ("", None), (3, None), (["spec"], None)):
        got = normalize_category(raw)
        if got != want:
            failures += 1
            print("::error::verify-board-route-backstop: normalize_category("
                  "{0!r}) == {1!r}, expected {2!r}.".format(raw, got, want))

    failures += hold_helper_failures()

    # An unappliable drafted diff on a held workflow file never reaches
    # route_final_diff() (a hold never pushes): route() records it.
    unknown = []
    unappliable = [{"path": ".github/workflows/w.yml", "diff": "@@ -1 +1 @@\n-nope\n+x\n"}]
    got_widened = drafted_contract_widened(unappliable, lambda _p: "on:\n  workflow_call:\n",
                                           unknown=unknown)
    held = route("fix", unappliable, 3, 40, lambda *_a: (False, 1, 2),
                 widened_paths_override=got_widened, workflow_push_blocked=[".github/workflows/w.yml"],
                 contract_unknown_paths=unknown)
    fixed = route("fix", unappliable, 3, 40, lambda *_a: (False, 1, 2),
                  widened_paths_override=got_widened, contract_unknown_paths=unknown)
    if (got_widened == [] and unknown == [".github/workflows/w.yml"]
            and held["measured"].get("contract_unknown_paths") == [".github/workflows/w.yml"]
            and "contract_unknown_paths" not in fixed["measured"]):
        print("[ok] a held path whose drafted diff could not be applied is recorded as contract-unchecked")
    else:
        failures += 1
        print("::error::verify-board-route-backstop: contract_unknown_paths: widened={0!r} "
              "unknown={1!r} held={2!r} fixed={3!r}".format(got_widened, unknown, held, fixed))

    # A composite in a held change is never pushed either: an unappliable
    # drafted diff that adds an input under its existing inputs: (no
    # column-0 signal) is recorded too, not only the held workflow file.
    unknown = []
    mixed = [{"path": ".github/workflows/w.yml", "diff": "@@ -1 +1 @@\n-on: push\n+on: [push]\n"},
             {"path": ".github/actions/wing-commander-m/action.yml",
              "diff": "@@ -3,1 +3,2 @@\n missing: context\n+  new-input:\n"}]
    mains = {".github/workflows/w.yml": "on: push\n",
             ".github/actions/wing-commander-m/action.yml": "inputs:\n  a:\n    description: a\n"}
    got_widened = drafted_contract_widened(mixed, mains.get, unknown=unknown)
    held = route("fix", mixed, 3, 40, lambda *_a: (False, 2, 3),
                 widened_paths_override=got_widened, workflow_push_blocked=[".github/workflows/w.yml"],
                 contract_unknown_paths=unknown)
    if (got_widened == [] and held["reason"] == "workflow_scope"
            and held["measured"].get("contract_unknown_paths")
            == [".github/actions/wing-commander-m/action.yml"]):
        print("[ok] a held change's unappliable composite diff is recorded as contract-unchecked")
    else:
        failures += 1
        print("::error::verify-board-route-backstop: held composite contract_unknown_paths: "
              "widened={0!r} unknown={1!r} held={2!r}".format(got_widened, unknown, held))

    for problem in stalled_sources_problems():
        failures += 1
        print("::error::verify-board-route-backstop: " + problem)
    if os.path.isfile(LABELS_CONTRACT):
        with open(LABELS_CONTRACT, encoding="utf-8") as fh:
            labels_text = fh.read()
        if stalled_sources_problems(labels_text.replace(STALLED_ROW_SOURCES[2], "")):
            print("[ok] mutation caught (review-fixup dropped from the board:stalled sources)")
        else:
            failures += 1
            print("::error::verify-board-route-backstop: mutation 'review-fixup dropped from "
                  "the board:stalled sources' was NOT caught.")

    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            workflow_text = fh.read()
    except OSError as exc:
        workflow_text = ""
        failures += 1
        print("::error::verify-board-route-backstop: cannot read {0}: "
              "{1}".format(BOARD_LOOP, exc))
    if workflow_text:
        for problem in extract_step_problems(workflow_text) + hold_wiring_problems(workflow_text):
            failures += 1
            print("::error::verify-board-route-backstop: " + problem)
        for label, old, new in (
                ("hold paths no longer passed", "workflow_push_blocked=blocked", "workflow_push_blocked=None"),
                ("rate-limited defer dropped", 'agent_rate_limited=os.environ.get("ROUTE_AGENT_VERDICT") == "rate-limited"',
                 "agent_rate_limited=False"),
                ("defer reads the wrong verdict", "ROUTE_AGENT_VERDICT: ${{ steps.route-verdict.outputs.verdict }}",
                 "ROUTE_AGENT_VERDICT: ${{ steps.triage-verdict.outputs.verdict }}"),
                ("pre-push contract check dropped", "widened_paths_override=widened",
                 "widened_paths_override=[]"),
                ("drafted contract check never run",
                 "widened = drafted_contract_widened(file_changes, read_text, unknown=contract_unknown)",
                 "widened = []"),
                ("unchecked contract paths not passed to route()",
                 "contract_unknown_paths=contract_unknown)", "contract_unknown_paths=None)"),
                ("route's hold not given its decision",
                 ' --route-decision "$RUNNER_TEMP/board-route-decision.json"', ""),
                ("hold step gated off", "steps.decide.outputs.verdict == 'hold'",
                 "steps.decide.outputs.verdict == 'held'"),
                ("hold step stops stalling", "board_workflow_scope_hold.py --site route ",
                 "board_item_marker.py --step route "),
                ("fix's pre-push check pasted back inline",
                 '          held="$(python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_workflow_scope_hold.py" --site fix ',
                 '          if [ "$CAN_PUSH_WORKFLOWS" != "true" ] && grep -q \'^\\.github/workflows/\' <<<"$changed_paths"; then exit 0; fi\n'
                 '          held="$(python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_workflow_scope_hold.py" --site fix '),
                ("review-fixup's call names the wrong site",
                 "board_workflow_scope_hold.py\" --site review-fixup ", "board_workflow_scope_hold.py\" --site fix "),
                ("review-fixup ignores the answer", 'if [ "$held" = "held" ]; then\n            exit 0\n          fi\n          # The step\'s default shell',
                 "# The step's default shell"),
                ("a hold comment pasted back inline",
                 "          # no Workflows permission.\n",
                 "          # no Workflows permission.\n"
                 "          # The follow-up changes a workflow file, which this loop cannot push.\n"),
                ("fix's listing pasted back as `git diff --name-only`",
                 '          held="$(python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_workflow_scope_hold.py" --site fix ',
                 '          changed_paths="$(git diff --name-only "$BASE_SHA" HEAD)"\n'
                 '          held="$(python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_workflow_scope_hold.py" --site fix '),
                ("review-fixup's --diff-base dropped",
                 ' --diff-base "$REVIEWED_SHA"', ""),
                ("fix's final diff detects renames again",
                 'git -c core.quotePath=false diff --no-renames "$BASE_SHA" HEAD',
                 'git diff "$BASE_SHA" HEAD'),
                ("the final diffs list their own paths",
                 'diff_paths = diff_name_list(os.environ["BASE_SHA"])', "diff_paths = []"),
                ("fix's switch dropped",
                 "          BASE_SHA: ${{ steps.base.outputs.base-sha }}\n          CAN_PUSH_WORKFLOWS: ${{ vars.WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS == 'true' }}\n",
                 "          BASE_SHA: ${{ steps.base.outputs.base-sha }}\n          CAN_PUSH_WORKFLOWS: 'false'\n")):
            if old not in workflow_text:
                failures += 1
                print("::error::verify-board-route-backstop: mutation {0!r} "
                      "no longer applies -- update it.".format(label))
            elif not hold_wiring_problems(workflow_text.replace(old, new)):
                failures += 1
                print("::error::verify-board-route-backstop: mutation {0!r} "
                      "was NOT caught.".format(label))
            else:
                print("[ok] mutation caught ({0})".format(label))
        # The check must be able to fail: the pre-#548 line, and the
        # import dropped, are both caught.
        good = "extracted = normalize_category(parsed.get(\"category\")) is not None"
        for label, old, new in (
                ("exact-match extracted line",
                 good, 'extracted = parsed.get("category") in ("fix", "spec")'),
                ("import dropped", NORMALIZE_IMPORT + "\n", "")):
            if old not in workflow_text:
                failures += 1
                print("::error::verify-board-route-backstop: mutation {0!r} "
                      "no longer applies -- update it.".format(label))
            elif not extract_step_problems(workflow_text.replace(old, new)):
                failures += 1
                print("::error::verify-board-route-backstop: mutation {0!r} "
                      "was NOT caught.".format(label))
            else:
                print("[ok] mutation caught ({0})".format(label))

    print("verify-board-route-backstop: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
