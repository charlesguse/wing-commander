#!/usr/bin/env python3
"""Gate 116 - no branch checkout can silently overwrite the trusted
.wing-commander-pipeline checkout (#611).

WHY THIS EXISTS
---------------
Every published stage checks the pipeline repository out at
.wing-commander-pipeline/ inside the workspace and loads its composites and
scripts from there for the rest of the job. Several jobs then check a
consumer branch out into the workspace root with `clean: false`.
actions/checkout forces that checkout, so a branch that tracks files under
.wing-commander-pipeline/ overwrites the pipeline's files, and every later
`uses: ./.wing-commander-pipeline/...` runs code the branch wrote, with the
App token in hand. .github/scripts/pipeline-checkout-guard.sh refuses such
a branch (and restores the pipeline checkout before it fails). A guard that
one new checkout step forgets is no guard, so this gate pins its placement.

WHAT IT CHECKS
--------------
1. Placement. In every job of a .github/workflows/*.yml file that checks
   the pipeline out (an actions/checkout step with
   `path: .wing-commander-pipeline`), every later actions/checkout step
   into the workspace root (no `path:`, or `.`) must be followed
   IMMEDIATELY by the guard step, and so must every root actions/checkout
   step in a composite under .github/actions/ (a composite is only ever
   loaded from the pipeline checkout, so it always has one). The guard
   step is:
     - `run:` exactly GUARD_RUN (read from the pipeline repository's object
       store at HEAD, never its working tree - the working tree is what the
       branch may just have overwritten);
     - `shell: bash` (pipefail, so a failed read fails the step; and bash
       on a caller-supplied container image);
     - the same `if:` as the checkout (so it runs exactly when the
       checkout did), and no `continue-on-error`.
2. Single home. No other `run:` block under .github/workflows/ or
   .github/actions/ lists tracked paths under .wing-commander-pipeline
   (`ls-files`/`ls-tree` beside the directory name) - a pasted copy of the
   check - or names pipeline-checkout-guard.sh any other way than GUARD_RUN
   (for instance from the working tree).
3. Subject. At least one guarded site exists, and the guard script exists.
   Zero sites is a failure, not a vacuous pass.

SELF-TEST
---------
`--self-test` runs the check on the real tree (must pass), then on in-memory
mutations of it, each of which must fail for its own reason: a guard
removed, a new unguarded `clean: false` checkout added after an existing
guard, a guard whose `if:` differs from its checkout's, a guard that runs
the script from the working tree, a guard without `shell: bash`, a guard
with continue-on-error, an inline copy of the check in another step, and
an unguarded root checkout in a composite. It then runs the shipped guard
script, read exactly as GUARD_RUN reads it, against scratch repositories:
a branch tracking nothing under the directory (passes), no repository at
the root (passes), and a hostile branch that overwrote a composite and
planted a file whose name carries a newline and `::` (fails with the
::error::, restores the trusted file, removes the planted one, and prints
no workflow command but its own).
"""
import argparse
import copy
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

PIPE = ".wing-commander-pipeline"
GUARD_SCRIPT = ".github/scripts/pipeline-checkout-guard.sh"
GUARD_RUN = ("git -C .wing-commander-pipeline cat-file blob "
             "HEAD:.github/scripts/pipeline-checkout-guard.sh | bash -s")
GUARD_NAME = "Refuse a branch that tracks .wing-commander-pipeline/"
ROOT_PATHS = (None, "", ".", "./")


def load_tree(root="."):
    """-> {relpath: parsed yaml} for every workflow and composite."""
    docs = {}
    paths = sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.yml")))
    paths += sorted(glob.glob(os.path.join(root, ".github", "actions", "*", "action.yml")))
    paths += sorted(glob.glob(os.path.join(root, ".github", "actions", "_shared", "*", "action.yml")))
    for p in paths:
        with open(p, encoding="utf-8") as f:
            docs[os.path.relpath(p, root)] = yaml.safe_load(f)
    return docs


def is_checkout(step):
    return isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")


def checkout_path(step):
    w = step.get("with") or {}
    return w.get("path")


def step_label(step, idx):
    return "step {0} ({1!r})".format(idx + 1, step.get("name") or step.get("uses"))


