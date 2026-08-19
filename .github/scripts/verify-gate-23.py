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
