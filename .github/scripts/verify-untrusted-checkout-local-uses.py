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
ERROR_JOB = "<error>"  # scan() entries with this job are failures, not exposures
# Anchored to command position: start of a line, or after `;`, `&`, `|`, `(`.
EXTRACT_RE = re.compile(
    r"(?m)(?:^|[;&|(])[ \t]*(?:sudo[ \t]+)?(tar[ \t]+-?[a-zA-Z]*x|unzip\b)")
DEST_RE = re.compile(r"(?:-C|-d|--directory)\s+(\S+)")
# Run steps that put another ref's or run's files into the workspace.
CHECKOUT_CMD_RE = re.compile(
    r"(?m)(?:^|[;&|(])[ \t]*(?:gh[ \t]+pr[ \t]+checkout|gh[ \t]+run[ \t]+"
    r"download|gh[ \t]+release[ \t]+download|git[ \t]+(?:checkout|switch)"
    r"(?![ \t]+--[ \t]))\b")
COPY_RE = re.compile(
    r"(?m)(?:^|[;&|(])[ \t]*cp[ \t]+(?:-[a-zA-Z]+[ \t]+)*-[a-zA-Z]*[rRa]"
    r"[a-zA-Z]*[ \t]+[^;&|\n]*?[ \t]+(\S+)[ \t]*(?:$|[;&|])")


def _norm(path):
    p = posixpath.normpath(str(path or ".").strip().strip("'\""))
    return p