def guard_problems(checkout, nxt):
    """-> list of reasons nxt is not a valid guard for checkout."""
    if not isinstance(nxt, dict):
        return ["no step follows it"]
    probs = []
    if str(nxt.get("run", "")).strip() != GUARD_RUN:
        probs.append("the next step's run: is not exactly `{0}`".format(GUARD_RUN))
    if nxt.get("shell") != "bash":
        probs.append("the guard step has no `shell: bash`")
    c_if = checkout.get("if")
    n_if = nxt.get("if")
    norm = lambda v: None if v is None else str(v).strip()
    if norm(c_if) != norm(n_if):
        probs.append("the guard step's if: ({0!r}) differs from the checkout's ({1!r})".format(n_if, c_if))
    if nxt.get("continue-on-error") not in (None, False):
        probs.append("the guard step has continue-on-error")
    return probs


def check_steps(where, steps, require_after_pipeline):
    """require_after_pipeline: only root checkouts after a pipeline checkout
    count (workflows); False means every root checkout counts (composites).
    -> (failures, sites)."""
    failures, sites = [], 0
    seen_pipeline = not require_after_pipeline
    for i, step in enumerate(steps):
        if not is_checkout(step):
            continue
        path = checkout_path(step)
        if path == PIPE:
            seen_pipeline = True
            continue
        if not seen_pipeline or path not in ROOT_PATHS:
            continue
        sites += 1
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        for prob in guard_problems(step, nxt):
            failures.append("{0}: {1} checks a branch out into the workspace root "
                            "after the {2} checkout but is not guarded: {3}.".format(
                                where, step_label(step, i), PIPE, prob))
    return failures, sites


def iter_run_blocks(docs):
    for path, doc in docs.items():
        if not isinstance(doc, dict):
            continue
        if isinstance(doc.get("jobs"), dict):
            for jn, job in doc["jobs"].items():
                for i, s in enumerate((job or {}).get("steps") or []):
                    if isinstance(s, dict) and "run" in s:
                        yield "{0} job {1} {2}".format(path, jn, step_label(s, i)), str(s["run"])
        runs = doc.get("runs")
        if isinstance(runs, dict):
            for i, s in enumerate(runs.get("steps") or []):
                if isinstance(s, dict) and "run" in s:
                    yield "{0} {1}".format(path, step_label(s, i)), str(s["run"])


def check(docs, root="."):
    failures, sites = [], 0
    for path, doc in sorted(docs.items()):
        if not isinstance(doc, dict):
            continue
        if isinstance(doc.get("jobs"), dict):
            for jn, job in doc["jobs"].items():
                steps = (job or {}).get("steps") or []
                f, n = check_steps("{0} job {1}".format(path, jn), steps, True)
                failures += f
                sites += n
        runs = doc.get("runs")
        if isinstance(runs, dict) and runs.get("using") == "composite":
            f, n = check_steps(path, runs.get("steps") or [], False)
            failures += f
            sites += n

    for where, run in iter_run_blocks(docs):
        body = run.strip()
        if body == GUARD_RUN:
            continue
        if "pipeline-checkout-guard.sh" in body:
            failures.append("{0}: names pipeline-checkout-guard.sh other than as `{1}` -- the "
                            "guard must be read from the pipeline repository's object store, "
                            "never its working tree.".format(where, GUARD_RUN))
        if PIPE in body and ("ls-files" in body or "ls-tree" in body):
            failures.append("{0}: lists tracked paths under {1} inline -- a pasted copy of the "
                            "check; call {2} instead (CLAUDE.md, one home).".format(
                                where, PIPE, GUARD_SCRIPT))

    if sites == 0:
        failures.append("found no branch checkout after a {0} checkout at all -- either this is "
                        "the wrong directory or the workflows changed shape; this gate has no "
                        "subject, which is a failure, not a clean pass.".format(PIPE))
    if not os.path.isfile(os.path.join(root, GUARD_SCRIPT)):
        failures.append("{0} is missing.".format(GUARD_SCRIPT))
    return failures, sites


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _first_guarded(docs):
    """-> (path, job, index of the checkout) of the first guarded workflow site."""
    for path, doc in sorted(docs.items()):
        for jn, job in ((doc or {}).get("jobs") or {}).items():
            steps = (job or {}).get("steps") or []
            for i, s in enumerate(steps):
                if (is_checkout(s) and checkout_path(s) in ROOT_PATHS
                        and i + 1 < len(steps)
                        and str(steps[i + 1].get("run", "")).strip() == GUARD_RUN):
                    return path, jn, i
    raise SystemExit("self-test: no guarded site found in the real tree")


