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
import sys

import json

DOCS_ONLY_GLOBS = ("docs/**", "specs/**")
VERIFY_SCRIPT_GLOB = ".github/scripts/verify-*.py"


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
    workflow_dispatch trigger; `uses_graph` maps each workflow path to the
    repo-relative workflow/composite paths it references. Ties break
    lexicographically so two runs over the same merge pick the same target.

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
