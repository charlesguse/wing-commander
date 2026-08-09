# Pipeline Architecture

How a feature request becomes merged code, stage by stage. All stages are
implemented, and each is published as a reusable `workflow_call` workflow
(`<stage>.yml`) that adopting repositories pin by tag
([docs/adoption.md](adoption.md)); this repository's own `wing-commander-*.yml`
files are thin wrappers calling those same stages by local path.

```
issue ──spec-request label──▶ [1 intake] ──▶ spec PR → main
  │                                              │  human merge
  │◀─ questions/answers ─ [1b clarify]           ▼
  │                            [2 plan] ──▶ spec/NNN branch + plan PR → spec/NNN
  │◀─ status comments                            │  human merge
  │                                              ▼
  │                           [3 tasks] ──▶ tasks.md auto-committed
  │                                              │  dispatch
  │                                              ▼
  │                     [4 implement ⟲ converge] (≤ WING_COMMANDER_MAX_ITERATIONS)
  │                                              │  dispatch
  │                                              ▼
  │◀─ manual tasks report  [5 finalize] ──▶ final PR spec/NNN → main
  │                                              │  human merge
  ▼                                              ▼
issue closed ◀──────────── [6 cleanup] ◀── branches deleted, labels flipped
```

## Foundations

### Published stages & thin wrappers (`specs/010-reusable-pipeline/`)

This section describes the **published contract** layer (constitution VII).

Every stage body lives in a published stage workflow (`<stage>.yml`) whose only trigger is
`workflow_call` — ten of them today. Stage workflows are *required* not to
read `github.event.*` or `vars.*`; every event fact (issue number, head/base
refs, merged flag, comment id) and
every knob (model, max-turns, review mode, iteration cap, chaining targets)
is a declared, typed input with a default matching the constitution's
tiering. The **wrapper** owns the trigger, the security gates, and the
event→input extraction; this repository's eleven `wing-commander-*.yml` wrappers are
the worked example, and adopters write the same shape against a version tag.

