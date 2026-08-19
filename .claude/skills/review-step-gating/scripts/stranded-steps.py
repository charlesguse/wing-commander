#!/usr/bin/env python3
"""Guards that fire on a tolerated failure, and the steps they strand.

THE DEFECT CLASS
----------------
`continue-on-error: true` on a step is an explicit statement: "this step
failing must not kill the job, because something below it handles the
failure." A later step that hard-exits on that same failure silently revokes
the statement. GitHub's job status goes to failure, and every subsequent step
whose `if:` lacks always() / !cancelled() / failure() is skipped — including
steps with no `if:` at all, which carry an implicit success(). The handler
the `continue-on-error` was added for is exactly such a step, so it becomes
unreachable dead code, and a reviewer reading top-to-bottom sees a
degradation path that looks present and correct.

Five sites shipped that way in PR #221: cleanup.yml's teardown, finalize.yml's
failure callout, and auto-update-spec-kit.yml's three read-backs.

WHAT THIS REPORTS
-----------------
A step is FLAGGED when all four hold:

  1. it derives from a `continue-on-error: true` step in the same job —
     directly or transitively, through any `steps.<id>.` reference in its
     `if:`, `env:`, `with:` or `run:`;
  2. its `run:` block can `exit` non-zero;
  3. it does not itself carry `continue-on-error: true`;
  4. at least one later step in the job is unprotected, i.e. would be
     skipped when it fires.

Condition 1 is what keeps the output readable. Ordinary setup steps
(`Resolve pipeline ref`, `Verify spec artifacts`) also exit non-zero and also
strand everything below them — correctly, since nothing declared their
failure tolerable. Only a guard standing downstream of a declared-tolerable
failure is a contradiction worth a reviewer's attention.

This tool does not decide whether a flagged guard is wrong. Whether a
stranded step is a teardown that must complete, the degradation path the
`continue-on-error` exists for, or work that genuinely should not run is a
question about intent. The contribution is that nobody has to reconstruct the
list by eye.

Usage:
    python3 stranded-steps.py                        # every .github/workflows/*.yml
    python3 stranded-steps.py path/to/workflow.yml   # one or more explicit files
    python3 stranded-steps.py --all                  # drop condition 1 (noisy)
    python3 stranded-steps.py --quiet                # findings only, no notes

Exit status is always 0. This is a review aid, not a gate.
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


class LineLoader(yaml.SafeLoader):
    """SafeLoader that records each mapping's source line as `__line__`.

    A finding nobody can jump to is a finding nobody acts on, and a step's
    name is not unique within a workflow — five files here contain more than
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
    """Every `steps.<id>` this step reads, from wherever it reads it."""
    blob = " ".join(str(step.get(key) or "") for key in ("if", "run"))
    for key in ("env", "with"):
        section = step.get(key)
        if isinstance(section, dict):
            blob += " " + " ".join(str(v) for v in section.values())
    return set(STEP_REF_RE.findall(blob))


def tolerated_closure(steps):
    """(indices, ids) whose failure was declared survivable, plus everything
    reading them. Transitive on purpose: a fail-loud step reads a verdict
    step, which reads the continue-on-error agent step, and it is the AGENT
    step's failure all three are ultimately about."""
    tainted_ids, tainted_idx = set(), set()
    for i, step in enumerate(steps):
        if isinstance(step, dict) and truthy(step.get("continue-on-error")):
            tainted_idx.add(i)
            if step.get("id"):
                tainted_ids.add(str(step["id"]))
    changed = True
    while changed:
        changed = False
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or i in tainted_idx:
                continue
            if step_refs(step) & tainted_ids:
                tainted_idx.add(i)
                if step.get("id"):
                    tainted_ids.add(str(step["id"]))
                changed = True
    return tainted_idx, tainted_ids


def is_protected(step):
    """Would this step still run after an earlier step failed the job?"""
    return bool(PROTECTED_RE.search(str(step.get("if") or "")))


def comparisons(step):
    """{(operand, operator, literal)} parsed out of this step's `if:`."""
    out = set()
    for sid, output, attr, op, literal in COMPARE_RE.findall(
            str(step.get("if") or "")):
        out.add((f"steps.{sid}.{output or attr}", op, literal))
    return out


def signal_ids(guard, tainted_ids):
    """The TOLERATED step ids the guard's own `if:` tests.

    Restricted to the tolerated closure on purpose. Unrestricted, this picks
    up the ordinary job-shape guards every step in these workflows shares
    (`steps.guard.outputs.skip != 'true'`), and then every step below reads
    "the same signal" and the marker means nothing.
    """
    return {sid for sid, _out, _attr, _op, _lit
            in COMPARE_RE.findall(str(guard.get("if") or ""))} & tainted_ids


