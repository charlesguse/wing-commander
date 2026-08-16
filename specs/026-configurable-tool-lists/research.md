# Research: Configurable Allowed/Disallowed Tool Lists Across Pipeline Stages

**Feature**: 026-configurable-tool-lists · **Date**: 2026-07-27

The spec (`spec.md`) arrived with all `[NEEDS CLARIFICATION]` markers already
resolved via the lifecycle issue (see `checklists/requirements.md`: FR-010,
FR-011, FR-012). This document records the *technical* decisions needed to
turn those resolved requirements into an implementable design — none of
these change or reinterpret the spec; they fill in the "how" the spec
deliberately left as "what".

## Current-state findings

Investigated every published stage workflow (`.github/workflows/{intake,
clarify,plan,tasks,implement,finalize,cleanup,rebase,watchdog}.yml`):

- All 9 stages invoke `anthropics/claude-code-action@v1`. That action has
  **no dedicated `allowed_tools`/`disallowed_tools` input** — every stage
  funnels tool permissions through a single opaque `claude_args:` multiline
  string, tokenized by the action into CLI flags: `--allowedTools "<comma
  list>"` and `--disallowedTools "<comma list>"`.
- 14 individual agent steps across the 9 stages each hard-code their own
  `--allowedTools`/`--disallowedTools` literal directly inline in
  `claude_args:`. There is no shared composite action or script that
  computes or centralizes these lists — the lists are fully duplicated.
- No stage's `workflow_call` `inputs:` block currently exposes anything
  tool-list-related. Every other piece of per-stage configuration (model,
  max-turns, branch prefixes) is exposed as a kebab-case `workflow_call`
  input, several with a `docs/setup.md` `WING_COMMANDER_*` repository
  variable at the dogfood wrapper layer.
- `specs/010-reusable-pipeline/contracts/stage-interfaces.md` is the
  normative `workflow_call` contract doc; it documents every existing
  common/per-stage input but has zero mention of tool lists — this is the
  doc FR-013 requires extending.
- `implement.yml` alone has three internal agent steps with three
  *different* default tool sets (a large "cycle"/"retry" set and a small
  read-only "post progress comment" set). No other stage varies internally.

## Decisions

### D1: Centralize composition in one new shared composite action

**Decision**: Add a new composite action, `wing-commander-tool-args`
(alongside the existing `wing-commander-preflight`, `wing-commander-context`,
etc. under `.github/actions/`), that takes a step's hard-coded default
allowed/disallowed lists plus the stage's consumer-supplied append/override
inputs, validates them, and outputs the two composed, ready-to-splice
`--allowedTools`/`--disallowedTools` fragments.

