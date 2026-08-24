#!/usr/bin/env python3
"""Gate 29 — a stage that dies at entry reaches the chain-stop notice, and
nothing else does.

Called "Gate 28" throughout specs/041-implement-stall-notice's plan/tasks/
data-model docs, written against a base state where that number was free.
By the time this landed, Gate 28 already named the gh-api-explicit-method
check, so this is 29 — the next free number, same script, same contract.

WHY THIS EXISTS
----------------
This whole feature (specs/041-implement-stall-notice) exists because
`implement.yml`'s `stalled` job's condition, `needs.implement.outputs.
final-ok == 'false'`, carried no status-check function — so GitHub's
implicit `success()` over the needs-closure suppressed it before that arm
was ever read, for every cause except the one the condition's own text
named. Gate 15 (amended alongside this gate) proves the CONDITION'S SHAPE is
readable; it does not prove the condition actually admits the failure
shapes it claims to. Only evaluating the shipped `if:` against modelled
`needs.*` values proves that — which is what this gate does, for exactly
the seven survivor-job call sites this feature ships (data-model.md's
condition table).

WHAT THIS CHECKS
----------------
1. Extracts each of the seven survivor-job `if:` strings directly from the
   shipped workflow YAML (`wc_shell_harness.find_job`).
2. Evaluates each against a fixture table of modelled `needs.*` result/
   output combinations (contracts/chain-stop-gate-coverage.md), asserting
   the boolean matches the intended reachability: fires on dependency
   failure, entry-job failure/skip, and (implement only) the exhausted-
   retry flag; stays silent on a healthy run, a cancelled run, and a
   refusal-flagged failure.
3. Applies the four required mutations (data-model.md's mutation table) to
   a COPY of each extracted condition and re-runs step 2, asserting at
   least one row now disagrees for every mutation (FR-013) — the same
   `if mutated == original` guard `verify-stall-restart-runbook.py`
   establishes, so a mutation that silently failed to apply cannot produce
   a false pass.

MECHANISM (research.md D8)
---------------------------
A small transpiler, not a general GitHub Actions expression interpreter:
`&&`/`||`/`!cancelled()` map onto Python's `and`/`or`/`not`, and
`needs.<job>.result` / `needs.<job>.outputs.<name>` / `inputs.<name>` map
onto dict lookups against a modelled context — then the whole thing is
`eval()`-ed. This is deliberately narrower than a real GHA evaluator (no
`success()`/`failure()`/`fromJSON`/functions beyond `cancelled()`) because
the seven conditions this feature ships use exactly this subset; growing it
is for the day a shipped condition needs more, not in anticipation of one.

Usage: python3 .github/scripts/verify-chain-stop-notice.py
"""
import copy
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_job, use_utf8_stdout

# ------------------------------------------------------------ the evaluator

_OUTPUT_RE = re.compile(r"needs\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")
_RESULT_RE = re.compile(r"needs\.([A-Za-z0-9_-]+)\.result\b")
_INPUT_RE = re.compile(r"inputs\.([A-Za-z0-9_-]+)\b")
_CANCELLED_RE = re.compile(r"!\s*cancelled\(\)")


def transpile(expr):
    """GHA expression subset -> Python source, evaluable against a context."""
    out = expr
    out = _CANCELLED_RE.sub("(not CANCELLED)", out)
    out = out.replace("cancelled()", "CANCELLED")
    out = _OUTPUT_RE.sub(r"NEEDS.get('\1', {}).get('outputs', {}).get('\2', '')", out)
    out = _RESULT_RE.sub(r"NEEDS.get('\1', {}).get('result', '')", out)
    out = _INPUT_RE.sub(r"INPUTS.get('\1', '')", out)
    out = out.replace("&&", " and ").replace("||", " or ")
    # The whole expression is wrapped in one outer paren pair so a bare
    # `X &&\n( Y )` shaped condition — valid YAML, invalid bare Python
    # continuation — parses: Python only allows an implicit line break
    # inside brackets, and the multi-line conditions this feature ships
    # break BEFORE that inner paren opens.
    return "(" + out + ")"


