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
  extract_gate_step("Gate 15")
"""
import io
import re
import sys

import yaml

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
# A third heredoc grammar exists beside these two markers:
# verify-gate-wiring.py's PY_HEREDOC_RE recognizes the same inline-python
# step shape for its own registry. The grammars are checked independently
# and both fail loudly on a shape they no longer recognize, so drift
# between them cannot pass silently — but a change to either belongs in
# both places.
HEREDOC_OPEN = "python3 - <<'PYEOF'"
HEREDOC_CLOSE = "PYEOF"


def extract_gate_step(step_prefix, path=LINT_WORKFLOW):
    """Return a gate's python source, read out of its shipped workflow step.

    Walks every job's steps in `path`, collects every step whose name starts
    with `step_prefix` and does not contain "self-test", and returns the
    source between the heredoc markers of the ONE such step that carries a
    heredoc. `step_prefix` must be unique among non-self-test steps: two
    unrelated features each landed a "Gate 22" and a "Gate 23", so those
    callers pass a longer prefix ("Gate 22 — every job", "Gate 23 — every
    published stage") that names their twin unambiguously. The heredoc
    check is a second line of defense, not an identity check — a prefix
    matching several steps only ONE of which holds a heredoc still resolves
    to that one, so a caller that wants a specific twin must say so in its
    prefix; two heredoc-bearing matches refuse loudly. Error text names the
    caller as "verify-" + the prefix's "Gate N" head ("Gate 12 …" ->
    "verify-gate-12"), which is every verifier's filename.
    """
    head = re.match(r"Gate \d+", step_prefix)
    caller = ("verify-" + head.group(0).lower().replace(" ", "-")
              if head else "verify-" + step_prefix.lower().replace(" ", "-"))
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    matched = extracted = 0
    source = None
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            name = (step or {}).get("name", "")
            if not (name.startswith(step_prefix) and "self-test" not in name):
                continue
            matched += 1
            lines = str(step.get("run") or "").splitlines()
            try:
                start = next(i for i, l in enumerate(lines)
                             if l.strip() == HEREDOC_OPEN)
                end = next(i for i, l in enumerate(lines)
                           if i > start and l.strip() == HEREDOC_CLOSE)
            except StopIteration:
                continue
            extracted += 1
            source = "\n".join(lines[start + 1:end]) + "\n"
    if matched == 0:
        sys.exit(f"::error file={path}::{caller} could not find a step named "
                 f"{step_prefix!r}. If it was renamed, update this script and "
                 f"the workflow together.")
    if extracted == 0:
        sys.exit(f"::error file={path}::{caller} found {matched} {step_prefix} "
                 f"step(s) but none holds the {HEREDOC_OPEN} ... {HEREDOC_CLOSE} "
                 f"block it keys on — the step's shape has changed.")
    if extracted > 1:
        sys.exit(f"::error file={path}::{caller} found {extracted} {step_prefix} "
                 f"steps each holding a {HEREDOC_OPEN} heredoc — ambiguous; this "
                 f"extractor cannot know which gate's source to self-test. "
                 f"Rename one step or teach the callers full step names.")
    return source
