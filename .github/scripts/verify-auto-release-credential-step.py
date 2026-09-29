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

specs/066-fine-grained-maintainer-token extended the step with a second
accepted credential shape (classic and fine-grained, detected from the
token's own literal prefix -- see docs/setup.md for the canonical statement
of what each shape must carry); this gate's scenarios and mutations were
extended alongside it to cover every row of that feature's data-model.md
Credential precheck outcome table, not only the shapes specs/055 shipped.

This gate runs the REAL step, extracted from the workflow, with a stubbed `gh`
(a bindir prepended to PATH), and asserts on what it publishes:

  * the documented outcomes -- exactly the test repository passes; an extra
    repository, an empty set, a different login, no write access, an unset
    token or username, a malformed token prefix, a fine-grained credential
    missing a needed permission or carrying Administration, an expired
    fine-grained credential, and a `gh api` call that fails outright (as
    opposed to succeeding with an empty result) each end `ok=false` with a
    fail-infra verdict distinguishable from every other one;
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
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = os.path.join(".github", "workflows", "auto-release.yml")
STEP = "Confirm the fixture maintainer identity's credential"
LOGIN = "machine-acct"
HEAD = "a" * 40
BASH = None


def _rfc(delta_days):
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).strftime(
        "%Y-%m-%d %H:%M:%S UTC")


# Answers the calls the step makes, from the environment:
#   gh repo view <repo> --json viewerPermission --jq ...        classic-only -> $STUB_PERMISSION
#   gh api user --jq .login                                     classic-only -> $STUB_LOGIN
#   gh api -i user                                               fine-grained login+expiry read:
#     empty $STUB_LOGIN -> exit 1 (transport failure / rejected token)
#     else prints a 200 status line, an optional expiration header from
#     $STUB_EXPIRY, and a JSON body carrying $STUB_LOGIN
#   gh api -i -X POST .../issues/999999999/comments             D6 Issues probe -> $STUB_ISSUES_STATUS
#     ($STUB_ISSUES_TRANSPORT_FAIL=1 -> exit 1, no output)
#   gh api -i -X PUT .../pulls/999999999/merge                  D6 Contents (merge) probe -> $STUB_PRS_STATUS
#     ($STUB_PRS_TRANSPORT_FAIL=1 -> exit 1, no output)
#   gh api -i .../actions/permissions                            D5 Administration probe -> $STUB_ADMIN_STATUS
#     ($STUB_ADMIN_TRANSPORT_FAIL=1 -> exit 1, no output)
#   gh api user/repos?... --paginate --jq .full_name             containment (both shapes) -> $STUB_REPOS
#     ($STUB_REPOS_TRANSPORT_FAIL=1 -> exit 1, no output -- research.md D4)
STUB_GH = r'''#!/usr/bin/env bash
if [ "$1" = "repo" ] && [ "$2" = "view" ]; then
  printf '%s\n' "${STUB_PERMISSION-}"
  exit 0
fi
if [ "$1" = "api" ] && [ "$2" = "user" ] && [ "$3" = "--jq" ]; then
  printf '%s\n' "${STUB_LOGIN-}"
  exit 0
fi
if [ "$1" = "api" ] && [ "$2" = "-i" ] && [ "$3" = "user" ]; then
  if [ -z "${STUB_LOGIN-}" ]; then
    exit 1
  fi
  printf 'HTTP/2.0 200 OK\r\n'
  if [ -n "${STUB_EXPIRY-}" ]; then
    printf 'github-authentication-token-expiration: %s\r\n' "${STUB_EXPIRY}"
  fi
  printf '\r\n{"login":"%s"}\n' "${STUB_LOGIN}"
  exit 0
fi
if [ "$1" = "api" ] && [ "$2" = "-i" ] && [ "$3" = "-X" ] && [ "$4" = "POST" ]; then
  if [ "${STUB_ISSUES_TRANSPORT_FAIL-0}" = "1" ]; then exit 1; fi
  printf 'HTTP/2.0 %s Status\r\n\r\n' "${STUB_ISSUES_STATUS:-404}"
  exit 0
fi
if [ "$1" = "api" ] && [ "$2" = "-i" ] && [ "$3" = "-X" ] && [ "$4" = "PUT" ]; then
  if [ "${STUB_PRS_TRANSPORT_FAIL-0}" = "1" ]; then exit 1; fi
  printf 'HTTP/2.0 %s Status\r\n\r\n' "${STUB_PRS_STATUS:-404}"
  exit 0
fi
if [ "$1" = "api" ] && [ "$2" = "-i" ]; then
  case "$3" in
    */actions/permissions)
      if [ "${STUB_ADMIN_TRANSPORT_FAIL-0}" = "1" ]; then exit 1; fi
      printf 'HTTP/2.0 %s Status\r\n\r\n' "${STUB_ADMIN_STATUS:-403}"
      exit 0
      ;;
  esac
fi
if [ "$1" = "api" ]; then
  case "$2" in
    user/repos*)
      if [ "${STUB_REPOS_TRANSPORT_FAIL-0}" = "1" ]; then exit 1; fi
      if [ -n "${STUB_REPOS-}" ]; then printf '%s' "$STUB_REPOS" | tr ';' '\n'; printf '\n'; fi
      exit 0
      ;;
  esac
fi
exit 0
'''