def _composite_with_checkout(docs):
    for path, doc in sorted(docs.items()):
        runs = (doc or {}).get("runs")
        if isinstance(runs, dict):
            for i, s in enumerate(runs.get("steps") or []):
                if is_checkout(s) and checkout_path(s) in ROOT_PATHS:
                    return path, i
    raise SystemExit("self-test: no composite with a root checkout in the real tree")


def mutations(docs):
    path, jn, i = _first_guarded(docs)

    def steps_of(d):
        return d[path]["jobs"][jn]["steps"]

    def remove_guard(d):
        del steps_of(d)[i + 1]

    def add_unguarded(d):
        steps_of(d).insert(i + 2, {
            "name": "Checkout another branch", "uses": "actions/checkout@v5",
            "with": {"ref": "some-branch", "clean": False}})

    def mismatched_if(d):
        steps_of(d)[i + 1]["if"] = "always()"

    def working_tree(d):
        steps_of(d)[i + 1]["run"] = "bash .wing-commander-pipeline/" + GUARD_SCRIPT

    def no_shell(d):
        del steps_of(d)[i + 1]["shell"]

    def coe(d):
        steps_of(d)[i + 1]["continue-on-error"] = True

    def inline_copy(d):
        steps_of(d).insert(0, {"name": "inline", "shell": "bash",
                               "run": "test -z \"$(git ls-files -- .wing-commander-pipeline)\""})

    cpath, ci = _composite_with_checkout(docs)

    def composite_unguarded(d):
        del d[cpath]["runs"]["steps"][ci + 1]

    return [
        ("a guard removed", remove_guard, "is not guarded"),
        ("a new unguarded clean: false checkout", add_unguarded, "'Checkout another branch'"),
        ("a guard with a different if:", mismatched_if, "differs from the checkout's"),
        ("a guard run from the working tree", working_tree, "never its working tree"),
        ("a guard without shell: bash", no_shell, "no `shell: bash`"),
        ("a guard with continue-on-error", coe, "has continue-on-error"),
        ("an inline copy of the check", inline_copy, "a pasted copy of the check"),
        ("an unguarded checkout in a composite", composite_unguarded, cpath),
    ]


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c",
                           "init.defaultBranch=main", "-c", "commit.gpgsign=false"] + list(args),
                          cwd=cwd, check=True, capture_output=True, text=True)


def _run_guard(ws):
    env = dict(os.environ)
    env.pop("GITHUB_STEP_SUMMARY", None)
    return subprocess.run(["bash", "-o", "pipefail", "-ec", GUARD_RUN], cwd=ws,
                          capture_output=True, text=True, env=env)


