#!/usr/bin/env python3
"""Gate - no `./` reference resolves inside an untrusted tree.

specs/132-workflow-trigger-security, contracts/untrusted-checkout-gate.md
(FR-016a, FR-016b).

WHY THIS EXISTS
---------------
`uses: ./path` runs the action found at `path` in the job's workspace. If the
workspace tree that path lies in came from a pull-request head, an item
branch, a consumer repository or an extracted artifact, the author of that
tree chooses the code that runs with the job's token. Trust comes from the
repository and ref a tree was checked out from, never from a directory name.

THE RULE
--------
Steps of each job are walked in order, tracking the trees placed in the
workspace:
  * actions/checkout places a tree at `path:` (default `.`).
  * actions/download-artifact, and a `run:` that extracts an archive
    (`tar -x`, `unzip`), place an untrusted tree at their target.
A tree is TRUSTED only when it is
  * the running repository at `github.sha` (or no `ref:`), in a top-level
    workflow or a repo-only reusable workflow, or
  * the pipeline repository (`inputs.pipeline-repo`) at the resolved pipeline
    ref (`steps.pipeline-ref.outputs.ref`), in a published stage.
In a published stage (a `workflow_call` workflow not listed in
repo-only-reusable-workflows.json) the running repository is the CONSUMER's,
so a checkout without `repository:` is untrusted there.
A `./` reference fails when the longest tree path containing it is untrusted.
Composites are judged per calling job (a composite's own steps are not walked
here; the calling job's workspace decides).

Usage:
    python3 .github/scripts/verify-untrusted-checkout-local-uses.py
    python3 .github/scripts/verify-untrusted-checkout-local-uses.py --audit
    python3 .github/scripts/verify-untrusted-checkout-local-uses.py --self-test
"""
import argparse
import glob
import io
import json
import os
import posixpath
import re
import shutil
import sys
import tempfile

import yaml

REPO_ONLY_PATH = ".github/scripts/repo-only-reusable-workflows.json"
EXTRACT_RE = re.compile(r"\b(tar\s+-?[a-zA-Z]*x|unzip\b)")
DEST_RE = re.compile(r"(?:-C|-d|--directory)\s+(\S+)")


def _norm(path):
    p = posixpath.normpath(str(path or ".").strip().strip("'\""))
    return p


def load_repo_only(root):
    try:
        with io.open(os.path.join(root, REPO_ONLY_PATH), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return set()
    items = data.get("workflows", data) if isinstance(data, dict) else data
    return {os.path.basename(str(i)) for i in items if isinstance(i, str)}


def _events(doc):
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(e) for e in on}
    if isinstance(on, dict):
        return {str(e) for e in on}
    return set()


def _is_published_stage(name, doc, repo_only):
    return "workflow_call" in _events(doc) and name not in repo_only


# The running repository's own default branch is reviewed, merged code, so it
# is as trusted as github.sha.
TRUSTED_RUNNING_REFS = ("", "${{ github.sha }}",
                        "${{ github.event.repository.default_branch }}")


def checkout_trusted(step_with, published):
    repo = str(step_with.get("repository") or "").strip()
    ref = str(step_with.get("ref") or "").strip()
    if not repo:
        # Running repository: the caller's tree in a published stage.
        if published:
            return False
        return ref in TRUSTED_RUNNING_REFS
    if "inputs.pipeline-repo" in repo:
        return "steps.pipeline-ref.outputs.ref" in ref
    if repo == "${{ github.repository }}":
        return not published and ref in TRUSTED_RUNNING_REFS
    return False


def _inside(ref_path, tree_path):
    return tree_path == "." or ref_path == tree_path or \
        ref_path.startswith(tree_path + "/")


def analyse_job(job, published):
    """-> [(step_label, ref, tree_path)] for every exposed `./` reference."""
    trees = []  # (path, trusted); a later entry at the same path replaces
    exposed = []
    for i, step in enumerate(job.get("steps") or []):
        if not isinstance(step, dict):
            continue
        label = str(step.get("id") or step.get("name") or "#{0}".format(i))
        uses = str(step.get("uses") or "")
        with_ = step.get("with") if isinstance(step.get("with"), dict) else {}
        if uses.startswith("actions/checkout@"):
            path = _norm(with_.get("path"))
            trees = [t for t in trees if t[0] != path]
            trees.append((path, checkout_trusted(with_, published)))
        elif uses.startswith("actions/download-artifact@"):
            path = _norm(with_.get("path"))
            trees = [t for t in trees if t[0] != path]
            trees.append((path, False))
        elif step.get("run") and EXTRACT_RE.search(str(step["run"])):
            m = DEST_RE.search(str(step["run"]))
            path = _norm(m.group(1)) if m else "."
            trees = [t for t in trees if t[0] != path]
            trees.append((path, False))
        elif uses.startswith("./"):
            ref_path = _norm(uses[2:] if uses != "./" else ".")
            best = None
            for path, trusted in trees:
                if _inside(ref_path, path) and (
                        best is None or len(path) >= len(best[0])):
                    best = (path, trusted)
            if best is not None and not best[1]:
                exposed.append((label, uses, best[0]))
    return exposed


