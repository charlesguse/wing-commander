#!/usr/bin/env python3
"""Gate — board_prove.py's actions_only() resolves every documented branch
correctly (specs/057-autonomous-board-loop, contracts/prove-step.md,
research.md D15), and specs/060-self-redrive-concurrency's directed-proof-run
mechanism (directed_stage(), joins_directed_group(),
directed_proof_group_busy(), scan_job_uses_graph()) resolves every
documented branch correctly too (FR-020/FR-021).
"""
import glob
import json
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_prove import (  # noqa: E402
    SCRIPT_PATH_RE, WORKFLOW_REF_RE,
    _close_script_imports, _resolve_script_imports, actions_only,
    aimable_jobs, directed_proof_group_busy, directed_stage,
    is_safe_redrive_target, joins_directed_group, outcome_reason,
    read_job_concurrency_group, redrive_target,
    scan_dispatchable_and_uses_graph, scan_job_uses_graph,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")
REPO_BOARD_LOOP = os.path.join(REPO_WORKFLOWS_DIR, "board-loop.yml")

CASES = [
    (["docs/setup.md", "specs/999-example-feature/spec.md"], False),
    ([".github/scripts/verify-board-triage.py"], False),
    ([".github/workflows/board-loop.yml"], True),
    ([".github/scripts/board_triage.py"], True),
    (["docs/setup.md", ".github/workflows/board-loop.yml"], True),
]

# is_safe_redrive_target(): a candidate missing attempt-token correlation
# support, or carrying another required input the composite has no way to
# supply, must never be offered to redrive_target() -- the composite could
# dispatch it but never observe the result, or gh would reject the
# dispatch outright.
SAFE_TARGET_CASES = [
    ("run-name: 'release ${{ inputs.attempt-token }}'\non:\n  workflow_dispatch:\n"
     "    inputs:\n      attempt-token:\n        required: true\n",
     {"attempt-token": {"required": True}}, True),
    ("name: plan\non:\n  workflow_dispatch: {}\n", {}, False),
    ("run-name: 'release ${{ inputs.attempt-token }}'\non:\n  workflow_dispatch:\n"
     "    inputs:\n      attempt-token:\n        required: true\n"
     "      version:\n        required: true\n",
     {"attempt-token": {"required": True}, "version": {"required": True}}, False),
    ("run-name: 'release ${{ inputs.attempt-token }}'\non:\n  workflow_dispatch:\n"
     "    inputs:\n      attempt-token:\n        required: true\n"
     "      breaking:\n        required: false\n",
     {"attempt-token": {"required": True}, "breaking": {"required": False}}, True),
]

# contracts/prove-step.md "Re-drive": which workflow proves the change.
# The wrapper/stage split is this repository's own shape -- a published
# stage carries workflow_call only, so only its wrapper can be dispatched.
DISPATCHABLE = [
    ".github/workflows/board-loop.yml",
    ".github/workflows/wing-commander-watchdog-test.yml",
]
USES_GRAPH = {
    ".github/workflows/board-loop.yml": [
        ".github/actions/wing-commander-dispatch-and-wait/action.yml",
    ],
    ".github/workflows/wing-commander-watchdog-test.yml": [
        ".github/workflows/watchdog.yml",
    ],
}

REDRIVE_CASES = [
    # 1. a changed workflow that dispatches itself is its own wrapper
    ([".github/workflows/board-loop.yml"], "board-loop.yml"),
    # 2. a workflow_call-only stage is reached through its wrapper
    ([".github/workflows/watchdog.yml"], "wing-commander-watchdog-test.yml"),
    # 2. a composite is reached through the workflow that uses it
    ([".github/actions/wing-commander-dispatch-and-wait/action.yml"],
     "board-loop.yml"),
    # 3. nothing dispatchable reaches it -- say so, never dispatch a
    #    workflow that would prove something else
    ([".github/actions/wing-commander-unreferenced/action.yml"], None),
]

# specs/060-self-redrive-concurrency research.md D1/D2: directed_stage()'s
# own job-uses-graph -- one aimable job per changed helper, plus a tied
# helper (board_item_marker.py) both review and readiness reference.
JOB_USES_GRAPH = {
    "triage": ["board_triage.py"],
    "review": ["board_reviewer.py", "board_item_marker.py"],
    "readiness": ["board_readiness.py", "board_item_marker.py"],
    "prove": ["board_prove.py"],
}

DIRECTED_STAGE_CASES = [
    (["board_triage.py"], "triage"),
    (["board_reviewer.py"], "review"),
    (["board_readiness.py"], "readiness"),
    (["board_prove.py"], "prove"),
    ([".github/scripts/board_unrelated_helper.py"], None),
    # tie-break: board_item_marker.py is referenced by both review and
    # readiness -- pipeline order, latest-stage-wins, so readiness wins.
    (["board_item_marker.py"], "readiness"),
]

# research.md D4/FR-001: self-target (board-loop.yml, an aimable job) is
# true by construction; an external target's own concurrency: group is read
# off the tree and compared against both wing-commander-board-loop* groups.
JOINS_DIRECTED_GROUP_CASES = [
    (REPO_BOARD_LOOP, "prove", True),
    (REPO_BOARD_LOOP, "readiness", True),
]

# research.md D3/D4 (T024): the directed pair's own concurrency.group:
# expression is load-bearing -- an expression that merely *differs* from the
# ordinary jobs' can still resolve to wing-commander-board-loop on both
# branches (or resolve the arms the wrong way round), which reintroduces the
# deadlock silently. Pin it byte-for-byte, normalized only for the folded
# scalar's own line breaks, so any such edit fails loudly here.
#
# specs/096-durable-prove-entry FR-004/FR-005 (contracts/
# prove-path-concurrency.md) inserted a third, per-merged-PR branch between
# the directed branch and the ordinary fallback, so prove-gate/prove's own
# `pull_request` trigger no longer shares the `wing-commander-board-loop`
# group with select/triage/route/fix/review/readiness either -- Gate 137
# (verify-prove-path-concurrency.py) asserts that half; this constant only
# needed its own literal updated to match.
DIRECTED_GROUP_EXPR = (
    "${{ (github.event_name == 'workflow_dispatch' && inputs.directed-stage != '') && "
    "'wing-commander-board-loop-directed-proof' || "
    "(github.event_name == 'pull_request' && format('wing-commander-board-loop-prove-{0}', "
    "github.event.pull_request.number)) || 'wing-commander-board-loop' }}"
)

# research.md D5/T045/T046/T049 (both directions, FR-020):
SCRIPT_IMPORT_CASES = [
    # positive: the sys.path.insert(0, ".github/scripts") + `from X import
    # Y` idiom resolves.
    ("sys.path.insert idiom",
     "run: |\n  sys.path.insert(0, \".github/scripts\")\n  from board_triage import triage\n",
     {".github/scripts/board_triage.py"}),
    # positive: the Gate 98 pristine-snapshot idiom (#583) fix/review/
    # readiness load helpers through resolves exactly like the working-tree
    # idiom above -- otherwise a board_*.py helper only ever imported this
    # way (e.g. board_readiness.py) resolves to no job at all (T048).
    ("pristine-snapshot sys.path.insert idiom",
     "run: |\n  sys.path.insert(0, os.path.join(os.environ[\"RUNNER_TEMP\"], "
     "\"wc-pristine\", \"scripts\"))\n  from board_readiness import evaluate_from_snapshot\n",
     {".github/scripts/board_readiness.py"}),
    # positive: a bare script path (no import idiom at all) resolves.
    ("bare script path",
     "run: python3 .github/scripts/board_stand_down.py\n",
     {".github/scripts/board_stand_down.py"}),
    # negative: a module name mentioned in prose, outside both the import
    # idiom and a real script path, resolves to nothing.
    ("bare module name outside the idiom, negative case",
     "run: echo \"the board_triage module handles triage\"\n",
     set()),
]

TRANSITIVE_SCRIPT_IMPORT_CASE = (
    # a helper-imports-helper chain (T046): job loads A directly; A imports
    # B; B imports C. The closure over all three is what a job's own
    # referenced set gets.
    {"a.py"},
    {"a.py": {"b.py"}, "b.py": {"c.py"}, "c.py": set()},
    {"a.py", "b.py", "c.py"},
)

DIRECTED_PROOF_GROUP_BUSY_CASES = [
    ("[]", None, False),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop [directed:prove]", "status": "in_progress"}]), None, True),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop [directed:prove]", "status": "completed"}]), None, False),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop", "status": "in_progress"}]), None, False),
    # PR #490 review, 2026-09-28: a directed run must not see its own
    # in-progress `[directed:]` row and report the group busy against
    # itself -- own_run_id excludes exactly that row.
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop [directed:prove]", "status": "in_progress"}]), 1, False),
    (json.dumps([{"databaseId": 1, "displayTitle": "board-loop [directed:prove]", "status": "in_progress"},
                 {"databaseId": 2, "displayTitle": "board-loop [directed:review]", "status": "in_progress"}]), 1, True),
]