**Rationale**: FR-006/SC-004 require the append/replace capability to be
*uniform* across every agent-running stage. Duplicating conflict validation
(FR-010) and the allow-wins-over-default-deny precedence (FR-011) 14 times
inline would itself violate the spirit of "uniform" and risks the 14 copies
drifting apart. A single composite action, called once per agent step with
that step's own defaults, keeps the composition rule defined exactly once
while still letting each step keep its own (already-differing, e.g.
`implement.yml`'s three steps) default baseline. This mirrors the existing
`wing-commander-preflight` pattern: pure shell, no agent, runs before the
agent step, fails fast with a `::error::` annotation.

**Alternatives considered**:
- *Inline duplication per step* — rejected: 14 copies of non-trivial set
  logic is exactly the drift risk the feature exists to eliminate (the
  spec's own framing: "fork and re-maintain the entire hard-coded list").
- *A reusable workflow instead of a composite action* — rejected: reusable
  workflows (`workflow_call`) can't be invoked as a step *within* an
  existing job to produce outputs consumed by a later step in the same job;
  a composite action can.

### D2: New `workflow_call` inputs, one set per stage, uniform names

**Decision**: Every stage's `workflow_call` `inputs:` block gains exactly
four new optional string inputs, named consistently across all 9 stages:

| Input | Purpose |
|---|---|
| `extra-allowed-tools` | FR-001 — appended to the stage's default allowed tools |
| `extra-disallowed-tools` | FR-002 — appended to the stage's default disallowed tools |
| `allowed-tools-override` | FR-003 — replaces the stage's default allowed tools entirely |
| `disallowed-tools-override` | FR-004 — replaces the stage's default disallowed tools entirely |

Each accepts a comma-separated tool list in the same literal syntax the
pipeline's own `--allowedTools`/`--disallowedTools` values already use
(e.g. `Bash(gh pr view:*)`), per the spec's own assumption that tool-name
syntax validity is the agent runtime's responsibility, not this feature's.

**Rationale**: Matches the existing kebab-case/string/optional convention
used for e.g. `spec-draft-prefix` (see `stage-interfaces.md` "Common
inputs"). Four inputs (two per direction: append + override) is the minimum
that expresses FR-001 through FR-004 without collapsing append and replace
into one ambiguous input (which is exactly the ambiguity FR-010 exists to
reject).

**Alternatives considered**:
- *A single input with a mode prefix* (e.g. `allowed-tools:
  "append:Bash(x:*)"`) — rejected: harder to validate, harder to document,
  and makes the FR-010 conflict case (both append and replace supplied)
  invisible to GitHub's own input-typing instead of an explicit two-input
  conflict the composite action can detect directly.
- *A single JSON-object input* — rejected: inconsistent with every other
  input in these workflows, which are flat scalars; JSON-in-YAML-string
  adds a parsing dependency for no benefit at this scale (a handful of
  short lists).

### D3: Distinguishing "unset" from "explicit empty" on override inputs

**Decision**: `allowed-tools-override` and `disallowed-tools-override`
default to the sentinel string `__unset__` (not `""`). The composite action
treats the input as "override provided" whenever its value is not literally
`__unset__` — including when it is `""` (explicit empty). `extra-allowed-tools`
and `extra-disallowed-tools` keep an ordinary `""` default, because an unset
append and an explicit empty append are behaviorally identical (both are a
no-op union) — the append inputs don't need the distinction FR-009 asks for;
only the override inputs (which switch composition mode) do.

**Rationale**: GitHub Actions `workflow_call` gives every unset optional
string input the same resolved value as an explicitly-passed `""` — there
is no native null. FR-009 requires the pipeline to tell these two cases
apart specifically for override ("an unset input keeps defaults; an
explicit empty replacement is treated as an explicit choice"), so a
reserved sentinel default is the standard, minimal-footprint way to recover
that distinction inside plain YAML/shell without adding a second boolean
input per list (which would double the input surface for no added clarity).

**Alternatives considered**:
- *A companion boolean `clear-allowed-tools: true/false` input* — rejected:
  doubles the input count (8 instead of 4) and still needs the same
  precedence work; the sentinel does the same job with two fewer inputs.
- *Treat `""` as always meaning "unset"* — rejected: this is precisely the
  behavior FR-009 calls out as wrong ("omitting configuration never
  unintentionally removes tools" implies an *explicit* empty must be
  distinguishable and honored as "no tools", not silently reinterpreted as
  defaults).

### D4: Composition/precedence algorithm

**Decision**: For each direction (allowed, disallowed) independently, per
agent step, given that step's hard-coded `DEFAULT_ALLOWED`/
`DEFAULT_DISALLOWED`:

```
consumer_allowed  = allowed-tools-override if provided (D3) else
                     DEFAULT_ALLOWED ∪ split(extra-allowed-tools)
base_disallowed   = disallowed-tools-override if provided (D3) else
                     DEFAULT_DISALLOWED ∪ split(extra-disallowed-tools)

effective_allowed    = consumer_allowed
effective_disallowed = base_disallowed − explicit_allow
```

where `explicit_allow` is the consumer's own explicit allow contribution —
`split(extra-allowed-tools)` in append mode, or the full
`allowed-tools-override` list in override mode — but *never* the stage's
own `DEFAULT_ALLOWED` entries. Sets are deduplicated on join (edge case:
"same tool name appears twice … collapse to a single grant/denial").

This single rule satisfies both spec edge cases without special-casing:
- **FR-011** (explicit allow beats *default* deny): a tool in both
  `DEFAULT_DISALLOWED` and the consumer's `extra-allowed-tools` is removed
  from `effective_disallowed` by the subtraction, so it survives only in
  `effective_allowed` → allowed.
- **User Story 2, Acceptance #2** (explicit deny beats *default* allow): a
  tool in both `DEFAULT_ALLOWED` and the consumer's `extra-disallowed-tools`
  is *not* subtracted (only `explicit_allow` subtracts, and this tool isn't
  in it) → it remains in `effective_disallowed`, and `anthropics/
  claude-code-action`'s underlying `claude` CLI already treats
  `--disallowedTools` as taking precedence over `--allowedTools` for a tool
  named in both → denied.
- A consumer who names the *same* tool in both their own
  `extra-allowed-tools` and their own `extra-disallowed-tools` (a
  self-contradiction the spec doesn't address) resolves the same way — deny
  wins, via the CLI's own allow/deny precedence — consistent with a
  restriction-leaning default when a consumer's own inputs conflict.

**Rationale**: This is the minimal rule that reproduces exactly the two
precedence examples the spec gives, without inventing new behavior for the
unaddressed self-contradiction case (it falls out of the same rule rather
than needing its own branch).

### D5: Granularity — one input set per stage, applied to every internal agent step

**Decision**: The four new inputs are declared **once per stage workflow**
(matching FR-006's "every pipeline stage," Assumptions' "configuration is
applied per stage," and User Story 4's framing), not once per internal
agent step. For a stage with multiple internal agent steps with different
defaults (only `implement.yml`, today: cycle/retry vs. the small
post-progress-comment step), the *same* four consumer inputs are passed
into the shared composite action multiple times in that job, once per
step, each call supplying that step's own default baseline.

**Rationale**: Keeps the consumer-facing surface at the granularity the
spec describes (a stage-level capability) while still correctly composing
against each step's own (already different) defaults. Exposing
per-internal-step inputs would multiply the input count for `implement.yml`
alone and isn't asked for anywhere in the spec.

**Consequence (documented, not silently handled)**: if a consumer supplies
`allowed-tools-override` on the `implement` stage, it replaces the allowed
list for *all three* of that stage's internal agent steps, including the
small read-only "post progress comment" step. Per FR-012, an override that
omits a tool an internal step needs (e.g. `Bash(gh issue comment:*)` for
that step) is the consumer's responsibility, exactly as it is for the
stage's primary work. This will be called out explicitly in the
documentation update (FR-013).

**Revisited 2026-08-16 — the append direction, and why stage-scope stands.**
The consequence above reasons about an *override* narrowing a step below what
it needs. The mirror case was not considered: an **append** widening a step
above what it needs. It is now live. This repository's own wrapper passes
`extra-allowed-tools: "Bash(python3 .github/scripts/run-local-gates.py:*),
Bash(bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh:*)"` to the
`implement` stage so the cycle and retry steps can run the gate suites their
task lists name (the defect that left specs/036 with four tasks unrun). Being
stage-scoped, that grant also reaches `implement.post-progress-comment` — a
four-entry, read-only step whose only job is posting a sentence, which runs
`continue-on-error: true`, so a hang there is invisible. Constitution V asks
each stage to run with the least-privilege allowlist it needs, and this is
strictly more than that step needs.

**Decision: stage-scope is retained and the widening is accepted.** The
alternative — per-internal-step inputs — is the input-count multiplication this
decision already declined, and it would add up to three inputs to `implement`'s
published interface to constrain a step that has no network tools, no write
tools, and no path to the repository beyond `gh issue comment`. The exposure is
bounded by what the consumer themselves granted: an append cannot introduce a
tool the consumer did not ask for, only apply it more widely than they may have
intended.

**Revisit when** a consumer needs to grant a stage a tool they would not want
every step in that stage to hold — a credentialed command, a write to anything
outside the feature branch, or a network-reaching tool. At that point the
grant's blast radius stops being a matter of tidiness and the per-step input
earns its cost. Until then this is documented behaviour (`docs/adoption.md`,
"these inputs are *stage-scoped* — the same values apply identically to every
internal step"), not an undeclared one.

### D6: Validation and failure mode (FR-010, FR-014)

**Decision**: The composite action runs as an early step in each stage's
job — before any agent step, in the same position `wing-commander-preflight`
already occupies — and hard-fails (`exit 1` with `::error::` and a
`GITHUB_STEP_SUMMARY` line, matching `wing-commander-preflight`'s existing
`fail()` helper convention) when, for a given direction (allowed or
disallowed), *both* the append input and the override input are non-default
at once. The error message names which stage, which direction, and both
conflicting input values, per FR-010's "clear message that identifies the
conflicting inputs."

**Rationale**: Reuses an established, already-audited pattern
(`wing-commander-preflight`) instead of introducing a second fail-fast
convention. Running before the agent step means a misconfiguration never
burns agent cost (consistent with `wing-commander-preflight`'s own stated
purpose).

### D7: Documentation surface (FR-013)

**Decision**: At implementation time, extend
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common
inputs" table with the four new inputs (D2) and add a per-stage default
tool list reference; also update `docs/architecture.md` and
`docs/adoption.md` (the latter already documents per-stage prerequisites in
a similar table) with a pointer to that reference and a short append-vs-
replace explainer. This plan's own `contracts/stage-default-tool-lists.md`
(Phase 1, this feature) is the source-of-truth draft for that table,
carried over verbatim at implementation time.

**Rationale**: `stage-interfaces.md` is already the constitution-recognized
normative `workflow_call` contract; adding to it (rather than creating a
second, competing contract doc in the shipped repo) keeps one place
consumers already know to check. This plan stage only *drafts* that content
under `specs/026-configurable-tool-lists/`, per this stage's file-scope
constraint — the actual edit to `specs/010-.../stage-interfaces.md` and
`docs/*` happens during the implement stage.

## Constitutional considerations flagged for documentation (not violations)

Principle V (Security) mandates web tools disabled and interactive-resume
tools (`ScheduleWakeup`, `Monitor`, `SendMessage`) stripped in issue/comment-
driven stages. FR-011's "no protected subset of default denials" means a
consumer who explicitly appends e.g. `WebFetch` to `extra-allowed-tools` on
an issue/comment-driven stage *does* re-enable it for that stage — this is
correct per the spec (already resolved via lifecycle-issue clarification,
`checklists/requirements.md`) and is not a Principle V violation: the new
inputs are `workflow_call` values supplied by the *calling workflow's own
YAML* (the same trust tier as `model`, `max-turns`, and branch prefixes
today), never derived from issue/comment body text — Principle V's
"untrusted content is never instructions" applies to the latter, not the
former. `ScheduleWakeup`/`Monitor`/`SendMessage` remain functionally inert
even if re-appended, since a one-shot Action still cannot service them
regardless of the tool being nominally "allowed." This tension — a consumer
can opt into a materially less restrictive stage — is exactly what FR-013
must document clearly so consumers make an informed choice.
