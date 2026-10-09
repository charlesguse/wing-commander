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
     - `run:` exactly GUARD_RUN: first an inline check that the path is
       still the trusted checkout (not a symlink, a real .git, its own top
       level, at the pipeline ref), removing it and failing otherwise; then
       the guard read from that repository's object store at HEAD, never
       its working tree - the working tree is what the branch may just have
       overwritten;
     - in a workflow, env WC_PIPELINE_REF equal to the job's pipeline
       checkout `ref:`, so HEAD is compared against it;
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
mutations of it, each of which must fail for its own reason: the symlink
check dropped, the unverified pre-fix one-liner restored, WC_PIPELINE_REF
dropped, a guard removed, a new unguarded `clean: false` checkout added after an existing
guard, a guard whose `if:` differs from its checkout's, a guard that runs
the script from the working tree, a guard without `shell: bash`, a guard
with continue-on-error, an inline copy of the check in another step, and
an unguarded root checkout in a composite. It then runs the shipped guard
script, read exactly as GUARD_RUN reads it, against scratch repositories:
a branch tracking nothing under the directory (passes), no repository at
the root (passes), a pipeline at another commit than WC_PIPELINE_REF
(refused, removed), a hostile branch that overwrote a composite and
planted a file whose name carries a newline and `::` (fails with the
::error::, restores the trusted file, removes the planted one, and prints
no workflow command but its own), and two branches that track the path
itself as a symlink - to `.` and to a directory of their own - with their
own passing guard: the pre-fix one-liner must be fooled by each (so the
scenario is real), and the shipped guard must refuse each and leave
nothing at the path. Every workspace is built with actions/checkout's own
`git checkout --force -B`.
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
# The guard step's whole run: block, pinned byte for byte (stripped). Lines 1-2
# run BEFORE anything is read from .wing-commander-pipeline and must stay
# inline: they are the only trusted code left once a branch has replaced
# the directory. A forced checkout of a branch that tracks the path itself
# (e.g. a symlink to `.`) deletes the untracked pipeline directory, .git and
# all, so `git -C .wing-commander-pipeline` would resolve to the root repo -
# the branch - and read the branch's own guard. So: the path must not be a
# symlink, must hold a real (non-symlink) .git directory, must be its own
# repository's top level, and, when the job's pipeline ref is a full SHA,
# must sit at that commit, the SHA peeled first so an annotated tag's object
# SHA names the commit it tags (#928). Otherwise it is removed (so a later always()-
# gated `uses: ./.wing-commander-pipeline/...` fails to resolve rather than
# load branch code) and the step fails. Line 3 then runs the tracked-path
# check from the verified repository's object store.
GUARD_RUN = "\n".join([
    'p=.wing-commander-pipeline; want="$(cd "$GITHUB_WORKSPACE" && pwd -P)/$p"',
    'if [ -L "$p" ] || [ ! -d "$p" ] || [ -L "$p/.git" ] || [ ! -d "$p/.git" ] || [ "$(git -C "$p" rev-parse --show-toplevel 2>/dev/null)" != "$want" ] || { [[ "${WC_PIPELINE_REF:-}" =~ ^[0-9a-f]{40}$ ]] && [ "$(git -C "$p" rev-parse HEAD 2>/dev/null)" != "$(git -C "$p" rev-parse --verify -q "${WC_PIPELINE_REF}^{commit}" 2>/dev/null)" ]; }; then rm -rf -- "$p"; echo "::error::wing-commander: $p is no longer the trusted pipeline checkout (a symlink, a missing or replaced .git, or another commit): the branch just checked out replaced it. Removed it so no later step loads branch code from there (#611)."; exit 1; fi',
    'git -C "$p" cat-file blob HEAD:.github/scripts/pipeline-checkout-guard.sh | bash -s',
])
# The verification clauses the self-test drops one at a time.
SYMLINK_CHECK = '[ -L "$p" ] || '
PIPELINE_REF_ENV = "WC_PIPELINE_REF"
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


