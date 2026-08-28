#!/usr/bin/env python3
"""Shared extraction of a lint-workflows.yml gate's python source, drift-free.

WHY THIS EXISTS
---------------
Seven of lint-workflows.yml's self-tests (Gate 6, 7, 12, 15, 16, 22, 23) each
carried their own copy of the same ~25 lines: find the (last, non-self-test)
step named "Gate N", then find the `python3 - <<'PYEOF' ... PYEOF` heredoc
inside that step's `run:` block and return the source between the markers.
Running the SHIPPED gate this way — rather than a copy of it — is the whole
point (Gate 5 exists because a copy sat green for weeks while checking a
filter that did not ship), but the extraction plumbing itself does not need
to exist seven times to make that promise.

verify-gate-7.py used to explain the duplication this way: "the extractor is
duplicated rather than shared because a module whose filename contains
hyphens cannot be imported." That is true of one `verify-gate-N.py` trying to
import another — it is not true of a `wc_`-prefixed shared module, which is
exactly the same reasoning `wc_chain_stop_conditions.py` gives for existing.
This module is that fix applied to `extract_gate`.

Gate 18 is deliberately NOT one of the seven callers here. Its gate source
was moved out of the workflow heredoc entirely (#213) into a checked-in
script (`verify-gate-18-scan.py`); its "extraction" is just reading that
file's text, a different shape this module has no reason to cover.

Usage:
  from wc_lint_gate_source import extract_gate_step
  extract_gate_step(LINT_WORKFLOW, "Gate 15")
"""
import io
import sys

import yaml

HEREDOC_OPEN = "python3 - <<'PYEOF'"
HEREDOC_CLOSE = "PYEOF"


def extract_gate_step(path, step_prefix, caller=None):
    """Return a gate's python source, read out of its shipped workflow step.

    Walks every job's steps in `path` and keeps the LAST `run:` block whose
    step name starts with `step_prefix` and does not contain "self-test" —
    the fleet's convention is a "Gate N" step followed later in the same job
    list by a "Gate N self-test" step, and taking the last match (rather than
    stopping at the first) is what makes that convention safe if a gate is
    ever preceded by an earlier same-prefixed step. `caller` names the
    invoking script in error text; by default it is derived from
    `step_prefix` ("Gate 12" -> "verify-gate-12"), which matches every
    verifier's filename — pass it only for a caller that breaks that
    convention.
    """
    if caller is None:
        caller = "verify-" + step_prefix.lower().replace(" ", "-")
    heredoc_open, heredoc_close = HEREDOC_OPEN, HEREDOC_CLOSE
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    run = None
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name", "")
            if name.startswith(step_prefix) and "self-test" not in name:
                run = step.get("run")
    if run is None:
        sys.exit(f"::error file={path}::{caller} could not find a step named "
                 f"{step_prefix!r}. If it was renamed, update this script and "
                 f"the workflow together.")

    lines = run.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heredoc_open)
        end = next(i for i, l in enumerate(lines)
                   if i > start and l.strip() == heredoc_close)
    except StopIteration:
        sys.exit(f"::error file={path}::{caller} found the {step_prefix} step but "
                 f"not the {heredoc_open} ... {heredoc_close} block it keys on — "
                 f"the step's shape has changed.")
    return "\n".join(lines[start + 1:end]) + "\n"
