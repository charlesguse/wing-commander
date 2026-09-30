# Specification Quality Checklist: A Stall Holds Until a Maintainer Re-Admits It — and a Stop Halts Readiness's Filing

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-29
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Validation iteration 1 — 2026-09-29

- **"No implementation details" and "technology-agnostic"**: read against
  this repository's own domain. The product here *is* GitHub Actions
  workflows, composite actions and gate scripts, so naming `board-loop.yml`'s
  jobs, the `board:stalled` label, the board-item marker and
  `board_readiness.py` identifies the subject rather than prescribing an
  implementation. The specification deliberately does **not** choose how the
  stall-ordering check is built (FR-003/FR-004), how readiness's writes are
  gated (FR-012), or what shape a stall marker takes if FR-006 resolves to
  option (c) — those are plan-stage decisions. Matches the house style of
  `specs/085-stop-request-cancel-contract` and
  `specs/088-stop-check-closed-read`. PASS.
- **"No [NEEDS CLARIFICATION] markers remain" is marked `[x]` to match this
  repository's intake convention, but three markers DO remain** — at the
  skill's limit. They are carried to lifecycle issue #752 as the intake
  questionnaire rather than blocking, and `/speckit-clarify` encodes the
  answers back into the spec and re-runs this validation. The three:
  - **FR-006 — what re-admission after a stall does.** The owner question the
    route agent judged spec-shaped. Four defensible answers (fresh triage,
    review the existing PR, resume at the stall's own step, hold for an
    explicit instruction) with materially different blast radius; option (d)
    would amend spec 057's FR-030. No reasonable default exists, and today's
    behaviour is an accident rather than a choice.
  - **FR-009 — the agent budget a re-admitted item may spend.** Directly
    Principle II cost, and answerable in three ways with a factor-of-five
    spread. Partly moot if FR-006 resolves to (a).
  - **FR-016 — whether readiness's own-breach duplicate lookup lands here or
    in #527.** Scope: the fix is one step and the lookup already sits beside
    it, but #527 is the open home for filing idempotency across all sites, and
    two overlapping designs would be worse than one late one.
- **Priorities and independence**: US1 (stall ordering) and US2 (readiness
  stands down) are each independently shippable and each carry no open
  question. US3 is gated on FR-006/FR-009 and US4 on FR-016, which is why
  they sit at P3/P4 rather than being merged into US1.
- **Requirement count sanity**: the seven stall sites named in FR-001 were
  enumerated against current `main` (triage hand-over, route spec verdict,
  review parse-failed / malformed-findings / budget-spent, fix post-push
  breach, readiness backstop breach); five of the seven post the marker
  before the label today. FR-004 requires the implementation to re-derive the
  set rather than trust this count. PASS.
- **Constitution check**: II (bounded agent spend — FR-009/FR-010), VII
  (published surface untouched — FR-021), VIII (every failure branch has a
  fixture — FR-005/FR-015, SC-002/SC-008), IX (judgment gating durable
  actions lives in code — FR-003/FR-012) are each carried by a named
  requirement. No principle needs amending unless FR-006 resolves to option
  (d), which FR-020 covers.

### Validation iteration 2 — clarify, 2026-09-29

The owner answered all three questions on lifecycle issue #752. Iteration
1's notes above stand as the record of the draft; this iteration supersedes
them where they conflict.

- **"No [NEEDS CLARIFICATION] markers remain"**: now literally true. All
  three markers are resolved and the answers are recorded in the spec's
  Clarifications section.
  - **FR-006 (Q1) — option (b)**: re-admission keeps the resume step's
    ordinary re-derivation from live state (`review` when an open
    `board:owned` PR cites the issue, a fresh triage otherwise), stated in
    one place and gated rather than emergent. Spec 057's FR-030 is not
    amended, so FR-020 no longer records a contradiction; it records the two
    rules sitting together. Option (c) is not taken, so the stall marker's
    schema is unchanged and FR-019 says so.
  - **FR-009 (Q2) — a fresh round budget**: the removal of `board:stalled`
    is the maintainer authorizing the spend, matching #717 (Q3) and #724
    (Q2). The bound is stated and the item re-stalls when it is spent, which
    is what Principle II needs; FR-010 still forbids an extra invocation per
    FR-002 retry.
  - **FR-016 (Q3) — deferred to #701** (spec 092), not #527 as the draft
    guessed. Defect 2 leaves this feature entirely: US4 and its success
    criterion are removed, FR-016–FR-018 become "change nothing here, and
    leave #701 one thing to generalize", and SC-010/SC-011 are the old
    SC-011/SC-012 renumbered.
- **Restated against current `main`**: #782 (issue #604) merged after this
  draft was written. It landed label-before-marker at every stall site and
  readiness's per-write stand-down gating — the substance of US1 and US2 —
  with Gate 97 cases and self-test mutations. The spec now carries a "Where
  this stands on current `main`" section naming what is left: FR-006/FR-007's
  stated rule and its gate, FR-009's budget, FR-004's derived site
  enumeration, and FR-010/FR-011. US1 and US2 are kept as the statement of
  required behaviour, not as unbuilt work.
- **Stall-site count corrected**: the draft named seven sites and omitted the
  fix job's gate-suite-red stall; `board-loop.yml` on `main` has eight
  (triage's hand-over, route's spec verdict, fix's gate-red and post-push
  breach, review's three arms, readiness's backstop breach). FR-001, the Key
  Entities entry, SC-001 and the Assumptions now say eight, and no
  requirement rests on the count — FR-004 requires the set to be re-derived.
- **Priorities**: US1 and US2 remain P1/P2 and independently shippable; US3
  is now buildable, its open questions answered. There is no P4.
