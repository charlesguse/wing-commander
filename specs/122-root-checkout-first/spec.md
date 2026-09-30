# Feature Specification: A Job's Root Checkout Runs Before Any Path-Scoped Checkout

**Feature Branch**: `spec-draft/122-root-checkout-first`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #866 — "Gate 60: a path-scoped sidecar checkout
placed before the job's root checkout passes, though the root checkout
wipes it". Originating issue #757, itself raised by the code review of
#683. A first, local fix attempt (PR #865) grew past the board's
size-and-path backstop by readiness time (measured: files=1, lines=125)
and was left open and unmerged, so the work arrives here to be sized by a
plan instead.

## Overview

Gate 60's `composite-checkout-order` check answers one question: does a
local `uses: ./...` step run **after** the `actions/checkout@` step that
populates the directory it resolves from? A bare `./.github/actions/...`
reference needs an earlier checkout with no `path:` (the workspace root);
a sidecar reference such as `./.wc-pristine-repo/.github/actions/...`
needs an earlier checkout whose `with.path` is that same first segment.

That is a **step-to-checkout** question. It leaves a
**checkout-to-checkout** question unasked, and the unasked one has the
same run-time cost.

`actions/checkout@v5` prepares its target directory before fetching. For
a checkout with no `path:`, the target is the workspace root, and on a
runner whose workspace root holds no `.git` the preparation removes every
entry it finds there — including a sidecar directory some earlier step
already populated. The removal is not a warning. A sidecar whose
permissions resist the removal turns it into an `EACCES` failure of the
checkout step; an ordinary sidecar is deleted silently and the job
continues until the first `uses: ./<sidecar>/...` step reports "Did you
forget to run actions/checkout".

So a job whose steps read

```yaml
- uses: actions/checkout@v5      # sidecar, populated first
  with:
    repository: ...
    path: .wc-pristine-repo
- uses: actions/checkout@v5      # root — wipes the sidecar
- uses: ./.wc-pristine-repo/.github/actions/some-composite
```

passes Gate 60 today. The sidecar checkout precedes the composite
reference, which is all the current check asks. It fails every time it
runs.

This is not hypothetical. PR #683 shipped exactly this order in
board-loop's `review` and `readiness` jobs with the whole gate suite
green; it was caught by manual review of the diff, which is the failure
mode the gate exists to remove. The gate could not fail its subject.

The fix the originating issue names is a single rule: **in a job that has
a root `actions/checkout` step, that root checkout is the job's first
`actions/checkout` step.** Any path-scoped checkout above it is populating
a directory the root checkout is about to remove. Plus the matching
self-test mutation — a fixture that moves a sidecar checkout above the
root one and must fail — because a rule with no mutation behind it is a
rule nobody has watched fail.

The rule itself is uncontroversial. What needs a decision is how far it
reaches (only `actions/checkout` steps, or every step that writes into the
workspace before the root checkout), whether an author can opt out by
declaring the root checkout non-destructive, and whether it reports under
the existing check name or its own. Those three choices change the size
of the change, the contents of the waiver register, and the gate step's
title — which gates byte-compare — which is why this is specced rather
than patched.

### Observed facts (verified against main at 717c9cd; re-check cited line numbers at plan time)

- `.github/scripts/verify-single-home-idioms.py:1008-1051`
  (`check_local_action_before_checkout`) walks each job's step list once,
  keeping `seen_root` (a checkout with no `with.path`) and `seen_scoped`
  (the set of `with.path` values seen). It raises a finding only on a
  `uses: ./...` step, and only when the directory that step resolves from
  has not yet been checked out. Nothing in the loop compares the position
  of a scoped checkout against the position of the root checkout.
