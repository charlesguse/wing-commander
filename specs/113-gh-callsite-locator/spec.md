# Feature Specification: Gate 12 — an authoring rule for `gh` call sites and one shared locator

**Feature Branch**: `113-gh-callsite-locator`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Gate 12: replace the hand-written bash parser with an authoring rule for gh call sites and one shared locator" (lifecycle issue #993)

**Layer**: This spec describes the repository's own gate suite (`lint-workflows.yml` and `.github/scripts/`), which checks both the published contract (stage workflows and `.github/actions/**`) and the consuming instrument (`wing-commander-*.yml` wrappers). It changes no stage input, output or secret name (Principle VII); the authoring rule it introduces is an internal rule for whoever writes `run:` blocks in this repository.

## Background

Gate 12 asserts that every executable `gh` call in a workflow or composite action runs under a token that can make it: the GitHub App grant listed in `docs/setup.md`, or the job's `permissions:` for `github.token`. To find those calls it currently hand-parses bash inline in `lint-workflows.yml` — quoting, `$(...)`, backticks, `${...}` nesting, heredocs, comments, Actions expressions and line continuations — about 690 of the gate's roughly 1,480 inline lines.

That parser has not converged. A recent extension attempt (PR #969, closed unmerged on 2026-10-10) went through five adversarial review passes that found 19 cases where the gate would miss a real write call, and six further gaps shared with `main` are recorded on the Maintenance backlog (#889): ANSI-C quoting, unquoted heredoc bodies, `case` inside `$( )`, glued method flags, separators inside escaped backticks, and quadratic heredoc stripping.

Meanwhile the repository's real call sites are simple. Across all 87 workflow and action files there are 478 executable `gh` calls: 294 at statement level, 183 as the first command of a one-level `$(...)` (bare or behind a `GH_TOKEN=` prefix), one wrapped in `timeout`, and none inside backticks, nested substitutions, `${…}` values, or with the subcommand/method held in a variable. The parsing that keeps producing misses serves shapes nobody writes. Separately, Gate 28 (`gh api` method declaration), the gate registry's heredoc reader, and #954's script-call reader each parse shell their own way, against CLAUDE.md's "shared logic has exactly one home" rule.

## Clarifications

### Session 2026-10-10

- Q: Does the owner accept a written authoring rule for `gh` call sites, enforced by a fail-closed gate, including in published stage workflows and composites? → A: Yes (A) — adopt the rule and the fail-closed locator everywhere, as chosen when PR #969 was closed in favour of this spec (FR-020).
- Q: Are Gate 28 and #954's script-call reader migrated onto the shared locator in this spec? → A: C — Gate 28 moves in this spec; #954's reader follows in its own lifecycle, waived in the single-home check meanwhile with a tracking line on #889 (FR-012).
- Q: Is a pinned `shfmt` binary an acceptable fallback dependency? → A: Not now — this spec adds no new dependency; a real-parser fallback becomes its own proposal, decided with evidence of the authoring rule's false-failure rate (FR-019).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A miss becomes impossible by construction (Priority: P1)

A maintainer (or the implement stage) adds or edits a `run:` block that calls `gh`. If the call is written in an allowed form, Gate 12 locates it, resolves its token and checks the permission exactly as today. If the call is written in any form the locator cannot prove is allowed, Gate 12 fails with a message naming the file, line and the instruction to rewrite the call to the allowed form — it never silently passes a call it did not understand.

**Why this priority**: This is the whole point. Gate 12 exists because token-permission 403s were found three times by accident (spec 005, spec 033's T062/T063). A gate that silently misses a write call is the failure mode Principle VIII names; replacing "parse every shape correctly" with "accept a few shapes and fail closed on the rest" closes that class of miss.

**Independent Test**: Feed the gate synthetic workflow trees — one allowed-form call under an insufficient token, one disallowed-form call (e.g. `gh` inside backticks, inside a nested `$( $( ) )`, with the subcommand in a variable), one pure mention (`gh` inside a plain quoted string, a quoted-delimiter heredoc body, a comment) — and assert: the first fails with a permission error, the second fails with "rewrite to the allowed form", the third passes.

**Acceptance Scenarios**:

1. **Given** a `run:` block with `gh issue comment …` at statement level under a token lacking `issues: write`, **When** Gate 12 runs, **Then** it fails naming the call, the token and the missing permission.
2. **Given** a `run:` block with `X=$(GH_TOKEN="$T" gh pr view …)`, **When** Gate 12 runs, **Then** the call is located, the per-command token prefix wins, and the permission check runs against that token.
3. **Given** a `run:` block with `` X=`gh pr merge …` `` or `$(foo $(gh api …))` or `gh "$VERB" …`, **When** Gate 12 runs, **Then** it fails with a "rewrite to the allowed form" message naming file and line, whether or not the token could have made the call.
4. **Given** a `run:` block with `echo "run gh pr merge to finish"` (a quoted span with no `$(` or backtick), a comment `# gh pr merge`, or a `<<'EOF'` heredoc body mentioning `gh`, **When** Gate 12 runs, **Then** none of those counts as a call and the gate passes on them.
5. **Given** any `gh` token whose classification the locator is unsure of (e.g. inside an unquoted heredoc body, an ANSI-C `$'…'` string, a `case` arm inside `$( )`), **When** Gate 12 runs, **Then** it is treated as a call (and either checked or failed as a disallowed form), never as a mention.

---

### User Story 2 - The current repository passes with minimal migration (Priority: P1)

A maintainer lands the change and `main` stays green: every existing call site either already conforms to the authoring rule or is migrated in the same change, and Gate 12 still checks every one of the 478 executable calls it checks today.

**Why this priority**: A rule that turns `main` red, or that quietly checks fewer calls than the parser did, is a regression. The change must be at least as strong on the calls the repository actually makes.

**Independent Test**: Run the full local gate suite on the change; compare the set of (file, line, subcommand, token) tuples Gate 12 checks before and after — the after-set must cover every executable call in the before-set.

**Acceptance Scenarios**:

1. **Given** the repository at the change's head, **When** the full local gate suite runs, **Then** Gate 12 passes and reports having checked at least as many executable `gh` calls as before.
2. **Given** the one call site wrapped in `timeout` (`wing-commander-lifecycle-gate/action.yml`), **When** Gate 12 runs, **Then** it is accepted (either as an allowed `timeout N` prefix or after migration to an allowed form).
3. **Given** any call site that does not fit the rule today (estimated at about two), **When** the change lands, **Then** that site has been rewritten to an allowed form with unchanged runtime behaviour.

---

### User Story 3 - The gate's acceptance corpus and a real-bash oracle prove it (Priority: P2)

A reviewer can see that the new locator agrees with real bash: the self-test replays PR #969's self-test scenarios against the new gate, and a differential check runs generated scripts through real bash with a stub `gh` to confirm that every call bash actually executes is either located by the gate or rejected as a disallowed form.

**Why this priority**: Principle VIII requires every failure branch to be exercised by a checked-in fixture. The real-bash oracle turns "every mistake falls on the safe side" from a claim into a test.

**Independent Test**: Run the Gate 12 self-test; it must exercise each failure branch (permission miss, disallowed form, unresolvable token, unknown subcommand) and the differential oracle must report zero calls that bash executed but the gate neither located nor rejected.

**Acceptance Scenarios**:

1. **Given** PR #969's self-test scenarios (183, preserved on branch `ccr-21847495-5ln7qn`), **When** they are replayed against the new gate, **Then** every scenario where #969 expected a failure still fails (by permission check or by disallowed form), and every scenario #969 expected to pass either passes or fails only as a disallowed form that is documented in the corpus as an intended rule-driven change.
2. **Given** the differential check runs scripts under real bash with a stub `gh` that records each invocation, **When** a recorded invocation is not located by the gate, **Then** the gate must have failed that script as a disallowed form; otherwise the self-test fails.
3. **Given** a mutation that makes the locator treat a real call as a mention, **When** the self-test runs, **Then** it goes red.

---

### User Story 4 - One home for locating `gh` call sites (Priority: P2)

A maintainer who needs to find `gh` calls in shell (Gate 12 and Gate 28's `gh api` method check in this spec; #954's script-call reader in its own follow-up lifecycle) imports one module instead of writing another parser. Gate 12 itself moves out of its inline heredoc in `lint-workflows.yml` into a `verify-*.py` script that the gate registry reaches and that runs identically locally and in CI.

**Why this priority**: The single-home rule exists because a pasted copy is invisible until the first divergent fix. Three independent shell readers will diverge.

**Independent Test**: Grep the scripts tree and workflows for independent `gh`-locating logic; only the shared module should contain it, and a gate check fails if a second copy reappears.

**Acceptance Scenarios**:

1. **Given** the change has landed, **When** Gate 12 runs, **Then** it runs from a `verify-*.py` script (not an inline heredoc) that uses the shared locator module.
2. **Given** Gate 28 after the change (see FR-012), **When** it needs to find `gh api` calls, **Then** it imports the shared locator rather than tokenising shell itself.
3. **Given** someone reintroduces an independent `gh`-locating parser in another gate, **When** the gate suite runs, **Then** the nearest existing gate fails naming the duplicate; the only reader it tolerates is #954's script-call reader, and only through a waiver cited to its tracking line on #889.

---

### Edge Cases

- A `gh` token inside a double-quoted string that also contains `$(` or a backtick: not provably a mention, so it is treated as a call (and, being nested, fails as a disallowed form unless it is the first command of a one-level `$(...)`).
- A `gh` token inside an unquoted-delimiter heredoc (`<<EOF`): the body undergoes expansion, so it is not provably a mention; it is treated as a call.
- A `gh` token inside a quoted-delimiter heredoc (`<<'EOF'`, `<<"EOF"`) body handed to another interpreter: provably a mention; not counted.
- A `gh` substring inside another word (`ghost`, `gh-pages`, `--gh-flag`): not a `\bgh\b` command token; not counted. A token like `gh-pages` as a separate argument must not be misread as a call.
- `gh` reached through a line continuation (`\` at end of line) between prefix and command: the locator handles continuations or fails closed.
- `gh` inside a GitHub Actions expression `${{ … }}` text: an expression is not shell; such a token is treated per FR-005 (provable mention only when inside a quoted span with no substitution).
- Agent-step tool grants (`Bash(gh run view:*)`) remain checked as today; they are not shell and are outside the locator.
- A call site whose subcommand or method is spelled through a variable (`gh "$SUB" …`, `gh api -X "$M" …`): fails as a disallowed form.
- Quadratic-time behaviour on large heredocs: the locator's running time must be roughly linear in input size.
- A composite action whose `run:` blocks contain `gh` calls: located with the same rule; token resolution through `inputs.*` to each call site is unchanged.

## Requirements *(mandatory)*

### Functional Requirements

**Authoring rule**

- **FR-001**: The repository MUST document a written authoring rule for `gh` call sites in `run:` blocks of workflows and composite actions: a call is accepted only (a) as a statement-level command, or (b) as the first command of a one-level `$(...)`; optionally preceded by a `GH_TOKEN=<value>` assignment or a `timeout N` prefix; with the `gh` subcommand (and, for `gh api`, the method flag) spelled literally.
- **FR-002**: The authoring rule MUST live in one canonical place in the repository's contributor documentation, and the gate's failure message MUST point at it.

**Locator**

- **FR-003**: Gate 12 MUST treat every `\bgh\b` command-position token in a `run:` block as a call unless the locator can prove it is a mention.
- **FR-004**: The locator MUST classify a token as a mention only when it is (a) inside a quoted span that contains no `$(` and no backtick, (b) inside the body of a heredoc whose delimiter is quoted, or (c) inside a shell comment. Nothing else is a mention.
- **FR-005**: A call located in a position the authoring rule does not allow MUST fail Gate 12 with a message naming the file, the line, and the instruction to rewrite the call to the allowed form, independent of whether the token could have made it.
- **FR-006**: Every classification uncertainty in the locator MUST resolve toward "call" (false failure), never toward "mention" (silent pass).
- **FR-007**: For calls in an allowed position, Gate 12 MUST keep its existing behaviour unchanged: token resolution (per-command `GH_TOKEN=` prefix, then step `env`, then job `env`; composite `inputs.*` resolved per call site), App-grant vs `github.token` classification, the evidence-only subcommand→permission table, the `docs/setup.md` grant parse, job/workflow `permissions:` checks, agent tool-grant checks, the cross-repository exclusion, and fail-loud on anything unrecognised or unresolvable.
- **FR-008**: The locator's running time MUST be linear (or near-linear) in the size of the scanned `run:` block, removing the quadratic heredoc-stripping behaviour.

**Gate placement and single home**

- **FR-009**: Gate 12 MUST move from its inline heredoc in `lint-workflows.yml` into a standalone `verify-*.py` script, reachable through the gate registry, run with the same arguments locally (`run-local-gates.py`) and in CI, and triggered by changes to the workflows, composite actions, `docs/setup.md`, and the locator module it checks against.
- **FR-010**: The `gh` call-site locator MUST live in exactly one shared module under `.github/scripts/` (e.g. `wc_gh_callsites.py`), imported by every in-scope consumer.
- **FR-011**: The nearest existing gate MUST fail if an independent `gh`-locating shell reader reappears outside the shared module (the "single home" check CLAUDE.md requires for every consolidation).
- **FR-012**: Gate 28 (`gh api` field/method declaration) MUST move onto the shared locator within this spec. #954's script-call reader (in `verify-stop-point-recording.py`) is out of scope and migrates in its own lifecycle; until it does, the FR-011 single-home check MUST carry a temporary waiver naming that reader as its only permitted exception, cited to a tracking checklist line on the Maintenance backlog (#889) that this change adds.

**Proof**

- **FR-013**: Gate 12's self-test MUST exercise every failure branch the gate ships with a checked-in fixture: permission miss, disallowed form, unresolvable token, unknown subcommand/path, unused composite, and the mention/call boundary of each FR-004 clause.
- **FR-014**: The self-test MUST include PR #969's 183 self-test scenarios as an acceptance corpus, each with its expected verdict under the new rule; any scenario whose verdict changes from #969's MUST be a pass→"disallowed form" change and MUST be annotated as such.
- **FR-015**: The self-test MUST include a differential check that runs generated shell through real bash with a stub `gh` (via `wc_shell_harness.py`'s stub-`gh` support) and fails if any invocation bash actually executes was neither located by the gate nor rejected as a disallowed form. PR #969's fuzzer is the starting corpus for the generator.
- **FR-016**: The self-test MUST include at least one mutation that turns a real call into a mention and prove the suite goes red on it.

**Migration and fallback**

- **FR-017**: Every existing call site that does not conform to the authoring rule MUST be rewritten to an allowed form in the same change, with unchanged runtime behaviour; no stage input, output or secret name changes.
- **FR-018**: The six `main`-shared parser gaps recorded on #889 (ANSI-C quoting, unquoted heredoc bodies, `case` inside `$( )`, glued method flags, separators inside escaped backticks, quadratic heredoc stripping) MUST each be closed by the new locator (either located correctly or failed closed) and covered by a fixture, so their checklist lines on #889 can be ticked.
- **FR-019**: This change MUST NOT add any new dependency (no `shfmt` or other external shell parser, in CI or in the implement image; see #989). The locator stays pure-Python. If the authoring rule's false-failure rate proves too high in practice, adopting a real shell parser is a separate proposal, decided with evidence of that measured false-failure rate, and is not part of this spec.
- **FR-020**: The written authoring rule (FR-001) and the fail-closed locator MUST apply to every `run:` block in this repository's workflows and composite actions, including the published stage workflows and composites, enforced by Gate 12 failing closed. (Owner decision on #993; this is the approach chosen when PR #969 was closed in favour of this spec.)

### Key Entities

- **Call site**: one occurrence of a `gh` command token in a `run:` block — file, line, position class (statement-level, first-in-`$( )`, disallowed), optional prefix (`GH_TOKEN=`, `timeout N`), literal subcommand and, for `gh api`, method and path.
- **Mention**: a `gh` token the locator can prove never executes (FR-004).
- **Authoring rule**: the written definition of allowed call-site positions and prefixes (FR-001).
- **Shared locator**: the single module that turns a `run:` block into call sites and mentions; the only shell-reading code for `gh` in the gate suite.
- **Acceptance corpus**: PR #969's 183 scenarios plus fuzzer, each with an expected verdict under the new rule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero calls in the differential real-bash check that bash executed but the gate neither located nor rejected.
- **SC-002**: Gate 12 checks at least the 478 executable `gh` calls the current parser checks on `main`, and `main` is green after the change.
- **SC-003**: The shell-reading code behind Gate 12 shrinks from about 690 lines to at most about 250 lines.
- **SC-004**: At most a handful (estimated about two) of existing call sites need rewriting to conform.
- **SC-005**: All six `main`-shared parser gaps recorded on #889 are closed and covered by fixtures.
- **SC-006**: Exactly one module in the repository locates `gh` call sites in shell, and a gate enforces it; the single waived exception is #954's script-call reader, pending its own migration lifecycle.
- **SC-008**: The change adds no new dependency to CI or the implement image.
- **SC-007**: Every failure branch Gate 12 ships is exercised by a checked-in fixture.

## Assumptions

- The census in the issue (87 files, 478 executable calls; 294 statement-level, 183 first-in-`$( )`, one `timeout`-wrapped, none in backticks/nested/`${…}`/variable-method) is accurate on `main` as of 2026-10-10 and is re-verified during planning.
- PR #969's branch `ccr-21847495-5ln7qn` (head 7fc5465f) remains available as the source of the acceptance corpus and fuzzer; the corpus is copied into this change rather than referenced remotely.
- `wc_shell_harness.py`'s stub-`gh` support is sufficient for the differential oracle, or can be extended within this spec.
- Gate numbering is preserved: the moved gate is still "Gate 12" in the registry and in workflow step names.
- No stage input, output or secret changes; this is an internal authoring rule (Principle VII) and does not widen the published contract.
- The authoring rule applies to `run:` blocks only; agent tool-grant strings (`Bash(gh …:*)`) are checked as today.
- Migrating #954's script-call reader onto the shared locator is a separate lifecycle; this spec only waives it in the single-home check.
- An adopter's own workflows are not subject to this repository's gate suite; the rule governs this repository's files.