# contracts/proof-outcome-taxonomy.md's eight-reason table (research.md D6):
# (group_busy, redrive_workflow, directed_stage_value, conclusion,
#  disambiguated_reason) -> expected outcome_reason.
OUTCOME_REASON_CASES = [
    ("group-busy", (True, "board-loop.yml", "prove", None, None), "group-busy"),
    ("nothing-reaches", (False, None, None, None, None), "nothing-reaches"),
    ("no-target", (False, "board-loop.yml", None, None, None), "no-target"),
    ("not-started", (False, "board-loop.yml", "prove", "timeout", "not-started"), "not-started"),
    ("unfinished", (False, "board-loop.yml", "prove", "timeout", "unfinished"), "unfinished"),
    ("displaced", (False, "board-loop.yml", "prove", None, "displaced"), "displaced"),
    ("uncorrelated", (False, "board-loop.yml", "prove", None, "uncorrelated"), "uncorrelated"),
    ("success", (False, "board-loop.yml", "prove", "success", None), "success"),
    ("failure", (False, "board-loop.yml", "prove", "failure", None), "failure"),
    # an external target (FR-004): no-target's board-loop.yml-only check
    # never applies, so a directed_stage_value of None does not misfire.
    ("external target success", (False, "release.yml", None, "success", None), "success"),
]