def handles_same_signal(guard, step, tainted_ids):
    """A stranded step that reads the very signal the guard fires on.

    This is the shape of a degradation path: something below the guard was
    written to look at the same verdict/outcome and do the survivable thing
    with it. Every one of the five PR #221 defects had one, and it is the
    single strongest hint that a finding is real rather than
    correct-by-design, so findings carrying one sort first.
    """
    return bool(step_refs(step) & signal_ids(guard, tainted_ids))


def is_moot(guard, step):
    """True when this step could not have run anyway on the run that fires
    the guard, so the guard stranding it costs nothing.

    The discriminator that separates the five real PR #221 defects from the
    dozen correct-by-design stranding sites. A guard gated
    `... verdict != 'healthy'` and a step gated `... verdict == 'healthy'`
    are mutually exclusive: on the run where the guard fires, that step was
    always going to be skipped, guard or no guard. A step with no such
    exclusion is one the guard genuinely takes away — and those are the ones
    that turned out to be teardowns and degradation paths.

    Conservative in the safe direction: an exclusion this simple parser
    cannot see reads as "not moot", i.e. as something to look at.
    """
    negatives = {(lhs, lit) for lhs, op, lit in comparisons(guard)
                 if op == "!="}
    positives = {(lhs, lit) for lhs, op, lit in comparisons(step)
                 if op == "=="}
    return bool(negatives & positives)


def check_job(path, job_name, steps, drop_taint_filter, findings, notes):
    tainted, tainted_ids = tolerated_closure(steps)
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if truthy(step.get("continue-on-error")):
            continue  # cannot fail the job, so strands nothing
        if not EXIT_NONZERO_RE.search(str(step.get("run") or "")):
            continue
        if i not in tainted and not drop_taint_filter:
            continue
        below = [(j, s) for j, s in enumerate(steps[i + 1:], start=i + 1)
                 if isinstance(s, dict) and not is_protected(s)]
        stranded = [(j, s, handles_same_signal(step, s, tainted_ids))
                    for j, s in below if not is_moot(step, s)]
        where = f"{path}:{step.get('__line__', '?')}"
        label = step_label(step, i)
        if not stranded:
            why = ("every step below it is always()/!cancelled()-protected"
                   if not below else
                   f"the {len(below)} unprotected step(s) below it are all "
                   f"gated on the condition this guard fires on NOT holding")
            notes.append(f"note: {where}: job {job_name!r}: {label!r} "
                         f"hard-exits on a tolerated failure, but {why} — "
                         f"nothing is stranded.")
            continue
        findings.append((where, job_name, label, stranded, len(below)))


def report(finding):
    where, job_name, label, stranded, below_count = finding
    print(f"\n{where}: job {job_name!r}")
    print(f"  guard: {label!r} hard-exits on a failure a continue-on-error "
          f"step above it declared survivable.")
    moot = below_count - len(stranded)
    also = (f" ({moot} more would have been skipped anyway)" if moot else "")
    print(f"  when it fires, these {len(stranded)} later step(s) in the same "
          f"job are SKIPPED{also}:")
    for j, s, reads_signal in stranded:
        cond = str(s.get("if") or "")
        shown = f"if: {cond}" if cond else "no if: (implicit success())"
        flag = "  <-- reads the same signal this guard fires on" \
            if reads_signal else ""
        print(f"    {s.get('__line__', '?'):>6}  {step_label(s, j)}{flag}")
        print(f"            {shown}")
    print("  ask: is any of those the degradation path the continue-on-error "
          "was added for, a teardown that must complete, or a "
          "maintainer-facing report?")


def main(argv):
    drop_taint_filter = "--all" in argv
    quiet = "--quiet" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        paths = sorted(glob.glob(WORKFLOWS_GLOB))

    findings, notes = [], []
    for path in paths:
        try:
            wf = yaml.load(open(path, encoding="utf-8"), Loader=LineLoader) or {}
        except yaml.YAMLError as exc:
            print(f"{path}: could not parse as YAML ({exc}) — skipped.")
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            # LineLoader stamps `__line__` into every mapping, including the
            # `jobs:` mapping itself — so one "job" in this loop is an int.
            if job_name == "__line__" or not isinstance(job, dict):
                continue
            check_job(path, job_name, job.get("steps") or [],
                      drop_taint_filter, findings, notes)

    # Findings whose stranded set contains a step reading the guard's own
    # signal go first: that is the degradation-path shape, and a reviewer
    # working top-down should meet the likely-real ones before the
    # correct-by-design ones.
    findings.sort(key=lambda f: (0 if any(r for _j, _s, r in f[3]) else 1,
                                 f[0]))
    for finding in findings:
        report(finding)
    if not quiet:
        if findings:
            print()
        for line in notes:
            print(line)
    print(f"\n{len(paths)} workflow(s): {len(findings)} guard(s) strand later "
          f"steps, {len(notes)} strand nothing.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
