# Feature Specification: Gate Number Allocation and Collision Detection

**Feature Branch**: `103-gate-number-allocation`

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Concurrent specs each claim the next free gate number, so every Finalize PR after the first collides. Each spec's tasks stage assigns its new gate 'the highest number in lint-workflows.yml + 1' as of when that branch was planned. When several specs are in flight at once, they all pick the same number. On 2026-09-28 there were ten open Finalize PRs; eight branches each added a 'Gate 99', and specs 060, 062, 066, 067, 079 and 086 also added a 'Gate 100'. Nothing fails on the collision itself — lint-workflows.yml can carry two steps named 'Gate 99', and no gate checks that gate numbers are unique. The damage shows up later: a gate that finds its own lint step by name prefix (GATE_PREFIX) can match the wrong step and fail in a way that looks unrelated (#463); the script's docstring, messages and file name plus the spec docs keep the stale number after the lint step is renumbered at rebase (#619, #620, #646 — CI printed 'Gate 99:' under a step named Gate 100); and every merge forces a renumbering round on each other open PR, costing an implement cycle apiece. Fix shape: (1) a uniqueness gate that fails if two lint-workflows.yml steps share a 'Gate N' or 'Gate N self-test' number, and fails when a script's own 'Gate N' label (docstring, GATE_PREFIX, or ::error::Gate N messages) differs from the number of the lint step that invokes it; (2) an allocation scheme — the owner's call between numbering at merge time in the rebase stage, keying gates by spec (e.g. 'Gate 079-a'), or reserving a number with a marker on main."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A colliding gate number is caught before it merges (Priority: P1)

A maintainer (or a pipeline implement stage) opens a PR that adds a new numbered gate step to the lint workflow. Another open PR already claims that number. Today both PRs are green, both merge, and the collision is discovered later as an unrelated-looking failure. With this feature, whichever PR is rebased onto the other's merge gets a red check that names both steps and the number they share, so the number is corrected in the PR that is already open rather than in a follow-up cycle.

**Why this priority**: This is the half of the fix that is deterministic and gate-shaped, and it converts every failure mode in this feature's history from silent drift into a red check at rebase time. It delivers value on its own even if no allocation scheme is ever adopted.

**Independent Test**: Add a second gate step carrying an existing gate number to the lint workflow in a scratch checkout, run the PR-time gate suite, and confirm it fails naming both steps. Remove the duplicate and confirm it passes.

**Acceptance Scenarios**:

1. **Given** a lint workflow whose steps carry distinct gate numbers, **When** the check runs, **Then** it passes and reports how many gate steps it compared.
2. **Given** a lint workflow with two steps both named `Gate 99 — ...` for two different subjects, **When** the check runs, **Then** it fails, naming both step names and the shared number.
3. **Given** a gate step and its own self-test step sharing a number (`Gate 80` and `Gate 80 self-test`), **When** the check runs, **Then** it passes — a gate and its self-test are distinct roles and legitimately share one number.
4. **Given** two *self-test* steps both named `Gate 23 self-test`, **When** the check runs, **Then** it fails, because both occupy the same role under the same number.
5. **Given** a lint workflow the check cannot parse, or one from which it extracts zero gate steps, **When** the check runs, **Then** it fails loudly rather than reporting a pass it did not earn.

---

### User Story 2 - A gate's own label matches the step that invokes it (Priority: P1)

A gate script prints `Gate 99:` in its output, carries `Gate 99` in its docstring, and matches its own lint step through a `Gate 99` prefix constant. At rebase the lint step was renumbered to `Gate 100`, but nothing in the script moved. CI now prints one number under a step named another, and the prefix constant can silently bind to a *different* gate's step whose name happens to start with the same characters. With this feature the mismatch is a red check naming the script, the label it carries, and the number of the step that actually invokes it.

**Why this priority**: This is the failure mode that already cost three issues (#619, #620, #646) and one misdiagnosed gate failure (#463). It is independent of uniqueness: a repository with no duplicate numbers at all can still ship a script whose self-description is stale.

**Independent Test**: Change one gate script's `Gate N` label to a different number without touching its lint step, run the gate suite, and confirm it fails naming both numbers; revert and confirm it passes.

**Acceptance Scenarios**:

1. **Given** a script whose docstring, step-matching prefix and error messages all say `Gate 30`, invoked by a lint step named `Gate 30 — ...`, **When** the check runs, **Then** it passes.
2. **Given** that same script after its lint step is renumbered to `Gate 31` with the script untouched, **When** the check runs, **Then** it fails, naming the script, the stale number and the step's number.
3. **Given** a script whose docstring says one number and whose printed messages say another, **When** the check runs, **Then** it fails on the internal disagreement even if one of the two matches the lint step.
4. **Given** a gate that lives entirely inside a workflow `run:` block with no script, **When** the check runs, **Then** its number participates in the uniqueness comparison and the label-consistency rule applies to the labels inside that block.
5. **Given** a gate script whose step-matching prefix is `Gate 2` while the workflow also contains steps named `Gate 22` and `Gate 23`, **When** the check runs, **Then** it fails, because the prefix does not identify exactly one step.

---

### User Story 3 - Two specs in flight never claim the same number (Priority: P2)

Ten Finalize PRs are open. Each was planned against a different snapshot of the lint workflow. Under the allocation scheme adopted for this feature, each spec's gate carries an identity that does not depend on what the other nine chose, so merging one does not force a renumbering commit on the other nine.

**Why this priority**: This is the half that removes the recurring cost rather than reporting it. It depends on an owner decision (see Clarifications) and is worth less on its own than the checks above, because without those checks nothing would hold a new scheme in place either.

**Independent Test**: Simulate two branches that each add a gate without knowledge of the other, merge both, and confirm the resulting tree passes the uniqueness check with no renumbering commit on either branch.

**Acceptance Scenarios**:

1. **Given** two branches that each add a new gate and neither has seen the other, **When** both are merged, **Then** the merged tree has no duplicate gate identity and neither branch needed a renumbering commit.
2. **Given** a branch whose gate identity was fixed before rebase, **When** it is rebased onto a `main` that gained other gates, **Then** the branch's gate identity is unchanged or is rewritten by the pipeline rather than by a human implement cycle.
3. **Given** the adopted scheme, **When** a maintainer reads a failing check's name in the GitHub UI, **Then** the identity still points unambiguously at one gate's subject.

---

### Edge Cases

- **A gate and its self-test.** `Gate 80` and `Gate 80 self-test` are two steps sharing one number by design. So are the multi-step gates that exist on `main` today (`Gate 71` appears three times — check, fixture check, self-test). The rule must not mistake the intended structure for drift.
- **Pre-existing collisions on `main`.** As of this spec, `lint-workflows.yml` already carries two unrelated `Gate 22` steps (agent-verdict composite vs. runner/container-image passthrough), two unrelated `Gate 23` steps (turn-budget protection vs. image prerequisites) with two `Gate 23 self-test` steps, and two `Gate 86` steps. A check that hard-fails on first run turns `main` red. See Clarifications.
- **Sub-numbered identities.** `release.yml` names a `Gate 1a`; the comparison must handle whatever suffix forms the repository uses rather than assuming a bare integer.
- **Gate numbers outside the lint workflow.** Some gates are wired to other workflows (release, watchdog self-test). Their numbers share the same namespace as the lint workflow's.
- **One script, two lint steps.** A script CI invokes twice with different flags (`verify-gate-23.py --selftest`) is reached from more than one step; "the number of the step that invokes it" must resolve to a single answer or fail as ambiguous.
- **A number that is correct in isolation.** A branch is internally consistent and only collides once it meets `main`. The check's subject is the merged tree, which is what makes rebase time the moment it fires.
- **A number retired by a deleted gate.** Whether a freed number may be reused by the next gate, or is burned permanently, is a property of the adopted allocation scheme.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A pull-request-time check MUST fail when two gate steps in the lint workflow carry the same gate identity in the same role, and MUST name both step names and the shared identity in its failure output.
- **FR-002**: The check MUST treat a gate's main step and its self-test step as distinct roles that legitimately share one number, and MUST still fail when two steps of the *same* role share a number.
- **FR-003**: The check MUST accept a gate that is deliberately spread across more than one step of the same role only through a recorded, reasoned exception — never by a silent pattern exclusion.
- **FR-004**: The check MUST fail when a gate script's own gate label disagrees with the number of the lint step that invokes it. "Label" covers at minimum the script's docstring, any constant it uses to find its own step by name, and the gate identity in the messages it prints.
- **FR-005**: The check MUST fail when a gate script's own labels disagree with *each other*, independently of what the invoking step is named.
- **FR-006**: The check MUST fail when a script's step-matching constant does not identify exactly one lint step — zero matches or more than one.
- **FR-007**: The check MUST cover gates whose implementation is inlined in a workflow `run:` block as well as gates backed by a script file, for both the uniqueness rule and the label-consistency rule.
- **FR-008**: The check MUST fail loudly — never pass quietly — when it cannot reach its subject: the workflow is missing or unparsable, or the set of gate steps it extracted is empty.
- **FR-009**: The check MUST be reachable through the repository's gate registry, run the same subject with the same arguments locally as in CI, and be triggered by changes to the files it reads.
- **FR-010**: Every failure branch the check ships MUST be exercised by a checked-in fixture through the check's own self-test, not by a manual demonstration.
- **FR-011**: Failure output MUST tell the author what to change, not merely that something is wrong — for a duplicate, which two steps collide; for a mismatch, which label is stale and what the invoking step says.
- **FR-012**: Any pre-existing collision that is not resolved by this feature MUST be recorded in the open with a reason and a tracking reference, and MUST be stale-checked in both directions so the record cannot outlive the condition it excuses. [NEEDS CLARIFICATION: the default branch already carries same-role duplicates (`Gate 22`, `Gate 23`, `Gate 23 self-test`, `Gate 71`, `Gate 86`) — renumber them in this feature, seed the exception register with them, or narrow the rule so a gate deliberately split across same-role steps is not a duplicate?]
- **FR-013**: The pipeline MUST allocate a new gate's identity such that two specs in flight simultaneously cannot claim the same identity without one of them learning about the other. [NEEDS CLARIFICATION: which allocation scheme — renumber at merge time in the rebase stage, key gates by spec (`Gate 079-a`), reserve a number with a marker on `main`, or adopt no scheme and rely on the checks above alone?]
- **FR-014**: The rule the pipeline follows when allocating a gate identity MUST be written down in one place that the stage prompts point at, rather than being an unwritten convention each stage re-derives.
- **FR-015**: When a gate's identity changes, every live reference to it MUST move with it in the same change. [NEEDS CLARIFICATION: does "live reference" include the live documents under `docs/` and `specs/*/contracts/` that name a gate number, or only the lint step and its script? Merged `specs/NNN-*/spec.md`, `plan.md` and `tasks.md` are historical records this repository does not correct.]
- **FR-016**: Adopting this feature MUST leave the repository's existing gates passing — the change may renumber gates, but MUST NOT silently disable one.

### Key Entities

- **Gate identity**: The label that distinguishes one gate from every other (`Gate 99` today). Appears in a lint step's name, in the gate's own output, and in the script constant that binds the two together.
- **Gate role**: Which part of a gate a step is — the check itself, or its self-test. Two steps may share an identity only across different roles.
- **Gate step**: A step in a workflow that invokes a gate, either by running a script or by inlining the check.
- **Gate script**: The file under the scripts directory that implements a gate and carries its own copy of the identity in prose, constants and messages.
- **Collision record**: An open, reasoned entry excusing a gate identity that two same-role steps share, carrying a tracking reference and subject to staleness checking in both directions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A change that introduces a duplicate gate identity in the same role fails a required check on the pull request, 100% of the time, before it can merge.
- **SC-002**: A change that leaves a gate's own label disagreeing with the step that invokes it fails a required check on the pull request, 100% of the time — the class of defect behind #619, #620 and #646.
- **SC-003**: After this feature merges, the repository's default branch carries zero unrecorded same-role gate-identity duplicates, and every recorded one names a reason and a tracking reference.
- **SC-004**: A reader of a failing run can name the two colliding steps, or the stale label and its step, from the check's output alone, without opening the check's source.
- **SC-005**: With more than one spec in flight, merging one spec's gate forces zero renumbering commits on the other open branches.
- **SC-006**: Every failure branch of the new check is demonstrated by a checked-in fixture, and removing any one fixture's trigger condition makes the self-test fail.
- **SC-007**: The new check runs in the standard local gate sweep with the same subject and arguments CI uses, and an edit to either the lint workflow or a gate script triggers it on the pull request.
- **SC-008**: The allocation rule is stated in exactly one place; no second copy of it exists in a stage prompt or document.

## Assumptions

- Gate identities remain human-readable labels that appear in step names, so a maintainer can still read a failing check's name in the GitHub UI and know which gate failed. Any scheme that replaces the global sequence keeps that property.
- The lint workflow remains the primary home for numbered gate steps; gates wired to other workflows are in scope for uniqueness but are not expected to grow in number as part of this feature.
- The check is a pull-request-time gate like the repository's existing ones — the same suite, the same local runner — and not a new mechanism.
- Numbers already burned by merged gates are not reclaimed retroactively; this feature governs how the *next* gate is identified and how drift is caught, not a renumbering of the whole fleet (beyond whatever the pre-existing-collision decision requires).
- Merged `specs/NNN-*/` spec, plan, research and tasks documents are historical records and are not corrected when a gate is renumbered; only live documents and contracts are candidates for FR-015.
- Any exception register this feature adds follows the repository's existing waiver convention — reason, tracking reference, stale-checked in both directions.
- The implementation is a deterministic check plus, if a scheme is adopted, deterministic pipeline plumbing. No agent judgment gates the durable action.

## Open Questions

The following remain open at intake and are posted to the lifecycle issue for the requester to answer:

1. **Allocation scheme** (FR-013). Renumber at merge time in the rebase stage, key gates by spec, reserve a number with a marker on `main`, or ship the checks alone and keep the current convention.
2. **Pre-existing collisions on `main`** (FR-012, FR-016). `Gate 22`, `Gate 23`, `Gate 23 self-test`, `Gate 71` and `Gate 86` each name more than one step today. Renumber them as part of this feature, seed the exception register with them, or narrow the rule so that same-subject multi-step gates are not duplicates at all.
3. **Reach of the label-consistency rule** (FR-015). Lint step plus script only, or also the live documents and contracts that name a gate number.
