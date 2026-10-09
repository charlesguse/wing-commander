# Contract: `auto-release.yml`'s own trigger, gating, and job shape

Status: normative for this feature's implementation. Cross-references
`research.md` (D1–D4, D14) for rationale.

## Triggers

```yaml
on:
  schedule:
    - cron: "9 9 * * *"   # one-line, PR-reviewed knob per FR-002 — not repository-variable-configurable
  workflow_dispatch: {}    # FR-005: on-demand, no inputs needed
```

No `workflow_call` trigger. This file is not a published stage
(research.md D1) — it is not `uses:`-invoked by anything, adopted by
nobody, and carries no `workflow_call.inputs`/`secrets` block.

## Concurrency

```yaml
concurrency:
  group: wing-commander-auto-release
  cancel-in-progress: false
```

At most one attempt in flight at a time (FR-023); a second trigger while
one is running queues rather than racing or cancelling it (research.md
D14).

## Kill switch

Every job in this workflow carries:

```yaml
if: vars.WING_COMMANDER_AUTO_RELEASE_PAUSED != 'true'
```

evaluated at the job level so that a paused repository starts **no** job
at all (FR-006, SC-009) — not a step-level check inside a job that has
already started (research.md D2, the watchdog's own deprecated
stage-side-shim lesson).

## Jobs (names are the load-bearing part of this contract; internal steps
are an implementation-stage decision)

| Job | Purpose | Depends on | Produces |
|---|---|---|---|
| `detect` | Resolve latest release tag and current head (data-model.md "Unreleased head", "Latest release tag"); derive this run's execution mode (specs/054); read the open `auto-release:failed` issue's recorded `**Mode**:` and decide whether this run verifies: on new work, or when that issue records this run's mode (#966); short-circuit to a no-op summary line when neither holds (FR-003, FR-004) | — | `head_sha`, `has-new-work`, `latest-tag`, `mode`, `paused`, `failure-issue`, `failure-issue-mode` (empty \| `container` \| `default-runner` \| `unrecorded` \| `unreadable`), `run-verification` outputs |
| `e2e-pin` | Replace the previous run's `e2e-verify-*` tag with this run's annotated tag on the head under verification, which the test repository's wrappers pin (#928); the only job holding `contents: write` | `detect`, only when `run-verification == 'true'` | `tag`, `failure` outputs |
| `verify-e2e` | Resolve/validate the test repository, reset its default branch, confirm `e2e-pin`'s tag, scaffold, kick off the trivial feature, poll to a terminal state, assert per-stage outputs, emit the verdict (data-model.md "End-to-end verdict") | `detect` and `e2e-pin`, only when `run-verification == 'true'`; still runs when `e2e-pin` failed, so the verdict names that failure | `verdict` (JSON) output |
| `decide-version` | Compute patch-vs-minor and the next version, detect a tag collision (data-model.md "Version decision") | `verify-e2e`, only when `has-new-work == 'true'` (a re-verification of an already-released head cuts nothing) and it succeeded and `verdict.outcome == 'pass'` | `next-version`, `collision` outputs |
| `dispatch-release` | `gh workflow run release.yml` with the computed version, poll that run to a conclusion (research.md D12) | `decide-version`, only when `collision == 'false'` | `release-outcome` (`released` \| `failed`) output |
| `report` | Write the `$GITHUB_STEP_SUMMARY` line for every path; on any `fail-*` outcome, file/update the durable `auto-release:failed` issue (data-model.md "Failure report"); on `released`, or a passing re-verification, close the open one only when its recorded mode is the mode this run verified, or it records none (#966) | `always()`, reads outputs from every prior job that ran | — |

Every job after `detect` that is skipped by its own `if:` (no new work,
verification failed, collision, paused) must still leave a legible reason
in the run's own summary (FR-030) — this is `report`'s job, gated
`if: always() && vars.WING_COMMANDER_AUTO_RELEASE_PAUSED != 'true'` so it
runs on every non-paused path including early no-ops.

## Permissions

```yaml
permissions: {}

jobs:
  dispatch-release:
    permissions:
      actions: write     # required for `gh workflow run release.yml` (research.md D12, Gate 12)
      contents: read
  # other jobs declare only what they individually need (contents: read for detect;
  # no repository-scoped write permission anywhere — the test-repository token in
  # verify-e2e is a separately minted App installation token, not this job's GITHUB_TOKEN)
```

`dispatch-release` uses `GH_TOKEN: ${{ github.token }}`, never the
wing-commander App token (documented incident: `implement.yml`'s own
comment on the App token having no `actions` permission; Gate 12).