def scan(root):
    """-> [(file, job, step, uses, tree)] over every workflow."""
    repo_only = load_repo_only(root)
    out = []
    for p in sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml"))):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        try:
            with io.open(p, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        published = _is_published_stage(os.path.basename(p), doc, repo_only)
        for jid, job in sorted((doc.get("jobs") or {}).items()):
            if not isinstance(job, dict):
                continue
            for label, uses, tree in analyse_job(job, published):
                out.append((rel, jid, label, uses, tree))
    return out


# ---------------------------------------------------------------- self-test

def _wf(on, checkouts_and_steps):
    return yaml.safe_dump({"on": on, "jobs": {"j": {
        "runs-on": "ubuntu-latest", "steps": checkouts_and_steps}}},
        sort_keys=False)


PR_HEAD = {"uses": "actions/checkout@v5",
           "with": {"ref": "${{ github.event.pull_request.head.sha }}"}}
LOCAL = {"uses": "./.github/actions/x"}


def self_test():
    sidecar = {"uses": "actions/checkout@v5", "with": {
        "repository": "${{ inputs.pipeline-repo }}",
        "ref": "${{ steps.pipeline-ref.outputs.ref }}",
        "path": ".wing-commander-pipeline"}}
    cases = [
        ("exposed job (PR-head checkout)",
         {"a.yml": _wf("pull_request_target", [PR_HEAD, LOCAL])},
         "a.yml", True),
        ("artifact-extracted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"uses": "actions/download-artifact@v5", "with": {"path": "."}},
             LOCAL])}, "a.yml", True),
        ("run-step extraction",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "tar -xzf x.tgz -C ."}, LOCAL])}, "a.yml", True),
        ("safe job: pristine repo at github.sha",
         {"a.yml": _wf("pull_request_target", [
             {"uses": "actions/checkout@v5", "with": {
                 "ref": "${{ github.sha }}", "path": ".wc-pristine-repo"}},
             {"uses": "./.wc-pristine-repo/.github/actions/x"}])},
         "a.yml", False),
        ("safe job: PR head elsewhere, ref inside trusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"uses": "actions/checkout@v5", "with": {
                 "ref": "${{ github.event.pull_request.head.sha }}",
                 "path": "pr"}},
             LOCAL])}, "a.yml", False),
        ("sidecar at pipeline ref in a published stage",
         {"a.yml": _wf({"workflow_call": {}}, [
             {"uses": "actions/checkout@v5"}, sidecar,
             {"uses": "./.wing-commander-pipeline/.github/actions/x"}])},
         "a.yml", False),
        ("published stage: consumer tree at `.` is untrusted",
         {"a.yml": _wf({"workflow_call": {}}, [
             {"uses": "actions/checkout@v5"}, LOCAL])}, "a.yml", True),
        ("unlisted workflow_call treated as published stage",
         {"a.yml": _wf({"workflow_call": {}}, [
             {"uses": "actions/checkout@v5"}, LOCAL])}, "a.yml", True),
        ("listed workflow_call is repo-only (trusted)",
         {"a.yml": _wf({"workflow_call": {}}, [
             {"uses": "actions/checkout@v5"}, LOCAL]),
          REPO_ONLY_PATH: json.dumps({"workflows": ["a.yml"]})},
         "a.yml", False),
    ]
    bad = 0
    for name, files, wf, want_exposed in cases:
        d = tempfile.mkdtemp(prefix="untrusted-selftest-")
        try:
            for rel, text in files.items():
                path = os.path.join(d, rel if rel == REPO_ONLY_PATH
                                    else ".github/workflows/" + rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with io.open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            got = bool(scan(d))
        finally:
            shutil.rmtree(d, ignore_errors=True)
        if got != want_exposed:
            bad += 1
            print("SELF-TEST FAIL: {0}: exposed={1}, wanted {2}".format(
                name, got, want_exposed))
    if bad:
        return 1
    print("verify-untrusted-checkout-local-uses self-test: {0} cases ok."
          .format(len(cases)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    found = scan(args.root)
    for f, job, step, uses, tree in found:
        print("{0}{1}: job `{2}` step `{3}` runs `{4}` from an untrusted "
              "tree at `{5}`.".format("" if args.audit else "::error::",
                                       f, job, step, uses, tree))
    if args.audit:
        print("verify-untrusted-checkout-local-uses audit: {0} exposed "
              "reference(s).".format(len(found)))
        return 0
    if found:
        return 1
    print("verify-untrusted-checkout-local-uses: no `./` reference resolves "
          "in an untrusted tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
