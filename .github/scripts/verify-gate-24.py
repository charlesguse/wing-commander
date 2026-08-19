#!/usr/bin/env python3
"""Gate 24 — a guard may not strand the degradation path it fires on.

WHY THIS EXISTS
---------------
`continue-on-error: true` on a step is a statement with a consequence: this
step failing must not kill the job, because something BELOW it handles the
failure. A later step that hard-exits on that same failure silently revokes
the statement. GitHub's job status flips to failure, and every subsequent
step whose `if:` lacks always()/!cancelled()/failure() is skipped — including
steps with no `if:` at all, which carry an implicit success(). The handler
the tolerance was added for is exactly such a step, so it becomes
unreachable dead code while still reading, top to bottom, as a correct and
present safety net.

Five sites shipped that way in one PR (#221), all the same shape: a new
`Fail loud on non-healthy agent verdict` inserted between an agent step that
was ALREADY `continue-on-error: true` and the deterministic fallback that
tolerance existed for.

  cleanup.yml teardown-done         the fallback summary text, closing the
                                    lifecycle issue, stage:done, deleting
                                    five pipeline branches
  finalize.yml finalize             `Verify agent output`, so `failed` was
                                    never set and the always()-gated failure
                                    callout skipped anyway
  auto-update-spec-kit evaluate-path `Read back decision` -> needs-migration
                                    human routing
  auto-update-spec-kit e2e-stage    `Read back stage result` -> all pass/fail
                                    reporting for the candidate
  auto-update-spec-kit comment-reply `Read back interpretation` -> the "ask
                                    for a clearer reply" prompt

Gate 23 cannot catch this. It checks that each agent call site HAS a
fail-loud step; it says nothing about where that step sits or what its
firing takes away. This gate is the placement half.

THE RULE, DELIBERATELY NARROW
-----------------------------
A step is a VIOLATION when all of:

  (a) it can `exit` non-zero and does not carry `continue-on-error: true`;
  (b) its `if:` fires ON a tolerated failure — a NEGATIVE test
      (`steps.<t>.outputs.x != '<lit>'`, or `steps.<t>.outcome == 'failure'`)
      of a step id in the tolerated closure: a `continue-on-error: true`
      step, or anything transitively reading one;
  (c) a LATER step in the same job is unprotected (no always()/!cancelled()/
      failure()), reads that SAME tolerated id, and is not mutually
      exclusive with the guard's own firing condition.

Every clause is doing work, and each one is what keeps this gate green
against a fleet full of legitimate hard exits:

  (b) excludes `Fail on agent API error` (clarify.yml, pr-conversation.yml),
      which is gated `verdict == 'healthy'` — it fires on the tolerated
      signal's SUCCESS, for an independent reason (a bad result shape), and
      stranding everything below it is that step's whole point. A literal of
      'skipped' is likewise not a failure test but a skip guard
      (`steps.agent.outcome != 'skipped'`), so it does not arm this gate.

  (c)'s "same tolerated id" is what separates a degradation path from
      ordinary downstream work. `tasks.yml`'s fail-loud does strand `Flip
      stage label` and `Dispatch implement stage` — correctly: a failed
      tasks agent SHOULD stop both. Neither reads the verdict the guard
      fired on. The read-backs and fallbacks in the five defects above all
      did.

  (c)'s mutual-exclusion test drops the pairing this fleet writes
      everywhere: a guard gated `verdict != 'healthy'` does not really
      strand a step gated `verdict == 'healthy'` — on the run the guard
      fires, that step was never going to execute anyway.

FOUR WAYS TO FIX A VIOLATION, ALL IN USE HERE
---------------------------------------------
  1. `continue-on-error: true` on the guard itself — the ::error:: lands
     where it belongs in the log and the degradation path below owns the
     run's outcome. 10 of the 19 agent sites, including all five above.
  2. Defer the guard to the job's last steps — intake.yml, so housekeeping
     completes and the run still ends red.
  3. `!cancelled()` on what must survive the guard — rebase.yml's
     abandon/escalate arm.
  4. Leave it: hard exit in place, because nothing below is a degradation
     path. 7 of the 19 sites. This gate is silent on those by construction.

Usage: python3 .github/scripts/verify-gate-24.py
"""
import glob
import re
import sys

