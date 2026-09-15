#!/usr/bin/env bash
# Behavioral test for watchdog.yml's "Collect: final PR claims" step
# (id: collect-final-pr-claims) — specs/046-watchdog-supervision-collectors,
# contracts/gate-coverage-046.md's verify-final-pr-claims-collector.sh row.
#
# specs/046-watchdog-supervision-collectors leg-2/leg-3: this used to feed
# hand-typed copies of extract_claim() and NARRATIVE_DRIFT_FILTER fixture
# inputs, so mutation testing found it stayed green through a shipped break
# (blanking the tasks_claim="$(extract_claim ...)" line) that a copy-based
# harness can never see, because it never calls extract_claim() the way the
# step itself does (constitution VIII). This EXECUTES the shipped step
# (wc_shell_harness.find_step/run_step) with `gh` stubbed to canned
# responses, so every line the step actually runs — including the ground-
# truth extraction leg-0 fixed (#274 fold leg-0) — is exercised for real.
#
# Usage: .github/scripts/verify-final-pr-claims-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-final-pr-claims-collector: jq and python3 are both required."
  exit 1
fi

python3 - <<'PY'
import base64
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, ".github/scripts")
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

use_utf8_stdout()
ensure_jq()
BASH = resolve_bash()
WATCHDOG = ".github/workflows/watchdog.yml"
STEP = "Collect: final PR claims"

step = find_step(WATCHDOG, STEP)
SCRIPT = step["run"]
if "${{" in SCRIPT:
    sys.exit(f"::error file={WATCHDOG}::verify-final-pr-claims-collector could "
             f"not resolve every ${{{{ }}}} expression in {STEP!r}.")

GITHUB_REPOSITORY = "charlesguse/wing-commander"


def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"

# A `gh` stand-in dispatching on the shipped step's own four call shapes
# (pr list, pr view, api compare, api contents) and returning canned,
# already-`--jq`-filtered text/JSON the way the real CLI would — the
# boundary this harness stubs is gh's own HTTP/--jq mechanics, not this
# feature's code, which is exactly what still runs for real below it.
STUB_GH = r'''#!/usr/bin/env bash
set -u
d=__FIXTURE_DIR__
case "$1" in
  pr)
    case "$2" in
      list)
        [ -f "$d/fail-list" ] && exit 1
        cat "$d/pr-list.txt"
        ;;
      view)
        [ -f "$d/fail-view" ] && exit 1
        cat "$d/pr-view.json"
        ;;
      *) echo "unexpected gh pr subcommand: $2" >&2; exit 1 ;;
    esac
    ;;
  api)
    p=""
    for arg in "$@"; do
      case "$arg" in repos/*) p="$arg" ;; esac
    done
    case "$p" in
      */compare/*)
        [ -f "$d/fail-compare" ] && exit 1
        cat "$d/compare.json"
        ;;
      */contents/*)
        [ -f "$d/fail-contents" ] && exit 1
        cat "$d/contents.b64"
        ;;
      *) echo "unexpected gh api path: $p" >&2; exit 1 ;;
    esac
    ;;
  *) echo "unexpected gh subcommand: $1" >&2; exit 1 ;;
esac
'''


