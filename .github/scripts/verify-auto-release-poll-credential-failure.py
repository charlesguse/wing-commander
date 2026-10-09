#!/usr/bin/env python3
"""Gate 115 -- a gate-driving act that keeps failing because the harness
credential itself was rejected ends fail-infra naming the credential, not an
undifferentiated fail-gate-stall.

specs/066-fine-grained-maintainer-token FR-011 (Edge Case "Expiry during a
long attempt"): a credential that is valid at the precheck (Gate 67) can
still expire, be revoked, or be scoped narrower mid-attempt. Before this
feature, every repeated gate-driving read/write failure in the `poll` step's
`write_repeated_failure_verdict` helper -- other than the pre-existing
rate-limit special case -- collapsed into `fail-gate-stall`, which `report`
files as a pipeline defect (specs/055 SC-010/FR-021) rather than the
infrastructure condition it actually is.

This gate runs the REAL "Poll the test repository to a verdict" step,
extracted from the workflow (via `find_step`, never a copy), with a stubbed
`gh` and a no-op `sleep`, and drives its `spec-draft PR merge` gate's read
(`gh pr list --state open`, used to locate this attempt's slug) to fail
repeatedly:

  * a repeated HTTP 401/"Bad credentials"/etc. failure ends `fail-infra`,
    naming the credential as cause -- including a fine-grained personal
    access token's own "Resource not accessible by personal access token"
    text, distinct from a GitHub App token's "...by integration" (maintainer
    feedback on #506);
  * a repeated failure carrying none of those signatures still ends
    `fail-gate-stall`, unchanged from before this feature (regression
    coverage: the new branch must not swallow every gate stall);
  * a repeated rate-limit failure still routes through the pre-existing
    rate-limit branch, naming the poll read rather than the credential
    (ordering coverage: the two `elif` arms must not shadow each other).

A mutation removes the new credential-signature branch and must make the
first scenario fall back to `fail-gate-stall`, proving this gate can see the
regression it exists for.

#979: the step's reads used to run under the scoped App installation token
(`steps.token`), which expires 60 minutes after it is minted, while the poll
budget is 135 minutes. A container-mode run crossed the hour, every
issue/comments read came back "Bad credentials (HTTP 401)", and the
credential arm above blamed the harness credential for it. Every scenario
now runs the step under the credentials its OWN `env:` mapping binds
(each `${{ }}` expression mapped to a named stand-in, never a hard-coded
choice), and two more scenarios use a stub that 401s a stand-in after a
few calls:

  * the App-token stand-in expires (the hour mark, compressed): the poll
    outlives it and reaches the issue's terminal state, never ending on a
    credential verdict;
  * the App-token stand-in never expires and the maintainer stand-in is
    revoked instead: the clarification reads are rejected, so the 401 the
    poll ends on is the maintainer secret's, the credential the verdict
    names. The verdict text names that secret as a fixed string, so only
    WHICH gate fails proves the reads ran under it -- under the App token
    they would keep succeeding and the attempt would end elsewhere.

A second mutation binds the step's GH_TOKEN back to `steps.token`, and each
mutation lists the scenarios that must break under it (`must_break`), so
"must fail both" is enforced rather than satisfied by any one failing
assertion. It makes no network call.
"""
import json
import os
import re
import shlex
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WORKFLOW = os.path.join(".github", "workflows", "auto-release.yml")
STEP = "Poll the test repository to a verdict"
SHARED = os.path.join(".github", "actions", "_shared")
SHARED_SCRIPTS = [
    "auto-release-verdict.sh",
    "auto-release-e2e-clarify-decision.sh",
    "auto-release-e2e-merge-decision.sh",
]

ISSUE = "42"
E2E_REPO = "charlesguse/test-repo"
HEAD = "a" * 40

BASH = None

