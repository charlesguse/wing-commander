#!/usr/bin/env python3
"""Gate 23 dispatcher — two unrelated features independently landed a
"Gate 23" (specs/037-agent-turn-budget-guard and
specs/038-runner-container-passthrough) and both named their script
.github/scripts/verify-gate-23.py. Rather than let one silently clobber the
other at rebase time, this file holds both bodies verbatim and dispatches on
an argument, so lint-workflows.yml's two "Gate 23" steps each keep the exact
behavior they shipped with.

    python3 .github/scripts/verify-gate-23.py             -> 037's Gate 23:
        every agent call site carries the full turn-budget protection.
    python3 .github/scripts/verify-gate-23.py --selftest   -> 038's Gate 23
        self-test: the image-prerequisites gate's detector actually detects.

Each body below is the complete, unmodified source of the script that used
to live at this path on its own branch, compiled and executed in its own
fresh namespace so the two scripts' many same-named helpers (main, note,
job, stage, ...) never collide with each other.
"""
import os
import sys

_TURN_BUDGET_GATE_SOURCE = r'''
"""Gate 23 — every agent call site carries the full turn-budget protection.

WHY THIS EXISTS
----------------
The defect this whole feature (specs/037-agent-turn-budget-guard/) exists to
fix was fixed once, by hand, at one site (auto-update-spec-kit.yml's
`decide`, 15->30) and re-hit 31 hours later at a different, unfixed site
(clarify.yml, run 31918153816, issue #204). "Fixed at every site I remembered
to check" is exactly the failure mode that produced that gap. This gate
enumerates every in-scope site DYNAMICALLY (YAML-parsed, never grepped, so a
site written in flow style or unusual indentation is not silently missed —
Gate 7's stated rationale for the same choice) and asserts each one still
carries the full ceiling/verdict/fail-loud wiring, so a new site that skips
it, or an existing site whose ceiling regresses back to a literal
`inputs.max-turns` passthrough (User Story 3 Acceptance Scenario 3), fails by
name instead of silently shipping.

WHAT COUNTS AS IN SCOPE
------------------------
Every step, in every job, in every .github/workflows/*.yml file, whose `uses`
starts with `anthropics/claude-code-action` AND whose `claude_args` contains
`--max-turns`. Steps without `--max-turns` (claude.yml, claude-code-review.yml
as of this writing) are out of scope by design (research.md R8) — a step
with no turn cap cannot experience the upstream defect this feature works
around.

WHAT EACH IN-SCOPE SITE MUST HAVE, ALL FOUR
--------------------------------------------
(a) A `wing-commander-turn-ceiling` step earlier in the same job (only other
    non-agent-step setup between them), and the site's `--max-turns` value is
    EXACTLY `${{ steps.<that-step-id>.outputs.ceiling }}` — never a literal,
    never a raw `inputs.max-turns` passthrough, and never a ceiling step
    whose `multiplier` is `1` or less (T025). A multiplier of 1 makes the
    ceiling equal the intended budget, which is a `--max-turns
    ${{ inputs.max-turns }}` passthrough wearing the composite's clothes —
    the agent gets cut off at exactly the budget this feature exists to stop
    it being cut off at.
(b) `continue-on-error: true` on the agent step itself.
(c) A `wing-commander-agent-verdict` step later in the same job, `if:`
    containing `always()`, before any step that reads its outputs.
(d) A later step in the same job, gated `if: ... always() ... != 'healthy'`
    (referencing that verdict step's `verdict` output), whose body both
    prints an `::error::`-shaped message and can exit non-zero.
(e) BOTH of those steps skip-guarded on `steps.<agent-id>.outcome !=
    'skipped'` and on NOTHING ELSE — no restatement of the agent step's own
    `if:` conditions. This one is not cosmetic. `always()` alone means the
    verdict step runs even when the agent step was legitimately skipped; it
    then finds no transcript, answers `unclassifiable`, and the fail-loud
    arm in (d) fails an otherwise-green job. Restating a SUBSET of the agent
    step's guards instead is the same bug with extra steps — it papers over
    the skips it happens to name and drifts the moment either side gains a
    condition. Two sites shipped with exactly that drift (finalize.yml's
    idempotent no-diff re-run, auto-update-spec-kit.yml's deduped run; PR
    #221 review). The agent step's own `outcome` already reflects every
    guard on that step, so it is the one guard that cannot drift by
    construction.

Usage: python3 .github/scripts/verify-gate-23.py
"""
import glob
import os
import re
import sys

import yaml

WORKFLOWS_GLOB = ".github/workflows/*.yml"
AGENT_USES_PREFIX = "anthropics/claude-code-action"
CEILING_USES = "wing-commander-turn-ceiling"
VERDICT_USES = "wing-commander-agent-verdict"

failures = []


def fail(site, msg):
    failures.append((site, msg))
    print(f"::error file={site[0]}::Gate 23: {site[1]}/{site[2]}: {msg}")


def note(msg):
    print(f"note: {msg}")


def step_uses(step, needle):
    return needle in str((step or {}).get("uses") or "")


def is_agent_step(step):
    return step_uses(step, AGENT_USES_PREFIX) \
        and "--max-turns" in str((step.get("with") or {}).get("claude_args") or "")


def is_ceiling_step(step):
    return step_uses(step, CEILING_USES)


def is_verdict_step(step):
    return step_uses(step, VERDICT_USES)


def truthy(value):
    return str(value).strip().lower() == "true"


def find_ceiling_ref(steps, agent_idx, prev_agent_idx):
    """The wing-commander-turn-ceiling step closest to (but before)
    agent_idx, bounded below by the PRIOR agent step in this job (exclusive)
    so a multi-agent job cannot borrow a sibling site's ceiling step.
    Returns (id, step) — the step itself so its `multiplier` can be checked."""
    for j in range(agent_idx - 1, prev_agent_idx, -1):
        step = steps[j]
        if is_ceiling_step(step):
            return step.get("id"), step
        if is_agent_step(step):
            break
    return None, None


def check_multiplier(site, ceiling_step):
    """A declared multiplier must exceed 1. Omitted is fine — the action's own
    default (2.5) applies. An expression (`${{ ... }}`) is not statically
    knowable here, so it passes; the action validates at runtime."""
    raw = (ceiling_step.get("with") or {}).get("multiplier")
    if raw is None:
        return True
    text = str(raw).strip()
    if "${{" in text:
        return True
    try:
        value = float(text)
    except ValueError:
        fail(site, f"the ceiling step declares multiplier: {text!r}, which "
                   f"is not a number.")
        return False
    if value <= 1:
        fail(site, f"the ceiling step declares multiplier: {text} — a "
                   f"multiplier of 1 or less makes the ceiling equal to (or "
                   f"smaller than) the intended budget, which is the raw "
                   f"--max-turns passthrough this gate rejects in the first "
                   f"place, just routed through the composite.")
        return False
    return True


def find_verdict_step(steps, agent_idx, next_agent_idx):
    """The first wing-commander-agent-verdict step after agent_idx, bounded
    above by the NEXT agent step in this job (exclusive)."""
    for j in range(agent_idx + 1, next_agent_idx):
        step = steps[j]
        if is_verdict_step(step):
            return j, step
        if is_agent_step(step):
            break
    return None, None


FAIL_LOUD_VERDICT_REF = re.compile(
    r"steps\.\s*([A-Za-z0-9_-]+)\s*\.\s*outputs\.\s*verdict\s*!=\s*['\"]healthy['\"]")


def find_fail_loud(steps, verdict_idx, next_agent_idx, verdict_id):
    """The fail-loud step itself, not just a boolean — requirement (e) has to
    inspect its `if:`, so the caller needs the step rather than a yes/no."""
    for j in range(verdict_idx + 1, next_agent_idx):
        step = steps[j]
        cond = str(step.get("if") or "")
        if "always()" not in cond:
            continue
        m = FAIL_LOUD_VERDICT_REF.search(cond)
        if not m or m.group(1) != verdict_id:
            continue
        run = str(step.get("run") or "")
        if "::error" in run and re.search(r"\bexit\s+[1-9]", run):
            return step
    return None


STEP_REF = re.compile(r"steps\.\s*([A-Za-z0-9_-]+)\s*\.")


def skip_guard_re(agent_id):
    return re.compile(
        r"steps\.\s*" + re.escape(agent_id)
        + r"\s*\.\s*outcome\s*!=\s*['\"]skipped['\"]")


def check_skip_guard(site, label, step, agent_id, also_allowed):
    """Requirement (e): this step carries the agent step's outcome guard and
    references no other step's state. Position within the `&&` chain is not
    checked — `always() && steps.x.outcome != 'skipped'` and the reverse are
    the same expression, and two shipped sites legitimately write it the
    other way round."""
    cond = str((step or {}).get("if") or "")
    ok = True
    if not skip_guard_re(agent_id).search(cond):
        fail(site, f"the {label} step is not skip-guarded on "
                   f"steps.{agent_id}.outcome != 'skipped' — when the agent "
                   f"step is legitimately skipped, this step still runs, "
                   f"finds no transcript, and turns a green path red.")
        ok = False
    strays = sorted(set(STEP_REF.findall(cond)) - ({agent_id} | set(also_allowed)))
    if strays:
        fail(site, f"the {label} step's if: also references "
                   f"{', '.join('steps.' + r for r in strays)} — a "
                   f"hand-copied subset of the agent step's own conditions, "
                   f"which drifts. steps.{agent_id}.outcome != 'skipped' "
                   f"already reflects every guard on the agent step; drop "
                   f"the rest.")
        ok = False
    return ok


def check_max_turns_ref(claude_args, ceiling_id):
    pattern = re.compile(
        r"--max-turns\s+\$\{\{\s*steps\.\s*" + re.escape(ceiling_id)
        + r"\s*\.\s*outputs\.\s*ceiling\s*\}\}")
    return bool(pattern.search(claude_args))


def check_job(path, job_name, steps):
    agent_indices = [i for i, s in enumerate(steps) if is_agent_step(s)]
    for pos, agent_idx in enumerate(agent_indices):
        step = steps[agent_idx]
        step_id = step.get("id") or step.get("name") or f"step[{agent_idx}]"
        site = (path, job_name, step_id)
        prev_agent_idx = agent_indices[pos - 1] if pos > 0 else -1
        next_agent_idx = agent_indices[pos + 1] if pos + 1 < len(agent_indices) else len(steps)

        claude_args = str((step.get("with") or {}).get("claude_args") or "")

        ceiling_id, ceiling_step = find_ceiling_ref(steps, agent_idx,
                                                    prev_agent_idx)
        ok = True
        if ceiling_step is not None and not check_multiplier(site,
                                                             ceiling_step):
            ok = False
        if not ceiling_id:
            fail(site, "no wing-commander-turn-ceiling step precedes this "
                       "agent step in the same job — --max-turns has no "
                       "ceiling composite to derive from.")
            ok = False
        elif not check_max_turns_ref(claude_args, ceiling_id):
            fail(site, f"--max-turns does not resolve to "
                       f"${{{{ steps.{ceiling_id}.outputs.ceiling }}}} — it "
                       f"is a literal or a raw passthrough instead of the "
                       f"ceiling composite's output.")
            ok = False

        if not truthy(step.get("continue-on-error")):
            fail(site, "the agent step is missing continue-on-error: true.")
            ok = False

        agent_id = step.get("id")
        if not agent_id:
            fail(site, "the agent step has no `id:` — without one nothing "
                       "downstream can skip-guard on its outcome (see (e) "
                       "in this script's header).")
            ok = False

        verdict_idx, verdict_step = find_verdict_step(steps, agent_idx, next_agent_idx)
        verdict_id = None
        if verdict_step is None:
            fail(site, "no wing-commander-agent-verdict step follows this "
                       "agent step in the same job.")
            ok = False
        else:
            verdict_id = verdict_step.get("id")
            if "always()" not in str(verdict_step.get("if") or ""):
                fail(site, "the wing-commander-agent-verdict step is not "
                           "gated if: always() — it would be skipped on a "
                           "non-success outcome.")
                ok = False
            if agent_id and not check_skip_guard(
                    site, "wing-commander-agent-verdict", verdict_step,
                    agent_id, ()):
                ok = False

        if verdict_id:
            fail_loud = find_fail_loud(steps, verdict_idx, next_agent_idx,
                                       verdict_id)
            if fail_loud is None:
                fail(site, f"no fail-loud step found: expected a later step "
                           f"in the same job gated "
                           f"if: always() && steps.{verdict_id}.outputs."
                           f"verdict != 'healthy', printing ::error and "
                           f"exiting non-zero.")
                ok = False
            elif agent_id and not check_skip_guard(
                    site, "fail-loud", fail_loud, agent_id, (verdict_id,)):
                ok = False

        if ok:
            note(f"{path}: job {job_name!r}, step {step_id!r}: full "
                 f"ceiling/verdict/fail-loud coverage confirmed "
                 f"(ceiling step {ceiling_id!r}, verdict step "
                 f"{verdict_id!r})")


def main():
    in_scope = 0
    for path in sorted(glob.glob(WORKFLOWS_GLOB)):
        try:
            wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            # Not a bare `continue`: dropping the file from coverage while
            # still returning 0 is how a workflow stops being checked
            # without anyone noticing. An unreadable workflow is an
            # unchecked workflow, which is the exact outcome this gate
            # exists to prevent.
            failures.append(((path, "-", "-"), "unparseable"))
            print(f"::error file={path}::Gate 23: could not parse this "
                 f"workflow as YAML ({exc}) — cannot confirm its agent call "
                 f"sites are protected, so this gate fails rather than "
                 f"silently dropping the file from coverage.")
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            steps = (job or {}).get("steps") or []
            agent_count = sum(1 for s in steps if is_agent_step(s))
            if agent_count == 0:
                continue
            in_scope += agent_count
            check_job(path, job_name, steps)

    if in_scope == 0:
        print("::error::Gate 23: found zero in-scope agent call sites "
             "(a claude-code-action step declaring --max-turns) across "
             "every .github/workflows/*.yml file. Either every such step "
             "was removed, or this gate's detection is broken — both are "
             "worth stopping the build over.")
        return 1

    print(f"Gate 23: {in_scope} in-scope site(s) checked; "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
'''

