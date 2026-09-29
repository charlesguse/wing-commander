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
regression it exists for. It makes no network call.
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

BASE = {
    "GH_TOKEN": "app-token",
    "HARNESS_TOKEN": "harness-token",
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


def _sq(text):
    return "'" + text.replace("'", "'\\''") + "'"


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
            lines.append(f"      printf '%s' {_sq(stderr)} 1>&2")
        lines.append(f"      exit {rc}")
        lines.append("      ;;")
    lines.append("  esac")
    lines.append("fi")
    lines.append('if [ "$1" = "issue" ] && [ "$2" = "view" ]; then exit 0; fi')
    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def verdict_of(outputs):
    raw = outputs.get("verdict")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return "NOT-JSON"


def run_scenario(script, slug_behaviors, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    for name in SHARED_SCRIPTS:
        dst = os.path.join(workdir, SHARED, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(os.path.join(SHARED, name), dst)
    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(gh_stub_script(slug_behaviors))
    os.chmod(gh_path, 0o755)
    sleep_path = os.path.join(bindir, "sleep")
    with open(sleep_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SLEEP_STUB)
    os.chmod(sleep_path, 0o755)
    call_count_file = os.path.join(workdir, "slug_call_count")
    env = dict(BASE)
    env["STUB_SLUG_CALL_COUNT"] = call_count_file
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
     ["the harness credential was rejected", "Bad credentials"]),
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
     ["the harness credential was rejected",
      "Resource not accessible by personal access token"]),
]


def suite(script, tmproot):
    failures = []
    for name, behaviors, want_outcome, want_failing_check, want_in_text in SCENARIOS:
        rc, out, outputs = run_scenario(script, behaviors, tmproot)
        if rc != 0:
            failures.append(f"{name}: the step exited {rc}, expected 0: {out.strip()}")
            continue
        verdict = verdict_of(outputs)
        if verdict in (None, "NOT-JSON"):
            failures.append(f"{name}: expected a JSON verdict, got {verdict!r}")
            continue
        if verdict.get("outcome") != want_outcome:
            failures.append(f"{name}: outcome={verdict.get('outcome')!r}, "
                            f"expected {want_outcome!r}")
        if verdict.get("failing_check") != want_failing_check:
            failures.append(f"{name}: failing_check={verdict.get('failing_check')!r}, "
                            f"expected {want_failing_check!r}")
        text = f"{verdict.get('expected', '')} | {verdict.get('observed', '')}"
        for want in want_in_text:
            if want not in text:
                failures.append(f"{name}: verdict {text!r} lacks {want!r}")
    return failures


def mut_drop_credential_branch(script):
    """Revert FR-011's new branch: a credential-rejection signature no
    longer matches, so the check falls through to the fail-gate-stall
    `else` arm regardless of what `$3` says."""
    old = ("grep -qiE 'HTTP 401|Bad credentials|Resource not accessible by "
           "integration|Resource not accessible by personal access "
           "token|requires authentication|insufficient .*scope|"
           "missing .*scope'")
    new = "grep -qiE 'this-signature-can-never-match-anything-xyz'"
    if old not in script:
        return script
    return script.replace(old, new, 1)


MUTATIONS = [
    ("FR-011's credential-signature branch dropped from write_repeated_failure_verdict",
     mut_drop_credential_branch),
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

    print(f"Gate 115: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
