#!/usr/bin/env python3
"""Gate 99 -- every agent prompt that instructs a commit renders the
canonical commit-message scratch-path guidance (specs/078-plan-tasks-
commit-scratch-path, FR-001 through FR-013).

WHY THIS EXISTS
----------------
Nine agent-prompt sites across five workflows (plan.yml x2, tasks.yml x2,
board-loop.yml x2, pr-conversation.yml x1, implement.yml x2) instruct an
agent to commit. Only implement.yml's two sites used to tell the agent how
to compose a multi-line message safely (Write the message to a named
scratch path outside the checkout, then `git commit -F` that path); the
other seven said nothing, so the first time one of those agents composed a
body it hit a silent permission denial it could not diagnose (#440). The
fix renders one canonical guidance paragraph -- the
wing-commander-commit-message-guidance composite action's output -- into
all nine prompts. This gate is the backstop: a future prompt edit that
drops the render, or a tenth commit-instructing prompt added with none,
fails the PR-time suite by name instead of the next agent run finding out
the hard way.

DISCOVERY -- WHY NOT A LITERAL "git commit" SUBSTRING MATCH
--------------------------------------------------------------
research.md D3 and contracts/commit-scratch-path-gate.md describe discovery
as "a step whose prompt: value contains the literal substring `git
commit`". Read literally, that is wrong in both directions:

  * It UNDER-counts. 7 of the 9 real sites (plan.yml x2, tasks.yml x2,
    pr-conversation.yml's fold, implement.yml x2) tell the agent to
    "Commit ..." and never spell the two words "git" and "commit" together
    -- board-loop.yml's two sites are the only ones that do.
  * It OVER-counts, and fails loudly on sites this feature never touched.
    rebase.yml's "Resolve conflicts" step and finalize.yml's "Summarize
    change and extract remaining manual work" step both contain the
    literal substring "git commit" -- inside a sentence that PROHIBITS it
    ("Never run `git commit`...", "do not run git commit...") -- so a
    literal-substring gate would discover both, find neither covered nor
    exempt (research.md D6 says the exemption list "ships empty"), and
    fail on day one.

This is a defect in the planning artifacts, reported separately (a
contract that contradicts the workflows it describes) rather than fixed
there. This gate instead scans for the word "commit" (case-insensitive,
word-boundary, so "committee" does not match) inside an agent step's own
`prompt:` text -- what FR-010 actually asks for ("every agent prompt...
that instructs the agent to create a commit") -- restricted to steps whose
`uses:` names `claude-code-action` (never a bare grep over the whole file:
YAML-parsed, per Gate 7/23/51's stated rationale, so a step in flow style
or unusual indentation is not silently missed, and env/with/run text that
happens to contain "commit" outside a prompt is never mistaken for one).
Applied across every .github/workflows/*.yml file (not just the five this
feature touched), that scan finds exactly the nine real sites plus three
sites that mention "commit" without needing this feature's guidance --
carried in EXEMPT_SITES below, each with the reason -- proving the
regression protection reaches a future eleventh site automatically rather
than trusting a hand-count.

WHAT EACH DISCOVERED SITE MUST HAVE, ONE OF TWO
--------------------------------------------------
(a) Covered: a step in the same job, ordered before the discovered step,
    invokes ./.github/actions/wing-commander-commit-message-guidance under
    some step id X, and the discovered step's prompt: contains the literal
    substring steps.X.outputs.guidance.
(b) Exempt: (basename, step name) is a literal entry in EXEMPT_SITES.

implement.yml's cycle and retry sites get a deeper, render-executing check
on top (FR-013): their guidance-composing step's scratch-filename is
pinned to the two filenames #440 shipped, retry's extra-note is non-empty
and, once rendered by actually executing the composite action's shipped
run: step (via wc_shell_harness.run_step -- never a Python
re-implementation of the render, matching verify-tooling-statement.py /
verify-plan-tasks-cost-line.py), the two sites' rendered guidance strings
are identical except for the substituted filename and the trailing
extra-note sentence.

Usage:
    python3 .github/scripts/verify-commit-message-scratch-path.py
    python3 .github/scripts/verify-commit-message-scratch-path.py --self-test
"""
import glob
import os
import re
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import resolve_bash, run_step, use_utf8_stdout, find_step  # noqa: E402

