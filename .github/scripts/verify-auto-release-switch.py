#!/usr/bin/env python3
"""auto-release-switch.yml sets or clears the auto-release kill switch and
reports what the variable now is; a bot account can pause but never resume.

WHY THIS EXISTS
---------------
WING_COMMANDER_AUTO_RELEASE_PAUSED stops every auto-release job. The switch
workflow is how a maintainer's session that can dispatch workflows, but
cannot write repository variables, pauses a failed auto-release again. It
must:

  - pause with `gh variable set ... --body true`, and resume by deleting
    the variable (unset is its documented resting state), an already-unset
    variable included;
  - let anyone who can dispatch it pause, but only the repository owner
    resume: resuming is never a runtime action the pipeline takes on
    itself (specs/055-unattended-e2e-gates FR-028). The actor is
    github.triggering_actor, so a bot re-running an owner's run is the bot;
  - fail, changing nothing, without its token, and on any other failed
    write;
  - read the variable back and fail unless it now holds what was asked.

This harness EXECUTES the shipped step through wc_shell_harness.run_step
against a `gh` stub that keeps the variable in a file and can fail any
call, the way the real CLI does. Each MUTATION reverts one rule and asserts
the suite then fails.

Usage: python3 .github/scripts/verify-auto-release-switch.py
Requires: bash.
"""
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

WORKFLOW = ".github/workflows/auto-release-switch.yml"
STEP = "Set the auto-release kill switch"
VAR = "WING_COMMANDER_AUTO_RELEASE_PAUSED"

# State is a file holding the variable's value; absent file = unset.
# STUB_FAIL names one verb (set/delete/get) to fail with a 403;
# STUB_SET_NOOP makes `set` report success without storing anything.
STUB_GH = r'''#!/usr/bin/env bash
printf '%s\n' "$*" >> "$STUB_LOG"
[ "$1" = "variable" ] || { echo "stub gh: unexpected call: $*" >&2; exit 97; }
verb="$2"
if [ "${STUB_FAIL:-}" = "$verb" ]; then
  echo "failed to $verb variable: HTTP 403: Resource not accessible by personal access token (https://api.github.com/...)" >&2
  exit 1
fi
case "$verb" in
  set)
    body=""
    while [ "$#" -gt 0 ]; do
      case "$1" in --body) body="$2"; shift ;; esac
      shift
    done
    [ -n "${STUB_SET_NOOP:-}" ] || printf '%s' "$body" > "$STUB_STATE"
    ;;
  delete)
    if [ ! -f "$STUB_STATE" ]; then
      echo "failed to delete variable $3: HTTP 404: Not Found (https://api.github.com/...)" >&2
      exit 1
    fi
    rm -f "$STUB_STATE"
    ;;
  get)
    if [ ! -f "$STUB_STATE" ]; then
      echo "variable $3 was not found" >&2
      exit 1
    fi
    cat "$STUB_STATE"; echo
    ;;
  *) echo "stub gh: unexpected verb: $verb" >&2; exit 97 ;;
esac
'''

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-auto-release-switch: {0} -- {1}".format(name, detail))


