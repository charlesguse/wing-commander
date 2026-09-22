#!/usr/bin/env python3
"""Board loop prove-step decision (specs/057-autonomous-board-loop,
contracts/prove-step.md, research.md D15).

WHY THIS EXISTS
---------------
A merged fix that changed behaviour running only inside Actions must be
re-driven and proven before its issue closes (FR-041); a merge that
changed nothing but docs/specs, or only a gate script the merged PR's own
required checks already re-executed, proves nothing a fresh dispatch would
add. This is a deterministic, path-based rule (Principle IX) -- never an
agent's guess.
"""
import fnmatch
import re
import sys

import json

DOCS_ONLY_GLOBS = ("docs/**", "specs/**")
VERIFY_SCRIPT_GLOB = ".github/scripts/verify-*.py"
RUN_NAME_ATTEMPT_TOKEN_RE = re.compile(r"^run-name:.*inputs\.attempt-token", re.MULTILINE)


def _matches_any(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def actions_only(changed_paths):
    """research.md D15: docs/**/specs/**-only, or
    .github/scripts/verify-*.py-only -> False (with the reason implied by
    which branch matched); any other changed path -> True."""
    if not changed_paths:
        return False, "no changed paths"

    if all(_matches_any(p, DOCS_ONLY_GLOBS) for p in changed_paths):
        return False, "docs/**/specs/**-only change"

    if all(fnmatch.fnmatch(p, VERIFY_SCRIPT_GLOB) for p in changed_paths):
        return False, "verify-*.py-only change, already proven by the merged PR's own required checks"

    return True, "changed path(s) outside docs/**, specs/**, and .github/scripts/verify-*.py"


def is_safe_redrive_target(workflow_text, workflow_dispatch_inputs=None):
    """Whether wing-commander-dispatch-and-wait can actually redrive this
    workflow unattended (research.md D14, its own action.yml header):

    1. Its own `run-name:` must read `inputs.attempt-token` -- the
       composite correlates the run it dispatches by that token embedded
       in the run's own name, never by recency, and cannot correlate a
       run whose name doesn't carry it.
    2. It must declare no *other* required `workflow_dispatch` input --
       the composite always supplies `attempt-token` itself but has no
       source for anything else a workflow like release.yml's `version`
       would need, and `gh workflow run` rejects a dispatch missing a
       required input outright.

    A candidate failing either check must never be offered to
    redrive_target(): a rejected or uncorrelatable dispatch is
    indistinguishable, from board-loop.yml's side, from an ordinary
    correlation failure (FR-043 anticipates an undispatchable proof run,
    but that must be because nothing reaches the change, never because
    this module picked a target that could never have worked).

    `workflow_dispatch_inputs`: {input_name: {"required": bool, ...}}, as
    parsed from the workflow's own `on.workflow_dispatch.inputs`."""
    if not RUN_NAME_ATTEMPT_TOKEN_RE.search(workflow_text or ""):
        return False
    for name, input_spec in (workflow_dispatch_inputs or {}).items():
        if name == "attempt-token":
            continue
        if (input_spec or {}).get("required"):
            return False
    return True


def redrive_target(changed_paths, dispatchable, uses_graph):
    """Which workflow to re-drive to prove the merged change (FR-042,
    contracts/prove-step.md "Re-drive": "the wrapper workflow that can
    dispatch the changed behavior").

    Deterministic and code-derived, never the agent's pick:

    1. A changed workflow that is itself `workflow_dispatch`-capable is its
       own wrapper -- re-drive it directly.
    2. Otherwise the changed behaviour is only reachable through something
       that calls it (a `workflow_call`-only published stage, or a
       composite under .github/actions/): re-drive the dispatchable
       workflow that references it.
    3. Neither exists -- there is no run that would prove this change, so
       say so rather than dispatching an unrelated workflow. The caller
       leaves the issue open carrying that fact (FR-043's own
       uncorrelated-dispatch discipline).

    `dispatchable` is the set of repo-relative workflow paths carrying a
    workflow_dispatch trigger -- the caller MUST have already narrowed
    this to workflows `is_safe_redrive_target()` accepts, never every
    workflow_dispatch-capable file in the repository, or this can pick a
    target the composite can dispatch but never correlate. `uses_graph`
    maps each workflow path to the repo-relative workflow/composite paths
    it references. Ties break lexicographically so two runs over the same
    merge pick the same target.

    Returns (workflow_file_basename_or_None, reason).
    """
    dispatchable = sorted(set(dispatchable))
    changed = set(changed_paths)

    direct = [p for p in dispatchable if p in changed]
    if direct:
        return direct[0].rsplit("/", 1)[-1], "the changed workflow dispatches itself"

    for candidate in dispatchable:
        referenced = set(uses_graph.get(candidate) or ())
        hit = sorted(referenced & changed)
        if hit:
            return (candidate.rsplit("/", 1)[-1],
                    "wrapper reaching the changed {0}".format(hit[0]))

    return None, "no workflow_dispatch-capable workflow reaches the changed path(s)"


def main():
    """Reads {"changed_paths": [...], "dispatchable": [...],
    "uses_graph": {...}} from stdin, prints
    {"actions_only": bool, "reason": str, "redrive_workflow": str|null,
    "redrive_reason": str} as JSON."""
    payload = json.load(sys.stdin)
    changed_paths = payload.get("changed_paths") or []
    only, reason = actions_only(changed_paths)
    target, target_reason = redrive_target(
        changed_paths, payload.get("dispatchable") or [],
        payload.get("uses_graph") or {})
    print(json.dumps({"actions_only": only, "reason": reason,
                      "redrive_workflow": target,
                      "redrive_reason": target_reason}))


if __name__ == "__main__":
    main()
