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

#402: the rate-limit ground closed a 451-turn, $43 run because it carried
an informational `rate_limit_event`. That ground needs rate-limit evidence
AND a failed run AND one turn (0..1) AND zero cost, and its evidence must
quote the transcript's own fields. Each guard has a fixture of its own
(many turns at $0, negative turns, one paid turn, no cost, a successful
run), closed cases pin the quoted evidence exactly, and a mutation per
guard -- plus one hard-coding the evidence -- must be caught.

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
   - every line of the `cite` step's run: is on an allowlist whose only
     read is ONE `board_triage.py find-cited-run` call with that variable
     as its sole file operand -- no second file, no raw grep that skips
     find_cited_run()'s quote/fence handling, no `gh`/`curl`/`wget`;
   - no triage step reads comments unfiltered (`/comments`, `--comments`,
     `--json ...comments`, a graphql `comments(` selection,
     `listComments`) in its `run:` text OR in any `env:`/`with:` value
     (a comments URL staged in env: and fetched as `gh api "$URL"`);
   - the evidence fetch takes RUN_ID from `steps.cite.outputs.run-id`
     (the 429 path reads that run's transcript) and the decide step takes
     RUN_URL from `steps.cite.outputs.run-url` and WORKFLOW_PATH from the
     fetch step's `workflow-path`, assigned as the issue dict's
     `"cited_run_workflow_path"` key (a code line, not a mention).
   Each is proven by mutating the real board-loop.yml in memory; every
   mutation must be caught.
3. find_cited_run() (behavioural): a `>`-quoted or fenced run link in
   trusted text is not a cite (a maintainer quote-replying to a stranger
   carries the stranger's link), a watchdog `_First seen: [this run](..)_`
   marker wins over an earlier link, and a plain body link still works.
   Removing the quote/fence stripping or the First-seen preference must
   fail these.

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
    # A closed rate_limit verdict's evidence must quote the transcript's own
    # fields (FR-013), so "evidence" pins them exactly.
    "429-present": {"outcome": "closed", "ground": "rate_limit", "evidence": {
        "rate_limit_event": True, "rate_limit_status": None,
        "terminal_reason": "api_error", "api_error_status": "429",
        "num_turns": 1, "cost_usd": 0}},
    "429-absent-genuine-failure": {"outcome": "proceed", "ground": None},
    "evidence-unavailable": {"outcome": "proceed", "ground": "evidence_unavailable"},
    "already-fixed-proposal": {"outcome": "handover", "ground": "already_fixed_proposal"},
}
# The rate-limit ground needs evidence AND a failed run AND one turn AND
# zero cost (#402). Each case below must NOT close; each guard has its own
# case so dropping any one guard fails the gate.
RATE_LIMIT_GUARD_CASES = {
    # #402's shape: informational events on a 451-turn, $43.06 run.
    "rate-limit-event-many-turns": {"outcome": "proceed", "ground": None},
    # turns guard alone (cost is 0).
    "429-many-turns-zero-cost": {"outcome": "proceed", "ground": None},
    # turns range: a negative count is not "one turn".
    "429-negative-turns": {"outcome": "proceed", "ground": None},
    # cost guard alone (one turn).
    "429-one-turn-nonzero-cost": {"outcome": "proceed", "ground": None},
    "429-cost-missing": {"outcome": "proceed", "ground": None},
    # failed-run guard alone: one turn, $0, but the run succeeded.
    "rate-limit-event-success": {"outcome": "proceed", "ground": None},
}
TRIAGE_CASES.update(RATE_LIMIT_GUARD_CASES)
# Evidence from a rate_limit_event alone (no api_error_status): hard-coded
# "429"/True evidence would misquote this run.
TRIAGE_CASES["rate-limit-event-only"] = {
    "outcome": "closed", "ground": "rate_limit", "evidence": {
        "rate_limit_event": True, "rate_limit_status": "rejected",
        "terminal_reason": "rate_limited", "api_error_status": None,
        "num_turns": 1, "cost_usd": 0}}
EVIDENCE_CASES = {k: v for k, v in TRIAGE_CASES.items() if "evidence" in v}
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


def run_triage_cases(cases, verbose=True):
    """One problem string per triage fixture whose verdict is wrong."""
    problems = []
    for case, expected in sorted(cases.items()):
        case_dir = os.path.join(FIXTURES_DIR, case)
        issue_path = os.path.join(case_dir, "issue.json")
        if not os.path.isfile(issue_path):
            problems.append("{0} is missing issue.json.".format(case_dir))
            if verbose:
                print("::error::verify-board-triage: " + problems[-1])
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
        if "evidence" in expected:
            want = dict(expected["evidence"],
                        run_url=(got.get("evidence") or {}).get("run_url"))
            if got.get("evidence") != want:
                ok = False
        if not ok:
            problems.append("{0}: expected outcome={1!r} ground={2!r}, got "
                            "{3!r}.".format(case, expected["outcome"],
                                            expected["ground"], got))
            if verbose:
                print("::error::verify-board-triage: " + problems[-1])
        elif verbose:
            print("[ok] {0}: triage() == outcome={1!r} ground={2!r}".format(
                case, got.get("outcome"), got.get("ground")))
    return problems


def _guardless_check_rate_limit(run_transcript_path):
    """The pre-#402 rule: any rate-limit evidence closes, whatever the run's
    turns or cost. Used only as a mutation."""
    try:
        with open(run_transcript_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    records = data if isinstance(data, list) else [data]
    result = board_triage._last_of_type(records, "result")
    if not result:
        return None
    if board_triage._last_of_type(records, "rate_limit_event") or (
            result.get("terminal_reason") == "api_error"
            and str(result.get("api_error_status") or "") == "429"):
        return {"rate_limit_event": True, "api_error_status": "429",
                "num_turns": result.get("num_turns"),
                "cost_usd": result.get("total_cost_usd")}
    return None


def _hardcoded_evidence(original):
    """check_rate_limit() asserting constants instead of quoting (F1)."""
    def mutated(path):
        got = original(path)
        if got is not None:
            got = dict(got, rate_limit_event=True, api_error_status="429")
        return got
    return mutated


def _turns_upper_bound_only(result):
    num_turns = board_triage._number(result.get("num_turns"))
    return num_turns is not None and num_turns <= 1


# (label, board_triage attribute, replacement factory taking the original).
RATE_LIMIT_MUTATIONS = (
    ("evidence-only rule restored (every guard removed)",
     "check_rate_limit", lambda orig: _guardless_check_rate_limit),
    ("turns guard removed", "_one_turn", lambda orig: lambda result: True),
    ("turns lower bound removed", "_one_turn",
     lambda orig: _turns_upper_bound_only),
    ("cost guard removed", "_zero_cost", lambda orig: lambda result: True),
    ("failed-run guard removed", "_failed", lambda orig: lambda result: True),
    ("evidence hard-coded instead of quoted", "check_rate_limit",
     _hardcoded_evidence),
)


def _mutation_check_rate_limit_guard():
    """Each rate-limit guard (#402), and quoting the transcript's own
    fields, is pinned by its own fixture: every mutation must be caught."""
    failures = []
    for label, name, factory in RATE_LIMIT_MUTATIONS:
        original = getattr(board_triage, name)
        setattr(board_triage, name, factory(original))
        try:
            caught = bool(run_triage_cases(TRIAGE_CASES, verbose=False))
        finally:
            setattr(board_triage, name, original)
        if caught:
            print("note: mutation caught (rate limit: {0}).".format(label))
        else:
            failures.append("mutation 'rate limit: {0}' was NOT caught"
                            .format(label))
    return failures


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

    failures += len(run_triage_cases(TRIAGE_CASES))

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
# Scanned in every triage step's run: text AND its env:/with: values -- a
# comments URL staged in env: and fetched as `gh api "$URL"` has no
# `/comments` in its run: text at all (#505 review).
UNFILTERED_COMMENT_RES = (
    re.compile(r"\bgh\s+api\b[^\n]*/comments\b"),
    re.compile(r"/comments\b"),
    re.compile(r"--comments\b"),
    re.compile(r"--json[=\s]+[\"']?[\w,]*\bcomments\b"),
    re.compile(r"\bcomments\s*\("),
    re.compile(r"\blistComments\b"),
)
# The cite step's whole run: body, line by line (comments and blank lines
# aside). Anything else -- a second file operand, a raw grep that skips
# find_cited_run()'s quote/fence handling, a read of its own -- fails.
CITE_CALL_RE = re.compile(
    r'^run_url="\$\(python3 \.github/scripts/board_triage\.py find-cited-run '
    r'--repository "\$GITHUB_REPOSITORY" "\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"'
    r'(?: \|\| true)?\)"$')
CITE_ALLOWED_LINES = frozenset((
    "set -uo pipefail",
    'echo "run-url=$run_url" >> "$GITHUB_OUTPUT"',
    'if [ -n "$run_url" ]; then',
    'echo "run-id=${run_url##*/}" >> "$GITHUB_OUTPUT"',
    "fi",
))
DECIDE_KEY_RE = re.compile(
    r'^\s*"cited_run_workflow_path":\s*os\.environ\.get\("WORKFLOW_PATH"\)',
    re.MULTILINE)


def _expr(value):
    return " ".join(str(value or "").split())


def _code_lines(run_text):
    """run: text with whole-line shell comments dropped."""
    return "\n".join(line for line in (run_text or "").split("\n")
                     if not line.lstrip().startswith("#"))


def _input_values(step):
    """Every env: and with: value of a step, as (key, text) pairs."""
    values = []
    for key in ("env", "with"):
        block = step.get(key)
        if isinstance(block, dict):
            values.extend((k, str(v)) for k, v in block.items())
    return values


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
        sources = [("run:", _code_lines(step.get("run")))]
        sources.extend(("input " + k, v) for k, v in _input_values(step))
        for where, text in sources:
            for pattern in UNFILTERED_COMMENT_RES:
                if pattern.search(text):
                    problems.append(
                        "triage step {0!r} reads issue comments unfiltered "
                        "in its {1} ({2}) -- use wing-commander-issue-"
                        "context's context-file".format(
                            step.get("name"), where, pattern.pattern))
                    break

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
    for var in ctx_vars:
        if any(p.search(code) for p in reassignment_res(var)):
            problems.append("the cite step reassigns {0}".format(var))

    calls = 0
    for line in code.split("\n"):
        line = line.strip()
        if not line or line in CITE_ALLOWED_LINES:
            continue
        m = CITE_CALL_RE.match(line)
        if m and m.group(1) in ctx_vars:
            calls += 1
            continue
        problems.append(
            "the cite step has a line outside its allowed shape: {0!r} -- "
            "its only read is `board_triage.py find-cited-run` with the "
            "context-file variable as the sole file operand".format(line))
    if calls != 1:
        problems.append("the cite step must call `board_triage.py "
                        "find-cited-run` on its context-file variable exactly "
                        "once (found {0})".format(calls))

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
    if not DECIDE_KEY_RE.search(_code_lines(decide.get("run"))):
        problems.append("the decide step never sets the issue's "
                        '"cited_run_workflow_path" key from WORKFLOW_PATH')
    fetch = steps[by_id["fetch"]] if "fetch" in by_id else {}
    if "workflow-path=" not in str(fetch.get("run") or ""):
        problems.append("the fetch step never emits workflow-path")
    return problems


_UNFILTERED_READ = ('          gh api "repos/$GITHUB_REPOSITORY/issues/'
                    '$ISSUE_NUMBER/comments" --paginate --jq \'.[].body\' '
                    '>> "$ISSUE_CONTEXT_FILE"\n')
_CITE_RUN_HEAD = ("        run: |\n          set -uo pipefail\n"
                  "          run_url=\"$(python3 .github/scripts/"
                  "board_triage.py find-cited-run")
_CITE_OPERAND = '--repository "$GITHUB_REPOSITORY" "$ISSUE_CONTEXT_FILE" || true)"'
_CITE_STEP = "      - name: Locate a cited run, if any\n"
_ENV_STAGED_READ = (
    "      - name: Stage extra context\n"
    "        env:\n"
    "          GH_TOKEN: ${{ env.WC_BOT_TOKEN }}\n"
    "          URL: repos/${{ github.repository }}/issues/"
    "${{ needs.select.outputs.issue-number }}/comments\n"
    "        run: |\n"
    "          gh api \"$URL\" --jq '.[].body' > \"$RUNNER_TEMP/extra.txt\"\n\n")

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
    ("an earlier step stages a comments URL in env: and fetches it",
     _CITE_STEP, _ENV_STAGED_READ + _CITE_STEP),
    ("cite scans a second file beside the context-file",
     _CITE_OPERAND,
     '--repository "$GITHUB_REPOSITORY" "$ISSUE_CONTEXT_FILE" '
     '"$RUNNER_TEMP/extra.txt" || true)"'),
    ("cite also greps a second file",
     _CITE_RUN_HEAD,
     _CITE_RUN_HEAD.replace(
         "set -uo pipefail\n",
         "set -uo pipefail\n          grep -oE 'actions/runs/[0-9]+' "
         "\"$RUNNER_TEMP/extra.txt\" >> \"$GITHUB_OUTPUT\"\n")),
    ("cite bypasses find_cited_run with a raw grep of the context-file",
     'run_url="$(python3 .github/scripts/board_triage.py find-cited-run '
     + _CITE_OPERAND,
     'run_url="$(grep -oE "https://github\\\\.com/${GITHUB_REPOSITORY}/'
     'actions/runs/[0-9]+" "$ISSUE_CONTEXT_FILE" | head -1 || true)"'),
    ("evidence fetch reads a run the cite step did not choose",
     "RUN_ID: ${{ steps.cite.outputs.run-id }}",
     "RUN_ID: ${{ steps.other.outputs.run-id }}"),
    ("decide drops the cited workflow path",
     "          WORKFLOW_PATH: ${{ steps.fetch.outputs.workflow-path }}\n",
     ""),
    ("decide names the key only in a comment",
     '              "cited_run_workflow_path": os.environ.get("WORKFLOW_PATH") or None,\n',
     '              # "cited_run_workflow_path" deliberately omitted\n'),
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


# ---------------------------------------------------------------------------
# Check 3 -- find_cited_run() ignores quoted/fenced links and prefers the
# watchdog's own "First seen" run (#505 review).
# ---------------------------------------------------------------------------

_REPO = "example/example"
_RUN = "https://github.com/example/example/actions/runs/"
_ISSUE_HEAD = "## Issue\n\nTitle\n\n"
FIND_CITED_RUN_CASES = (
    ("a plain body link is still cited",
     _ISSUE_HEAD + "Broke in {0}11 today.\n".format(_RUN), _RUN + "11"),
    ("a >-quoted link in a trusted comment is ignored",
     _ISSUE_HEAD + "No run here.\n\n## Comment by @owner (t)\n\n"
     "> see {0}22\n\nI disagree.\n".format(_RUN), None),
    ("a nested/indented quote is ignored",
     _ISSUE_HEAD + "  >> {0}22\n".format(_RUN), None),
    ("a fenced link is ignored",
     _ISSUE_HEAD + "```\n{0}33\n```\n".format(_RUN), None),
    ("a ~~~ fence and a longer closing fence are handled",
     _ISSUE_HEAD + "~~~~\n{0}33\n~~~~~\nafter {0}34\n".format(_RUN), _RUN + "34"),
    ("an unclosed fence hides the rest",
     _ISSUE_HEAD + "```text\n{0}35\n".format(_RUN), None),
    ("a quoted link does not shadow a later plain one",
     _ISSUE_HEAD + "> {0}22\n\nReal cite: {0}44\n".format(_RUN), _RUN + "44"),
    ("the watchdog's First seen run wins over an earlier link",
     _ISSUE_HEAD + "Evidence: {0}55\n\n_First seen: [this run]({0}66)_\n"
     .format(_RUN), _RUN + "66"),
    ("a quoted First seen marker does not win",
     _ISSUE_HEAD + "Cite {0}77\n\n> _First seen: [this run]({0}88)_\n"
     .format(_RUN), _RUN + "77"),
    ("another repository's run is never cited",
     _ISSUE_HEAD + "https://github.com/other/repo/actions/runs/99\n", None),
    ("a /job/ suffix still yields the run URL",
     _ISSUE_HEAD + "{0}12/job/34\n".format(_RUN), _RUN + "12"),
)


def run_find_cited_run_cases(verbose=True):
    failures = []
    for label, text, expected in FIND_CITED_RUN_CASES:
        got = board_triage.find_cited_run(text, _REPO)
        if got != expected:
            failures.append("find_cited_run: {0}: expected {1!r}, got {2!r}"
                            .format(label, expected, got))
        elif verbose:
            print("[ok] find_cited_run: {0} ({1!r})".format(label, got))
    return failures


def _mutation_check_find_cited_run():
    failures = []
    mutations = (
        ("quote/fence stripping removed", "_unquoted_unfenced",
         lambda text: text),
    )
    for label, name, replacement in mutations:
        original = getattr(board_triage, name)
        setattr(board_triage, name, replacement)
        try:
            caught = bool(run_find_cited_run_cases(verbose=False))
        finally:
            setattr(board_triage, name, original)
        if caught:
            print("note: mutation caught ({0}).".format(label))
        else:
            failures.append("mutation {0!r} was NOT caught".format(label))
    # First-seen preference dropped: only the plain first-link search left.
    original = board_triage.find_cited_run

    def first_link_only(text, repository):
        m = re.search(r"https://github\.com/{0}/actions/runs/[0-9]+".format(
            re.escape(repository)), board_triage._unquoted_unfenced(text))
        return m.group(0) if m else None

    board_triage.find_cited_run = first_link_only
    try:
        caught = bool(run_find_cited_run_cases(verbose=False))
    finally:
        board_triage.find_cited_run = original
    if caught:
        print("note: mutation caught (First seen preference dropped).")
    else:
        failures.append("mutation 'First seen preference dropped' was NOT caught")
    return failures


def run():
    failures = run_fixtures()

    problems = _mutation_check_rate_limit_guard()
    problems.extend(run_find_cited_run_cases())
    problems.extend(_mutation_check_find_cited_run())

    problems.extend(run_scoping_cases())
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
