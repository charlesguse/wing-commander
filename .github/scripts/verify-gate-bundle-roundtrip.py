#!/usr/bin/env python3
"""Gate 155 -- a workspace bundle survives the round trip it exists for
(spec 095, contracts/workspace-bundle.md).

WHY THIS EXISTS
---------------
The agent's commits leave the job that wrote them as a git bundle
(_shared/build-gate-bundle.sh), are gated in a credential-free job
(_shared/contained-gate-suite.sh) and are restored in the job that pushes
them (_shared/restore-gate-bundle.sh). Each script is simple on its own;
what can break is the hand-off between them. The first version fetched the
bundle with a `refs/*` refspec while the bundle's one ref is `HEAD`: the
fetch exited 0, imported nothing, every gate verdict read "head could not be
checked out" and every restore failed -- and every gate stayed green,
because none drove the three scripts end to end (code review of #990).

WHAT IT CHECKS
--------------
Against real local git repositories -- an agent clone that commits past a
base, a trusted clone and a publisher clone that hold only the base:
  1. a head whose suite passes is bundled, gated (verdict pass, bound to the
     head and the trusted SHA) and restored (HEAD is that commit, on the
     named branch);
  2. a head whose suite fails yields verdict fail naming the first FAIL line;
  3. a head that made no commits since the base still round-trips, without
     shipping the whole history;
  4. the restore refuses a head the producer did not report, and a missing
     bundle;
  5. a missing bundle, or a head that deleted run-local-gates.py, is a fail
     verdict, never a pass or a skip;
  6. a suite that outlives its time budget is stopped and is a fail verdict
     naming the budget and any failure logged before the stop, never an
     absent verdict (run 40101571746) -- under a BusyBox-shaped timeout too,
     and a timeout that refuses -k, or a leading-zero budget, never turns a
     passing suite red or drops the verdict.
--self-test reruns the checks with each script's fetch reverted to the
`refs/*` refspec, and with the restore's head check removed, and asserts
each mutation is caught.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 147. It is
numbered 155, not 147: 141-146 were taken by spec 110's PR #982 and 147-148
by spec 112's PR #1003, which claimed them first among the open
lifecycle branches.

Usage: python3 .github/scripts/verify-gate-bundle-roundtrip.py [--self-test]
Requires: bash, git, jq.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(HERE, "..", "actions", "_shared")
SCRIPTS = ("build-gate-bundle.sh", "contained-gate-suite.sh", "restore-gate-bundle.sh",
           "git-push-hardening.sh", "gate-bundle-import.sh")
PASSING_SUITE = "print('PASS  verify-x.py')\n"
FAILING_SUITE = "import sys\nprint('FAIL  verify-x.py (planted)')\nsys.exit(1)\n"
# No flush=True: run-local-gates.py never flushes, so this must not either.
SLOW_SUITE = ("import time\nprint('FAIL  verify-y.py (planted, before the stop)')\n"
              "time.sleep(8)\nprint('PASS  verify-x.py')\n")
# A BusyBox-shaped timeout: no long options, and a stop exits 143 (the TERM
# it sent), not 124. The real one does the rest.
SHORT_OPTS_TIMEOUT = ('#!/bin/sh\ncase " $* " in *" --"*) echo "timeout: unrecognized option" >&2; '
                      'exit 1 ;; esac\n{0} "$@"\nrc=$?\n[ "$rc" -eq 124 ] && exit 143\nexit "$rc"\n')
# An old BusyBox timeout: refuses -k as well.
NO_KILL_TIMEOUT = '#!/bin/sh\necho "timeout: invalid option -- k" >&2\nexit 1\n'

TRUSTED_SHA = "b" * 40
BUDGET_RUNS = []  # one entry per budget_checks() run


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                           "-c", "commit.gpgsign=false"] + list(args), cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def sh(shared, script, args, cwd, env_extra=None):
    out = tempfile.mktemp()
    # A host's PYTHONUNBUFFERED would hide a suite whose output is lost when
    # it is stopped; a runner sets none.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
    env.update(GITHUB_OUTPUT=out, **(env_extra or {}))
    proc = subprocess.run(["bash", os.path.join(shared, script)] + list(args), cwd=cwd,
                          env=env, capture_output=True, text=True)
    outputs = {}
    if os.path.exists(out):
        for line in open(out, encoding="utf-8").read().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                outputs[k] = v
    return proc.returncode, proc.stdout + proc.stderr, outputs


def world(tmp, agent_change):
    """origin with a base commit; an agent clone that applies agent_change;
    trusted and publisher clones at the base. Returns paths and SHAs."""
    origin = os.path.join(tmp, "origin")
    os.makedirs(origin)
    git(origin, "init", "-q", "-b", "main")
    write(origin, "HISTORY", "an earlier commit, so the base is not a root\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "history")
    write(origin, ".github/scripts/run-local-gates.py", PASSING_SUITE)
    write(origin, "README", "base\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "base")
    base = git(origin, "rev-parse", "HEAD")
    clones = {}
    for name in ("agent", "trusted", "publisher"):
        clones[name] = os.path.join(tmp, name)
        git(tmp, "clone", "-q", origin, clones[name])
    agent_change(clones["agent"])
    head = git(clones["agent"], "rev-parse", "HEAD")
    return clones, base, head


def commit_file(rel, text):
    def change(repo):
        write(repo, rel, text)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "agent: " + rel)
    return change


def remove_suite(repo):
    git(repo, "rm", "-q", ".github/scripts/run-local-gates.py")
    git(repo, "commit", "-q", "-m", "agent: drop the suite")


def no_change(_repo):
    pass


def stub_timeout(tmp, body):
    """-> a PATH whose `timeout` is body, ahead of the rest of PATH."""
    stub = os.path.join(tmp, "stub-bin")
    os.makedirs(stub)
    path = os.path.join(stub, "timeout")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, 0o755)
    return stub + os.pathsep + os.environ.get("PATH", "")


def round_trip(shared, tmp, change, site="board-fix", base_override=None, meta_edit=None,
               gate_env=None):
    """-> (verdict dict or None, build/gate output, clones, base, head, bundle dir)."""
    clones, base, head = world(tmp, change)
    bundle = os.path.join(tmp, "bundle")
    rc, out, outs = sh(shared, "build-gate-bundle.sh",
                       [site, base_override or base, bundle], clones["agent"])
    if rc == 0 and meta_edit:
        meta_path = os.path.join(bundle, "meta.json")
        meta = json.load(open(meta_path))
        meta.update(meta_edit(base, head))
        json.dump(meta, open(meta_path, "w"))
    if rc != 0:
        return None, "build exited {0}: {1}".format(rc, out), clones, base, head, bundle
    verdict_path = os.path.join(tmp, "verdict.json")
    rc2, out2, _ = sh(shared, "contained-gate-suite.sh",
                      [site, bundle, TRUSTED_SHA, verdict_path], clones["trusted"], gate_env)
    verdict = None
    if os.path.exists(verdict_path):
        with open(verdict_path, encoding="utf-8") as fh:
            verdict = json.load(fh)
    return verdict, out + out2, clones, base, head, bundle


def checks(shared):
    failures = []

    def ck(name, cond, detail=""):
        if not cond:
            failures.append("{0} -- {1}".format(name, detail))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, clones, base, head, bundle = round_trip(shared, tmp,
                                                        commit_file("src.txt", "fix\n"))
        ck("a passing head is gated green and bound to it",
           v is not None and v.get("outcome") == "pass" and v.get("head_sha") == head
           and v.get("trusted_sha") == TRUSTED_SHA, "verdict={0}\n{1}".format(v, out[-800:]))
        rc, rout, routs = sh(shared, "restore-gate-bundle.sh", [bundle, head, "fix/7-x"],
                             clones["publisher"])
        ck("the publisher restores exactly that head on the named branch",
           rc == 0 and git(clones["publisher"], "rev-parse", "HEAD") == head
           and git(clones["publisher"], "rev-parse", "--abbrev-ref", "HEAD") == "fix/7-x"
           and routs.get("head-sha") == head, "rc={0}\n{1}".format(rc, rout))
        rc, rout, _ = sh(shared, "restore-gate-bundle.sh", [bundle, base, "fix/7-x"],
                         clones["publisher"])
        other = "c" * 40
        rc2, rout2, _ = sh(shared, "restore-gate-bundle.sh", [bundle, other, "fix/7-x"],
                           clones["publisher"])
        ck("the restore refuses a head the producer did not report",
           rc2 != 0 and "does not hold" in rout2, "rc={0}\n{1}".format(rc2, rout2))
        rc3, rout3, _ = sh(shared, "restore-gate-bundle.sh",
                           [os.path.join(tmp, "nowhere"), head, "b"], clones["publisher"])
        ck("the restore refuses a missing bundle", rc3 != 0, rout3)
        corrupt = os.path.join(tmp, "corrupt")
        os.makedirs(corrupt)
        with open(os.path.join(corrupt, "bundle.git"), "w") as fh:
            fh.write("not a bundle\n")
        rc4, rout4, _ = sh(shared, "restore-gate-bundle.sh", [corrupt, head, "b"],
                           clones["publisher"])
        ck("a bundle that fails verification is refused with an annotation saying the "
           "containment could not be established",
           rc4 != 0 and "::error::" in rout4 and "containment could not be established" in rout4,
           rout4)
        # The verdict writer's copy is write-protected before the head is
        # checked out (static: this harness runs as whatever user CI uses,
        # root included, for whom a mode bit proves nothing).
        text = open(os.path.join(shared, "contained-gate-suite.sh"), encoding="utf-8").read()
        protect = text.find('chmod -R a-w "$trusted_copy"')
        checkout = text.find("git worktree add")
        ck("the verdict writer's copy is write-protected before the head is checked out",
           0 <= protect < checkout, "chmod at {0}, worktree add at {1}".format(protect, checkout))
        verdict_path = os.path.join(tmp, "missing-verdict.json")
        sh(shared, "contained-gate-suite.sh",
           ["board-fix", os.path.join(tmp, "nowhere"), TRUSTED_SHA, verdict_path],
           clones["trusted"])
        mv = json.load(open(verdict_path)) if os.path.exists(verdict_path) else {}
        ck("a missing bundle is a fail verdict, never a skip",
           mv.get("outcome") == "fail" and "missing" in mv.get("first_failure", ""), str(mv))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, *_rest = round_trip(shared, tmp, commit_file(".github/scripts/"
                                                             "run-local-gates.py", FAILING_SUITE))
        ck("a failing head is gated red, naming the first FAIL line",
           v is not None and v.get("outcome") == "fail"
           and v.get("first_failure", "").startswith("FAIL  verify-x.py"),
           "verdict={0}\n{1}".format(v, out[-800:]))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, clones, base, head, bundle = round_trip(shared, tmp, no_change)
        heads = git(clones["agent"], "bundle", "list-heads", os.path.join(bundle, "bundle.git"))
        verify = subprocess.run(["git", "bundle", "verify", os.path.join(bundle, "bundle.git")],
                                cwd=clones["agent"], capture_output=True, text=True)
        ck("a head with no new commits still round-trips",
           v is not None and v.get("outcome") == "pass" and v.get("head_sha") == head == base,
           "verdict={0}\n{1}".format(v, out[-800:]))
        ck("a head with no new commits ships one commit, not the whole history",
           "requires" in (verify.stdout + verify.stderr) and head in heads,
           verify.stdout + verify.stderr)

    with tempfile.TemporaryDirectory() as tmp:
        # A resumed branch whose recorded base this repository does not hold:
        # the bundle must not guess a prerequisite.
        v, out, clones, base, head, bundle = round_trip(
            shared, tmp, commit_file("src.txt", "fix\n"), base_override="1" * 40)
        rc, rout, _ = sh(shared, "restore-gate-bundle.sh", [bundle, head, "b"],
                         clones["publisher"])
        ck("a base the agent's repository does not hold still round-trips",
           v is not None and v.get("outcome") == "pass" and v.get("head_sha") == head
           and rc == 0, "verdict={0}\n{1}\n{2}".format(v, out[-600:], rout))

    with tempfile.TemporaryDirectory() as tmp:
        # meta.json naming a commit other than the bundle's HEAD (one the
        # trusted checkout holds, so a checkout of it would succeed).
        v, out, *_rest = round_trip(shared, tmp, commit_file("src.txt", "fix\n"),
                                    meta_edit=lambda base, head: {"head_sha": base})
        ck("a bundle whose HEAD is not its metadata's head_sha is red",
           v is not None and v.get("outcome") == "fail"
           and "does not match" in v.get("first_failure", ""), str(v))

    with tempfile.TemporaryDirectory() as tmp:
        # The trusted commit gained the suite after the head was cut: the head
        # never had it, so it did not remove it.
        origin = os.path.join(tmp, "origin")
        os.makedirs(origin)
        git(origin, "init", "-q", "-b", "main")
        write(origin, "README", "before the suite\n")
        git(origin, "add", "-A")
        git(origin, "commit", "-q", "-m", "before the suite")
        cut = git(origin, "rev-parse", "HEAD")
        write(origin, ".github/scripts/run-local-gates.py", PASSING_SUITE)
        git(origin, "add", "-A")
        git(origin, "commit", "-q", "-m", "the suite arrives")
        trusted = os.path.join(tmp, "trusted")
        agent = os.path.join(tmp, "agent")
        git(tmp, "clone", "-q", origin, trusted)
        git(tmp, "clone", "-q", origin, agent)
        git(agent, "checkout", "-q", "-b", "spec/x", cut)
        write(agent, "src.txt", "fix\n")
        git(agent, "add", "-A")
        git(agent, "commit", "-q", "-m", "agent, on a branch cut before the suite")
        pre_head = git(agent, "rev-parse", "HEAD")
        bundle = os.path.join(tmp, "pre-bundle")
        sh(shared, "build-gate-bundle.sh", ["board-fix", cut, bundle], agent)
        verdict_path = os.path.join(tmp, "pre-verdict.json")
        sh(shared, "contained-gate-suite.sh", ["board-fix", bundle, TRUSTED_SHA, verdict_path],
           trusted)
        pv = json.load(open(verdict_path)) if os.path.exists(verdict_path) else {}
        ck("a head that predates the suite is red, saying so -- not 'removed'",
           pv.get("outcome") == "fail" and pv.get("head_sha") == pre_head
           and "predates the gate suite" in pv.get("first_failure", ""), str(pv))

    with tempfile.TemporaryDirectory() as tmp:
        v, out, *_rest = round_trip(shared, tmp, remove_suite)
        ck("a head that deleted run-local-gates.py is red, never a skip",
           v is not None and v.get("outcome") == "fail"
           and "removed run-local-gates.py" in v.get("first_failure", ""), str(v))
    return failures


def budget_checks(shared):
    """The suite time budget (scenario 6). Apart from checks() so --self-test
    runs these slow round trips only for the mutations of the budget path,
    never once per mutation (the suite this gate sits in is what the budget
    is for)."""
    BUDGET_RUNS.append(shared)
    failures = []

    def ck(name, cond, detail=""):
        if not cond:
            failures.append("{0} -- {1}".format(name, detail))

    if shutil.which("timeout"):
        with tempfile.TemporaryDirectory() as tmp:
            v, out, *_rest = round_trip(shared, tmp,
                                        commit_file(".github/scripts/run-local-gates.py",
                                                    SLOW_SUITE),
                                        gate_env={"WC_GATE_SUITE_TIMEOUT_SECONDS": "2"})
            ck("a suite that outlives its time budget is stopped and red, naming the budget "
               "and the failure it logged before the stop",
               v is not None and v.get("outcome") == "fail"
               and "did not finish within its time budget (2s)" in v.get("first_failure", "")
               and "before the stop: FAIL  verify-y.py" in v.get("first_failure", ""),
               "verdict={0}\n{1}".format(v, out[-800:]))
        with tempfile.TemporaryDirectory() as tmp:
            stub = stub_timeout(tmp, SHORT_OPTS_TIMEOUT.format(shutil.which("timeout")))
            v, out, *_rest = round_trip(shared, tmp,
                                        commit_file(".github/scripts/run-local-gates.py",
                                                    SLOW_SUITE),
                                        gate_env={"WC_GATE_SUITE_TIMEOUT_SECONDS": "2",
                                                  "PATH": stub})
            ck("a timeout with no long options that exits 143 (BusyBox) still bounds the "
               "suite and names the budget",
               v is not None and "did not finish within its time budget (2s)"
               in v.get("first_failure", ""), "verdict={0}\n{1}".format(v, out[-800:]))
    with tempfile.TemporaryDirectory() as tmp:
        stub = stub_timeout(tmp, NO_KILL_TIMEOUT)
        v, out, *_rest = round_trip(shared, tmp, no_change, gate_env={"PATH": stub})
        ck("a timeout that refuses -k leaves a passing suite unbounded and green, never red "
           "before it starts, and says it ran with no budget",
           v is not None and v.get("outcome") == "pass" and "no time budget of its own" in out,
           "verdict={0}\n{1}".format(v, out[-800:]))
    with tempfile.TemporaryDirectory() as tmp:
        v, out, *_rest = round_trip(shared, tmp, no_change,
                                    gate_env={"WC_GATE_SUITE_TIMEOUT_MINUTES": "08"})
        ck("a budget with a leading zero (08) is read as decimal minutes, never an octal "
           "error that writes no verdict",
           v is not None and v.get("outcome") == "pass", "verdict={0}\n{1}".format(v, out[-800:]))
    action = open(os.path.join(shared, "..", "wing-commander-contained-gate-suite", "action.yml"),
                  encoding="utf-8").read()
    script = open(os.path.join(shared, "contained-gate-suite.sh"), encoding="utf-8").read()
    ck("the composite passes its suite-timeout-minutes input to the script under the name "
       "the script reads",
       "WC_GATE_SUITE_TIMEOUT_MINUTES: ${{ inputs.suite-timeout-minutes }}" in action
       and '"${WC_GATE_SUITE_TIMEOUT_MINUTES:-50}"' in script,
       "action.yml or contained-gate-suite.sh no longer carries WC_GATE_SUITE_TIMEOUT_MINUTES")
    return failures


def mutated_shared(tmp, edits):
    """A copy of _shared/ (and a .github/scripts beside it, which the gate
    script reads its verdict writer from) with (script, old, new) edits."""
    root = os.path.join(tmp, "m", ".github")
    shared = os.path.join(root, "actions", "_shared")
    os.makedirs(shared)
    os.symlink(os.path.abspath(HERE), os.path.join(root, "scripts"))
    for name in SCRIPTS:
        shutil.copy(os.path.join(SHARED, name), os.path.join(shared, name))
    composite = os.path.join(root, "actions", "wing-commander-contained-gate-suite")
    os.makedirs(composite)
    shutil.copy(os.path.join(SHARED, "..", "wing-commander-contained-gate-suite", "action.yml"),
                composite)
    for name, old, new in edits:
        path = os.path.join(shared, name)
        text = open(path, encoding="utf-8").read()
        if old not in text:
            sys.exit("::error::Gate 155 self-test: {0!r} not in {1}; update the "
                     "mutation with the script.".format(old, name))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))
    return shared


MUTATIONS = (
    ("both consumers fetch the bundle with a refs/* refspec",
     [("gate-bundle-import.sh", '"+HEAD:refs/wc-gate/head"', '"+refs/*:refs/wc-gate/*"')]),
    ("the restore stops checking that the bundle holds the reported head",
     [("restore-gate-bundle.sh", 'if [ "$fetched" != "$expected" ]; then', "if false; then")]),
    ("the gate job gates whatever meta.json names",
     [("contained-gate-suite.sh", 'if [ "$fetched" != "$head_sha" ]; then', "if false; then")]),
    ("a head that predates the suite is reported as having removed it",
     [("contained-gate-suite.sh", '! git cat-file -e "${fork}:.github/scripts/run-local-gates.py"',
       "false")]),
    ("the verdict writer's copy is left writable",
     [("contained-gate-suite.sh", 'chmod -R a-w "$trusted_copy"', "true")]),
    ("a bundle that fails verification is refused without saying why",
     [("restore-gate-bundle.sh", "this checkout does not hold. The containment could not be "
       "established; nothing is pushed.\"", "\"")]),
    ("an unknown base is bundled as a thin range anyway",
     [("build-gate-bundle.sh", 'if [ -n "$base_sha" ] && ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then',
       'if false; then')]),
    ("a head with no new commits ships the whole history",
     [("build-gate-bundle.sh", 'git bundle create --quiet "$out_dir/bundle.git" HEAD~1..HEAD HEAD',
       'git bundle create --quiet "$out_dir/bundle.git" HEAD')]),
)

# Mutations of the budget path, which budget_checks() alone must catch.
BUDGET_MUTATIONS = (
    ("the suite runs with no time budget",
     [("contained-gate-suite.sh", 'bound=(timeout -k 60 "$suite_seconds")', "bound=()")]),
    ("a stopped suite is reported as an ordinary failure",
     [("contained-gate-suite.sh", 'elif [ "${#bound[@]}" -gt 0 ] && [ "$elapsed" -ge "$suite_seconds" ]',
       'elif false && [ "$elapsed" -ge "$suite_seconds" ]')]),
    ("the budget is passed to timeout as a GNU-only long option",
     [("contained-gate-suite.sh", 'bound=(timeout -k 60 "$suite_seconds")',
       'bound=(timeout --kill-after=60 "$suite_seconds")')]),
    ("any timeout on PATH is trusted to accept -k",
     [("contained-gate-suite.sh", 'timeout -k 1 5 true >/dev/null 2>&1 && bound=',
       'command -v timeout >/dev/null 2>&1 && bound=')]),
    ("a stopped suite's verdict drops the failure it logged before the stop",
     [("contained-gate-suite.sh", '${first:+; first failure before the stop: $first}', "")]),
    ("a stopped suite's buffered output is lost",
     [("contained-gate-suite.sh", 'python3 -u .github/scripts/run-local-gates.py)',
       'python3 .github/scripts/run-local-gates.py)')]),
    ("BusyBox's 143 is read as an ordinary failure",
     [("contained-gate-suite.sh", '|| [ "$rc" -eq 143 ]; }', '; }')]),
    ("an unbounded suite runs silently",
     [("contained-gate-suite.sh", '[ "${#bound[@]}" -gt 0 ] || echo "::warning::', '[ "${#bound[@]}" -gt 0 ] || true "')]),
    ("a leading-zero budget is read as octal",
     [("contained-gate-suite.sh", 'suite_minutes=$((10#$suite_minutes))',
       'suite_minutes=$((suite_minutes))')]),
)


def main():
    failures = checks(os.path.abspath(SHARED)) + budget_checks(os.path.abspath(SHARED))
    if "--self-test" in sys.argv[1:]:
        if failures:
            failures = ["the shipped scripts already fail: " + f for f in failures]
        for label, edits in MUTATIONS + BUDGET_MUTATIONS:
            with tempfile.TemporaryDirectory() as tmp:
                shared = mutated_shared(tmp, edits)
                caught = (budget_checks(shared) if (label, edits) in BUDGET_MUTATIONS
                          else checks(shared))
            if caught:
                print("note: mutation caught ({0}): {1}".format(label, caught[0][:160]))
            else:
                failures.append("mutation {0!r} was NOT caught".format(label))
        if len(BUDGET_RUNS) != 1 + len(BUDGET_MUTATIONS):
            failures.append("the slow budget round trips ran {0} times, not once plus once per "
                            "budget-path mutation ({1})".format(len(BUDGET_RUNS),
                                                                1 + len(BUDGET_MUTATIONS)))
    for f in failures:
        print("::error::Gate 155: " + f)
    if failures:
        return 1
    print("Gate 155{0}: a workspace bundle round-trips from the agent's job through the "
          "gate job to the publisher.".format(" self-test" if "--self-test" in sys.argv[1:]
                                              else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