import ast  # noqa: E402
import shutil  # noqa: E402
import warnings  # noqa: E402

from board_prove import Exemption  # noqa: E402

# specs/124-merge-proof-list research D2/D6: the reach computation and the
# need-a-run rule have one home, board_prove.py; the other helpers the proof
# list reuses keep theirs. NAME -> the one file allowed to define it.
SINGLE_HOME_NAMES = {
    "actions_only": ".github/scripts/board_prove.py",
    "reach": ".github/scripts/board_prove.py",
    "mention_edges": ".github/scripts/board_prove.py",
    "reaching_workflows": ".github/scripts/board_prove.py",
    "workflow_triggers": ".github/scripts/board_prove.py",
    "runs_of_its_own": ".github/scripts/board_prove.py",
    "nightly_e2e_edges": ".github/scripts/board_prove.py",
    "diff_name_list": ".github/scripts/board_route_backstop.py",
    "pr_issue": ".github/scripts/board_backlog_lines.py",
    "pr_line": ".github/scripts/board_backlog_lines.py",
    "utf16_len": ".github/scripts/board_spec_request_body.py",
}
# The two consumers of the reach computation.
REACH_CONSUMERS = (
    ".claude/skills/prove-after-merge/scripts/redrive_candidates.py",
    ".github/scripts/wc_proof_list.py",
)
CONSUMER_IMPORTS = ("reaching_workflows", "actions_only")
FILE_WALKERS = frozenset({"listdir", "walk", "scandir", "glob", "iglob", "rglob"})

# A file here is excused from the single-home check until its maintainer
# commit thins it (spec 124 T028); an entry whose file breaks nothing is stale.
# Gate 124 reads this table, so it is only ever written as this literal.
EXEMPT_REACH_COPIES = {}


def _py_files(root):
    """The repository's own .py files under .github/ and .claude/, outside
    fixtures. Listed through wc_repo_files.repo_files (git's tracked files,
    the one home for this), so the untracked worktrees a local checkout keeps
    under the ignored .claude/worktrees/ are never read as copies."""
    from wc_repo_files import repo_files
    for rel in repo_files(root):
        parts = rel.split("/")
        if parts[0] in (".github", ".claude") and rel.endswith(".py") and "fixtures" not in parts[:-1]:
            yield rel


