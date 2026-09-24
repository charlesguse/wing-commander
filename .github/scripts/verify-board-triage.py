#!/usr/bin/env python3
"""Gate — board_triage.py's triage() and _first_divergent_pin() resolve
every FR-064 bullet-1 branch correctly (specs/057-autonomous-board-loop,
contracts/triage.md), check_action_bump() compares only the cited run's
own workflow, and board-loop.yml's triage job takes its cited run only
from trust-filtered text (#505).

WHY THIS EXISTS
---------------
Triage is the one place this feature is allowed to close an issue with no
human in the loop. A regression that closed on an agent's say-so, or that
missed a genuine 429, would be invisible on every fixture except the exact
one it broke -- this gate pins all six documented branches, including the
one FR-012 exists to forbid (an "already fixed" proposal must NOT close).

#505: both close grounds are only as trustworthy as the run they read. The
triage job's "Locate a cited run" step used to scan the issue body AND
every comment unfiltered, and check_action_bump() compared every
workflow's pins -- so anyone could comment a link to an old run from
before an unrelated upstream action bump and get a maintainer's issue
closed. Two checks keep that shut:

1. scoping (behavioural, a throwaway git repo): a pin bump in a workflow
   the cited run did not run must NOT count; one in the cited workflow,
   or in a local reusable workflow it calls, must; an unknown or
   untracked cited workflow yields no bump. A mutation that widens the
   scope back to every workflow must fail these cases.
2. cite-source (structural, board-loop.yml's triage job):
   - the `cite` step reads the issue ONLY from an env var mapped to
     exactly `${{ steps.ID.outputs.context-file }}`, where ID is an
     earlier, un-gated wing-commander-issue-context step in the same job
     (context-file, not comments-file: the body is where a watchdog issue
     cites its run), and never reassigns that variable;
   - the `cite` step makes no read of its own: no `gh`, `curl` or `wget`;
   - no `run:` in the triage job reads comments unfiltered (`gh api`
     of `.../comments`, `--comments`, `--json ...comments`, a graphql
     `comments(` selection);
   - the evidence fetch takes RUN_ID from `steps.cite.outputs.run-id`
     (the 429 path reads that run's transcript) and the decide step takes
     RUN_URL from `steps.cite.outputs.run-url` and WORKFLOW_PATH from the
     fetch step's `workflow-path`, passed as `cited_run_workflow_path`.
   Each is proven by mutating the real board-loop.yml in memory; every
   mutation must be caught.

Fixtures (FR-064 bullet 1), each a checked-in transcript/workflow-pin pair
under .github/scripts/tests/board-triage/<case>/. Fails loudly, not
vacuously, if any fixture file is missing.
"""
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
import board_triage  # noqa: E402
from board_triage import triage, _first_divergent_pin  # noqa: E402

FIXTURES_DIR = os.path.join(SCRIPTS_DIR, "tests", "board-triage")

TRIAGE_CASES = {
    "429-present": {"outcome": "closed", "ground": "rate_limit"},
    "429-absent-genuine-failure": {"outcome": "proceed", "ground": None},
    "evidence-unavailable": {"outcome": "proceed", "ground": "evidence_unavailable"},
    "already-fixed-proposal": {"outcome": "handover", "ground": "already_fixed_proposal"},
}
PIN_CASES = {
    "action-bump-ahead": "divergent",
    "pins-equal": "none",
}
EXPECTED = dict.fromkeys(list(TRIAGE_CASES) + list(PIN_CASES))

