# Contract: Published Stage Interfaces

The `workflow_call` signature of every published stage. Input/secret names
below are normative; implementation may add inputs but may not remove or
repurpose these without a major version bump (see [versioning.md](versioning.md)).

## Conventions shared by all stages

**Secrets** (declared by every stage that runs an agent or writes to the repo):

| Secret | Required |
|---|---|
| `claude-code-oauth-token` | one of the two Claude credentials (agent stages) |
| `anthropic-api-key` | one of the two Claude credentials (agent stages) |
| `speckit-app-id` | yes — GitHub App identity for pushes/PRs/comments |
| `speckit-app-private-key` | yes |

Credential behavior: see [credentials.md](credentials.md).

**Common inputs**:

| Input | Type | Default | Purpose |
|---|---|---|---|
| `pipeline-repo` | string | the publishing repository | Where the stage checks out its own shared composite actions, at `github.job_workflow_sha` (research D3). Only forks that republish need to set it. |
| `default-branch` | string | `""` = derive | The consuming repository's default branch. When empty, the stage derives it itself (`gh repo view --json defaultBranchRef`) — stages never assume `main` (spec edge case 3). |

**Universal behavior**:
- `on:` is `workflow_call` **only**; stages never read `github.event` — all
  event facts arrive as inputs (research D2).
- Deterministic preflight runs before any agent step: credential invariant +
  spec-kit presence + the stage's preconditions (research D4/D7). Failure stops
  the run with a message naming the missing item and the step that provides it
  (FR-004, FR-009).
- Every agent step declares `--model` and `--max-turns` from inputs/defaults
  (constitution II) and is followed by the metrics-summary step.
- All side effects land in the consuming repository only (FR-005).
- No branch-convention hardcoding: every reference to the consuming
  repository's default branch (checkout refs, PR bases, rebase targets) uses
  the `default-branch` input or its derived value — never a literal `main`
  (spec edge case 3). The `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`
  branch *prefixes* remain part of the shared artifact contract (spec
  assumption 5).
- Chaining is opt-in: `next-workflow`-style inputs default to `""` = no
  dispatch, so any stage runs standalone (FR-002/US2). When set, the stage
  dispatches that workflow *file in the consuming repository* via
  `gh workflow run`, using the chaining payload contract below.
- Per-spec serialization: every stage that checks out and publishes to a
  specification's `spec/NNN-slug` working branch — `rebase`, `plan`, `tasks`
  (both `mode: generate` and `mode: approved`), `implement`, and `finalize` —
  declares the same job-level `concurrency: wing-commander-<spec-dir>` group
  (`cancel-in-progress: false`), so at most one of them ever runs against a
  given specification at a time (specs/013-serialize-rebase-stages/contracts/concurrency-groups.md).

**Wrapper gate obligations** (documented, adopter-owned — constitution V
guidance shipped in docs/adoption.md): maintainer-label entry gate before
intake; commenter is maintainer-or-author and not a bot before clarify;
never pass fork-PR head refs as checkout targets.

**Chaining payload contract**: when a stage dispatches a `next-workflow` /
`self-workflow`, the dispatch target is a *wrapper file in the consuming
repository*, and that wrapper's `workflow_dispatch` signature is therefore
part of this contract. A dispatch-target wrapper MUST declare these
`workflow_dispatch` inputs (snake_case — these are the historical dispatch
names; the wrapper translates them to the stage's kebab-case inputs):

| Dispatch target | Required `workflow_dispatch` inputs |
|---|---|
| implement wrapper (`next-workflow` of tasks; `self-workflow` of implement) | `spec_dir` (string), `issue` (string), `iteration` (string) |
| finalize wrapper (`next-workflow` of implement) | `spec_dir` (string), `issue` (string), `converged` (string) |

docs/adoption.md's wrapper examples MUST show these signatures verbatim.

## reusable-intake.yml

| | |
|---|---|
| Inputs | `issue-number` (number, required); `model` (string, default `claude-opus-4-8`); `max-turns` (number, default `50`) |
| Preconditions | spec-kit present in consumer checkout |
| Behavior | Allocate next feature number (scans `specs/` + open pipeline branches), run `/speckit-specify` against the issue, create `spec-draft/NNN-slug` + draft spec PR to the default branch, write `spec-meta.json`, label issue (`spec:NNN-slug`, `stage:spec`), post clarification questions or ready-for-review comment |
| Outputs | `spec-dir`, `feature-num` |

## reusable-clarify.yml

| | |
|---|---|
| Inputs | `issue-number` (number, required); `comment-id` (number, required); `model` (string, default `claude-opus-4-8`); `max-turns` (number, default `40`) |
| Preconditions | spec-kit present; open `spec-draft/NNN-slug` PR for the issue's `spec:` label |
| Behavior | Fold the answers from the referenced comment into the draft spec PR, confirm on the issue |
| Outputs | none |

## reusable-plan.yml

| | |
|---|---|
| Inputs | `head-ref` (string) **or** `slug` (string) — one required; `merged` (boolean, default `true`); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `80`) |
| Preconditions | `specs/NNN-slug/spec.md` + `spec-meta.json` exist on the default branch; no existing `plan/NNN-slug` branch (duplicate guard) |
| Behavior | Derive+validate slug internally from `head-ref` (`spec-draft/` prefix) or take `slug` directly; create/reuse `spec/NNN-slug`; create lifecycle issue for hand-submitted specs; run `/speckit-plan`; open plan PR → `spec/NNN-slug`; advance `spec-meta.json` to `plan`; flip label |
| Outputs | `spec-branch`, `spec-dir` |

