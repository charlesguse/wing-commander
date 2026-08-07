# Phase 0 Research: Structured Clarification Questionnaires With a Single Content-and-Decision Artifact

`spec.md` carries two `[NEEDS CLARIFICATION]` markers (FR-008, FR-009). Per
this pipeline's CI deviation for the plan stage, both are resolved here with
a documented decision rather than a clarification round with the requester;
both are called out again in the "Decisions made without clarification"
section of the plan-completion issue comment.

## Current-state findings (grounding for every decision below)

- **`intake.yml`'s decision grep** (line 611) and **`clarify.yml`'s decision
  grep** (line 431) are both `grep -q '\[NEEDS CLARIFICATION' "$SPEC_DIR/spec.md"`
  — the bare-token form, with no trailing colon requirement. Neither site
  today enforces the colon form the spec's FR-008 describes tightening
  *to*. This means the colon-form cross-check is **not** already shipped
  anywhere in this repository; #159 (a spec whose prose names the bare
  token) is reproducible against the code as it stands right now.
- Both grep sites carry a comment ("No closing `\]`: real markers are
  `[NEEDS CLARIFICATION: <question>]`... the bare-bracket literal never
  matched one") that explains a *prior* fix (dropping a trailing `\]` that
  never matched — the #109 class) but that fix left the leading bare-token
  match in place, which is the #159 class. The two failures are independent
  defects in the same three-line grep and neither is fixed by the other.
- **The two callout branches are mutually exclusive `if:` steps** gated on
  the SAME grep output (`steps.clarification.outputs.needed` /
  `steps.clarification.outputs.outcome`) in both files — confirming the
  spec's description that a wrong branch silently deletes the correct one's
  callout (US2) rather than merely posting an extra one.
- **The questionnaire content is agent-authored prose written straight to a
  temp file** (`${{ runner.temp }}/intake-clarification.md`,
  `${{ runner.temp }}/clarify-followup.md`) by an unconstrained final
  message in the agent step's own prompt instructions (intake.yml step 7,
  clarify.yml step 6) — nothing validates that file's shape, and nothing
  ties its existence/content to the grep decision made in a *later*,
  independent step. This is the literal "two independent mechanisms that
  can silently disagree" the spec names.
- **The established precedent for schema-constrained output + deterministic
  read-back** already exists twice in this repository, both reusable:
  - `watchdog.yml`'s `diagnose` job (lines ~941–1257): a `--json-schema`
    argument built by a prior deterministic step (`Resolve finding-class
    vocabulary`), an object-wrapped array (`{"findings":[...]}` — a
    top-level `"type":"array"` schema is rejected by the API with
    `input_schema.type: Input should be 'object'`), and a `Read back
    diagnose outcome` step that parses the terminal `result`-type record
    out of `claude-execution-output.json`, degrading a missing/unparseable/
    `is_error` result to a `diagnose-failed` outcome rather than fabricating
    zero findings as a clean pass.
  - `auto-update-spec-kit.yml`'s `Interpret the maintainer's reply` step
    (line ~1957): `--json-schema
    '{"type":"object","properties":{"recognized":{"type":"boolean"},"chosen_option":{"type":["string","null"]}},"required":["recognized"]}'`
    — a boolean discriminator (`recognized`) alongside the payload field
    (`chosen_option`), read back the same way. This is the closest existing
    precedent for a schema that must express more than one outcome from a
    single structured artifact.
  Both confirm the spec's own Assumptions section ("the
  schema-constrained-output-plus-deterministic-read-back pattern already
  used by the watchdog's diagnose step... including its documented inline-
  schema quoting considerations").
- **`--json-schema` is unconditional, not agent-optional.** In both existing
  uses, the CLI is invoked with `--json-schema` set on every run of that
  step; nothing in either workflow lets the agent's own choice of path
  (e.g. an early-return decision) skip producing a schema-conforming
  terminal result. A run only lacks a valid structured result when the step
  itself fails or errors (crashed, exhausted turns, non-`success` `result`
  subtype) — never as a legitimate "the agent chose not to answer" branch.
  This directly informs the FR-009 decision below.
- **`wing-commander-callout`'s `body-file` contract is unchanged by this
  feature.** Both `intake.yml`'s and `clarify.yml`'s clarification callouts
  already post via `body-file: ${{ runner.temp }}/<file>.md` (never
  shell-interpolated `--body`). This feature only changes *what writes*
  that file — from agent prose to a deterministic render — never how it is
  posted (`.github/actions/wing-commander-callout/action.yml`, unchanged).
- **The reader-facing block shape** is defined once, in
  `.claude/skills/speckit-specify/SKILL.md` (~line 206): a `## Question [N]`
  heading, a `**Context**:` line, a `**What we need to know**:` line, and a
  `**Suggested Answers**:` table with columns `Option | Answer |
  Implications` plus an always-present `Custom | Provide your own answer |
  ...` row. FR-010 requires this exact shape survive the move to a
  deterministic renderer.
