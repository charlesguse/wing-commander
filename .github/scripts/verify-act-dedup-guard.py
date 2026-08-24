#!/usr/bin/env python3
"""The act job's dedup guard never treats an unresolved triage decision as
"file it as new" (PR #240 maintainer feedback on spec 024).

WHY THIS EXISTS
---------------
`act`'s "Load triage decision" step falls back to a report-only shape when
this matrix leg's own triage-decision artifact never arrived (its sibling
`triage` leg failed before "Persist triage decision" ran, or the artifact
download itself failed). Before this fix that fallback set `dedup=""`, but
the "Ensure pipeline-defect issue" step's `if:` guard only excludes
`data-integrity` and `unknown` — so an empty dedup value fell THROUGH the
guard into the comment-on-existing-issue branch and ran `gh issue comment
""`, which fails the job under this run: block's `-e`. Nothing exercised
this path: it needs a missing artifact, which no fixture had ever
simulated.

The fix reuses the guard's existing `unknown` handling — the fallback now
emits `dedup=unknown` instead of `dedup=`, one mechanism rather than a
second empty-string special case. This harness EXECUTES the shipped "Load
triage decision" step against a missing artifact, evaluates the shipped
"Ensure pipeline-defect issue" step's real `if:` expression against its
real outputs, and — whenever that expression evaluates true — EXECUTES that
step's `run:` text too, with a `gh` stub that fails exactly the way the
real CLI does when handed an empty issue reference. A regression is
therefore caught as an actual `gh issue comment ""` failure, not merely as
a recorded-output mismatch.

A MUTATION reverts the fallback to `dedup=` and asserts the suite then
fails on the missing-artifact scenario — reproducing the shipped bug.

Usage: python3 .github/scripts/verify-act-dedup-guard.py
Requires: bash, jq.
"""
import json
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import ensure_jq, resolve_bash, run_step, use_utf8_stdout

WATCHDOG = ".github/workflows/watchdog.yml"
JOB = "act"
DECISION_STEP = "Load triage decision"
ENSURE_STEP = "Ensure pipeline-defect issue"

BASH = None


def load_steps():
    with open(WATCHDOG, encoding="utf-8") as fh:
        wf = yaml.safe_load(fh) or {}
    job = (wf.get("jobs") or {}).get(JOB) or {}
    found = {}
    for step in job.get("steps") or []:
        name = (step or {}).get("name")
        if name in (DECISION_STEP, ENSURE_STEP):
            found[name] = step
    for name in (DECISION_STEP, ENSURE_STEP):
        if name not in found:
            sys.exit(f"::error file={WATCHDOG}::no step named {name!r} in job "
                     f"{JOB!r}. If it was renamed, update the workflow and "
                     f"this gate together — do not drop the check.")
    return found


def resolve_inline(script, subst):
    """Substitute `${{ EXPR }}` tokens embedded directly in a run: block's
    own text (not routed through env:) — this step's file paths and its
    warning message both do this rather than declaring env vars for them."""
    def repl(m):
        key = m.group(1).strip()
        if key not in subst:
            sys.exit(f"::error file={WATCHDOG}::verify-act-dedup-guard: "
                     f"unresolved expression '${{{{ {key} }}}}' — this "
                     f"harness only knows: {sorted(subst)}.")
        return subst[key]
    return re.sub(r"\$\{\{(.*?)\}\}", repl, script)