def evaluate(expr, needs, inputs, cancelled):
    """True/False for GHA expression `expr` under the given modelled context."""
    src = transpile(expr)
    try:
        return bool(eval(src, {"__builtins__": {}},  # noqa: S307
                         {"NEEDS": needs, "INPUTS": inputs, "CANCELLED": cancelled}))
    except Exception as exc:  # noqa: BLE001 — report, do not crash the gate
        raise ValueError(f"could not evaluate {expr!r} (transpiled: {src!r}): "
                         f"{exc}") from exc


# --------------------------------------------------------------- call sites

CALL_SITES = [
    {"file": ".github/workflows/implement.yml", "job_id": "stalled",
     "entry": "implement", "upstream": ["verify-image-prerequisites"],
     "exhausted_retry": True, "mode": None},
    {"file": ".github/workflows/clarify.yml", "job_id": "stalled",
     "entry": "clarify", "upstream": ["verify-image-prerequisites"],
     "exhausted_retry": False, "mode": None},
    {"file": ".github/workflows/finalize.yml", "job_id": "stalled",
     "entry": "finalize", "upstream": ["verify-image-prerequisites"],
     "exhausted_retry": False, "mode": None},
    {"file": ".github/workflows/intake.yml", "job_id": "stalled",
     "entry": "intake", "upstream": ["verify-image-prerequisites"],
     "exhausted_retry": False, "mode": None},
    {"file": ".github/workflows/pr-conversation.yml", "job_id": "stalled",
     "entry": "classify-and-announce", "upstream": ["verify-image-prerequisites"],
     "exhausted_retry": False, "mode": None},
    {"file": ".github/workflows/tasks.yml", "job_id": "stalled",
     "entry": "tasks", "upstream": ["verify-image-prerequisites", "resolve-spec"],
     "exhausted_retry": False, "mode": ("mode", "generate")},
    {"file": ".github/workflows/tasks.yml", "job_id": "stalled-approved",
     "entry": "tasks-approved", "upstream": ["verify-image-prerequisites", "resolve-spec"],
     "exhausted_retry": False, "mode": ("mode", "approved")},
]


def extract_condition(site):
    job = find_job(site["file"], site["job_id"])
    cond = job.get("if")
    if not cond or not isinstance(cond, str):
        sys.exit(f"::error file={site['file']}::job {site['job_id']!r} has no "
                 f"string `if:` — Gate 29 has nothing to evaluate.")
    return cond


# ------------------------------------------------------------- fixture rows
#
# (label, needs_overrides, cancelled, expect) — needs_overrides is a dict of
# job-id -> {"result": ..., "outputs": {...}} merged over a default
# all-succeeded, no-output context. Only the ENTRY job's/upstream jobs'
# results matter; every other declared job defaults to success with no
# outputs, matching a healthy run.

def default_needs(site):
    needs = {j: {"result": "success", "outputs": {}} for j in site["upstream"]}
    needs[site["entry"]] = {"result": "success", "outputs": {}}
    return needs


def fixtures_for(site):
    entry = site["entry"]
    upstream = site["upstream"][0]
    rows = []

    def row(label, overrides, expect, cancelled=False):
        needs = copy.deepcopy(default_needs(site))
        for job, patch in overrides.items():
            needs.setdefault(job, {"result": "success", "outputs": {}})
            needs[job].update({k: v for k, v in patch.items() if k != "outputs"})
            needs[job].setdefault("outputs", {})
            needs[job]["outputs"].update(patch.get("outputs", {}))
        rows.append((label, needs, cancelled, expect))

    row("healthy run", {}, False)
    row("entry job success, refusal-reason set", {
        entry: {"outputs": {"refusal-reason": "missing credential"}}}, False)
    row("entry job failure, refusal-reason set", {
        entry: {"result": "failure", "outputs": {"refusal-reason": "missing credential"}}},
        False)
    row("entry job failure, refusal-reason empty", {
        entry: {"result": "failure"}}, True)
    row("entry job skipped", {entry: {"result": "skipped"}}, True)
    row("upstream dependency failure, entry job skipped", {
        upstream: {"result": "failure"}, entry: {"result": "skipped"}}, True)
    row("run cancelled", {entry: {"result": "failure"}}, False, cancelled=True)
    if site["exhausted_retry"]:
        row("exhausted retry: entry success, final-ok false, no refusal", {
            entry: {"outputs": {"final-ok": "false"}}}, True)
    if len(site["upstream"]) > 1:
        extra = site["upstream"][1]
        row(f"{extra} refused, entry job also failed/skipped", {
            extra: {"outputs": {"refusal-reason": "cannot resolve a spec slug"}},
            entry: {"result": "skipped"}}, False)
    return rows


