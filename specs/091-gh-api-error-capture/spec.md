# Feature Specification: A Failed `gh api` Read Never Becomes Data

**Feature Branch**: `091-gh-api-error-capture`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Audit gh api --jq captures: on an HTTP error the JSON error body lands on stdout. On an HTTP error, `gh api ... --jq '<filter>'` exits non-zero and still prints the raw JSON error body (`{\"message\":\"Not Found\",...,\"status\":\"404\"}`) to stdout. The filter is not applied, and only the `gh: Not Found (HTTP 404)` line goes to stderr. The review of #497 confirmed this with gh 2.63.2 and 2.81.0. So `x=\"$(gh api ... --jq ...)\"` leaves `x` holding the error JSON, not an empty string. This is only harmless when the failure branch exits or resets `x`. #497 fixed this for auto-release's slug fallback and audited the other captures in that step. Two gaps remain: the rest of `.github/workflows/` and `.github/actions/` have not been audited — any capture whose failure path continues without resetting the variable (e.g. `|| true`, or an `if !` branch that only logs) can carry the error JSON downstream as data; and the lifecycle-gate diagnostic at `wing-commander-lifecycle-gate/action.yml:118` was flagged by the reviewer as worth checking. A gate could flag `x=\"$(gh api ...)\"` captures whose failure path neither exits nor reassigns `x`. It could also require the harness stubs (`wc_shell_harness`) to print a JSON error body on stdout, as real gh does, so other harness-driven gates stop passing vacuously the way #497's first stub did."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - No live capture site can carry an error body downstream (Priority: P1)

A maintainer needs confidence that when a GitHub API read inside the pipeline
fails, the value the step goes on to use is either absent or explicitly
handled — never the API's own error JSON masquerading as a slug, a branch
name, a run id, a label, or a count.

