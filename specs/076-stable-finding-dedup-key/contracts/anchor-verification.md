# Contract: Anchor Verification (FR-004, FR-005, FR-006, FR-007)

Governs the one new step in `wing-commander-stage-findings/action.yml`'s
"Extract, validate, cap, and prepare findings" — inserted after schema
validation (D5 of spec 056) and before fingerprint derivation (D6 of spec
056, amended by this feature), per survivor.

## Inputs (already available to that step; no new composite input)

- `finding.fingerprint_basis.file_path` — schema-validated non-empty string.
- `finding.fingerprint_basis.gate_or_artifact` — schema-validated non-empty
  string; this contract is what changes how it is used.
- The job's own working directory (`GITHUB_WORKSPACE` at runtime), already
  the tree `evidence.file_paths` is implicitly read against.

## Behavior

1. Resolve `file_path` relative to the working directory.
2. If the resolved path does not exist, is not a regular file, or cannot be
   read: anchor is **unverifiable** (research.md D3).
3. Otherwise compute `norm(gate_or_artifact)`. If empty: anchor is
   **unverifiable** (research.md D1 — an all-punctuation/whitespace anchor
   is not a usable key component).
4. Otherwise compute `norm(file_text)` from the file's full content and
   test containment: `norm(gate_or_artifact) in norm(file_text)`.
   - Contained → anchor **verifies**.
   - Not contained → anchor is **unverifiable**.
5. Anchor unverifiable → the finding is not dropped. It is keyed under the
   FR-007 fallback shape (data-model.md "Dedup Key"), and one line is
   appended to the run's existing `notes` list naming the finding's title,
   the anchor value that failed, the file it was checked against, and that
   the finding was keyed via the fallback route rather than dropped
   (FR-006; research.md D4 — no new run-summary counter).
6. Anchor verifies → the finding is keyed under the with-anchor shape,
   using `norm(gate_or_artifact)` as computed in step 3 (not the raw
   value) as the key's third segment.

## Properties this contract must hold (traced to requirements)

- **Determinism (FR-002)**: steps 1-6 depend only on the finding's own
  fields and the named file's content at run time — no other run state, no
  randomness, no agent input beyond what schema validation already
  admitted.
- **No trusted-on-faith component (FR-005)**: `gate_or_artifact` enters the
  key only after step 4 succeeds; it is never hashed directly from the
  agent's proposal.
- **Position-independence (Edge Cases)**: containment (step 4) does not
  record or depend on *where* in the file the anchor occurs, only that it
  occurs — an anchor repeated many times in one file verifies the same way
  a once-occurring anchor does.
- **Not a silent drop (FR-007, SC-004)**: every code path through steps 2-6
  ends in either the with-anchor shape or the fallback shape; none of them
  is "and the finding is discarded."

## Fixture coverage (FR-010, FR-011 — see research.md D8)

| Scenario | Expected route |
|---|---|
| Anchor typed with different punctuation/case/spacing, both verbatim-verifiable against one fixture file, differing titles/what | same with-anchor key |
| Two genuinely different, both-verifiable anchors in one fixture file | two distinct with-anchor keys |
| Anchor absent from the named file's content | fallback key; a note recorded |
| Two such absent-anchor findings in one file | share the fallback key |
| One fallback-keyed and one with-anchor-keyed finding in the same file | distinct keys |
| Anchor that normalizes to empty (e.g. only punctuation) | fallback key, never an empty-string key |
| Named file does not exist in the tree | fallback key (User Story 3) |
