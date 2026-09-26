# Contract Delta: Agent Run Metrics Record (schema version 1)

This is a delta against `specs/043-durable-metrics-record/contracts/
metrics-record-schema.md` as already amended by `specs/050-branch-drift-
sha-baseline/contracts/metrics-record-schema-delta.md`. Only the clause
below changes; the `branch_advance` group's shape, the four
compatibility rules, and every other field are unchanged.

## Amended clause: who populates `branch_advance`, and what "before" means

**Current contract** (post-050): "A record produced by a
`wing-commander-metrics-summary` version that predates this feature has
no `branch_advance` key at all... The group is stage-neutral... so
`plan`/`tasks` may populate it in a later feature using the same shape
and the same `branch_advance.available` gate, with no contract change
required."

**Amended contract**: `plan` and `tasks` now populate the group, using
the same shape and the same gate, exactly as anticipated. All three
push-expected stages — `implement`, `plan`, `tasks` — populate
`branch_advance` for a run that reaches the point where its metrics
record is emitted (SC-001). A `plan`/`tasks` record's `branch` is the
branch that run actually pushed to for the review mode it ran in: the
persistent spec branch (`spec/<slug>`) in `auto` mode, or the run's own
review branch (`plan/<slug>`, `tasks/<slug>`) in `pr` mode — recorded
literally, never derivable by a reader from a prefix or the review mode
itself, because the record does not carry the mode (FR-004).

**"Before," restated stage-neutrally**: `before_sha` is "the point the
run advanced the branch from." For a branch that already existed at the
start of the run's work, that is its tip at that moment (implement's
existing meaning, unchanged). For a branch the run itself creates — a
`pr`-mode plan/tasks run creating its own review branch, or an
`auto`-mode plan run whose spec branch does not yet exist — it is the
commit the branch was created from. A single reader-side rule ("compare
`before_sha` to `after_sha`") covers both cases without the reader
needing to know which one applies (FR-005). This is a widening of the
field's definition, not a behavior change for any already-persisted
record: every value implement has ever recorded in this field already
satisfies the widened definition (specs/050's own Assumption, restated).

**Example — a `pr`-mode plan run's record**:

```json
{
  "branch_advance": {
    "available": true,
    "branch": "plan/068-plan-tasks-branch-advance",
    "before_sha": "a1b2c3d...",
    "before_available": true,
    "after_sha": "a1b2c3d...",
    "after_available": true,
    "commits": 0,
    "commits_available": true
  }
}
```

(Equal `before_sha`/`after_sha` here means the `pr`-mode agent never
pushed its review branch past the commit it branched from — the
lost-progress case US1 exists to catch, whether or not the branch was
freshly created by this same run.)

## No change to the invariant, the compatibility rules, the group's shape, or any other field

`per_model`'s sum invariant, `schema_version: 1`, the `branch_advance`
group's eight sub-fields and their types, and every field this delta
does not name are unchanged. This delta is purely additive per the base
contract's own rule 1, and purely a widening of one field's stated
meaning per FR-005/FR-009 — no already-persisted record's correct
reading changes.