def run_case(*, run_name="Wing Commander · 6 finalize", run_conclusion="success",
             slug="046-watchdog-supervision-collectors",
             spec_dir="specs/046-watchdog-supervision-collectors",
             pr_number=301, fail_list=False, fail_view=False, fail_compare=False,
             fail_contents=False, body="", base_sha="basesha", head_sha="headsha",
             total_commits=0, added=(), tasks_md=""):
    workdir = tempfile.mkdtemp()
    runner_temp = tempfile.mkdtemp()
    bindir = tempfile.mkdtemp()
    fixture_dir = tempfile.mkdtemp()
    try:
        with open(os.path.join(fixture_dir, "pr-list.txt"), "w", encoding="utf-8") as fh:
            fh.write(str(pr_number) if pr_number is not None else "")
        if fail_list:
            open(os.path.join(fixture_dir, "fail-list"), "w").close()
        with open(os.path.join(fixture_dir, "pr-view.json"), "w", encoding="utf-8") as fh:
            json.dump({"body": body, "baseRefName": "main", "headRefName": f"spec/{slug}",
                       "baseRefOid": base_sha, "headRefOid": head_sha}, fh)
        if fail_view:
            open(os.path.join(fixture_dir, "fail-view"), "w").close()
        with open(os.path.join(fixture_dir, "compare.json"), "w", encoding="utf-8") as fh:
            json.dump({"total_commits": total_commits, "added": list(added)}, fh)
        if fail_compare:
            open(os.path.join(fixture_dir, "fail-compare"), "w").close()
        with open(os.path.join(fixture_dir, "contents.b64"), "w", encoding="utf-8") as fh:
            fh.write(base64.b64encode(tasks_md.encode("utf-8")).decode("ascii"))
        if fail_contents:
            open(os.path.join(fixture_dir, "fail-contents"), "w").close()

        gh_path = os.path.join(bindir, "gh")
        with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(STUB_GH.replace("__FIXTURE_DIR__", shell_quote(fixture_dir)))
        os.chmod(gh_path, 0o755)

        with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
            fh.write("[]")
        with open(os.path.join(runner_temp, "collector-outcomes.json"), "w", encoding="utf-8") as fh:
            fh.write("[]")

        env = {
            "GITHUB_REPOSITORY": GITHUB_REPOSITORY,
            "GH_TOKEN": "dummy-token",
            "RUN_NAME": run_name,
            "RUN_CONCLUSION": run_conclusion,
            "SLUG": slug,
            "SPEC_DIR": spec_dir,
            "SPEC_PREFIX": "spec/",
            "PATH": bindir + os.pathsep + os.environ["PATH"],
        }
        rc, out, outputs, summary = run_step(BASH, SCRIPT, workdir, env, runner_temp)
        with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
            signals = json.load(fh)
        with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
            outcomes = json.load(fh)
        return rc, out, signals, outcomes, summary
    finally:
        for d in (workdir, runner_temp, bindir, fixture_dir):
            shutil.rmtree(d, ignore_errors=True)


failures = []


def check(tag, cond, detail):
    if not cond:
        failures.append(f"[{tag}] {detail}")
        print(f"::error::verify-final-pr-claims-collector: [{tag}] {detail}")
    else:
        print(f"::notice::verify-final-pr-claims-collector: [{tag}] ok")


def drift_signals(signals, claim_type=None):
    out = [s for s in signals if s.get("class-hint") == "narrative-drift"]
    if claim_type is not None:
        out = [s for s in out if s.get("facts", {}).get("claim-type") == claim_type]
    return out


# ── Positive: task-count mismatch (claimed 42, actual 41 checked boxes).
rc, out, signals, outcomes, _ = run_case(
    body="This PR completes 42 tasks across three phases.",
    tasks_md="\n".join(f"- [x] task {i}" for i in range(41)) + "\n- [ ] one more\n",
    total_commits=10, added=[])
check("task mismatch", rc == 0 and len(drift_signals(signals, "tasks")) == 1,
      f"expected exactly one tasks narrative-drift signal, got rc={rc} signals={signals} out={out}")

# ── Positive: commit-count mismatch (claimed 10, actual 12).
rc, out, signals, outcomes, _ = run_case(
    body="10 commits landed for this feature.", total_commits=12)
check("commit mismatch", rc == 0 and len(drift_signals(signals, "commits")) == 1,
      f"expected exactly one commits narrative-drift signal, got rc={rc} signals={signals} out={out}")

# ── Positive: test-count (fixture-file-count) mismatch (claimed 5, actual 3).
rc, out, signals, outcomes, _ = run_case(
    body="Added 5 test cases for this change.",
    added=["specs/x/fixtures/a.json", "specs/x/fixtures/b.json", "specs/x/fixtures/c.json"])
check("test mismatch", rc == 0 and len(drift_signals(signals, "tests")) == 1,
      f"expected exactly one tests narrative-drift signal, got rc={rc} signals={signals} out={out}")

# ── Negative: unparseable claim shape (no isolable number) → no signal.
rc, out, signals, outcomes, _ = run_case(
    body="A great deal of work went into the tasks for this spec.",
    tasks_md="- [x] done\n", total_commits=5)
check("unparseable claim", rc == 0 and drift_signals(signals) == [],
      f"prose with no isolable number must produce no signal, got rc={rc} signals={signals} out={out}")