- `.github/scripts/verify-single-home-idioms.py:135-145` and `987-1003`
  state the check's contract in exactly those step-to-checkout terms
  ("every workflow job's own step list scanned for a local `uses: ./...`
  step preceding the `actions/checkout@` step that actually populates the
  directory it resolves from"). The documented contract and the code
  agree; both are silent on checkout ordering.
- `.github/scripts/verify-single-home-idioms.py:294` — `CHECK_NAMES` is
  the tuple of declared-home check names plus `"promotion"` and
  `"composite-checkout-order"`. A waiver naming any other check is a hard
  failure (`check_waiver_shape`), so a new check name must be registered
  here before it can be waived.
- `.github/scripts/verify-single-home-idioms.py:1952-1969` — the two
  existing `composite-checkout-order` self-test mutations: a fixture whose
  composite reference precedes any checkout, and a fixture whose sidecar
  reference is preceded only by an unrelated root checkout. Both are
  expected to fail. There is no mutation for checkout-to-checkout order.
- `.github/workflows/lint-workflows.yml:3581-3586` — Gate 60 runs as two
  steps, the scan and `--self-test`, both gated `if: "!cancelled()"`, with
  titles that other gates byte-compare.
- `.github/workflows/board-loop.yml` — every job that uses a sidecar
  (`select`, `triage`, `route`, `fix`, `review`, `readiness`,
  `prove-gate`, `prove`) currently checks out the root first and
  `.wc-pristine-repo` second. The #683 order was corrected; main is
  believed to satisfy the new rule already (see Assumptions).
- The pipeline's own stage workflows (`implement.yml`, `finalize.yml`,
  `watchdog.yml`, `pr-conversation.yml`) all use the same
  `path: .wing-commander-pipeline` sidecar pattern, so the rule's subject
  population is every stage workflow, not one file.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The wiped sidecar fails at gate time (Priority: P1)

An agent or maintainer adds a sidecar checkout to a job and places it
above the job's root checkout. They run the gate suite locally
(`python .github/scripts/run-local-gates.py`) before pushing. Gate 60
fails, naming the file, the job and the offending step, and says the root
checkout must come first because it removes the sidecar. They reorder the
two steps and the gate passes.

**Why this priority**: this is the whole feature. Without it the defect
reaches a run and costs a manual review or a red run to find, which is
exactly what happened on #683.

**Independent Test**: take a workflow job in the current tree, swap its
root and sidecar checkout steps, run Gate 60, and confirm it fails with a
message that identifies that job; restore the order and confirm it
passes.

**Acceptance Scenarios**:

1. **Given** a job with a path-scoped checkout followed by a root
   checkout, **When** Gate 60 runs, **Then** it fails and its message
   names the workflow file, the job id, the path-scoped checkout's path
   and the reason (the root checkout removes it).
2. **Given** a job with a root checkout followed by a path-scoped
   checkout, **When** Gate 60 runs, **Then** it raises no finding for
   that job.
3. **Given** a job with one or more path-scoped checkouts and no root
   checkout at all, **When** Gate 60 runs, **Then** it raises no finding
   for that job — there is nothing to wipe the sidecars.
4. **Given** the current tree unmodified, **When** Gate 60 runs, **Then**
   it passes, and no waiver is needed to make it pass.

---

### User Story 2 - The new rule has been watched fail (Priority: P2)

A reviewer of the gate change wants evidence the rule can fail its
subject rather than merely existing. `--self-test` builds a fixture whose
sidecar checkout sits above the root checkout and asserts the scan
rejects it; the self-test fails loudly if that fixture ever starts
passing.

**Why this priority**: the defect being fixed *is* a rule that could not
fail its subject. A rule added without a mutation repeats it at one
remove.

**Independent Test**: run `verify-single-home-idioms.py --self-test` and
confirm it exercises and reports the new mutation; then neutralise the new
rule in the scan and confirm the self-test fails.

**Acceptance Scenarios**:

1. **Given** the shipped gate, **When** `--self-test` runs, **Then** it
   exercises a fixture with a sidecar checkout above the root checkout
   and asserts a finding is raised.
2. **Given** the new ordering rule removed or disabled, **When**
   `--self-test` runs, **Then** it exits non-zero naming that mutation.
3. **Given** a fixture whose job has a root checkout first and a sidecar
   second, **When** `--self-test` runs, **Then** that ordering is
   asserted clean, so the rule cannot pass by rejecting everything.

---

### User Story 3 - A deliberate exception is recorded, not invisible (Priority: P3)

A future job has a genuine reason to populate a directory before its root
checkout. The author cannot silence the rule by rearranging comments or
by adding an unrelated early checkout; the only route is the existing
waiver register, where the entry names the file, the check, the pattern,
the count and the reason, and is stale-checked like every other waiver.

**Why this priority**: valuable, but no such case exists in the tree
today. It matters that the escape hatch is the shared one rather than a
bespoke skip.

**Independent Test**: add a waiver for a deliberately misordered fixture
and confirm the gate passes; remove the misordering and confirm the gate
now fails on the stale waiver.

**Acceptance Scenarios**:

