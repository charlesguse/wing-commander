# Pipeline Architecture

How a feature request becomes merged code, stage by stage. Stages 1–6 are
implemented.

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
  │                     [4 implement ⟲ converge] (≤ SPECKIT_MAX_ITERATIONS)
  │                                              │  dispatch
  │                                              ▼
  │◀─ manual tasks report  [5 finalize] ──▶ final PR spec/NNN → main
  │                                              │  human merge
  ▼                                              ▼
issue closed ◀──────────── [6 cleanup] ◀── branches deleted, labels flipped
```

## Foundations

### Identity & chaining: the speckit-bot App
Everything the pipeline does to the repo (push, PR, label, comment) uses a
GitHub App installation token minted per-job by `.github/actions/speckit-context`.
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
- **Branches** (routing keys for PR-event triggers):
  - `spec-draft/NNN-slug` — draft spec PR head (intake → main)
  - `spec/NNN-slug` — long-lived per-spec integration branch (concurrent specs)
  - `plan/NNN-slug`, `impl/NNN-slug-iterN` — stage work branches → spec branch
- **Labels** on the lifecycle issue: `spec:NNN-slug` + one `stage:*` label.
- **spec-kit targeting**: every agent step sets
  `SPECIFY_FEATURE_DIRECTORY=specs/NNN-slug` (spec-kit ≥0.12 resolves the active
  feature from this env var or `.specify/feature.json`, never from branch names),
  so concurrent specs can't cross-contaminate.

### Concurrency
Each stage job uses `concurrency: speckit-<spec key>` — one spec's stages
serialize, different specs run in parallel. Intake serializes globally
(`speckit-intake`) so feature numbers can't collide.

### Model tiering (constitution II)
| Work | Model |
|---|---|
| Triage, diff summaries, labels | `claude-haiku-4-5` |
| specify / clarify | `claude-opus-4-8` (constitution v1.1.0: spec quality is bought up front) |
| plan / tasks | `claude-sonnet-5` |
| implement / converge | `vars.SPECKIT_IMPLEMENT_MODEL` (default `claude-sonnet-5`; `claude-opus-4-8` via variable or `model:opus` label) |

Every agent step declares `--model` and `--max-turns`.

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

## Stage 2 — Plan (`speckit-3-plan.yml`, implemented)

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
4. claude-code-action on the spec branch, `SPECIFY_FEATURE_DIRECTORY` set:
   run `/speckit-plan` (proceeding despite unresolved markers, FR-011), commit
   plan artifacts to `plan/NNN-slug`, open a PR **targeting `spec/NNN-slug`**,
   update spec-meta.json (`stage: plan`), comment the summary on the issue.
5. Deterministic post-step verifies the plan PR exists, then flips the issue
   label to `stage:plan`.
6. A plan PR closed **unmerged** marks the spec stalled (`stage:stalled` label,
   spec-meta.json `stage: "stalled"`, issue comment); restart is manual —
   delete `plan/NNN-slug` and dispatch the workflow (FR-012).

## Stage 3 — Tasks (`speckit-4-tasks.yml`, implemented)

Specified in [`specs/003-tasks-stage/`](../specs/003-tasks-stage/spec.md).

**Trigger**: `pull_request: closed` with base `spec/**`, head `plan/*`, merged;
plus `workflow_dispatch` (input: `slug`) for manual restarts (same restart
idiom as the plan stage).

**Flow**: resolve + validate the slug from the head branch (refuse to guess,
FR-012); idempotency-guard on `spec-meta.json` `stage == "plan"` (duplicate
notifications no-op, FR-011; a manual dispatch may also proceed from
`"stalled"` — that is the restart path). Then run `/speckit-tasks`
(`claude-sonnet-5`, `SPECIFY_FEATURE_DIRECTORY` set), gated by
`vars.SPECKIT_TASKS_REVIEW`:
- `auto` (default, any other value falls open to it): commit `tasks.md` +
  `spec-meta.json` (`stage: "tasks"`) directly to `spec/NNN-slug`; post a task
  summary to the lifecycle issue; flip its label to `stage:tasks`; then a
  deterministic step runs `gh workflow run speckit-5-implement.yml
  -f spec_dir=… -f issue=… -f iteration=1`.
- `pr`: open a `tasks/NNN-slug` PR carrying the same changes; a
  `tasks-approved` job in this same workflow does the dispatch when that PR
  merges. A tasks PR closed **unmerged** marks the spec stalled
  (`stage:stalled` label, `spec-meta.json` `stage: "stalled"`, issue comment);
  restart is manual — delete `tasks/NNN-slug` and dispatch the workflow.

## Stage 4 — Implement ⟲ converge (`speckit-5-implement.yml`, implemented)

Implemented via `specs/005-implement-converge/` (issue #15); the design below
is what the implementation follows.

**Trigger**: `workflow_dispatch` (`spec_dir`, `issue`, `iteration`). Looping is
**re-dispatch, not an in-job loop**: each iteration is a separate auditable run,
stays under the 6-hour job cap, and the cap check is trivial (`iteration <=
vars.SPECKIT_MAX_ITERATIONS`).

**Design**:
1. **Implement**: checkout `spec/NNN-slug`; `/speckit-implement` with
   `--model vars.SPECKIT_IMPLEMENT_MODEL` (or Opus if the lifecycle issue has
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

## Stage 5 — Finalize (`speckit-6-finalize.yml`, implemented — see `specs/006-finalize-stage/`)

**Trigger**: `workflow_dispatch` (`spec_dir`, `issue`, `converged`).

**Design**:
1. Haiku step summarizes `git diff main...spec/NNN-slug` and extracts unchecked /
   manual items from tasks.md (structured output via `--json-schema`).
2. Plain `gh pr create`: `spec/NNN-slug → main`, body = what changed, how to see
   it (diff link, key files), remaining manual tasks, lifecycle issue link.
3. Comment the same manual-task list on the lifecycle issue; label `stage:review`.

## Stage 6 — Cleanup (`speckit-7-cleanup.yml`, implemented — see `specs/007-cleanup-stage/`)

**Trigger**: `pull_request: closed`, repo-wide — self-selects one of three
outcomes from the event payload alone (head ref prefix + base ref + `merged`),
never guessed. Every other closed-PR shape is a deliberate no-op.

**Design** — three independently-gated jobs, exactly one of which runs per
closed PR:
- `teardown-done` — final PR (`spec/NNN-slug → main`) **merged**: delete
  `spec-draft/`, `spec/`, `plan/`, `tasks/`, and any `impl/*-iterN` branches
  for that spec; close the lifecycle issue (atomically, with a
  Haiku-written completion summary); flip its label to `stage:done`.
- `teardown-rejected` — draft PR (`spec-draft/NNN-slug → main`) **closed
  unmerged**: delete `spec-draft/NNN-slug`; remove the `stage:*`/`spec:*`
  labels; comment that the spec was rejected; leave the issue **open** so
  the requester can revise and re-enter the pipeline.
- `mark-stalled` — final PR closed unmerged (built work rejected), **or** a
  non-final `plan/`/`tasks/`/`impl/*` pull request into `spec/NNN-slug`
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

## Auto-rebase (`speckit-rebase.yml`)

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
`<!-- speckit-rebase: blocked branch-sha=… main-sha=… -->` marker plus a
`rebase:blocked` label; `discover` reads that marker to skip a branch whose
`(branch, main)` pair hasn't changed since it was reported blocked, so a stall
is only escalated once until either side moves (a subsequent success removes
the label).

---

## Reusability roadmap

The current workflows are repo-local; extraction is milestone 4 of the
[roadmap](../README.md#roadmap). One contract already holds today and must
survive extraction unchanged (constitution VI): **the pipeline reads everything
project-specific from the consuming repository's checkout** — its
`.specify/memory/constitution.md`, its templates and scripts under `.specify/`,
its `.claude/skills/speckit-*`, its `specs/` directory. No stage resolves any
artifact from speckit-action itself, and no workflow hardcodes a repository
name or owner; every path is relative to the checkout, so the same workflow
bodies operate on whichever repository runs them.

The extraction path:
1. Move stage bodies into `workflow_call` reusable workflows with explicit
   inputs (`spec_dir`, `issue_number`, `iteration`) and `secrets: inherit`.
2. Consuming repos keep thin event-trigger wrappers
   (`uses: <org>/speckit-action/.github/workflows/speckit-3-plan.yml@v1`)
   plus their own `specify init` output — constitution, templates, scripts,
   and skills are theirs, not inherited from this repo.
3. Everything repo-specific stays in the `speckit-context` composite.

## Known risks

| Risk | Mitigation |
|---|---|
| Slash/skill invocation in `prompt` regresses (action issue #523, fixed v1.0.10) | Pin `@v1`; prompts name the skill file path explicitly as fallback context |
| spec-kit moves fast (v0.12 changed feature resolution & dropped git from scripts) | Version pinned in `.specify/init-options.json`; re-verify scripts on upgrade |
| `pull_request: closed` + `paths:` false-triggers | Head-branch prefix guards in every stage's `if:` |
| Converge "unchanged tasks.md" is syntactic, not semantic | Iteration cap + final converge report always posted to the issue |
| Prompt injection via issue/comment bodies | Never interpolated; framed as data; least-privilege tools; no web tools; maintainer label gate |
| Rate-limit exhaustion (subscription auth) | `--max-turns` everywhere; Sonnet default; Opus is explicit opt-in |