WORKFLOWS_GLOB = ".github/workflows/*.yml"
GUIDANCE_ACTION_PATH = ".github/actions/wing-commander-commit-message-guidance/action.yml"
GUIDANCE_ACTION_NAME = "wing-commander-commit-message-guidance"
GUIDANCE_RENDER_STEP_NAME = "Render commit-message guidance"

COMMIT_RE = re.compile(r"\bcommit\b", re.I)
GUIDANCE_OUTPUT_RE = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.guidance")

# Sites this gate's dynamic scan discovers (their prompt: mentions "commit")
# but that do not need the scratch-path guidance -- each commented with why.
EXEMPT_SITES = {
    ("rebase.yml", "Resolve conflicts"):
        "prohibits committing outright (\"Never run `git commit`, `git "
        "push`... they are not available to you\") -- mentions the word "
        "but never composes a commit message at all.",
    ("finalize.yml", "Summarize change and extract remaining manual work"):
        "read-only agent (\"Constraints: read-only -- do not run git "
        "commit, git push...\") -- mentions the word but never composes a "
        "commit message at all.",
    ("clarify.yml", "Fold answers into the draft spec"):
        "commits, but always the fixed one-line \"spec: resolve "
        "clarifications from #<issue>\" -- deterministic, never "
        "multi-line, so the scratch-path convention has nothing to add.",
    ("board-loop.yml", "Triage-propose"):
        "read-only (\"You are read-only: you never close, label, or "
        "comment on anything yourself\") -- mentions \"commit\" only when "
        "discussing an existing commit already on main, never composes "
        "one itself.",
    ("board-loop.yml", "Route-propose"):
        "read-only (\"You are read-only: you never write, commit, or "
        "push anything\") -- drafts a diff for a deterministic backstop "
        "to apply, never commits itself.",
    ("board-loop.yml", "Reviewer"):
        "read-only reviewer -- \"commit\" appears only in staged, "
        "read-only context (this branch's own commits/commit messages), "
        "never as an instruction to compose one.",
    ("cleanup.yml", "Completion summary"):
        "read-only agent (\"Constraints: read-only -- do not run git "
        "commit, git push...\") -- mentions the word but never composes a "
        "commit message at all.",
    ("watchdog.yml", "Diagnose"):
        "pure analysis agent -- \"commit\" appears only inside descriptive "
        "evidence vocabulary (\"tool name, branch, commit counts, matched "
        "sentinel\"), never as an instruction to compose one.",
    ("intake.yml", "Create spec from issue"):
        "a genuine gap, not a deterministic one-liner: step 5 instructs "
        "\"commit ONLY the new spec directory ... and push it\" with an "
        "unspecified message, and Write plus Bash(git commit:*) are both "
        "granted (intake.yml:585) -- an intake agent composing a "
        "multi-line message here hits the same silent denial this "
        "feature exists to fix (#440). spec.md/research.md's nine-site "
        "enumeration never surveyed intake.yml, and wiring it in is "
        "outside specs/078-plan-tasks-commit-scratch-path's task list "
        "(tasks.md T003-T011 name only plan.yml/tasks.yml/board-loop.yml/"
        "pr-conversation.yml/implement.yml). Recorded here as an "
        "explicit, auditable exemption per FR-010 (\"MUST be an explicit "
        "exemption under FR-012, not an omission\") rather than left as "
        "a silent gap; reported separately as a follow-up finding.",
}

# implement.yml's two sites: FR-013's deeper, render-executing check.
DEEP_CHECK_SITES = {
    ("implement.yml", "Implement and converge (cycle)"): {
        "guidance_step_name": "Compose commit-message guidance (implement.cycle)",
        "scratch_filename": "implement-commit-message-cycle.txt",
        "needs_extra_note": False,
    },
    ("implement.yml", "Implement and converge (retry at escalation model)"): {
        "guidance_step_name": "Compose commit-message guidance (implement.retry)",
        "scratch_filename": "implement-commit-message-retry.txt",
        "needs_extra_note": True,
    },
}

BASH = None


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def load_workflow(path):
    return yaml.safe_load(open(path, encoding="utf-8")) or {}