1. **Given** a misordered job and a matching waiver entry, **When** Gate
   60 runs, **Then** it passes and the waiver is counted.
2. **Given** a waiver for the new rule whose subject no longer matches,
   **When** Gate 60 runs, **Then** it fails asking for the waiver's
   removal, with the same wording every other stale waiver gets.
3. **Given** a waiver naming a check name the gate does not declare,
   **When** Gate 60 runs, **Then** it hard-fails, as it does today.

### Edge Cases

- **A job with several path-scoped checkouts and one root checkout.**
  Every scoped checkout above the root one is wiped. All of them should be
  reported, not just the first, so one pass of the gate gives the author
  the whole list.
- **A job with more than one root checkout.** The second root checkout
  wipes whatever the first one and everything after it produced. The rule
  as stated ("the root checkout is the job's first checkout") is about the
  first root checkout's position; a later root checkout is a separate
  hazard this feature does not have to solve, but it must not make the
  rule misreport.
- **A conditional checkout.** `watchdog.yml` has a sidecar checkout with
  `continue-on-error: true`, and `pr-conversation.yml` has sidecar
  checkouts behind `if:`. A step's `if:` is not knowable at gate time, so
  the rule treats every checkout step as if it runs; a gated sidecar above
  an ungated root checkout is still reported.
- **A root checkout declared non-destructive.** `clean: false` changes
  the run-time behaviour. Whether it changes the rule is
  [NEEDS CLARIFICATION: does a root `actions/checkout` step with
  `clean: false` (or an equivalent declaration that it will not clear the
  workspace) satisfy the rule, letting a sidecar precede it, or is the
  ordering absolute with the waiver register as the only exception?]
- **A non-checkout step that writes into the workspace before the root
  checkout** — `actions/download-artifact` with a `path:`, a cache
  restore, or a `run:` block creating a directory. The wipe does not care
  how the directory got there.
  [NEEDS CLARIFICATION: does the rule cover only path-scoped
  `actions/checkout` steps, or every step that demonstrably populates a
  workspace directory before the root checkout (e.g. `download-artifact`
  with `path:`, cache restores, `run:` blocks that create files)?]
- **A composite action's own `runs.steps`.** Composite steps execute
  inside the caller's already-prepared workspace and cannot contain the
  job's root checkout, so they are not subjects — the same exclusion the
  existing check already documents.
- **A job with no checkout at all.** No subject, no finding.
- **Reusable-workflow calls (`uses:` a `workflow_call` target) in place of
  steps.** Such a job has no step list of its own and is not a subject.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Gate 60 MUST fail when a workflow job contains a root
  `actions/checkout` step (one with no `with.path`) that is not the
  first `actions/checkout` step in that job's step list.
- **FR-002**: The failure message MUST identify the workflow file, the
  job id, and the path-scoped checkout that precedes the root checkout
  (by its `with.path` value), and MUST state the reason — the root
  checkout clears the workspace and removes that directory — so the
  author can act without reading the gate's source.
- **FR-003**: Every path-scoped checkout above the job's first root
  checkout MUST be reported in a single run of the gate, not only the
  first one found.
- **FR-004**: A job with no root `actions/checkout` step MUST NOT be
  reported by this rule, however many path-scoped checkouts it has.
- **FR-005**: A job whose root checkout is its first checkout MUST NOT be
  reported by this rule, however many path-scoped checkouts follow it.
- **FR-006**: The rule MUST NOT change the outcome of the existing
  step-to-checkout `composite-checkout-order` behaviour: a `uses: ./...`
  step that today raises a finding MUST still raise it, and one that
  today passes MUST still pass.
- **FR-007**: `--self-test` MUST include a mutation whose fixture places a
  path-scoped checkout above the job's root checkout and MUST assert that
  the scan rejects it; the self-test MUST exit non-zero if that fixture
  ever passes.
- **FR-008**: `--self-test` MUST include a fixture whose root checkout
  comes first and MUST assert it is clean, so the new rule cannot satisfy
  its mutation by rejecting all orderings.
- **FR-009**: A deliberate exception to the rule MUST be expressible only
  through `.github/scripts/single-home-waivers.json`, using the existing
  waiver shape and the existing stale-waiver and count checks; the gate
  MUST NOT gain a bespoke unconditional skip for this rule.