def behavioural(repo_root):
    """-> list of failure strings from running the shipped guard."""
    bad = []
    tmp = tempfile.mkdtemp(prefix="gate116-")
    try:
        src = os.path.join(tmp, "pipe-src")
        os.makedirs(os.path.join(src, ".github", "scripts"))
        os.makedirs(os.path.join(src, ".github", "actions", "x"))
        shutil.copy(os.path.join(repo_root, GUARD_SCRIPT), os.path.join(src, GUARD_SCRIPT))
        trusted = os.path.join(".github", "actions", "x", "action.yml")
        with open(os.path.join(src, trusted), "w") as f:
            f.write("trusted\n")
        _git(src, "init", "-q")
        _git(src, "add", "-A")
        _git(src, "commit", "-qm", "pipeline")

        # No repository at the root: passes.
        ws0 = os.path.join(tmp, "ws0")
        os.makedirs(ws0)
        _git(ws0, "clone", "-q", src, PIPE)
        r = _run_guard(ws0)
        if r.returncode != 0:
            bad.append("no root repository: expected a pass, got rc={0}: {1}{2}".format(
                r.returncode, r.stdout, r.stderr))

        # The consumer repository: a clean branch, and a hostile one that
        # tracks a composite's path and a crafted name under the directory.
        consumer = os.path.join(tmp, "consumer")
        os.makedirs(consumer)
        _git(consumer, "init", "-q")
        with open(os.path.join(consumer, "README"), "w") as f:
            f.write("consumer\n")
        _git(consumer, "add", "README")
        _git(consumer, "commit", "-qm", "consumer")
        _git(consumer, "checkout", "-q", "-b", "hostile")
        planted = os.path.join(PIPE, "::warning::x\n::error::y")
        os.makedirs(os.path.join(consumer, PIPE, ".github", "actions", "x"))
        with open(os.path.join(consumer, PIPE, trusted), "w") as f:
            f.write("EVIL\n")
        with open(os.path.join(consumer, planted), "w") as f:
            f.write("planted\n")
        _git(consumer, "add", "-f", "--", os.path.join(PIPE, trusted), planted)
        _git(consumer, "commit", "-qm", "hostile")

        # The job's workspace, as the stages build it: the pipeline checked
        # out at PIPE first, then a forced checkout of a consumer branch
        # into the root with nothing cleaned (actions/checkout, clean: false).
        ws = os.path.join(tmp, "ws")
        os.makedirs(ws)
        _git(ws, "init", "-q")
        _git(ws, "clone", "-q", src, PIPE)
        _git(ws, "fetch", "-q", consumer, "main:refs/remotes/origin/main",
             "hostile:refs/remotes/origin/hostile")
        _git(ws, "checkout", "-q", "-f", "origin/main")
        r = _run_guard(ws)
        if r.returncode != 0:
            bad.append("clean branch: expected a pass, got rc={0}: {1}{2}".format(
                r.returncode, r.stdout, r.stderr))

        _git(ws, "checkout", "-q", "-f", "origin/hostile")
        with open(os.path.join(ws, PIPE, trusted)) as f:
            if f.read() != "EVIL\n":
                bad.append("hostile branch: the forced checkout did not overwrite the "
                           "pipeline file, so this scenario does not reproduce #611")
        r = _run_guard(ws)
        if r.returncode == 0:
            bad.append("hostile branch: expected a failure, got a pass: " + r.stdout)
        if "::error::wing-commander: the checked-out branch" not in r.stdout:
            bad.append("hostile branch: no ::error:: naming the branch: " + r.stdout)
        if "tracks 2 path(s)" not in r.stdout:
            bad.append("hostile branch: expected 2 tracked paths reported: " + r.stdout)
        if "were restored" not in r.stdout:
            bad.append("hostile branch: restore not reported: " + r.stdout)
        cmd_lines = [l for l in r.stdout.splitlines() if l.strip().startswith("::")]
        if len(cmd_lines) != 1:
            bad.append("hostile branch: expected exactly one workflow command, got {0!r}".format(cmd_lines))
        with open(os.path.join(ws, PIPE, trusted)) as f:
            if f.read() != "trusted\n":
                bad.append("hostile branch: the trusted composite was not restored")
        if os.path.exists(os.path.join(ws, planted)):
            bad.append("hostile branch: the planted file was not removed")
    except subprocess.CalledProcessError as e:
        bad.append("scratch setup failed: {0} {1}".format(e, e.stderr))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return bad


def self_test():
    bad = 0
    docs = load_tree(".")
    failures, sites = check(docs)
    if failures:
        bad += 1
        print("[FAIL] real tree: expected a clean pass, got: " + " | ".join(failures))
    else:
        print("[ok] real tree: {0} guarded site(s)".format(sites))
    for name, mutate, expect in mutations(docs):
        d = copy.deepcopy(docs)
        mutate(d)
        failures, _ = check(d)
        joined = " | ".join(failures)
        if not failures:
            bad += 1
            print("[FAIL] {0}: expected a failure, got a clean pass".format(name))
        elif expect not in joined:
            bad += 1
            print("[FAIL] {0}: failed for the WRONG reason. expected {1!r}, got: {2}".format(
                name, expect, joined))
        else:
            print("[ok] {0}: caught".format(name))
    empty, _ = check({})
    if not any("has no subject" in f for f in empty):
        bad += 1
        print("[FAIL] no subjects: expected a failure")
    else:
        print("[ok] no subjects: caught")
    for b in behavioural("."):
        bad += 1
        print("[FAIL] guard script: " + b)
    if not bad:
        print("[ok] guard script: passes a clean branch and a missing root repo; refuses and restores on a hostile branch")
    print("Gate 116 self-test: {0}".format("passed" if not bad else "{0} failure(s)".format(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="Gate 116 - pipeline checkout guard placement")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    failures, sites = check(load_tree("."))
    for f in failures:
        print("::error::Gate 116: " + f)
    print("Gate 116: {0} branch checkout(s) after a {1} checkout; {2} failure(s).".format(
        sites, PIPE, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