# Stand-ins for the credential expressions the step's own `env:` may bind
# GH_TOKEN/HARNESS_TOKEN to (resolve_token_env below), so a step that reads
# under the App token runs here under "app-token" and the expiry stub
# rejects it the way GitHub does once the hour is up.
APP_TOKEN = "app-token"
HARNESS_TOKEN = "harness-token"
HARNESS_SECRET = "WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN"
APP_TOKEN_EXPR = "steps.token.outputs.token"
HARNESS_TOKEN_EXPR = f"secrets.{HARNESS_SECRET}"
TOKEN_STANDINS = {
    APP_TOKEN_EXPR: APP_TOKEN,
    HARNESS_TOKEN_EXPR: HARNESS_TOKEN,
}
# The App-token stand-in answers this many calls, then 401s every call after.
APP_TOKEN_LIFETIME_CALLS = 2
# The issue reaches a terminal label on this `gh issue view` call, several
# poll iterations in. The stub counts only views that pass its token check,
# so a poll whose view runs under an expired or revoked credential never
# reaches the terminal label at all and ends on MAX_GATE_FAILURES (3)
# rejected clarification reads instead; the value only has to leave the
# poll enough iterations to make more than APP_TOKEN_LIFETIME_CALLS reads.
TERMINAL_AT_VIEW = 6

BASE = {
    "HARNESS_LOGIN": "machine-acct",
    "E2E_REPO": E2E_REPO,
    "DEFAULT_BRANCH": "main",
    "ISSUE": ISSUE,
    "ISSUE_URL": f"https://github.com/{E2E_REPO}/issues/{ISSUE}",
    "HEAD_SHA": HEAD,
    "POLL_BUDGET_SECONDS": "8100",
    "MAX_CLARIFICATION_ROUNDS": "3",
    "MODE": "default-runner",
}

SLEEP_STUB = "#!/usr/bin/env bash\nexit 0\n"


def resolve_token_env(step_env):
    """{GH_TOKEN, HARNESS_TOKEN} -> stand-in, read from the step's `env:`."""
    out = {}
    for var in ("GH_TOKEN", "HARNESS_TOKEN"):
        raw = str((step_env or {}).get(var, "")).strip()
        m = re.fullmatch(r"\$\{\{\s*(.+?)\s*\}\}", raw)
        if not m or m.group(1) not in TOKEN_STANDINS:
            sys.exit(f"::error file={WORKFLOW}::step {STEP!r} binds {var} to "
                     f"{raw!r}, which this harness has no stand-in for. Add one "
                     f"to TOKEN_STANDINS rather than dropping the check.")
        out[var] = TOKEN_STANDINS[m.group(1)]
    return out