**One stage does not meet the rule.** `watchdog.yml` reads `vars.*` in 15
places — branch prefixes, two model overrides, the self-dispatch cap, and a
deprecated pause shim. It went unnoticed because `release.yml`'s Gate 1b
greps a hardcoded eight-file list rather than every published stage, so the
ninth was never examined; the count grew 2 → 9 → 15 across four tagged
releases with the gate passing each time. Constitution VII requires a
deviation like this to carry a registered, machine-checked exception. Neither
the register nor the complete gate exists yet — [issue
#149](https://github.com/charlesguse/wing-commander/issues/149) tracks both,
and until it lands this paragraph *is* the exception record.

**A second, deliberate deviation**: `specs/031-stage-environment-binding`
binds every job in every published stage to a deployment environment
(`environment`/`environment-deployment` `workflow_call` inputs, job-level
`environment:` mapping) — a security gate that, per the rule above, should
live in the wrapper, not the stage. It can't: GitHub rejects
`jobs.<job_id>.environment` outright on a job whose body is `uses: <reusable
workflow>`, and `on.workflow_call.inputs` has no mechanism to accept or
forward it either. There is no wrapper-side syntax to reject in favor of, so
the gate is published-contract surface instead — registered here, not
silently absorbed, per constitution VII's registration requirement.

Mechanics worth knowing:

- **Composite-action self-checkout** (research.md D3): inside a called
  workflow, relative `uses: ./...` resolves against the *caller's* workspace,
  so each stage checks out the pipeline repository itself into
  `.wing-commander-pipeline/` at `github.job_workflow_sha` — the exact commit of the
  running workflow file — and reaches `wing-commander-context`, `wing-commander-preflight`,
  and `wing-commander-metrics-summary` through that path. A version pin therefore
  covers workflow body *and* composites; there is no skew and no release-time
  ref rewriting. Consumer re-checkouts pass `clean: false` so the untracked
  `.wing-commander-pipeline/` survives.
- **Lifecycle gate** (`wing-commander-lifecycle-gate` composite,
  `specs/022-gate-closed-lifecycle/`): a closed lifecycle issue is inert. The
  composite re-fetches the issue's live `state` from the API (`gh issue view
  --json state`, never the stale triggering-event payload) and exposes
  `is-open`. It is the **first billable step** — after the pipeline
  self-checkout, before Preflight — of `clarify.yml`, `intake.yml`,
  `finalize.yml`, and `implement.yml`, and is inserted before the sole write
  step of `tasks.yml`'s `tasks-approved` job. Every subsequent step in those
  jobs carries `if: steps.lifecycle-gate.outputs.is-open == 'true'`, so a
  comment, label, PR-merge, or dispatch against a closed issue — including the
  very comment that closed it — does no checkout-as-bot, commit, push, or PR
  edit, and posts exactly one `kind: info` decline note ("This lifecycle issue
  is closed — no action was taken."). The composite only reads state; it does
  no write and posts the decline note via a sibling `wing-commander-callout`
  step. `plan.yml`/`cleanup.yml`/`claude.yml` are deliberately out of scope
  (PR-merge trigger, teardown mechanism, and `if: false` respectively).
- **Preflight** (`wing-commander-preflight` composite): a deterministic, pre-agent
  fail-fast — at least one Claude credential (`claude-code-oauth-token` or
  `anthropic-api-key`; both passed through, Claude Code's documented
  precedence applies when both are set), spec-kit artifacts present in the
  consumer checkout, stage preconditions met, and a warn-only spec-kit
  version check against the composite's `SPECKIT_SUPPORTED_VERSION` constant.
- **Next-step callouts** (`wing-commander-callout` composite): every
  human-action moment the pipeline reaches posts through one shared action so
  the action-required/informational split is enforced in one place.
  Action-required moments (`kind: action`) render inside a GitHub
  `[!IMPORTANT]` alert box naming what the reader must do (and linking the PR
  or stating timing when relevant); informational moments (`kind: info`)
  render as a plain message with no alert wrapper.
  `contracts/callout-format.md` (specs/019) is the source of truth for the
  template.
- **No branch-name assumptions**: stages take a `default-branch` input or
  derive it (`gh repo view --json defaultBranchRef`); only the five branch
  *prefixes* are contract, and each is configurable-with-default via its
  `WING_COMMANDER_*_PREFIX` repository variable
  (`WING_COMMANDER_SPEC_DRAFT_PREFIX` → `spec-draft/`, `_SPEC_PREFIX` → `spec/`,
  `_PLAN_PREFIX` → `plan/`, `_TASKS_PREFIX` → `tasks/`, `_IMPL_PREFIX` →
  `impl/`), so consumers can rename them while the contract holds.
- **Chaining is opt-in**: `next-workflow`/`self-workflow` inputs name wrapper
  files in the consuming repository to `gh workflow run`; empty (the
  default) means the stage reports to the lifecycle issue and stops, so any
  stage runs standalone.
- **Releases** (`release.yml`): actionlint + interface-invariant greps gate a
  manually dispatched tag `vX.Y.Z`; the floating major tag (`v1`) advances
  only on non-breaking releases, breaking changes start a new major, and
  release notes always carry a Breaking-changes section. This repo's
  local-path wrappers dogfood unreleased head, so interface breakage
  surfaces here before any tag moves.

### Identity & chaining: the wing-commander-bot App
Everything the pipeline does to the repo (push, PR, label, comment) uses a
GitHub App installation token minted per-job by `.github/actions/wing-commander-context`.
Reasons:
- `GITHUB_TOKEN` events **don't trigger workflows** (documented exceptions:
  `workflow_dispatch` / `repository_dispatch`) — the pipeline would halt after
  one stage.
- Filtering `github.actor` on `<app-slug>[bot]` gives loop protection.
- No PAT anywhere (a PAT in an AI-driven workflow is an exfiltration target).

Where a stage has no natural GitHub event (tasks → implement, iteration N → N+1,
implement → finalize), chaining is explicit via `gh workflow run`
(`workflow_dispatch`), which works regardless of token type.

### State model
- **`specs/NNN-slug/spec-meta.json`** — durable source of truth:
  `{issue, spec_dir, feature_num, stage, iteration, spec_branch}`.
- **Branches** (routing keys for PR-event triggers; each prefix is
  configurable-with-default via its `WING_COMMANDER_*_PREFIX` repository
  variable, defaults shown):
  - `<spec-draft-prefix>NNN-slug` (default `spec-draft/`) — draft spec PR head
    (intake → main)
  - `<spec-prefix>NNN-slug` (default `spec/`) — long-lived per-spec integration
    branch (concurrent specs)
  - `<plan-prefix>NNN-slug` (default `plan/`), `<impl-prefix>NNN-slug-iterN`
    (default `impl/`) — stage work branches → spec branch
- **Labels** on the lifecycle issue: `spec:NNN-slug` + one `stage:*` label.
- **spec-kit targeting**: every agent step sets
  `SPECIFY_FEATURE_DIRECTORY=specs/NNN-slug` (spec-kit ≥0.12 resolves the active
  feature from this env var or `.specify/feature.json`, never from branch names),
  so concurrent specs can't cross-contaminate.

### Concurrency
Each stage job uses `concurrency: wing-commander-<spec key>` — one spec's stages
serialize, different specs run in parallel. Intake serializes globally
(`wing-commander-intake`) so feature numbers can't collide.

### Model tiering (constitution II)
| Work | Model |
|---|---|
| Triage, diff summaries, labels | `claude-haiku-4-5` |
| Watchdog diagnosis | `claude-opus-5` (evidence adjudication under a strict schema — not the triage tier; see issue #124) |
| specify / clarify | `claude-opus-4-8` (constitution v1.1.0: spec quality is bought up front) |
| plan / tasks | `claude-sonnet-5` |
| implement / converge | stage `model` input (default `claude-sonnet-5`); this repo's wrapper wires `vars.WING_COMMANDER_IMPLEMENT_MODEL` and the `model:opus` label opt-in into it |

Every agent step declares `--model` and `--max-turns`. Each is followed by a
deterministic `.github/actions/wing-commander-metrics-summary` step that reads the
run's own execution transcript and appends a metrics block (model, turns used
against budget, duration, tokens, cost, with an ≥80% turn-budget warning) to
that run's `$GITHUB_STEP_SUMMARY` — pure read, no agent, never fails the stage
(`specs/009-agent-metrics/`).

**What a "turn" is here**, because the transcript offers two numbers and only
one of them is the budget's:

- `--max-turns` caps **main-loop model turns** — distinct assistant API
  responses with no `parent_tool_use_id`. Two consequences follow. A single
  response streamed across several transcript records is *one* turn (counting
  records inflates by ~1.6x), and **subagent turns are free**: Task-tool
  subagents are inlined into the same transcript but spend no parent budget,
  so a stage that delegates can do far more work per budget than one that does
  not.
- `.num_turns` on the result record is a larger, differently-defined total.
  Measured against this repository's own history it runs 1.0x-2.3x above the
  capped counter, always upward.

The metrics action counts the former and reports subagent turns separately;
until 2026-08-09 it rendered the latter, which is why job summaries carried
lines like "198 / 100 turns (198%)" for runs that used 87 of 100 and were
never at risk. `.github/scripts/verify-metrics-turn-accounting.py`
(lint-workflows gate 11) holds that distinction to fixtures.

**Bedrock pass-through** (`specs/016-bedrock-support/`): the per-stage
`use-bedrock` input changes only which backend serves these already-tiered
`model` inputs — the consumer supplies Bedrock-compatible identifiers directly
through the same `model` inputs, with no new model-mapping mechanism and no
change to the tiering above.

### Security (constitution V)
- Pipeline entry = maintainer-applied `spec-request` label.
- Comment triggers: commenter must be OWNER/MEMBER/COLLABORATOR **or** the
  original issue author; `Bot`-type users never trigger.
- Issue/comment bodies are never interpolated into prompts or shell — they are
  fetched by the agent (`gh issue view`) or staged into files via env-var
  indirection, and framed as untrusted data.
- Web tools disabled in all issue/comment-driven stages; per-stage least-privilege
  `--allowedTools`. Each stage ships those default allow/deny lists inline, but a
  consumer can extend or replace them per stage without touching the pipeline:
  `extra-allowed-tools`/`extra-disallowed-tools` *append* to the defaults
  (union), while `allowed-tools-override`/`disallowed-tools-override` *replace* a
  default list wholesale — the two are per-direction, mutually exclusive choices,
  composed by the `wing-commander-tool-args` composite action before the agent
  step runs (`specs/026-configurable-tool-lists/`). The per-stage default lists
  are catalogued in
  [stage-interfaces.md](../specs/010-reusable-pipeline/contracts/stage-interfaces.md#per-stage-default-tool-lists).
- Only trusted refs are checked out (main, repo-local `spec*/` branches) — never
  fork PR heads.
- Humans merge every PR into main. The bot cannot approve or merge.

---

## Stage 1 / 1b — Intake & clarify (`intake.yml`, `clarify.yml`)

Specified in [`specs/001-spec-intake/`](../specs/001-spec-intake/spec.md),
[`specs/004-clarify-on-pr/`](../specs/004-clarify-on-pr/spec.md) and
[`specs/032-structured-clarification-gate/`](../specs/032-structured-clarification-gate/spec.md).

**Trigger**: maintainer applies the `spec-request` label to an issue (intake);
a reply on that issue from a maintainer or the original requester, while it
carries a `spec:` label plus `stage:spec` or `stage:clarify` (clarify).

Intake runs the specify skill, opens the spec PR, and then makes one
either/or decision: post **"Answer the open clarification questions"** (the
requester replies, and 1b picks the reply up) or **"Review the spec PR"**.
Getting that split wrong has been this pipeline's most repeated bug class —
a marker grep that could never match (#159), and a guard re-added to only one
arm of the split, which let intake ask for a reply on an issue whose labels
made 1b's trigger unable to fire. Both were invisible to the workflow linter,
because both are valid YAML and valid bash.

The decision, every gate on it, and what each gate buys are drawn out in
**[contracts/decision-points.md § Flow: how intake decides what to post](../specs/032-structured-clarification-gate/contracts/decision-points.md#flow-how-intake-decides-what-to-post)**.
The two rules worth carrying in your head:

- Both callouts key off a single output derived from one read of the agent's
  schema-validated result — never two independently computed conditions. That
  is the structural fix for #159.
- **A callout that asks for a reply must only fire where a reply can be
  acted on.** `wing-commander-2-clarify.yml` needs a `spec:` label plus
  `stage:spec|clarify`; the agent's `specified` discriminator is what keeps
  the questionnaire off the "no discernible feature request" path, where none
  of those labels exist.

`.github/scripts/verify-clarification-gating.py` (lint-workflows Gate 8)
executes the shipped decision shell against synthetic agent transcripts and
asserts which callouts fire on every path — and, separately, that the run
goes red when the cross-check vetoes. Blocking both callouts without failing
the run is the worse half of that defect: the requester sees only the
run-started comment while a marker-carrying spec PR sits in the review queue.

`.github/scripts/verify-sentinel-collector.py` (lint-workflows Gate 9) does
the same for the other end of the loop — watchdog.yml's `Collect: step
summaries`, which is what turns the sentinels these stages emit into signals
the watchdog can reason about.

Both import `.github/scripts/wc_shell_harness.py`, which holds the mechanics
of running an extracted `run:` block the way the runner would (see its
docstring for the three ways that goes wrong off ubuntu).

---

## Stage 2 — Plan (`plan.yml`, wrapper `wing-commander-3-plan.yml`)

Specified in [`specs/002-plan-stage/`](../specs/002-plan-stage/spec.md).

**Trigger**: `pull_request: closed` touching `specs/**`, gated on
`merged == true && base == main && startsWith(head.ref, 'spec-draft/')` (the
head-prefix guard prevents unrelated PRs touching `specs/**` from
false-triggering); plus `workflow_dispatch` (input: `slug`) for manual restarts.

**Flow**:
1. Resolve + validate the slug from the merged head branch (or dispatch input);
   refuse to guess if `spec.md` / `spec-meta.json` are missing (FR-010).
2. Create `spec/NNN-slug` from `main` (plain git push with the App token),
   reusing it if it exists; if `plan/NNN-slug` already exists, stop — that's a
   duplicate planning attempt (FR-009).
3. Hand-submitted specs (`"issue": null`) get a lifecycle issue created and
   labeled before anything is reported (FR-007).
4. Resolve the review mode from `vars.WING_COMMANDER_PLAN_REVIEW` (Gate 3):
   unset or `pr` → `pr`; `auto` → `auto`; any other non-empty value fails open
   to `pr` (never to `auto`) and is surfaced — `::warning::` annotation, a
   step-summary line, and a note on the "planning started" lifecycle-issue
   comment naming the invalid value (spec `014-configurable-gates`, FR-008).
   This differs from Stage 3's `WING_COMMANDER_TASKS_REVIEW` resolution
   (below), which silently falls open to `auto` with no invalid-value
   surfacing — the two gates are configured and resolved independently
   (FR-003).
5. claude-code-action on the spec branch, `SPECIFY_FEATURE_DIRECTORY` set: run
   `/speckit-plan` (proceeding despite unresolved markers, FR-011), update
   spec-meta.json (`stage: plan`), comment the summary on the issue. Then,
   gated on the resolved mode:
   - `pr` (default): commit plan artifacts to `plan/NNN-slug`, open a PR
     **targeting `spec/NNN-slug`**; a deterministic post-step verifies the
     plan PR exists, then flips the issue label to `stage:plan`.
   - `auto`: commit plan artifacts directly to `spec/NNN-slug` — no
     `plan/NNN-slug` branch, no PR; a deterministic step verifies `plan.md`
     is on the spec branch and `spec-meta.json.stage == "plan"`, flips the
     issue label to `stage:plan`, then (if `next-workflow` is configured)
     runs `gh workflow run <next-workflow> -f slug=…` to dispatch the tasks
     stage automatically — zero human action on the plan artifact.
6. `pr` mode only: a plan PR closed **unmerged** marks the spec stalled
   (`stage:stalled` label, spec-meta.json `stage: "stalled"`, issue comment);
   restart is manual — delete `plan/NNN-slug` and dispatch the workflow
   (FR-012). `auto` mode never opens a PR that could be closed unmerged, so
   this stalled path does not apply to it.

## Stage 3 — Tasks (`tasks.yml`, wrapper `wing-commander-4-tasks.yml`)

Specified in [`specs/003-tasks-stage/`](../specs/003-tasks-stage/spec.md).

**Trigger**: `pull_request: closed` with base `spec/**`, head `plan/*`, merged;
plus `workflow_dispatch` (input: `slug`) for manual restarts (same restart
idiom as the plan stage).

**Flow**: resolve + validate the slug from the head branch (refuse to guess,
FR-012); idempotency-guard on `spec-meta.json` `stage == "plan"` (duplicate
notifications no-op, FR-011; a manual dispatch may also proceed from
`"stalled"` — that is the restart path). Then run `/speckit-tasks`
(`claude-sonnet-5`, `SPECIFY_FEATURE_DIRECTORY` set), gated by
`vars.WING_COMMANDER_TASKS_REVIEW`:
- `auto` (default, any other value falls open to it): commit `tasks.md` +
  `spec-meta.json` (`stage: "tasks"`) directly to `spec/NNN-slug`; post a task
  summary to the lifecycle issue; flip its label to `stage:tasks`; then a
  deterministic step runs `gh workflow run wing-commander-5-implement.yml
  -f spec_dir=… -f issue=… -f iteration=1`.
- `pr`: open a `tasks/NNN-slug` PR carrying the same changes; a
  `tasks-approved` job in this same workflow does the dispatch when that PR
  merges. A tasks PR closed **unmerged** marks the spec stalled
  (`stage:stalled` label, `spec-meta.json` `stage: "stalled"`, issue comment);
  restart is manual — delete `tasks/NNN-slug` and dispatch the workflow.

## Stage 4 — Implement ⟲ converge (`implement.yml`, wrapper `wing-commander-5-implement.yml`)

Implemented via `specs/005-implement-converge/` (issue #15); the design below
is what the implementation follows.

**Trigger**: `workflow_dispatch` (`spec_dir`, `issue`, `iteration`). Looping is
**re-dispatch, not an in-job loop**: each iteration is a separate auditable run,
stays under the 6-hour job cap, and the cap check is trivial (`iteration <=
vars.WING_COMMANDER_MAX_ITERATIONS`).

**Design**:
1. **Implement**: checkout `spec/NNN-slug`; `/speckit-implement` with
   `--model vars.WING_COMMANDER_IMPLEMENT_MODEL` (or Opus if the lifecycle issue has
   `model:opus`); commits pushed to the spec branch as task phases complete;
   generous `--max-turns`.
2. **Converge**: `/speckit-converge`. Its contract is append-only: gaps ⇒ a new
   `## Phase N: Convergence` section appended to tasks.md (committed with a
   `converge:` prefix); converged ⇒ tasks.md byte-identical + "✅ Converged"
   report. So the loop condition is machine-checkable — the implementation
   realizes it as a deterministic commit-range walk (a `converge:`-prefixed
   commit touching tasks.md landed this cycle ⇒ not converged; none ⇒
   converged), since implement's own checkbox edits to tasks.md make a raw
   working-tree diff ambiguous across the job boundary
   (`specs/005-implement-converge/research.md`).
3. On hitting the iteration cap: post the remaining tasks + final converge
   report to the lifecycle issue and dispatch finalize with `converged=false`.
4. Post a brief progress comment (`claude-haiku-4-5` summary) each iteration.
5. **Failure ≠ non-convergence** (FR-013): an outright pass failure (step
   fails, or `spec-meta.json` didn't advance as instructed) auto-retries the
   same iteration once, one model tier up (`claude-sonnet-5` →
   `claude-opus-4-8`). A failed retry — or a failure already on the top
   tier — marks the spec `stalled` (label, `spec-meta.json`, issue comment);
   restart is manual: re-dispatch the workflow with the same iteration.

## Stage 5 — Finalize (`finalize.yml`, wrapper `wing-commander-6-finalize.yml` — see `specs/006-finalize-stage/`)

**Trigger**: `workflow_dispatch` (`spec_dir`, `issue`, `converged`).

**Design**:
1. Haiku step summarizes `git diff main...spec/NNN-slug` and extracts unchecked /
   manual items from tasks.md (structured output via `--json-schema`).
2. Plain `gh pr create`: `spec/NNN-slug → main`, body = what changed, how to see
   it (diff link, key files), remaining manual tasks, lifecycle issue link.
3. Comment the same manual-task list on the lifecycle issue; label `stage:review`.

## Stage 6 — Cleanup (`cleanup.yml`, wrapper `wing-commander-7-cleanup.yml` — see `specs/007-cleanup-stage/`)

**Trigger**: `pull_request: closed`, repo-wide — self-selects one of three
outcomes from the event payload alone (head ref prefix + base ref + `merged`),
never guessed. Every other closed-PR shape is a deliberate no-op.

**Design** — three independently-gated jobs, exactly one of which runs per
closed PR:
- `teardown-done` — final PR (`spec/NNN-slug → main`) **merged**: delete the
  spec-draft, spec, plan, tasks, and any impl `*-iterN` branches for that spec
  (each identified by its configurable-with-default prefix — defaults
  `spec-draft/`, `spec/`, `plan/`, `tasks/`, `impl/`); close the lifecycle
  issue (atomically, with a
  Haiku-written completion summary); flip its label to `stage:done`.
- `teardown-rejected` — draft PR (`spec-draft/NNN-slug → main`) **closed
  unmerged**: delete `spec-draft/NNN-slug`; remove the `stage:*`/`spec:*`
  labels; comment that the spec was rejected; leave the issue **open** so
  the requester can revise and re-enter the pipeline.
- `mark-stalled` — final PR closed unmerged (built work rejected), **or** a
  non-final plan/tasks/impl pull request (heads matching the
  configurable-with-default `plan/`, `tasks/`, `impl/` prefixes) into
  `spec/NNN-slug`
  closed unmerged: commit `spec-meta.json`'s `stage: "stalled"` directly onto
  the still-intact `spec/NNN-slug`; flip the label to `stage:stalled`;
  comment a rejection notice with a manual full-teardown runbook. No branch
  is deleted on this path — everything is preserved for revival. This job is
  the sole owner of "non-final pipeline PR closed unmerged"; the plan and
  tasks stages no longer run their own `stalled` jobs.

Every job runs an identity-refusal step first (derive the slug from the
event payload, validate spec artifacts exist and self-identify consistently)
and reports failures via a pull-request comment, never a lifecycle-issue
comment, since the issue can't yet be trusted to be the right one. Every
outcome's own target state doubles as its idempotency check — no separate
"already processed" marker exists.

## Rebase (`rebase.yml`, wrapper `wing-commander-rebase.yml`)

**Trigger**: `push` to main (skipping `*[bot]` actors) redispatches through
`workflow_dispatch` — a `claude-code-action` step cannot run under `push`
itself, so the wrapper's `redispatch` job fires a lightweight
`gh workflow run` instead of calling the stage directly; the nightly
schedule and manual `workflow_dispatch` reach the stage immediately, with no
redispatch hop.

`lint-workflows.yml` gate 6 keeps that property from regressing: it walks
every wrapper's declared events through the local `uses:` call graph and
fails the PR if an event the agent does not support can reach a
`claude-code-action` step. The unsupported-event failure surfaces *at the
agent step of a real conflict*, long after merge, so nothing else in CI
sees it. Because a detector on a healthy fleet prints the same "0
failure(s)" whether or not it works,
`.github/scripts/verify-gate-6.py` runs the shipped gate — extracted from
`lint-workflows.yml`, not copied — against synthetic trees carrying known
defects and asserts both the verdict and the error text.

**Design**: a `discover` job selects every in-flight `spec/NNN-slug` branch
(reading each branch's *own* `spec-meta.json` tip, skipping `stalled` and
unidentifiable ones), then fans out one isolated `rebase` matrix job per
branch. Each runs `git rebase origin/main`; clean ⇒ `push --force-with-lease`
(a rejected lease means the branch moved meanwhile — skip silently, retry next
run); conflicts ⇒ claude-code-action (`--model claude-sonnet-5`, prompt scoped
to resolving the in-progress rebase without unrelated edits, verified by a
deterministic per-commit file-scope check before publish); still stuck ⇒ abort
the rebase (branch left byte-for-byte untouched) and comment on the lifecycle
issue for human help. The escalation comment carries a
`<!-- wing-commander-rebase: blocked branch-sha=… main-sha=… -->` marker plus a
`rebase:blocked` label; `discover` reads that marker to skip a branch whose
`(branch, main)` pair hasn't changed since it was reported blocked, so a stall
is only escalated once until either side moves (a subsequent success removes
the label).

## Stage 9 — Watchdog (`watchdog.yml`, wrapper `wing-commander-8-watchdog.yml`)

**Trigger**: `workflow_run: [completed]` across the eight other stage
wrappers, plus manual `workflow_dispatch` with a `run-id` to re-inspect any
past run. The thin wrapper only resolves the inspected run's identity
(`run-id`/`run-name`); every job below lives in the reusable `watchdog.yml`.

Self-inspection (FR-021) lives in a **second wrapper**,
`wing-commander-8b-watchdog-self.yml`, which listens to stage 8. It cannot be
folded into stage 8: GitHub rejects any workflow that names itself under
`workflow_run.workflows` — *"failed to parse workflow: Workflow '<name>'
cannot listen to itself"* — and an unparseable workflow is never registered,
so the attempt takes the whole stage offline instead of adding
self-inspection. Recursion terminates by construction (8 → 8b, and nothing
listens to 8b).

8b is **deterministic** — it does not call `watchdog.yml`. It originally did,
but an agent inspecting an agent compounds error rates (an audit found half
of its runs elevating collector self-matches into false findings, one
disproved by the target's own turn count), and "did the
watchdog run do its job" needs no judgment. 8b runs
`.github/scripts/verify-watchdog-run.sh` against the completed stage-8 run:
conclusion is success; runtime sits inside a band derived from the workflow's
own successful history (catches instant agent deaths and multi-minute
stalls); the conditional reporter steps that encode agent-crash /
could-not-inspect / internal-failure truths all read `skipped` (the agent
step itself always looks green in the API — `continue-on-error` reports the
post-rescue conclusion); and the diagnose execution log parses without
`is_error` or known fabrication markers. On any failure 8b turns red and
files (or appends to) a deduplicated `pipeline-defect` issue. The chain can
be exercised on demand — including its red path — via the manual
`wing-commander-watchdog-test.yml` (`inject-failure: true` dispatches stage 8
at an unresolvable run-id and asserts red propagates).

Two constraints the wrappers must hold, both enforced by
`lint-workflows.yml` (gates 1–3):
- Every name in `workflow_run.workflows` must match another workflow's
  `name:` **exactly**. A name matching nothing is not an error to GitHub —
  just a trigger that silently never fires.
- The calling job's `permissions:` must be a superset of `watchdog.yml`'s
  workflow-level grant (notably `actions: read`). GitHub validates this
  against every job in the called workflow at startup and kills the run with
  zero jobs if the caller grants less.

**Design** — four sequential jobs, `collect → diagnose → triage → act`:
- `collect` — deterministic evidence gathering only (no agent). Five FR-006
  sources — execution-output denied-tool counts, branch drift (zero pushed
  commits on a push-expected stage), `spec-meta.json` stage vs. expected,
  step-summary sentinels, and check-run annotations — merge into one
  normalized `signals.json`.

  The denied-tool collector has two paths. The **authoritative** one reads
  the terminal result record's `permission_denials`, whose elements are one
  denial each — `{tool_name, tool_use_id, tool_input:{command, …}}` — and
  groups them by `tool_name`, carrying up to five distinct denied commands
  as `denied-commands` so a Finding can name what was refused. (Spec 022
  believed this field did not exist and guessed its shape as `{tool, count}`;
  both halves were wrong, and because this is the branch actually taken,
  every `denied-tool` finding filed before PR #137 carried
  `{tool: null, denials: null}`.) The **fallback** log scan runs only when no
  result record carries the field: it requires a `tool_result` to be both
  `is_error` *and* to carry permission-denial text, because `is_error` alone
  is set for any failing call — an `actionlint` exit 1 counted as a denial
  and inflated 8 real denials into 20 on a live artifact. It records each
  denial's array position under `record-index`, not `turn` (spec 022,
  FR-008/FR-010: a raw SDK-message-array position that can exceed the run's
  own `num_turns` and must never be presented as a conversation turn).

  `.github/scripts/verify-denied-tool-collector.sh` holds both paths to
  fixtures — including one run described both ways, where the two paths must
  agree on the per-tool counts — and `lint-workflows.yml` gate 5 runs it on
  every PR *and* diffs its copy of the filter against watchdog.yml's. Both
  halves are load-bearing: the previous keep-in-sync-by-comment arrangement
  failed silently the first time the collector changed, and because no
  fixture exercised the authoritative path, the check stayed green while
  verifying a filter that no longer shipped.

  **A collector stays silent when the run was never in a position to cause
  the condition.** Both run-attribution guards were added after the watchdog
  filed confident findings against runs that had done nothing wrong, and both
  are deterministic on purpose — the condition is fully settled by the run's
  own metadata, so it is decided here rather than left for the agent to
  reason around:

  - `branch-drift` and `spec-meta` emit nothing when the inspected run's
    conclusion is `skipped` or `cancelled`. It executed nothing, so it owes
    no commits and no stage transition. A `plan` run correctly skipped for a
    stalled spec was reported as a stage-mismatch defect — issue #125.
  - `branch-drift` additionally emits nothing when the run's head branch is
    not the branch that stage pushes to. `plan` and `tasks` are
    `pull_request`-triggered, so they report the *draft* branch as head while
    committing to the persistent spec branch; counting commits on the head
    branch measures a branch the stage never promised to touch, and zero is
    the correct answer. Issue #112: a run was filed as `lost-progress`
    against `spec-draft/022-…` while that same run pushed `e97b9b6` to
    `spec/022-…` inside its own measurement window.

  Best-effort spec-slug/lifecycle-issue
  resolution: a run that can't be tied to a spec (e.g. a `main`-based
  cleanup) is still inspected and reported against its own run URL. Only if
  *every* collector errors outright does it flip `evidence-available: false`
  → "could not inspect this run" (FR-005); an empty-but-successful signal set
  still proceeds to `diagnose`.
- `diagnose` — one `claude-opus-5`, read-only, structured-output step
  (no write tools, no `git`/`gh` write access) turning signals into zero or
  more Findings. `signals.json` and anything read is framed as untrusted
  data, never instructions (FR-023). Zero Findings ⇒ "passed inspection"
  (FR-004) and nothing is filed.

  A Finding's `class` is half the dedup fingerprint, so it is **not** free
  text. The vocabulary lives in GitHub labels (`🐕 · <type>`), is queried at
  run time and compiled into the structured-output schema as an enum the
  model cannot step outside; `signalId` is likewise enum-constrained to the
  ids this run actually emitted, so citing evidence is selection from a fixed
  list rather than free-text authorship. Asking the prompt for stable names
  was tried first and did not hold — one rebase-discover defect arrived as
  `missing-spec-metadata`, `missing-spec-artifact` and
  `spec-excluded-missing-meta` across three runs (#118, #120, #122). A
  genuinely novel type goes through `"__new__"` plus a `proposedClass`, which
  a deterministic step (never the agent) kebab-cases and registers as a
  label, so the vocabulary self-heals after one occurrence and a new problem
  type needs a label rather than a code change. Keeping the registry in
  labels also makes the classes usable as issue triage facets.
- `triage` — one matrix entry per Finding: coexistence-suppression check
  (a Finding already handled by `implement.yml`'s stalled job or
  `cleanup.yml`'s `mark-stalled` is reported, not re-acted, FR-024), the
  dedup fingerprint, `gh search issues` dedup over the marker
  (`--state all`), an optional `claude-sonnet-5` propose-fix step scoped to
  `.github/**`/`docs/**` for known-remediable classes, and the deterministic
  **rung gate**.

  The fingerprint is `sha256(class + "|signals:" + <the sorted ids of the
  collector signals the Finding cites>)` whenever the Finding cites signals
  this run actually emitted — which makes it derivable from deterministic
  collector output rather than from model prose. It was originally hashed
  over the model's own `normalizedFacts`, and FR-016 asks for a *stable*
  fingerprint without requiring a *deterministic* one: every occurrence of a
  recurring defect drew a fresh hash, and 9 of the watchdog's first 19 issues
  were duplicates (#118). Four distinct drift axes were found and closed in
  turn before the basis moved to signals outright — an unconstrained key set,
  keys that did not discriminate, unnormalized values (`spec/012-x` vs
  `012-x`), and one identity arriving under a different key (`spec` vs
  `branch`). Two `claude-opus-5` runs over the *identical* finding emitted
  `{"actual","expected"}` and `{"actual","expected","stage","workflow"}` —
  both legal under the schema, both different hashes.

  The `normalizedFacts` fallback survives for Findings that cite no usable
  signal, and still carries those lessons: it projects to the minimum
  discriminating key set per class, lowercases, strips known branch prefixes,
  reduces `file` to its basename, and folds `spec` into `branch`. Every extra
  key is drift surface rather than precision. Both the fallback itself and an
  unrecognized class within it emit `::warning::`, because degraded dedup
  should be visible rather than quietly wrong.
- `act` — one matrix entry per non-suppressed Finding: executes exactly what
  the rung gate selected and always appends a per-Finding report to the
  lifecycle issue (FR-022).
- `report-unhandled-failure` — `needs: [collect, diagnose, triage, act]`,
  `if: always()` (specs/020-fix-watchdog). No-ops when every job above
  succeeded or was cleanly skipped; otherwise independently re-resolves a
  GitHub App token and the lifecycle issue (never trusting `collect`'s
  outputs, since `collect` may be the job that failed) and posts "could not
  inspect this run: the `<job>` job ended `<result>` unexpectedly" — to the
  lifecycle issue if one resolves, else the run summary. The structural
  safety net that makes a hard job failure in any of the four jobs above
  still end in a truthful verdict instead of silence, rather than the bare
  red X with no verdict anywhere that issue #96 reported.

**The triage ladder** (no LLM judgment ever gates an autonomous write —
FR-011's crisp, testable rule lives in deterministic bash/jq):
- **rung 1** — a fix diff that clears all three FR-011 guardrail conditions
  (allowlisted change-class, allowlisted paths, changed lines
  `<= min(class.maxDiffLines, config.maxDiffLines)`) opens a PR to the
  default branch with no prior pipeline-defect issue. A human still merges
  (constitution V); "autonomous" is the diagnosis speed, not the merge.
- **rung 2** — a fix diff that fails any guardrail condition: create/find/
  reopen the pipeline-defect issue and open a PR referencing it with
  `Refs #N` (never an auto-closing keyword).
- **rung 3** — no fix attempted and no dedup match: file a new pipeline-defect
  issue carrying the fingerprint marker.
- **dedup-only** — no fix, but an existing issue matches the fingerprint:
  comment fresh evidence (open) or reopen + comment (closed); file nothing
  new. More than one match is a data-integrity finding, reported for a human.

**Guardrail/pause/self-dispatch knobs** — `.specify/memory/watchdog-guardrails.json`
(consuming-repo-owned, read-only from the watchdog) defines the rung-1
change-class allowlist and line caps; a missing file or class simply fails
rung-1 eligibility, never invents a default. There are two operator switches.
`vars.WING_COMMANDER_WATCHDOG_PAUSED` (`true` ⇒ no watchdog job starts at all)
is read **wrapper-side**, by `wing-commander-8-watchdog.yml` and
`wing-commander-8b-watchdog-self.yml`. It was originally read only
stage-side, in `act`'s write-suppression gate, which suppressed writes while
still running collect, diagnose, and triage — so a "paused" watchdog kept
paying for the diagnose and propose-fix agents and threw the verdict away.
Gating the trigger is both cheaper and what "paused" plainly means; adopters
gate their own wrappers the same way (constitution VII: the wrapper owns
triggers, gates, and `vars.*`). The stage-side read is retained as a
**deprecated compatibility shim** so that removing it does not silently
re-enable autonomous writes for an adopter who set the variable and gates
nothing; it is scheduled for removal in the watchdog rework's next major,
alongside the stage's other `vars.*` reads (#149). Gating the 8b verifier is
not optional — with stage 8's jobs
skipped its run still completes with conclusion `skipped`, and
`verify-watchdog-run.sh` fails any conclusion that is not `success`, so an
ungated 8b would file a pipeline-defect issue per paused run.
`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`) remains
stage-side in `act`; the cap counts the consecutive `workflow_run`-sourced
self-inspection chain and, once reached, suppresses all writes so an
unattended watchdog-inspects-watchdog loop is bounded (FR-018). (Since 8b
went deterministic the agentic self-inspection path only arises from a
manual stage-8 dispatch at a watchdog run; the cap remains as its bound.) Detection,
fingerprinting, dedup, and reporting are identical whether the inspected run
is a watchdog run or any other stage (FR-021) — the self-dispatch-depth count
is the only place the stage looks at its own name.

**Triaging a watchdog-filed issue.** Treat one as a lead, not a verdict.
Across the watchdog's first ~200 runs it filed 19 issues, which reduced to 10
distinct findings: 5 were false positives, 3 correctly identified a
deliberately injected test failure, and 2 were genuine unknown problems. Both
genuine ones came from a deterministic component (the 8b verify script and a
collector signal). Every false positive was a bad collector signal faithfully
reported by `diagnose`, which sees only `signals.json` and cannot check a
signal against the world — so the collectors, not the agent, are where a
suspect finding is usually resolved. In rough order of cost:

1. **Open the inspected run before reading the issue's argument.** All five
   false positives were internally coherent and cited real evidence.
2. **Check the run's conclusion.** `skipped` or `cancelled` means it executed
   nothing. `branch-drift` and `spec-meta` now guard this; other collectors
   do not.
3. **Check which branch the run pushed to versus which one was measured** —
   `git log --since` on the spec branch inside the run's own time window.
   Two separate false positives were exactly this.
4. **Check whether the cited facts are non-empty.** `{tool: null}`-shaped
   facts mean a collector is reading a field that does not exist, which is a
   defect in the watchdog rather than in the inspected run.
5. **Search for the fingerprint marker before filing anything by hand.** The
   watchdog files its own duplicates, and a hand-written report alongside
   them splits one defect's history across two issues.

Rungs 1 and 2 have never fired in production; every finding so far has landed
on rung 3, the report-only one. That is the intended conservative default,
not evidence that rungs 1 and 2 work — they have not been exercised.

## Auto-Update Spec Kit (`auto-update-spec-kit.yml`, wrapper `wing-commander-auto-update-spec-kit.yml`)

**Trigger**: daily `schedule` (`cron: "13 7 * * *"`) + manual
`workflow_dispatch` (the routine adoption path), plus `pull_request:
[closed]` and `issue_comment: [created]` (the self-managing lifecycle-issue
and maintainer-reply paths). The wrapper resolves a single typed `trigger`
input (`scheduled`/`dispatch`/`pr-merged`/`comment-reply`) from
`github.event_name` and checks the `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_PAUSED`
kill-switch in its own job-level `if:` (constitution VII); the stage never
reads `github.event.*`/`vars.*`.

**Design** — a seven-job upgrade chain plus two entry-point jobs, all under
one `concurrency: wing-commander-auto-update-spec-kit` group so a scheduled
run, a manual dispatch, and a comment-reply resume can never race (FR-015 —
one active upgrade cycle at a time):

- `health-check` (scheduled/dispatch only) re-verifies the **currently
  pinned** version first — its failure short-circuits the chain straight to
  `act`'s rollback branch, which is what makes an "already adopted and later
  found broken" regression discoverable at all (FR-006).
- `detect` deterministically reads `repos/github/spec-kit/releases`
  (`prerelease == false`, semver-sorted), compares against
  `.specify/init-options.json`'s `speckit_version`, and classifies the delta
  as `patch`/`minor`/`major`. Not newer ⇒ no issue, no PR (SC-007).
- `settle` runs a **settle-window** state machine: a freshly detected
  candidate is never adopted the same day it appears — it must be observed
  unchanged for `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_STABILIZATION_CHECKS`
  (default `1`) **consecutive daily checks** (no fixed calendar window,
  FR-002). State lives in one open lifecycle issue's body marker
  (`<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=N -->`),
  found via a quoted-phrase `gh search issues` (the same tokenization gotcha
  `watchdog.yml` documents); a superseding candidate resets the count, and
  more than one open marker is a data-integrity condition left for a human.
- `evaluate-path` is the one agent step (`claude-sonnet-5`, read-only,
  structured output) deciding `clean-bump` (⇒ `prepare`), `needs-migration`
  (⇒ routed to a maintainer, no diff), or `ambiguous-options` (⇒ a
  `kind: action` question posted, the marker flagged `awaiting-decision=true`,
  the cycle paused). Fetched release notes are framed as untrusted data,
  never instructions (constitution V).
- `prepare` writes the version-bump diff (both `speckit_version` **and**
  `wing-commander-preflight`'s `SPECKIT_SUPPORTED_VERSION` in one commit, plus
  the candidate's own `.specify/` artifact regeneration) to a fresh branch —
  bundled as an artifact, never pushed until `act`.
- `verify` runs **tiered** verification against the prepared candidate in an
  isolated worktree: a lightweight tier always (`check-prerequisites.sh` +
  `create-new-feature.sh --json` exit 0 and produce the documented JSON
  shape), plus an end-to-end tier for `minor`/`major` jumps (a disposable
  spec generated and discarded — never touches the real `specs/` tree).
- `act` opens the version-bump PR on a pass, leaves the pin untouched and
  flags the issue on a fail, or opens the revert PR on a health-check
  failure. It never merges its own PR (constitution V, FR-017).

**Self-recognition** — the feature owns no `spec:<NNN>` identity and never
assumes any other PR/issue is its own. PRs it opens carry a body marker
(`<!-- wing-commander-auto-update-spec-kit: version-bump -->` or `: revert`);
lifecycle issues carry the settle-tracking marker. The `pr-merged` entry job
no-ops on any closed PR lacking the marker, and `comment-reply` no-ops on any
commented-on issue lacking the settle marker or not carrying an outstanding
`awaiting-decision=true` question. `comment-reply` additionally gates the
commenter (`OWNER`/`MEMBER`/`COLLABORATOR` or the issue author — the same
actor gate `wing-commander-2-clarify.yml` uses) and interprets the reply with
a read-only `claude-haiku-4-5` step before re-entering `prepare` → `verify` →
`act`.

**Outcome recording** — the split mirrors this repo's existing convention: a
successful adoption closes its lifecycle issue **only** via the version-bump
PR's `Closes #N` keyword on merge (never a direct `gh issue close`, avoiding a
race with a human), and the sole visible flag is the `auto-update:failed`
label added on any verification failure or rollback — there is no busy label
for the routine success path (SC-004). All routine narration posts through
`wing-commander-callout` (`kind: info`); only the FR-012 ambiguous-options
question and the "please reply more clearly" re-ask use `kind: action`.

---

## Reusability (current state — `specs/010-reusable-pipeline/`)

Extraction is done: every stage is a published `workflow_call` workflow, and
this repository consumes them the same way adopters do (milestone 4 of the
[roadmap](../README.md#roadmap)). The load-bearing contract is constitution
VI: **the pipeline reads everything project-specific from the consuming
repository's checkout** — its `.specify/memory/constitution.md`, its
templates and scripts under `.specify/`, its `.claude/skills/speckit-*`, its
`specs/` directory. No stage resolves any project artifact from
Wing Commander itself; the one self-reference is the composite-action
checkout at `github.job_workflow_sha`, parameterized by the `pipeline-repo`
input (defaulting to the publisher).

The shape that shipped (details in the Foundations section above and in
[docs/adoption.md](adoption.md)):

1. Stage bodies live in `<stage>.yml` with explicit typed inputs and
   declared secrets (no `secrets: inherit` — the credential surface is part
   of the interface).
2. Consuming repos keep thin event-trigger wrappers
   (`uses: charlesguse/wing-commander/.github/workflows/plan.yml@v2`)
   plus their own `specify init` output — constitution, templates, scripts,
   and skills are theirs, never inherited from this repo.
3. Shared mechanics live in the `wing-commander-context`, `wing-commander-preflight`, and
   `wing-commander-metrics-summary` composites, reached via the self-checkout so a
   single version pin covers everything.
4. `release.yml` publishes exact `vX.Y.Z` tags and advances the floating
   major tag on non-breaking releases; this repo's wrappers call by local
   path, so dogfooded runs validate unreleased head before any tag moves.

## Known risks

| Risk | Mitigation |
|---|---|
| Slash/skill invocation in `prompt` regresses (action issue #523, fixed v1.0.10) | Pin `@v1`; prompts name the skill file path explicitly as fallback context |
| spec-kit moves fast (v0.12 changed feature resolution & dropped git from scripts) | Version pinned in `.specify/init-options.json`; re-verify scripts on upgrade |
| `pull_request: closed` + `paths:` false-triggers | Head-branch prefix guards in every stage's `if:` |
| Converge "unchanged tasks.md" is syntactic, not semantic | Iteration cap + final converge report always posted to the issue |
| Prompt injection via issue/comment bodies | Never interpolated; framed as data; least-privilege tools; no web tools; maintainer label gate |
| Rate-limit exhaustion (subscription auth) | `--max-turns` everywhere; Sonnet default; Opus is explicit opt-in |
