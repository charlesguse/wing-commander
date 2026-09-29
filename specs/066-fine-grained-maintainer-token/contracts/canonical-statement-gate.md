# Contract: a new gate enforces FR-017/FR-018's single canonical statement

research.md D7 explains why this is a new, topic-specific gate rather than
an extension of Gate 47 (`verify-comment-canonical-pointers.py`), whose
declared scope is `#` comments in `.github/workflows/*.yml` only. This
contract describes the new gate's subject, its pass/fail rule, and its
required self-test — the same shape every gate in this repository's suite
follows (Constitution VIII).

## Subject

Four sites, named by the spec's User Story 4:

1. **Canonical**: `docs/setup.md` §2, the
   `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN` row.
2. **Pointer**: `auto-release.yml`'s comment block above the "Confirm the
   fixture maintainer identity's credential" step.
3. **Pointer**: the precheck's own expectation text — the `expected`
   arguments passed to `auto-release-verdict.sh` inside that step, and the
   scenario/docstring text of `.github/scripts/verify-auto-release-
   credential-step.py` (Gate 67).
4. **Pointer, historical**: `specs/055-unattended-e2e-gates/research.md`
   D1/D2 and its `spec.md` Clarifications session.

## Pass/fail rule

- A small, fixed set of phrases that would contradict the canonical
  statement is checked for at every site **other than** the canonical one:
  an unqualified "not fine-grained" or "never fine-grained" claim, "classic
  PAT... the only accepted shape" (or equivalent absolute language), and
  "Write — never Admin" stated as this credential's own bound (superseded
  by FR-016's "no Administration permission on the credential" framing).
  This is a fixed phrase list, not a generic overlap heuristic (research.md
  D7) — the gate exists to catch a specific, previously-drifted claim, not
  to police prose generally.
- A site other than the canonical one MAY restate a **qualified** version
  of the claim (e.g. "a classic PAT is still accepted during the
  transition — see docs/setup.md") — the gate flags an unqualified,
  absolute-sounding phrase from the fixed list, not every mention of the
  word "classic" or "fine-grained".
- Every one of sites 2 and 3 MUST carry a pointer to site 1, in either of
  the two forms Gate 47 already recognizes (`-- see docs/setup.md` or `(see
  docs/setup.md)`), so that a reader who lands on the non-canonical site is
  led to the canonical one.
- Site 4 (specs/055) MUST carry the FR-019 annotation — a sentence stating
  the decision was superseded and pointing at specs/066 — rather than
  either restating the old absolute claim unpointed, or being silently
  rewritten to read as though the new shape had always been chosen. The
  gate checks for the annotation's presence near the D1/D2 headings and in
  the Clarifications session, not for exact wording.
- The canonical site itself is exempt from the phrase check (it is where
  those words, appropriately qualified, are expected to live).

## Failure output

Same convention as every other gate in this suite: `::error::` lines naming
the file, the offending phrase or missing pointer, and which rule (fixed
phrase found unpointed / missing FR-019 annotation) fired — never a bare
"gate failed."

## Self-test obligation (Constitution VIII)

The gate's own test suite MUST include:

- A clean fixture (current-state text at all four sites) that passes.
- A mutation reintroducing one of the fixed contradicting phrases at each
  pointer site without a pointer — MUST fail.
- A mutation removing the pointer from site 2 or site 3 while leaving the
  qualified restatement in place — MUST fail (a restatement without a
  pointer is still a second, unlinked copy).
- A mutation removing the FR-019 annotation from specs/055's research.md —
  MUST fail.
- A mutation pointing site 2 or 3 at a nonexistent target — MUST fail
  (reuses Gate 47's own "every pointer resolves" check as prior art for
  this rule's shape, applied to this gate's own narrower site list).

This gate is picked up by `run-local-gates.py` automatically once
registered in `lint-workflows.yml`'s gate registry (Constitution VIII: same
subject, same arguments, locally and in CI), the same way Gate 67 and every
gate before it already are.
