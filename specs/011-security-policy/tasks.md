---

description: "Task list for SECURITY.md Vulnerability-Reporting Policy"
---

# Tasks: SECURITY.md Vulnerability-Reporting Policy

**Input**: Design documents from `/specs/011-security-policy/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/security-md-convention.md, quickstart.md

**Tests**: Not requested — this is a single static Markdown file with no code and no automated test suite. Validation is the manual `quickstart.md` procedure, captured below as the Polish phase task.

**Organization**: Tasks are grouped by user story. Both stories add content to the same single new file, `SECURITY.md`, so there is no cross-file parallelism; tasks are ordered sequentially within that one file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

## Phase 1: Setup

**Purpose**: Confirm the ground the implementation builds on.

- [ ] T001 Confirm `SECURITY.md` does not already exist at the repository root and that no other pending change in this branch touches any file besides the new one to be created (FR-007, SC-004).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the file and its single top-level heading that every user story's content is added under.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Create `SECURITY.md` at the repository root with exactly one top-level (`#`) heading naming the security policy (e.g. "Security Policy"), per the contract in `specs/011-security-policy/contracts/security-md-convention.md` (FR-001, FR-006, SC-002).

**Checkpoint**: `SECURITY.md` exists with its heading — user story content can now be added.

---

## Phase 3: User Story 1 - Report a vulnerability through the private channel (Priority: P1) 🎯 MVP

**Goal**: A visitor who finds the policy (via the Security tab or the file itself) learns to use GitHub's private vulnerability reporting rather than a public issue.

**Independent Test**: Open the repository's Security tab (or read `SECURITY.md` directly) and confirm it names GitHub's private vulnerability reporting as the intended channel and explicitly discourages public issues.

### Implementation for User Story 1

- [ ] T003 [US1] Add a body paragraph to `SECURITY.md` directing reporters to GitHub's private vulnerability reporting for this repository (Security tab → "Report a vulnerability") and stating that public issues are not the channel for vulnerability reports (FR-002, FR-003, SC-003(1), SC-003(2)).

**Checkpoint**: `SECURITY.md` alone satisfies User Story 1 — a reporter reading it knows the private channel and knows not to use public issues. Independently testable now.

---

## Phase 4: User Story 2 - Understand that credential handling is in scope (Priority: P2)

**Goal**: A reporter learns that pipeline runs execute Claude agents with repository write access via a GitHub App, and that credential-handling reports (leaked tokens, overly broad permissions) are explicitly welcome.

**Independent Test**: Read `SECURITY.md` and confirm it states that pipeline runs execute Claude agents with repository write access via a GitHub App, and that credential-handling reports are explicitly in scope.

### Implementation for User Story 2

- [ ] T004 [US2] Add a body paragraph (or extend the existing one, staying within the three-paragraph ceiling) to `SECURITY.md` stating plainly that pipeline runs execute Claude agents with repository write access via a GitHub App, and that credential-handling reports — including leaked tokens and overly broad permissions — are explicitly in scope (FR-004, FR-005, SC-003(3), SC-003(4)).

**Checkpoint**: Both user stories are satisfied — `SECURITY.md` now carries all four required disclosures within at most three body paragraphs.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation against the full requirement set.

- [ ] T005 Run the `specs/011-security-policy/quickstart.md` validation end-to-end: confirm `git diff --stat` shows exactly one changed file (`SECURITY.md`), exactly one top-level heading, at most three body paragraphs, all four required disclosures present, and (post-merge or via branch preview) that the Security tab surfaces the policy in one click (FR-006, FR-007, SC-001…SC-004).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS both user stories (the file and its heading must exist before body paragraphs are added).
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion. No dependency on User Story 2.
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion. Builds on the same file as US1 but adds an independently-verifiable disclosure; does not require US1's paragraph to exist first, though in practice both land in the same commit.
- **Polish (Phase 5)**: Depends on both user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — no dependency on User Story 2.
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) — no dependency on User Story 1, though both edit `SECURITY.md` so cannot literally run in parallel without a merge conflict.

### Within Each User Story

- Each story adds exactly one body paragraph to the single shared file.
- Story complete before moving to next priority.

### Parallel Opportunities

- None in the strict sense: every task after T002 edits the same single file, `SECURITY.md`. Tasks are listed sequentially by design (see plan.md's Structure Decision — one file, no source tree). This mirrors the project's smallest-prior-precedent pattern of a single shared file with limited parallelism.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (creates the file and heading).
3. Complete Phase 3: User Story 1 (reporting-channel paragraph).
4. **STOP and VALIDATE**: Confirm the Security tab / file names the private channel and discourages public issues.
5. This alone is a mergeable, valuable increment: a discoverable policy exists.

### Incremental Delivery

1. Setup + Foundational → file with heading exists.
2. Add User Story 1 → validate independently → mergeable MVP.
3. Add User Story 2 → validate independently → full policy complete.
4. Run Polish (Phase 5) quickstart validation → ready for implementation PR.

## Notes

- [Story] label maps task to specific user story for traceability.
- No [P] markers are used: all tasks after Setup touch the same single file, `SECURITY.md`, so none can run concurrently without conflicting.
- Commit after each task or logical group.
- Stop at either checkpoint (T003 or T004) to validate that story's disclosures independently before proceeding.
- Avoid: adding a fourth body paragraph, touching any file other than `SECURITY.md` (FR-007).