BASE = {
    "MAINTAINER_TOKEN": "ghp_dummytoken",
    "MAINTAINER_USERNAME": LOGIN,
    "MAINTAINER_TOKEN_EXPIRY_WARNING_DAYS": "14",
    "E2E_REPO": "charlesguse/test-repo",
    "HEAD_SHA": HEAD,
    "MODE": "default-runner",
    "STUB_PERMISSION": "WRITE",
    "STUB_LOGIN": LOGIN,
    "STUB_REPOS": "charlesguse/test-repo",
}

# Fine-grained scenarios start from BASE plus this shape switch; the stub's
# defaults for the D5/D6 probes (403/403) already match "every permission
# this shape needs is granted, Administration is not", so a fine-grained
# scenario need only override the fields it means to test.
FG = {"MAINTAINER_TOKEN": "github_pat_dummytoken"}


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
    ("a token without write access", {"STUB_PERMISSION": "READ"}, "false",
     ["viewerPermission was 'READ'"]),
    ("gh returns no login for the token", {"STUB_LOGIN": ""}, "false",
     ["gh rejected the token"], ["viewerPermission"]),
    # Each "unset" branch must be the one that fires: without asserting which
    # secret the verdict names, deleting a guard would fall through to the
    # "different login" branch, which is also ok=false, and this gate would
    # stay green. The username guard is also what keeps the redaction's
    # pattern from ever being empty.
    ("the token secret unset", {"MAINTAINER_TOKEN": ""}, "false",
     ["MAINTAINER_TOKEN set to a classic or fine-grained PAT", "unset"]),
    ("the username secret unset", {"MAINTAINER_USERNAME": ""}, "false",
     ["MAINTAINER_USERNAME set to that account's login", "unset"]),
    ("the username secret stored with a trailing newline",
     {"MAINTAINER_USERNAME": LOGIN + "\n",
      "STUB_REPOS": f"charlesguse/test-repo;{LOGIN}/notes"}, "false",
     ["<maintainer account>/notes"]),

    # specs/066-fine-grained-maintainer-token: research.md D1 -- a token
    # matching neither accepted prefix, ahead of every other check, for
    # either shape's own value shape.
    ("a malformed credential matching neither accepted prefix",
     {"MAINTAINER_TOKEN": "not-a-real-token"}, "false",
     ["matches neither accepted shape"]),

    # data-model.md row #2 (fine-grained variants): a probe transport-fails
    # outright rather than returning a permission-denied response.
    ("fine-grained: the login/expiry probe fails outright",
     {**FG, "STUB_LOGIN": ""}, "false", ["gh rejected the token"]),
    ("fine-grained: the Issues/Contents probe fails outright",
     {**FG, "STUB_ISSUES_TRANSPORT_FAIL": "1"}, "false",
     ["a permission probe call failed outright"]),
    ("fine-grained: the Administration probe fails outright",
     {**FG, "STUB_ADMIN_TRANSPORT_FAIL": "1"}, "false",
     ["a permission probe call failed outright"]),
    ("fine-grained: an already-expired credential",
     {**FG, "STUB_EXPIRY": _rfc(-1)}, "false",
     ["the credential expired at"]),

    # data-model.md row #4 (fine-grained variant): D6 rejects Issues and/or
    # Contents write. The merge probe is gated by GitHub on Contents:write,
    # not Pull-requests:write (maintainer feedback on #506).
    ("fine-grained: Issues write rejected",
     {**FG, "STUB_ISSUES_STATUS": "403"}, "false",
     ["Issues and Contents write, per research.md D6",
      "issues: 403"]),
    ("fine-grained: Contents write rejected (merge probe)",
     {**FG, "STUB_PRS_STATUS": "403"}, "false",
     ["Issues and Contents write, per research.md D6",
      "contents: 403"]),

    # data-model.md row #5: D5 accepts (200) -- the credential itself grants
    # Administration, never produced for the classic shape (FR-003).
    ("fine-grained: the credential grants Administration permission",
     {**FG, "STUB_ADMIN_STATUS": "200"}, "false",
     ["no Administration permission on the test repository",
      "the credential grants Administration permission"]),

    # A correctly scoped fine-grained credential passes exactly like a
    # classic one -- same containment mechanism, different shape.
    ("fine-grained: exactly the test repository passes", FG, "true", None),

    # data-model.md rows #6/#7 under the fine-grained shape (User Story 3):
    # over-scoped fails naming the extra repository; a `gh api` call that
    # itself fails is distinguishable from a call that succeeds empty.
    ("fine-grained: an extra repository owned by someone else",
     {**FG, "STUB_REPOS": "charlesguse/test-repo;other-owner/thing"}, "false",
     ["other-owner/thing", "reached 2 repositories"]),
    ("fine-grained: the containment call itself fails outright",
     {**FG, "STUB_REPOS_TRANSPORT_FAIL": "1"}, "false",
     ["the credential's reachable-repository set can be observed",
      "the gh api call to list reachable repositories failed"],
     ["reached 0 repositories"]),
    ("classic: the containment call itself fails outright",
     {"STUB_REPOS_TRANSPORT_FAIL": "1"}, "false",
     ["the credential's reachable-repository set can be observed",
      "the gh api call to list reachable repositories failed"],
     ["reached 0 repositories"]),
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
    for name, overrides, want_ok, want_in_verdict, *rest in SCENARIOS:
        want_not_in_verdict = rest[0] if rest else []
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
                # Both fields: `expected` names which secret or check the
                # branch is about, `observed` says what was found.
                text = f"{verdict.get('expected', '')} | {verdict.get('observed', '')}"
                for want in want_in_verdict or []:
                    if want not in text:
                        failures.append(f"{name}: verdict {text!r} lacks {want!r}")
                for unwanted in want_not_in_verdict:
                    if unwanted in text:
                        failures.append(f"{name}: verdict {text!r} unexpectedly "
                                        f"contains {unwanted!r}")
        # The invariant this gate exists for: the secret's value reaches no
        # output, whatever the scenario and whatever its letter case.
        secret = (env.get("MAINTAINER_USERNAME") or "").strip()
        if secret and secret.lower() in json.dumps(outputs, sort_keys=True).lower():
            failures.append(f"{name}: the masked login {secret!r} appears in a step "
                            f"output -- GitHub would drop that output")
    return failures


