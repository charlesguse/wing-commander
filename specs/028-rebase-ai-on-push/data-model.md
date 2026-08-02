# Phase 1 Data Model: Auto-Rebase AI Conflict Resolution on Push-Triggered Rebases

This feature adds no runtime application data — the "entities" here are the
workflow-graph shapes the wrapper fix and Gate 6 read from and write to
`.github/workflows/*.yml`. They give concrete field-level shape to the
spec's Key Entities section.

## Wrapper Workflow (spec: "Auto-rebase wrapper", generalized by Gate 6 to any wrapper)

| Field | Description |
|---|---|
| File | e.g. `.github/workflows/wing-commander-rebase.yml` |
| `on:` | The set of top-level triggering events the file declares (`push`, `schedule`, `workflow_dispatch`, ...) — PyYAML resolves the bare `on` key to boolean `True` per YAML 1.1; existing Gate 2 already handles this via `wf.get(True, wf.get("on"))`, and Gate 6 reuses the same access pattern |
| Jobs with a local reusable call | Every job whose steps include `uses: ./.github/workflows/<stage>.yml` — the same shape Gate 3 already detects for permission-grant checking |
| Job `if:` | Per-job condition string, used by Gate 6 to narrow the job's reachable-event set below the wrapper's full `on:` set (data-model "Job Reachable-Event Set" below) |

### This feature's concrete instance: `wing-commander-rebase.yml`

| | Before | After |
|---|---|---|
| `on:` | `push` (branches: `[main]`), `schedule` (`17 4 * * *`) | `push`, `schedule`, `workflow_dispatch` (`{}`, no inputs — the redispatched run needs none; `discover` re-derives everything from repository state) |
| Jobs | One job, `rebase`, `if: !endsWith(github.actor, '[bot]')`, calls `uses: ./.github/workflows/rebase.yml` unconditionally for both `push` and `schedule` | Two jobs: `redispatch` (`if: github.event_name == 'push' && !endsWith(github.actor, '[bot]')`, no `uses:` — calls `gh workflow run wing-commander-rebase.yml`) and `rebase` (`if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`, unchanged `uses: ./.github/workflows/rebase.yml` call, `with:`/`secrets:` byte-for-byte unchanged) |
| `redispatch` job permissions | N/A | `actions: write` only — least privilege for a single `gh workflow run` call (constitution V) |

## Resolved Stage (spec: "the reusable rebase stage" the wrapper triggers)

| Field | Description |
|---|---|
| File | The target of a wrapper job's `uses: ./.github/workflows/<stage>.yml`, resolved by basename the same way Gate 3 already resolves reusable-workflow callees |
| Agent-bearing? | `True` iff any job in the resolved file contains a step whose `uses:` starts with `anthropics/claude-code-action` (the literal marker `release.yml`'s existing agent-count grep already uses) |

### This feature's concrete instance: `rebase.yml`

Unchanged by this feature (constitution VII, FR-006, FR-007). Agent-bearing
= `True` (the `rebase` job's "Resolve conflicts" step). Its `discover` job
is not agent-bearing — Gate 6 does not need job-level granularity inside
the *resolved stage*, only inside the *wrapper* (a stage's own internal
job structure isn't something a wrapper's trigger choice can make
unreachable in the way this defect requires).

## AI-Agent Step (spec: "AI conflict-resolution step", generalized by Gate 6 to any `claude-code-action` step)

| Field | Description |
|---|---|
| Marker | `uses:` value starting with `anthropics/claude-code-action` |
| Location | Any job, in any resolved stage file — Gate 6 only needs "does at least one exist," not which job or how many |

## Supported-Event Set (spec: "the fixed set of events under which the AI-agent step can run")

A fixed list encoded directly inside Gate 6 (research.md R6), not read from
any external source or configuration file:

| Event | Evidence in this repository (wrapper → stage, both currently green in production) |
|---|---|
| `issues` | `wing-commander-1-intake.yml` → `intake.yml` |
| `issue_comment` | `wing-commander-2-clarify.yml` → `clarify.yml` |
| `pull_request` | `wing-commander-3-plan.yml`/`wing-commander-4-tasks.yml`/`wing-commander-7-cleanup.yml` → `plan.yml`/`tasks.yml`/`cleanup.yml` |
| `workflow_dispatch` | `wing-commander-3-plan.yml`/`wing-commander-4-tasks.yml`/`wing-commander-5-implement.yml`/`wing-commander-6-finalize.yml` → their respective stages |
| `workflow_run` | `wing-commander-8-watchdog.yml` → `watchdog.yml` |
| `schedule` | `wing-commander-auto-update-spec-kit.yml` → `auto-update-spec-kit.yml`'s `evaluate-path` job |

`push` is deliberately absent — the confirmed defect (spec Input, FR-001).
Any event not listed is treated as unsupported until a maintainer adds it
here with its own evidence (research.md R6, FR-010).

## Job Reachable-Event Set (new abstraction, computed only by Gate 6 — not persisted anywhere)

For a given wrapper job that calls an agent-bearing resolved stage:

| `if:` shape | Reachable-event set |
|---|---|
| Absent, or present but no `github.event_name ==`/`!=` clause found | The wrapper's full declared `on:` event set (conservative default — research.md R7) |
| Contains one or more `github.event_name == '<event>'` clauses | The union of matched `<event>` values, intersected with the wrapper's declared `on:` set |
| Contains one or more `github.event_name != '<event>'` clauses (and no `==` clause) | The wrapper's declared `on:` set minus the matched `<event>` values |

**Gate 6 verdict**: for each wrapper job calling an agent-bearing stage,
`flagged = reachable_event_set − supported_event_set`. Non-empty ⇒ the
pull request fails, with an annotation naming the wrapper file and every
member of `flagged` (FR-011). A wrapper whose resolved stage is not
agent-bearing is never evaluated at all (FR-009) — the job-reachability
computation above never runs for it.

### This feature's concrete instances, post-fix

| Wrapper job | `if:` | Reachable-event set | Flagged? |
|---|---|---|---|
| `wing-commander-rebase.yml` / `redispatch` | `github.event_name == 'push' && ...` | `{push}` | N/A — `redispatch` has no `uses: ./.github/workflows/*.yml` call, so Gate 6 never evaluates it in the first place |
| `wing-commander-rebase.yml` / `rebase` | `github.event_name == 'schedule' \|\| github.event_name == 'workflow_dispatch'` | `{schedule, workflow_dispatch}` | No — both are in the supported set |

### Pre-fix instance (what Gate 6 would have caught, had it existed)

| Wrapper job | `if:` | Reachable-event set | Flagged? |
|---|---|---|---|
| `wing-commander-rebase.yml` / `rebase` (original, single job) | `!endsWith(github.actor, '[bot]')` (no `event_name` clause) | `{push, schedule}` (full wrapper `on:` set, conservative default) | **Yes — `push`** |

## No new persisted entity, no new external write surface

The `redispatch` job's only write is the `gh workflow run` API call
(triggering a new Actions run — not a repository content write). Gate 6
writes only `::error` annotations and a process exit code, identical in
shape to Gates 2/3/5 — no `GITHUB_STEP_SUMMARY`, no artifact, no comment.
`rebase.yml`'s existing publish/escalate write surface (force-with-lease
push, lifecycle-issue comment/label) is completely unchanged.