def run(script, paused, start=None, actor="charlesguse", token="t", fail="", set_noop=False,
        owner="charlesguse"):
    """-> (rc, output, summary, calls, end state or None for unset)."""
    tmp = tempfile.mkdtemp(prefix="wc-ar-switch-")
    try:
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        gh = os.path.join(bindir, "gh")
        open(gh, "w").write(STUB_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        state = os.path.join(tmp, "state")
        if start is not None:
            open(state, "w").write(start)
        log = os.path.join(tmp, "gh.log")
        open(log, "w").close()
        runner_temp = os.path.join(tmp, "runner-temp")
        os.makedirs(runner_temp)
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"],
               "GH_TOKEN": token, "PAUSED": paused, "ACTOR": actor, "OWNER": owner,
               "SWITCH_VAR": VAR, "GITHUB_REPOSITORY": "o/r",
               "STUB_STATE": state, "STUB_LOG": log, "STUB_FAIL": fail,
               "STUB_SET_NOOP": "1" if set_noop else ""}
        rc, output, _, summary = run_step(BASH, script, tmp, env, runner_temp)
        end = open(state).read() if os.path.exists(state) else None
        return rc, output, summary, open(log).read(), end
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def suite(script, quiet=False):
    failed = []

    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    rc, out, summary, calls, end = run(script, "true")
    ck("pausing sets the variable to true and reports it",
       rc == 0 and end == "true" and "variable set {0} --body true -R o/r".format(VAR) in calls
       and "auto-release is paused" in summary,
       "rc={0} end={1!r}\n{2}\n{3}".format(rc, end, calls, out))
    rc, out, summary, calls, end = run(script, "false", start="true")
    ck("resuming deletes the variable and reports it unset",
       rc == 0 and end is None and "variable delete {0} -R o/r".format(VAR) in calls
       and "auto-release is resumed" in summary,
       "rc={0} end={1!r}\n{2}\n{3}".format(rc, end, calls, out))
    rc, out, summary, calls, end = run(script, "false", start=None)
    ck("resuming an already-unset variable succeeds",
       rc == 0 and end is None and "auto-release is resumed" in summary,
       "rc={0} end={1!r}\n{2}".format(rc, end, out))
    rc, out, summary, calls, end = run(script, "false", start="true", actor="wing-commander-bot[bot]")
    ck("FR-028: a bot account cannot resume, and nothing is written",
       rc != 0 and end == "true" and calls.strip() == "" and "only the repository owner" in out,
       "rc={0} end={1!r}\n{2}\n{3}".format(rc, end, calls, out))
    rc, out, summary, calls, end = run(script, "false", start="true", actor="some-collaborator")
    ck("a person other than the owner cannot resume either",
       rc != 0 and end == "true" and calls.strip() == "",
       "rc={0} end={1!r}\n{2}\n{3}".format(rc, end, calls, out))
    rc, out, summary, calls, end = run(script, "false", start="true", actor="CharlesGuse")
    ck("the owner check ignores login case",
       rc == 0 and end is None, "rc={0} end={1!r}\n{2}".format(rc, end, out))
    rc, out, summary, calls, end = run(script, "true", start=None, actor="github-actions[bot]")
    ck("a bot account can still pause",
       rc == 0 and end == "true", "rc={0} end={1!r}\n{2}".format(rc, end, out))
    rc, out, summary, calls, end = run(script, "false", start="true", token="")
    ck("without its token it fails and calls nothing",
       rc != 0 and end == "true" and calls.strip() == ""
       and "WC_AUTO_RELEASE_SWITCH_TOKEN secret is not set" in out,
       "rc={0}\n{1}\n{2}".format(rc, calls, out))
    rc, out, summary, calls, end = run(script, "false", start="true", fail="delete")
    ck("a failed delete (not a 404) fails the run",
       rc != 0 and end == "true" and "could not delete" in out, "rc={0}\n{1}".format(rc, out))
    rc, out, summary, calls, end = run(script, "true", fail="get")
    ck("a failed read-back fails the run",
       rc != 0 and "could not read" in out, "rc={0}\n{1}".format(rc, out))
    rc, out, summary, calls, end = run(script, "true", set_noop=True)
    ck("a write that did not take fails the read-back check",
       rc != 0 and "reads '(unset)' after this run, not 'true'" in out, "rc={0}\n{1}".format(rc, out))
    rc, out, summary, calls, end = run(script, "maybe")
    ck("any other input fails and calls nothing",
       rc != 0 and calls.strip() == "", "rc={0}\n{1}".format(rc, out))
    return failed


MUTATIONS = (
    ("the owner check removed", 'if [ "${ACTOR,,}" != "${OWNER,,}" ]; then', 'if false; then'),
    ("the owner check made case-sensitive", 'if [ "${ACTOR,,}" != "${OWNER,,}" ]; then',
     'if [ "$ACTOR" != "$OWNER" ]; then'),
    ("any delete failure tolerated", '*"HTTP 404"*) ;;', '*) ;;'),
    ("the read-back comparison removed", 'if [ "$now" != "$want" ]; then', 'if false; then'),
    ("the empty-token check removed", 'if [ -z "$GH_TOKEN" ]; then', 'if false; then'),
)


def main():
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    step = find_step(WORKFLOW, STEP)
    script = step["run"]
    # The rule is only as good as the field it reads: github.actor would let
    # a bot re-running an owner's resume run through as the owner.
    env = step.get("env") or {}
    check("ACTOR is github.triggering_actor and OWNER is github.repository_owner",
          env.get("ACTOR") == "${{ github.triggering_actor }}"
          and env.get("OWNER") == "${{ github.repository_owner }}",
          "env is {0!r}".format(env))
    for name, old, _new in MUTATIONS:
        if script.count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches the step text "
                     "exactly once. Update the mutation with the step.".format(WORKFLOW, name))
    suite(script)
    for name, old, new in MUTATIONS:
        check("mutation caught: " + name, bool(suite(script.replace(old, new), quiet=True)),
              "the suite stayed green with this rule reverted")
    if failures:
        print("verify-auto-release-switch: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-auto-release-switch: ok")


if __name__ == "__main__":
    main()
