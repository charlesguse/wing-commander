# Working on wing-commander

## Before pushing

Run the full PR-time gate suite locally — it is derived from what
lint-workflows.yml actually invokes, so it is the same set CI runs:

    python .github/scripts/run-local-gates.py

A change that touches any `if:`, `continue-on-error:`, or failing step in a
workflow should also get a pass from the `review-step-gating` skill.

## Shared logic has exactly one home

Before pasting a `run:` block, jq program, or shell helper into a second
workflow, move it instead:

- Cross-workflow shell/jq belongs in a composite action under
  `.github/actions/` (scripts shared between composites go in
  `.github/actions/_shared/`), with the workflows consuming its outputs.
  Each call site keeps at most a one-line fallback for the case where the
  composite never ran.
- Repeated comment prose gets ONE canonical comment; every other site
  points at it (`-- see clarify.yml`). Gates enforce the pointers.

Why this is worth the detour: a pasted copy is invisible until the first
divergent fix. The per-run cost line was once pasted into 12 run-blocks
across 9 stage workflows, where a rounding fix would have had to land 12
times with nothing failing on a drifted copy; it now lives solely in
`wing-commander-metrics-summary`'s `cost-line` output, and
`verify-metrics-summary-record-emission.py` fails if a copy of the
formatter reappears in a workflow. When you consolidate something like
this, add the "single home" check to the nearest existing gate the same
way — a rule with no gate behind it lasts until the next session.

## Other repo-specific rules

- Workflow comments are load-bearing: gates byte-compare and mutate them.
  Treat comment edits as code edits and re-run the suite.
- This repository is public. Never reference private downstream consumers
  (repo names, orgs, customers) in code, comments, commits, PRs, or
  issues.