import yaml

WORKFLOWS_GLOB = ".github/workflows/*.yml"
PROTECTED_RE = re.compile(r"always\s*\(\s*\)|!\s*cancelled\s*\(\s*\)"
                          r"|failure\s*\(\s*\)|\bcancelled\s*\(\s*\)")
EXIT_NONZERO_RE = re.compile(r"\bexit\s+[1-9]")
STEP_REF_RE = re.compile(r"steps\.\s*([A-Za-z0-9_-]+)\s*\.")
# `steps.<id>.outputs.<name>` / `steps.<id>.outcome` compared to a literal.
COMPARE_RE = re.compile(
    r"steps\.\s*([A-Za-z0-9_-]+)\s*\.\s*"
    r"(?:outputs\.\s*([A-Za-z0-9_-]+)|(outcome|conclusion))\s*"
    r"(==|!=)\s*['\"]([^'\"]*)['\"]")
# A skip guard, not a failure test. `steps.<agent>.outcome != 'skipped'` is
# the convention Gate 23 REQUIRES on every fail-loud step, so reading it as
# "fires on a tolerated failure" would arm this gate at all 19 sites.
SKIP_LITERAL = "skipped"
FAILURE_OUTCOMES = {"failure", "cancelled"}

failures = []


def fail(path, job_name, msg):
    failures.append((path, job_name, msg))
    print(f"::error file={path}::Gate 24: {job_name}: {msg}")


def note(msg):
    print(f"note: {msg}")


class LineLoader(yaml.SafeLoader):
    """SafeLoader that records each mapping's source line as `__line__`.

    A finding nobody can jump to is a finding nobody acts on, and a step's
    name is not unique within a workflow — five files here carry more than
    one `Fail loud on non-healthy agent verdict`.
    """


def _construct_mapping(loader, node, deep=False):
    mapping = yaml.SafeLoader.construct_mapping(loader, node, deep=deep)
    mapping["__line__"] = node.start_mark.line + 1
    return mapping


LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def truthy(value):
    return str(value).strip().lower() == "true"


def step_label(step, index):
    name = step.get("name") or step.get("id") or step.get("uses")
    return str(name) if name else f"step[{index}]"


def step_refs(step):
    """Every `steps.<id>` this step reads, from wherever it reads it.

    `if:`, `run:`, `env:` and `with:` all count. The read-backs in three of
    the five defects reached the verdict through `env:`, not through their
    condition, so a checker that only parsed `if:` would have missed them.
    """
    blob = " ".join(str(step.get(key) or "") for key in ("if", "run"))
    for key in ("env", "with"):
        section = step.get(key)
        if isinstance(section, dict):
            blob += " " + " ".join(str(v) for v in section.values())
    return set(STEP_REF_RE.findall(blob))


def tolerated_closure(steps):
    """The ids whose failure this job declared survivable, plus everything
    transitively reading them.

    Transitive on purpose: a fail-loud step reads a verdict step, which
    reads the continue-on-error agent step, and it is the AGENT step's
    failure all three are ultimately about.
    """
    tainted = set()
    for step in steps:
        if isinstance(step, dict) and truthy(step.get("continue-on-error")) \
                and step.get("id"):
            tainted.add(str(step["id"]))
    changed = True
    while changed:
        changed = False
        for step in steps:
            if not isinstance(step, dict) or not step.get("id"):
                continue
            sid = str(step["id"])
            if sid in tainted:
                continue
            if step_refs(step) & tainted:
                tainted.add(sid)
                changed = True
    return tainted


