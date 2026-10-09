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
# The stub holds what GitHub returns and runs the step's own three `--jq`
# programs over it through real jq, and a mutation pass breaks each program
# in turn and expects the cases to fail (#889, the #766 class).
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
import shlex
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

# A `gh` stand-in dispatching on the shipped step's own four call shapes
# (pr list, pr view, api compare, api contents). Each fixture holds what
# gh itself receives -- `gh pr list --json number`'s array, the compare
# and contents REST objects -- and `out` reduces it with the caller's own
# `--jq` program through real jq, printing a string result raw, as gh
# does. Only gh's HTTP is stubbed; the step's jq programs run for real.
STUB_GH = r'''#!/usr/bin/env bash
set -u
d=__FIXTURE_DIR__
jq_prog=""
prev=""
for arg in "$@"; do
  case "$prev" in --jq|-q) jq_prog="$arg" ;; esac
  prev="$arg"
done
out() {
  if [ -n "$jq_prog" ]; then jq -rc "$jq_prog" "$1"; else cat "$1"; fi
}
case "$1" in
  pr)
    case "$2" in
      list)
        [ -f "$d/fail-list" ] && exit 1
        out "$d/pr-list.json"
        ;;
      view)
        [ -f "$d/fail-view" ] && exit 1
        out "$d/pr-view.json"
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
        out "$d/compare.json"
        ;;
      */contents/*)
        [ -f "$d/fail-contents" ] && exit 1
        out "$d/contents.json"
        ;;
      *) echo "unexpected gh api path: $p" >&2; exit 1 ;;
    esac
    ;;
  *) echo "unexpected gh subcommand: $1" >&2; exit 1 ;;
esac
'''


def tasks_contents(tasks_md):
    """The REST contents object for tasks.md: GitHub wraps its base64 at
    60 characters, so the step's `base64 -d` must take embedded newlines."""
    b64 = base64.b64encode(tasks_md.encode("utf-8")).decode("ascii")
    wrapped = "".join(b64[i:i + 60] + "\n" for i in range(0, len(b64), 60))
    return {"type": "file", "encoding": "base64", "path": "tasks.md", "content": wrapped}


def compare_body(total_commits, added):
    """The REST compare object. Files that were modified or removed sit
    beside the added ones, under */fixtures/* too, so only the step's own
    `select(.status=="added")` keeps them out of the test count."""
    files = [{"filename": f, "status": "added"} for f in added]
    files += [{"filename": "specs/x/fixtures/modified.json", "status": "modified"},
              {"filename": "specs/x/fixtures/removed.json", "status": "removed"}]
    return {"total_commits": total_commits, "ahead_by": total_commits, "files": files}


def pr_list_body(pr_number):
    """`gh pr list --json number` for the branch, newest PR in the middle:
    only the step's own sort-then-reverse picks it."""
    if pr_number is None:
        return []
    return [{"number": pr_number - 50}, {"number": pr_number}, {"number": pr_number - 200}]