def load_repo_only(root):
    """-> set of file names, or None when the register is unreadable (the
    caller fails rather than treating every reusable workflow as published)."""
    try:
        with io.open(os.path.join(root, REPO_ONLY_PATH), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    items = data.get("workflows") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
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
# On a `pull_request` event github.sha is the merge commit the PR author
# controls, and a checkout with no ref gets that same commit.
MERGE_COMMIT_REFS = ("", "${{ github.sha }}")
PR_MERGE_EVENTS = {"pull_request", "pull_request_review",
                   "pull_request_review_comment"}
# Workflows whose `pull_request` trigger may still trust github.sha, each
# with the reason. Keep this list short: an entry is an accepted risk.
PULL_REQUEST_SHA_ALLOWLIST = {
    "board-loop.yml": "its only pull_request trigger is `types: [closed]` "
                      "(the prove resume path), not a PR-head or opened/"
                      "synchronize run; listed for the owner to confirm",
}


def checkout_trusted(step_with, published, pr_merge=False):
    repo = str(step_with.get("repository") or "").strip()
    ref = str(step_with.get("ref") or "").strip()
    refs = tuple(r for r in TRUSTED_RUNNING_REFS
                 if not (pr_merge and r in MERGE_COMMIT_REFS))
    if not repo:
        # Running repository: the caller's tree in a published stage.
        if published:
            return False
        return ref in refs
    if "inputs.pipeline-repo" in repo:
        return "steps.pipeline-ref.outputs.ref" in ref
    if repo == "${{ github.repository }}":
        return not published and ref in refs
    return False


def _inside(ref_path, tree_path):
    return tree_path == "." or ref_path == tree_path or \
        ref_path.startswith(tree_path + "/")


def _place(trees, path, trusted, clean=True):
    """A tree placed at `path` replaces everything at or below it, because
    actions/checkout's default `git clean` deletes the untracked nested
    trees. `clean: false` keeps them, so only the tree at `path` itself is
    replaced."""
    trees = [t for t in trees if not (t[0] == path or (
        clean and (path == "." or t[0].startswith(path + "/"))))]
    trees.append((path, trusted))
    return trees


def _extract_dest(step):
    """-> workspace-relative extraction directory for a tar/unzip step: the
    -C/-d target, else the step's working-directory or a leading `cd`, else
    the workspace root (where a bare extraction lands)."""
    run = str(step["run"])
    base = _norm(step.get("working-directory"))
    m = re.match(r"\s*cd\s+(\S+)\s*(?:&&|;|\n)", run)
    if m:
        base = posixpath.normpath(posixpath.join(base, _norm(m.group(1))))
    d = DEST_RE.search(run)
    if d:
        target = _norm(d.group(1))
        return target if target.startswith("/") else \
            posixpath.normpath(posixpath.join(base, target))
    return base


def analyse_job(job, published, pr_merge=False):
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
            trees = _place(trees, _norm(with_.get("path")),
                           checkout_trusted(with_, published, pr_merge),
                           clean=str(with_.get("clean", True)).lower()
                           != "false")
        elif uses.startswith("actions/download-artifact@"):
            trees = _place(trees, _norm(with_.get("path")), False, clean=False)
        elif uses.startswith("actions/cache/restore@") or \
                uses.startswith("actions/cache@"):
            first = str(with_.get("path") or ".").splitlines()
            trees = _place(trees, _norm(first[0] if first else "."), False,
                           clean=False)
        elif step.get("run") and EXTRACT_RE.search(str(step["run"])):
            trees = _place(trees, _extract_dest(step), False, clean=False)
        elif step.get("run") and CHECKOUT_CMD_RE.search(str(step["run"])):
            # Replaces only the tree at the working directory: nested trusted
            # trees (a pristine copy, a pipeline sidecar) stay in place.
            trees = _place(trees, _norm(step.get("working-directory")), False,
                           clean=False)
        elif step.get("run") and COPY_RE.search(str(step["run"])):
            dest = _norm(COPY_RE.search(str(step["run"])).group(1))
            base = _norm(step.get("working-directory"))
            dest = dest if dest.startswith("/") else \
                posixpath.normpath(posixpath.join(base, dest))
            trees = _place(trees, dest, False, clean=False)
        elif uses.startswith("./"):
            ref_path = _norm(uses[2:] if uses != "./" else ".")
            best = None
            for path, trusted in trees:
                if _inside(ref_path, path) and (
                        best is None or len(path) >= len(best[0])):
                    best = (path, trusted)
            if best is not None and not best[1]:
                exposed.append((label, uses, best[0]))
            elif published and best is None and (
                    ref_path == ".github/actions"
                    or ref_path.startswith(".github/actions/")):
                # A published stage's workspace is the consumer's: a raw
                # ./.github/actions reference never resolves to pipeline code.
                exposed.append((label, uses, "."))
    return exposed


def scan(root):
    """-> [(file, job, step, uses, tree)] over every workflow."""
    repo_only = load_repo_only(root)
    out = []
    if repo_only is None:
        # Fail closed: without the register every reusable workflow would
        # silently be judged a published stage (or a repo-only one).
        out.append((REPO_ONLY_PATH, ERROR_JOB, "register",
                    "an unreadable or invalid register", "-"))
        repo_only = set()
    for p in sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml"))):
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        try:
            with io.open(p, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            out.append((rel, ERROR_JOB, "parse", "an unparsable workflow", "-"))
            continue
        if not isinstance(doc, dict):
            out.append((rel, ERROR_JOB, "parse", "a workflow that is not a "
                        "mapping", "-"))
            continue
        published = _is_published_stage(os.path.basename(p), doc, repo_only)
        pr_merge = (bool(_events(doc) & PR_MERGE_EVENTS)
                    and os.path.basename(p) not in PULL_REQUEST_SHA_ALLOWLIST)
        for jid, job in sorted((doc.get("jobs") or {}).items()):
            if not isinstance(job, dict):
                continue
            for label, uses, tree in analyse_job(job, published, pr_merge):
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


def _real_step(docs, fname, job_id, pred):
    for step in docs[fname]["jobs"][job_id]["steps"]:
        if pred(step or {}):
            return step
    raise LookupError("the step this mutation needs is gone from {0} job {1}; "
                      "update the self-test alongside the workflow."
                      .format(fname, job_id))


def _mut_consumer_raw_reference(docs):
    """pr-conversation.yml's act job resolves its outstanding-task-item
    composite from the PR branch it checked out at the root."""
    step = _real_step(docs, "pr-conversation.yml", "act", lambda s: (
        "wing-commander-outstanding-task-item" in str(s.get("uses", ""))))
    step["uses"] = "./.github/actions/wing-commander-outstanding-task-item"


def _mut_untrusted_root_ref(docs):
    """shared-pr-reviewer.yml's find job checks the PR head out at the root
    instead of the commit its composites come from."""
    step = _real_step(docs, "shared-pr-reviewer.yml", "find", lambda s: (
        str(s.get("uses", "")).startswith("actions/checkout@")))
    step["with"] = dict(step.get("with") or {},
                        ref="${{ needs.prepare.outputs.head-sha }}")


def _mut_side_checkout_moved_to_root(docs):
    """The watchdog's metrics-branch checkout loses its path:, so the
    trial-bound composite after it resolves from the metrics branch."""
    step = _real_step(docs, "wing-commander-8-watchdog.yml", "trial-bound",
                      lambda s: (s.get("with") or {}).get("path")
                      == ".wing-commander-metrics")
    del step["with"]["path"]


# Moved here from Gate 104's former rule (g) (specs/132 FR-016a one home):
# each mutates the shipped workflows and must be reported as exposed.
REAL_MUTATIONS = (
    ("pr-conversation.yml act job: raw composite after the PR-branch root "
     "checkout", "pr-conversation.yml", _mut_consumer_raw_reference),
    ("shared-pr-reviewer.yml find job: PR head checked out at the root",
     "shared-pr-reviewer.yml", _mut_untrusted_root_ref),
    ("watchdog trial-bound job: metrics-branch checkout moved to the root",
     "wing-commander-8-watchdog.yml", _mut_side_checkout_moved_to_root),
)


def _real_tree_mutations(root="."):
    """-> number of failures. The shipped tree must be clean, and each
    REAL_MUTATIONS entry must make its own workflow exposed."""
    src = os.path.join(root, ".github", "workflows")
    if not os.path.isdir(src):
        print("SELF-TEST FAIL: run from the repository root; {0} not found."
              .format(src))
        return 1
    bad = 0
    if scan(root):
        bad += 1
        print("SELF-TEST FAIL: the shipped workflows already fail: {0}"
              .format(scan(root)))
    for name, fname, mutate in REAL_MUTATIONS:
        docs = {}
        for f in os.listdir(src):
            if f.endswith((".yml", ".yaml")):
                with io.open(os.path.join(src, f), encoding="utf-8") as fh:
                    docs[f] = yaml.safe_load(fh)
        try:
            mutate(docs)
        except (LookupError, KeyError, TypeError) as e:
            bad += 1
            print("SELF-TEST FAIL: {0}: {1}".format(name, e))
            continue
        d = tempfile.mkdtemp(prefix="untrusted-selftest-")
        try:
            os.makedirs(os.path.join(d, ".github", "workflows"))
            for f, doc in docs.items():
                with io.open(os.path.join(d, ".github", "workflows", f), "w",
                             encoding="utf-8") as fh:
                    yaml.safe_dump(doc, fh, sort_keys=False)
            reg = os.path.join(root, REPO_ONLY_PATH)
            if os.path.isfile(reg):
                os.makedirs(os.path.dirname(os.path.join(d, REPO_ONLY_PATH)),
                            exist_ok=True)
                shutil.copy(reg, os.path.join(d, REPO_ONLY_PATH))
            got = [r for r in scan(d) if r[0].endswith("/" + fname)]
        finally:
            shutil.rmtree(d, ignore_errors=True)
        if not got:
            bad += 1
            print("SELF-TEST FAIL: {0}: not reported as exposed.".format(name))
    return bad


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
        ("published stage: raw ./.github/actions with no checkout",
         {"a.yml": _wf({"workflow_call": {}}, [LOCAL])}, "a.yml", True),
        ("pull_request: default checkout is the merge commit",
         {"a.yml": _wf("pull_request", [
             {"uses": "actions/checkout@v5"}, LOCAL])}, "a.yml", True),
        ("pull_request: github.sha checkout is the merge commit",
         {"a.yml": _wf("pull_request", [
             {"uses": "actions/checkout@v5",
              "with": {"ref": "${{ github.sha }}"}}, LOCAL])}, "a.yml", True),
        ("pull_request: default-branch checkout is trusted",
         {"a.yml": _wf("pull_request", [
             {"uses": "actions/checkout@v5", "with": {
                 "ref": "${{ github.event.repository.default_branch }}"}},
             LOCAL])}, "a.yml", False),
        ("unzip in a scratch working-directory leaves the root trusted",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "unzip x.zip", "working-directory": "scratch"},
             LOCAL])}, "a.yml", False),
        ("tar -C into a scratch dir leaves the root trusted",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "tar -xzf x.tgz -C scratch"}, LOCAL])}, "a.yml", False),
        ("re-checkout at `.` drops an earlier nested untrusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/download-artifact@v5", "with": {"path": "art"}},
             {"uses": "actions/checkout@v5"},
             {"uses": "./art/.github/actions/x"}])}, "a.yml", False),
        ("re-checkout with clean: false keeps an earlier nested tree",
         {"a.yml": _wf({"workflow_call": {}}, [
             {"uses": "actions/checkout@v5"}, sidecar,
             {"uses": "actions/checkout@v5", "with": {"clean": False}},
             {"uses": "./.wing-commander-pipeline/.github/actions/x"}])},
         "a.yml", False),
        ("pull_request_review: default checkout is the merge commit",
         {"a.yml": _wf("pull_request_review", [
             {"uses": "actions/checkout@v5"}, LOCAL])}, "a.yml", True),
        ("pull_request_review_comment: github.sha is the merge commit",
         {"a.yml": _wf({"pull_request_review_comment": {}}, [
             {"uses": "actions/checkout@v5",
              "with": {"ref": "${{ github.sha }}"}}, LOCAL])}, "a.yml", True),
        ("gh pr checkout places an untrusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "gh pr checkout 5"}, LOCAL])}, "a.yml", True),
        ("git checkout of another ref places an untrusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "git checkout origin/pr-branch"}, LOCAL])},
         "a.yml", True),
        ("gh run download places an untrusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "gh run download 7"}, LOCAL])}, "a.yml", True),
        ("cp -r into the root places an untrusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "cp -r other/. ."}, LOCAL])}, "a.yml", True),
        ("cache restore into the root places an untrusted tree",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"uses": "actions/cache/restore@v4",
              "with": {"path": ".", "key": "k"}}, LOCAL])}, "a.yml", True),
        ("artifact download keeps a nested trusted sidecar",
         {"a.yml": _wf({"workflow_call": {}}, [
             {"uses": "actions/checkout@v5"}, sidecar,
             {"uses": "actions/download-artifact@v5", "with": {"path": "."}},
             {"uses": "./.wing-commander-pipeline/.github/actions/x"}])},
         "a.yml", False),
        ("`unzip` inside an echo is not an extraction",
         {"a.yml": _wf("push", [
             {"uses": "actions/checkout@v5"},
             {"run": "echo 'run unzip later'"}, LOCAL])}, "a.yml", False),
        ("unparsable workflow fails",
         {"a.yml": "on: [push\njobs: {"}, "a.yml", True),
        ("missing register fails",
         {"a.yml": _wf("push", [{"uses": "actions/checkout@v5"}, LOCAL]),
          REPO_ONLY_PATH: None}, "a.yml", True),
    ]
    bad = _real_tree_mutations()
    for name, files, wf, want_exposed in cases:
        d = tempfile.mkdtemp(prefix="untrusted-selftest-")
        files = dict({REPO_ONLY_PATH: json.dumps({"workflows": []})}, **files)
        try:
            for rel, text in files.items():
                if text is None:
                    continue
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
    print("verify-untrusted-checkout-local-uses self-test: {0} cases and {1} "
          "shipped-workflow mutations ok.".format(len(cases), len(REAL_MUTATIONS)))
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
        if job == ERROR_JOB:
            print("{0}{1}: cannot judge `./` references: {2}.".format(
                "" if args.audit else "::error::", f, uses))
            continue
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