## reusable-tasks.yml

| | |
|---|---|
| Inputs | `mode` (string `generate`\|`approved`, default `generate`); `head-ref` or `slug` (one required); `tasks-review` (string `auto`\|`pr`, default `auto`); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `60`); `next-workflow` (string, default `""`) — wrapper filename to dispatch for implement |
| Preconditions | `generate`: `plan.md` exists; `spec-meta.json.stage == "plan"` (or `stalled` on manual restart). `approved`: `spec-meta.json.stage == "tasks"` and `head-ref` is a `tasks/NNN-slug` branch |
| Behavior | `generate`: run `/speckit-tasks`; `auto` commits tasks.md to the spec branch and (if `next-workflow` set) dispatches implement directly; `pr` opens a `tasks/NNN-slug` PR and stops — no dispatch. `approved` (no agent work): the entry point for a merged tasks PR in `pr` review mode — validates the slug and dispatches `next-workflow` with `spec_dir`, `issue`, `iteration=1`. A `workflow_call` workflow has no triggers of its own, so the **wrapper** owns the `pull_request: closed` (base `spec/**`, head `tasks/*`, merged) trigger and calls this stage with `mode: approved` |
| Outputs | `spec-dir` |

## reusable-implement.yml

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `iteration` (number, required); `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `100`); `max-iterations` (number, default `5`); `self-workflow` (string, default `""`) — wrapper filename for iteration N+1 re-dispatch; `next-workflow` (string, default `""`) — wrapper filename for finalize |
| Preconditions | `tasks.md` exists; `spec/NNN-slug` branch exists; `iteration <= max-iterations` |
| Behavior | One implement ⟲ converge iteration on the spec branch (deterministic convergence check, single tier-up retry on outright failure, stall marking — all internal, as today); converged or capped ⇒ dispatch `next-workflow` (if set) with `converged`; not converged ⇒ dispatch `self-workflow` (if set) with `iteration+1`; empty chaining inputs ⇒ report to issue and stop |
| Outputs | `converged` (boolean) |

## reusable-finalize.yml

| | |
|---|---|
| Inputs | `spec-dir` (string, required); `issue-number` (number, required); `converged` (boolean, required); `summary-model` (string, default `claude-haiku-4-5`); `max-turns` (number, default `20`) |
| Preconditions | `spec/NNN-slug` branch exists with commits ahead of the default branch |
| Behavior | Summarize diff + unchecked/manual tasks; open final PR `spec/NNN-slug` → default branch; comment manual-task list on issue; label `stage:review` |
| Outputs | `pr-number` |

## reusable-cleanup.yml

| | |
|---|---|
| Inputs | `head-ref` (string, required); `base-ref` (string, required); `merged` (boolean, required); `summary-model` (string, default `claude-haiku-4-5`); `max-turns` (number, default `20`) |
| Preconditions | identity-refusal check: derived slug's artifacts exist and self-identify consistently |
| Behavior | Self-select exactly one outcome from the three PR-closure shapes (teardown-done / teardown-rejected / mark-stalled) internally — wrappers pass raw PR facts on any `pull_request: closed` event; every non-matching shape is a no-op |
| Outputs | `outcome` (string) |

## reusable-rebase.yml

The stage the spec calls "auto-rebase" — `rebase` is its canonical published id.

| | |
|---|---|
| Inputs | `model` (string, default `claude-sonnet-5`); `max-turns` (number, default `30`) |
| Preconditions | none (discovers in-flight `spec/*` branches itself; empty discovery is a clean no-op) |
| Behavior | Discover → fan-out per-branch rebase onto the default branch; clean push with lease, agent conflict resolution with deterministic scope check, escalate-once marker on stuck branches — all internal, as today |
| Outputs | none |