- **The watchdog's step-summary sentinel set** (FR-012) is one literal
  extended-regex alternation on one line: `.github/workflows/watchdog.yml`
  line 618, `sentinels='stalled|rejected|turn budget warning|could not
  inspect|denied|abandon'`, consumed by the `Collect: step summaries` job
  that scans each job's *runtime* log output (explicitly excluding echoed
  step source, per that step's own comment about a 2026-07-24 false-positive
  audit) for a match. Adding `clarification-mismatch` here is a one-token
  change to that alternation; no other sentinel-handling code needs to
  change (the fingerprinting/dedup machinery downstream keys off whichever
  word matched, generically).

## Decision: Resolve FR-008 — the colon-form cross-check ships as part of this feature

**Decision**: This feature both tightens the marker cross-check to the
colon form (`grep -q '\[NEEDS CLARIFICATION:' "$SPEC_DIR/spec.md"`,
replacing the bare-token grep at both existing call sites) AND makes it a
non-deciding cross-check per FR-004/FR-005. There is no separately-shipped
precursor to build on.

**Rationale**: The spec's own text floats two readings ("is the colon-form
cross-check delivered as part of this feature, or assumed already shipped as
the independently shippable precursor the follow-up comment describes").
The current-state grep audit above settles it empirically: both existing
call sites use the bare-token form today, so there is nothing already
shipped to build on. Treating it as already-shipped would leave #159
reproducible after this feature ships, which contradicts SC-002 ("the #159
class is eliminated") — so the only reading consistent with the spec's own
success criteria is that this feature delivers the tightening itself.

**Alternatives considered**: Treat colon-form tightening as a separate,
prerequisite feature and block this plan on it landing first. Rejected —
no such feature exists in `specs/`, no issue references it as in flight, and
FR-008 is phrased as a MUST this feature satisfies, not a dependency this
feature assumes; splitting it out would leave FR-008 unsatisfied by this
plan's own tasks for no benefit (the change is a single-token edit at two
call sites, not separable implementation work).

## Decision: Resolve FR-009 — `none` is carried as an explicit discriminator in the structured output, not inferred from the artifact's absence

**Decision**: Clarify's structured output schema is
`{"answered": boolean, "clarifications": [...]}` (both required). The agent
sets `answered: false` (and an empty `clarifications` array) on exactly the
early-STOP path already described in `clarify.yml`'s prompt step 2 ("If the
reply does not actually answer any open question... STOP without editing
anything" — it has already posted its own comment by that point, unchanged
per FR-014). `answered: true` covers every other completion, with
`clarifications` empty (→ `ready`) or non-empty (→ `needs-clarification`).
The deterministic read-back step maps:

| `answered` | `clarifications` | Outcome |
|---|---|---|
| `false` | (ignored) | `none` |
| `true` | `[]` | `ready` |
| `true` | non-empty | `needs-clarification` |

A step whose terminal result is missing, unparseable, or `is_error`/non-
`success` (the step itself failed, not a legitimate agent choice) is a
**validation failure** (FR-002) — it surfaces as a run failure, and is
never coerced into `none`.