Today exactly one site (auto-release's pass-path slug fallback, fixed under
#497) is known to be safe. Every other capture across the pipeline's
workflows and composite actions is unreviewed: any one of them whose failure
path only logs, only sets a flag, or swallows the status with `|| true` will
continue with a variable holding `{"message":"Not Found","status":"404"}`.
That value then reaches a comparison, a branch name, an issue body, or a
downstream step output, where it reads as a plausible-looking string rather
than as a failure.

**Why this priority**: This is the defect itself. Until the live sites are
corrected, the shipped pipeline can act on error text as if it were data —
the failure is silent, produces a wrong outcome rather than a red check, and
is the kind of thing that only surfaces during an incident. Everything else
in this feature exists to keep this state from returning.

**Independent Test**: Enumerate every command-substitution capture of a
`gh` read in `.github/workflows/` and `.github/actions/`, and for each one
show that a non-zero exit leads to a path that exits the step, reassigns the
captured variable, or documents at the site why holding the error body is
intended. Delivers value on its own: the audit's corrections ship even if no
gate is ever written.

**Acceptance Scenarios**:

1. **Given** a step that captures a `gh` read into a variable and whose
   failure branch only logs a message, **When** the read returns an HTTP
   error, **Then** the step does not proceed with the error body in that
   variable — it either stops or continues from an explicitly reset value.
2. **Given** a step that captures a `gh` read with the failure status
   swallowed (`|| true`, or a capture whose exit status is masked by the
   assignment form), **When** the read returns an HTTP error, **Then** the
   subsequent emptiness test that the step relies on behaves as the author
   intended, because the variable was reset rather than assumed empty.
3. **Given** the lifecycle-gate diagnostic capture flagged by the #497
   reviewer, **When** the underlying read fails, **Then** the diagnostic
   text it builds is the one the classification branches below it are
   written to match, and the site records whether the error body is
   deliberately part of that diagnostic.
4. **Given** a corrected site, **When** the same read succeeds, **Then** the
   step's existing successful behaviour is unchanged.

---

### User Story 2 - A new unsafe capture cannot merge (Priority: P2)

A contributor adds a step that captures a `gh` read and handles the failure
by logging and carrying on. The PR-time gate suite flags the capture by file
and line, names the variable, and explains what the failure path must do
instead. The contributor fixes it in the same PR.

**Why this priority**: The audit in User Story 1 is a point-in-time sweep
across roughly fifty files. Without an enforcing check, the next capture
written by a human or by the implement agent restores the defect and nothing
goes red — the repository's own rule is that a rule with no gate behind it
lasts until the next session.

**Independent Test**: Run the gate against the repository as it stands after
the audit and see it pass; introduce a capture whose failure path neither
exits nor reassigns and see it fail with the file, line and variable named;
introduce a capture whose failure path does reassign and see it pass.

**Acceptance Scenarios**:

1. **Given** a capture whose failure path neither exits the step nor
   reassigns the captured variable, **When** the gate suite runs, **Then**
   it fails and names the file, the line, and the variable.
2. **Given** a capture whose failure path reassigns the variable before any
   further use, **When** the gate suite runs, **Then** it passes.
3. **Given** a site where holding the error body is deliberate, **When** the
   site carries the project's explicit opt-in marker, **Then** the gate
   passes and the marker is discoverable by a reader of that step.
4. **Given** the gate itself, **When** its self-test runs, **Then** each
   regression it exists to catch — including the exact shape the #497 review
   found — is shown to make it fail, so it cannot pass while checking
   nothing.

---

### User Story 3 - Harness stubs behave like real `gh` on an error (Priority: P3)

A gate author writes a harness that executes a shipped `run:` block against a
stubbed `gh`. The stub's error arm prints a JSON error body to stdout and the
`gh: ... (HTTP NNN)` line to stderr, exactly as the real tool does, so a
shipped block that forgets to reset a captured variable fails the harness
instead of passing it.

**Why this priority**: #497's first stub left stdout empty on error, which
made the harness green against a block that still had the bug. Every other
harness-driven gate that stubs `gh` has the same latent hole — they are not
wrong today, but each is capable of passing vacuously on exactly this class
of defect. This is prevention for the gate suite rather than for the shipped
pipeline, so it ranks below both.

**Independent Test**: Take an existing harness-driven gate, mutate the
shipped block it executes to drop a variable reset on a failure path, and
confirm the gate now fails where before it passed.

**Acceptance Scenarios**:

1. **Given** a harness stub for `gh`, **When** it simulates an HTTP error,
   **Then** it writes a JSON error body to stdout, the human-readable error
   line to stderr, and exits non-zero.
2. **Given** a harness whose stub does not do this, **When** the conformance
   check runs, **Then** it is reported, naming the gate script.
3. **Given** the error-body behaviour, **When** a second harness needs it,
   **Then** it takes it from the one shared home rather than retyping it.

---

### Edge Cases

- A capture whose only consumer is inside the failure branch that exits —
  no reset is needed and the check must not demand one.
- A capture whose failure path deliberately wants the error text, such as a
  diagnostic that classifies the failure by matching on it. The rule must
  admit this rather than force a reset that would blank the diagnostic.
- A capture written as `local x="$(gh ...)"` or `declare x="$(gh ...)"`,
  where the assignment builtin's own exit status masks the command's, so
  `if ! local x=...` never sees the failure at all.
- A capture inside a pipeline (`gh ... | jq ...`) where the default shell
  has no `pipefail`, so the failure status is discarded before any branch
  can test it.
- A read that succeeds at the HTTP layer but returns an empty result, which
  must stay distinguishable from a read that failed.
- A capture that feeds a step output or a job output, where the error body
  escapes the step entirely and reaches another job.
- A capture whose error body reaches a posted comment or issue body, where
  it becomes visible to users as if it were a real value.
- A read that fails for a reason other than an HTTP status — no network,
  killed process, authentication refused — where stdout may be empty rather
  than a JSON body.
- A future `gh` release that changes which stream the error body lands on,
  which must not silently turn the checks into no-ops.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every command-substitution capture of a `gh` read in
  `.github/workflows/` and `.github/actions/` MUST be audited, and each one
  recorded as either already safe, corrected, or deliberately holding the
  error body with the reason stated at the site.
- **FR-002**: A capture site MUST be treated as safe only when a non-zero
  exit from the read leads to a path that exits the step, reassigns the
  captured variable before any further use of it, or carries the project's
  explicit opt-in marker for intentionally retaining the error body.
- **FR-003**: The lifecycle-gate diagnostic capture flagged by the #497
  review MUST be resolved explicitly — corrected if the error body can
  corrupt the diagnostic it builds, or annotated as intentional if the
  classification branches below it depend on that text.
- **FR-004**: Correcting a site MUST NOT change its behaviour when the read
  succeeds.
- **FR-005**: A PR-time check MUST fail when a capture site does not meet
  FR-002, naming the file, the line, and the captured variable, and stating
  what the failure path must do instead.
- **FR-006**: The check MUST run in the same PR-time gate suite the
  repository already runs locally and in CI, and be reachable from the
  repository's single local gate-suite entry point.
- **FR-007**: The check MUST carry a self-test that demonstrates it fails on
  each regression it exists to catch, including the specific shape the #497
  review found (a failure branch taken but the captured variable left
  holding what the read printed on its way to a non-zero exit).
- **FR-008**: The check MUST offer an explicit, discoverable opt-in for a
  site that intends to retain the error body, so that suppressing the check
  is visible to a reader of the step rather than silent.
- **FR-009**: Harness stubs that simulate a failing `gh` read MUST emit a
  JSON error body on stdout, the human-readable error line on stderr, and a
  non-zero exit status, matching the real tool's observed behaviour.
- **FR-010**: The error-response shape used by FR-009 MUST have exactly one
  home, with every harness taking it from there rather than retyping it, and
  a check MUST fail if a second copy of that shape appears.
- **FR-011**: A check MUST report any harness-driven gate whose `gh` stub
  simulates an error without meeting FR-009.
- **FR-012**: The system MUST record, at the single home for the
  error-response shape, the `gh` versions against which the two-stream
  behaviour was observed, so a future change in that behaviour is traceable
  rather than invisible.
- **FR-013**: The surface the checks cover MUST include [NEEDS
  CLARIFICATION: only `gh api` captures, or every `gh` read that can print a
  body to stdout on failure — `gh api` with and without `--jq`, `gh pr list
  --json`, `gh issue view --json`, `gh run view --json`?]
- **FR-014**: Capture sites that exist at the time this feature lands MUST
  be handled by [NEEDS CLARIFICATION: correcting every site before the check
  is turned on, or recording a reviewed baseline of existing sites that the
  check accepts while failing on any new or modified one?]
- **FR-015**: Existing harness stubs that predate FR-009 MUST be handled by
  [NEEDS CLARIFICATION: retrofitting all of them in this feature, or
  publishing the shared shape and requiring it only of new and modified
  stubs, with the rest reported as a known list?]

### Key Entities

- **Capture site**: One place in a workflow or composite action where the
  output of a `gh` read is assigned to a shell variable via command
  substitution. Identified by file, line, and variable name.
- **Failure path**: The code a capture site reaches when the read exits
  non-zero. Classified as exiting, reassigning, opted-in, or unsafe.
- **Capture check**: The PR-time check that classifies every capture site
  and fails on an unsafe one, together with its self-test.
- **Harness error response**: The single canonical description of what a
  failing `gh` read emits on each stream, consumed by every harness stub
  that simulates an error.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of capture sites in `.github/workflows/` and
  `.github/actions/` are classified as exiting, reassigning, or explicitly
  opted-in; zero remain unsafe.
- **SC-002**: A newly introduced unsafe capture is caught before merge in
  100% of cases, evidenced by the check failing on a deliberately introduced
  example.
- **SC-003**: The check's self-test shows it failing on every regression it
  claims to catch, with zero mutations passing.
- **SC-004**: For every harness-driven gate whose stub simulates a failing
  `gh` read, that stub emits the error body on stdout; a mutation that
  removes a variable reset from the shipped block one of those gates
  executes makes that gate fail.
- **SC-005**: The canonical error-response shape appears exactly once in the
  repository, and a deliberately introduced second copy is reported.
- **SC-006**: A maintainer can see, from the check's failure message alone
  and without reading the check's source, which file and line is at fault
  and what the failure path must do instead.
- **SC-007**: No workflow or composite action changes behaviour on a
  successful read as a result of this feature, evidenced by the existing
  gate suite staying green.

## Assumptions

- The observed `gh` behaviour is stable across the versions the pipeline
  runs: on an HTTP error, the JSON error body goes to stdout, the
  `gh: <message> (HTTP NNN)` line goes to stderr, exit status is non-zero,
  and a `--jq` filter is not applied. Confirmed on 2.63.2 and 2.81.0 by the
  #497 review.
- The audit's boundary is `.github/workflows/` and `.github/actions/`.
  Standalone scripts under `.github/scripts/` are in scope only where a
  workflow or composite action sources or invokes them as part of a capture
  site's failure path.
- The `.github/scripts/` gate scripts themselves, and their fixtures, are in
  scope only for the harness-stub requirements (FR-009 through FR-011).
- The check is deterministic and static — it reads the shipped text rather
  than executing every workflow — and so is expected to be conservative:
  it may require an explicit opt-in at a site a human would call safe, and
  that opt-in is the intended resolution rather than a weakening of the
  check.
- Correcting a site means the smallest change that makes the failure path
  explicit; it does not mean reworking the step's error handling or its
  retry behaviour.
- The audit is expected to find sites that are already safe. Those are
  recorded as reviewed, not rewritten.
- This work rides the repository's existing PR-time gate suite and its
  single local entry point; no new CI surface is introduced.
- The repository is public, so no example error body used in a fixture or a
  comment may contain a real private repository, organisation, or customer
  name.
