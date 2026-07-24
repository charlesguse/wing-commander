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

Every stage body lives in a published stage workflow (`<stage>.yml`) whose only trigger is
`workflow_call`. Stage workflows never read `github.event.*` or `vars.*` —
every event fact (issue number, head/base refs, merged flag, comment id) and
every knob (model, max-turns, review mode, iteration cap, chaining targets)
is a declared, typed input with a default matching the constitution's
tiering. The **wrapper** owns the trigger, the security gates, and the
event→input extraction; this repository's eight `wing-commander-*.yml` wrappers are
the worked example, and adopters write the same shape against a version tag.

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
| specify / clarify | `claude-opus-4-8` (constitution v1.1.0: spec quality is bought up front) |
| plan / tasks | `claude-sonnet-5` |
| implement / converge | stage `model` input (default `claude-sonnet-5`); this repo's wrapper wires `vars.WING_COMMANDER_IMPLEMENT_MODEL` and the `model:opus` label opt-in into it |

Every agent step declares `--model` and `--max-turns`. Each is followed by a
deterministic `.github/actions/wing-commander-metrics-summary` step that reads the
run's own execution transcript and appends a metrics block (model, turns used
against budget, duration, tokens, cost, with an ≥80% turn-budget warning) to
that run's `$GITHUB_STEP_SUMMARY` — pure read, no agent, never fails the stage
(`specs/009-agent-metrics/`).

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
  `--allowedTools`.
- Only trusted refs are checked out (main, repo-local `spec*/` branches) — never
  fork PR heads.
- Humans merge every PR into main. The bot cannot approve or merge.

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

**Trigger**: `push` to main (skipping `*[bot]` actors) + nightly schedule.

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

**Trigger**: `workflow_run: [completed]` across all nine stage wrappers —
including itself, for self-inspection (FR-021) — plus manual
`workflow_dispatch` with a `run-id` to re-inspect any past run. The thin
wrapper only resolves the inspected run's identity (`run-id`/`run-name`);
every job below lives in the reusable `watchdog.yml`.

**Design** — four sequential jobs, `collect → diagnose → triage → act`:
- `collect` — deterministic evidence gathering only (no agent). Five FR-006
  sources — execution-output denied-tool counts, branch drift (zero pushed
  commits on a push-expected stage), `spec-meta.json` stage vs. expected,
  step-summary sentinels, and check-run annotations — merge into one
  normalized `signals.json`. Best-effort spec-slug/lifecycle-issue
  resolution: a run that can't be tied to a spec (e.g. a `main`-based
  cleanup) is still inspected and reported against its own run URL. Only if
  *every* collector errors outright does it flip `evidence-available: false`
  → "could not inspect this run" (FR-005); an empty-but-successful signal set
  still proceeds to `diagnose`.
- `diagnose` — one `claude-haiku-4-5`, read-only, structured-output step
  (no write tools, no `git`/`gh` write access) turning signals into zero or
  more Findings. `signals.json` and anything read is framed as untrusted
  data, never instructions (FR-023). Zero Findings ⇒ "passed inspection"
  (FR-004) and nothing is filed.
- `triage` — one matrix entry per Finding: coexistence-suppression check
  (a Finding already handled by `implement.yml`'s stalled job or
  `cleanup.yml`'s `mark-stalled` is reported, not re-acted, FR-024),
  deterministic `sha256(class + "|" + canonical(normalizedFacts))`
  fingerprint (the `rebase.yml` marker-dedup convention), `gh search issues`
  dedup over the marker (`--state all`), an optional `claude-sonnet-5`
  propose-fix step scoped to `.github/**`/`docs/**` for known-remediable
  classes, and the deterministic **rung gate**.
- `act` — one matrix entry per non-suppressed Finding: executes exactly what
  the rung gate selected and always appends a per-Finding report to the
  lifecycle issue (FR-022).

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
rung-1 eligibility, never invents a default. `vars.WING_COMMANDER_WATCHDOG_PAUSED`
(`true` ⇒ report-only, every write at every rung suppressed) and
`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`) are the two
operator switches; the cap counts the consecutive `workflow_run`-sourced
self-inspection chain and, once reached, suppresses all writes so an
unattended watchdog-inspects-watchdog loop is bounded (FR-018). Detection,
fingerprinting, dedup, and reporting are identical whether the inspected run
is a watchdog run or any other stage (FR-021) — the self-dispatch-depth count
is the only place the stage looks at its own name.

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
