#!/usr/bin/env python3
"""Shared shell-pin resolution for caller-supplied-container jobs.

WHY THIS EXISTS
---------------
`case_container_pipefail_steps_pin_shell_bash`
(verify-metrics-summary-record-emission.py) and the `container-shell-safety`
skill's `unpinned-container-steps.py` both need the same answer to "does
this step run under bash": Actions' own precedence (a step's own `shell:`
wins over its job's `defaults:`, which wins over the workflow's
`defaults:`), and the fact that a custom shell command template (`bash
--noprofile --norc -eo pipefail {0}`) pins bash exactly as well as the bare
keyword does.

PR #293 shipped that logic once, inline, in the gate -- with a precedence
bug (step and job shell OR'd together instead of layered) that an
independent review caught only because it happened to re-derive the same
rule by hand and got it right. A second inline copy for the skill's script
would only get the chance to make, and then separately forget to fix, that
same mistake again. This module is the one place both read from.

`is_container_bound` is here for the same reason: it is the "which jobs
does any of this even apply to" half of the same fact, and the gate and the
skill script disagreeing about which jobs are caller-supplied-container
would be exactly the kind of two-approximations-of-one-fact drift
CLAUDE.md's "shared logic has exactly one home" rule exists to prevent.
"""


def pins_bash(shell):
    """True if a `shell:` value pins bash -- either the bare `bash`
    keyword or a custom command-template whose program is bash (e.g.
    `bash --noprofile --norc -eo pipefail {0}`, which is what GitHub
    itself expands the bare keyword to, or a path-qualified spelling like
    `/bin/bash --noprofile --norc -eo pipefail {0}`; a step that spells
    that out explicitly is no less protected than one that writes
    `bash`)."""
    if not shell:
        return False
    program = str(shell).split()[0]
    return program == "bash" or program.rsplit("/", 1)[-1] == "bash"


def effective_shell(step, job, workflow_doc):
    """The shell Actions resolves for `step` in `job` of `workflow_doc`,
    applying step > job > workflow precedence -- never an OR of the three
    independently, which would let a step that explicitly opts into a
    non-bash shell be masked as covered by its job's or workflow's
    default."""
    step = step or {}
    job = job or {}
    workflow_doc = workflow_doc or {}
    job_shell = ((job.get("defaults") or {}).get("run") or {}).get("shell")
    workflow_shell = ((workflow_doc.get("defaults") or {})
                       .get("run") or {}).get("shell")
    return step.get("shell") or job_shell or workflow_shell


def is_container_bound(job):
    """True if `job`'s container image is a caller-supplied input, not a
    literal this repo controls -- the same `inputs.container-image`
    substring test `case_container_pipefail_steps_pin_shell_bash` has used
    since PR #293, kept here as the one place it is written down."""
    container = (job or {}).get("container")
    if not isinstance(container, dict):
        return False
    return "inputs.container-image" in str(container.get("image", ""))