def discover(workflows_glob):
    """-> (sites, parse_failures).

    sites is [(path, job_name, job, step, step_name, prompt), ...] for
    every agent step whose prompt: mentions "commit". parse_failures is
    [(path, error message)] for any file that could not be YAML-parsed."""
    sites = []
    parse_failures = []
    for path in sorted(glob.glob(workflows_glob)):
        try:
            wf = load_workflow(path)
        except yaml.YAMLError as exc:
            parse_failures.append((path, str(exc)))
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            job = job or {}
            for step in job.get("steps") or []:
                step = step or {}
                uses = str(step.get("uses") or "")
                if "claude-code-action" not in uses:
                    continue
                prompt = str((step.get("with") or {}).get("prompt") or "")
                if not COMMIT_RE.search(prompt):
                    continue
                step_name = step.get("name") or step.get("id") or "<unnamed>"
                sites.append((path, job_name, job, step, step_name, prompt))
    return sites, parse_failures


def preceding_guidance_step_ids(job, before_step):
    """Step ids, in order, of every step in `job` before `before_step`
    that `uses:` the canonical guidance composite."""
    ids = []
    for step in job.get("steps") or []:
        if step is before_step:
            break
        step = step or {}
        if GUIDANCE_ACTION_NAME in str(step.get("uses") or "") and step.get("id"):
            ids.append(step["id"])
    return ids


def find_named_step(job, name):
    for step in job.get("steps") or []:
        if (step or {}).get("name") == name:
            return step
    return None


# --------------------------------------------------------------------------
# Per-site pass condition
# --------------------------------------------------------------------------
def check_site(path, job, step, step_name, prompt):
    """-> None if covered/exempt, else a failure message string."""
    key = (os.path.basename(path), step_name)
    if key in EXEMPT_SITES:
        return None
    ids_before = preceding_guidance_step_ids(job, step)
    m = GUIDANCE_OUTPUT_RE.search(prompt)
    if m and m.group(1) in ids_before:
        return None
    return (
        f"instructs a commit but does not render the canonical commit-"
        f"message scratch-path guidance -- no step earlier in this job "
        f"invokes {GUIDANCE_ACTION_NAME} whose output this prompt "
        f"interpolates via steps.<id>.outputs.guidance, and "
        f"({os.path.basename(path)!r}, {step_name!r}) is not a registered "
        f"EXEMPT_SITES entry. An agent here composing a multi-line commit "
        f"message hits a silent permission denial it cannot diagnose "
        f"(#440).")


# --------------------------------------------------------------------------
# implement.yml's deep, render-executing check (FR-013)
# --------------------------------------------------------------------------
def render_guidance(scratch_filename, extra_note, root, runner_temp):
    """Execute the composite action's shipped render step for real. ->
    (rc, output, guidance).

    `runner_temp` is the caller's to pick -- it MUST be the same value for
    every render within one job's comparison (cycle and retry render in the
    same real job, so `${{ runner.temp }}` is one shared value; using a
    fresh directory per call here would make two otherwise-identical
    renders differ by their temp-dir prefix and break the "same except for
    the substituted filename" comparison outright)."""
    step = find_step(GUIDANCE_ACTION_PATH, GUIDANCE_RENDER_STEP_NAME)
    workdir = tempfile.mkdtemp(dir=root)
    env = {
        "SCRATCH_FILENAME": scratch_filename,
        "EXTRA_NOTE": extra_note,
        "RUNNER_TEMP_DIR": runner_temp,
    }
    rc, out, outputs, _ = run_step(BASH, str(step["run"]), workdir, env, runner_temp)
    return rc, out, outputs.get("guidance", "")