def _parse(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return ast.parse(fh.read())
    except (OSError, SyntaxError):
        return None


def _name_breaks(tree, rel):
    return sorted(
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in SINGLE_HOME_NAMES
        and SINGLE_HOME_NAMES[node.name] != rel)


def _consumer_breaks(tree):
    imported = set()
    walks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "board_prove":
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in FILE_WALKERS:
                walks.append(name)
    out = ["does not import {0} from board_prove".format(n)
           for n in CONSUMER_IMPORTS if n not in imported]
    out += ["lists or walks files itself ({0}())".format(n) for n in sorted(set(walks))]
    return out


def check_single_home(root, exempt):
    """specs/124 research D2: failures for a copy of the reach computation.
    `exempt` is {relpath: Exemption} (passed in, never written here)."""
    failures = []
    for rel in sorted(_py_files(root)):
        tree = _parse(root, rel)
        if tree is None:
            continue
        broken = _name_breaks(tree, rel)
        if rel in REACH_CONSUMERS:
            broken += _consumer_breaks(tree)
        if broken and rel not in exempt:
            failures.append("{0}: carries its own copy of the shared logic ({1}); it has one "
                            "home, board_prove.py (CLAUDE.md single home).".format(rel, "; ".join(broken)))
        elif not broken and rel in exempt:
            failures.append("{0}: its EXEMPT_REACH_COPIES entry is stale -- the file no longer "
                            "breaks the single-home rule; delete the entry.".format(rel))
    for rel in sorted(exempt):
        if not os.path.isfile(os.path.join(root, rel)):
            failures.append("{0}: EXEMPT_REACH_COPIES names a file that does not exist; "
                            "delete the entry.".format(rel))
    return failures


_COPY_REACH = "def reach(workflow, uses_graph):\n    return set()\n"
_COPY_ACTIONS = "def actions_only(paths):\n    return False, ''\n"
_THIN = ("from board_prove import actions_only, reaching_workflows\n"
         "def main():\n    return reaching_workflows([], {}), actions_only([])\n")
_INLINE = _THIN + "import os\ndef main2():\n    return os.listdir('.github/workflows')\n"
SKILL = REACH_CONSUMERS[0]


def single_home_fixture_cases():
    """Each case fails without the code it tests; returns problem strings.
    The cases with an entry pass their own table, never EXEMPT_REACH_COPIES:
    the maintainer commit that deletes the live entry (T028) must not turn
    these red (plan.md "Build details")."""
    own_entry = {SKILL: Exemption(reason="fixture: the unthinned consumer", issue=(889,))}
    cases = [
        ("a copy of reach in another file", {".github/scripts/b.py": _COPY_REACH}, {}, True),
        ("a copy of actions_only", {".github/scripts/b.py": _COPY_ACTIONS}, {}, True),
        ("the home itself defining them", {".github/scripts/board_prove.py":
                                           _COPY_REACH + _COPY_ACTIONS}, {}, False),
        ("a thinned consumer, no exemption", {SKILL: _THIN}, {}, False),
        ("an inline mention loop left in the consumer", {SKILL: _INLINE}, {}, True),
        ("the unthinned consumer passes only with its entry", {SKILL: _COPY_REACH},
         own_entry, False),
        ("the unthinned consumer without its entry", {SKILL: _COPY_REACH}, {}, True),
        ("a stale entry for a thinned consumer", {SKILL: _THIN}, own_entry, True),
        ("an entry for a missing file", {}, own_entry, True),
    ]
    problems = []
    for label, files, exempt, want_fail in cases:
        root = tempfile.mkdtemp(prefix="verify_board_prove_home_")
        try:
            for rel, text in files.items():
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            os.makedirs(os.path.join(root, ".github"), exist_ok=True)
            got = bool(check_single_home(root, exempt))
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if got != want_fail:
            problems.append("single-home fixture {0!r}: failed={1}, expected {2}".format(
                label, got, want_fail))
        else:
            print("[ok] single-home fixture: {0}".format(label))
    return problems



def worktree_copy_fixture_cases():
    """R11: a checkout with a git worktree under the ignored .claude/worktrees/
    holds an untracked copy of board_prove.py; it must not be reported, while
    a tracked copy elsewhere still is."""
    import subprocess
    problems = []
    for label, tracked_copy, want_fail in (
            ("an untracked copy inside an ignored worktree directory", False, False),
            ("a tracked copy in another file", True, True)):
        root = tempfile.mkdtemp(prefix="verify_board_prove_wt_")
        try:
            files = {".gitignore": ".claude/worktrees/\n",
                     ".github/scripts/board_prove.py": _COPY_REACH,
                     ".claude/worktrees/wt/.github/scripts/board_prove.py": _COPY_REACH}
            if tracked_copy:
                files[".github/scripts/b.py"] = _COPY_REACH
            for rel, text in files.items():
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
            for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "c"]):
                subprocess.run(git + args, cwd=root, check=True, capture_output=True)
            got = check_single_home(root, {})
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if bool(got) != want_fail:
            problems.append("worktree fixture {0!r}: {1}".format(label, got or "did not fail"))
    return problems


