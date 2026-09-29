# Data Model: A Stable Finding Dedup Key

This feature changes how an existing entity's key is derived; it does not
add a persisted store. Per FR-012, the canonical statement of the key rule
itself has exactly one home — `specs/056-stage-found-defect-filing/data-model.md`'s
"Fingerprint" section — and this document does not restate it in full; a
second full copy here would be exactly the drift-prone duplication this
feature exists to close off elsewhere. What follows is the delta each
entity in spec 056's data model (and spec 057's, for the one entity FR-015
touches) undergoes, and the one genuinely new entity (Key Anchor) spec.md's
own Key Entities section already named.

## Stage Finding (proposal) — unchanged shape

No field is added, renamed, or removed. `fingerprint_basis.file_path` and
`fingerprint_basis.gate_or_artifact` keep their names and their JSON Schema
constraints in `.github/schemas/stage-finding.schema.json` (`minLength: 1`
string, both required) — this feature changes what the pipeline does with
`gate_or_artifact` after schema validation passes, not the shape schema
validation checks. An agent proposing a finding still supplies exactly the
same four top-level fields spec 056 defined.

## Key Anchor (new entity, per spec.md's Key Entities)

A value the pipeline checks against the tree rather than trusts.

| Property | Value |
|---|---|
| Source | `fingerprint_basis.gate_or_artifact`, as proposed |
| Verified against | the current content of `fingerprint_basis.file_path`, resolved relative to the run's own checkout (research.md D3) |
| Verification rule | `norm(gate_or_artifact)` is a non-empty substring of `norm(file_text)` (research.md D1); `norm` is the one already defined in spec 056's data-model.md, unchanged |
| On success | enters the dedup key as the with-anchor shape's third segment (research.md D2) |
| On failure (file unreadable, or normalized anchor absent from normalized file text, or normalized anchor itself empty) | does not enter the key at all; the finding takes the FR-007 fallback key; the run records why (research.md D4) |

An anchor's *raw* value is still shown to a maintainer verbatim in the
filed issue's body (the existing `## What is wrong` / evidence rendering is
unchanged) — only the *key* derivation treats it as untrusted until
checked, per Constitution Principle IX.

## Dedup Key — two derivable shapes, not one

Spec 056's data-model.md states the formula; this feature changes it from
a single three-segment hash to two mutually exclusive shapes, both
governed by the invariants FR-001/FR-002/FR-003/FR-005 state (and FR-015
requires spec 057's own, differently-composed key to keep satisfying too):

| Shape | Used when | Segments hashed (research.md D2) |
|---|---|---|
| With-anchor | the Key Anchor verifies | shape tag, stage, `norm(file_path)`, `norm(gate_or_artifact)` |
| Fallback (FR-007) | it does not | shape tag, stage, `norm(file_path)` |

Both shapes are individually stable across re-wordings of `title` and
`what` (FR-001) and re-derivable by a reviewer from the run's recorded
inputs alone (FR-002), and both remain scoped by stage (FR-003). Neither
shape is ever built from a component the pipeline did not compute itself or
verify against the tree (FR-005) — the fallback shape simply has one fewer
component than the with-anchor shape has, rather than substituting an
unverified one in the anchor's place.

**Compatibility**: an issue filed under the pre-076 single-shape formula
carries a marker that matches neither new shape; its next encounter files
once under whichever shape that encounter now produces, per FR-014. This
consequence is recorded in spec 056's data-model.md alongside the amended
formula (research.md D9), not duplicated here.

## Filed Finding Issue — append behavior gains one requirement (FR-008)

Body composition and labeling are unchanged from spec 056. What changes:
when a later encounter appends to an issue already open under either key
shape, the append comment MUST carry that encounter's own `title` and
`what` (not only the existing "seen again in run `<url>`" recap), because
the fallback shape's coarser key means several genuinely different defects
can now legitimately share one issue (FR-007's accepted cost), and FR-008
requires each to stay individually legible from the issue body alone.

## Run Summary Record — unchanged shape (research.md D4)

`proposed` / `filed` / `appended` / `dropped_malformed` / `dropped_cap` /
`dropped_api_failure` keep their existing meanings and are the only
counters. An anchor that fails verification is not a new drop category —
the finding it belongs to still reaches the board (filed or appended) — so
it is recorded only as a `notes` line, matching the existing free-text note
convention `dropped_malformed`/`dropped_cap` entries already use.

## Board Review Finding (spec 057) — key composition untouched, split held by a gate (FR-015)

`board-review-finding.schema.json`'s shape and `board-loop.yml`'s own
`sha256("<issue>|<norm(title)>|<norm(file_path)>")` formula are unchanged by
this feature. What is new: a gate (research.md D6, contracts/gates.md)
that fails if that formula and this feature's formula ever become
textually identical, or if either loses the literal ingredient that makes
it recognizably its own (spec 057's issue-number segment; this feature's
shape tag) — holding FR-015's split in place as a checked decision rather
than an unenforced comment.
