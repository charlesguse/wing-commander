# Phase 1 Data Model: Structured Clarification Questionnaires

This feature has no runtime data store; its "entities" (per `spec.md`'s Key
Entities section) are realized as the JSON Schema shape each agent step's
`--json-schema` argument enforces, and the fields the deterministic
read-back/render step derives from the resulting structured result. Full
schema JSON is in `contracts/clarification-schema.md`; this document
specifies the conceptual fields, relationships, and validation rules.

## Entity: Clarification question

One open question the agent authored (spec.md Key Entities: "a question,
optional context, optional answer options — rendered into a `## Question N`
block"). One array item in both stages' structured output.

| Field | Description | Required |
|---|---|---|
| `question` | The specific thing the maintainer must decide — rendered as the `**What we need to know**:` line | yes |
| `context` | Quoted/paraphrased relevant spec section — rendered as the `**Context**:` line | no |
| `options` | Ordered list of Answer Options — rendered as rows A, B, C... of the suggested-answer table | no |

**Validation rules**:
- `question` MUST be non-empty (FR-001 "at minimum a question"; a schema
  violation here is a validation failure per FR-002, not a silently
  dropped item).
- An item with no `options` still renders a well-formed block (spec.md Edge
  Case "Question with no options and no context": only a `Custom` row) —
  the renderer, not the schema, guarantees this (`contracts/
  clarification-schema.md`'s render algorithm).
- `options`, when present, MUST be non-empty if the key is included at all
  (an empty array and an absent key are the same "no options" case; the
  schema permits either and the renderer treats them identically).

## Entity: Answer option

One suggested answer for a Clarification question — one row of the
`**Suggested Answers**:` table (excluding the always-present `Custom` row).

| Field | Description | Required |
|---|---|---|
| `answer` | The suggested answer text — the `Answer` column | yes |
| `implications` | What choosing this answer means for the feature — the `Implications` column | no |

**Validation rules**: `implications` absent renders an em dash (`—`) in the
Implications column rather than an empty cell (spec.md Assumptions:
"the absence of an implications field in the structured output is
acceptable").

## Entity: Clarification questionnaire (intake structured output)

The schema-validated artifact `intake.yml`'s agent step emits (spec.md Key
Entities). Wrapped in a top-level object per the diagnose precedent's
`input_schema.type` constraint (`research.md`).

| Field | Description | Required |
|---|---|---|
| `clarifications` | Array of Clarification question | yes (may be empty) |

**Validation rules**:
- An empty array is the deciding signal for "no open questions" (FR-001) —
  distinct from a missing/malformed structured result, which is a
  validation failure (FR-002), never coerced to empty.
- This is the sole schema for `intake.yml`; intake has no `none`-equivalent
  outcome once a spec directory exists (its own early-stop, "no discernible
  feature request," happens before this step is reached and is unaffected
  by this feature — `research.md`).

## Entity: Clarify read-back envelope (clarify structured output)

The schema-validated artifact `clarify.yml`'s agent step emits — a superset
of the intake shape, carrying the discriminator that keeps `none` distinct
from an empty `ready` array (FR-009, `research.md`'s FR-009 decision).

| Field | Description | Required |
|---|---|---|
| `answered` | `true` if the reply addressed at least one open question (the agent proceeded past its early-STOP check); `false` on the early-STOP path itself | yes |
| `clarifications` | Array of Clarification question still open after folding in the reply. Meaningful only when `answered` is `true`; the agent sets it to `[]` when `answered` is `false` | yes (may be empty) |

**Validation rules**:
- `answered: false` → Stage outcome `none`, regardless of `clarifications`
  content (the deterministic read-back ignores `clarifications` in this
  case — FR-009 Edge Case "Clarify early-STOP").
- `answered: true` + `clarifications: []` → Stage outcome `ready`.
- `answered: true` + `clarifications` non-empty → Stage outcome
  `needs-clarification`.
- A missing/unparseable/`is_error` terminal result is a validation failure
  (FR-002) at the step level, never mapped to `none` (`research.md`'s
  FR-009 decision: `--json-schema` never legitimately omits a conforming
  result in this codebase's existing usage).

## Entity: Marker cross-check

A deterministic scan of `spec.md` for the colon-form marker, used only to
detect disagreement (spec.md Key Entities).

| Field | Description |
|---|---|
| pattern | `\[NEEDS CLARIFICATION:` (colon-form — tightened from today's bare-token grep, FR-008) |
| `structured` | boolean: does the relevant structured-output array decide "questions open"? (intake: `clarifications` non-empty; clarify: `answered && clarifications` non-empty) |
| `marker` | boolean: does the colon-form grep match `spec.md`? |
| `mismatch` | `structured != marker` |

**Validation rules**:
- `marker` MUST NOT influence which callout branch runs (FR-004) — it is
  read, compared, and discarded for branch-selection purposes.
- When `mismatch` is true, the run writes `clarification-mismatch` to
  `$GITHUB_STEP_SUMMARY`, citing both boolean values and the spec path
  (FR-006).
- For clarify, this check runs only when the Stage outcome is not `none`
  (`research.md`'s cross-check-scope decision) — there is no post/don't-post
  decision for a disagreement to be about when the reply resolved nothing.
- No questionnaire content is ever derived from the marker match itself
  (FR-007) — `marker` is a boolean, never a source of question text.

## Entity: Stage outcome

The decision each stage's deterministic step reaches, gating which callout
(if any) is posted (spec.md Key Entities).

| Stage | Possible outcomes | Determined by |
|---|---|---|
| `intake.yml` | `needed` (post clarification callout) / not needed (post spec-PR-ready callout) | `clarifications` array non-empty / empty |
| `clarify.yml` | `none` / `ready` / `needs-clarification` | `answered` + `clarifications` (table above) |

**Relationships**:
- `needed` / `needs-clarification` → the deterministic render step's output
  file is passed as `wing-commander-callout`'s `body-file:` for the
  existing "Answer the open/remaining clarification questions" action
  callout (unchanged `wing-commander-callout` invocation shape,
  `contracts/decision-points.md`).
- not-needed / `ready` → the existing "Review the spec PR" action callout
  fires, unsuppressed by the questionnaire branch (FR-011 — the two
  branches are `if:` steps keyed off the *same* Stage outcome, mutually
  exclusive by construction rather than by two independently-computed
  conditions, which is what let #159 delete the correct branch).
- `none` → neither callout is posted; the agent's own early-STOP comment
  (unchanged, FR-014) is the only issue-facing signal for this run.

## Entity: Step-summary sentinel set

The watchdog's list of phrases whose presence in a run's step summary marks
a run as carrying a defect signal (spec.md Key Entities); gains
`clarification-mismatch`.

| Field | Before | After |
|---|---|---|
| `sentinels` (watchdog.yml ~line 618) | `'stalled\|rejected\|turn budget warning\|could not inspect\|denied\|abandon'` | `'stalled\|rejected\|turn budget warning\|could not inspect\|denied\|abandon\|clarification-mismatch'` |

**Validation rules**: No other sentinel-handling code changes — the
downstream fingerprint/dedup machinery (`.github/workflows/watchdog.yml`'s
`Stamp signal ids` step) keys off whichever alternation member matched,
generically, per the existing `step-summary` signal-kind mapping
(`research.md`). Full contract in `contracts/watchdog-sentinel.md`.

## State / lifecycle

None of these entities have persisted state — each is a point-in-time
decision made fresh by the deterministic read-back step immediately
following an agent step's terminal result, using only that run's own
`claude-execution-output.json` and a fresh grep of the current `spec.md`.
No new field is added to `spec-meta.json`. The rendered questionnaire
markdown is written to the same runner-temp paths `wing-commander-callout`
already consumes today; nothing about the callout's own append-only posting
model (spec 019, FR-012 there) changes.
