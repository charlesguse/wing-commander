#!/usr/bin/env python3
"""Gate 91 -- auto-release.yml's pass-path specs/ reads classify a 404 as a
missing spec (pipeline defect), never as infrastructure (#482, #396 item 3).

WHY THIS EXISTS
---------------
#469 (for #396 item 3) made every pass-path read in the `poll` step's
"Poll the test repository to a verdict" run-block fail infra-closed on a
`gh api` error, via one shared `fail_infra_on_read` helper. `gh api` also
exits non-zero on a plain 404, and a 404 on `repos/<E2E_REPO>/contents/specs`
is exactly what the E2E target returns when the pipeline never created
`specs/` at all -- a genuine wrong-output outcome (a pipeline defect), not an
infrastructure one. Before #469 the empty `slug` fell through to
`missing_file="specs/<slug>/"`, which reported `fail-wrong-output`; #469
made it report `fail-infra` instead, blaming infrastructure for a pipeline
defect.

The per-file existence probe a few lines below already makes this
distinction (`grep -q 'HTTP 404'` on the captured stderr keeps a 404 on the
old missing-file path, any other failure goes through `fail_infra_on_read`).
#482 applies the same check to the slug fallback, reusing the idiom rather
than adding a second helper (see the file/probe pattern already duplicated,
by design, at wing-commander-resolve-checkout-ref's own branch probe).

#469's own behavioural coverage (502/403 -> fail-infra, 404/empty -> the old
missing-file path) existed only in a local scratch harness, per the issue,
so nothing in the checked-in suite would have caught this regression. This
harness closes that gap by EXECUTING the real "Poll the test repository to a
verdict" step (read out of auto-release.yml at run time, so there is no
second copy to drift) against a stubbed `gh` that fast-forwards it past the
polling loop (an immediately CLOSED/stage:done issue, an empty open-PR list
so `slug` stays unresolved) straight into the two reads under test: the slug
fallback and, with an already-resolved slug, the per-file existence probe.

Ends with a MUTATION that restores the pre-#482 slug-fallback text (no 404
distinction) and asserts the 404 scenario then fails, proving this harness
can see the regression it exists to catch.

Usage: python3 .github/scripts/verify-auto-release-specs-fallback.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
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
BASH = None

E2E_REPO = "charlesguse/test-repo"
ISSUE = "42"
HEAD = "a" * 40
REAL_SLUG = "055-real-feature"

BASE = {
    "GH_TOKEN": "dummy-gh-token",
    "HARNESS_TOKEN": "dummy-harness-token",
    "HARNESS_LOGIN": "machine-acct",
    "E2E_REPO": E2E_REPO,
    "DEFAULT_BRANCH": "main",
    "ISSUE": ISSUE,
    "ISSUE_URL": f"https://github.com/{E2E_REPO}/issues/{ISSUE}",
    "HEAD_SHA": HEAD,
    "POLL_BUDGET_SECONDS": "8100",
    "MAX_CLARIFICATION_ROUNDS": "3",
    "MODE": "default-runner",
    # Consumed by the stub gh below, not by the step itself.
    "STUB_SLUG_MODE": "ok",
    "STUB_SLUG_VALUE": REAL_SLUG,
    "STUB_SLUG_ERROR": "gh: Internal Server Error (HTTP 500)",
    "STUB_FILE_MODE": "ok",
    "STUB_FILE_ERROR": "gh: Internal Server Error (HTTP 500)",
}

STAGE_LABELS = ["stage:spec", "stage:plan", "stage:tasks", "stage:implement", "stage:review"]

# Fast-forwards the real "poll" step straight past the loop (an issue that
# is already CLOSED with stage:done on the very first check, and an empty
# open-PR list so `slug` is never resolved there -- the exact "pass path
# reached before the loop ever bound slug" case the fallback comment
# describes) and into the two reads this gate exists for. Any call this
# stub does not recognise fails loudly instead of no-op'ing, so an
# unstubbed read this harness has not accounted for is a hard error here,
# not a silently-green pass.
STUB_GH = r'''#!/usr/bin/env bash
case "$*" in
  "api repos/"*"/issues/"*" --jq .user.id")
    printf '1\n'
    exit 0
    ;;
  "api repos/"*"/issues/"*"/comments --paginate --jq"*)
    exit 0
    ;;
  "pr list --repo "*" --state open --json headRefName,title")
    printf '[]\n'
    exit 0
    ;;
  "issue view "*" --repo "*" --json state,labels")
    printf '%s\n' '{"state":"CLOSED","labels":[{"name":"stage:done"}]}'
    exit 0
    ;;
  "api repos/"*"/issues/"*"/timeline --paginate --jq"*)
    for s in STAGE_LABELS_PLACEHOLDER; do printf '%s\n' "$s"; done
    exit 0
    ;;
  "api repos/"*"/contents/specs --jq"*)
    case "$STUB_SLUG_MODE" in
      404) echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
      error) printf '%s\n' "$STUB_SLUG_ERROR" >&2; exit 1 ;;
      *) printf '%s\n' "$STUB_SLUG_VALUE"; exit 0 ;;
    esac
    ;;
  "api repos/"*"/contents/specs/"*)
    case "$STUB_FILE_MODE" in
      404) echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
      error) printf '%s\n' "$STUB_FILE_ERROR" >&2; exit 1 ;;
      *) exit 0 ;;
    esac
    ;;
  *)
    echo "unexpected gh invocation: $*" >&2
    exit 1
    ;;
esac
'''.replace("STAGE_LABELS_PLACEHOLDER", " ".join(STAGE_LABELS))

SHARED_SCRIPTS = [
    "auto-release-verdict.sh",
    "auto-release-e2e-clarify-decision.sh",
    "auto-release-e2e-merge-decision.sh",
]


def verdict_of(outputs):
    raw = outputs.get("verdict")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return "NOT-JSON"


# name, env overrides, expected outcome, substrings expected in
# "failing_check | expected | observed", substrings that must NOT appear.
SCENARIOS = [
    ("slug fallback 404s (specs/ never created): the old missing-spec path, "
     "not fail-infra",
     {"STUB_SLUG_MODE": "404"}, "fail-wrong-output",
     ["specs/<slug>/ present in the default branch"], ["fail-infra"]),
    ("slug fallback fails for another reason (rate limit/5xx): fail-infra, "
     "never read as a missing spec",
     {"STUB_SLUG_MODE": "error",
      "STUB_SLUG_ERROR": "gh: Internal Server Error (HTTP 500)"},
     "fail-infra",
     ["reading the E2E repository's specs/ directory to resolve the "
      "pass-path slug", "HTTP 500"], ["fail-wrong-output"]),
    ("per-file probe 404s after a resolved slug: unchanged missing-spec path",
     {"STUB_SLUG_MODE": "ok", "STUB_FILE_MODE": "404"}, "fail-wrong-output",
     [f"specs/{REAL_SLUG}/spec.md present in the default branch"],
     ["fail-infra"]),
    ("per-file probe fails for another reason after a resolved slug: "
     "unchanged fail-infra path",
     {"STUB_SLUG_MODE": "ok", "STUB_FILE_MODE": "error",
      "STUB_FILE_ERROR": "gh: Internal Server Error (HTTP 500)"},
     "fail-infra",
     [f"reading specs/{REAL_SLUG}/spec.md to confirm it exists after "
      "stage:done", "HTTP 500"], ["fail-wrong-output"]),
]


def run_scenario(script, overrides, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    shared_dir = os.path.join(workdir, ".github", "actions", "_shared")
    os.makedirs(shared_dir, exist_ok=True)
    for name in SHARED_SCRIPTS:
        shutil.copyfile(os.path.join(".github", "actions", "_shared", name),
                        os.path.join(shared_dir, name))
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
    return rc, out, outputs


def suite(script, tmproot):
    failures = []
    for name, overrides, want_outcome, want_in, want_not_in in SCENARIOS:
        rc, out, outputs = run_scenario(script, overrides, tmproot)
        if rc != 0:
            failures.append(f"{name}: the step exited {rc}, expected 0: {out}")
            continue
        verdict = verdict_of(outputs)
        if verdict in (None, "NOT-JSON"):
            failures.append(f"{name}: expected a JSON verdict, got {verdict!r} "
                            f"(outputs={outputs!r})")
            continue
        if verdict.get("outcome") != want_outcome:
            failures.append(f"{name}: outcome={verdict.get('outcome')!r}, "
                            f"expected {want_outcome!r} (verdict={verdict})")
            continue
        text = (f"{verdict.get('failing_check', '')} | "
                f"{verdict.get('expected', '')} | {verdict.get('observed', '')}")
        for want in want_in:
            if want not in text:
                failures.append(f"{name}: verdict text {text!r} lacks {want!r}")
        for unwanted in want_not_in:
            if unwanted in text:
                failures.append(f"{name}: verdict text {text!r} unexpectedly "
                                f"contains {unwanted!r}")
    return failures


# The pre-#482 slug-fallback text: every `gh api` failure on
# repos/<repo>/contents/specs went straight to fail_infra_on_read, with no
# 404 distinction -- the exact regression #482 fixes.
OLD_SLUG_FALLBACK = (
    'if [ -z "$slug" ]; then\n'
    '  if ! slug="$(gh api "repos/${E2E_REPO}/contents/specs" '
    '--jq \'[.[] | select(.type=="dir")][0].name // empty\' '
    '2>"$RUNNER_TEMP/auto-release-slug-err.txt")"; then\n'
    '    fail_infra_on_read "reading the E2E repository\'s specs/ '
    'directory to resolve the pass-path slug" \\\n'
    '      "gh api repos/contents/specs succeeds" '
    '"$RUNNER_TEMP/auto-release-slug-err.txt"\n'
    '  fi\n'
    'fi'
)

NEW_SLUG_FALLBACK = (
    'if [ -z "$slug" ]; then\n'
    '  if ! slug="$(gh api "repos/${E2E_REPO}/contents/specs" '
    '--jq \'[.[] | select(.type=="dir")][0].name // empty\' '
    '2>"$RUNNER_TEMP/auto-release-slug-err.txt")"; then\n'
    '    if ! grep -q \'HTTP 404\' '
    '"$RUNNER_TEMP/auto-release-slug-err.txt"; then\n'
    '      fail_infra_on_read "reading the E2E repository\'s specs/ '
    'directory to resolve the pass-path slug" \\\n'
    '        "gh api repos/contents/specs succeeds" '
    '"$RUNNER_TEMP/auto-release-slug-err.txt"\n'
    '    fi\n'
    '  fi\n'
    'fi'
)


def mut_no_404_distinction(script):
    """#482's regression, put back: every slug-fallback failure -- 404
    included -- reports fail-infra, never the missing-spec path."""
    if script.count(NEW_SLUG_FALLBACK) != 1:
        sys.exit("::error::verify-auto-release-specs-fallback: expected "
                 "exactly one occurrence of the #482 slug-fallback text in "
                 f"{WORKFLOW}, found {script.count(NEW_SLUG_FALLBACK)} -- "
                 "the step text may have changed shape; update this "
                 "harness alongside it.")
    return script.replace(NEW_SLUG_FALLBACK, OLD_SLUG_FALLBACK, 1)


MUTATIONS = [
    ("the slug fallback's 404 distinction removed (#482's own regression)",
     mut_no_404_distinction),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {WORKFLOW} not found.")
    step = find_step(WORKFLOW, STEP)
    if step is None:
        sys.exit(f"::error file={WORKFLOW}::step {STEP!r} not found.")
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
                print(f"::error::mutation {label!r} changed nothing -- the "
                      f"code it edits was rewritten. Update the mutation so "
                      f"this gate keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(mutated, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - {label} broke nothing in "
                      f"this suite, so the suite is not testing that defect. "
                      f"Fix the scenarios, not the mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"Gate 91: {len(SCENARIOS)} scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