_IMAGE_PREREQ_SELFTEST_SOURCE = r'''
"""Self-test for lint-workflows.yml's Gate 23.

Gate 23 asserts two things (specs/038-runner-container-passthrough):
  1. every published stage declares verify-image-prerequisites, gated on
     `if: inputs.container-image != ''` with no container: of its own, and
     every entry job / always()/!cancelled()-style survival job depends on
     it via the skip-tolerant if: (FR-006, FR-010, FR-011).
  2. the canonical required-tool list (.github/scripts/required-tools.txt)
     is not missing a tool a run: block anywhere in the repository actually
     invokes (FR-011a's drift check).

The fleet it guards is uniform today and should stay that way, so the gate
will print "0 failure(s)" forever — whether its detection works or not. This
script feeds Gate 23 synthetic fixtures that each carry one known defect (or
one known NON-defect) and asserts the verdict, including what the error text
names — same discipline as verify-gate-7.py / verify-gate-22.py.

Drift-proofing: the gate's source is EXTRACTED from lint-workflows.yml at run
time rather than copied here, so there is no second copy to fall out of sync.

Usage: python3 .github/scripts/verify-gate-23.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
STEP_PREFIX = "Gate 23"
HEREDOC_OPEN = "python3 - <<'PYEOF'"
HEREDOC_CLOSE = "PYEOF"


def extract_gate(path=LINT_WORKFLOW):
    """Return Gate 23's python source, read out of the shipped workflow."""
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    run = None
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name", "")
            if name.startswith(STEP_PREFIX) and "self-test" not in name:
                run = step.get("run")
    if run is None:
        sys.exit(f"::error file={path}::verify-gate-23 could not find a step named "
                 f"{STEP_PREFIX!r}. If it was renamed, update this script and the "
                 f"workflow together.")

    lines = run.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == HEREDOC_OPEN)
        end = next(i for i, l in enumerate(lines)
                   if i > start and l.strip() == HEREDOC_CLOSE)
    except StopIteration:
        sys.exit(f"::error file={path}::verify-gate-23 found the {STEP_PREFIX} step but "
                 f"not the {HEREDOC_OPEN} ... {HEREDOC_CLOSE} block it keys on — the "
                 f"step's shape has changed.")
    return "\n".join(lines[start + 1:end]) + "\n"


# ---------------------------------------------------------------- fixtures

# Post-#224: verify-image-prerequisites never skips, so there is no
# skipped result to tolerate. A status-guarded job still has to check the
# check's result explicitly — its status function is what defeats ordinary
# skip-propagation — and an unguarded job must NOT restate it.
RESULT_GUARD = "needs.verify-image-prerequisites.result == 'success'"
STALE_TOLERANT = ("(needs.verify-image-prerequisites.result == 'success' || "
           "needs.verify-image-prerequisites.result == 'skipped')")


def yaml_str(s):
    """A YAML scalar guaranteed to parse back as the literal string `s`.

    Several fixture if: values start with `!` (e.g. `!cancelled()`), which
    YAML 1.1 reads as a custom tag, not the start of a string, and blows up
    the parse entirely rather than producing a wrong-but-parseable value.
    JSON double-quoted syntax is valid YAML flow-scalar syntax, so this is
    safe for every fixture string used here.
    """
    return json.dumps(s)


def canonical_tools():
    """The canonical list, read from the same file the harness copies into
    every fixture directory.

    So a fixture's embedded REQUIRED_TOOLS agrees with its own
    required-tools.txt by construction, and only the cases that MEAN to
    disagree do. Hardcoding the list here instead would make every fixture
    fail the moment the real list gained a tool — the kind of self-test that
    gets deleted rather than fixed.
    """
    tools = []
    for ln in io.open(os.path.join(".github", "scripts", "required-tools.txt"),
                      encoding="utf-8"):
        t = ln.split("#", 1)[0].strip()
        if t:
            tools.append(t)
    return " ".join(tools)


CANONICAL = object()   # sentinel: "the real list", vs None = "no list at all"


def vip_job(if_expr=None, step_if="inputs.container-image != ''",
            with_container=False, tools=CANONICAL, quote='"'):
    """The check job. `if_expr` is the DEFECT case (#224): a job-level
    condition here skips the job, and a skipped job takes its whole
    descendant closure with it. The healthy shape conditions the step."""
    lines = ["  verify-image-prerequisites:"]
    if if_expr is not None:
        lines.append(f"    if: {yaml_str(if_expr)}")
    lines.append("    runs-on: ubuntu-latest")
    if with_container:
        lines.append("    container:\n      image: alpine")
    lines += ["    steps:"]
    if step_if is not None:
        lines.append(f"      - if: {yaml_str(step_if)}")
        lines.append("        run: |")
    else:
        lines.append("      - run: |")
    if tools is CANONICAL:
        tools = canonical_tools()
    if tools is not None:
        lines.append(f"          REQUIRED_TOOLS={quote}{tools}{quote}")
    lines.append("          echo check")
    return "\n".join(lines) + "\n"


def job(name, needs=None, if_expr=None, run="echo work"):
    lines = [f"  {name}:"]
    if needs:
        needs_str = needs if isinstance(needs, str) else "[" + ", ".join(needs) + "]"
        lines.append(f"    needs: {needs_str}")
    if if_expr:
        lines.append(f"    if: {yaml_str(if_expr)}")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    steps:")
    lines.append("      - run: |")
    for l in run.splitlines():
        lines.append(f"          {l}")
    return "\n".join(lines) + "\n"


def stage(*jobs, vip=None, inputs_needed=True):
    if vip is None:
        vip = vip_job()
    inputs = ("    inputs:\n      container-image:\n        type: string\n"
             "        required: false\n        default: \"\"\n") if inputs_needed else ""
    return (f"name: stage\non:\n  workflow_call:\n{inputs}"
            f"jobs:\n{vip}{''.join(jobs)}")


PLAIN_WORKFLOW = """\
name: not a stage
on:
  pull_request: {}
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo no wiring here, and none wanted
"""

CALLER_JOB = """\
  call-other:
    uses: ./.github/workflows/other.yml
"""

HEALTHY_ENTRY = job("entry", needs="verify-image-prerequisites")

WIRING_CASES = [
    # name, files, expect_fail, must_mention
    ("healthy: entry job correctly wired to verify-image-prerequisites",
     {"stage.yml": stage(HEALTHY_ENTRY)},
     False, ()),

    ("the defect this gate exists for: entry job has no needs: at all",
     {"stage.yml": stage(job("entry"))},
     True, ("'entry'", "entry job")),

    ("the #224 defect: an entry job restates the check's result with no "
     "status function, so GitHub never reads it",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             if_expr=STALE_TOLERANT))},
     True, ("'entry'", "never read")),

    ("no false positive: an entry job may carry an unrelated condition",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             if_expr="inputs.trigger == 'scheduled'"))},
     False, ()),

    ("a downstream job with no status-check function inherits automatically "
     "and needs no separate wiring",
     {"stage.yml": stage(HEALTHY_ENTRY, job("downstream", needs="entry"))},
     False, ()),

    ("the always()-survivor defect: needs the upstream job but not "
     "verify-image-prerequisites directly, defeating skip propagation",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         job("survivor", needs="entry", if_expr="always()"))},
     True, ("'survivor'", "status-check function")),

    ("an always()-survivor correctly wired directly to verify-image-prerequisites",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         job("survivor", needs=["entry", "verify-image-prerequisites"],
                             if_expr=f"always() && {RESULT_GUARD}"))},
     False, ()),

    ("a survivor wired to the check but not guarding on its result would "
     "run straight past a failed pull",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         job("survivor", needs=["entry", "verify-image-prerequisites"],
                             if_expr="always()"))},
     True, ("'survivor'", "unchecked")),

    ("a !cancelled() survivor is guarded exactly like an always() survivor",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         job("survivor", needs="entry", if_expr="!cancelled()"))},
     True, ("'survivor'",)),

    ("verify-image-prerequisites job missing entirely",
     {"stage.yml": ("name: stage\non:\n  workflow_call:\n    inputs:\n"
                    "      container-image:\n        type: string\n"
                    "        required: false\n        default: \"\"\n"
                    "jobs:\n" + job("only", needs="verify-image-prerequisites"))},
     True, ("no verify-image-prerequisites job",)),

    ("the other half of #224: the check job is skip-conditioned, which "
     "silently suppresses the whole stage",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         vip=vip_job(if_expr="inputs.container-image != ''"))},
     True, ("must never skip",)),

    ("the check job runs unconditionally but its step is not conditioned, "
     "so a run naming no image would try to pull nothing",
     {"stage.yml": stage(HEALTHY_ENTRY, vip=vip_job(step_if=None))},
     True, ("every step of",)),

    ("verify-image-prerequisites declares its own container: block",
     {"stage.yml": stage(HEALTHY_ENTRY, vip=vip_job(with_container=True))},
     True, ("its own container",)),

    ("no false positive: a workflow that is not a published stage",
     {"lint.yml": PLAIN_WORKFLOW},
     True, ("checked nothing",)),

    ("no false positive: a job that calls another workflow needs no wiring",
     {"stage.yml": stage(HEALTHY_ENTRY) + CALLER_JOB},
     False, ()),
]

DRIFT_CASES = [
    ("the defect this gate exists for: an unrecognized tool is invoked and "
     "absent from the canonical list",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             run="somefancytool --check-version"))},
     True, ("somefancytool",)),

    ("no false positive: canonical tools (git, gh, jq, curl, python3, bash, node)",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             
                             run="git status && gh pr list && jq '.' f.json && "
                                 "curl -s url && python3 x.py && bash y.sh && node z.js"))},
     False, ()),

    ("no false positive: POSIX/coreutils/bash-builtin commands",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             
                             run="echo hi && mkdir -p /tmp/x && sed -n 1p f && "
                                 "grep foo f | sort | uniq"))},
     False, ()),

    ("no false positive: a maintenance-only tool this repo's own CI uses, "
     "never a published stage's adopter-facing image",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             run="docker build -t x ."))},
     False, ()),

    ("heredoc bodies are not scanned for command tokens — a look-alike word "
     "inside an embedded python/jq/js script must not be flagged",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             
                             run="python3 - <<'PYEOF'\n"
                                 "somefancytool --this-is-python-source-not-shell\n"
                                 "PYEOF"))},
     False, ()),

    ("drift is repository-wide, not scoped to published stages — a plain "
     "workflow's run: block is scanned too",
     {"lint.yml": PLAIN_WORKFLOW.replace(
         "echo no wiring here, and none wanted",
         "somefancytool3 --lint")},
     True, ("somefancytool3",)),

    ("composite actions under .github/actions/** are scanned for drift too",
     {},
     True, ("somefancytool4",)),

    # FR-011a's other direction: each stage's EMBEDDED list must be the
    # canonical one. The drift scan above cannot see this — the embedded
    # list is a shell assignment (skipped as a VAR=value prefix, never
    # tokenized as an invocation) and the check loop iterates the variable
    # rather than the tool names — so until Gate 23 compared them, the
    # twelve copies agreed by hand-coordination alone.
    ("a stage whose embedded list drops a canonical tool",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         vip=vip_job(tools=canonical_tools().replace(" node", "")))},
     True, ("node", "not the canonical one")),

    ("a stage whose embedded list adds a tool the canonical list disowns",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         vip=vip_job(tools=canonical_tools() + " yq"))},
     True, ("yq", "not the canonical one")),

    ("a stage that embeds no REQUIRED_TOOLS list at all",
     {"stage.yml": stage(HEALTHY_ENTRY, vip=vip_job(tools=None))},
     True, ("REQUIRED_TOOLS",)),

    ("no false positive: the single-quoted assignment form is read too",
     {"stage.yml": stage(HEALTHY_ENTRY,
                         vip=vip_job(tools=canonical_tools(), quote="'"))},
     False, ()),

    # The tokenizer's own placeholders. strip_command_substitutions emits
    # DOLLARSUBST and the expression pass emits GHEXPR, both of which match
    # TOKEN_RE — so a statement STARTING with either idiom used to be
    # reported as "a run: block invokes dollarsubst", naming a tool that
    # does not exist.
    ("no false positive: a statement starting with a command substitution "
     "is not reported as an invocation of 'dollarsubst'",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             
                             run="$(command -v git) --version"))},
     False, ()),

    ("no false positive: a statement starting with an Actions expression "
     "is not reported as an invocation of 'ghexpr'",
     {"stage.yml": stage(job("entry", needs="verify-image-prerequisites",
                             
                             run="${{ inputs.runner }} --version"))},
     False, ()),
]


def norm(path):
    p = path.strip().replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def check_derivations_agree(gate_path):
    """Gate 23's inline stage detection vs the shared wc_published_stages module.

    Same reasoning as verify-gate-7.py / verify-gate-22.py: a stage visible
    to one derivation and invisible to the other is issue #149 again.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from wc_published_stages import published_stages
    except ImportError as exc:
        return [("shared stage derivation", [f"cannot import "
                 f"wc_published_stages ({exc}); release.yml's pass 1 depends "
                 f"on it"], "")]

    module_stages = {norm(p) for p in published_stages()}
    proc = subprocess.run([sys.executable, gate_path], cwd=".",
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"Gate 23: (\d+) published stage\(s\)", out)
    if not m:
        return [("shared stage derivation",
                 ["could not read the stage count out of Gate 23's own output; "
                  "its summary line has changed shape"], out.strip())]

    gate_count = int(m.group(1))
    gate_stages = {norm(p) for p in
                   re.findall(r"^note: (.+): published stage$", out, re.M)}
    if len(gate_stages) != gate_count:
        return [("shared stage derivation", [
            f"Gate 23's summary says {gate_count} published stage(s) but it "
            f"named {len(gate_stages)} of them."], out.strip())]

    if gate_stages != module_stages:
        only_gate = sorted(gate_stages - module_stages)
        only_module = sorted(module_stages - gate_stages)
        return [("shared stage derivation", [
            f"Gate 23 and wc_published_stages.py disagree about which "
            f"workflows are published stages. Seen only by Gate 23: "
            f"{only_gate or '(none)'}. Seen only by wc_published_stages.py: "
            f"{only_module or '(none)'}."], "")]
    print(f"ok    the shared stage derivation agrees with Gate 23 "
          f"({gate_count} published stages)")
    return []


def check_real_fleet(gate_path):
    """Gate 23 must actually PASS against this repository's own real files.

    Covers both halves at once: the wiring check against the eleven real
    stages (T029/T033) AND the FR-011a drift check against every real run:
    block in .github/workflows and .github/actions — the fixtures above
    prove the DETECTOR works; this proves the thing it detects on has
    actually been fixed, and that the drift check's allowlists are wide
    enough not to false-positive on this repository's own scripts.
    """
    proc = subprocess.run([sys.executable, gate_path], cwd=".",
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return [("Gate 23 against the real repository",
                 ["Gate 23 fails when run against this repository's own "
                  "real workflows/actions — the fixtures above can be "
                  "green while the real surface is not."], out.strip())]
    print("ok    Gate 23 passes against this repository's own real fleet")
    return []


def main():
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate23_")
    gate_path = os.path.join(root, "gate23.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    tools_path = ".github/scripts/required-tools.txt"
    if not os.path.isfile(tools_path):
        sys.exit(f"::error::run this from the repository root; {tools_path} not found.")
    required_tools_text = io.open(tools_path, encoding="utf-8").read()

    failures = []

    def record(name, problems, out):
        failures.append((name, problems, out))
        print(f"FAIL  {name}")
        for problem in problems:
            print(f"        - {problem}")
        for line in (out or "").strip().splitlines():
            print(f"        | {line}")

    for name, problems, out in check_derivations_agree(gate_path):
        record(name, problems, out)
    for name, problems, out in check_real_fleet(gate_path):
        record(name, problems, out)

    all_cases = list(WIRING_CASES) + list(DRIFT_CASES)
    try:
        for name, files, expect_fail, must_mention in all_cases:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            wf_dir = os.path.join(case_dir, ".github", "workflows")
            scripts_dir = os.path.join(case_dir, ".github", "scripts")
            os.makedirs(wf_dir)
            os.makedirs(scripts_dir)
            io.open(os.path.join(scripts_dir, "required-tools.txt"), "w",
                   encoding="utf-8").write(required_tools_text)
            for fname, body in files.items():
                io.open(os.path.join(wf_dir, fname), "w", encoding="utf-8").write(body)

            # The composite-action fixture carries no `files` of its own —
            # it exercises the .github/actions/**/action.yml glob path
            # instead, alongside a minimal healthy stage so the wiring half
            # of the gate has something to pass on.
            if name.startswith("composite actions"):
                io.open(os.path.join(wf_dir, "stage.yml"), "w",
                       encoding="utf-8").write(stage(HEALTHY_ENTRY))
                act_dir = os.path.join(case_dir, ".github", "actions", "fancy")
                os.makedirs(act_dir)
                io.open(os.path.join(act_dir, "action.yml"), "w", encoding="utf-8").write(
                    "name: fancy\nruns:\n  using: composite\n  steps:\n"
                    "    - run: somefancytool4 --check\n      shell: bash\n")

            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            out = (proc.stdout or "") + (proc.stderr or "")
            fired = proc.returncode != 0

            problems = []
            if fired != expect_fail:
                problems.append(
                    f"expected the gate to {'FAIL' if expect_fail else 'PASS'}, "
                    f"it {'FAILED' if fired else 'PASSED'}")
            for token in must_mention:
                if token not in out:
                    problems.append(f"error text never mentions {token!r}")

            if problems:
                record(name, problems, out)
            else:
                print(f"ok    {name}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    total = len(all_cases) + 2
    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 23 self-test: "
              f"{len(failures)} of {total} check(s) behaved wrongly "
              f"({', '.join(name for name, _, _ in failures)}). Gate 23's "
              f"detection logic does not do what its name claims, so a green Gate 23 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 23 self-test: all {total} checks behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _run(source):
    # __file__ is NOT free here. exec() gives the compiled body only the
    # globals this dict holds, and 038's self-test resolves its sibling
    # modules with os.path.dirname(os.path.abspath(__file__)) — so without
    # it that body died on NameError before running a single check, and the
    # shipped "Gate 23 self-test" step exited 1 every time. Both bodies get
    # the dispatcher's own path, which is the path they had when they were
    # standalone files.
    namespace = {"__name__": "__main__", "__file__": os.path.abspath(__file__)}
    exec(compile(source, "<verify-gate-23>", "exec"), namespace)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _run(_IMAGE_PREREQ_SELFTEST_SOURCE)
    else:
        _run(_TURN_BUDGET_GATE_SOURCE)