def deep_check(path, job, root):
    """-> [failure message, ...] for implement.yml's cycle/retry sites."""
    failures = []
    basename = os.path.basename(path)
    rendered = {}
    shared_runner_temp = os.path.join(tempfile.mkdtemp(dir=root), "runner_temp")
    os.makedirs(shared_runner_temp, exist_ok=True)
    for (fname, step_name), spec in DEEP_CHECK_SITES.items():
        if fname != basename:
            continue
        guidance_step = find_named_step(job, spec["guidance_step_name"])
        if guidance_step is None:
            failures.append(
                f"{path}: {step_name!r} needs a preceding step named "
                f"{spec['guidance_step_name']!r} invoking "
                f"{GUIDANCE_ACTION_NAME}, but no such step exists in this "
                f"job (FR-013).")
            continue
        with_block = guidance_step.get("with") or {}
        actual_filename = str(with_block.get("scratch-filename") or "")
        if actual_filename != spec["scratch_filename"]:
            failures.append(
                f"{path}: {spec['guidance_step_name']!r} passes "
                f"scratch-filename {actual_filename!r}, expected "
                f"{spec['scratch_filename']!r} (FR-013 -- #440's filename "
                f"must survive the conversion unchanged).")
        extra_note = str(with_block.get("extra-note") or "")
        if spec["needs_extra_note"] and not extra_note.strip():
            failures.append(
                f"{path}: {spec['guidance_step_name']!r} must set a "
                f"non-empty extra-note (FR-013 -- retry must still be told "
                f"to use a name distinct from the cycle step's scratch "
                f"file).")
        if spec["needs_extra_note"] and "distinct" not in extra_note.lower():
            failures.append(
                f"{path}: {spec['guidance_step_name']!r}'s extra-note does "
                f"not mention using a distinct filename from the cycle "
                f"step's scratch file (FR-013).")
        rc, out, guidance = render_guidance(
            actual_filename or spec["scratch_filename"], extra_note, root,
            shared_runner_temp)
        if rc != 0:
            failures.append(
                f"{path}: rendering {spec['guidance_step_name']!r}'s "
                f"guidance failed (exit {rc}):\n{out}")
            continue
        rendered[step_name] = (actual_filename or spec["scratch_filename"],
                               extra_note, guidance)

    cycle_key = "Implement and converge (cycle)"
    retry_key = "Implement and converge (retry at escalation model)"
    if cycle_key in rendered and retry_key in rendered:
        cycle_fname, _cycle_note, cycle_guidance = rendered[cycle_key]
        retry_fname, retry_note, retry_guidance = rendered[retry_key]
        if cycle_fname == retry_fname:
            failures.append(
                f"{path}: cycle and retry both render with scratch-"
                f"filename {cycle_fname!r} -- FR-006 requires two agent "
                f"sites able to run in the same job to use distinct "
                f"scratch paths.")
        else:
            expected_retry_base = cycle_guidance.replace(cycle_fname, retry_fname)
            if not retry_guidance.startswith(expected_retry_base):
                failures.append(
                    f"{path}: cycle's and retry's rendered guidance differ "
                    f"by more than the substituted filename and trailing "
                    f"extra-note (FR-009) -- cycle: {cycle_guidance!r}, "
                    f"retry: {retry_guidance!r}")
            else:
                trailing = retry_guidance[len(expected_retry_base):].strip()
                if retry_note.strip() and trailing != retry_note.strip():
                    failures.append(
                        f"{path}: retry's rendered guidance's trailing "
                        f"text {trailing!r} does not match its extra-note "
                        f"{retry_note.strip()!r} verbatim (FR-013).")
    return failures


