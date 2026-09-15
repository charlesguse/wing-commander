# Contract Delta: Agent Run Metrics Record (schema version 1)

This is a delta against `specs/043-durable-metrics-record/contracts/
metrics-record-schema.md`, which remains the base contract for every
field this feature does not touch. Only the clause and shape below
change; the four compatibility rules, the `per_model` sum invariant, and
every existing field's meaning are unchanged.

## New clause: the `branch_advance` group

**Current contract**: The `## Shape` block has no field describing which
branch, if any, a run advanced, or between which two points.

**Amended contract**: Every schema-version-1 record MAY carry a
`branch_advance` object (data-model.md has the full field table):

```json
{
  "branch_advance": {
    "available": true,
    "branch": "spec/050-branch-drift-sha-baseline",
    "before_sha": "5f2a1c9...",
    "before_available": true,
    "after_sha": "9b7e004...",
    "after_available": true,
    "commits": 3,
    "commits_available": true
  }
}
```

A record produced by a `wing-commander-metrics-summary` version that
predates this feature has no `branch_advance` key at all. A reader MUST
treat its absence identically to `{available: false, branch: null,
before_sha: null, before_available: false, after_sha: null,
after_available: false, commits: null, commits_available: false}` —
never as a validation failure (compatibility rule 2, restated for this
specific field: "any unavailable value explicitly marked... rather than
absent" governs the group's *contents* once present; the group's own
*absence* on a pre-feature record is the ordinary additive-field
backward-compatibility case rule 1 already covers).

The group is stage-neutral (FR-020 of specs/050): its name and shape
carry no reference to "implement" specifically, so `plan`/`tasks` may
populate it in a later feature using the same shape and the same
`branch_advance.available` gate, with no contract change required.

## Degraded-record example, updated

The base contract's "Degraded record (transcript missing/empty/
unparseable)" example gains the same group, `available: false` (the
degraded case this feature itself produces — an intentionally-absent
transcript path, research.md R2 — carries a *populated* `branch_advance`
alongside `record_available: false`; the base contract's own degraded
example, produced by an unintentional transcript failure at a call site
that never populated the new inputs, keeps `branch_advance.available:
false` too). This confirms `record_available` and `branch_advance
.available` are independent axes: a record can be transcript-degraded
and branch-advance-populated at the same time (the new fourth call
site's normal case), or transcript-healthy and branch-advance-absent
(every pre-existing call site).

## No change to the invariant, the compatibility rules, or any other field

The `per_model` sum invariant, `schema_version: 1`, and every field this
delta does not name are unchanged. This delta is purely additive per the
base contract's own rule 1.