CWD = os.getcwd()
BOARD_LOOP = os.path.join(".github", "workflows", "board-loop.yml")
ISSUE_CONTEXT_USES = "wing-commander-issue-context"
# A not-rate-limited transcript, so triage() reaches the action-bump ground.
GENUINE_FAILURE_TRANSCRIPT = os.path.join(
    FIXTURES_DIR, "429-absent-genuine-failure", "transcript.json")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run_fixtures():
    failures = 0

    if not os.path.isdir(FIXTURES_DIR):
        print("::error::verify-board-triage: fixtures directory {0} does "
              "not exist.".format(FIXTURES_DIR))
        return 1

    cases_found = {
        os.path.basename(path)
        for path in glob.glob(os.path.join(FIXTURES_DIR, "*"))
        if os.path.isdir(path)
    }
    missing_cases = sorted(set(EXPECTED) - cases_found)
    if missing_cases:
        print("::error::verify-board-triage: missing fixture case(s): "
              "{0}".format(", ".join(missing_cases)))
        return 1

    for case, expected in sorted(TRIAGE_CASES.items()):
        case_dir = os.path.join(FIXTURES_DIR, case)
        issue_path = os.path.join(case_dir, "issue.json")
        if not os.path.isfile(issue_path):
            failures += 1
            print("::error::verify-board-triage: {0} is missing "
                  "issue.json.".format(case_dir))
            continue
        issue = _load(issue_path)
        # Fixture-declared transcript paths are repo-root-relative;
        # normalise against this process's own cwd so the gate is safe to
        # invoke from any directory.
        transcript_path = issue.get("cited_run_transcript_path")
        if transcript_path and not os.path.isabs(transcript_path):
            issue = dict(issue)
            issue["cited_run_transcript_path"] = os.path.join(CWD, transcript_path)
        got = triage(issue, cited_run="https://github.com/example/example/actions/runs/1")
        ok = got.get("outcome") == expected["outcome"] and got.get("ground") == expected["ground"]
        if case == "already-fixed-proposal" and got.get("outcome") == "closed":
            ok = False  # FR-012: never a close ground, regardless of anything else
        if not ok:
            failures += 1
            print("::error::verify-board-triage: {0}: expected outcome={1!r} "
                  "ground={2!r}, got {3!r}.".format(
                      case, expected["outcome"], expected["ground"], got))
        else:
            print("[ok] {0}: triage() == outcome={1!r} ground={2!r}".format(
                case, got.get("outcome"), got.get("ground")))

    for case, expected in sorted(PIN_CASES.items()):
        case_dir = os.path.join(FIXTURES_DIR, case)
        pins_path = os.path.join(case_dir, "pins.json")
        if not os.path.isfile(pins_path):
            failures += 1
            print("::error::verify-board-triage: {0} is missing "
                  "pins.json.".format(case_dir))
            continue
        pins = _load(pins_path)
        got = _first_divergent_pin(
            pins["workflow_file"], pins["run_pins"], pins["main_pins"])
        got_shape = "divergent" if got is not None else "none"
        if got_shape != expected:
            failures += 1
            print("::error::verify-board-triage: {0}: expected {1!r}, "
                  "got {2!r} ({3!r}).".format(case, expected, got_shape, got))
        else:
            print("[ok] {0}: _first_divergent_pin() == {1!r}".format(case, got))

    return failures


# ---------------------------------------------------------------------------
# Check 1 -- check_action_bump() scoping (#505), against a real git history.
# ---------------------------------------------------------------------------

WF = ".github/workflows/"
_OLD_TREE = {
    WF + "ci.yml": "jobs:\n  a:\n    steps:\n      - name: co\n"
                   "        uses: actions/checkout@v4\n",
    WF + "other.yml": "jobs:\n  a:\n    steps:\n      - name: node\n"
                      "        uses: actions/setup-node@v3\n",
    WF + "wrapper.yml": "jobs:\n  call:\n"
                        "    uses: ./.github/workflows/stage.yml\n",
    WF + "stage.yml": "jobs:\n  a:\n    steps:\n      - name: py\n"
                      "        uses: actions/setup-python@v4\n",
}
# main: every workflow except ci.yml and wrapper.yml bumps its pin.
_BUMPS = {
    WF + "other.yml": ("@v3", "@v4"),
    WF + "stage.yml": ("@v4", "@v5"),
}
# Main's bump in ci.yml exists only for the "cited workflow bumped" case.
_CI_BUMP = (WF + "ci.yml", ("@v4", "@v5"))

ALL_WORKFLOWS = sorted(_OLD_TREE)