def run_decision(script, artifact, tmproot):
    """Execute "Load triage decision" against an optional artifact dict
    (None = the artifact never arrived, the fallback path this gate
    exists for). Returns (rc, out, outputs)."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    resolved = resolve_inline(
        script, {"runner.temp": runner_temp.replace("\\", "/"),
                 "matrix.index": "0"})
    if artifact is not None:
        triage_dir = os.path.join(runner_temp, "triage")
        os.makedirs(triage_dir, exist_ok=True)
        with open(os.path.join(triage_dir, "watchdog-triage-decision.json"),
                  "w", encoding="utf-8") as fh:
            json.dump(artifact, fh)
    rc, out, outputs, _ = run_step(BASH, resolved, workdir, {}, runner_temp)
    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(runner_temp, ignore_errors=True)
    return rc, out, outputs


IF_CLAUSE_RE = re.compile(
    r"^steps\.([\w-]+)\.outputs\.([\w-]+)\s*(!=|==)\s*'([^']*)'$")


def eval_if_expr(if_expr, outputs):
    """Evaluate this repository's `steps.X.outputs.Y (!=|==) 'literal' &&
    ...` if: expressions against concrete step outputs. Only the shape
    this workflow actually uses is supported — anything else is a hard
    error so this gate cannot silently mis-evaluate a future guard shape
    it was never updated for."""
    for clause in (c.strip() for c in if_expr.split("&&")):
        m = IF_CLAUSE_RE.match(clause)
        if not m:
            sys.exit(f"::error file={WATCHDOG}::verify-act-dedup-guard: "
                     f"unsupported if: clause {clause!r} in "
                     f"{ENSURE_STEP!r} — update this gate alongside the "
                     f"guard.")
        step_id, output_name, op, literal = m.groups()
        actual = outputs.get((step_id, output_name), "")
        matched = actual == literal
        if not (matched if op == "==" else not matched):
            return False
    return True


GH_STUB = r'''#!/usr/bin/env bash
echo "gh $*" >> "$GH_CALLS"
case "$1 $2" in
  "issue create")
    echo "https://github.com/o/r/issues/55"
    exit 0
    ;;
  "issue comment")
    if [ -z "${3:-}" ]; then
      echo "gh: issue comment: no issue number or url provided" >&2
      exit 1
    fi
    exit 0
    ;;
esac
exit 0
'''


def run_ensure_issue(step, decision_outputs, tmproot):
    """Execute "Ensure pipeline-defect issue" wired to one decision step's
    real outputs and a fixed, unsuppressed write-suppression outcome (that
    step's own guard is a separate concern from the one this gate proves).
    Returns (rc, out, calls) — calls is every `gh` invocation recorded by
    the stub, so a `gh issue comment` with an empty target is visible even
    when it does not make the step itself non-zero."""
    resolved_env = {
        "GH_TOKEN": "dummy-token",
        "DEDUP_OUTCOME": decision_outputs.get("dedup", ""),
        "DEDUP_ISSUE": decision_outputs.get("dedup-issue", ""),
        "FINGERPRINT": decision_outputs.get("fingerprint", ""),
        "CANONICAL_FACTS": decision_outputs.get("canonical-facts", ""),
        "FINDING_CLASS": "denied-tool",
        "FINDING_DESCRIPTION": "test finding",
        "FINDING_EVIDENCE": json.dumps(
            [{"source": "result-record", "locator": "signal-1"}]),
        "RUN_URL": "https://github.com/o/r/actions/runs/1",
    }
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    calls_file = os.path.join(workdir, "gh_calls")
    open(calls_file, "w").close()
    stub_path = os.path.join(bindir, "gh")
    with open(stub_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(stub_path, 0o755)

    script = resolve_inline(str(step["run"]),
                            {"runner.temp": runner_temp.replace("\\", "/")})
    env = dict(resolved_env)
    env["GH_CALLS"] = calls_file
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    rc, out, _, _ = run_step(BASH, script, workdir, env, runner_temp)
    with open(calls_file, encoding="utf-8") as fh:
        calls = fh.read()
    shutil.rmtree(workdir, ignore_errors=True)
    shutil.rmtree(runner_temp, ignore_errors=True)
    shutil.rmtree(bindir, ignore_errors=True)
    return rc, out, calls


WRITE_SUPPRESSION_OUTPUTS = {("write-suppression", "suppressed"): "false"}

FIXTURE_NONE = {"suppressed": False, "evidence-valid": True,
                "evidence-reason": "", "fingerprint": "abc123",
                "short-fingerprint": "abc123", "canonical-facts": "x",
                "dedup": "none", "dedup-issue": ""}
FIXTURE_UNKNOWN = {"suppressed": False, "evidence-valid": True,
                   "evidence-reason": "", "fingerprint": "abc123",
                   "short-fingerprint": "abc123", "canonical-facts": "x",
                   "dedup": "unknown", "dedup-issue": ""}


def scenarios(decision_script, ensure_step, if_expr, tmproot):
    failures = []

    def note(msg):
        failures.append(msg)

    # 1. Baseline: a normal, present artifact with dedup=none must still
    #    reach "Ensure pipeline-defect issue" and file a fresh issue — this
    #    fix must not turn INTO a new false negative for the ordinary path.
    rc, out, outputs = run_decision(decision_script, FIXTURE_NONE, tmproot)
    if rc != 0:
        note(f"dedup=none, artifact present: Load triage decision exited "
             f"{rc}: {out.strip()}")
    else:
        step_outputs = dict(WRITE_SUPPRESSION_OUTPUTS)
        step_outputs.update({("decision", k): v for k, v in outputs.items()})
        fires = eval_if_expr(if_expr, step_outputs)
        if not fires:
            note("dedup=none, artifact present: the Ensure pipeline-defect "
                 "issue guard did not fire — a normal new finding would go "
                 "unfiled.")
        else:
            rc2, out2, calls = run_ensure_issue(ensure_step, outputs, tmproot)
            if rc2 != 0:
                note(f"dedup=none, artifact present: Ensure pipeline-defect "
                     f"issue exited {rc2}: {out2.strip()}")
            if "issue create" not in calls:
                note(f"dedup=none, artifact present: guard fired but never "
                     f"called `gh issue create`. gh calls: "
                     f"{calls.strip() or '(none)'}")

    # 2. dedup=unknown with the artifact present (the ordinary broken-lookup
    #    path, T035/T036): the guard must not fire.
    rc, out, outputs = run_decision(decision_script, FIXTURE_UNKNOWN, tmproot)
    if rc != 0:
        note(f"dedup=unknown, artifact present: Load triage decision exited "
             f"{rc}: {out.strip()}")
    else:
        step_outputs = dict(WRITE_SUPPRESSION_OUTPUTS)
        step_outputs.update({("decision", k): v for k, v in outputs.items()})
        if eval_if_expr(if_expr, step_outputs):
            note("dedup=unknown, artifact present: the guard fired — a "
                 "broken dedup lookup must never be treated as fileable.")

    # 3. The bug this fix targets: the triage-decision artifact never
    #    arrived at all. The fallback must (a) record dedup=unknown, the
    #    SAME outcome scenario 2 already proves is report-only, not merely
    #    happen to route around the guard by some other value, and (b)
    #    the guard itself must not fire.
    rc, out, outputs = run_decision(decision_script, None, tmproot)
    if rc != 0:
        note(f"missing triage-decision artifact: Load triage decision "
             f"exited {rc}: {out.strip()}")
    else:
        if outputs.get("dedup") != "unknown":
            note(f"missing triage-decision artifact: dedup output is "
                 f"{outputs.get('dedup')!r}, expected 'unknown' — the "
                 f"fallback must reuse the guard's existing suppress-and-"
                 f"report mechanism, not a second empty-string special "
                 f"case.")
        step_outputs = dict(WRITE_SUPPRESSION_OUTPUTS)
        step_outputs.update({("decision", k): v for k, v in outputs.items()})
        if eval_if_expr(if_expr, step_outputs):
            rc2, out2, calls = run_ensure_issue(ensure_step, outputs, tmproot)
            note(f"missing triage-decision artifact: the Ensure "
                 f"pipeline-defect issue guard fired (it must stay "
                 f"report-only). Execution then {'exited ' + str(rc2) if rc2 else 'ran'}"
                 f" — gh calls: {calls.strip() or '(none)'}. "
                 f"{out2.strip()}")
    return failures


def mut_revert_to_empty_dedup(script):
    """The shipped bug: the fallback emitted `dedup=` instead of
    `dedup=unknown`, which fell through the guard's `!= 'unknown'` check."""
    old = 'echo "dedup=unknown"'
    if old not in script:
        sys.exit(f"::error file={WATCHDOG}::verify-act-dedup-guard: could "
                 f"not find {old!r} in {DECISION_STEP!r} to mutate — the "
                 f"step text may have changed shape.")
    return script.replace(old, 'echo "dedup="')


MUTATIONS = [
    ("the missing-artifact fallback reverted to dedup= instead of "
     "dedup=unknown", mut_revert_to_empty_dedup),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    steps = load_steps()
    decision_step = steps[DECISION_STEP]
    ensure_step = steps[ENSURE_STEP]
    if_expr = str(ensure_step.get("if") or "")
    if not if_expr:
        sys.exit(f"::error file={WATCHDOG}::{ENSURE_STEP!r} carries no if: "
                 f"condition — this gate's whole premise (the guard "
                 f"excludes unknown/data-integrity) no longer holds.")
    decision_script = str(decision_step["run"])

    root = tempfile.mkdtemp()
    failures = []
    try:
        failures = scenarios(decision_script, ensure_step, if_expr, root)
        for f in failures:
            print(f"::error::{f}")

        for label, mutate in MUTATIONS:
            mutated = mutate(decision_script)
            if mutated == decision_script:
                print(f"::error::mutation {label!r} changed nothing — the "
                      f"code it edits was rewritten. Update the mutation so "
                      f"this gate keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = scenarios(mutated, ensure_step, if_expr, root)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - reintroducing {label} "
                      f"broke nothing in this suite, so the suite is not "
                      f"testing that defect. Fix the scenarios, not the "
                      f"mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print(f"act dedup guard: 3 scenario(s), {len(MUTATIONS)} mutation(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