def guard_problems(checkout, nxt, pipeline_ref):
    """-> list of reasons nxt is not a valid guard for checkout.
    pipeline_ref: the job's pipeline checkout `with.ref` expression, or None
    (a composite, or a pipeline checkout with no ref)."""
    if not isinstance(nxt, dict):
        return ["no step follows it"]
    probs = []
    if str(nxt.get("run", "")).strip() != GUARD_RUN:
        probs.append("the next step's run: is not exactly GUARD_RUN (the inline "
                     "verification of {0} followed by the object-store read of {1})".format(
                         PIPE, GUARD_SCRIPT))
    env = nxt.get("env") or {}
    if pipeline_ref is not None and str(env.get(PIPELINE_REF_ENV, "")).strip() != str(pipeline_ref).strip():
        probs.append("the guard step's env {0} ({1!r}) is not the pipeline checkout's ref ({2!r})".format(
            PIPELINE_REF_ENV, env.get(PIPELINE_REF_ENV), pipeline_ref))
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
    pipeline_ref = None
    for i, step in enumerate(steps):
        if not is_checkout(step):
            continue
        path = checkout_path(step)
        if path == PIPE:
            seen_pipeline = True
            pipeline_ref = (step.get("with") or {}).get("ref")
            continue
        if not seen_pipeline or path not in ROOT_PATHS:
            continue
        sites += 1
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        for prob in guard_problems(step, nxt, pipeline_ref):
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
            failures.append("{0}: names pipeline-checkout-guard.sh other than as GUARD_RUN -- the "
                            "guard must be read from the verified pipeline repository's object "
                            "store, never its working tree.".format(where))
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

    def no_symlink_check(d):
        run = steps_of(d)[i + 1]["run"]
        assert SYMLINK_CHECK in run
        steps_of(d)[i + 1]["run"] = run.replace(SYMLINK_CHECK, "", 1)

    def pre_fix_run(d):
        steps_of(d)[i + 1]["run"] = PRE_FIX_RUN

    def no_pipeline_ref(d):
        del steps_of(d)[i + 1]["env"][PIPELINE_REF_ENV]

    cpath, ci = _composite_with_checkout(docs)

    def composite_unguarded(d):
        del d[cpath]["runs"]["steps"][ci + 1]

    return [
        ("a guard that drops the symlink check", no_symlink_check, "is not exactly GUARD_RUN"),
        ("a guard reverted to the unverified pre-fix one-liner", pre_fix_run, "is not exactly GUARD_RUN"),
        ("a guard without the pipeline ref to compare HEAD to", no_pipeline_ref,
         "is not the pipeline checkout's ref"),
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


def _run_guard(ws, script=None, pipeline_ref=None):
    """Run a guard step body the way `shell: bash` does, in workspace ws."""
    env = dict(os.environ)
    env.pop("GITHUB_STEP_SUMMARY", None)
    env.pop(PIPELINE_REF_ENV, None)
    env["GITHUB_WORKSPACE"] = ws
    if pipeline_ref is not None:
        env[PIPELINE_REF_ENV] = pipeline_ref
    return subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c",
                           script or GUARD_RUN], cwd=ws, capture_output=True, text=True, env=env)


# The pre-fix one-liner: read the guard from whatever repository
# `git -C .wing-commander-pipeline` resolves to, with no verification.
PRE_FIX_RUN = ("git -C .wing-commander-pipeline cat-file blob "
               "HEAD:.github/scripts/pipeline-checkout-guard.sh | bash -s")


def _write(root, rel, text):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


