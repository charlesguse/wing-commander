#!/usr/bin/env python3
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
    never a raw `inputs.max-turns` passthrough.
(b) `continue-on-error: true` on the agent step itself.
(c) A `wing-commander-agent-verdict` step later in the same job, `if:`
    containing `always()`, before any step that reads its outputs.
(d) A later step in the same job, gated `if: ... always() ... != 'healthy'`
    (referencing that verdict step's `verdict` output), whose body both
    prints an `::error::`-shaped message and can exit non-zero.

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
    """The wing-commander-turn-ceiling step id closest to (but before)
    agent_idx, bounded below by the PRIOR agent step in this job (exclusive)
    so a multi-agent job cannot borrow a sibling site's ceiling step."""
    for j in range(agent_idx - 1, prev_agent_idx, -1):
        step = steps[j]
        if is_ceiling_step(step):
            return step.get("id")
        if is_agent_step(step):
            break
    return None


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
            return True
    return False


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

        ceiling_id = find_ceiling_ref(steps, agent_idx, prev_agent_idx)
        ok = True
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

        if verdict_id:
            if not find_fail_loud(steps, verdict_idx, next_agent_idx, verdict_id):
                fail(site, f"no fail-loud step found: expected a later step "
                           f"in the same job gated "
                           f"if: always() && steps.{verdict_id}.outputs."
                           f"verdict != 'healthy', printing ::error and "
                           f"exiting non-zero.")
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
            print(f"::error file={path}::Gate 23: could not parse this "
                 f"workflow as YAML ({exc}); skipping.")
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