def comparisons(step):
    """{(step_id, field, operator, literal)} parsed out of this step's `if:`."""
    return {(sid, output or attr, op, literal)
            for sid, output, attr, op, literal
            in COMPARE_RE.findall(str(step.get("if") or ""))}


def fires_on(step, tolerated):
    """The tolerated ids this step's `if:` tests NEGATIVELY — the signals it
    turns into a red job. See clause (b) in this script's header."""
    out = set()
    for sid, field, op, literal in comparisons(step):
        if sid not in tolerated or literal == SKIP_LITERAL:
            continue
        if op == "!=" or (field in ("outcome", "conclusion")
                          and literal in FAILURE_OUTCOMES):
            out.add(sid)
    return out


def is_protected(step):
    """Would this step still run after an earlier step failed the job?"""
    return bool(PROTECTED_RE.search(str(step.get("if") or "")))


def is_moot(guard, step):
    """True when this step could not have run anyway on the run that fires
    the guard, so the guard stranding it costs nothing.

    Conservative in the safe direction: an exclusion this parser cannot see
    reads as "not moot", i.e. as something to report.
    """
    negatives = {(sid, field, literal)
                 for sid, field, op, literal in comparisons(guard)
                 if op == "!="}
    positives = {(sid, field, literal)
                 for sid, field, op, literal in comparisons(step)
                 if op == "=="}
    return bool(negatives & positives)


def check_job(path, job_name, steps):
    tolerated = tolerated_closure(steps)
    if not tolerated:
        return 0
    guards = 0
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if truthy(step.get("continue-on-error")):
            continue
        if not EXIT_NONZERO_RE.search(str(step.get("run") or "")):
            continue
        signals = fires_on(step, tolerated)
        if not signals:
            continue
        guards += 1
        guard_label = step_label(step, i)
        guard_line = step.get("__line__", "?")
        clean = True
        for j, later in enumerate(steps[i + 1:], start=i + 1):
            if not isinstance(later, dict) or is_protected(later):
                continue
            if not (step_refs(later) & signals):
                continue
            if is_moot(step, later):
                continue
            clean = False
            fail(path, job_name,
                 f"{guard_label!r} (line {guard_line}) hard-exits on "
                 f"{', '.join('steps.' + s for s in sorted(signals))}, whose "
                 f"failure a continue-on-error step above it declared "
                 f"survivable — and that failure then SKIPS "
                 f"{step_label(later, j)!r} (line "
                 f"{later.get('__line__', '?')}), which reads the same "
                 f"signal and is therefore the degradation path for it. "
                 f"Either give the guard continue-on-error: true and let "
                 f"that step own the outcome, defer the guard to the end of "
                 f"the job, or gate that step on !cancelled().")
        if clean:
            note(f"{path}: job {job_name!r}: {guard_label!r} (line "
                 f"{guard_line}) fires on a tolerated failure and strands no "
                 f"step that reads it.")
    return guards


def main():
    guards = 0
    paths = sorted(glob.glob(WORKFLOWS_GLOB))
    for path in paths:
        try:
            wf = yaml.load(open(path, encoding="utf-8"), Loader=LineLoader) or {}
        except yaml.YAMLError as exc:
            # Not a bare `continue`: an unreadable workflow is an unchecked
            # workflow, which is how a file stops being covered without
            # anyone noticing (Gate 23's stated reasoning).
            failures.append((path, "-", "unparseable"))
            print(f"::error file={path}::Gate 24: could not parse this "
                  f"workflow as YAML ({exc}) — cannot confirm its guards do "
                  f"not strand a degradation path, so this gate fails rather "
                  f"than silently dropping the file from coverage.")
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            # LineLoader stamps `__line__` into every mapping, including the
            # `jobs:` mapping itself — so one "job" in this loop is an int.
            if job_name == "__line__" or not isinstance(job, dict):
                continue
            guards += check_job(path, job_name, job.get("steps") or [])

    print(f"Gate 24: {len(paths)} workflow(s), {guards} guard(s) firing on a "
          f"tolerated failure; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
