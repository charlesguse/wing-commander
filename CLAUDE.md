# Working on wing-commander

## Before pushing

Run the full PR-time gate suite locally — it is derived from what
lint-workflows.yml actually invokes, so it is the same set CI runs:

    python .github/scripts/run-local-gates.py

A change that touches any `if:`, `continue-on-error:`, or failing step in a
workflow should also get a pass from the `review-step-gating` skill.

A change that adds a `container:` block to a job, or a `run:` step inside
one, should also get a pass from the `container-shell-safety` skill.

## Shared logic has exactly one home

Before pasting a `run:` block, jq program, or shell helper into a second
workflow, move it instead:

- Cross-workflow shell/jq belongs in a composite action under
  `.github/actions/` (scripts shared between composites go in
  `.github/actions/_shared/`), with the workflows consuming its outputs.
  Each call site keeps at most a one-line fallback for the case where the
  composite never ran.
- Repeated comment prose gets ONE canonical comment; every other site
  points at it (`-- see clarify.yml`). Gate 47
  (verify-comment-canonical-pointers.py) enforces the pointers.

Why this is worth the detour: a pasted copy is invisible until the first
divergent fix. The per-run cost line was once pasted into 12 run-blocks
across 9 stage workflows, where a rounding fix would have had to land 12
times with nothing failing on a drifted copy; it now lives solely in
`wing-commander-metrics-summary`'s `cost-line` output, and
`verify-metrics-summary-record-emission.py` fails if a copy of the
formatter reappears in a workflow. When you consolidate something like
this, add the "single home" check to the nearest existing gate the same
way — a rule with no gate behind it lasts until the next session.

## Working the issue board

Open issues are worked in this order: triage, route, fix, review, merge,
prove. Each step has a rule.

- Triage against current main before touching code. Read the commits
  since the issue was filed and the run it cites. A watchdog
  `pipeline-defect` whose execution-output artifact records an API 429
  (a `rate_limit_event`, `api_error_status: 429`, one turn, zero cost) or
  an upstream action bump is closed with that evidence quoted, not fixed.
- Route by shape. A change that is deterministic and gate-shaped (a new
  `verify-*.py`, a plumbing fix, a comment correction) and carries no
  design trade-off is a local fix PR. A change that needs the owner to
  decide a trade-off, spans several stages, or would benefit from the
  clarify stage's questions gets the `spec-request` label so the pipeline
  runs it. File the issue first and apply the label as a separate action;
  the label event is what starts intake.
- Every fix PR gets a code review before merge. Fix the findings in the
  same PR. A bug the review surfaces outside the PR's scope becomes a new
  issue carrying the line `Found by the code review of #N`, never an
  extra commit that widens the PR.
- A fix to behaviour that only runs in Actions is proven after merge by
  re-driving one run (`gh workflow run` on the wrapper that can dispatch
  it) and recording the evidence on the PR or the issue.
- Pipeline agent runs and local Claude sessions share one usage window.
  Keep concurrent local agents to about three, and note any lifecycle
  issue in `stage:implement` before fanning out so a stall can be
  attributed to the burst rather than to the pipeline.
- `gh pr merge` on a PR that touches `.github/workflows/` needs a token
  with the `workflow` scope. When GitHub refuses for that reason, hand the
  merge to the maintainer (`gh auth refresh -h github.com -s workflow`);
  never push to main around the refusal.

## Other repo-specific rules

- Workflow comments are load-bearing: gates byte-compare and mutate them.
  Treat comment edits as code edits and re-run the suite.
- This repository is public. Never reference private downstream consumers
  (repo names, orgs, customers) in code, comments, commits, PRs, or
  issues.
- The Sync Impact Report comments stacked at the top of
  `.specify/memory/constitution.md` are this repository's amendment
  history. Keep them. The vendored `speckit-constitution` skill (Spec Kit
  v1.0.5+) calls its report temporary scratch to be removed before commit;
  that instruction does not apply here.