# (label, cited workflow path, bump ci.yml on main too?, expected
# workflow_file of the divergence, or None for "no bump").
SCOPING_CASES = (
    ("bump only in an unrelated workflow does not count",
     WF + "ci.yml", False, None),
    ("bump in the cited workflow counts",
     WF + "ci.yml", True, WF + "ci.yml"),
    ("bump in a local reusable workflow the cited one calls counts",
     WF + "wrapper.yml", False, WF + "stage.yml"),
    ("run API path carrying an @ref suffix is normalised",
     WF + "ci.yml@refs/heads/main", True, WF + "ci.yml"),
    ("no cited workflow path yields no bump",
     None, True, None),
    ("a cited workflow main does not track (dynamic) yields no bump",
     "dynamic/pages/pages-build-deployment", True, None),
)


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", repo, "-c", "user.name=gate", "-c",
         "user.email=gate@example.invalid", "-c", "commit.gpgsign=false"]
        + list(args),
        check=True, capture_output=True, text=True)


def _write_tree(repo, tree):
    for rel, text in tree.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def _build_repo(repo, bump_ci):
    """old commit (the cited run's) -> main commit with the pin bumps."""
    _git(repo, "init", "-q")
    _write_tree(repo, _OLD_TREE)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "run commit")
    run_sha = subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True).stdout.strip()
    bumps = dict(_BUMPS)
    if bump_ci:
        bumps[_CI_BUMP[0]] = _CI_BUMP[1]
    main_tree = {rel: (text.replace(*bumps[rel]) if rel in bumps else text)
                 for rel, text in _OLD_TREE.items()}
    _write_tree(repo, main_tree)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main bumps")
    return run_sha


def run_scoping_cases(verbose=True):
    """Returns a list of failure strings. Runs check_action_bump() (and
    triage() on top of it) inside a throwaway repo, since both read the
    run's commit via `git show` and main's file from the working tree."""
    failures = []
    for bump_ci in (False, True):
        with tempfile.TemporaryDirectory() as repo:
            try:
                run_sha = _build_repo(repo, bump_ci)
            except (OSError, subprocess.CalledProcessError) as exc:
                return ["scoping: could not build the fixture repo: {0}".format(exc)]
            prev = os.getcwd()
            os.chdir(repo)
            try:
                for label, cited, needs_ci_bump, expected in SCOPING_CASES:
                    if needs_ci_bump != bump_ci:
                        continue
                    got = board_triage.check_action_bump(
                        run_sha, ALL_WORKFLOWS, cited)
                    got_file = got.get("workflow_file") if got else None
                    verdict = triage({
                        "cited_run_transcript_path": GENUINE_FAILURE_TRANSCRIPT,
                        "cited_run_commit_sha": run_sha,
                        "cited_run_workflow_path": cited,
                        "workflow_files": ALL_WORKFLOWS,
                        "agent_proposal": {},
                    }, cited_run="https://github.com/example/example/actions/runs/1")
                    want_outcome = "closed" if expected else "proceed"
                    if got_file != expected or verdict.get("outcome") != want_outcome:
                        failures.append(
                            "scoping: {0}: expected divergence in {1!r} and "
                            "triage outcome {2!r}, got {3!r} and {4!r}".format(
                                label, expected, want_outcome, got,
                                verdict.get("outcome")))
                    elif verbose:
                        print("[ok] scoping: {0} ({1!r})".format(label, got_file))
            finally:
                os.chdir(prev)
    return failures


def _mutation_check_scoping():
    """The scoping cases must fail once the scope is widened back to every
    tracked workflow (the pre-#505 behaviour)."""
    original = board_triage._scoped_workflow_files
    board_triage._scoped_workflow_files = (
        lambda cited, workflow_files, read_at_run: list(workflow_files or []))
    try:
        caught = bool(run_scoping_cases(verbose=False))
    finally:
        board_triage._scoped_workflow_files = original
    if not caught:
        return ["mutation 'scope widened to every workflow' was NOT caught"]
    print("note: mutation caught (scope widened to every workflow).")
    return []


# ---------------------------------------------------------------------------
# Check 2 -- the cite step reads only trust-filtered text (#505).
# ---------------------------------------------------------------------------

