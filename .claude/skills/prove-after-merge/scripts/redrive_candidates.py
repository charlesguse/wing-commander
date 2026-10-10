#!/usr/bin/env python3
"""Which runs would prove a merged change -- for a local session.

WHY THIS IS NOT JUST board_prove.redrive_target()
-------------------------------------------------
board-loop.yml's prove job answers this for the pipeline, and its answer is
deliberately narrow: it may only re-drive a workflow it can correlate by an
`attempt-token` in the run's own name (board_prove.is_safe_redrive_target),
which today is board-loop.yml alone. A local session dispatching by hand
finds its run by workflow and time instead, so every workflow_dispatch
wrapper is open to it, and a workflow reached only by a schedule or an
event is still worth naming: proof may mean waiting for that run.

So this script reuses the pipeline's own pieces -- the changed-path listing
(board_route_backstop.diff_name_list), the "does this need a run at all"
rule (board_prove.actions_only) and the workflow/composite uses-graph scan
(board_prove.scan_dispatchable_and_uses_graph) -- and reports, beside the
pipeline's own pick, every workflow whose uses-graph reaches a changed path,
following reusable workflows transitively (a wrapper -> implement.yml -> a
composite). A composite that calls another composite is not followed; the
uses-graph doesn't record that edge.

USAGE
-----
  redrive_candidates.py [--merge SHA] [--base SHA] [--json]

  --merge defaults to HEAD; --base to the merge's first parent (a squash
  merge's whole change). Run it on a checkout that contains the merge: the
  scan reads the checked-out tree, as the prove job reads the merge
  commit's own tree.
"""
import argparse
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, ".github", "scripts"))

import yaml  # noqa: E402  (board_prove needs it too)
from board_prove import (  # noqa: E402
    actions_only, redrive_target, scan_dispatchable_and_uses_graph)
from board_route_backstop import diff_name_list  # noqa: E402

WORKFLOWS_DIR = ".github/workflows"


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True, text=True)


def triggers(path):
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    on = doc.get("on", doc.get(True)) or {}
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return on


def required_dispatch_inputs(trigger_map):
    dispatch = trigger_map.get("workflow_dispatch")
    inputs = (dispatch.get("inputs") or {}) if isinstance(dispatch, dict) else {}
    return sorted(name for name, spec in inputs.items()
                  if (spec or {}).get("required") and (spec or {}).get("default") in (None, ""))


def reach(workflow, uses_graph):
    seen, stack = set(), [workflow]
    while stack:
        node = stack.pop()
        for ref in uses_graph.get(node, ()):
            if ref not in seen:
                seen.add(ref)
                if ref in uses_graph:
                    stack.append(ref)
    return seen | {workflow}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--merge", default="HEAD")
    parser.add_argument("--base")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    os.chdir(REPO_ROOT)

    merge = git("rev-parse", "--verify", args.merge + "^{commit}").stdout.strip()
    if not merge:
        sys.exit("redrive_candidates: {0} is not a commit here".format(args.merge))
    if git("merge-base", "--is-ancestor", merge, "HEAD").returncode != 0:
        sys.exit("redrive_candidates: check out a tree that contains {0} first".format(merge[:12]))
    base = args.base or merge + "^1"

    changed = diff_name_list(base, merge)
    needs_run, needs_reason = actions_only(changed)
    safe, uses_graph = scan_dispatchable_and_uses_graph(WORKFLOWS_DIR)
    pick, pick_reason = redrive_target(changed, safe, uses_graph)

    # The uses-graph resolves .py helpers only, so a shell script a workflow
    # runs by path (`bash .github/scripts/verify-watchdog-run.sh`, #976's
    # merge) would reach nothing. Count a literal mention of a changed path
    # under .github/ in a workflow or composite file as an edge to it (docs
    # paths are only ever mentioned in comments, and need no run).
    mentioned_by = {path: set() for path in changed}
    texts = {}
    for name in os.listdir(WORKFLOWS_DIR):
        if name.endswith((".yml", ".yaml")):
            texts["{0}/{1}".format(WORKFLOWS_DIR, name)] = None
    for dirpath, _dirs, names in os.walk(".github/actions"):
        for name in names:
            if name in ("action.yml", "action.yaml"):
                texts[os.path.join(dirpath, name).replace(os.sep, "/")] = None
    for path in texts:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for changed_path in changed:
            if (changed_path.startswith(".github/") and changed_path != path
                    and changed_path in text):
                mentioned_by[changed_path].add(path)

    changed_set = set(changed)
    candidates = []
    for workflow in sorted(uses_graph):
        reached = reach(workflow, uses_graph)
        hits = sorted(path for path in changed_set
                      if path in reached or mentioned_by[path] & reached)
        if not hits:
            continue
        trigger_map = triggers(workflow)
        candidates.append({
            "workflow": workflow.rsplit("/", 1)[-1],
            "dispatchable": "workflow_dispatch" in trigger_map,
            "required_inputs": required_dispatch_inputs(trigger_map),
            "triggers": sorted(str(name) for name in trigger_map),
            "reaches": hits,
        })
    candidates.sort(key=lambda c: (not c["dispatchable"], c["workflow"]))

    report = {
        "merge": merge, "base": base, "changed_paths": changed,
        "needs_proving_run": needs_run, "needs_reason": needs_reason,
        "pipeline_pick": pick, "pipeline_pick_reason": pick_reason,
        "candidates": candidates,
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("Merge {0}: {1} changed path(s)".format(merge[:12], len(changed)))
    print("Needs a proving run: {0} ({1})".format("yes" if needs_run else "no", needs_reason))
    print("Board loop's own pick: {0} ({1})".format(pick or "none", pick_reason))
    if not candidates:
        print("No workflow reaches the changed paths.")
    for c in candidates:
        how = "dispatch" if c["dispatchable"] else "only via " + ", ".join(c["triggers"])
        if c["dispatchable"] and c["required_inputs"]:
            how += " (required inputs: {0})".format(", ".join(c["required_inputs"]))
        shown = ", ".join(c["reaches"][:3]) + (" ..." if len(c["reaches"]) > 3 else "")
        print("  {0}: {1}; reaches {2}".format(c["workflow"], how, shown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
