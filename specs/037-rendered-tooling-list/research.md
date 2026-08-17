# Research: The Prompt's Tooling List States What the Run Actually Permits

**Feature**: 037-rendered-tooling-list · **Date**: 2026-08-16

`spec.md` carries no literal `[NEEDS CLARIFICATION]` markers — every open
question the spec itself raised was already resolved inline (Assumptions,
Out of Scope, and the D5-revisit note in
`specs/026-configurable-tool-lists/research.md`). This document records the
technical decisions needed to turn the spec's "what" into an implementable
"how," and flags (§"Decisions made without explicit spec text") the handful
of render-grammar choices the spec leaves to the plan because no configuration
in the repository exercises them today.

## Current-state findings

- `.github/actions/wing-commander-tool-args/action.yml` already **declares**
  `shell-commands` in its own `outputs:` block (this and the retroactive
  documentation below both landed in the prior PR, #214, which wrote this
  spec) — the "ships undeclared" problem is about the check that would *keep*
  it declared, not about today's snapshot being undocumented.
- Three docs already carry `shell-commands`, written retroactively by #214
  specifically to name this spec's four divergences as known caveats:
  `specs/026-configurable-tool-lists/contracts/tool-composition-action.md`
  (Outputs table + a "Caveats as shipped" block, lines 64-90),
  `specs/010-reusable-pipeline/contracts/stage-interfaces.md` ("What the
  agent is *told*, not only what it is permitted", lines 57-72), and
  `docs/architecture.md` (Security section, lines 216-230). This feature's
  documentation job is to *correct* those three, not originate them —
  replace "Caveats as shipped" with the fixed contract once the render is
  fixed, matching what #214 already promised.
- `specs/026-configurable-tool-lists/contracts/tool-list-inputs.md` (the
  consumer-facing `workflow_call`-input contract) and `docs/adoption.md`
  (the adopter's-first-read doc) are both silent on `shell-commands` — FR-013
  ("published per-stage tool-list documentation MUST state what the
  statement includes and excludes") reaches these too, since SC-008 requires
  an adopter to predict the statement from "the published documentation"
  generally, not from `stage-interfaces.md` alone.
- The composite's own render step (`action.yml`'s single `Compose tool args`
  step, `run:` lines 86-214) already computes `effective_allowed` and
  `effective_disallowed` correctly per spec 026 D4 — this feature does not
  touch that computation (Out of Scope: "Changing how tool lists are
  composed"). It only fixes the `shell_commands=...` render at the bottom of
  the same step (lines 189-213), which today walks `effective_allowed` alone
  with no subtraction, no bare-`Bash` case, and no exact/prefix distinction.
- `implement.yml` is the only consumer that reads `shell-commands` today, at
  two of its three internal agent steps (`cycle`: prompt lines 577-591;
  `retry`: lines 792-806, byte-identical apart from the step-id reference).
  `post-progress-comment` composes tool args but never reads `shell-commands`
  — nothing about this feature requires it to start.
- No executable coverage exists for `wing-commander-tool-args` at all
  (`specs/026-configurable-tool-lists/tasks.md` T003: validated once, by
  hand). The nearest precedent for testing a *composite action's* shipped
  shell in isolation is `.github/scripts/verify-metrics-turn-accounting.py`
  (Gate 11): it extracts a named step's `run:` block straight out of an
  `action.yml` via `yaml.safe_load`, drives it with
  `wc_shell_harness.run_step()` (writes the block to a file, runs
  `bash -e <file>`, parses `$GITHUB_OUTPUT`/`$GITHUB_STEP_SUMMARY` from
  throwaway files), and ends with a `MUTATIONS` list that re-runs the whole
  suite against deliberately broken copies of the script, asserting each one
  goes red — this is FR-015's "self-test demonstrating it failing on a
  known-bad input," done inline rather than as a second script.
- The gate registry (`.github/scripts/wc_gate_registry.py`,
  `verify-gate-wiring.py`) needs no manifest edit: any `.github/scripts/
  verify-*.py` invoked from a `run:` block in some workflow is auto-detected
  and required to be wired, in both directions. Registering new coverage is
  just: name the script `verify-*.py`, add a `- name: Gate N — ...` /
  `run: python3 .github/scripts/verify-*.py` step to
  `.github/workflows/lint-workflows.yml`. Existing gate numbers run through
  17 (`grep -n "Gate [0-9]* —" lint-workflows.yml`); the next two free
  numbers as of this writing are 18 and 19, but the implementer must re-check
  at implementation time in case another spec's PR lands first — the number
  is cosmetic, not part of any contract.

## Decisions

### D1: Grant classification — three shell-grant forms, non-shell entries ignored

**Decision**: Every entry in `effective_allowed`/`effective_disallowed` is
classified as exactly one of:

- **ANY** — the bare literal `Bash` (unrestricted shell).
- **PREFIX(cmd)** — `Bash(cmd:*)` or `Bash(cmd *)`, permitting `cmd` with any
  arguments (including none — the matcher syntax does not distinguish, and
  nothing in the spec asks the render to).
- **EXACT(cmd)** — `Bash(cmd)` with no trailing `:*`/` *`, permitting only
  that literal invocation with no arguments.
- **not a shell grant** — anything not matching one of the three `Bash(...)`
  shapes above or the bare `Bash` literal (e.g. `Read`, `Skill`,
  `Grep`) — excluded from the render entirely, per FR-010 and the existing
  non-`Bash` skip the action already performs.

**Rationale**: This is exactly the vocabulary FR-004/FR-005/FR-007 use
("any arguments" vs. "only the exact command" vs. "unrestricted") and the
vocabulary the action's existing unwrap step already partially implements
(it strips `:*`/` *` but doesn't yet remember *that* it did).

### D2: Subtraction — a deny removes a command only when it covers the allow entirely

**Decision**: An allow grant is removed from the statement iff some deny
grant for the *same command* has a scope that is a superset of the allow
grant's scope. Coverage between forms:

| deny \ allow | EXACT(cmd) | PREFIX(cmd) |
|---|---|---|
| ANY | covers | covers |
| PREFIX(cmd) | covers (PREFIX ⊇ EXACT) | covers |
| EXACT(cmd) | covers | does **not** cover |

A deny for a *different* command never covers an allow (edge case: "a deny
naming a command that is not granted at all... is not an error"). This is
evaluated per (allow, deny) pair — a command is subtracted if *any single*
deny grant covers it, not by unioning several partial denies (the spec's
Assumptions section frames it as "a deny removes a command... when it
denies everything the corresponding allow permits", singular).

**Rationale**: Reproduces both edge cases in the spec verbatim: "a command
permitted with any arguments, and one specific invocation of it denied... is
still stated" is deny=EXACT/allow=PREFIX → not covered → kept. "A deny that
covers the allow entirely removes it" is any of the three "covers" cells.
This table is the whole of FR-002 and the deny-side edge cases; it needs no
further case analysis because there are only three forms in the format
(Out of Scope: "Making the entry separator escapable" — no fourth form is
introduced here either).

**Subtraction runs against the run's already-composed `effective_disallowed`**
(the existing D4 computation from spec 026) — never a separate recomputation
— so FR-003 ("producing the statement MUST NOT alter the enforced... lists")
holds structurally: the statement reads the same values the step already
enforces and writes nothing back into them.

### D3: An unrestricted allow under a partial deny states the exception

**Decision** *(no configuration in the repository exercises this; flagged
below as a decision made without explicit spec text)*: when the allowed side
carries ANY and the disallowed side denies one or more specific commands
that do not themselves cover ANY (i.e. anything other than a disallowed bare
`Bash`), the statement is **"any shell command except: `cmd1`, `cmd2`."**
rather than plain "any shell command." If the disallowed side also carries a
bare `Bash` (ANY covers ANY per D2's table), the statement is the User Story
2 empty case ("no shell command is permitted"), because the entire
unrestricted grant is covered.

**Rationale**: FR-002 requires excluding every fully-denied command
regardless of what form the allow takes; FR-005 requires stating "any shell
command," not silence, whenever the grant is unrestricted. Dropping the
specific denials from an ANY statement would violate FR-002 the moment a
consumer pairs an unrestricted allow with a narrow deny — a legal
configuration nothing in the spec excludes. Stating the exception is the
minimal extension that keeps both requirements true simultaneously; it
introduces no new grant form and no change to composition.

**Alternative considered**: state plain "any shell command" regardless of
partial denies, treating the ANY case as exempt from subtraction. Rejected —
SC-001 ("zero named commands that the run denies") does not carve out an
exception for the unrestricted case, and the spec's own edge case for
unrestricted grants only says the *bug* is stating it as empty, not that
denies should be ignored once it's fixed.

### D4: Same command in two forms — state once, in the broader surviving form

**Decision**: After D2's subtraction, group surviving allow grants by
command. A command with both a surviving EXACT and a surviving PREFIX grant
is stated once, as PREFIX (the broader form — "any arguments," no
`(exact command only)` qualifier). A command with only EXACT surviving
(its own PREFIX grant, if any, was independently subtracted by a deny that
covered PREFIX but not EXACT — D2's table shows this is possible: a deny
EXACT(cmd) covers allow EXACT(cmd) but not allow PREFIX(cmd), and
conversely there is no deny shape that covers PREFIX while sparing EXACT,
since PREFIX ⊇ EXACT always) is stated with the exact-only qualifier.

**Rationale**: This is FR-007 ("stated once, reflecting the broader of the
two grants") composed with D2 rather than handled as a special case —
broadening and deduplication fall out of "group by command, keep the
broadest surviving form," the same shape the action's existing (buggy)
dedup-before-unwrap already gestures at, just now ordered correctly
(unwrap-and-classify, then dedupe-by-broadest, rather than dedupe raw
strings before unwrap, which is what collapses `Bash(cmd)` and
`Bash(cmd:*)` into the same rendered text today).

### D5: The rendered value is a complete, self-contained sentence — not a bare list

**Decision**: `shell-commands`'s value changes shape. Today it is a
backticked, comma-joined fragment meant to be spliced into a fixed carrier
sentence (`"...are exactly ${shell-commands} — that list is..."`), which is
exactly what produces the dangling-em-dash defect on empty input (FR-008).
Instead, the composite renders one of four complete sentences, chosen by
case:

1. **Enumerated** (one or more surviving commands): `` This run permits these shell commands: `cmd1`, `cmd2`, `cmd3` (exact command only). `` — PREFIX entries are bare backticked text; EXACT entries get the trailing `(exact command only)` qualifier (D4). Commands are joined in first-seen order (matching the existing dedup convention) with `, ` and a final period.
2. **Unrestricted, no exception** (D3, no partial deny): `` This run permits any shell command. ``
3. **Unrestricted, with exception** (D3, partial deny present): `` This run permits any shell command except: `cmd1`, `cmd2`. ``
4. **Empty** (no surviving shell grant at all — either no `Bash(...)`/`Bash` entry in `effective_allowed`, or every one was fully covered by D2): `` This run permits no shell command. ``

Every case is a complete sentence: subject, verb, terminal period, no
dangling connective. A consuming prompt embeds the value directly (no
carrier sentence needed), which is also what makes the value independently
meaningful in `$GITHUB_STEP_SUMMARY` for User Story 5 (D8) and reusable by a
stage other than `implement` without that stage inventing its own carrier
sentence (edge case: "a stage other than the implement stage adopting the
same statement").

**Output name is unchanged** (`shell-commands`) — the contract already
declares it under that name in three docs (#214); renaming would be an
unforced breaking removal-plus-add of a name adopters may already be
reading, and nothing in the spec asks for a rename.

**Rationale**: FR-008 requires "no dangling punctuation... no empty
enumeration" for *every* legal configuration; a value that is always a
complete sentence satisfies this by construction rather than by enumerating
which carrier-sentence edits happen to avoid a dangling artifact for each
case. The Key Entities section's own wording — "**Tooling statement**: the
sentence in an agent prompt..." (singular, "the sentence") — reads as a
single complete unit, not a fragment assembled from two pieces.

**Alternative considered**: keep the bare-list shape and instead special-case
the prompt's carrier sentence per configuration (e.g. an `if:`-conditioned
prompt block). Rejected — this would need to be re-derived correctly by
every future consumer (edge case explicitly anticipates more than one), the
same "hand-maintained copy" failure mode this whole feature exists to close,
just moved one layer up.

### D6: `implement.yml`'s two prompt sites — drop the overclaim, embed the sentence directly

**Decision**: Both `cycle` (lines 577-591) and `retry` (lines 792-806) drop
the phrase `"are exactly ... — that list is rendered from this step's own
--allowedTools, so it is authoritative"` and instead embed the now-complete
sentence directly, followed by the same operational guidance the paragraph
already carries (auto-denial burns turns; note missing commands for the
human; use the Grep tool; lint tool names conditioned on being in the list).
Illustrative shape (exact wording is an implementation-time task, not fixed
by this plan):

```
Tooling: ${{ steps.tool-args-cycle.outputs.shell-commands }} That
statement is derived from this run's own composed allowed and disallowed
tool lists, so a command's presence or absence here matches what this run
actually permits. If a check needs a shell command not covered above, note
it for the human instead of retrying variants. ...
```

**Rationale**: FR-009 ("MUST NOT claim more than the composition
guarantees... or MUST be narrowed to the claim that does") is satisfied by
"matches what this run actually permits" — true for every legal
configuration per D1-D4 — where "exactly... authoritative" was false the
moment a deny narrowed the allow list. Two call sites, not one, because
`implement.yml` has two internal steps that each read their own
`tool-args-*` output (cycle, retry); `post-progress-comment` is untouched
(it never read `shell-commands` and nothing requires it to start —
Out of Scope: "Wiring the statement into stages that do not state their
tooling today").

### D7: Recoverability from the run's own record (US5, FR-018)

**Decision**: The composite's `Compose tool args` step appends a line to its
own `$GITHUB_STEP_SUMMARY` block (alongside the existing
`✅ wing-commander-tool-args (...): composed tool lists.` line) carrying the
literal rendered sentence, e.g. `**Tooling statement**: <value>`. GitHub
aggregates every step's summary into one job summary page, so a maintainer
reading a completed run's own Actions page — no workflow source required —
sees the exact sentence that step's prompt was given, for every stage that
calls this composite, not only `implement`.

**Rationale**: This is the cheapest correct place to satisfy US5: the
composite already writes to `$GITHUB_STEP_SUMMARY` in the same step that
computes the value, so no new step, no new output, and no dependency on the
consuming stage doing anything extra. It also directly answers Acceptance
Scenario 2 ("a composition that produced no permitted shell commands...
visible as such rather than as a missing entry") — case 4's sentence
("This run permits no shell command.") appears in the summary exactly like
any other case, never as a blank line.

### D8: The render-correctness gate — extend the Gate-11-style harness

**Decision**: A new `.github/scripts/verify-tooling-statement.py` (naming
follows the existing `verify-*.py` convention gate-registry auto-detects)
extracts the `Compose tool args` step's `run:` block from
`wing-commander-tool-args/action.yml` (mirroring
`verify-metrics-turn-accounting.py`'s `shipped_script()`), drives it via
`wc_shell_harness.run_step()` once per representative configuration, and
asserts the `shell-commands` line in `$GITHUB_OUTPUT` matches the expected
sentence. Representative configurations, one per acceptance scenario in User
Stories 1 and 2:

- No consumer configuration at all → statement names exactly the stage's
  hard-coded defaults (Acceptance 1.3).
- A deny that fully covers a default allow → command absent, `allowed-tools`/
  `disallowed-tools` outputs unchanged from the no-subtraction case
  (Acceptance 1.1, 1.2).
- A wholesale allow replacement → statement derived from the replacement,
  not the defaults (Acceptance 1.4).
- A command denied then separately re-allowed (explicit-allow-beats-
  default-deny, spec 026 D4) → statement agrees with the enforced outcome
  (Acceptance 1.5).
- Bare `Bash` allow, no matching deny → "any shell command." (Acceptance
  2.1).
- Bare `Bash` allow, one specific deny → "any shell command except: ..."
  (D3).
- No `Bash(...)`/`Bash` entry in the allowed list at all (but other tools
  present) → "no shell command." as a complete sentence (Acceptance 2.2).
- `Bash(cmd)` only → exact-only phrasing (Acceptance 2.3).
- `Bash(cmd)` and `Bash(cmd:*)` both granted → stated once, prefix form
  (Acceptance 2.4).
- A deny that only partially overlaps an allow (EXACT deny under a PREFIX
  allow) → command still stated (edge case).
- A non-shell-only allowed list (e.g. `Read,Grep`, no `Bash` entry) →
  "no shell command," other tools untouched (edge case).

The script ends with a `MUTATIONS`-style self-test (Gate 11's pattern):
revert the subtraction, the unrestricted-shell case, the empty-list
fallback, and the deduplication one at a time against a scratch copy of the
extracted script, re-run the suite, and assert each mutation turns at least
one case red — this is User Story 4's "break each guarantee in turn... a
distinct test fails for each" and FR-015's self-test requirement, satisfied
inline rather than as a second script.

**Rationale**: Reuses the one existing precedent for testing a composite
action's shipped shell rather than inventing a second harness style; the
mutation phase is the same mechanism Gate 11 already uses to prove a gate
"actually detects," so User Story 4's self-test requirement (Acceptance 4)
is met by the same pattern reviewers already know.

### D9: The contract-agreement check — a new, separate gate

**Decision**: A second new script,
`.github/scripts/verify-tool-args-contract.py`, holds two things in
agreement in both directions: the `outputs:` keys `action.yml` declares, and
the outputs actually written to `$GITHUB_OUTPUT` by its `run:` block (parsed
from the `echo "...=..." >> "$GITHUB_OUTPUT"` lines, the same script text
D8's harness already extracts) — an output declared but never emitted, or
emitted but never declared, fails and names which. It separately checks that
every key in `action.yml`'s `outputs:` block also appears as a row in
`specs/026-configurable-tool-lists/contracts/tool-composition-action.md`'s
Outputs table (the "published contract" a maintainer edits by hand,
distinct from the machine-checked `action.yml` declaration) — a mismatch
here fails and names the output. Self-test: run the same check against a
scratch copy of `action.yml` with a fourth output added only to `outputs:`
(not emitted) and a scratch copy with an emitted output's `outputs:` entry
deleted, asserting both fail, per FR-015's self-test requirement (this is
User Story 4 Acceptance 4's "the check that holds the contract and the
action in agreement... demonstrates it failing on a known-bad input").

**Rationale**: This is the mechanical form of FR-011/FR-012/User Story 3 —
"declared but not emitted" and "emitted but not declared" are exactly the
two directions User Story 3 Acceptance 3-4 name. Keeping it a separate
script from D8 follows the existing one-script-per-gate convention (Gate 11
tests render correctness of a different composite; nothing in this
repository combines two independent guarantees behind one gate number) and
keeps each self-test's mutation set scoped to what it actually checks.

### D10: Documentation updates finish what #214 started, they do not originate it

**Decision**: At implementation time,
`tool-composition-action.md`'s "Caveats as shipped" block (lines 64-90) is
replaced with the corrected render description (D1-D5) — the four
divergences it lists become the four guarantees D2/D3/D5 now hold, not
caveats. `stage-interfaces.md`'s "What the agent is *told*" paragraph
(lines 57-72) drops the "Four divergences... are known and being fixed"
sentence and states the corrected behavior directly, keeping its pointer to
`tool-composition-action.md#outputs`. `docs/architecture.md`'s Security
section (lines 216-230) gets the same correction. Two docs the prior PR did
not touch also get a one-line addition each, since SC-008 ("reading only
the published documentation") is not scoped to a single file:
`tool-list-inputs.md` (silent on `shell-commands` today) gets a pointer to
`tool-composition-action.md#outputs`; `docs/adoption.md`'s existing
"Tool-list inputs" bullet (lines 801-815) gets one sentence noting the
composed lists also drive the stage's own stated-tooling prompt where one
exists.

**Rationale**: Keeps one normative contract doc per constitution VII rather
than a second competing one; matches spec 026's D7 precedent of drafting
content under the feature's own `specs/` directory at plan time and editing
the real files at implementation time (this plan stage's file-scope
constraint — only `specs/037-rendered-tooling-list/` is writable here).

## Decisions made without explicit spec text

These are documented in the issue comment as required by this pipeline's
plan-stage deviation rules, since the spec left them to the plan (no
`[NEEDS CLARIFICATION]` markers exist, but each is a genuine design choice
the spec's acceptance scenarios don't fully pin down):

1. **D3** — an unrestricted allow (`Bash`) paired with a partial deny states
   the exception ("any shell command except: ...") rather than staying
   silent about the narrowing. No configuration in the repository exercises
   this combination today.
2. **D5** — the exact sentence grammar (four templates) and the decision to
   make `shell-commands` a complete sentence rather than a bare list spliced
   into a fixed carrier. The spec's Key Entities wording ("the sentence")
   supports this reading but doesn't mandate the specific templates.
3. **D9's second check** — whether the contract-agreement check treats
   `tool-composition-action.md`'s Outputs table as the sole "published
   contract" surface, versus also gating `stage-interfaces.md` structurally.
   Decision: only `tool-composition-action.md` is machine-checked (it is the
   implementer-facing contract for this composite specifically);
   `stage-interfaces.md` and the other docs are corrected by D10 but not
   gated by D9, since gating prose in an adopter-facing narrative doc this
   precisely would be brittle for a check whose job is the declared/emitted
   agreement, not doc style.
4. **Gate numbers** (18/19) are placeholders; the implementer confirms the
   next free numbers against `lint-workflows.yml` at implementation time.