**Rationale**: The spec's FR-009 marker names exactly two candidate designs
— absence-of-structured-output vs. an explicit discriminator — and asks
which. The current-state finding above (`--json-schema` is unconditional in
both existing precedents; nothing in `claude-code-action`'s contract lets an
agent's internal branch produce a missing/non-conforming terminal result as
a *legitimate* outcome, only as a failure) rules out the absence-based
design: it would conflate "the agent deliberately chose `none`" with "the
step crashed," which is precisely the FR-002 failure mode this feature
exists to make loud rather than silently reinterpreted. The
`auto-update-spec-kit.yml` precedent (`recognized: boolean` alongside
`chosen_option`) already establishes a boolean-discriminator-plus-payload
shape in this exact codebase for an analogous three-way "did the agent find
an answer" question, so `answered` follows established, working practice
rather than inventing a new pattern.

**Alternatives considered**:
- *Infer `none` from a missing/empty terminal structured result.* Rejected
  for the reason above — it is not reliably distinguishable from a crashed
  step under this repo's actual `--json-schema` semantics, and conflating
  the two would recreate a silent-loss failure mode of the same shape this
  feature exists to close.
- *A three-value `outcome` enum (`"none" | "ready" | "needs-clarification"`)
  computed entirely by the agent*, instead of a boolean plus a derived
  read-back. Rejected — `ready` vs `needs-clarification` is *already*
  fully determined by `clarifications`' emptiness (that is FR-003's whole
  point: the decision must derive from the array, not be separately
  asserted); asking the agent to also assert the derived label creates a
  second place the two could disagree with each other, the exact defect
  shape (two independent signals for one decision) this feature is fixing.
  `answered` alone carries genuinely new information (`clarifications`
  cannot express it, since an empty array is ambiguous between "resolved"
  and "the reply didn't address anything"); `outcome` would not.

## Decision: One JSON Schema shape for intake, a superset shape for clarify

**Decision**: Both schemas share a `clarifications` array whose items are
`{"question": string (required), "context": string|null (optional),
"options": [{"answer": string (required), "implications": string|null
(optional)}] (optional)}`, wrapped in a top-level object per the diagnose
precedent's `input_schema.type` constraint. Intake's schema is
`{"type":"object","properties":{"clarifications":{...}},"required":["clarifications"]}`.
Clarify's schema adds the `answered` boolean (previous decision):
`{"type":"object","properties":{"answered":{"type":"boolean"},"clarifications":{...}},"required":["answered","clarifications"]}`.
Full definitions live in `contracts/clarification-schema.md`.

**Rationale**: FR-001 requires "at minimum a question and optionally
supporting context and a list of answer options" for both call sites — a
shared item shape avoids two divergent renderers for the same
`## Question N` format (FR-010). Intake has no early-STOP-before-schema
path analogous to clarify's (its own early-stop, "the issue does not
contain a discernible feature request," happens *before* a spec directory
exists at all, and is already gated out via `steps.created.outputs.spec-dir
!= ''` — untouched by this feature), so intake's schema does not need the
`answered` discriminator.

**Alternatives considered**: A single shared schema for both call sites,
with intake simply never setting `answered: false`. Rejected — it would let
intake's read-back silently accept a shape it structurally cannot produce a
meaningful `false` for, and would force intake's prompt to explain a field
that has no possible legitimate value there; two purpose-fit schemas, one
shared item shape, is clearer and matches how the diagnose/auto-update
precedents each define their own top-level schema while reusing the same
CLI mechanism.

## Decision: The marker cross-check compares against the same boolean the structured output would have decided, and is skipped when no post/don't-post decision is being made