def behavioural(repo_root):
    """-> list of failure strings from running the shipped guard."""
    bad = []
    tmp = tempfile.mkdtemp(prefix="gate116-")
    try:
        src = os.path.join(tmp, "pipe-src")
        _write(src, GUARD_SCRIPT, open(os.path.join(repo_root, GUARD_SCRIPT)).read())
        trusted = os.path.join(".github", "actions", "x", "action.yml")
        _write(src, trusted, "trusted\n")
        _git(src, "init", "-q")
        _git(src, "add", "-A")
        _git(src, "commit", "-qm", "pipeline")
        pipe_sha = _git(src, "rev-parse", "HEAD").stdout.strip()

        # No repository at the root: passes.
        ws0 = os.path.join(tmp, "ws0")
        os.makedirs(ws0)
        _git(ws0, "clone", "-q", src, PIPE)
        r = _run_guard(ws0, pipeline_ref=pipe_sha)
        if r.returncode != 0:
            bad.append("no root repository: expected a pass, got rc={0}: {1}{2}".format(
                r.returncode, r.stdout, r.stderr))

        # The consumer repository. main is clean. hostile tracks a
        # composite's path and a crafted name under the directory. The two
        # symlink branches track the path ITSELF as a symlink (to `.`, and to
        # a directory of their own) and carry their own guard, which passes.
        consumer = os.path.join(tmp, "consumer")
        os.makedirs(consumer)
        _git(consumer, "init", "-q")
        _write(consumer, "README", "consumer\n")
        _git(consumer, "add", "README")
        _git(consumer, "commit", "-qm", "consumer")

        _git(consumer, "checkout", "-q", "-b", "hostile", "main")
        planted = os.path.join(PIPE, "::warning::x\n::error::y")
        _write(consumer, os.path.join(PIPE, trusted), "EVIL\n")
        _write(consumer, planted, "planted\n")
        _git(consumer, "add", "-f", "--", os.path.join(PIPE, trusted), planted)
        _git(consumer, "commit", "-qm", "hostile")
        _git(consumer, "checkout", "-q", "-f", "main")

        for branch, target, prefix in (("symlink-dot", ".", ""),
                                       ("symlink-other", "evil", "evil")):
            _git(consumer, "checkout", "-q", "-f", "-b", branch, "main")
            # `git -C` resolves to the root repository either way, and
            # `HEAD:<path>` is read from its top level.
            _write(consumer, GUARD_SCRIPT, "exit 0\n")
            _write(consumer, os.path.join(prefix, trusted), "EVIL\n")
            os.symlink(target, os.path.join(consumer, PIPE))
            _git(consumer, "add", "-f", "-A")
            _git(consumer, "commit", "-qm", branch)
            _git(consumer, "checkout", "-q", "-f", "main")
            _git(consumer, "clean", "-qffdx")

        def workspace(name, branch):
            """The job's workspace as the stages build it: the pipeline
            checked out at PIPE, then a forced checkout of a consumer branch
            into the root with nothing cleaned - actions/checkout with
            clean: false runs `git checkout --force -B <branch> <ref>`."""
            ws = os.path.join(tmp, name)
            os.makedirs(ws)
            _git(ws, "init", "-q")
            _git(ws, "clone", "-q", src, PIPE)
            _git(ws, "fetch", "-q", consumer, "+refs/heads/*:refs/remotes/origin/*")
            _git(ws, "checkout", "-q", "--force", "-B", "work", "origin/" + branch)
            return ws

        ws = workspace("ws", "main")
        r = _run_guard(ws, pipeline_ref=pipe_sha)
        if r.returncode != 0:
            bad.append("clean branch: expected a pass, got rc={0}: {1}{2}".format(
                r.returncode, r.stdout, r.stderr))
        r = _run_guard(ws, pipeline_ref="0" * 40)
        if r.returncode == 0 or os.path.lexists(os.path.join(ws, PIPE)):
            bad.append("pipeline at another commit than {0}: expected a refusal that removes "
                       "the directory, got rc={1}: {2}".format(PIPELINE_REF_ENV, r.returncode, r.stdout))

        # #928: a stage called through an annotated tag (the floating `@v2`
        # release.yml recreates with `git tag -fa`) resolves its pipeline ref
        # to the TAG OBJECT's SHA, while the checkout sits at the commit it
        # tags. The pipeline is checked out the way actions/checkout does it
        # for a SHA ref: a shallow fetch of that one object, then a forced
        # checkout of it, which leaves HEAD on the peeled commit.
        _git(src, "tag", "-a", "v2", "-m", "floating v2")
        tag_sha = _git(src, "rev-parse", "v2").stdout.strip()
        _git(src, "config", "uploadpack.allowAnySHA1InWant", "true")
        # A tag on another commit, kept off main so every later workspace
        # still clones the pipeline at pipe_sha.
        _git(src, "checkout", "-q", "-b", "elsewhere")
        _git(src, "commit", "-q", "--allow-empty", "-m", "elsewhere")
        _git(src, "tag", "-a", "v9", "-m", "a tag on another commit")
        other_tag_sha = _git(src, "rev-parse", "v9").stdout.strip()
        _git(src, "checkout", "-q", "main")
        def tag_workspace(name):
            ws_t = os.path.join(tmp, name)
            pipe_dir = os.path.join(ws_t, PIPE)
            os.makedirs(pipe_dir)
            _git(ws_t, "init", "-q")
            _git(pipe_dir, "init", "-q")
            _git(pipe_dir, "remote", "add", "origin", "file://" + src)
            _git(pipe_dir, "-c", "protocol.version=2", "fetch", "-q", "--no-tags", "--depth=1",
                 "origin", tag_sha)
            _git(pipe_dir, "checkout", "-q", "--force", tag_sha)
            return ws_t, pipe_dir

        ws_tag, pipe_dir = tag_workspace("ws-annotated-pre")
        if _git(pipe_dir, "rev-parse", "HEAD").stdout.strip() != pipe_sha:
            bad.append("annotated tag: the checkout by tag object did not land on the tagged "
                       "commit, so this scenario does not reproduce #928")
        peel = '"$(git -C "$p" rev-parse --verify -q "${WC_PIPELINE_REF}^{commit}" 2>/dev/null)"'
        if GUARD_RUN.count(peel) != 1:
            bad.append("annotated tag: GUARD_RUN no longer carries the #928 peel text exactly "
                       "once, so the pre-#928 control below cannot be built from it. Update "
                       "this scenario with the guard")
        r = _run_guard(ws_tag, script=GUARD_RUN.replace(peel, '"$WC_PIPELINE_REF"'),
                       pipeline_ref=tag_sha)
        if r.returncode == 0:
            bad.append("annotated tag: the pre-#928 guard (raw ref against HEAD) was expected "
                       "to refuse it, got a pass, so this scenario does not reproduce #928")
        ws_tag, _ = tag_workspace("ws-annotated")
        r = _run_guard(ws_tag, pipeline_ref=tag_sha)
        if r.returncode != 0:
            bad.append("annotated tag: a pipeline ref that is an annotated tag's object SHA, "
                       "checked out at the commit it tags, was expected to pass (#928), got "
                       "rc={0}: {1}{2}".format(r.returncode, r.stdout, r.stderr))
        ws_other = workspace("ws-other-tag", "main")
        _git(os.path.join(ws_other, PIPE), "fetch", "-q", "origin", "+refs/tags/*:refs/tags/*")
        r = _run_guard(ws_other, pipeline_ref=other_tag_sha)
        if r.returncode == 0 or os.path.lexists(os.path.join(ws_other, PIPE)):
            bad.append("annotated tag on another commit: expected a refusal that removes the "
                       "directory, got rc={0}: {1}".format(r.returncode, r.stdout))

        for branch, target in (("symlink-dot", "."), ("symlink-other", "evil")):
            # The pre-fix one-liner is fooled: proves the scenario is real.
            ws = workspace("ws-pre-" + branch, branch)
            if not os.path.islink(os.path.join(ws, PIPE)):
                bad.append("{0}: the forced checkout did not replace the pipeline directory "
                           "with the symlink, so this scenario does not reproduce the "
                           "finding".format(branch))
            r = _run_guard(ws, script=PRE_FIX_RUN)
            if r.returncode != 0:
                bad.append("{0}: the pre-fix invocation was expected to be fooled (pass), "
                           "got rc={1}".format(branch, r.returncode))
            # The shipped guard refuses it and leaves nothing at the path.
            ws = workspace("ws-" + branch, branch)
            r = _run_guard(ws, pipeline_ref=pipe_sha)
            if r.returncode == 0:
                bad.append("{0}: expected a refusal, got a pass: {1}".format(branch, r.stdout))
            if "::error::wing-commander: .wing-commander-pipeline is no longer" not in r.stdout:
                bad.append("{0}: no ::error:: for the replaced pipeline: {1}".format(branch, r.stdout))
            if os.path.lexists(os.path.join(ws, PIPE)):
                bad.append("{0}: something still sits at {1} after the refusal, so a later "
                           "`uses: ./{1}/...` could load branch code".format(branch, PIPE))
            if not os.path.isfile(os.path.join(ws, "README")) or (
                    target != "." and not os.path.isdir(os.path.join(ws, target))):
                bad.append("{0}: the refusal removed more than the path itself".format(branch))

        ws = workspace("ws-hostile", "hostile")
        with open(os.path.join(ws, PIPE, trusted)) as f:
            if f.read() != "EVIL\n":
                bad.append("hostile branch: the forced checkout did not overwrite the "
                           "pipeline file, so this scenario does not reproduce #611")
        r = _run_guard(ws, pipeline_ref=pipe_sha)
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
        print("[ok] guard: passes a clean branch and a missing root repo; refuses a pipeline at "
              "another commit; passes a pipeline ref that is an annotated tag's object SHA "
              "and refuses one tagging another commit (#928); refuses and restores on a "
              "branch tracking files under the "
              "directory; refuses a branch tracking the path as a symlink (to . and to its own "
              "directory) that fools the pre-fix one-liner, and leaves nothing at the path")
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