def run_suite(site, cond):
    inputs = {}
    if site["mode"]:
        key, value = site["mode"]
        inputs[key] = value
    failures = []
    for label, needs, cancelled, expect in fixtures_for(site):
        try:
            actual = evaluate(cond, needs, inputs, cancelled)
        except ValueError as exc:
            failures.append(f"{site['file']}:{site['job_id']} [{label}]: {exc}")
            continue
        if actual != expect:
            failures.append(
                f"{site['file']}:{site['job_id']} [{label}]: expected "
                f"{expect}, got {actual} — needs={needs} cancelled={cancelled}")
    return failures


# -------------------------------------------------------------- mutations

def _mut_remove_status_guard(cond):
    """Strip !cancelled() — the condition is provably suppressed on a
    cancelled run, the exact defect this feature closes."""
    return cond.replace("!cancelled() &&", "").replace("!cancelled() && ", "")


def _mut_narrow_drop_failure_arm(cond):
    """Drop the entry-job-itself-failed arm, keeping only 'skipped'.

    Identifies the ENTRY job by its 'skipped' arm — only the entry job's own
    result is ever compared against 'skipped' in these conditions — so this
    only ever touches the entry job's own failure arm, never an upstream
    one (which would also break the upstream-dependency row and understate
    what this mutation proves).
    """
    m = re.search(r"needs\.([A-Za-z0-9_-]+)\.result == 'skipped'", cond)
    if not m:
        return cond
    entry = re.escape(m.group(1))
    # Flexible whitespace: the block scalar's stripped indentation differs
    # by call site (implement.yml's base indent is not clarify.yml's), so a
    # literal "\n        " would silently no-op on some files and only ever
    # get exercised by whichever site happened to match.
    pat = re.compile(rf"needs\.{entry}\.result == 'failure' \|\|\s*")
    return pat.sub("", cond, count=1)


def _mut_widen_admit_success(cond):
    """Widen to also fire on the entry job's own success — the healthy-run
    and refusal rows would now wrongly reach the notice."""
    m = re.search(r"needs\.([A-Za-z0-9_-]+)\.result == 'skipped'", cond)
    if not m:
        return cond
    entry = m.group(1)
    return cond.replace(f"needs.{entry}.result == 'skipped'",
                        f"needs.{entry}.result == 'skipped' || "
                        f"needs.{entry}.result == 'success'")


def _mut_bespoke_condition(cond):
    """Point the call site at a condition that does not match the shared
    shape at all — always true, i.e. `always()`."""
    return "always()"


MUTATIONS = [
    ("remove the !cancelled() status-check guard", _mut_remove_status_guard),
    ("narrow: drop the entry-job-itself-failed arm", _mut_narrow_drop_failure_arm),
    ("widen: also fire on the entry job's own success", _mut_widen_admit_success),
    ("bespoke: not the shared shape at all (always())", _mut_bespoke_condition),
]


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github/workflows"):
        sys.exit("::error::run this from the repository root.")

    failures = []
    conditions = {}
    for site in CALL_SITES:
        cond = extract_condition(site)
        conditions[(site["file"], site["job_id"])] = cond
        failures += run_suite(site, cond)

    for f in failures:
        print(f"::error::{f}")

    mutation_failures = []
    for label, apply_mutation in MUTATIONS:
        any_disagreed = False
        for site in CALL_SITES:
            original = conditions[(site["file"], site["job_id"])]
            mutated = apply_mutation(original)
            if mutated == original:
                continue  # this mutation may not apply to every call site
            if run_suite(site, mutated):
                any_disagreed = True
        if any_disagreed:
            print(f"Mutation OK — {label}: caught.")
        else:
            print(f"::error::MUTATION SURVIVED — {label}: no call site's "
                  f"fixture table disagreed after this mutation, or the "
                  f"mutation never applied to any of the seven conditions.")
            mutation_failures.append(label)
    failures += [f"mutation survived: {m}" for m in mutation_failures]

    print(f"Gate 29: {len(CALL_SITES)} survivor-job condition(s), "
          f"{len(MUTATIONS)} mutation(s); {len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
