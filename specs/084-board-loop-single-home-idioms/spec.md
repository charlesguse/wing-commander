# Feature Specification: Single-home the remaining board-loop idioms

**Feature Branch**: `084-board-loop-single-home-idioms`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue #607, routed from the board loop (originating issue #462): "board-loop.yml duplicates the kill-switch recheck (and smaller idioms) across its six jobs". Found by the code review of #451 (Reuse and Conventions angles, independently).

## Context

`CLAUDE.md`'s "Shared logic has exactly one home" section says that before a `run:` block, jq program, or shell helper is pasted into a second site, it is moved instead — cross-workflow shell belongs in a composite action under `.github/actions/`, and "when you consolidate something like this, add the single-home check to the nearest existing gate the same way — a rule with no gate behind it lasts until the next session."

The originating issue named three pasted idioms in `.github/workflows/board-loop.yml`. Triaged against current `main` (commit `e170077`):

1. **Kill-switch/stop-request recheck** — **already consolidated**. `.github/actions/wing-commander-board-stop-check` exists and all six jobs (triage, route, fix, review, readiness, prove) reach the idiom only through it. The drifting comment prose the issue flagged is gone with it. What did **not** land alongside the extraction is the structural single-home check `CLAUDE.md` asks for: the composite's behaviour is covered by `verify-board-stop-check.py`, but nothing fails when a *seventh* site re-pastes the `gh api` pagination → `find_stop_request` → `gh run cancel` → `paused=` shell somewhere else.

2. **PR-branch resolution** — **still duplicated**, 2 sites. The `review` job's "Resolve the PR under review" step and the `readiness` job's "Resolve the PR under readiness" step each run the same `gh pr view … --json headRefName --jq .headRefName` read and the same `{ echo "pr-number=…"; echo "branch=…"; } >> "$GITHUB_OUTPUT"` write.

3. **Board-item-marker write bootstrap** — **still duplicated**, 17 sites across five jobs. Each is an inline `python3 -c` one-liner that inserts a scripts directory onto `sys.path`, imports `write_marker` (sometimes alongside `BREACH_STEP` or `AWAITING_MERGE_STEP` from `board_eligibility`), and prints the result. The 17 sites come in two spellings that are **not** interchangeable: six use the working tree (`sys.path.insert(0, '.github/scripts')`, in triage/route/prove) and eleven use the pristine snapshot (`os.path.join(os.environ['RUNNER_TEMP'], 'wc-pristine', 'scripts')`, in fix/review/readiness, where Gate 98 — `verify-board-loop-helper-provenance.py` — requires every helper import to come from a copy taken before any agent step).

The risk is the one `CLAUDE.md`'s own worked example names: a fix that has to land N times, with nothing failing on a drifted copy. `board_item_marker.write_marker()` already changed shape once (issue #555/#580 added the `**Run:**` line); the next change to how a marker is produced has 17 landing sites.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The marker-write bootstrap has one home (Priority: P1)

A maintainer changes how a board item marker is produced — a new field, a different announcement line, a different failure behaviour when an environment variable is missing. They change it in one place, and every board-loop job that writes a marker picks the change up.

