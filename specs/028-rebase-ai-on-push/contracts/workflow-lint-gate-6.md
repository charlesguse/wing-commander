# Contract Delta: `lint-workflows.yml` — Gate 6

There is no prior contract document for `lint-workflows.yml` beyond
`specs/025-lint-composite-actions/contracts/lint-guard-delta.md` (which
covers the "Parse YAML and bash -n every run block" step, unaffected here).
This delta adds a new, independent gate to the same `lint` job (which
already runs Gates 2/3/5) — it does not modify any existing gate's logic or
output.

## New check: agent-bearing wrapper ↔ supported-event mismatch

```python
import glob, os, sys, re, yaml

SUPPORTED_EVENTS = {
    "issues", "issue_comment", "pull_request",
    "workflow_dispatch", "workflow_run", "schedule",
}  # research.md R6 — deliberately excludes push (the confirmed defect);
   # extend only with a new entry backed by evidence in this repository.

CLAUDE_ACTION_PREFIX = "anthropics/claude-code-action"

docs = {}
for f in sorted(glob.glob(".github/workflows/*.yml")):
    docs[os.path.basename(f)] = yaml.safe_load(open(f, encoding="utf-8")) or {}

def is_agent_bearing(wf):
    for job in (wf.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            uses = (step or {}).get("uses", "")
            if uses.startswith(CLAUDE_ACTION_PREFIX):
                return True
    return False

def reachable_events(if_expr, wrapper_events):
    if not if_expr:
        return set(wrapper_events)
    included = set(re.findall(r"event_name\s*==\s*'([\w-]+)'", if_expr))
    excluded = set(re.findall(r"event_name\s*!=\s*'([\w-]+)'", if_expr))
    if included:
        return included & set(wrapper_events)
    if excluded:
        return set(wrapper_events) - excluded
    return set(wrapper_events)  # no recognizable clause — conservative default (research.md R7)

failures = 0
for fname, wf in docs.items():
    on = wf.get(True, wf.get("on"))
    wrapper_events = set(on.keys()) if isinstance(on, dict) else set(on or []) if isinstance(on, list) else set()
    if not wrapper_events:
        continue

    for jname, job in (wf.get("jobs") or {}).items():
        uses = (job or {}).get("uses", "")
        if not uses.startswith("./.github/workflows/"):
            continue
        called = docs.get(os.path.basename(uses))
        if called is None or not is_agent_bearing(called):
            continue

        reachable = reachable_events(job.get("if", ""), wrapper_events)
        flagged = sorted(reachable - SUPPORTED_EVENTS)
        if flagged:
            print(f"::error file=.github/workflows/{fname}::job {jname!r} calls "
                  f"{uses}, whose resolved stage runs a claude-code-action step, "
                  f"under event(s) {flagged} — that agent does not support "
                  f"{'this event' if len(flagged) == 1 else 'these events'}. "
                  f"Supported: {sorted(SUPPORTED_EVENTS)}.")
            failures += 1

print(f"Gate 6: checked every agent-bearing wrapper↔stage pair; {failures} failure(s).")
sys.exit(1 if failures else 0)
```

**Purpose**: FR-008 through FR-011 — a static, pre-merge check that fails a
pull request whenever a wrapper job reaches an agent-bearing resolved stage
under an event the agent doesn't support, naming the wrapper file, the job,
and every offending event.

**Behavior**:

1. FR-009 (only agent-bearing wrappers are evaluated): `is_agent_bearing`
   gates the entire per-job check — a wrapper calling a stage with no
   `claude-code-action` step contributes zero failures, regardless of what
   events it declares (spec Acceptance Scenario 3 / User Story 2).
2. FR-010 (forward-looking): `flagged` is computed as a set difference
   against `SUPPORTED_EVENTS`, not an equality check against `push` — any
   future unsupported event (a release event, a branch-creation event, or
   anything else not on the list) is caught the same way (Acceptance
   Scenario 4).
3. Edge case ("a wrapper triggered by several events, only some
   unsupported"): `flagged` can contain more than one event; the check
   does not short-circuit on the first match, and the annotation lists all
   of them.
4. FR-011 (actionable output): the `::error` annotation names the wrapper
   file (`file=` attribute, consistent with Gates 2/3/5's own annotation
   shape), the job identifier, the resolved stage path, and the exact
   flagged event list — a maintainer does not need run logs to act on it.
5. Data-model.md's "Job Reachable-Event Set" table is this function's
   contract precisely: `reachable_events` implements the three-row table
   (no clause / `==` clauses / `!=` clauses) verbatim.

**Permissions**: Runs inside the existing `lint` job
(`if: github.event_name == 'pull_request'`), which already declares
`permissions: contents: read` — Gate 6 reads only files already in the
checkout (workflow YAML), writes only `::error` annotations, matching
Gates 2/3/5's existing footprint. No new job, no new trigger, no new
permission.

**Trigger scope**: Unchanged — `lint-workflows.yml`'s existing
`on.pull_request.paths` (`.github/workflows/**`, `.github/actions/**`,
`.github/scripts/**`, `.specify/scripts/**`) already covers any PR that
edits a wrapper's `on:`/`if:` or a stage's agent step, since both live
under `.github/workflows/**`. No path filter change is needed for this
gate (contrast with `specs/025-lint-composite-actions/`, which needed a
path-filter addition because it discovered a previously-uncovered file
tree; Gate 6 only reads files the trigger already covers).

**Non-goals**: Gate 6 is not a general GitHub Actions expression evaluator
(research.md R7) — an `if:` that gates event-reachability through
something other than a literal `github.event_name ==`/`!=` comparison
(e.g. a `needs.*.outputs` value, a `contains()` call) falls back to the
conservative "every wrapper-declared event is reachable" default rather
than being resolved precisely. It also does not evaluate `claude.yml` or
`claude-code-review.yml` (research.md R8) — those embed the agent step
directly rather than through a wrapper/resolved-stage split, which is
outside what FR-008 through FR-011 describe.
