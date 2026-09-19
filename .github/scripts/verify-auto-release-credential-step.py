#!/usr/bin/env python3
"""Gate 67 -- auto-release's maintainer-credential step never lets the masked
login reach a step output, and every documented failure ends fail-infra.

`auto-release.yml`'s "Confirm the fixture maintainer identity's credential"
step reads the machine account's login from a SECRET
(WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_USERNAME). GitHub Actions masks a
secret's value and drops any step output that contains it, so a verdict that
quotes the login is silently replaced downstream by a generic "verdict not a
JSON object" -- in the containment case, exactly when the verdict was meant to
name the extra repositories the account can reach. That happened once already
(the `reached: [<login>/...]` text, #396), and the review that should have
caught it recorded the fix as "verified by inspection".

This gate runs the REAL step, extracted from the workflow, with a stubbed `gh`
(a bindir prepended to PATH), and asserts on what it publishes:

  * the documented outcomes -- exactly the test repository passes; an extra
    repository, an empty set, a different login, no write access, an unset
    token or username each end `ok=false` with a fail-infra verdict;
  * the invariant: whatever the scenario, the login value appears NOWHERE in
    the step's outputs, in any letter case.

A mutation restores the old raw-name text and must make the login-bearing
scenarios fail, so the gate proves it can see the defect it exists for. It
fails loudly if it cannot find its subject step. It reads the workflow and the
shared verdict helper only; it makes no network call.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = os.path.join(".github", "workflows", "auto-release.yml")
STEP = "Confirm the fixture maintainer identity's credential"
LOGIN = "machine-acct"
HEAD = "a" * 40
BASH = None

# Answers the three gh calls the step makes, from the environment:
#   gh repo view <repo> --json viewerPermission --jq ...   -> $STUB_PERMISSION
#   gh api user --jq .login                                -> $STUB_LOGIN
#   gh api user/repos?... --paginate --jq .full_name       -> $STUB_REPOS
#     (';'-separated, one full name each)
STUB_GH = r'''#!/usr/bin/env bash
if [ "$1" = "repo" ] && [ "$2" = "view" ]; then
  printf '%s\n' "${STUB_PERMISSION-}"
elif [ "$1" = "api" ] && [ "$2" = "user" ]; then
  printf '%s\n' "${STUB_LOGIN-}"
elif [ "$1" = "api" ]; then
  case "$2" in
    user/repos*) if [ -n "${STUB_REPOS-}" ]; then printf '%s' "$STUB_REPOS" | tr ';' '\n'; printf '\n'; fi ;;
  esac
fi
exit 0
'''

BASE = {
    "MAINTAINER_TOKEN": "dummy-token",
    "MAINTAINER_USERNAME": LOGIN,
    "E2E_REPO": "charlesguse/test-repo",
    "HEAD_SHA": HEAD,
    "MODE": "default-runner",
    "STUB_PERMISSION": "WRITE",
    "STUB_LOGIN": LOGIN,
    "STUB_REPOS": "charlesguse/test-repo",
}


def verdict_of(outputs):
    raw = outputs.get("verdict")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return "NOT-JSON"


# name, env overrides, expected ok, expected substrings in verdict `observed`
# (None = no verdict expected), and a check on the whole verdict text.
SCENARIOS = [
    ("exactly the test repository passes", {}, "true", None),
    ("an extra repository owned by someone else",
     {"STUB_REPOS": "charlesguse/test-repo;other-owner/thing"}, "false",
     ["other-owner/thing", "reached 2 repositories"]),
    ("an extra repository owned by the machine account itself",
     {"STUB_REPOS": f"charlesguse/test-repo;{LOGIN}/notes"}, "false",
     ["<maintainer account>/notes", "reached 2 repositories"]),
    ("the same, with the login in another letter case",
     {"STUB_REPOS": "Machine-Acct/Notes;charlesguse/test-repo"}, "false",
     ["<maintainer account>/Notes", "reached 2 repositories"]),
    ("only a repository the account owns (the test repository unreachable)",
     {"STUB_REPOS": f"{LOGIN}/notes"}, "false",
     ["<maintainer account>/notes", "reached 1 repositories"]),
    ("an empty reachable set", {"STUB_REPOS": ""}, "false",
     ["reached 0 repositories"]),
    ("a token that authenticates as a different login",
     {"STUB_LOGIN": "someone-else"}, "false", ["authenticated as a different login"]),
    ("a token without write access", {"STUB_PERMISSION": "READ"}, "false", []),
    ("the token secret unset", {"MAINTAINER_TOKEN": ""}, "false", []),
    ("the username secret unset", {"MAINTAINER_USERNAME": ""}, "false", []),
]


def run_scenario(script, name, overrides, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    helper_dst = os.path.join(workdir, ".github", "actions", "_shared",
                              "auto-release-verdict.sh")
    os.makedirs(os.path.dirname(helper_dst), exist_ok=True)
    shutil.copyfile(os.path.join(".github", "actions", "_shared",
                                 "auto-release-verdict.sh"), helper_dst)
    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB_GH)
    os.chmod(gh_path, 0o755)
    env = dict(BASE)
    env.update(overrides)
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    try:
        rc, out, outputs, _summary = run_step(BASH, script, workdir, env, runner_temp)
    finally:
        for d in (workdir, runner_temp, bindir):
            shutil.rmtree(d, ignore_errors=True)
    return env, rc, out, outputs


def suite(script, tmproot):
    failures = []
    for name, overrides, want_ok, want_in_observed in SCENARIOS:
        env, rc, _out, outputs = run_scenario(script, name, overrides, tmproot)
        if rc != 0:
            failures.append(f"{name}: the step exited {rc}, expected 0 (every branch "
                            f"ends the step cleanly and reports through its outputs)")
            continue
        if outputs.get("ok") != want_ok:
            failures.append(f"{name}: ok={outputs.get('ok')!r}, expected {want_ok!r}")
            continue
        verdict = verdict_of(outputs)
        if want_ok == "true":
            if verdict is not None:
                failures.append(f"{name}: a passing check published a verdict: {verdict}")
        else:
            if verdict in (None, "NOT-JSON"):
                failures.append(f"{name}: expected a JSON fail-infra verdict, got {verdict!r}")
            else:
                if verdict.get("outcome") != "fail-infra":
                    failures.append(f"{name}: outcome={verdict.get('outcome')!r}, "
                                    f"expected 'fail-infra'")
                observed = str(verdict.get("observed", ""))
                for want in want_in_observed or []:
                    if want not in observed:
                        failures.append(f"{name}: observed {observed!r} lacks {want!r}")
        # The invariant this gate exists for: the secret's value reaches no
        # output, whatever the scenario and whatever its letter case.
        secret = env.get("MAINTAINER_USERNAME") or ""
        if secret and secret.lower() in json.dumps(outputs, sort_keys=True).lower():
            failures.append(f"{name}: the masked login {secret!r} appears in a step "
                            f"output -- GitHub would drop that output")
    return failures


def mut_raw_repository_names(script):
    """The old text: the reached names quoted verbatim, login included."""
    old = "'gsub($login; \"<maintainer account>\"; \"i\")'"
    new = "'.'"
    return script.replace(old, new)


MUTATIONS = [
    ("the reached repository names quoted verbatim (login not redacted)",
     mut_raw_repository_names),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {WORKFLOW} not found.")
    step = find_step(WORKFLOW, STEP)
    script = str(step["run"])
    if "${{" in script:
        sys.exit(f"::error file={WORKFLOW}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")

    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        failures = suite(script, tmproot)
        for f in failures:
            print(f"::error::{f}")
        for label, mutate in MUTATIONS:
            mutated = mutate(script)
            if mutated == script:
                print(f"::error::mutation {label!r} changed nothing -- the code it "
                      f"edits was rewritten. Update the mutation so this gate keeps "
                      f"proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(mutated, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - {label} broke nothing in this "
                      f"suite, so the suite is not testing that defect. Fix the "
                      f"scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"Gate 67: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