# ── Negative: every claim matches ground truth → no signal.
rc, out, signals, outcomes, _ = run_case(
    body="This PR completes 1 tasks, 1 commits, 1 tests.",
    tasks_md="- [x] only\n", total_commits=1, added=["specs/x/fixtures/a.json"])
check("matching claims", rc == 0 and drift_signals(signals) == [],
      f"claims matching ground truth must produce no signal, got rc={rc} signals={signals} out={out}")

# ── Negative: non-finalize run → scope guard exits before any signal or
#    collector-outcomes write.
rc, out, signals, outcomes, _ = run_case(
    run_name="Wing Commander · 3 plan",
    body="This PR completes 42 tasks.", tasks_md="- [x] a\n", total_commits=1)
check("non-finalize scope guard", rc == 0 and signals == [] and outcomes == [],
      f"a non-finalize run must skip before writing signals or collector-outcomes, got rc={rc} "
      f"signals={signals} outcomes={outcomes} out={out}")

# ── Negative: no PR resolvable for the branch → outcome 'ok', no signal.
rc, out, signals, outcomes, _ = run_case(pr_number=None)
check("no PR resolvable", rc == 0 and signals == []
      and outcomes == [{"collector": "collect-final-pr-claims", "outcome": "ok"}],
      f"no resolvable PR must record outcome 'ok' with no signal, got rc={rc} signals={signals} "
      f"outcomes={outcomes} out={out}")

# ── Negative: `gh pr view` itself fails → outcome 'failed', no signal, and
#    (FR-010/leg-0) collector-outcomes is still WRITTEN, not lost.
rc, out, signals, outcomes, _ = run_case(fail_view=True)
check("pr view read failure", rc == 0 and signals == []
      and outcomes == [{"collector": "collect-final-pr-claims", "outcome": "failed"}],
      f"a failed gh pr view must record outcome 'failed' without losing the collector-outcomes "
      f"record, got rc={rc} signals={signals} outcomes={outcomes} out={out}")

# ── Regression (leg-0, #274 fold leg-0): tasks.md with ZERO checked boxes.
#    Before the fix, `grep -c ... || echo 0` under pipefail left tasks_actual
#    holding two lines ('0\n0'), which made the `jq -n --argjson tasks_actual`
#    call fail and the whole step die before ever appending to
#    collector-outcomes.json. This must now complete cleanly and compare the
#    claim against a genuine 0.
rc, out, signals, outcomes, _ = run_case(
    body="This PR completes 5 tasks.",
    tasks_md="- [ ] not yet\n- [ ] also not yet\n", total_commits=0)
check("leg-0 zero checked boxes does not crash the step",
      rc == 0 and outcomes == [{"collector": "collect-final-pr-claims", "outcome": "ok"}],
      f"a tasks.md with zero checked boxes must not abort the step before recording its "
      f"collector-outcomes entry, got rc={rc} outcomes={outcomes} out={out}")
tasks_mismatch = drift_signals(signals, "tasks")
check("leg-0 zero checked boxes still compares against the real actual value",
      len(tasks_mismatch) == 1 and tasks_mismatch[0]["facts"]["actual-value"] == 0,
      f"claiming 5 tasks against a genuine 0 checked boxes must produce one tasks "
      f"narrative-drift signal with actual-value 0, got {signals}")

# ── Boundary (leg-3, #274 fold leg-3): an EMPTY PR body. Every claim
#    extraction must come back null, so no signal fires even though the
#    ground truth (5 checked boxes, 3 commits) differs from "nothing claimed."
rc, out, signals, outcomes, _ = run_case(
    body="", tasks_md="- [x] a\n- [x] b\n- [x] c\n- [x] d\n- [x] e\n", total_commits=3)
check("leg-3 empty PR body", rc == 0 and drift_signals(signals) == [],
      f"an empty PR body must parse no claims and produce no signal regardless of the actual "
      f"values, got rc={rc} signals={signals} out={out}")

if failures:
    print(f"❌ verify-final-pr-claims-collector: {len(failures)} assertion(s) failed:")
    for f in failures:
        print(f"- {f}")
    sys.exit(1)

print("✅ verify-final-pr-claims-collector: all assertions passed.")
PY