def gh_stub_script(slug_behaviors):
    """A `gh` stub answering exactly the calls this step makes before it
    ever finds a slug: the clarification gate's author-id and comments
    reads (always succeed, no marker comment -> `decide` returns "none"),
    and the spec-draft slug lookup (`gh pr list --state open`, no --head),
    whose behavior is driven call-by-call from `slug_behaviors` -- a list
    of (rc, stderr) tuples, 1-indexed by call to that read; a call beyond
    the list repeats the last entry (same convention as
    verify-lifecycle-gate-retry.py's gh_stub_script).

    The slug never resolves in any scenario here (the lookup always
    fails), so the PR-merge gates' own `--head`-scoped `gh pr list` and
    the bottom-of-loop `gh issue view` are never reached for a real
    assertion; both are stubbed to a harmless empty success so a scenario
    that has not yet hit its failure bound can still complete the
    iteration and loop back around.
    """
    lines = [
        "#!/usr/bin/env bash",
        'if [ "$1" = "api" ]; then',
        '  case "$2" in',
        "    */comments) exit 0 ;;",
        "    */issues/*) printf '999\\n'; exit 0 ;;",
        "  esac",
        "fi",
        'if [ "$1" = "pr" ] && [ "$2" = "list" ]; then',
        '  for a in "$@"; do',
        '    if [ "$a" = "--head" ]; then exit 0; fi',
        "  done",
        '  n=$(cat "$STUB_SLUG_CALL_COUNT" 2>/dev/null || echo 0)',
        "  n=$((n + 1))",
        '  echo "$n" > "$STUB_SLUG_CALL_COUNT"',
        '  case "$n" in',
    ]
    for i, (rc, stderr) in enumerate(slug_behaviors, start=1):
        label = str(i) if i < len(slug_behaviors) else "*"
        lines.append(f"    {label})")
        if stderr:
            lines.append(f"      printf '%s' {shlex.quote(stderr)} 1>&2")
        lines.append(f"      exit {rc}")
        lines.append("      ;;")
    lines.append("  esac")
    lines.append("fi")
    lines.append('if [ "$1" = "issue" ] && [ "$2" = "view" ]; then exit 0; fi')
    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def expiry_stub_script(app_expires_after, harness_expires_after=None):
    """A `gh` stub for a poll that outlives the App token: a call made
    under the App-token stand-in counts toward `app_expires_after` (None:
    never expires) and 401s once past it, the way an installation token does
    at the hour mark.
    Calls under the harness stand-in never expire unless
    `harness_expires_after` is given, in which case they 401 past that many
    calls too (the harness credential revoked mid-attempt). Every read
    otherwise succeeds empty (no comments, no PRs), and `gh issue view`
    reports the issue in flight until its TERMINAL_AT_VIEW-th call, which
    reports stage:stalled -- a terminal state the poll reaches only if its
    reads kept working."""
    app_limit = "" if app_expires_after is None else str(app_expires_after)
    harness_limit = "" if harness_expires_after is None else str(harness_expires_after)
    return "\n".join([
        "#!/usr/bin/env bash",
        "reject() {",
        "  n=$(cat \"$1\" 2>/dev/null || echo 0)",
        "  n=$((n + 1))",
        "  echo \"$n\" > \"$1\"",
        "  if [ -n \"$2\" ] && [ \"$n\" -gt \"$2\" ]; then",
        "    printf 'gh: Bad credentials (HTTP 401)\\n' 1>&2",
        "    exit 1",
        "  fi",
        "}",
        f'if [ "$GH_TOKEN" = "{APP_TOKEN}" ]; then',
        f'  reject "$STUB_APP_CALLS" "{app_limit}"',
        f'elif [ "$GH_TOKEN" = "{HARNESS_TOKEN}" ]; then',
        f'  reject "$STUB_HARNESS_CALLS" "{harness_limit}"',
        "else",
        "  printf 'stub: unknown token\\n' 1>&2",
        "  exit 1",
        "fi",
        'if [ "$1" = "api" ]; then',
        '  case "$2" in',
        "    */comments|*/timeline) exit 0 ;;",
        "    */issues/*) printf '999\\n'; exit 0 ;;",
        "  esac",
        "  exit 0",
        "fi",
        "if [ \"$1\" = \"pr\" ] && [ \"$2\" = \"list\" ]; then printf '[]\\n'; exit 0; fi",
        'if [ "$1" = "issue" ] && [ "$2" = "view" ]; then',
        '  v=$(cat "$STUB_VIEW_CALLS" 2>/dev/null || echo 0)',
        "  v=$((v + 1))",
        '  echo "$v" > "$STUB_VIEW_CALLS"',
        f'  if [ "$v" -ge {TERMINAL_AT_VIEW} ]; then',
        "    printf '{\"state\":\"OPEN\",\"labels\":[{\"name\":\"stage:stalled\"}]}\\n'",
        "  else",
        "    printf '{\"state\":\"OPEN\",\"labels\":[{\"name\":\"stage:clarify\"}]}\\n'",
        "  fi",
        "  exit 0",
        "fi",
        "exit 0",
    ]) + "\n"


def verdict_of(outputs):
    raw = outputs.get("verdict")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return "NOT-JSON"