def _load_reassignment_res():
    """Gate 93's own "this variable is never reassigned" patterns -- one
    home for that shell idiom, not a second copy here."""
    path = os.path.join(SCRIPTS_DIR, "verify-issue-context-single-home.py")
    spec = importlib.util.spec_from_file_location("_gate93", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._reassignment_res


CONTEXT_FILE_RE = re.compile(
    r"^\$\{\{\s*steps\.([A-Za-z0-9_-]+)\.outputs\.context-file\s*\}\}$")
OWN_READ_RE = re.compile(r"(?:^|[\s;|&(`])(?:gh|curl|wget)(?:\s|$)")
UNFILTERED_COMMENT_RES = (
    re.compile(r"\bgh\s+api\b[^\n]*/comments\b"),
    re.compile(r"--comments\b"),
    re.compile(r"--json[=\s]+[\"']?[\w,]*\bcomments\b"),
    re.compile(r"\bcomments\s*\("),
)


def _expr(value):
    return " ".join(str(value or "").split())


def _code_lines(run_text):
    """run: text with whole-line shell comments dropped."""
    return "\n".join(line for line in (run_text or "").split("\n")
                     if not line.lstrip().startswith("#"))


def check_cite_source(path, reassignment_res):
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        return ["{0}: could not parse: {1}".format(path, exc)]
    job = ((doc or {}).get("jobs") or {}).get("triage")
    if not isinstance(job, dict):
        return ["{0}: no `triage` job -- check 2 cannot be vacuous".format(path)]
    steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
    by_id = {s.get("id"): i for i, s in enumerate(steps) if s.get("id")}
    problems = []

    for step in steps:
        code = _code_lines(step.get("run"))
        for pattern in UNFILTERED_COMMENT_RES:
            if pattern.search(code):
                problems.append(
                    "triage step {0!r} reads issue comments unfiltered ({1}) "
                    "-- use wing-commander-issue-context's context-file".format(
                        step.get("name"), pattern.pattern))

    if "cite" not in by_id:
        problems.append("triage job has no step with id `cite`")
        return problems
    cite_index = by_id["cite"]
    cite = steps[cite_index]
    code = _code_lines(cite.get("run"))

    if OWN_READ_RE.search(code):
        problems.append("the cite step makes a read of its own (gh/curl/wget)"
                        " -- it must scan only the context-file")

    env = cite.get("env") or {}
    ctx_vars = []
    for var, value in env.items():
        m = CONTEXT_FILE_RE.match(_expr(value))
        if not m:
            continue
        src = by_id.get(m.group(1))
        if (src is not None and src < cite_index
                and ISSUE_CONTEXT_USES in str(steps[src].get("uses") or "")
                and "if" not in steps[src]):
            ctx_vars.append(var)
    if not ctx_vars:
        problems.append(
            "the cite step's env maps no variable to "
            "`${{ steps.ID.outputs.context-file }}` of an earlier, un-gated "
            "wing-commander-issue-context step")
    elif not any(re.search(r'"\$\{?' + re.escape(v) + r'\}?"', code)
                 for v in ctx_vars):
        problems.append("the cite step never reads its context-file variable "
                        "({0})".format(", ".join(ctx_vars)))
    for var in ctx_vars:
        if any(p.search(code) for p in reassignment_res(var)):
            problems.append("the cite step reassigns {0}".format(var))

    wiring = (
        ("fetch", "RUN_ID", "${{ steps.cite.outputs.run-id }}"),
        ("decide", "RUN_URL", "${{ steps.cite.outputs.run-url }}"),
        ("decide", "WORKFLOW_PATH", "${{ steps.fetch.outputs.workflow-path }}"),
    )
    for step_id, var, want in wiring:
        step = steps[by_id[step_id]] if step_id in by_id else None
        got = _expr(((step or {}).get("env") or {}).get(var))
        if got != _expr(want):
            problems.append("triage step `{0}` must map {1} to exactly {2} "
                            "(got {3!r})".format(step_id, var, want, got))
    decide = steps[by_id["decide"]] if "decide" in by_id else {}
    if "cited_run_workflow_path" not in str(decide.get("run") or ""):
        problems.append("the decide step never passes cited_run_workflow_path"
                        " to triage()")
    fetch = steps[by_id["fetch"]] if "fetch" in by_id else {}
    if "workflow-path=" not in str(fetch.get("run") or ""):
        problems.append("the fetch step never emits workflow-path")
    return problems


_UNFILTERED_READ = ('          gh api "repos/$GITHUB_REPOSITORY/issues/'
                    '$ISSUE_NUMBER/comments" --paginate --jq \'.[].body\' '
                    '>> "$ISSUE_CONTEXT_FILE"\n')
_CITE_RUN_HEAD = ("        run: |\n          set -uo pipefail\n"
                  "          run_url=\"$(grep -oE")

# Each mutation rewrites the REAL board-loop.yml in memory the way a later
# edit could reopen #505; check 2 must catch every one.
CITE_MUTATIONS = (
    ("cite re-reads every comment via gh api",
     _CITE_RUN_HEAD,
     _CITE_RUN_HEAD.replace("set -uo pipefail\n",
                            "set -uo pipefail\n" + _UNFILTERED_READ)),
    ("cite reads gh issue view --comments",
     _CITE_RUN_HEAD,
     _CITE_RUN_HEAD.replace(
         "set -uo pipefail\n",
         "set -uo pipefail\n          gh issue view \"$N\" --comments "
         ">> \"$ISSUE_CONTEXT_FILE\"\n")),
    ("cite reads --json body,comments",
     _CITE_RUN_HEAD,
     _CITE_RUN_HEAD.replace(
         "set -uo pipefail\n",
         "set -uo pipefail\n          gh issue view \"$N\" --json "
         "body,comments > \"$ISSUE_CONTEXT_FILE\"\n")),
    ("cite fed the comments-file (drops the body)",
     "ISSUE_CONTEXT_FILE: ${{ steps.issue-context-triage.outputs.context-file }}",
     "ISSUE_CONTEXT_FILE: ${{ steps.issue-context-triage.outputs.comments-file }}"),
    ("cite reassigns its context-file variable",
     _CITE_RUN_HEAD,
     _CITE_RUN_HEAD.replace(
         "set -uo pipefail\n",
         "set -uo pipefail\n          ISSUE_CONTEXT_FILE=/tmp/raw.md\n")),
    ("issue-context fetch gated off",
     "        id: issue-context-triage\n",
     "        id: issue-context-triage\n        if: false\n"),
    ("another triage step reads comments unfiltered",
     "      - name: Fetch the cited run's own evidence, if reachable\n",
     "      - name: Stage raw comments\n        run: |\n" + _UNFILTERED_READ
     + "\n      - name: Fetch the cited run's own evidence, if reachable\n"),
    ("evidence fetch reads a run the cite step did not choose",
     "RUN_ID: ${{ steps.cite.outputs.run-id }}",
     "RUN_ID: ${{ steps.other.outputs.run-id }}"),
    ("decide drops the cited workflow path",
     "          WORKFLOW_PATH: ${{ steps.fetch.outputs.workflow-path }}\n",
     ""),
    ("cite step renamed away",
     "        id: cite\n",
     "        id: cite-any\n"),
)


def _mutation_check_cite(reassignment_res):
    failures = []
    try:
        with open(BOARD_LOOP, encoding="utf-8") as fh:
            original = fh.read()
    except OSError as exc:
        return ["mutation check: could not read {0}: {1}".format(BOARD_LOOP, exc)]
    with tempfile.TemporaryDirectory() as tmpdir:
        for label, old, new in CITE_MUTATIONS:
            if old not in original:
                failures.append(
                    "mutation {0!r} no longer applies ({1!r} not in {2}) -- "
                    "update CITE_MUTATIONS so this gate stays proven.".format(
                        label, old, BOARD_LOOP))
                continue
            path = os.path.join(tmpdir, "board-loop-mutated.yml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(original.replace(old, new, 1))
            if not check_cite_source(path, reassignment_res):
                failures.append("mutation {0!r} was NOT caught".format(label))
            else:
                print("note: mutation caught ({0}).".format(label))
    return failures


def run():
    failures = run_fixtures()

    problems = run_scoping_cases()
    problems.extend(_mutation_check_scoping())

    reassignment_res = _load_reassignment_res()
    cite_problems = check_cite_source(BOARD_LOOP, reassignment_res)
    if not cite_problems:
        print("[ok] cite-source: {0}'s triage job reads its cited run only "
              "from the trust-filtered context-file".format(BOARD_LOOP))
    problems.extend(cite_problems)
    problems.extend(_mutation_check_cite(reassignment_res))

    for problem in problems:
        print("::error::verify-board-triage: {0}".format(problem))
    failures += len(problems)
    print("verify-board-triage: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
