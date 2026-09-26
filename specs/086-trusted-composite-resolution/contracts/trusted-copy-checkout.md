# Contract: The Trusted Copy Checkout Step

Applies to every job in `.github/workflows/board-loop.yml` that resolves
one or more local composite actions: `select`, `triage`, `route`, `fix`,
`review`, `readiness`, `prove-gate`, `prove`. `resolve-model` carries no
composite reference today and gains no step (research.md D3); if it ever
gains one, this same contract applies to it with no amendment.

## Step shape

```yaml
- name: Checkout board-loop's own trusted copy (composites)
  uses: actions/checkout@v5
  with:
    ref: ${{ github.sha }}
    path: .wc-pristine-repo
    persist-credentials: false
```

followed, in the same job, by a provenance line (data-model.md
"Provenance Record", FR-013):

```yaml
  # (either a `run:` line appended to the step above via a shell one-liner,
  # or a tiny sibling step immediately after it)
  run: |
    echo "board-loop: composites resolved from $(git -C .wc-pristine-repo rev-parse HEAD) at ref ${{ github.sha }}." >> "$GITHUB_STEP_SUMMARY"
```

The step's `name:` is the canonical string Gate 99 matches on
(contracts/gate-99.md rule (b)/(c)/(d)) — it MUST NOT be reworded per call
site.

## Placement rule (FR-002/FR-006)

The step MUST appear, in its own job, before:

1. every `uses: ./.wc-pristine-repo/.github/actions/...` reference in that
   job (in practice, always before the job's first composite call, which
   is `wing-commander-context`);
2. every step that mints or re-establishes the App credential
   (`wing-commander-context`, at every call site in the job — pre-agent
   and post-agent alike);
3. every `anthropics/claude-code-action@` step in the job.

Concretely:

- `select`, `triage`, `route`, `prove-gate`, `prove`: immediately after the
  job's own initial `Checkout` step (these jobs have no helper-script
  snapshot to sit beside — research.md D2).
- `fix`, `review`, `readiness`: immediately after the existing "Snapshot
  helper scripts (before any agent runs)" step (Gate 98's subject),
  keeping both trusted-provenance steps adjacent by convention. In `fix`,
  this is still before the "Fetch main / checkout the fix branch" step
  that switches the workspace to the item's own branch — the ordering
  that makes User Story 1 Acceptance Scenario 3/4 hold for both the resume
  and fresh-entry paths.

## Composite reference rewrite (FR-001)

Every `uses: ./.github/actions/<name>` anywhere in `board-loop.yml`
becomes `uses: ./.wc-pristine-repo/.github/actions/<name>`. No exceptions,
no job-scoped list — Gate 99 bans the raw form file-wide
(contracts/gate-99.md rule (a)).

## Fail-closed (FR-006)

The step MUST carry no `continue-on-error: true` and no `if:` condition
that could let the job proceed past it without having established the
sidecar (a bare `!cancelled()`/`success()` consistent with the job's own
existing `if:` is fine; a condition that could evaluate false while a
dependent composite reference still runs is not). A checkout failure
(unresolvable ref, transient network) fails the job outright, before any
credential mint and before any agent step — there is no fallback to a
workspace-relative `uses:`.

## Non-staging guarantee (FR-007)

`.wc-pristine-repo` MUST be listed in this repository's own `.gitignore`
(research.md D4) so that no `git add` invocation in the job — including
the fixer and review-fixup agents' own `Bash(git add:*)` tool grant —
stages it into the item's branch, regardless of whether that invocation
names the path, uses `-A`, or uses `.`. This is a repository-file fact,
not a per-step guard; Gate 99 rule (e) checks the `.gitignore` entry
exists and matches the sidecar path exactly.

## What this step is not

It carries no `token:`/`repository-repo-token` input (D1: always this
same repository, never an adopter-configurable one) and no
`fetch-depth: 0` (a composite action's directory needs only the tip
tree of one commit, not history). It does not replace, move, or widen the
existing `$RUNNER_TEMP/wc-pristine` helper-script/schema snapshot
(research.md D13) — both exist side by side, resolving the same
`github.sha`/`$GITHUB_SHA` by two different mechanisms for two
structurally different needs.