**Decision**: For intake, the cross-check always runs (there is no `none`
equivalent there): `structured = (clarifications array non-empty)`,
`marker = (colon-form grep matches)`; a mismatch (`structured != marker`)
writes `clarification-mismatch` to `$GITHUB_STEP_SUMMARY` (FR-006), citing
both booleans and the spec path, but `structured` alone still selects the
branch (FR-004). For clarify, the same comparison runs only when
`answered == true` — when `answered == false` (`none`), no clarification
callout is posted in either direction (FR-009's own Edge Case), so there is
no post/don't-post decision for a marker disagreement to be *about*; running
the comparison anyway would fire on every ordinary `none` run (the reply
resolved nothing, so genuine markers almost always still remain) and
produce exactly the noise-without-signal the spec's Assumptions section
warns against ("marker prose is never a good questionnaire" — nor is an
unrelated-decision mismatch a meaningful cross-check result).

**Rationale**: FR-006's acceptance scenarios (spec.md US3) are both framed
as "the stage reconciles the two signals" while deciding a branch; `none`
is explicitly a third outcome with no branch to reconcile toward (US4).
Scoping the cross-check to the two states where it is actually informative
keeps SC-004 ("every disagreement... emits a warning") meaningful rather
than universally true-by-construction.

**Alternatives considered**: Always run the cross-check, including on
`none`. Rejected per the rationale above — it would make
`clarification-mismatch` fire routinely on the single most common clarify
outcome (a reply that didn't address the open questions, spec.md still
carrying its markers), defeating FR-012's purpose of making the watchdog
sentinel a meaningful signal rather than expected noise.

## Decision: Rendering is a deterministic bash+jq step, not a new composite action

**Decision**: The `## Question N` markdown is rendered by a `run:` step
(bash + `jq`) added immediately after each agent step, reading the same
`claude-execution-output.json` the read-back parses for the outcome
decision, and writing the rendered markdown to the same temp-file paths
already used today (`${{ runner.temp }}/intake-clarification.md`,
`${{ runner.temp }}/clarify-followup.md`) so `wing-commander-callout`'s
existing `body-file:` invocations need no change. No new composite action
is introduced.

**Rationale**: Neither existing precedent (`diagnose`, the
`auto-update-spec-kit` interpreter) uses a composite action for its
read-back/render logic — both are inline `run:` steps in the owning
workflow, because the logic is specific to that step's schema shape. A
composite action would be premature reuse for a two-call-site renderer, and
would need to be threaded through the same `.wing-commander-pipeline`
self-checkout path every other shared composite uses for no benefit over an
inline step (constitution VI is about consumer-owned *artifacts*, not about
minimizing `run:` step count).

**Alternatives considered**: A shared composite action
(`wing-commander-render-clarifications`) callable from both `intake.yml` and
`clarify.yml`. Considered but not chosen for this plan — two call sites
sharing ~15 lines of `jq` is not yet the duplication threshold that
justified `wing-commander-callout` (ten call sites, `contracts/019`) or
`wing-commander-lifecycle-gate` (used by every stage); revisit if a third
call site appears.

## Decision: No fallback questionnaire synthesis — nothing to build, a negative requirement

**Decision**: FR-007's "MUST NOT synthesise a fallback questionnaire from
raw marker text" requires no new code — it is satisfied by the absence of
any code path that reads `spec.md`'s marker text to construct a
`clarifications` array. The plan's task list must not introduce one, and
`quickstart.md`'s validation for US3 explicitly checks that a mismatch run
produces no such synthesized content.

**Rationale**: Named explicitly because the *pre-existing* design this
feature replaces has no such fallback either (today's grep either fires or
doesn't; it never manufactures question text) — the risk FR-007 guards
against is a plausible-sounding *addition* someone might reach for while
building the mismatch-warning path (e.g. "when they disagree, at least show
the marker text as a stand-in question"), not a regression from current
behavior.

## Decision: Scope confirmation — three files, no new labels, no new repository variables

**Decision**: This feature touches exactly `.github/workflows/intake.yml`,
`.github/workflows/clarify.yml`, and `.github/workflows/watchdog.yml` (the
one-line sentinel addition), per FR-013's explicit two-gate scope and
FR-012. No new GitHub label, repository variable, or `workflow_call` input
is introduced — the schema strings are inline (`--json-schema` compiled by
a `run:` step, following the `class-vocab` precedent), not configuration
surface.

**Rationale**: Matches spec's own "Scope boundary" Assumption verbatim; kept
here so `tasks.md` generation has an explicit closed file list to check
itself against, the same discipline `contracts/callout-points.md` provided
for spec 019.