def check_nightly_edges(root):
    """-> (problems, wrappers): nightly_e2e_edges() on `root`'s tree reads at
    least one wrapper and every wrapper it names exists. No fixed count: the
    array is the source, so adding or removing a stage wrapper is not a
    failure (round-4 finding 9)."""
    import board_prove
    try:
        wrappers = board_prove.nightly_e2e_edges(root).get(board_prove.AUTO_RELEASE) or []
    except ValueError as exc:
        return ["nightly_e2e_edges() failed on {0}: {1}".format(root, exc)], []
    missing = [w for w in wrappers if not os.path.isfile(os.path.join(root, w))]
    if not wrappers or missing:
        return ["nightly_e2e_edges() read {0}; expected at least one wrapper, each an existing "
                "file (missing: {1})".format(wrappers, missing)], wrappers
    return [], wrappers


def nightly_edges_fixture_cases():
    """check_nightly_edges on small trees: two wrappers pass; a named wrapper
    that does not exist, and an array that cannot be parsed, fail."""
    array = ("jobs:\n  j:\n    steps:\n      - run: |\n          declare -A stage_file=(\n"
             "            [wing-commander-1-a.yml]=a.yml\n            [wing-commander-2-b.yml]=b.yml\n"
             "          )\n")
    wrappers = {".github/workflows/wing-commander-1-a.yml": "on: {}\n",
                ".github/workflows/wing-commander-2-b.yml": "on: {}\n"}
    cases = [
        ("two wrappers, both present", dict(wrappers), False),
        ("a named wrapper that does not exist",
         {".github/workflows/wing-commander-1-a.yml": "on: {}\n"}, True),
        ("an array that cannot be parsed", None, True),
    ]
    problems = []
    for label, files, want_fail in cases:
        root = tempfile.mkdtemp(prefix="verify_board_prove_nightly_")
        try:
            text = array if files is not None else "jobs: {}\n"
            for rel, body in dict(files or {}, **{".github/workflows/auto-release.yml": text}).items():
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(body)
            got = bool(check_nightly_edges(root)[0])
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if got != want_fail:
            problems.append("nightly-edges fixture {0!r}: failed={1}, expected {2}".format(label, got, want_fail))
    return problems


from board_prove import fixtures_name_no_live_table  # noqa: E402,F401  (single home)