# --------------------------------------------------------------------------
# Stale-exemption check
# --------------------------------------------------------------------------
def all_step_names(workflows_glob):
    """-> {(basename, step_name), ...} for every step in every workflow,
    regardless of whether it mentions "commit" -- the universe a stale
    EXEMPT_SITES entry is checked against."""
    names = set()
    for path in sorted(glob.glob(workflows_glob)):
        try:
            wf = load_workflow(path)
        except yaml.YAMLError:
            continue
        basename = os.path.basename(path)
        for job in (wf.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                step = step or {}
                name = step.get("name") or step.get("id")
                if name:
                    names.add((basename, name))
    return names


# --------------------------------------------------------------------------
# Top-level scan
# --------------------------------------------------------------------------
def scan(workflows_glob, root, check_exempt_staleness=True):
    """-> (checked_count, failures) -- failures is [((path, job, step), msg)].

    check_exempt_staleness is False for self-test fixtures scanning an
    isolated tempdir that was never going to contain rebase.yml's/
    finalize.yml's/clarify.yml's real exempt steps in the first place --
    the staleness question only means something against the real tree."""
    failures = []
    sites, parse_failures = discover(workflows_glob)
    for path, msg in parse_failures:
        failures.append(((path, "-", "-"),
                          f"could not parse this workflow as YAML ({msg}) -- "
                          f"cannot confirm its agent prompts render the "
                          f"scratch-path guidance, so this gate fails rather "
                          f"than silently dropping the file."))

    checked = 0
    seen_jobs = {}  # (path, job_name) -> job dict, from discover() -- never re-parsed.
    for path, job_name, job, step, step_name, prompt in sites:
        checked += 1
        msg = check_site(path, job, step, step_name, prompt)
        if msg:
            failures.append(((path, job_name, step_name), msg))
        seen_jobs[(path, job_name)] = job

    for (path, job_name), job in sorted(seen_jobs.items()):
        for msg in deep_check(path, job, root):
            failures.append(((path, job_name, "-"), msg))

    if check_exempt_staleness:
        all_names = all_step_names(workflows_glob)
        for (basename, step_name) in sorted(EXEMPT_SITES):
            if not any(b == basename and n == step_name for b, n in all_names):
                failures.append(
                    ((basename, "-", step_name),
                     f"EXEMPT_SITES names ({basename!r}, {step_name!r}), but "
                     f"no step with that name exists in any "
                     f".github/workflows/*.yml file -- a stale exemption "
                     f"hides nothing today, but documents a site that no "
                     f"longer exists."))

    return checked, failures


def main(argv):
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()

    if "--self-test" in argv:
        return self_test()

    tmproot = tempfile.mkdtemp(prefix="verify_commit_scratch_path_")
    try:
        checked, failures = scan(WORKFLOWS_GLOB, tmproot)
    finally:
        import shutil
        shutil.rmtree(tmproot, ignore_errors=True)

    for site, msg in failures:
        print(f"::error file={site[0]}::Gate 99: job {site[1]!r} step "
              f"{site[2]!r}: {msg}")
    if checked == 0:
        print("::error::Gate 99: found zero agent prompts mentioning "
              "\"commit\" across every .github/workflows/*.yml file. Either "
              "none exist, or this gate's detection is broken -- both are "
              "worth stopping the build over.")
        return 1
    print(f"Gate 99: {checked} commit-instructing agent prompt(s) checked; "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Self-test -- synthetic fixtures (Gate 47/51 style), never a mutation of
# the real workflow files in place.
# --------------------------------------------------------------------------
GUIDANCE_STEP_YAML = """\
      - name: Compose commit-message guidance (x)
        id: commit-guidance-x
        uses: ./.github/actions/wing-commander-commit-message-guidance
        with:
          scratch-filename: x-commit-message.txt
"""

COVERED_SITE = """\
name: covered-fixture
on:
  workflow_call: {{}}
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
{guidance_step}      - name: Do the work
        id: agent
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Commit your work as "demo: fixture".

            ${{{{ steps.commit-guidance-x.outputs.guidance }}}}
"""

UNCOVERED_SITE = """\
name: uncovered-fixture
on:
  workflow_call: {}
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - name: Do the work
        id: agent
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Commit your work as "demo: fixture".
"""

ORPHANED_REFERENCE_SITE = """\
name: orphaned-fixture
on:
  workflow_call: {}
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - name: Do the work
        id: agent
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Commit your work as "demo: fixture".

            ${{ steps.commit-guidance-x.outputs.guidance }}
"""


def _scan_fixture(label, filename, body, root, check_exempt_staleness=False):
    fixture_dir = tempfile.mkdtemp(dir=root)
    with open(os.path.join(fixture_dir, filename), "w", encoding="utf-8") as fh:
        fh.write(body)
    _checked, failures = scan(os.path.join(fixture_dir, "*.yml"), root,
                              check_exempt_staleness=check_exempt_staleness)
    return failures


def self_test():
    failed = []
    root = tempfile.mkdtemp(prefix="verify_commit_scratch_path_selftest_")

    def check(label, filename, body, expect_fail):
        failures = _scan_fixture(label, filename, body, root)
        fired = len(failures) > 0
        if fired != expect_fail:
            failed.append(
                f"{label}: expected the gate to "
                f"{'FAIL' if expect_fail else 'PASS'}, it "
                f"{'FAILED' if fired else 'PASSED'} ({failures!r})")
            return
        print(f"ok    {label}")

    check("(1) a covered site (guidance rendered) passes",
          "covered.yml", COVERED_SITE.format(guidance_step=GUIDANCE_STEP_YAML),
          expect_fail=False)
    check("(2) a site whose prompt never renders the guidance fails",
          "uncovered.yml", UNCOVERED_SITE, expect_fail=True)
    check("(3) a site whose prompt references a guidance step that was "
          "deleted from the job fails",
          "orphaned.yml", ORPHANED_REFERENCE_SITE, expect_fail=True)

    # (4) a stale EXEMPT_SITES entry -- point it at a fixture tree with none
    # of the registered exempt steps.
    empty_fixture = """\
name: empty-fixture
on:
  workflow_call: {}
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - name: Not an agent step
        run: echo hi
"""
    failures = _scan_fixture("stale exemption", "empty.yml", empty_fixture, root,
                              check_exempt_staleness=True)
    if not failures:
        failed.append(
            "(4) a stale EXEMPT_SITES entry: expected the gate to FAIL "
            "(none of the registered exempt sites exist in this fixture "
            "tree), it PASSED")
    else:
        print("ok    (4) a stale EXEMPT_SITES entry fails")

    # (5) zero sites discovered at all.
    checked, failures = scan(os.path.join(tempfile.mkdtemp(dir=root), "*.yml"), root)
    if checked != 0:
        failed.append(f"(5) zero-file glob: expected checked == 0, got {checked}")
    else:
        print("ok    (5) zero sites discovered at all is treated as a failure by main()")

    # (6)/(7) implement.yml's deep check: a scratch-filename collision, and
    # a blanked retry extra-note, each caught.
    cycle_guidance = GUIDANCE_STEP_YAML.replace(
        "commit-guidance-x", "commit-guidance-cycle").replace(
        "x-commit-message.txt", "implement-commit-message-cycle.txt").replace(
        "guidance (x)", "guidance (implement.cycle)")
    retry_guidance_ok = """\
      - name: Compose commit-message guidance (implement.retry)
        id: commit-guidance-retry
        uses: ./.github/actions/wing-commander-commit-message-guidance
        with:
          scratch-filename: implement-commit-message-retry.txt
          extra-note: >-
            Use a name distinct from the cycle step's scratch file above.
"""
    implement_ok = """\
name: implement.yml
on:
  workflow_call: {{}}
jobs:
  implement:
    runs-on: ubuntu-latest
    steps:
{cycle}      - name: Implement and converge (cycle)
        id: cycle
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Commit AND push progress.

            ${{{{ steps.commit-guidance-cycle.outputs.guidance }}}}
{retry}      - name: Implement and converge (retry at escalation model)
        id: retry
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Commit AND push progress.

            ${{{{ steps.commit-guidance-retry.outputs.guidance }}}}
""".format(cycle=cycle_guidance, retry=retry_guidance_ok)

    failures = _scan_fixture("implement.yml clean deep-check", "implement.yml",
                              implement_ok, root)
    if failures:
        failed.append(f"(6a) implement.yml clean fixture should PASS the "
                       f"deep check, it FAILED: {failures!r}")
    else:
        print("ok    (6a) implement.yml's cycle/retry pass the deep render check")

    retry_collision = retry_guidance_ok.replace(
        "implement-commit-message-retry.txt", "implement-commit-message-cycle.txt")
    implement_collision = implement_ok.replace(retry_guidance_ok, retry_collision)
    failures = _scan_fixture("implement.yml collision", "implement.yml",
                              implement_collision, root)
    if not failures:
        failed.append("(6b) implement.yml with cycle/retry sharing one "
                       "scratch-filename should FAIL (FR-006), it PASSED")
    else:
        print("ok    (6b) implement.yml's cycle/retry scratch-filename collision fails")

    retry_blanked = """\
      - name: Compose commit-message guidance (implement.retry)
        id: commit-guidance-retry
        uses: ./.github/actions/wing-commander-commit-message-guidance
        with:
          scratch-filename: implement-commit-message-retry.txt
"""
    implement_blanked = implement_ok.replace(retry_guidance_ok, retry_blanked)
    failures = _scan_fixture("implement.yml blanked extra-note", "implement.yml",
                              implement_blanked, root)
    if not failures:
        failed.append("(6c) implement.yml with retry's extra-note blanked "
                       "should FAIL (FR-013), it PASSED")
    else:
        print("ok    (6c) implement.yml's retry with a blanked extra-note fails")

    import shutil
    shutil.rmtree(root, ignore_errors=True)

    if failed:
        print(f"::error::Gate 99 self-test: {len(failed)} check(s) behaved "
              f"wrongly: {'; '.join(failed)}. Gate 99's detection logic does "
              f"not do what its name claims, so a green Gate 99 on the real "
              f"fleet means nothing.")
        return 1
    print("Gate 99 self-test: all checks behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
