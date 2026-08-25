#!/usr/bin/env python3
"""Shared plumbing for the chain-stop notice's survivor-job conditions.

WHY THIS EXISTS
----------------
Gate 29 (`verify-chain-stop-notice.py`) and the refusal-exclusion check
(`verify-chain-stop-refusal-exclusion.py`, User Story 3) both need to
extract and evaluate the same seven survivor-job `if:` conditions
(specs/041-implement-stall-notice). A Python module cannot `import` a
hyphenated filename, so this lives under the `wc_` prefix — shared module,
exempt from the gate-wiring rule (`wc_gate_registry.py`), imported by both.

The evaluator (research.md D8): a small transpiler, not a general GitHub
Actions expression interpreter. `&&`/`||`/`!cancelled()` map onto Python's
`and`/`or`/`not`, and `needs.<job>.result` / `needs.<job>.outputs.<name>` /
`inputs.<name>` map onto dict lookups against a modelled context — then the
whole thing is `eval()`-ed. Deliberately narrower than a real GHA evaluator
(no `success()`/`failure()`/`fromJSON`/functions beyond `cancelled()`)
because the seven conditions this feature ships use exactly this subset.
"""
import copy
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import find_job  # noqa: E402

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
    except Exception as exc:  # noqa: BLE001 — report, do not crash the caller
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
                 f"string `if:` — nothing to evaluate.")
    return cond


def default_needs(site):
    """All declared jobs succeeding with no outputs — a healthy run."""
    needs = {j: {"result": "success", "outputs": {}} for j in site["upstream"]}
    needs[site["entry"]] = {"result": "success", "outputs": {}}
    return needs


def inputs_for(site):
    return dict([site["mode"]]) if site["mode"] else {}


def fixtures_for(site):
    """(label, needs, cancelled, expect) rows — contracts/chain-stop-gate-
    coverage.md's fixture table, per call site."""
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
        upstream: {"result": "failure"}, entry: {"result": "skipped"}}, False)
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
    inputs = inputs_for(site)
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