def run():
    failures = 0
    for changed_paths, expected in CASES:
        got, reason = actions_only(changed_paths)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: {0}: expected actions_only={1}, "
                  "got {2} ({3}).".format(changed_paths, expected, got, reason))
        else:
            print("[ok] {0}: actions_only={1} ({2})".format(changed_paths, got, reason))

    for changed_paths, expected in REDRIVE_CASES:
        got, reason = redrive_target(changed_paths, DISPATCHABLE, USES_GRAPH)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: {0}: expected redrive target "
                  "{1}, got {2} ({3}).".format(changed_paths, expected, got, reason))
        else:
            print("[ok] {0}: redrive={1} ({2})".format(changed_paths, got, reason))

    for workflow_text, inputs, expected in SAFE_TARGET_CASES:
        got = is_safe_redrive_target(workflow_text, inputs)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: is_safe_redrive_target({0!r}, {1!r}): "
                  "expected {2}, got {3}.".format(workflow_text, inputs, expected, got))
        else:
            print("[ok] is_safe_redrive_target(...): {0}".format(got))

    # #1161: a literal path mention is a whole path, never a substring of
    # a longer one (`.yml.bak`, `.pyc`, an `x`-prefixed `.github` root).
    mention_cases = [
        (WORKFLOW_REF_RE, "uses .github/workflows/a.yml.bak", []),
        (WORKFLOW_REF_RE, "uses x.github/workflows/a.yml", []),
        (WORKFLOW_REF_RE, "see ./.github/workflows/a.yml.", [".github/workflows/a.yml"]),
        (WORKFLOW_REF_RE, "'.github/workflows/a.yml'", [".github/workflows/a.yml"]),
        (SCRIPT_PATH_RE, "python3 .github/scripts/foo.pyc", []),
        (SCRIPT_PATH_RE, "python3 .github/scripts/foo.py.bak", []),
        (SCRIPT_PATH_RE, "python3 .github/scripts/foo.py", [(".github/scripts/foo.py")]),
    ]
    for regex, text, expected in mention_cases:
        got = [m.group(0) if regex is WORKFLOW_REF_RE else
               ".github/scripts/{0}.py".format(m.group(1) or m.group(2) or m.group(3))
               for m in regex.finditer(text)]
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: mention scan of {0!r}: expected "
                  "{1}, got {2}.".format(text, expected, got))
        else:
            print("[ok] mention scan of {0!r} = {1}".format(text, got))

    for changed_paths, expected in DIRECTED_STAGE_CASES:
        got = directed_stage(changed_paths, JOB_USES_GRAPH, aimable_jobs)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: directed_stage({0}): expected "
                  "{1}, got {2}.".format(changed_paths, expected, got))
        else:
            print("[ok] directed_stage({0}) = {1}".format(changed_paths, got))

    for target_workflow, target_job, expected in JOINS_DIRECTED_GROUP_CASES:
        got = joins_directed_group(target_workflow, target_job, aimable_jobs)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: joins_directed_group({0}, {1}): "
                  "expected {2}, got {3}.".format(target_workflow, target_job, expected, got))
        else:
            print("[ok] joins_directed_group({0}, {1}) = {2}".format(target_workflow, target_job, got))

    # External-target cases (FR-004/FR-001): a workflow sharing this
    # repository's own board-loop group must read as joining it (False);
    # one with a genuinely distinct group must read as not joining (True).
    # release.yml is a real, checked-in workflow with its own distinct
    # group (wing-commander-release) -- an integration case, not only a
    # synthetic fixture, same discipline as the real-tree check below.
    release_yml = os.path.join(REPO_WORKFLOWS_DIR, "release.yml")
    got = joins_directed_group(release_yml, "release", aimable_jobs)
    if got is not True:
        failures += 1
        print("::error::verify-board-prove: joins_directed_group(release.yml, ...): "
              "expected True (distinct group), got {0}.".format(got))
    else:
        print("[ok] joins_directed_group(release.yml, ...) = True (distinct group)")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as fh:
        fh.write("on: workflow_dispatch\nconcurrency:\n  group: wing-commander-board-loop\n"
                  "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps: []\n")
        shared_group_path = fh.name
    try:
        got = joins_directed_group(shared_group_path, "x", aimable_jobs)
        if got is not False:
            failures += 1
            print("::error::verify-board-prove: joins_directed_group(shared group fixture): "
                  "expected False, got {0}.".format(got))
        else:
            print("[ok] joins_directed_group(shared group fixture) = False")
    finally:
        os.unlink(shared_group_path)

    # specs/096-durable-prove-entry research.md D8: read_job_concurrency_group()
    # extracted from joins_directed_group()'s own inline tree-read above --
    # a job-level (not workflow-level) concurrency.group: read, against a
    # fixture board-loop.yml.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as fh:
        fh.write(
            "on: pull_request\n"
            "jobs:\n"
            "  prove-gate:\n"
            "    runs-on: ubuntu-latest\n"
            "    concurrency:\n"
            "      group: example-prove-group\n"
            "    steps: []\n"
            "  no-group-job:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps: []\n"
        )
        read_job_group_fixture_path = fh.name
    try:
        got = read_job_concurrency_group(read_job_group_fixture_path, "prove-gate")
        if got != "example-prove-group":
            failures += 1
            print("::error::verify-board-prove: read_job_concurrency_group(fixture, prove-gate): "
                  "expected 'example-prove-group', got {0!r}.".format(got))
        else:
            print("[ok] read_job_concurrency_group(fixture, prove-gate) = 'example-prove-group'")

        got = read_job_concurrency_group(read_job_group_fixture_path, "no-group-job")
        if got != "":
            failures += 1
            print("::error::verify-board-prove: read_job_concurrency_group(fixture, no-group-job): "
                  "expected '', got {0!r}.".format(got))
        else:
            print("[ok] read_job_concurrency_group(fixture, no-group-job) = ''")

        got = read_job_concurrency_group(read_job_group_fixture_path, "does-not-exist")
        if got != "":
            failures += 1
            print("::error::verify-board-prove: read_job_concurrency_group(fixture, does-not-exist): "
                  "expected '', got {0!r}.".format(got))
        else:
            print("[ok] read_job_concurrency_group(fixture, does-not-exist) = ''")
    finally:
        os.unlink(read_job_group_fixture_path)

    for name, text, expected in SCRIPT_IMPORT_CASES:
        got = _resolve_script_imports(text)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: _resolve_script_imports {0}: "
                  "expected {1!r}, got {2!r}.".format(name, expected, got))
        else:
            print("[ok] _resolve_script_imports {0} = {1!r}".format(name, got))

    paths, graph, expected_closure = TRANSITIVE_SCRIPT_IMPORT_CASE
    got_closure = _close_script_imports(paths, graph)
    if got_closure != expected_closure:
        failures += 1
        print("::error::verify-board-prove: _close_script_imports transitive "
              "chain: expected {0!r}, got {1!r}.".format(expected_closure, got_closure))
    else:
        print("[ok] _close_script_imports transitive chain = {0!r}".format(got_closure))

    # T049's composite case, against the real tree: wing-commander-board-
    # stop-check's own action.yml loads board_stop_check.py via the
    # sys.path.insert idiom (T047), and select/triage/review/readiness all
    # `uses:` that composite -- confirm at least one real job resolves it.
    real_job_uses_graph_for_composite = scan_job_uses_graph(".github/workflows/board-loop.yml")
    composite_resolved = any(
        ".github/scripts/board_stop_check.py" in referenced
        for referenced in real_job_uses_graph_for_composite.values()
    )
    if not composite_resolved:
        failures += 1
        print("::error::verify-board-prove: no job in board-loop.yml's own "
              "job-uses-graph resolves board_stop_check.py through "
              "wing-commander-board-stop-check's own action.yml (T047) on "
              "the checked-out tree.")
    else:
        print("[ok] a composite's own action.yml script import "
              "(board_stop_check.py via wing-commander-board-stop-check) "
              "resolves on the checked-out tree")

    for run_list_json, own_run_id, expected in DIRECTED_PROOF_GROUP_BUSY_CASES:
        got = directed_proof_group_busy(run_list_json, own_run_id)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: directed_proof_group_busy({0}, {1}): "
                  "expected {2}, got {3}.".format(run_list_json, own_run_id, expected, got))
        else:
            print("[ok] directed_proof_group_busy({0}, {1}) = {2}".format(run_list_json, own_run_id, got))

    for name, args, expected in OUTCOME_REASON_CASES:
        got = outcome_reason(*args)
        if got != expected:
            failures += 1
            print("::error::verify-board-prove: outcome_reason {0}: expected "
                  "{1!r}, got {2!r}.".format(name, expected, got))
        else:
            print("[ok] outcome_reason {0} = {1!r}".format(name, got))

    # Integration check, not just fixtures: the synthetic DISPATCHABLE/
    # SAFE_TARGET_CASES above can all pass while scan_dispatchable_and_uses_graph()
    # filters every REAL workflow in this repository out to an empty set
    # (this is exactly how the redrive mechanism went dead for every
    # workflow, including board-loop.yml itself, without failing CI --
    # board-loop.yml lacked the run-name/attempt-token wiring
    # is_safe_redrive_target() requires). board-loop.yml is its own
    # documented redrive target (REDRIVE_CASES case 1 above); assert it
    # actually is one on the checked-out tree, not only in a fixture.
    real_dispatchable, _real_uses_graph = scan_dispatchable_and_uses_graph(REPO_WORKFLOWS_DIR)
    real_dispatchable_basenames = {p.rsplit("/", 1)[-1] for p in real_dispatchable}
    if "board-loop.yml" not in real_dispatchable_basenames:
        failures += 1
        print("::error::verify-board-prove: board-loop.yml is not in the real "
              "repository's dispatchable set ({0}) -- the redrive/prove "
              "mechanism cannot re-drive itself, and a merge that changes only "
              "board-loop.yml's own logic can never be proven.".format(sorted(real_dispatchable_basenames)))
    else:
        print("[ok] board-loop.yml is a real, safe redrive target on the checked-out tree")

    # research.md D4: "a future edit narrowing or removing the split fails
    # loudly rather than silently reintroducing the deadlock" -- read the
    # real, checked-out board-loop.yml's own per-job concurrency.group:
    # expressions and assert the directed pair's literally differs from
    # every ordinary job's.
    with open(REPO_BOARD_LOOP, encoding="utf-8") as fh:
        real_board_loop = yaml.safe_load(fh.read())
    real_jobs = real_board_loop.get("jobs") or {}
    directed_groups = {
        job: (real_jobs.get(job) or {}).get("concurrency", {}).get("group")
        for job in ("prove-gate", "prove")
    }
    ordinary_groups = {
        job: (real_jobs.get(job) or {}).get("concurrency", {}).get("group")
        for job in ("select", "triage", "route", "fix", "review", "readiness")
    }
    for job, group in directed_groups.items():
        if not group:
            failures += 1
            print("::error::verify-board-prove: {0}'s own concurrency.group: "
                  "is missing on the checked-out tree.".format(job))
            continue
        clashes = [oj for oj, og in ordinary_groups.items() if og == group]
        if clashes:
            failures += 1
            print("::error::verify-board-prove: {0}'s own concurrency.group: "
                  "expression is byte-identical to {1}'s -- the directed/"
                  "ordinary split (research.md D3) has been narrowed or "
                  "removed.".format(job, clashes))
        else:
            print("[ok] {0}'s own concurrency.group: expression differs from "
                  "every ordinary job's on the checked-out tree".format(job))
        normalized = " ".join(str(group).split())
        if normalized != DIRECTED_GROUP_EXPR:
            failures += 1
            print("::error::verify-board-prove: {0}'s own concurrency.group: "
                  "expression is not the canonical directed-proof split.\n"
                  "  expected: {1}\n  found:    {2}\n"
                  "A group that differs from the ordinary jobs' but still "
                  "resolves to wing-commander-board-loop on its directed "
                  "branch reintroduces the deadlock (research.md D4).".format(
                      job, DIRECTED_GROUP_EXPR, normalized))
        else:
            print("[ok] {0}'s own concurrency.group: expression matches the "
                  "canonical directed-proof split byte-for-byte".format(job))

    # research.md D5/FR-014/FR-021 (T048): every board_*.py helper resolves
    # to at least one stage of board-loop.yml on the checked-out tree --
    # completing T024's real-tree assertion, the same discipline that would
    # have caught the dispatchable-set bug this feature fixes had it
    # existed before PR #451.
    real_job_uses_graph = scan_job_uses_graph(".github/workflows/board-loop.yml")
    all_referenced = set()
    for referenced in real_job_uses_graph.values():
        all_referenced.update(referenced)
    real_helpers = sorted(
        p.replace(os.sep, "/") for p in glob.glob(os.path.join(REPO_ROOT, ".github", "scripts", "board_*.py")))
    unreachable_helpers = []
    for helper in real_helpers:
        rel = ".github/scripts/" + os.path.basename(helper)
        if rel not in all_referenced:
            unreachable_helpers.append(rel)
    if unreachable_helpers:
        failures += 1
        print("::error::verify-board-prove: {0} resolve(s) to no job in "
              "board-loop.yml's own job-uses-graph on the checked-out tree "
              "-- FR-014 requires every board_*.py helper reach at least "
              "one stage.".format(unreachable_helpers))
    else:
        print("[ok] every .github/scripts/board_*.py helper ({0}) resolves "
              "to at least one job in board-loop.yml's own job-uses-graph "
              "on the checked-out tree".format(len(real_helpers)))

    for problem in (single_home_fixture_cases() + fixtures_name_no_live_table(single_home_fixture_cases)
                    + worktree_copy_fixture_cases()):
        failures += 1
        print("::error::verify-board-prove: {0}".format(problem))
    for problem in check_single_home(REPO_ROOT, EXEMPT_REACH_COPIES):
        failures += 1
        print("::error::verify-board-prove: {0}".format(problem))
    print("[ok] the reach computation has one home (board_prove.py)")

    import board_prove  # noqa: E402
    problems, wrappers = check_nightly_edges(REPO_ROOT)
    problems += nightly_edges_fixture_cases()
    for problem in problems:
        failures += 1
        print("::error::verify-board-prove: {0}".format(problem))
    if not problems:
        print("[ok] nightly_e2e_edges() reads the {0} wrapper files of auto-release.yml".format(len(wrappers)))
    graph = {"a.yml": ["b.yml"], "b.yml": [".github/x.sh"]}
    if board_prove.reach("a.yml", graph) != {"a.yml", "b.yml", ".github/x.sh"}:
        failures += 1
        print("::error::verify-board-prove: reach() did not close transitively.")
    if board_prove.runs_of_its_own(os.path.join(REPO_WORKFLOWS_DIR, "implement.yml")):
        failures += 1
        print("::error::verify-board-prove: implement.yml (workflow_call only) reported runs of its own.")

    print("verify-board-prove: {0} failure(s).".format(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