def run_with_stub(script, token_env, stub_text, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    for name in SHARED_SCRIPTS:
        dst = os.path.join(workdir, SHARED, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(SHARED, name), dst)
    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(stub_text)
    os.chmod(gh_path, 0o755)
    sleep_path = os.path.join(bindir, "sleep")
    with open(sleep_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SLEEP_STUB)
    os.chmod(sleep_path, 0o755)
    env = dict(BASE)
    env.update(token_env)
    for var, fname in (("STUB_SLUG_CALL_COUNT", "slug_call_count"),
                       ("STUB_APP_CALLS", "app_calls"),
                       ("STUB_HARNESS_CALLS", "harness_calls"),
                       ("STUB_VIEW_CALLS", "view_calls")):
        env[var] = os.path.join(workdir, fname)
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    try:
        rc, out, outputs, _summary = run_step(BASH, script, workdir, env, runner_temp)
    finally:
        for d in (workdir, runner_temp, bindir):
            shutil.rmtree(d, ignore_errors=True)
    return rc, out, outputs


# name, slug_behaviors, expected outcome, expected failing_check, expected
# substrings in the joined expected|observed verdict text.
SCENARIOS = [
    ("a repeated credential rejection (HTTP 401) names the credential",
     [(1, "HTTP 401: Bad credentials")],
     "fail-infra", "spec-draft PR merge",
     ["the harness credential", HARNESS_SECRET, "was rejected", "Bad credentials"]),
    ("a repeated failure with no credential signature still gate-stalls",
     [(1, "HTTP 502: Bad Gateway (https://api.github.com/graphql)")],
     "fail-gate-stall", "spec-draft PR merge",
     ["HTTP 502"]),
    ("a repeated rate-limit failure still routes through the poll's own "
     "rate-limit branch, not the credential branch",
     [(1, "API rate limit exceeded for installation ID 12345678.")],
     "fail-infra", "polling the test repository for a terminal state",
     ["rate limit"]),
    # specs/066-fine-grained-maintainer-token maintainer feedback on #506:
    # a fine-grained personal access token's own 403 body text differs from
    # the GitHub App token's ("Resource not accessible by integration"),
    # so the regex must also catch the PAT's own wording.
    ("a repeated fine-grained-PAT rejection names the credential",
     [(1, "HTTP 403: Resource not accessible by personal access token")],
     "fail-infra", "spec-draft PR merge",
     ["the harness credential", HARNESS_SECRET, "was rejected",
      "Resource not accessible by personal access token"]),
]

# #979: name, app_expires_after, harness_expires_after, expected outcome,
# expected failing_check, substrings the verdict text must carry, substrings
# it must NOT carry.
EXPIRY_OUTLIVES_APP_TOKEN = (
    "the poll outlives the App token's 60-minute lifetime and reaches the "
    "issue's terminal state (#979)")
EXPIRY_NAMES_REJECTED_CREDENTIAL = (
    "a 401 the poll ends on comes from the maintainer secret it names, "
    "rejected at the clarification gate's reads (#979)")
EXPIRY_SCENARIOS = [
    (EXPIRY_OUTLIVES_APP_TOKEN,
     APP_TOKEN_LIFETIME_CALLS, None,
     "fail-incomplete", "end-to-end run reaching stage:done",
     ["stage:stalled"], ["credential", "HTTP 401"]),
    # The App-token stand-in never expires here: if the clarification reads
    # ran under it they would keep succeeding, and the revoked maintainer
    # credential would surface only at the spec-draft PR list (or not at
    # all before the terminal view) -- never as a "clarification" verdict.
    (EXPIRY_NAMES_REJECTED_CREDENTIAL,
     None, 4,
     "fail-infra", "clarification",
     [HARNESS_SECRET, "was rejected", "Bad credentials"], []),
]


def check_verdict(name, rc, out, outputs, want_outcome, want_failing_check,
                  want_in_text, want_not_in_text=()):
    if rc != 0:
        return [f"{name}: the step exited {rc}, expected 0: {out.strip()}"]
    verdict = verdict_of(outputs)
    if verdict in (None, "NOT-JSON"):
        return [f"{name}: expected a JSON verdict, got {verdict!r}"]
    failures = []
    if verdict.get("outcome") != want_outcome:
        failures.append(f"{name}: outcome={verdict.get('outcome')!r}, "
                        f"expected {want_outcome!r} (verdict: {verdict!r})")
    if verdict.get("failing_check") != want_failing_check:
        failures.append(f"{name}: failing_check={verdict.get('failing_check')!r}, "
                        f"expected {want_failing_check!r}")
    text = f"{verdict.get('expected', '')} | {verdict.get('observed', '')}"
    for want in want_in_text:
        if want not in text:
            failures.append(f"{name}: verdict {text!r} lacks {want!r}")
    for unwanted in want_not_in_text:
        if unwanted in text:
            failures.append(f"{name}: verdict {text!r} carries {unwanted!r}")
    return failures


def suite(script, step_env, tmproot):
    token_env = resolve_token_env(step_env)
    failures = []
    for name, behaviors, want_outcome, want_failing_check, want_in_text in SCENARIOS:
        rc, out, outputs = run_with_stub(script, token_env,
                                         gh_stub_script(behaviors), tmproot)
        failures += check_verdict(name, rc, out, outputs, want_outcome,
                                  want_failing_check, want_in_text)
    for (name, app_after, harness_after, want_outcome, want_failing_check,
         want_in_text, want_not_in_text) in EXPIRY_SCENARIOS:
        rc, out, outputs = run_with_stub(script, token_env,
                                         expiry_stub_script(app_after, harness_after),
                                         tmproot)
        failures += check_verdict(name, rc, out, outputs, want_outcome,
                                  want_failing_check, want_in_text,
                                  want_not_in_text)
    return failures


def mut_drop_credential_branch(script, step_env):
    """Revert FR-011's new branch: a credential-rejection signature no
    longer matches, so the check falls through to the fail-gate-stall
    `else` arm regardless of what `$3` says."""
    old = ("grep -qiE 'HTTP 401|Bad credentials|Resource not accessible by "
           "integration|Resource not accessible by personal access "
           "token|requires authentication|insufficient .*scope|"
           "missing .*scope'")
    new = "grep -qiE 'this-signature-can-never-match-anything-xyz'"
    if old not in script:
        return script, step_env
    return script.replace(old, new, 1), step_env


def mut_reads_under_app_token(script, step_env):
    """Revert #979's fix: the step's own GH_TOKEN -- what every read not
    prefixed with GH_TOKEN="$HARNESS_TOKEN" runs under -- is the scoped App
    installation token again."""
    env = dict(step_env or {})
    env["GH_TOKEN"] = "${{ " + APP_TOKEN_EXPR + " }}"
    return script, env


# label, mutation, scenario names each of which must fail under it (empty:
# any one failing assertion is enough). Every scenario that expects the
# credential arm's verdict must break when that arm is dropped.
MUTATIONS = [
    ("FR-011's credential-signature branch dropped from write_repeated_failure_verdict",
     mut_drop_credential_branch,
     (SCENARIOS[0][0], SCENARIOS[3][0], EXPIRY_NAMES_REJECTED_CREDENTIAL)),
    ("the poll step's reads run under the App installation token again (#979)",
     mut_reads_under_app_token,
     (EXPIRY_OUTLIVES_APP_TOKEN, EXPIRY_NAMES_REJECTED_CREDENTIAL)),
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
    step_env = dict(step.get("env") or {})
    if "${{" in script:
        sys.exit(f"::error file={WORKFLOW}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")

    tmproot = tempfile.mkdtemp()
    failures = []
    try:
        failures = suite(script, step_env, tmproot)
        for f in failures:
            print(f"::error::{f}")
        for label, mutate, must_break in MUTATIONS:
            m_script, m_env = mutate(script, step_env)
            if m_script == script and m_env == step_env:
                print(f"::error::mutation {label!r} changed nothing -- the code it "
                      f"edits was rewritten. Update the mutation so this gate keeps "
                      f"proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(m_script, m_env, tmproot)
            unbroken = [n for n in must_break
                        if not any(b.startswith(f"{n}:") for b in broke)]
            if unbroken:
                for n in unbroken:
                    print(f"::error::MUTATION SURVIVED IN PART - {label} left the "
                          f"scenario {n!r} passing, so that scenario does not see "
                          f"this defect. Fix the scenario, not the mutation.")
                failures.append(f"mutation survived in part: {label}")
            elif broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - {label} broke nothing in this "
                      f"suite, so the suite is not testing that defect. Fix the "
                      f"scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    total = len(SCENARIOS) + len(EXPIRY_SCENARIOS)
    print(f"Gate 115: {total} scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