**Why this priority**: 17 sites is the largest paste in the file and the one with an already-demonstrated change cadence. It is also the one that interacts with a hard constraint (Gate 98's provenance allowlist), so getting it right is the load-bearing decision of this feature.

**Independent Test**: Change the marker's rendered output in its single home; confirm without editing `board-loop.yml` that every marker-writing step in every job emits the new output, and that the fix, review and readiness jobs still satisfy the pristine-snapshot provenance rule.

**Acceptance Scenarios**:

1. **Given** the marker-write idiom has a single home, **When** a maintainer greps `board-loop.yml` for the `sys.path` + `board_item_marker` bootstrap, **Then** no inline re-typing of it remains at any of the 17 former sites.
2. **Given** a marker-writing step inside the fix, review or readiness job, **When** Gate 98 runs, **Then** it passes — the step still resolves its helper from the pristine snapshot taken before any agent step, never from the working tree.
3. **Given** a marker-writing step inside the triage, route or prove job, **When** it runs, **Then** it produces byte-identical output to the inline one-liner it replaced, for every `step`/`round`/`pr`/`branch`/`base_sha` combination those sites pass today — including the two sites that resolve `BREACH_STEP` and `AWAITING_MERGE_STEP` from `board_eligibility`.
4. **Given** the consolidation has landed, **When** a new marker-writing site is added anywhere that re-types the bootstrap inline instead of using the single home, **Then** a gate fails.

---

### User Story 2 - PR-branch resolution has one home (Priority: P2)

A maintainer changes how the loop resolves the branch of the PR a job is about to act on — a different token, a fallback when the read fails, a refusal when the PR is closed. They change it once and both the review and readiness jobs follow.

**Why this priority**: only 2 sites, but they are the step that decides which ref two agent-bearing jobs check out — the copies diverging is a correctness problem, not only a maintenance one. Smaller and independent of User Story 1, so it can ship on its own.

**Independent Test**: Change the resolution behaviour in its single home; confirm both the review and readiness jobs check out the same ref they would have, and that neither job's `run:` block still contains the `gh pr view … headRefName` read.

**Acceptance Scenarios**:

1. **Given** the PR-branch idiom has a single home, **When** the review and readiness jobs resolve their PR, **Then** both reach the idiom through that home and neither re-types the `gh pr view` read or the `GITHUB_OUTPUT` write.
2. **Given** the review job, **When** it resolves its PR, **Then** it still emits the `round` value it emits today — the round is the loop's own bookkeeping, carried by the caller, never re-derived from the PR.
3. **Given** the `gh pr view` read fails or returns an empty branch name, **When** either job resolves its PR, **Then** the job fails loudly rather than continuing with an empty ref.
4. **Given** the consolidation has landed, **When** a third site re-types the PR-branch read, **Then** a gate fails.

---

### User Story 3 - Every consolidated board-loop idiom is gated (Priority: P3)

A maintainer (or an agent) pastes a consolidated idiom into a new site. A gate fails on the pull request, naming the idiom and its declared home.

**Why this priority**: it is the half of `CLAUDE.md`'s rule that the already-landed kill-switch consolidation skipped. Without it, each of the three consolidations is a convention a reviewer has to remember. It depends on User Stories 1 and 2 having declared homes to point at, so it is last — but it also retroactively covers the kill-switch recheck, which has a home and no structural check today.

**Independent Test**: For each of the three idioms, introduce a re-paste at a new site in a scratch copy of the tree and confirm the gate fails; remove it and confirm the gate passes.

**Acceptance Scenarios**:

1. **Given** the kill-switch/stop-request recheck idiom, **When** its shell is re-pasted into any workflow or composite outside `wing-commander-board-stop-check`, **Then** a gate fails.
2. **Given** the marker-write bootstrap idiom, **When** it is re-typed inline at a new site, **Then** a gate fails.
3. **Given** the PR-branch resolution idiom, **When** it is re-typed at a new site, **Then** a gate fails.
4. **Given** each new check, **When** the gate's own self-test runs, **Then** each failure branch it ships is exercised by a checked-in fixture — the check is proven able to fail its subject, not merely present (Constitution VIII).
5. **Given** a deviation a maintainer decides to keep, **When** it is registered in the existing waiver file with a reason and a tracking issue, **Then** the gate passes — and it fails again if the waiver's pattern stops matching or its count changes.

---

### Edge Cases

- A marker-writing site that needs a value not on today's `write_marker` signature (a future sixth field): the single home must be extendable without reintroducing an inline spelling at that one site.
- The two marker-write sites that also import a constant from `board_eligibility` (`BREACH_STEP`, `AWAITING_MERGE_STEP`): the single home must cover them, or they become the first drifted copy on day one.
- The `review` job's marker write that computes `next_round` in the caller's shell before rendering: the round is caller state, so the single home takes it as a value and does not derive it.
- A site that passes `null` for `pr`/`branch`/`base_sha` (the `stalled` markers) versus one that passes integers and strings: the single home must distinguish an absent value from an empty string, since the marker's JSON shape is read back by `read_marker`.
- A new board-loop job that writes a marker but takes no pristine snapshot: the single home must not silently give it a working-tree helper import that Gate 98 would have refused had it been spelled inline.
- The gate's pattern matching a structurally similar but conceptually distinct piece of shell elsewhere in the fleet (the case the existing waiver file exists for) — a false positive must be resolvable in the open, with a reason, not by loosening the pattern.
- The kill-switch composite is called by six jobs with the same five inputs; a seventh caller is legitimate, a seventh *re-paste* is not. The gate must tell those apart.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The board-item-marker write bootstrap MUST have exactly one home, and every marker-writing site in `board-loop.yml` MUST reach it through that home rather than re-typing the `sys.path` insertion and `board_item_marker` import inline.
- **FR-002**: That single home MUST serve both provenance contexts — the jobs that run helpers from the working tree and the jobs that run them from the pristine snapshot — without either context losing the guarantee it has today. A site inside the fix, review or readiness job MUST continue to resolve its helper from the snapshot taken before any agent step.
- **FR-003**: The consolidated marker write MUST produce output byte-identical to the current inline spelling for every argument combination the 17 existing sites pass, including the two that resolve a step constant from `board_eligibility`.
- **FR-004**: The consolidated marker write MUST preserve the distinction between an absent field (`null` in the marker JSON) and an empty string, so `read_marker` reads back what `write_marker` wrote.
- **FR-005**: The consolidation MUST NOT change any marker's rendered text, the `**Run:**` announcement line, or the order of a comment's contents — this feature moves the idiom, it does not redesign it. [NEEDS CLARIFICATION: how should the marker-write bootstrap be consolidated given Gate 98's provenance allowlist — a command-line entrypoint on the existing helper module invoked from each provenance context's own scripts directory, a composite action, or a shell helper script snapshotted alongside the other helpers?]
- **FR-006**: PR-branch resolution MUST have exactly one home, and both the `review` job's "Resolve the PR under review" step and the `readiness` job's "Resolve the PR under readiness" step MUST reach it through that home.
- **FR-007**: The PR-branch single home MUST expose the PR number and the resolved head branch name to its caller, and MUST NOT own the review round — the round remains caller state that the `review` job continues to emit unchanged.
- **FR-008**: The PR-branch single home MUST fail loudly when the underlying read fails or yields an empty branch name, rather than returning an empty ref that a later checkout would interpret as the default branch.
- **FR-009**: The PR-branch single home's placement MUST be a deliberate decision about the published contract, recorded in the feature's own artifacts. [NEEDS CLARIFICATION: should the PR-branch resolution composite be published (a `wing-commander-*` action, whose inputs and outputs become an adopter-pinned compatibility surface under Constitution VII) or internal (under `.github/actions/_shared/`, not part of the adopter-pinned surface)?]
- **FR-010**: A structural check MUST exist for each of the three idioms — kill-switch/stop-request recheck, marker-write bootstrap, PR-branch resolution — that fails when the idiom is re-pasted at a site other than its declared home, anywhere under `.github/workflows/` or `.github/actions/`.
- **FR-011**: The kill-switch/stop-request recheck MUST gain such a check in this feature even though its home already exists, closing the gap the earlier consolidation left.
- **FR-012**: Each new check MUST be able to fail its own subject: every failure branch it ships MUST be exercised by a checked-in fixture or a mutation self-test, not by a manual demonstration (Constitution VIII).
- **FR-013**: Each new check MUST be reachable through the gate registry, MUST run the same subject with the same arguments locally as in CI, and MUST be triggered by changes to the files it checks.
- **FR-014**: Deviations from a declared home MUST be registrable in the existing single-home waiver file, carrying a file, a check name, a pattern, a count, a tracking issue and a reason — and the waiver MUST be stale-checked in both directions, so a pattern that matches nothing and a count that no longer matches each fail the gate.
- **FR-015**: Where the new checks live MUST be a single decision applied to all three idioms, so a future maintainer looking for "the single-home check" finds one place. [NEEDS CLARIFICATION: should the three new checks extend the existing cross-workflow single-home gate's declared-homes list, or be added to each idiom's own nearest existing gate?]
- **FR-016**: The consolidation MUST NOT change any observable board-loop behaviour: the same markers are written at the same points, the same refs are checked out, the same jobs pause on the same stop signals.
- **FR-017**: The full PR-time gate suite MUST pass on the change, including the workflow-comment gates that byte-compare and mutate comment prose.

### Key Entities

- **Declared home**: the single file that owns an idiom's implementation — a composite action, a helper module entry point, or a shared script — named in the gate that enforces it.
- **Idiom**: a recognisable shell/Python fragment that has been pasted more than once; identified by a co-occurrence of fragments distinctive enough not to match unrelated code.
- **Board item marker**: the HTML-comment payload (`step`, `round`, `pr`, `branch`, `base_sha`) the loop appends to its own status comments, plus the `**Run:**` announcement line that precedes it.
- **Provenance context**: which scripts directory a board-loop step imports helpers from — the working tree, or the read-only pristine snapshot taken from the running commit before any agent step.
- **Waiver**: a registered, stale-checked exception to a declared home, carrying a reason and a tracking issue.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The number of sites in `board-loop.yml` that re-type the marker-write bootstrap inline drops from 17 to 0.
- **SC-002**: The number of sites that re-type the PR-branch read drops from 2 to 0.
- **SC-003**: A change to how a board item marker is rendered lands in exactly 1 file and is picked up by all 5 marker-writing jobs, verifiable without editing the workflow.
- **SC-004**: Introducing a re-paste of any of the 3 consolidated idioms at a new site causes at least one gate to fail, demonstrated by a checked-in fixture for each of the 3.
- **SC-005**: Each new check's failure branches are each exercised by a checked-in fixture or mutation self-test — 0 failure branches proven only by a manual demonstration.
- **SC-006**: Board-loop behaviour is unchanged: every marker the loop writes before the change is byte-identical to the marker it writes after, for all argument combinations the existing sites use.
- **SC-007**: The full PR-time gate suite passes, and Gate 98's provenance allowlist still passes for the fix, review and readiness jobs.
- **SC-008**: 0 new waivers are needed for this feature's own consolidation; any waiver that does land names a tracking issue and a reason.

## Assumptions

- The kill-switch/stop-request recheck (item 1 of the originating issue, and the one the issue called "the main one") is already consolidated on `main` into `.github/actions/wing-commander-board-stop-check`; this feature's remaining work on it is the missing structural single-home check, not another extraction.
- The behaviour of `write_marker`, `read_marker`, and `find_stop_request` is correct as-is and out of scope; this feature moves call sites, not semantics.
- Gate 98's provenance rule is a hard constraint that this feature works within, not one it may relax — the fix, review and readiness jobs keep importing helpers from the pristine snapshot.
- The `review` job's `round` output and the `readiness` job's lack of one are deliberate, not drift, and stay as they are.
- The existing single-home waiver file's shape (`{file, check, pattern, count, issue, reason}`) and its both-directions stale check are reused rather than re-invented.
- Consolidating an idiom that lives entirely inside one file is in the spirit of `CLAUDE.md`'s rule even though the rule's wording is about a *second workflow*; the cost the rule prevents — N landing sites with nothing failing on a drifted copy — is the same.
- No change to the adopter-facing behaviour of the board loop is intended; whether the adopter-facing *surface* widens is the open question in FR-009.
- The three consolidations are independently shippable; a plan may sequence them, but none blocks the others.

## Out of Scope

- Any change to what the board loop decides — triage verdicts, routing, merge gating, stop-request semantics.
- Consolidating idioms in workflows other than `board-loop.yml`.
- Repointing the two consolidations that already carry waivers for unrelated reasons (`pr-conversation.yml`'s size-path backstop, `auto-release.yml`'s dispatch-and-wait).
- Rewriting or deduplicating comment prose beyond what moving a `run:` block necessarily moves.