# specs/066-fine-grained-maintainer-token T014: the approaching-expiry note
# is report-only text on a pass, never a verdict field -- checked separately
# from suite() above, which only inspects `ok` and `verdict`.
EXPIRY_NOTE_SCENARIOS = [
    ("fine-grained: expiry within the warning window notes it on a pass",
     {**FG, "STUB_EXPIRY": _rfc(5)}, True),
    ("fine-grained: expiry well outside the warning window notes nothing",
     {**FG, "STUB_EXPIRY": _rfc(365)}, False),
    ("classic: no expiration header, nothing to note",
     {"STUB_EXPIRY": ""}, False),
]


def check_expiry_notes(script, tmproot):
    failures = []
    for name, overrides, want_note in EXPIRY_NOTE_SCENARIOS:
        _env, rc, _out, outputs = run_scenario(script, name, overrides, tmproot)
        if rc != 0:
            failures.append(f"{name}: the step exited {rc}, expected 0")
            continue
        if outputs.get("ok") != "true":
            failures.append(f"{name}: ok={outputs.get('ok')!r}, expected 'true'")
            continue
        has_note = bool(outputs.get("expiry-warning"))
        if has_note != want_note:
            failures.append(f"{name}: expiry-warning output present={has_note}, "
                            f"expected {want_note}")
    return failures


