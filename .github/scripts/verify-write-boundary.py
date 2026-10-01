#!/usr/bin/env python3
"""Gate 133 — the implement stage's write boundary is stated, classified,
and routed consistently (specs/090-stage-write-boundary,
contracts/write-boundary-gate.md).

WHY THIS EXISTS
----------------
Before this feature, implement.yml granted its agent an unscoped Write/Edit
and stated no path it may not touch, so a task naming a path like
`.claude/skills/spec-cross-reference/SKILL.md` (spec 060's T055) was
discovered to be impossible only by being refused mid-cycle -- and because
`/speckit-converge` is append-only and convergence is `unchecked-count ==
0`, it then held the loop open every remaining cycle and evaporated into
finalize.yml's remaining-manual-work prose with no owner. This gate is the
SC-007 backstop: a future edit that disables the boundary check, drops the
routing call, or lets the prompt statement drift from the no-write-paths
input it is supposed to render fails this gate by name, rather than the
next agent run discovering the hard way again.

WHAT THIS CHECKS
----------------
(a) single definition (FR-003); (b) statement fidelity (FR-004/FR-005/
SC-001/SC-007); (c) classification correctness (FR-006/FR-014/FR-015);
(d) termination and reason (FR-010/FR-011/FR-012); (e) no filing on a
truncated run (FR-013); (f) idempotency (FR-008); (g) fingerprint
single-home (research.md D6); (h) board-loop label separation
(research.md D4) -- see contracts/write-boundary-gate.md for the exact
scenario tables. --self-test reintroduces each of the 7 mutations that
contract names and asserts every one is caught.

Usage: python3 .github/scripts/verify-write-boundary.py [--self-test]
Requires: bash, jq, git (all present on ubuntu-latest runners).
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash, run_step,
                              parse_github_output, use_utf8_stdout)

GATE_PREFIX = "Gate 133"
THIS_SCRIPT = ".github/scripts/verify-write-boundary.py"
LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"

STAGE = ".github/workflows/implement.yml"
FINALIZE = ".github/workflows/finalize.yml"
TOOL_ARGS_COMPOSITE = ".github/actions/wing-commander-tool-args/action.yml"
WRITE_BOUNDARY_COMPOSITE = ".github/actions/wing-commander-write-boundary/action.yml"
STAGE_FINDINGS_COMPOSITE = ".github/actions/wing-commander-stage-findings/action.yml"
WRITE_BOUNDARY_LOOKUP_COMPOSITE = ".github/actions/wing-commander-write-boundary-lookup/action.yml"
CLASSIFY_SCRIPT = ".github/actions/_shared/classify-out-of-boundary-tasks.sh"
FINGERPRINT_SCRIPT = ".github/actions/_shared/compute-finding-fingerprint.sh"
COUNT_TASKS_CHECKBOXES = ".github/actions/_shared/count-tasks-checkboxes.sh"

COMPOSE_STEP = "Compose tool args"
CLASSIFY_STEP = "Classify unchecked tasks against the write boundary"
CYCLE_STEP = "Read back cycle outcome"
RETRY_STEP = "Read back retry outcome"
ROUTE_STEP = "Route out-of-boundary tasks"
LOOKUP_STEP = "Look up routed write-boundary items"

SPEC_PREFIX = "spec/"
SLUG = "090-fixture"
SPEC_DIR = f"specs/{SLUG}"
ITERATION = "3"
PRIOR_ITERATION = "2"
AGENT_AUTHOR_RE = r"claude\[bot\]|wing-commander-bot\[bot\]"

BASH = None

# The literal quoted no-write-paths default (FR-003) -- pass condition (a)
# greps for this outside its one declared home in STAGE.
DEFAULT_LITERAL = '".claude/"'


def sh(script, cwd):
    """Run a helper snippet through the same bash the steps get (mirrors
    verify-tasks-checkbox-convergence-signal.py's own `sh`)."""
    fd, path = tempfile.mkstemp(suffix=".sh")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script)
        return subprocess.run([BASH, "-e", path.replace("\\", "/")], cwd=cwd,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def write_file(repo, relpath, content):
    path = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def git_commit(repo, message):
    proc = sh(f"""cd '{repo}'
git add -A
git commit -q -m {json.dumps(message)}
""", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::commit {message!r} failed: {proc.stdout}{proc.stderr}")


def git_push(repo, branch):
    proc = sh(f"cd '{repo}' && git push -q origin '{branch}'", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::push of '{branch}' failed: {proc.stdout}{proc.stderr}")


def rev_parse(repo, rev="HEAD"):
    return sh(f"cd '{repo}' && git rev-parse {rev}", repo).stdout.strip()


def _meta(iteration, **extra):
    meta = {"stage": "implement", "iteration": int(iteration), "spec_dir": SPEC_DIR}
    meta.update(extra)
    return json.dumps(meta) + "\n"


def make_workspace(root, base_tasks_md):
    branch = f"{SPEC_PREFIX}{SLUG}"
    work = tempfile.mkdtemp(dir=root)
    remote = os.path.join(work, "remote.git")
    repo = os.path.join(work, "repo")
    setup = f"""
git init --bare -q -b main '{remote}'
git clone -q '{remote}' '{repo}'
cd '{repo}'
git config user.email 'claude[bot]@users.noreply.invalid'
git config user.name 'claude[bot]'
"""
    proc = sh(setup, work)
    if proc.returncode != 0:
        sys.exit(f"::error::harness could not build a git workspace: "
                 f"{proc.stdout}{proc.stderr}")
    write_file(repo, f"{SPEC_DIR}/tasks.md", base_tasks_md)
    write_file(repo, f"{SPEC_DIR}/spec-meta.json", _meta(PRIOR_ITERATION))
    write_file(repo, "README.md", "unrelated\n")
    git_commit(repo, "seed")
    git_push(repo, "main")
    proc = sh(f"cd '{repo}' && git checkout -q -b '{branch}'", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::branching failed: {proc.stdout}{proc.stderr}")
    git_push(repo, branch)
    base_sha = rev_parse(repo)
    return work, repo, base_sha, branch


def build_scenario(root, *, base_tasks_md, tip_tasks_md, advance=True,
                    iteration=ITERATION):
    work, repo, base_sha, branch = make_workspace(root, base_tasks_md)
    if tip_tasks_md != base_tasks_md:
        write_file(repo, f"{SPEC_DIR}/tasks.md", tip_tasks_md)
        git_commit(repo, "implement: tick tasks")
    if advance:
        write_file(repo, f"{SPEC_DIR}/spec-meta.json", _meta(iteration))
        git_commit(repo, "implement: advance lifecycle record")
    git_push(repo, branch)
    return work, repo, base_sha, branch


def build_converge_scenario(root, *, base_tasks_md, tip_tasks_md, iteration=ITERATION):
    """Like build_scenario, but commits the tasks.md change with a
    `converge: ...` subject (PR #836 review, item 2; Gate 133 (d) scenario
    4), simulating /speckit-converge's own append-and-commit convention
    rather than a plain agent edit -- the ONLY thing that sets
    `converge_sha` in the shipped read-back step."""
    work, repo, base_sha, branch = make_workspace(root, base_tasks_md)
    if tip_tasks_md != base_tasks_md:
        write_file(repo, f"{SPEC_DIR}/tasks.md", tip_tasks_md)
        git_commit(repo, "converge: append outstanding out-of-boundary work")
    write_file(repo, f"{SPEC_DIR}/spec-meta.json", _meta(iteration))
    git_commit(repo, "implement: advance lifecycle record")
    git_push(repo, branch)
    return work, repo, base_sha, branch


def checkbox_count_env(repo, ref):
    """Runs the REAL shared script -- see verify-tasks-checkbox-
    convergence-signal.py's identical helper for the parsing rationale."""
    script = os.path.abspath(COUNT_TASKS_CHECKBOXES).replace("\\", "/")
    proc = sh(f"cd '{repo}' && bash '{script}' '{ref}' '{SPEC_DIR}/tasks.md'", repo)
    if proc.returncode != 0:
        sys.exit(f"::error::checkbox_count_env: count-tasks-checkboxes.sh failed "
                 f"against a fixture that should be readable: {proc.stdout}{proc.stderr}")
    lines = proc.stdout.splitlines()
    checked = lines[0].split("=", 1)[1] if lines and "=" in lines[0] else "0"
    unchecked = lines[1].split("=", 1)[1] if len(lines) > 1 and "=" in lines[1] else "0"
    items = ""
    if len(lines) > 2 and "<<" in lines[2]:
        delim = lines[2].split("<<", 1)[1]
        body = []
        for line in lines[3:]:
            if line == delim:
                break
            body.append(line)
        items = "\n".join(body)
    return checked, unchecked, items


READ_SPEC_META = ".github/actions/_shared/read-spec-meta.sh"


def read_spec_meta_env(repo):
    script = os.path.abspath(READ_SPEC_META).replace("\\", "/")
    proc = sh(f"cd '{repo}' && bash '{script}' '{SPEC_PREFIX}' '{SLUG}' '{SPEC_DIR}'", repo)
    kv = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    return {"META_IDENTITY_OK": kv.get("meta_identity_ok", ""),
            "META_STAGE": kv.get("meta_stage", ""),
            "META_ITERATION": kv.get("meta_iteration", "")}


def run_classify(unchecked_items, no_write_paths, tasks_path=f"{SPEC_DIR}/tasks.md",
                  spec_dir=SPEC_DIR):
    """Drives the SHIPPED classify-out-of-boundary-tasks.sh directly
    (contracts/write-boundary-gate.md's Inputs section), never a Python
    re-implementation of the classification rule."""
    script = os.path.abspath(CLASSIFY_SCRIPT).replace("\\", "/")
    proc = subprocess.run([BASH, script, unchecked_items, no_write_paths,
                           tasks_path, spec_dir],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    fd, out_path = tempfile.mkstemp()
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(proc.stdout)
        outputs = parse_github_output(out_path)
    finally:
        os.remove(out_path)
    return proc.returncode, proc.stdout + proc.stderr, outputs


def classify_env(unchecked_items, no_write_paths):
    """(all-unchecked-out-of-boundary, findings-json) for feeding a
    read-back step's env the way write-boundary-cycle/-retry's own outputs
    already would."""
    rc, out, outputs = run_classify(unchecked_items, no_write_paths)
    if rc != 0:
        sys.exit(f"::error::classify_env: classify-out-of-boundary-tasks.sh "
                 f"failed against a fixture that should classify cleanly: {out}")
    return outputs.get("all-unchecked-out-of-boundary", "false"), outputs.get("findings-json", "[]")


def run_cycle_step(steps, repo, base_sha, *, verdict, cycle_result,
                    no_write_paths=".claude/", iteration=ITERATION):
    runner_temp = tempfile.mkdtemp(dir=os.path.dirname(repo))
    checked_base, _, _ = checkbox_count_env(repo, base_sha)
    checked_tip, unchecked_tip, items_tip = checkbox_count_env(
        repo, f"origin/{SPEC_PREFIX}{SLUG}")
    all_oob, findings_json = classify_env(items_tip, no_write_paths)
    env = {"SLUG": SLUG, "SPEC_DIR": SPEC_DIR, "ITERATION": str(iteration),
           "BASE_SHA": base_sha, "CYCLE_RESULT": cycle_result,
           "VERDICT": verdict, "SPEC_PREFIX": SPEC_PREFIX,
           "AGENT_AUTHOR_RE": AGENT_AUTHOR_RE, "DEFAULT_BRANCH": "main",
           "CHECKED_BASE": checked_base, "CHECKED_TIP": checked_tip,
           "UNCHECKED_TIP": unchecked_tip, "REMAINING_TIP": items_tip,
           "WRITE_BOUNDARY_ALL_OOB": all_oob,
           "WRITE_BOUNDARY_FINDINGS_JSON": findings_json}
    env.update(read_spec_meta_env(repo))
    return run_step(BASH, steps[CYCLE_STEP], repo, env, runner_temp)


# ---------------------------------------------------------------------------
# (a) Single definition
# ---------------------------------------------------------------------------

def check_single_definition():
    failures = []
    stage_text = open(STAGE, encoding="utf-8").read()
    count = stage_text.count(DEFAULT_LITERAL)
    if count != 1:
        failures.append(
            f"(a) {STAGE}: expected exactly one literal default "
            f"{DEFAULT_LITERAL} for no-write-paths (FR-003), found {count}.")
    for other in (TOOL_ARGS_COMPOSITE, WRITE_BOUNDARY_COMPOSITE):
        text = open(other, encoding="utf-8").read()
        if DEFAULT_LITERAL in text:
            failures.append(
                f"(a) {other}: contains a second literal {DEFAULT_LITERAL} "
                f"default -- FR-003 requires the one declaration to live "
                f"solely in {STAGE}.")

    doc = yaml.safe_load(stage_text) or {}
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            step_id = (step or {}).get("id")
            if step_id in ("tool-args-cycle", "tool-args-retry"):
                with_block = (step or {}).get("with") or {}
                got = with_block.get("no-write-paths")
                if got != "${{ inputs.no-write-paths }}":
                    failures.append(
                        f"(a) {STAGE}: step id={step_id!r} does not wire "
                        f"no-write-paths from ${{{{ inputs.no-write-paths "
                        f"}}}} (got {got!r}).")
    return failures


# ---------------------------------------------------------------------------
# (b) Statement fidelity
# ---------------------------------------------------------------------------

STATEMENT_FIXTURES = [
    ("", "This run's agent may write any path in the checkout."),
    (".claude/", "This run's agent may not write: .claude/."),
    (".claude/,.git/", "This run's agent may not write: .claude/, .git/."),
]


def run_compose(steps, no_write_paths, runner_temp):
    env = {"STEP_LABEL": "gate133", "DEFAULT_ALLOWED": "Read,Write",
           "DEFAULT_DISALLOWED": "WebFetch", "EXTRA_ALLOWED": "",
           "EXTRA_DISALLOWED": "", "ALLOWED_OVERRIDE": "__unset__",
           "DISALLOWED_OVERRIDE": "__unset__", "NO_WRITE_PATHS": no_write_paths}
    return run_step(BASH, steps[COMPOSE_STEP], runner_temp, env, runner_temp)


def check_statement_fidelity(steps, root):
    failures = []
    for no_write_paths, expected in STATEMENT_FIXTURES:
        workdir = tempfile.mkdtemp(dir=root)
        rc, out, outputs, _ = run_compose(steps, no_write_paths, workdir)
        if rc != 0:
            failures.append(f"(b) compose step exited {rc} for "
                            f"no-write-paths={no_write_paths!r}: {out.strip()}")
            continue
        got = outputs.get("write-paths-statement", "")
        if got != expected:
            failures.append(f"(b) no-write-paths={no_write_paths!r}: expected "
                            f"write-paths-statement={expected!r}, got {got!r}")
    return failures


# ---------------------------------------------------------------------------
# (i) Enforcement parity (PR #836 review, item 3)
# ---------------------------------------------------------------------------

ENFORCEMENT_FIXTURES = [
    ("", []),
    (".claude/", ["Edit(.claude/**)", "Write(.claude/**)"]),
    (".claude/,.git/", ["Edit(.claude/**)", "Write(.claude/**)",
                        "Edit(.git/**)", "Write(.git/**)"]),
]


def check_enforcement_parity(steps, root):
    """The composed disallowed-tools list must enforce the SAME boundary
    write-paths-statement states -- a stated-but-unenforced boundary is the
    same failure as making no statement at all (PR #836 review, item 3;
    FR-004/FR-005, Principle V/IX)."""
    failures = []
    for no_write_paths, expected_denies in ENFORCEMENT_FIXTURES:
        workdir = tempfile.mkdtemp(dir=root)
        rc, out, outputs, _ = run_compose(steps, no_write_paths, workdir)
        if rc != 0:
            failures.append(f"(i) compose step exited {rc} for "
                            f"no-write-paths={no_write_paths!r}: {out.strip()}")
            continue
        disallowed = outputs.get("disallowed-tools", "").split(",")
        for entry in expected_denies:
            if entry not in disallowed:
                failures.append(f"(i) no-write-paths={no_write_paths!r}: "
                                f"expected disallowed-tools to contain "
                                f"{entry!r}, got {outputs.get('disallowed-tools')!r}")
    return failures


# ---------------------------------------------------------------------------
# (c) Classification correctness
# ---------------------------------------------------------------------------

CLASSIFY_FIXTURES = [
    ("single out-of-boundary path",
     "- [ ] T001 edit `.claude/skills/foo/SKILL.md`", ".claude/", 1, "true"),
    ("several paths, one in-reach",
     "- [ ] T002 edit `.claude/skills/foo/SKILL.md` and `.github/workflows/bar.yml`",
     ".claude/", 0, "false"),
    ("no path in text",
     "- [ ] T003 write documentation", ".claude/", 0, "false"),
    ("partial prefix match is not a match",
     "- [ ] T004 edit `.claude-extra/foo`", ".claude/", 0, "false"),
    ("empty boundary never classifies",
     "- [ ] T005 edit `.claude/skills/foo/SKILL.md`", "", 0, "false"),
    # US4/T031: a second no-write-paths entry classifies exactly like the
    # first, with zero changes to the classifier itself.
    ("a second boundary entry (.git/) classifies just like the first",
     "- [ ] T006 edit `.git/hooks/pre-commit`", ".claude/,.git/", 1, "true"),
    # PR #836 review, item 8 / spec.md Edge Cases: a task that would widen
    # the stage's own grants (editing .claude/settings.json's
    # permissions.allow) is exactly the case the boundary exists to deny --
    # dedicated fixture so the outcome is asserted explicitly rather than
    # left to fall out of the prefix comparison by coincidence.
    (".claude/settings.json (the boundary-widening edge case) classifies out-of-boundary",
     "- [ ] T007 grant Edit on `.claude/settings.json`", ".claude/", 1, "true"),
]


def check_classification(root):
    failures = []
    for name, unchecked_items, no_write_paths, expect_count, expect_all in CLASSIFY_FIXTURES:
        rc, out, outputs = run_classify(unchecked_items, no_write_paths)
        if rc != 0:
            failures.append(f"(c) {name}: classify script exited {rc}: {out}")
            continue
        got_count = outputs.get("out-of-boundary-count", "")
        got_all = outputs.get("all-unchecked-out-of-boundary", "")
        if got_count != str(expect_count):
            failures.append(f"(c) {name}: expected out-of-boundary-count="
                            f"{expect_count}, got {got_count!r}")
        if got_all != expect_all:
            failures.append(f"(c) {name}: expected all-unchecked-out-of-"
                            f"boundary={expect_all}, got {got_all!r}")
    return failures


# ---------------------------------------------------------------------------
# (d) Termination and reason
# ---------------------------------------------------------------------------

def check_termination_and_reason(steps, root):
    failures = []

    # Only unchecked task is out-of-boundary, nothing else progressed.
    base = "- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n"
    work, repo, base_sha, _ = build_scenario(root, base_tasks_md=base, tip_tasks_md=base)
    rc, out, outputs, _ = run_cycle_step(steps, repo, base_sha, verdict="healthy",
                                         cycle_result="success")
    if rc != 0:
        failures.append(f"(d) scenario 1: {CYCLE_STEP!r} exited {rc}: {out.strip()}")
    else:
        if outputs.get("handoff") != "true" or outputs.get("routed") != "true":
            failures.append(f"(d) scenario 1: expected handoff=true routed=true, "
                            f"got handoff={outputs.get('handoff')!r} "
                            f"routed={outputs.get('routed')!r}")
        reason = outputs.get("reason", "")
        if "write boundary" not in reason or ".claude/skills/foo/SKILL.md" not in reason:
            failures.append(f"(d) scenario 1: reason did not name the routed "
                            f"task -- got {reason!r}")

    # Same, but another task also got checked this cycle (progressed=true)
    # -- ticking the last in-reach task on what may be the final iteration
    # must still file the out-of-boundary task rather than let it reach the
    # PR as orphan prose (PR #836 review, item 2, SC-005). handoff stays
    # false (spec 059's own progress test is unaffected), but routed is
    # now true and the reason narrative names the task.
    base2 = "- [ ] T000 do something\n- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n"
    tip2 = "- [x] T000 do something\n- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n"
    work, repo, base_sha, _ = build_scenario(root, base_tasks_md=base2, tip_tasks_md=tip2)
    rc, out, outputs, _ = run_cycle_step(steps, repo, base_sha, verdict="healthy",
                                         cycle_result="success")
    if rc != 0:
        failures.append(f"(d) scenario 2: {CYCLE_STEP!r} exited {rc}: {out.strip()}")
    else:
        if outputs.get("handoff") != "false":
            failures.append(f"(d) scenario 2: expected handoff=false (spec "
                            f"059's own progress test is unaffected), got "
                            f"handoff={outputs.get('handoff')!r}")
        if outputs.get("routed") != "true":
            failures.append(f"(d) scenario 2: expected routed=true -- ticking "
                            f"the last in-reach task must not block filing the "
                            f"still-unchecked out-of-boundary task (item 2), "
                            f"got routed={outputs.get('routed')!r}")
        reason = outputs.get("reason", "")
        if "write boundary" not in reason or ".claude/skills/foo/SKILL.md" not in reason:
            failures.append(f"(d) scenario 2: expected the routed narrative "
                            f"naming the task, now that routed=true overrides "
                            f"spec 059's generic hand-off text -- got "
                            f"reason={reason!r}")

    # A converge: commit whose appended lines are all out-of-boundary must
    # not disqualify routed either (PR #836 review, item 2): the converge
    # commit here re-appends a second out-of-boundary line, so converge_sha
    # is set and progressed=false, which used to force the generic
    # "converge appended new work" text and routed=false.
    base4 = "- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n"
    tip4 = ("- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n"
            "- [ ] T002 edit `.claude/skills/bar/SKILL.md`\n")
    work, repo, base_sha, _ = build_converge_scenario(root, base_tasks_md=base4,
                                                       tip_tasks_md=tip4)
    rc, out, outputs, _ = run_cycle_step(steps, repo, base_sha, verdict="healthy",
                                         cycle_result="success")
    if rc != 0:
        failures.append(f"(d) scenario 4: {CYCLE_STEP!r} exited {rc}: {out.strip()}")
    else:
        if outputs.get("routed") != "true":
            failures.append(f"(d) scenario 4: a converge: commit whose "
                            f"appended lines are all out-of-boundary must not "
                            f"disqualify routed -- got "
                            f"routed={outputs.get('routed')!r}")
        reason = outputs.get("reason", "")
        if "write boundary" not in reason or "converge appended new work" in reason:
            failures.append(f"(d) scenario 4: expected the routed narrative "
                            f"to override spec 059's \"converge appended new "
                            f"work\" text -- got reason={reason!r}")

    # Mixed unchecked set (one out-of-boundary, one ordinary).
    base3 = "- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n- [ ] T002 write docs\n"
    work, repo, base_sha, _ = build_scenario(root, base_tasks_md=base3, tip_tasks_md=base3)
    rc, out, outputs, _ = run_cycle_step(steps, repo, base_sha, verdict="healthy",
                                         cycle_result="success")
    if rc != 0:
        failures.append(f"(d) scenario 3: {CYCLE_STEP!r} exited {rc}: {out.strip()}")
    else:
        if outputs.get("routed") != "false":
            failures.append(f"(d) scenario 3: a mixed unchecked set must not "
                            f"route -- got routed={outputs.get('routed')!r}")
        if outputs.get("handoff") != "true":
            failures.append(f"(d) scenario 3: expected handoff=true (spec "
                            f"059's own hand-off condition, unaffected), got "
                            f"handoff={outputs.get('handoff')!r}")
        expected_reason = ("the cycle checked nothing new, so the loop is "
                           "ending here rather than dispatching another cycle")
        if outputs.get("reason", "") != expected_reason:
            failures.append(f"(d) scenario 3: existing hand-off narrative "
                            f"changed -- got reason={outputs.get('reason')!r}")
    return failures


# ---------------------------------------------------------------------------
# (e) No filing on a truncated run
# ---------------------------------------------------------------------------

def eval_if_expr(expr, context):
    """A tiny, deliberately narrow evaluator for this repository's own
    `if:` expressions -- substitutes each `steps.X.outputs.Y` token with
    its modelled string value, translates &&/|| to and/or, then evaluates
    the result as a Python boolean expression. Sufficient for the fixed
    shape this gate's own targets use; not a general GitHub Actions
    expression engine."""
    e = expr.strip()
    if e.startswith("${{") and e.endswith("}}"):
        e = e[3:-2].strip()
    e = e.replace("!cancelled()", "True")
    e = e.replace("&&", " and ").replace("||", " or ")

    def repl(m):
        return repr(context.get(m.group(0), ""))

    e = re.sub(r"steps\.[\w.\-]+\.outputs\.[\w\-]+", repl, e)
    return bool(eval(e, {"__builtins__": {}}, {}))


def check_no_filing_on_truncated():
    failures = []
    doc = yaml.safe_load(open(STAGE, encoding="utf-8")) or {}
    step = None
    for job in (doc.get("jobs") or {}).values():
        for s in (job or {}).get("steps") or []:
            if (s or {}).get("name") == ROUTE_STEP:
                step = s
                break
    if step is None:
        return [f"(e) no step named {ROUTE_STEP!r} found in {STAGE}."]
    if_expr = str(step.get("if", ""))
    context = {"steps.final.outputs.ok": "true",
               "steps.final.outputs.truncated": "true",
               "steps.final.outputs.routed": "true"}
    try:
        result = eval_if_expr(if_expr, context)
    except Exception as exc:  # noqa: BLE001 -- a malformed if: is itself the finding
        return [f"(e) could not evaluate {ROUTE_STEP!r}'s if: expression "
                f"{if_expr!r}: {exc}"]
    if result:
        failures.append(f"(e) {ROUTE_STEP!r}'s if: expression evaluates true "
                        f"even when truncated=true (FR-013) -- if: was "
                        f"{if_expr!r}")
    return failures


# ---------------------------------------------------------------------------
# (f) Idempotency
# ---------------------------------------------------------------------------

def run_fingerprint(stage, file_path, gate_or_artifact, cwd=None):
    script = os.path.abspath(FINGERPRINT_SCRIPT).replace("\\", "/")
    proc = subprocess.run([BASH, script, stage, file_path, gate_or_artifact],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd)
    kv = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    return proc.returncode, kv.get("fingerprint", ""), kv.get("verified", "")


def check_idempotency(root):
    """Runs with a real tasks.md present so the anchor path verifies (the
    fallback shape is keyed only on (stage, file_path), never on
    gate_or_artifact -- two different lines would collide there, which is
    not what this pass condition is testing)."""
    failures = []
    file_path = f"{SPEC_DIR}/tasks.md"
    line = "- [ ] T001 edit `.claude/skills/foo/SKILL.md`"
    workdir = tempfile.mkdtemp(dir=root)
    write_file(workdir, file_path, line + "\n")
    rc1, fp1, verified1 = run_fingerprint("implement", file_path, line, cwd=workdir)
    rc2, fp2, verified2 = run_fingerprint("implement", file_path, line, cwd=workdir)
    if rc1 != 0 or rc2 != 0:
        failures.append(f"(f) compute-finding-fingerprint.sh exited nonzero "
                        f"(rc1={rc1}, rc2={rc2}).")
    elif verified1 != "true" or verified2 != "true":
        failures.append(f"(f) fixture setup did not verify the anchor -- "
                        f"verified1={verified1!r} verified2={verified2!r} "
                        f"(the fallback shape does not depend on the line "
                        f"text, so this fixture would prove nothing).")
    elif fp1 != fp2:
        failures.append(f"(f) the same line fingerprinted twice produced "
                        f"different values: {fp1!r} vs {fp2!r}.")
    # A trailing-whitespace-only change would not do: normalize_basis
    # collapses whitespace, so it would (correctly) still verify to the
    # SAME normalized anchor. Change an actual word instead.
    reworded = line.replace("edit", "adjust")
    write_file(workdir, file_path, line + "\n" + reworded + "\n")
    rc3, fp3, verified3 = run_fingerprint("implement", file_path, reworded, cwd=workdir)
    if rc3 == 0 and verified3 == "true" and fp1 == fp3:
        failures.append("(f) a line reworded by one character produced the "
                        "SAME fingerprint as the original -- expected a "
                        "different value (accepted, narrow limitation "
                        "aside: re-wording is never detected as \"the same\" "
                        "task).")
    return failures


# ---------------------------------------------------------------------------
# (g) Fingerprint single-home
# ---------------------------------------------------------------------------

SHA_LITERAL_RE = re.compile(r'sha256\(\s*["\'](anchor|fallback)\|')


def check_fingerprint_single_home():
    """Scoped to the shipped call sites -- workflows, composite actions, and
    _shared/ scripts -- mirroring verify-spec-meta-single-home.py's own
    glob (Gate 61). Deliberately excludes .github/scripts/: a gate's own
    fixtures (this script's mutation-6 replacement string, or Gate 71's
    stage-findings-tests/run_fixtures.py, which independently re-derives
    the formula as a pre-existing TEST ORACLE to assert the shipped
    composite's real output against) are not the "second production copy"
    D6 exists to catch."""
    failures = []
    import glob
    allowed = {os.path.normpath(FINGERPRINT_SCRIPT)}
    files = (glob.glob(".github/workflows/*.yml")
            + glob.glob(".github/workflows/*.yaml")
            + glob.glob(".github/actions/**/action.yml", recursive=True)
            + glob.glob(".github/actions/**/action.yaml", recursive=True)
            + glob.glob(".github/actions/_shared/*.sh"))
    for f in sorted(files):
        path = os.path.normpath(f)
        if path in allowed:
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if SHA_LITERAL_RE.search(text):
            failures.append(f"(g) {path}: contains a second "
                            f"sha256(\"anchor|...\"/\"fallback|...\"-shaped "
                            f"literal -- the one home is {FINGERPRINT_SCRIPT} "
                            f"(research.md D6).")
    return failures


# ---------------------------------------------------------------------------
# (h) Board-loop label separation
# ---------------------------------------------------------------------------

def check_label_separation():
    failures = []
    doc = yaml.safe_load(open(STAGE, encoding="utf-8")) or {}
    # PyYAML (1.1 resolver) parses the bare `on:` key as the boolean True,
    # not the string "on" -- mirrors board_prove.py's/verify-metrics-
    # wrapper-trigger-drops-watchdog.py's own fallback.
    on_block = doc.get("on") or doc.get(True) or {}
    inputs = ((on_block or {}).get("workflow_call") or {}).get("inputs") or {}
    write_boundary_default = (inputs.get("write-boundary-label-prefix") or {}).get("default")
    findings_default = (inputs.get("findings-label-prefix") or {}).get("default")
    if write_boundary_default == findings_default:
        failures.append(f"(h) write-boundary-label-prefix's default "
                        f"({write_boundary_default!r}) equals findings-"
                        f"label-prefix's default -- research.md D4 requires "
                        f"them distinct so the board loop never treats a "
                        f"routed item as fix-shaped authorization.")
    if write_boundary_default == "spec-request":
        failures.append("(h) write-boundary-label-prefix's default is the "
                        "literal string 'spec-request' -- that label is one "
                        "of Principle X's authorized-entry classes.")
    return failures


# ---------------------------------------------------------------------------
# SC-005: finalize.yml's routed-item lookup
# ---------------------------------------------------------------------------

# PR #836 review, item 5: the real step now calls `gh issue list --repo ...
# --label ... --state all --json number,url,body` ONCE and matches the
# marker client-side via jq contains() -- the SAME shape wing-commander-
# durable-failure-issue's own dedup lookup uses -- rather than a per-line
# `gh issue list --search`. This stub responds to that one call with a
# JSON array carrying the marker in `body`, or fails it when FAIL_GH=true
# (exercising the ::warning:: path, never silently swallowed).
GH_LOOKUP_STUB = """#!/bin/sh
args="$*"
echo "$args" >> "$GH_CALLS"
case "$args" in
  *"issue list"*)
    if [ "${FAIL_GH:-}" = "true" ]; then
      echo "simulated API failure" >&2
      exit 1
    fi
    printf '[{"number":42,"url":"%s","body":"body containing %s marker"}]' "$MATCH_URL" "$MATCH_MARKER"
    ;;
  *) printf '[]' ;;
esac
exit 0
"""


def check_finalize_lookup(steps, root):
    failures = []
    routed_line = "- [ ] T001 edit `.claude/skills/foo/SKILL.md`"
    ordinary_line = "- [ ] T002 write docs"
    unchecked_items = routed_line + "\n" + ordinary_line
    tasks_path = f"{SPEC_DIR}/tasks.md"
    match_url = "https://github.com/acme/repo/issues/42"

    workdir = tempfile.mkdtemp(dir=root)
    runner_temp = os.path.join(workdir, "runner_temp")
    bindir = os.path.join(workdir, "bin")
    calls_file = os.path.join(workdir, "gh_calls")
    os.makedirs(runner_temp, exist_ok=True)
    os.makedirs(bindir, exist_ok=True)
    os.makedirs(os.path.join(workdir, SPEC_DIR), exist_ok=True)
    write_file(workdir, tasks_path, unchecked_items + "\n")
    open(calls_file, "w").close()

    # Computed with the SAME cwd (workdir) the shipped step will use, so the
    # anchor verifies against the identical tasks.md content and this
    # matches what the shipped step independently (re)computes.
    _, fp, verified = run_fingerprint("implement", tasks_path, routed_line, cwd=workdir)
    if verified != "true":
        failures.append(f"SC-005: fixture setup did not verify the anchor "
                        f"for the routed line -- verified={verified!r}")
    marker = f"<!-- wing-commander-finding: fingerprint={fp} -->"
    with open(os.path.join(bindir, "gh"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_LOOKUP_STUB)
    os.chmod(os.path.join(bindir, "gh"), 0o755)

    base_env = {
        "GH_TOKEN": "x", "UNCHECKED_ITEMS": unchecked_items,
        "TASKS_PATH": tasks_path, "LABEL_PREFIX": "route-out-of-boundary",
        "MATCH_MARKER": marker, "MATCH_URL": match_url,
        "GH_CALLS": calls_file, "GITHUB_REPOSITORY": "acme/repo",
        # Actions sets this to the composite's own directory -- resolves
        # $GITHUB_ACTION_PATH/../_shared/... to the REAL shared script
        # (mirrors verify-chain-stop-notice-body.py's identical convention).
        "GITHUB_ACTION_PATH": os.path.abspath(os.path.dirname(WRITE_BOUNDARY_LOOKUP_COMPOSITE)),
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    env = dict(base_env, FAIL_GH="false")
    rc, out, outputs, _ = run_step(BASH, steps[LOOKUP_STEP], workdir, env, runner_temp)
    if rc != 0:
        failures.append(f"SC-005: {LOOKUP_STEP!r} exited {rc}: {out.strip()}")
        return failures
    mapping = outputs.get("mapping", "[]")
    try:
        parsed = json.loads(mapping) if mapping.strip() else []
    except ValueError:
        failures.append(f"SC-005: mapping output was not valid JSON: {mapping!r}")
        parsed = []
    lines_mapped = {entry.get("line") for entry in parsed}
    if routed_line not in lines_mapped:
        failures.append(f"SC-005: the routed line was not present in the "
                        f"lookup mapping -- mapping={mapping!r}")
    if ordinary_line in lines_mapped:
        failures.append(f"SC-005: the ordinary (unmatched) line was wrongly "
                        f"present in the lookup mapping -- mapping={mapping!r}")
    rendered = outputs.get("rendered", "")
    if match_url not in rendered or "routed" not in rendered:
        failures.append(f"SC-005: the rendered instruction did not reference "
                        f"the routed item's URL -- rendered={rendered!r}")

    # (j) A failed `gh issue list` must be surfaced, not silently swallowed
    # into "no routed items found" (PR #836 review, item 5).
    fail_env = dict(base_env, FAIL_GH="true")
    rc2, out2, outputs2, _ = run_step(BASH, steps[LOOKUP_STEP], workdir, fail_env, runner_temp)
    if rc2 != 0:
        failures.append(f"(j) {LOOKUP_STEP!r} exited {rc2} on a failed `gh "
                        f"issue list` -- it must degrade to an empty "
                        f"mapping, never fail the job: {out2.strip()}")
    else:
        if "::warning::" not in out2:
            failures.append(f"(j) a failed `gh issue list` produced no "
                            f"::warning:: annotation -- got output={out2!r}")
        mapping2 = outputs2.get("mapping", "[]")
        if mapping2.strip() not in ("[]", ""):
            failures.append(f"(j) a failed `gh issue list` should degrade "
                            f"to an empty mapping -- got mapping={mapping2!r}")
    return failures


# ---------------------------------------------------------------------------
# Mutations (--self-test)
# ---------------------------------------------------------------------------

def _mut_second_literal_default(steps):
    """(1) no-write-paths hand-edited to a second literal default inside
    wing-commander-write-boundary's call site."""
    marker = "  no-write-paths: ${{ inputs.no-write-paths }}"
    replacement = '  no-write-paths: ".claude/"'
    text = open(STAGE, encoding="utf-8").read()
    if marker not in text:
        return None
    return text.replace(marker, replacement, 1)


def _mut_statement_drift(steps):
    """(2) the rendered write-paths-statement mutated to include a prefix
    absent from the input."""
    marker = 'write_paths_statement="This run\'s agent may not write: $write_paths_list."'
    replacement = ('write_paths_statement="This run\'s agent may not write: '
                   '$write_paths_list, .ssh/."')
    if marker not in steps[COMPOSE_STEP]:
        return None
    mutated = copy.deepcopy(steps)
    mutated[COMPOSE_STEP] = mutated[COMPOSE_STEP].replace(marker, replacement, 1)
    return mutated


def _mut_substring_match():
    """(3) the classification rule's prefix-match relaxed to a substring
    match."""
    script_path = os.path.abspath(CLASSIFY_SCRIPT)
    text = open(script_path, encoding="utf-8").read()
    marker = "return any(token.startswith(prefix) for prefix in prefixes)"
    replacement = "return any(prefix in token for prefix in prefixes)"
    if marker not in text:
        return None
    return script_path, text.replace(marker, replacement, 1)


def _mut_routed_ignores_classification(steps):
    """(4) the routed computation changed to ignore classification entirely
    -- hard-coded true whenever ok && !truncated, even when the remaining
    unchecked work is NOT all out-of-boundary (PR #836 review, item 2's fix
    dropped the old handoff gate on `routed`; this mutation now targets the
    classification gate that replaced it, never a resurrected handoff
    check)."""
    marker = ('routed=false\n'
              'if [ "$ok" = "true" ] && [ "$truncated" = "false" ] && '
              '[ "$WRITE_BOUNDARY_ALL_OOB" = "true" ]; then\n'
              '  routed=true\nfi')
    replacement = ('routed=false\n'
                  'if [ "$ok" = "true" ] && [ "$truncated" = "false" ]; then\n'
                  '  routed=true\nfi')
    if marker not in steps[CYCLE_STEP]:
        return None
    mutated = copy.deepcopy(steps)
    mutated[CYCLE_STEP] = mutated[CYCLE_STEP].replace(marker, replacement, 1)
    return mutated


def _mut_drop_truncated_guard():
    doc_text = open(STAGE, encoding="utf-8").read()
    marker = ("steps.final.outputs.truncated != 'true' && "
             "steps.final.outputs.routed == 'true'")
    replacement = "steps.final.outputs.routed == 'true'"
    if marker not in doc_text:
        return None
    return doc_text.replace(marker, replacement, 1)


def _mut_inline_fingerprint_in_finalize():
    """(6) compute-finding-fingerprint.sh re-implemented inline a second
    time -- in the finalize-facing lookup composite, since that (never
    finalize.yml itself, which may not resolve _shared/ directly -- Gate
    60's promotion-prevention check) is where the call site lives."""
    text = open(WRITE_BOUNDARY_LOOKUP_COMPOSITE, encoding="utf-8").read()
    marker = 'bash "$FP_SCRIPT" implement "$TASKS_PATH" "$line"'
    replacement = ('python3 -c \'import hashlib; print("fingerprint=" + '
                   'hashlib.sha256("anchor|implement|x".encode()).hexdigest())\'')
    if marker not in text:
        return None
    return text.replace(marker, replacement, 1)


def check_mutation_1(steps, root):
    mutated_text = _mut_second_literal_default(steps)
    if mutated_text is None:
        print("::error::mutation 'second literal default' changed nothing.")
        return ["mutation inapplicable: second literal default"]
    fd, path = tempfile.mkstemp(suffix=".yml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(mutated_text)
    count = mutated_text.count(DEFAULT_LITERAL)
    os.remove(path)
    if count >= 2:
        print("Mutation OK -- second literal default: caught (a).")
        return []
    return ["mutation survived: second literal default"]


def check_mutation_2(steps, root):
    mutated = _mut_statement_drift(steps)
    if mutated is None:
        print("::error::mutation 'statement drift' changed nothing.")
        return ["mutation inapplicable: statement drift"]
    workdir = tempfile.mkdtemp(dir=root)
    rc, out, outputs, _ = run_step(BASH, mutated[COMPOSE_STEP],
                                   workdir,
                                   {"STEP_LABEL": "gate133", "DEFAULT_ALLOWED": "Read",
                                    "DEFAULT_DISALLOWED": "WebFetch", "EXTRA_ALLOWED": "",
                                    "EXTRA_DISALLOWED": "", "ALLOWED_OVERRIDE": "__unset__",
                                    "DISALLOWED_OVERRIDE": "__unset__",
                                    "NO_WRITE_PATHS": ".claude/"},
                                   workdir)
    if rc == 0 and outputs.get("write-paths-statement", "") == "This run's agent may not write: .claude/, .ssh/.":
        print("Mutation OK -- statement drift: caught (b).")
        return []
    return ["mutation survived: statement drift"]


def check_mutation_3():
    result = _mut_substring_match()
    if result is None:
        print("::error::mutation 'substring match' changed nothing.")
        return ["mutation inapplicable: substring match"]
    _script_path, mutated_text = result
    fd, tmp_path = tempfile.mkstemp(suffix=".sh")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(mutated_text)
        os.chmod(tmp_path, 0o755)
        # ".claude-extra/foo" would not even trip a substring match (it
        # never contains the literal text ".claude/" anywhere) -- the
        # fixture that actually distinguishes prefix-match from
        # substring-match is a path that CONTAINS ".claude/" without
        # starting with it.
        proc = subprocess.run(
            [BASH, tmp_path, "- [ ] T004 edit `src/.claude/nested/thing.md`",
             ".claude/", f"{SPEC_DIR}/tasks.md", SPEC_DIR],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        os.remove(tmp_path)
    if proc.returncode == 0 and "out-of-boundary-count=1" in proc.stdout:
        print("Mutation OK -- substring match: caught (c).")
        return []
    return [f"mutation survived: substring match (rc={proc.returncode}, "
            f"stdout={proc.stdout!r}, stderr={proc.stderr!r})"]


def check_mutation_4(steps, root):
    mutated = _mut_routed_ignores_classification(steps)
    if mutated is None:
        print("::error::mutation 'routed ignores classification' changed nothing.")
        return ["mutation inapplicable: routed ignores classification"]
    base3 = "- [ ] T001 edit `.claude/skills/foo/SKILL.md`\n- [ ] T002 write docs\n"
    work, repo, base_sha, _ = build_scenario(root, base_tasks_md=base3, tip_tasks_md=base3)
    rc, out, outputs, _ = run_cycle_step(mutated, repo, base_sha, verdict="healthy",
                                         cycle_result="success")
    if rc == 0 and outputs.get("routed") == "true":
        print("Mutation OK -- routed ignores classification: caught (d)'s mixed-set scenario.")
        return []
    return ["mutation survived: routed ignores classification"]


def check_mutation_5():
    mutated_text = _mut_drop_truncated_guard()
    if mutated_text is None:
        print("::error::mutation 'drop truncated guard' changed nothing.")
        return ["mutation inapplicable: drop truncated guard"]
    doc = yaml.safe_load(mutated_text) or {}
    step = None
    for job in (doc.get("jobs") or {}).values():
        for s in (job or {}).get("steps") or []:
            if (s or {}).get("name") == ROUTE_STEP:
                step = s
    if step is None:
        return ["mutation inapplicable: drop truncated guard (step not found)"]
    context = {"steps.final.outputs.ok": "true",
               "steps.final.outputs.truncated": "true",
               "steps.final.outputs.routed": "true"}
    result = eval_if_expr(str(step.get("if", "")), context)
    if result:
        print("Mutation OK -- drop truncated guard: caught (e).")
        return []
    return ["mutation survived: drop truncated guard"]


def check_mutation_6():
    mutated_text = _mut_inline_fingerprint_in_finalize()
    if mutated_text is None:
        print("::error::mutation 'inline fingerprint in finalize' changed nothing.")
        return ["mutation inapplicable: inline fingerprint in finalize"]
    if SHA_LITERAL_RE.search(mutated_text):
        print("Mutation OK -- inline fingerprint in finalize: caught (g).")
        return []
    return ["mutation survived: inline fingerprint in finalize"]


def run_mutations(steps, root):
    failures = []
    failures.extend(check_mutation_1(steps, root))
    failures.extend(check_mutation_2(steps, root))
    failures.extend(check_mutation_3())
    failures.extend(check_mutation_4(steps, root))
    failures.extend(check_mutation_5())
    failures.extend(check_mutation_6())
    # (7) zero fixtures discovered/executed at all.
    if not CLASSIFY_FIXTURES or not STATEMENT_FIXTURES:
        failures.append("mutation survived: zero fixtures (Constitution VIII)")
    else:
        print("Mutation OK -- zero fixtures would fail loudly (Constitution VIII): "
              f"{len(CLASSIFY_FIXTURES)} classification, {len(STATEMENT_FIXTURES)} "
              "statement fixture(s) are wired.")
    return failures


# ---------------------------------------------------------------------------

def check_gate_wired():
    wf = yaml.safe_load(open(LINT_WORKFLOW, encoding="utf-8")) or {}
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name") or ""
            if name.startswith(GATE_PREFIX):
                if str(step.get("if", "")).strip().lower() == "false":
                    return [f"{GATE_PREFIX} step is present in {LINT_WORKFLOW} "
                            f"but disabled (if: false)."]
                if THIS_SCRIPT not in str(step.get("run", "")):
                    return [f"{GATE_PREFIX} step in {LINT_WORKFLOW} does not "
                            f"invoke {THIS_SCRIPT}."]
                return []
    return [f"no step named {GATE_PREFIX!r} found in {LINT_WORKFLOW}."]


STEPS_CACHE = {}


def load_steps():
    STEPS_CACHE[COMPOSE_STEP] = find_step(TOOL_ARGS_COMPOSITE, COMPOSE_STEP)["run"]
    STEPS_CACHE[CLASSIFY_STEP] = find_step(WRITE_BOUNDARY_COMPOSITE, CLASSIFY_STEP)["run"]
    STEPS_CACHE[CYCLE_STEP] = find_step(STAGE, CYCLE_STEP)["run"]
    STEPS_CACHE[RETRY_STEP] = find_step(STAGE, RETRY_STEP)["run"]
    STEPS_CACHE[LOOKUP_STEP] = find_step(WRITE_BOUNDARY_LOOKUP_COMPOSITE, LOOKUP_STEP)["run"]
    return STEPS_CACHE


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not shutil.which("git"):
        sys.exit("::error::git is not on PATH. The shipped steps under test "
                 "commit and push, so nothing here can run without it.")

    self_test = "--self-test" in sys.argv[1:]
    steps = load_steps()
    root = tempfile.mkdtemp()
    failures = []
    try:
        if self_test:
            failures.extend(run_mutations(steps, root))
        else:
            failures.extend(check_single_definition())
            failures.extend(check_statement_fidelity(steps, root))
            failures.extend(check_enforcement_parity(steps, root))
            failures.extend(check_classification(root))
            failures.extend(check_termination_and_reason(steps, root))
            failures.extend(check_no_filing_on_truncated())
            failures.extend(check_idempotency(root))
            failures.extend(check_fingerprint_single_home())
            failures.extend(check_label_separation())
            failures.extend(check_finalize_lookup(steps, root))
            failures.extend(check_gate_wired())
    finally:
        shutil.rmtree(root, ignore_errors=True)

    label = "self-test" if self_test else "scenarios"
    print(f"write boundary {label}: {len(failures)} failure(s).")
    for f in failures:
        print(f"::error::{f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
