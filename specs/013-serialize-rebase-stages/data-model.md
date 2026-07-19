# Phase 1 Data Model: Serialize Rebase and Stages Per Specification

This feature has no application data model and introduces no new persisted
file, field, or schema — `spec-meta.json`'s shape is unchanged, no new
label or issue-comment marker is added. The "entities" below are the ones
named in `spec.md`'s Key Entities section, expressed as the concrete
GitHub Actions constructs research.md's decisions (D1–D5) resolve them to.

## Specification working branch (`spec/NNN-slug`)

Unchanged from spec 008/010 — the persistent, long-lived branch a
specification's plan/tasks/implement/finalize stages and auto-rebase all
mutate. This feature does not change how the branch is discovered, checked
out, or published; it changes only *when* each of those operations is
allowed to run relative to the others.

| Field | Source | Used for |
|---|---|---|
| `slug` | `NNN-slug`, parsed from a branch name, a `head-ref` input, or `inputs.slug` | Canonical spec identity |
| `spec-dir` | `specs/<slug>` | Half of the concurrency group key (D2); also every stage's existing artifact-path root |

## Concurrency group (the mutual-exclusion key this feature creates)

Not a file — a string, computed once per job invocation and passed to
GitHub Actions' own `concurrency:` block, which is where the actual
mutual-exclusion behavior lives (this feature adds no custom locking code).

| Field | Value | Computed by |
|---|---|---|
| Canonical group string | `wing-commander-${spec-dir}` (e.g. `wing-commander-specs/013-serialize-rebase-stages`) | Already the literal value of `implement.yml`/`finalize.yml`'s existing group (`inputs.spec-dir` is passed to them directly, D2) |
| `rebase.yml`'s group | Same string, sourced from `matrix.spec_dir` (already emitted by `discover`, D2) | The `rebase` matrix job, one per selected branch |
| `plan.yml`'s group | Same string, sourced from a new `resolve-spec` job's `spec-dir` output (D3) | The `plan` job, via `needs.resolve-spec.outputs.spec-dir` |
| `tasks.yml`'s group | Same string, sourced from a new `resolve-spec` job's `spec-dir` output (D3), shared by both `tasks` and `tasks-approved` | Whichever of the two jobs `inputs.mode` selects |

**Membership** (FR-005, FR-008, D5): exactly the six job instances in
research.md D1's table share this group per specification —
`rebase.yml`'s `rebase` matrix entry, `plan.yml`'s `plan` job,
`tasks.yml`'s `tasks` and `tasks-approved` jobs, `implement.yml`'s
`implement` and dispatch-next jobs, and `finalize.yml`'s `finalize` job.
`intake.yml` (`wing-commander-intake`, global — no slug exists yet),
`clarify.yml` (`wing-commander-${issue-number}` — keyed to the lifecycle
issue, not a `spec/NNN-slug` branch), and `cleanup.yml`
(`wing-commander-cleanup-${head-ref}` — runs only after a spec's terminal
stage, D5) are explicitly **not** members; their existing groups are
unchanged.

**State transitions** (all owned by GitHub Actions, not this feature's
code):

```
no job holds wing-commander-<spec-dir>        → a request runs immediately (FR-006: uncontended path unchanged)
one job holds it, one more requests it        → the second queues, runs after the first completes (FR-001/FR-002/FR-003)
one job holds it, two+ more request it         → only the most-recently-queued request survives to run next
                                                  (GitHub Actions native behavior, D4) — never a problem for FR-004,
                                                  since the next main-line push or nightly schedule requeues a rebase,
                                                  and the next stage hand-off requeues a stage
```

## Resolved spec identity (new: `resolve-spec` job output, `plan.yml`/`tasks.yml`)

Ephemeral, not persisted beyond the workflow run that produces it — exists
only to make the slug/spec-dir available at job-start time, before the
`concurrency:` block of the job that `needs:` it is evaluated (D3).

| Field | Derived from | Validation |
|---|---|---|
| `slug` | `inputs.slug`, or `inputs.head-ref` with its stage-specific prefix stripped (`spec-draft/` for `plan.yml`; `plan/` or `tasks/`, selected by `inputs.mode`, for `tasks.yml`) | Must match `^[0-9]{3}-[a-z0-9][a-z0-9-]*$`; failing this fails the `resolve-spec` job with `::error::`, exactly as the (now-removed) same-job step did before |
| `spec-dir` | `specs/<slug>` | — |

This replaces, rather than duplicates, the `Resolve spec identity` step
that exists today inside `plan`/`tasks`/`tasks-approved` — the downstream
job consumes `needs.resolve-spec.outputs.*` instead of recomputing the same
value.

## Lifecycle issue (unchanged)

This feature adds no new comment, label, or marker to the lifecycle issue.
Existing rebase escalation (`rebase:blocked`, spec 008) and every stage's
existing status comments are unaffected; SC-002's "no manual re-dispatch
required" is achieved by queuing runs correctly, not by any new reporting.
