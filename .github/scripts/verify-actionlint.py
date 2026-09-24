#!/usr/bin/env python3
"""Gate 46 -- actionlint over every workflow file, at PR time.

GitHub evaluates a ${{ }} reference to a not-yet-defined step id as
empty, silently, so an `if:` reading a step defined below it is
constant-false and the step never runs. GitHub's own parser cannot flag
that (expression semantics are outside its scope); actionlint type-checks
each expression against a steps context built from the steps ABOVE it, so
a use-before-definition is a hard diagnostic naming the line.

release.yml's Gate 1a has run actionlint since specs/031, but only on a
workflow_dispatch release. This is the PR-time (and, via
run-local-gates.py, pre-push) half, over EVERY workflow file rather than
the published stages alone -- lint-workflows.yml and release.yml carry
${{ }} expressions too. Gate 1a's pass 1 now invokes this same script, so
the two answers cannot drift (the Gate 31 arrangement). Its pass 2 -- the
shellcheck pass over the opt-in list, and the closure check on that list
-- is verify-stage-shell-lint.py (Gate 48), which drives a pinned
shellcheck directly; the pinned-binary cache both gates download into
and the allowance strings below live in wc_actionlint.py.

THE ALLOWANCES (actionlint 1.7.7 schema gaps, all verified real)
------------------------------------------------------------------
- github.job_workflow_sha: a documented context property 1.7.7 does not
  know (specs/031 research.md D3). -ignore'd outright -- the message
  names the property, so nothing else can hide behind the pattern.
- environment.deployment: GitHub accepts and acts on the key
  (specs/031-stage-environment-binding/contracts/environment-binding.md);
  1.7.7's schema knows only name/url. NOT -ignore'd: counted instead,
  exactly one diagnostic per `deployment:` line, so the allowance goes
  loudly stale the day actionlint learns the key. See classify().
- container.credentials as an expression: GitHub accepts and acts on an
  expression-valued `credentials:` that resolves to a mapping at runtime
  (specs/044-private-registry-credentials/research.md D3, measured
  2026-09-07 on PR #285); 1.7.7's schema requires credentials to be a
  literal mapping node with both username and password keys present
  statically, so it emits two diagnostics per binding site ("credentials"
  section is scalar node but mapping node is expected, and both
  "username" and "password" must be specified in "credentials" section).
  NOT -ignore'd: counted instead, exactly two diagnostics per
  `credentials: >-` line, so this allowance goes loudly stale the day
  actionlint learns the expression-valued shape. See classify().

Shell lint of run: blocks is Gate 48's job (verify-stage-shell-lint.py;
#149 tracks widening its opt-in list). `-shellcheck= -pyflakes=` keeps
this gate's subject the schema/expression pass alone, byte-identical
between CI and run-local-gates.py.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_actionlint import (  # noqa: E402
    COUNTED, CRED_SCALAR, CRED_USERPASS, IGNORED, KNOWN, ensure_actionlint)

WORKFLOWS_DIR = ".github/workflows"
# Every workflow that publishes a stage checks itself out here, pinned at
# its own ref, so `uses: ./.wing-commander-pipeline/.github/actions/X`
# resolves during a real run (specs/010-reusable-pipeline). This gate must
# still check those call sites' inputs (a real diagnostic there is exactly
# what it exists to catch), but it must never resolve them against
# whatever this checkout happens to carry on disk: CI's lint job never
# creates it, so a real run always lints the SAME ref the workflow files
# themselves are at, and this gate has to match that or it answers a
# different question than CI does. It also must never touch the real
# directory in place -- during a live implement.yml run (implement.yml
# running the gate suite under a 10-minute timeout) this IS the running
# job's own checkout, and every later `uses: ./.wing-commander-pipeline/
# ...` step, including the failure reporter, depends on it staying put.
# See _lint_tree() (#442, and the review of #479 that replaced an earlier
# rename-based attempt).
STALE_PIPELINE_DIR = ".wing-commander-pipeline"
# The binding is a job-level environment sub-key: jobs(0) / <job>(2) /
# environment(4) / deployment(6). Matched on the key's own line rather
# than the full binding so this file never contains a literal GitHub
# expression (release.yml Gate 1a's original reasoning, kept verbatim).
BINDING_RE = re.compile(r"^ {6}deployment:")
# Same reasoning, for the container.credentials expression binding
# (jobs(0) / <job>(2) / container(4) / credentials(6)) -- specs/044.
CRED_BINDING_RE = re.compile(r"^ {6}credentials: >-$")


def ensure_binary():
    """Path to the pinned actionlint -- wc_actionlint.ensure_actionlint,
    which Gate 48 shares, so both passes lint with one binary."""
    return ensure_actionlint()


def _lint_tree(root="."):
    """A scratch copy of `root`'s .github/, plus a second copy of
    .github/actions/ laid down at .wing-commander-pipeline/.github/actions/,
    so actionlint resolves BOTH `uses: ./.github/actions/X` and `uses:
    ./.wing-commander-pipeline/.github/actions/X` against this same
    working tree's own actions -- always the ref being linted, never
    whatever a real or leftover self-checkout happens to carry (#442).

    A real copy, not a symlink: actionlint reads `uses:` paths through
    Go's directory walk, which does not follow a symlinked ancestor
    directory the way a shell `cd` would, so a symlinked
    .wing-commander-pipeline resolves to nothing and the call sites under
    it go unchecked again -- the same blind spot this replaces.

    The real STALE_PIPELINE_DIR, if one is present in `root` (a running
    implement.yml job's own live checkout, or a leftover from one), is
    never opened, moved or deleted -- only .github/ is copied out of
    `root`. Caller removes the returned directory.

    actionlint resolves a local `uses:` path only inside a directory it
    can root at a `.git` -- measured empirically fixing #442's fix: the
    "action" rule runs (it logs every `uses:` it checks) but silently
    skips local ones with no diagnostic and no error, gate-shaped or
    otherwise, when `.git` is missing, which would have made this gate
    stop checking every local composite call site rather than just the
    self-checkout ones. A directory-only `git init` supplies that marker
    without a commit, an index, or reading anything from `root`'s own
    .git.
    """
    td = tempfile.mkdtemp(prefix="wc-gate46-")
    shutil.copytree(os.path.join(root, ".github"), os.path.join(td, ".github"))
    shutil.copytree(os.path.join(td, ".github", "actions"),
                     os.path.join(td, STALE_PIPELINE_DIR, ".github", "actions"))
    subprocess.run(["git", "init", "-q"], cwd=td, check=True,
                   capture_output=True)
    return td


def workflow_files(root="."):
    base = os.path.join(root, WORKFLOWS_DIR)
    return sorted(glob.glob(os.path.join(base, "*.yml"))
                  + glob.glob(os.path.join(base, "*.yaml")))


def count_bindings(files):
    total = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            total += sum(1 for line in fh if BINDING_RE.match(line))
    return total


def count_cred_bindings(files):
    total = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            total += sum(1 for line in fh if CRED_BINDING_RE.match(line))
    return total


def run_actionlint(binary, files, extra_ignores=(), cwd=None):
    """Diagnostic lines from the schema/expression pass, one per line.

    `cwd`, with `files` given relative to it, keeps the printed paths
    (and so this gate's ordinary output) identical whether `files` came
    straight from the working tree or from a _lint_tree() copy.
    """
    cmd = [binary, "-no-color", "-oneline", "-shellcheck=", "-pyflakes=",
           "-ignore", IGNORED]
    for pat in extra_ignores:
        cmd += ["-ignore", pat]
    proc = subprocess.run(cmd + list(files), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)
    out = (proc.stdout or "") + (proc.stderr or "")
    return [l for l in out.splitlines() if l.strip()]


def _check_count_allowance(errors, seen, bindings, label):
    if bindings > 0 and seen == 0:
        errors.append(f"actionlint no longer flags {label} "
                      f"({bindings} binding(s), 0 diagnostics) -- its schema "
                      f"has learned the shape. Delete this allowance and the "
                      f"counting around it.")
    elif seen != bindings:
        errors.append(f"expected one {label} diagnostic per "
                      f"binding ({bindings}), saw {seen} -- either a binding "
                      f"is going unlinted or an unrelated diagnostic is "
                      f"being counted as known.")


def classify(diag_lines, bindings, cred_bindings=0):
    """The allowance accounting, as a pure function so --self-test can
    drive its failure branches without faking a linter run.

    Returns (errors, other_lines): errors non-empty means the gate
    fails; other_lines are the diagnostics beyond the accounted
    environment.deployment and container.credentials allowances, for
    printing.
    """
    seen = sum(1 for l in diag_lines if KNOWN in l)
    seen_cred_scalar = sum(1 for l in diag_lines if CRED_SCALAR in l)
    seen_cred_userpass = sum(1 for l in diag_lines if CRED_USERPASS in l)
    other = [l for l in diag_lines
             if not any(c in l for c in COUNTED)]
    errors = []
    if other:
        errors.append(f"actionlint reported {len(other)} diagnostic(s) "
                      f"beyond the known environment.deployment and "
                      f"container.credentials schema gaps.")
    _check_count_allowance(errors, seen, bindings, "environment.deployment")
    _check_count_allowance(errors, seen_cred_scalar, cred_bindings,
                           "credentials-is-scalar")
    _check_count_allowance(errors, seen_cred_userpass, cred_bindings,
                           "credentials username/password")
    return errors, other


def run_gate():
    files = workflow_files()
    # A derived-empty set must not read as a clean pass -- the same
    # reasoning as Gate 7's stages == 0 guard.
    if not files:
        sys.exit(f"no workflow files found under {WORKFLOWS_DIR} -- "
                 f"this gate linted nothing. Run from the repository root.")
    binary = ensure_binary()
    tree = _lint_tree()
    try:
        tree_files = ["./" + os.path.relpath(f, tree)
                      for f in workflow_files(tree)]
        diags = run_actionlint(binary, tree_files, cwd=tree)
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    bindings = count_bindings(files)
    cred_bindings = count_cred_bindings(files)
    errors, other = classify(diags, bindings, cred_bindings)
    for line in other:
        print(line)
    for e in errors:
        print(f"::error::{e}")
    print(f"Gate 46: {len(files)} workflow file(s), {bindings} deployment "
          f"binding(s), {cred_bindings} credentials binding(s), "
          f"{len(diags) - len(other)} accounted diagnostic(s), "
          f"{len(other)} other.")
    return 1 if errors else 0


def self_test():
    """The linter flags what this gate exists to catch, and the
    accounting's failure branches actually fire.

    The forward-reference fixture is the PR #277 shape itself: an `if:`
    reading a step id defined below it. If a future actionlint bump
    stops flagging that, this gate is no longer checking the thing it
    was built for, and this is what says so.
    """
    binary = ensure_binary()
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    with tempfile.TemporaryDirectory() as td:
        fwd = os.path.join(td, "forward-ref.yml")
        with open(fwd, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "on: push\n"
                "jobs:\n"
                "  a:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - name: reads an id defined below\n"
                "        if: steps.later.outputs.x != ''\n"
                "        run: echo unreachable\n"
                "      - id: later\n"
                "        run: echo \"x=1\" >> \"$GITHUB_OUTPUT\"\n")
        diags = run_actionlint(binary, [fwd])
        check("use-before-definition is a diagnostic",
              any('"later" is not defined' in l for l in diags),
              f"got {diags!r}")
        errors, _ = classify(diags, 0)
        check("and the accounting fails the gate on it", bool(errors))

        binding = os.path.join(td, "binding.yml")
        with open(binding, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "on: push\n"
                "jobs:\n"
                "  a:\n"
                "    runs-on: ubuntu-latest\n"
                "    environment:\n"
                "      name: pipeline\n"
                "      deployment: wc-test\n"
                "    steps:\n"
                "      - run: echo ok\n")
        diags = run_actionlint(binary, [binding])
        bindings = count_bindings([binding])
        check("a deployment binding is counted, not ignored",
              bindings == 1 and sum(1 for l in diags if KNOWN in l) == 1,
              f"bindings={bindings} diags={diags!r}")
        errors, _ = classify(diags, bindings)
        check("and balances to a clean pass", not errors, f"got {errors!r}")

        cred_binding = os.path.join(td, "cred-binding.yml")
        with open(cred_binding, "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "on:\n"
                "  workflow_call:\n"
                "    secrets:\n"
                "      container-registry-username:\n"
                "        required: false\n"
                "      container-registry-password:\n"
                "        required: false\n"
                "jobs:\n"
                "  a:\n"
                "    runs-on: ubuntu-latest\n"
                "    container:\n"
                "      image: node:20\n"
                "      credentials: >-\n"
                "        ${{\n"
                "          (secrets.container-registry-username != '' && secrets.container-registry-password != '')\n"
                "            && fromJSON(format('{{\"username\":{0},\"password\":{1}}}', toJSON(secrets.container-registry-username), toJSON(secrets.container-registry-password)))\n"
                "            || fromJSON('{}')\n"
                "        }}\n"
                "    steps:\n"
                "      - run: echo ok\n")
        diags = run_actionlint(binary, [cred_binding])
        cred_bindings = count_cred_bindings([cred_binding])
        check("a credentials binding is counted, not ignored",
              cred_bindings == 1
              and sum(1 for l in diags if CRED_SCALAR in l) == 1
              and sum(1 for l in diags if CRED_USERPASS in l) == 1,
              f"cred_bindings={cred_bindings} diags={diags!r}")
        errors, _ = classify(diags, 0, cred_bindings)
        check("and balances to a clean pass", not errors, f"got {errors!r}")

        typo_root = os.path.join(td, "typo-fixture")
        act_dir = os.path.join(typo_root, ".github", "actions", "wc-typo-test")
        os.makedirs(os.path.join(typo_root, ".github", "workflows"))
        os.makedirs(act_dir)
        with open(os.path.join(act_dir, "action.yml"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(
                "name: wc-typo-test\n"
                "inputs:\n"
                "  sweep-runs:\n"
                "    required: false\n"
                "runs:\n"
                "  using: composite\n"
                "  steps:\n"
                "    - run: echo ok\n"
                "      shell: bash\n")
        with open(os.path.join(typo_root, ".github", "workflows", "typo.yml"),
                  "w", encoding="utf-8", newline="\n") as f:
            f.write(
                "on: push\n"
                "jobs:\n"
                "  a:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: ./.wing-commander-pipeline/.github/actions/wc-typo-test\n"
                "        with:\n"
                "          sweep-runz: x\n")
        # A stale, differently-typo'd decoy checkout sitting in the fixture
        # root (the #442/#479-review shape) -- must not change the answer:
        # _lint_tree() always copies from the fixture's own .github/actions,
        # never from whatever a leftover checkout happens to carry.
        decoy_dir = os.path.join(typo_root, STALE_PIPELINE_DIR, ".github",
                                 "actions", "wc-typo-test")
        os.makedirs(decoy_dir)
        with open(os.path.join(decoy_dir, "action.yml"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(
                "name: wc-typo-test\n"
                "inputs:\n"
                "  sweep-runz:\n"
                "    required: false\n"
                "runs:\n"
                "  using: composite\n"
                "  steps:\n"
                "    - run: echo ok\n"
                "      shell: bash\n")

        tree = _lint_tree(typo_root)
        try:
            typo_files = ["./" + os.path.relpath(f, tree)
                          for f in workflow_files(tree)]
            diags = run_actionlint(binary, typo_files, cwd=tree)
        finally:
            shutil.rmtree(tree, ignore_errors=True)
        check("a call-site input typo through "
              "./.wing-commander-pipeline/... is caught, even with a "
              "stale, differently-typo'd checkout present in the tree",
              any('"sweep-runz" is not defined' in l for l in diags),
              f"got {diags!r}")
        check("the fixture's own stale checkout was never touched",
              os.path.isdir(os.path.join(typo_root, STALE_PIPELINE_DIR)),
              "decoy directory missing after the run")

    # The accounting's failure branches, driven directly (pure function).
    errors, _ = classify([], 3)
    check("stale allowance fires when bindings exist but nothing is flagged",
          any("has learned the shape" in e for e in errors))
    errors, _ = classify([f"a.yml:1:1: {KNOWN} [syntax-check]"], 2)
    check("an unlinted binding fires the imbalance branch",
          any("going unlinted" in e for e in errors))
    errors, _ = classify(["a.yml:1:1: something real [expression]"], 0)
    check("a real diagnostic is never absorbed by the allowance",
          any("beyond the known" in e for e in errors))
    errors, _ = classify([], 0, 2)
    check("stale credentials allowance fires when bindings exist but "
          "nothing is flagged",
          any("has learned the shape" in e for e in errors))
    errors, _ = classify(
        [f"a.yml:1:1: {CRED_SCALAR} [syntax-check]"], 0, 2)
    check("an unlinted credentials binding fires the imbalance branch "
          "(username/password half missing)",
          any("going unlinted" in e for e in errors))

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or "
                 f"nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