def mut_raw_repository_names(script):
    """The old text: the reached names quoted verbatim, login included."""
    old = "'gsub($login; \"<maintainer account>\"; \"i\")'"
    new = "'.'"
    return script.replace(old, new)


def mut_no_username_guard(script):
    """The username-unset guard deleted: an empty username would fall through
    to the different-login branch (also ok=false), and the redaction could
    receive an empty pattern."""
    return script.replace('if [ -z "$MAINTAINER_USERNAME" ]; then', "if false; then")


def mut_no_whitespace_trim(script):
    """The one-time whitespace strip of the username removed."""
    old = 'MAINTAINER_USERNAME="$(printf \'%s\' "$MAINTAINER_USERNAME" | tr -d \'[:space:]\')"'
    return script.replace(old, ":")


def mut_malformed_prefix_accepted(script):
    """research.md D1: a token matching neither accepted prefix silently
    treated as classic, instead of ending fail-infra."""
    old = "github_pat_*) shape=fine-grained ;;\n"
    new = old + "  *) shape=classic ;;\n"
    return script.replace(old, new)


def mut_d6_rejection_accepted(script):
    """research.md D6: a 403 (permission absent) on either write probe no
    longer fails the precheck."""
    old = 'if [ "$issues_status" = "403" ] || [ "$contents_status" = "403" ]; then'
    new = 'if [ "$issues_status" = "999" ] || [ "$contents_status" = "999" ]; then'
    return script.replace(old, new)


def mut_d5_grant_accepted(script):
    """research.md D5: a 200 (Administration granted) on the
    actions/permissions probe no longer fails the precheck."""
    old = 'if [ "$admin_status" = "200" ]; then'
    new = 'if [ "$admin_status" = "999" ]; then'
    return script.replace(old, new)


def mut_expiry_check_dropped(script):
    """research.md D2: an already-expired fine-grained credential no longer
    ends the attempt."""
    old = 'if [ "$expiry_epoch" -le "$now_epoch" ]; then'
    new = "if false; then"
    return script.replace(old, new)


def mut_containment_exit_status_swallowed(script):
    """research.md D4 reverted: the `gh api` call's own exit status folded
    back into the same `2>/dev/null` swallow into `sort -u`, so a call that
    fails outright is indistinguishable from one that succeeds empty."""
    old_start = 'if ! reachable_raw="$(GH_TOKEN="$MAINTAINER_TOKEN" gh api "user/repos?affiliation=owner,collaborator,organization_member" --paginate --jq \'.full_name\' 2>/dev/null)"; then'
    old_end = 'reachable_repos="$(printf \'%s\' "$reachable_raw" | sort -u)"'
    start = script.find(old_start)
    end = script.find(old_end)
    if start == -1 or end == -1:
        return script
    end += len(old_end)
    new = ('reachable_repos="$(GH_TOKEN="$MAINTAINER_TOKEN" gh api '
           '"user/repos?affiliation=owner,collaborator,organization_member" '
           '--paginate --jq \'.full_name\' 2>/dev/null | sort -u)"')
    return script[:start] + new + script[end:]


MUTATIONS = [
    ("the reached repository names quoted verbatim (login not redacted)",
     mut_raw_repository_names),
    ("the username-unset guard deleted", mut_no_username_guard),
    ("the username's whitespace no longer stripped", mut_no_whitespace_trim),
    ("a malformed credential prefix silently accepted as classic",
     mut_malformed_prefix_accepted),
    ("a D6 write-permission rejection (403) no longer fails the precheck",
     mut_d6_rejection_accepted),
    ("a D5 Administration grant (200) no longer fails the precheck",
     mut_d5_grant_accepted),
    ("the expiry check dropped -- an expired credential no longer fails",
     mut_expiry_check_dropped),
    ("research.md D4 reverted: a gh api failure folded back into 'reached 0 repositories'",
     mut_containment_exit_status_swallowed),
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
        failures += check_expiry_notes(script, tmproot)
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
            broke = suite(mutated, tmproot) + check_expiry_notes(mutated, tmproot)
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