def run_case(script, *, resolved_stage="finalize", resolved_stage_source="name", run_conclusion="success",
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
        with open(os.path.join(fixture_dir, "pr-list.json"), "w", encoding="utf-8") as fh:
            json.dump(pr_list_body(pr_number), fh)
        if fail_list:
            open(os.path.join(fixture_dir, "fail-list"), "w").close()
        with open(os.path.join(fixture_dir, "pr-view.json"), "w", encoding="utf-8") as fh:
            json.dump({"body": body, "baseRefName": "main", "headRefName": f"spec/{slug}",
                       "baseRefOid": base_sha, "headRefOid": head_sha}, fh)
        if fail_view:
            open(os.path.join(fixture_dir, "fail-view"), "w").close()
        with open(os.path.join(fixture_dir, "compare.json"), "w", encoding="utf-8") as fh:
            json.dump(compare_body(total_commits, added), fh)
        if fail_compare:
            open(os.path.join(fixture_dir, "fail-compare"), "w").close()
        with open(os.path.join(fixture_dir, "contents.json"), "w", encoding="utf-8") as fh:
            json.dump(tasks_contents(tasks_md), fh)
        if fail_contents:
            open(os.path.join(fixture_dir, "fail-contents"), "w").close()

        gh_path = os.path.join(bindir, "gh")
        with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(STUB_GH.replace("__FIXTURE_DIR__", shlex.quote(fixture_dir)))
        os.chmod(gh_path, 0o755)

        with open(os.path.join(runner_temp, "signals.json"), "w", encoding="utf-8") as fh:
            fh.write("[]")
        with open(os.path.join(runner_temp, "collector-outcomes.json"), "w", encoding="utf-8") as fh:
            fh.write("[]")

        env = {
            "GITHUB_REPOSITORY": GITHUB_REPOSITORY,
            "GH_TOKEN": "dummy-token",
            "RESOLVED_STAGE": resolved_stage,
            "RESOLVED_STAGE_SOURCE": resolved_stage_source,
            "RUN_CONCLUSION": run_conclusion,
            "SLUG": slug,
            "SPEC_DIR": spec_dir,
            "SPEC_PREFIX": "spec/",
            "PATH": bindir + os.pathsep + os.environ["PATH"],
        }
        rc, out, outputs, summary = run_step(BASH, script, workdir, env, runner_temp)
        with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
            signals = json.load(fh)
        with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
            outcomes = json.load(fh)
        return rc, out, signals, outcomes, summary
    finally:
        for d in (workdir, runner_temp, bindir, fixture_dir):
            shutil.rmtree(d, ignore_errors=True)


def make_check(failures, verbose):
    def check(tag, cond, detail):
        if not cond:
            failures.append(f"[{tag}] {detail}")
            if verbose:
                print(f"::error::verify-final-pr-claims-collector: [{tag}] {detail}")
        elif verbose:
            print(f"::notice::verify-final-pr-claims-collector: [{tag}] ok")
    return check


def drift_signals(signals, claim_type=None):
    out = [s for s in signals if s.get("class-hint") == "narrative-drift"]
    if claim_type is not None:
        out = [s for s in out if s.get("facts", {}).get("claim-type") == claim_type]
    return out


def suite(script, verbose=True):
    """Run every case against `script`; -> the failed assertions."""
    failures = []
    check = make_check(failures, verbose)

    # ── Positive: task-count mismatch (claimed 42, actual 41 checked boxes).
    rc, out, signals, outcomes, _ = run_case(
        script,
        body="This PR completes 42 tasks across three phases.",
        tasks_md="\n".join(f"- [x] task {i}" for i in range(41)) + "\n- [ ] one more\n",
        total_commits=10, added=[])
    check("task mismatch", rc == 0 and len(drift_signals(signals, "tasks")) == 1,
          f"expected exactly one tasks narrative-drift signal, got rc={rc} signals={signals} out={out}")
    check("task mismatch reads the newest PR and the decoded tasks.md",
          [(s["facts"]["pr"], s["facts"]["actual-value"]) for s in drift_signals(signals, "tasks")]
          == [(301, 41)],
          f"expected the signal for PR 301 (the newest of the branch's PRs) with actual-value 41 "
          f"(tasks.md's checked boxes), got {signals}")

    # ── Positive: commit-count mismatch (claimed 10, actual 12).
    rc, out, signals, outcomes, _ = run_case(
        script,
        body="10 commits landed for this feature.", total_commits=12)
    check("commit mismatch", rc == 0 and len(drift_signals(signals, "commits")) == 1,
          f"expected exactly one commits narrative-drift signal, got rc={rc} signals={signals} out={out}")
    check("commit mismatch reads the compare total",
          [s["facts"]["actual-value"] for s in drift_signals(signals, "commits")] == [12],
          f"expected actual-value 12 (the compare's total_commits), got {signals}")

    # ── Positive: test-count (fixture-file-count) mismatch (claimed 5, actual 3).
    rc, out, signals, outcomes, _ = run_case(
        script,
        body="Added 5 test cases for this change.",
        added=["specs/x/fixtures/a.json", "specs/x/fixtures/b.json", "specs/x/fixtures/c.json"])
    check("test mismatch", rc == 0 and len(drift_signals(signals, "tests")) == 1,
          f"expected exactly one tests narrative-drift signal, got rc={rc} signals={signals} out={out}")
    check("test mismatch counts only added fixture files",
          [s["facts"]["actual-value"] for s in drift_signals(signals, "tests")] == [3],
          f"expected actual-value 3 (the added fixtures, not the modified or removed ones), "
          f"got {signals}")

    # ── Negative: unparseable claim shape (no isolable number) → no signal.
    rc, out, signals, outcomes, _ = run_case(
        script,
        body="A great deal of work went into the tasks for this spec.",
        tasks_md="- [x] done\n", total_commits=5)
    check("unparseable claim", rc == 0 and drift_signals(signals) == [],
          f"prose with no isolable number must produce no signal, got rc={rc} signals={signals} out={out}")

    # ── Negative: every claim matches ground truth → no signal.
    rc, out, signals, outcomes, _ = run_case(
        script,
        body="This PR completes 1 tasks, 1 commits, 1 tests.",
        tasks_md="- [x] only\n", total_commits=1, added=["specs/x/fixtures/a.json"])
    check("matching claims", rc == 0 and drift_signals(signals) == [],
          f"claims matching ground truth must produce no signal, got rc={rc} signals={signals} out={out}")

    # ── Negative: non-finalize run → scope guard exits before any signal or
    #    collector-outcomes write.
    rc, out, signals, outcomes, _ = run_case(
        script,
        resolved_stage="plan", resolved_stage_source="name",
        body="This PR completes 42 tasks.", tasks_md="- [x] a\n", total_commits=1)
    check("non-finalize scope guard", rc == 0 and signals == [] and outcomes == [],
          f"a non-finalize run must skip before writing signals or collector-outcomes, got rc={rc} "
          f"signals={signals} outcomes={outcomes} out={out}")

    # ── Negative: no PR resolvable for the branch → outcome 'ok', no signal.
    rc, out, signals, outcomes, _ = run_case(script, pr_number=None)
    check("no PR resolvable", rc == 0 and signals == []
          and outcomes == [{"collector": "collect-final-pr-claims", "outcome": "ok"}],
          f"no resolvable PR must record outcome 'ok' with no signal, got rc={rc} signals={signals} "
          f"outcomes={outcomes} out={out}")

    # ── Negative: `gh pr view` itself fails → outcome 'failed', no signal, and
    #    (FR-010/leg-0) collector-outcomes is still WRITTEN, not lost.
    rc, out, signals, outcomes, _ = run_case(script, fail_view=True)
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
        script,
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
        script,
        body="", tasks_md="- [x] a\n- [x] b\n- [x] c\n- [x] d\n- [x] e\n", total_commits=3)
    check("leg-3 empty PR body", rc == 0 and drift_signals(signals) == [],
          f"an empty PR body must parse no claims and produce no signal regardless of the actual "
          f"values, got rc={rc} signals={signals} out={out}")
    return failures


