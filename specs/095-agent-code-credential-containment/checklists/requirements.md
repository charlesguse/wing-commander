# Specification Quality Checklist: Agent-Authored Code Never Runs Beside the Loop's Write Token

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

- All three [NEEDS CLARIFICATION] markers are resolved. The intake stage runs
  headless and does not wait for answers, so the questions were posted to
  lifecycle issue #737 and answered there; the clarify stage folded the
  answers in. The decisions:
  - **FR-005** (scope) — **widened beyond the board loop.** The containment
    applies to every job that runs an agent and later performs a durable
    action with the App token: the board loop's two gate-suite call sites plus
    `implement`, `converge` and `pr-conversation`. Bounding it to the board
    loop would have left a known equivalent exposure recorded but open. The
    consequence to carry into planning: the feature now touches the published
    stage surface, not only `board-loop.yml` (recorded in Assumptions).
  - **FR-006** (security, mechanism class) — **a separate `permissions: read`
    job with no App token**, the verdict returned as an artifact that fails
    closed when absent or malformed. Chosen over in-place environment
    scrubbing and a stronger isolation boundary because it is the only
    candidate that also closes FR-007 and FR-008: the agent's code no longer
    shares a filesystem or a `$GITHUB_ENV` with the steps that push.
  - **FR-018** (security) — **both**, each behind its own structural gate: a
    `.git/**` deny in the covered agents' disallowed tools, and hardened push
    steps. The answer corrected this question's premise: disallowed tools are
    enforced by the harness, not honoured at the model's discretion, so the
    deny is a real boundary and Principle IX does not weaken it. The push
    hardening is still required, for plants arriving by routes the tool
    allowlist does not govern.
- Named job names, step names, composite names, file paths and environment
  variables appear in the Overview, Edge Cases and Key Entities as *evidence
  of the reported exposure* and as the boundary of the change — the same
  convention spec 086's checklist records. The functional requirements
  themselves name behaviours (what must not be reachable, what must not be
  alterable, what must fail closed) rather than mechanisms. The two places a
  requirement names a concrete artifact — the gate suite's entry point and
  `wing-commander-board-stop-check` — are named because they are the
  deliberate carve-out the fix must preserve and the one known instance of
  FR-011 respectively.
- Success criteria are stated as observable outcomes counted over fixtures
  and re-driven runs. They were written to stay valid under any of FR-006's
  three candidate strategies and were not rewritten when option (a) was
  chosen; only their scope widened to match FR-005.
- The Overview records three sibling items from the originating issue that
  have since been closed (spec 086's composite resolution, the reviewer's
  `git_read.py` grant, and #593's `\Z` translation), and FR-023 forbids
  re-implementing them. This is scope bounding, not history.
- Counts are stated as "every composite reachable from the affected jobs"
  and "both call sites" rather than literal numbers, so the requirements
  cannot go stale as call sites move.
- FR-006 and FR-018 now name concrete mechanisms (a separate credential-free
  job with an artifact verdict; `core.hooksPath`, `GIT_CONFIG_GLOBAL`,
  `GIT_CONFIG_NOSYSTEM`, an explicit push URL). That is deliberate: these were
  owner trade-off decisions, and recording the chosen option is the point of
  the clarification. The "no implementation details" boxes above stay checked
  on the reading that a resolved decision is part of the requirement, not a
  design leak.
- Remaining items are complete; with all three clarifications folded in, the
  spec is ready for `/speckit-plan`.
</content>
</invoke>
