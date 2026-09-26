# Data Model: Composite Resolution in board-loop's Item-Branch Jobs

This feature persists nothing in a new storage layer (research.md D9):
every entity below is either a workflow-file structural shape Gate 99
checks statically, or a fact written to a run's own
`$GITHUB_STEP_SUMMARY`. This document gives each of the spec's Key
Entities a concrete, checkable shape.

## Trusted Copy

The sidecar checkout every covered job establishes.

| Field | Type | Source | Notes |
|---|---|---|---|
| `ref` | string, always `${{ github.sha }}` | the checkout step's own `with.ref` | FR-003 — the commit whose `board-loop.yml` is running; Gate 99 rule (c) fails any other expression or a hardcoded ref |
| `path` | string, always `.wc-pristine-repo` | the checkout step's own `with.path` | research.md D1; must match the `.gitignore` entry Gate 99 rule (e) checks and every rewritten `uses:` prefix |
| `established_before` | ordered list of step names in the same job | job structure | must include every `uses: ./.wc-pristine-repo/...` reference, every `wing-commander-context` call, and every `anthropics/claude-code-action@` step (FR-002); Gate 99 rule (b) |
| `fail_closed` | boolean, must be `true` | absence of `continue-on-error: true` and of a skipping `if:` on the checkout step | FR-006; Gate 99 rule (d) |
| `resolved_commit` | string (a real SHA) | `$(git -C .wc-pristine-repo rev-parse HEAD)`, echoed at runtime | FR-013 — written to `$GITHUB_STEP_SUMMARY`, not stored; equals `ref` unless the checkout itself is broken, in which case the job already failed (FR-006) before this line runs |

## Board-Loop Job (Gate 99's subject)

Every job in `board-loop.yml`, as Gate 99 sees it.

| Field | Type | Notes |
|---|---|---|
| `name` | string | `select`, `resolve-model`, `triage`, `route`, `fix`, `review`, `readiness`, `prove-gate`, `prove` |
| `has_item_checkout` | boolean | true for `fix` (resume path onward), `review`, `readiness` — the pre-existing "item-branch job" set (spec.md Key Entities); informational only, since FR-011 makes the rule apply regardless |
| `composite_refs` | list of `{step_name, uses_path}` | every `uses: ./...` line in the job; Gate 99 rule (a) fails if any `uses_path` starts with `./.github/actions/` rather than `./.wc-pristine-repo/.github/actions/` |
| `sidecar_checkout_present` | boolean | true iff the job contains the canonical `Checkout board-loop's own trusted copy (composites)` step; required whenever `composite_refs` is non-empty (Gate 99 rule (b)) |
| `sidecar_checkout_position` | int (step index) | must be less than the index of every entry in `composite_refs`, every `wing-commander-context` call, and every `anthropics/claude-code-action@` step in the same job |

`resolve-model` is the one job with `composite_refs == []` today
(research.md D3) — it has no `sidecar_checkout_present` requirement unless
a future change adds a composite reference, at which point Gate 99's rule
(b) applies to it exactly as to any other job, with no gate edit.

## Provenance Record (FR-013)

Not a stored entity — a run-observable fact.

| Field | Type | Where it appears | Notes |
|---|---|---|---|
| `job` | string | the run's own job name in the Actions UI | which job's sidecar this line describes |
| `ref` | string | `$GITHUB_STEP_SUMMARY` line, literal `github.sha` value | e.g. `a34fea2...` |
| `resolved_commit` | string | same line | `git -C .wc-pristine-repo rev-parse HEAD`, which must equal `ref` |

## Gate 99 Fixture Set

Validated by `verify-board-loop-composite-provenance.py --self-test`
(research.md D7). Each row is one checked-in mutation of the real
`board-loop.yml`, asserted caught and attributable to its own rule; the
gate also asserts the *unmutated* file is clean before applying any
mutation (Principle VIII: a gate that starts dirty on its own subject is
not proof of anything).

| Mutation | Rule exercised | Expected failure names |
|---|---|---|
| Reintroduce one raw `uses: ./.github/actions/wing-commander-context` | (a) file-wide ban | the job and the offending line |
| Move the sidecar checkout after a composite reference | (b) placement | the job and the out-of-order reference |
| Drop the sidecar checkout from a job with a `.wc-pristine-repo` reference | (b) placement (orphaned reference) | the job and the missing checkout |
| Change the checkout's `ref:` to a literal branch or blank it | (c) ref pin | the job and the bad `ref:` value |
| Add `continue-on-error: true` to the checkout step | (d) fail-closed | the job and the step |
| Remove the `.gitignore` entry for `.wc-pristine-repo` | (e) staging defense | the missing `.gitignore` line |
| Widen rule (a) to admit a second exempted pattern | no-allowlist invariant | that the widened check still catches the original violation |

## Documentation Pointer Map (FR-014)

Not persisted state — the set of files this feature's canonical statement
and pointers touch (contracts/documentation-updates.md gives the exact
text for each row).

| File | Role |
|---|---|
| `.github/workflows/board-loop.yml` (file header) | Canonical statement: what the sidecar is, why, and the one provenance rule (D13) covering both the composite checkout and the pre-existing helper/schema snapshot |
| Each job's sidecar checkout step (8 call sites) | Pointer: "see this file's header" — never repeated prose |
| `.github/actions/wing-commander-context/action.yml` (header) | Pointer: board-loop.yml is not a published stage and resolves composites the same way from its own repository at `github.sha` — see board-loop.yml's header |
| `.github/workflows/lint-workflows.yml` (Gate 98's comment block) | Pointer: the composite half of this same provenance property is Gate 99 |
