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

import re as _re


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


# Host-path expressions in container jobs. The canonical explanation is the
# "Container-side paths" comment in
# .github/actions/wing-commander-context/action.yml; in short: inside a
# `container:` job these contexts evaluate to the HOST path, and the runner
# maps a host path back to its container mount only where it leads a whole
# environment value (ContainerStepHost translates every env entry, which
# covers a step's `env:` and a JavaScript action's INPUT_* from `with:`).
HOST_PATH_CONTEXTS = ("runner.temp", "runner.workspace", "runner.tool_cache",
                      "github.workspace", "github.action_path")
_CTX_ALT = "|".join(_re.escape(c) for c in HOST_PATH_CONTEXTS)
_EXPR_RE = _re.compile(r"\$\{\{(?:(?!\}\}).)*\}\}", _re.S)
_CTX_RE = _re.compile(r"(?<![\w.-])(?:" + _CTX_ALT + r")(?![\w-])")


def host_path_exprs(text):
    """The `${{ }}` expressions in `text` that read a host-path context,
    including one wrapped in a function call such as format(...)."""
    return [m.group(0) for m in _EXPR_RE.finditer(str(text))
            if _CTX_RE.search(m.group(0))]


_LEADING_RE = _re.compile(r"\$\{\{\s*(?:" + _CTX_ALT + r")\s*\}\}(?:/[^\n]*)?")


def host_path_value_is_translated(value):
    """True if `value`, used as a whole env/with/working-directory value,
    reaches a container step with its host path translated: the expression
    is the value's very start, it is the only such expression, and the
    value is one line (translation is a prefix rewrite of the whole value,
    so a second line or a second path is left as the host path)."""
    value = str(value)
    return (_LEADING_RE.fullmatch(value) is not None
            and len(host_path_exprs(value)) == 1)


def host_path_misuses(step):
    """(field, expression) pairs in `step` where a host-path context
    expression would reach a container step untranslated: anywhere in a
    `run:` body, and in any `env:`, `with:` or `working-directory:` value
    that is not the single leading expression of a one-line value."""
    step = step or {}
    out = []
    run = step.get("run")
    if run:
        out += [("run", expr) for expr in host_path_exprs(run)]
    values = [(f"env.{k}", v) for k, v in (step.get("env") or {}).items()]
    values += [(f"with.{k}", v) for k, v in (step.get("with") or {}).items()]
    if step.get("working-directory") is not None:
        values.append(("working-directory", step["working-directory"]))
    for field, value in values:
        found = host_path_exprs(value)
        if found and not host_path_value_is_translated(value):
            out += [(field, expr) for expr in found]
    return out


def env_host_path_misuses(env):
    """The same test for a job- or workflow-level `env:` map, whose values
    reach every step's environment and are translated the same way."""
    out = []
    for k, v in (env or {}).items():
        found = host_path_exprs(v)
        if found and not host_path_value_is_translated(v):
            out += [(f"env.{k}", expr) for expr in found]
    return out