- **FR-010**: The check name this rule reports under MUST be declared in
  the gate's set of legal waiver check names, so a waiver for it is
  accepted and a waiver for an undeclared name still hard-fails.
  Which name that is:
  [NEEDS CLARIFICATION: does the rule report under the existing
  `composite-checkout-order` check name — one name, one waiver key, no
  change to the gate step's title — or under a new check name of its own,
  which separates the two rules in waivers and findings but changes
  `CHECK_NAMES`, the gate step title that other gates byte-compare, and
  the gate's module docstring?]
- **FR-011**: The gate's module docstring MUST describe the new rule,
  including the run-time mechanism (the root checkout's workspace
  preparation removes entries that lack `.git`, so a preceding sidecar is
  either deleted silently or turns the checkout into an `EACCES`
  failure) and the evidence for it (PR #683 shipped this order with the
  suite green), since that docstring is where the gate's contract lives.
- **FR-012**: The gate suite MUST pass on the tree as shipped, with no
  waiver added for the new rule. If the new rule flags a job in the
  current tree, that job's checkout order MUST be corrected in the same
  change and the correction called out.
- **FR-013**: The change MUST keep Gate 60's existing registration intact
  — same script path, same two steps in `lint-workflows.yml`, same
  `if: "!cancelled()"` gating, same gate number — so no gate-wiring or
  gate-numbering check has to move.
- **FR-014**: The rule's subjects MUST be workflow job step lists only;
  a composite action's `runs.steps` MUST NOT be scanned for it.

### Key Entities

- **Job step list**: the ordered steps of one workflow job — the unit
  this rule reasons over. Order within it is the whole subject.
- **Root checkout step**: an `actions/checkout@` step with no
  `with.path`. Its target is the workspace root, and preparing that
  target clears the workspace.
- **Path-scoped (sidecar) checkout step**: an `actions/checkout@` step
  with a `with.path`, populating a named directory inside the workspace —
  `.wc-pristine-repo` and `.wing-commander-pipeline` in this fleet.
- **Finding**: the gate's per-violation record (file, check name, line,
  message), the thing a waiver matches against.
- **Waiver entry**: the recorded exception in
  `single-home-waivers.json` — file, check, pattern, count, reason —
  stale-checked and count-checked on every run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer can take any workflow job in the repository,
  move its sidecar checkout above its root checkout, run the gate suite,
  and get a failure that names that job — in one run, with no argument or
  environment variable to enable the rule.
- **SC-002**: The #683 defect is caught at gate time: reconstructing that
  ordering in board-loop's `review` and `readiness` jobs produces a gate
  failure naming both jobs, where the suite previously ran green.
- **SC-003**: The gate suite passes on the shipped tree without any
  waiver for the new rule, so the rule costs nothing to adopt.
- **SC-004**: Disabling the new rule in the scan makes `--self-test`
  fail, so the rule cannot be silently removed by a later edit.
- **SC-005**: No existing Gate 60 outcome changes: the gate's findings on
  the current tree before and after the change are identical (both
  empty), and each existing self-test mutation still fails as before.
- **SC-006**: A reader of the gate's module docstring can state the rule
  and why it exists without opening the code.

## Assumptions

- **The current tree already satisfies the rule.** `board-loop.yml`'s
  eight sidecar-using jobs and the stage workflows' sidecar checkouts were
  inspected and all place the root checkout first; the #683 order was
  corrected. If the implemented rule flags anything, FR-012 governs — fix
  the order, do not waive it.
- **The run-time mechanism is as the originating issue states**:
  `actions/checkout@v5`'s workspace preparation removes entries without
  `.git`, so a preceding sidecar is deleted (or makes the removal fail
  with `EACCES` when write-protected). The feature does not re-derive this
  from the action's source; the plan may cite it.
- **A step's `if:` is not evaluated.** The rule is static and treats every
  checkout step in a job as present, which is the same assumption the
  existing check makes.
- **`clean:` default is `true`**, so a root checkout with no `clean:` key
  is destructive.
- **The prior attempt is not a dependency.** PR #865 and its branch are
  open and unmerged; this feature is planned and implemented from main.
  Its diff may be read for reference but is not carried over.
- **No renumbering.** This is an extension of Gate 60, not a new gate, so
  no gate number is claimed and no gate-count or gate-wiring register
  moves.
- **Scope is this one gate.** No workflow behaviour changes, no sidecar
  pattern changes, and no other gate is edited — beyond the
  `lint-workflows.yml` step title, and only if the answer to FR-010's
  question requires it.