# Each mutation breaks one of the step's own --jq programs; the cases above
# must then fail. A mutation that no longer applies fails too, so this list
# moves with the step's text.
MUTATIONS = [
    ("the pr list --jq drops the sort and takes the first PR listed",
     "--jq 'sort_by(.number) | reverse | .[0].number // empty'",
     "--jq '.[0].number // empty'"),
    ("the compare --jq reads .files from a wrong key",
     "added: [.files[]? | select(.status==\"added\") | .filename]",
     "added: [.file[]? | select(.status==\"added\") | .filename]"),
    ("the compare --jq counts every file, not only the added ones",
     "added: [.files[]? | select(.status==\"added\") | .filename]",
     "added: [.files[]? | .filename]"),
    ("the compare --jq reads total_commits from a wrong key",
     "--jq '{total_commits, added:",
     "--jq '{total_commits: .commits, added:"),
    ("the contents --jq reads a wrong key",
     "--jq '.content'",
     "--jq '.contents'"),
]

failures = suite(SCRIPT)
for label, old, new in MUTATIONS:
    if SCRIPT.count(old) != 1:
        failures.append(f"mutation {label!r}: expected exactly one {old!r} in {STEP!r}, "
                        f"found {SCRIPT.count(old)} -- update this harness alongside the step.")
        print(f"::error::verify-final-pr-claims-collector: {failures[-1]}")
        continue
    broke = suite(SCRIPT.replace(old, new, 1), verbose=False)
    if broke:
        print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
    else:
        failures.append(f"MUTATION SURVIVED - {label}.")
        print(f"::error::verify-final-pr-claims-collector: {failures[-1]}")

if failures:
    print(f"❌ verify-final-pr-claims-collector: {len(failures)} assertion(s) failed:")
    for f in failures:
        print(f"- {f}")
    sys.exit(1)

print("✅ verify-final-pr-claims-collector: all assertions passed.")
PY
