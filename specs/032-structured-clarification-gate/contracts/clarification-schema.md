# Contract: Clarification Structured-Output Schemas and Render Algorithm

This is the normative schema and read-back/render contract for FR-001,
FR-002, FR-003, FR-009, FR-010. `data-model.md` defines the conceptual
fields; this file defines the literal JSON Schema each `--json-schema`
argument compiles to, and the deterministic algorithm that turns the
resulting structured result into the posted `## Question N` markdown.

## Shared item schema: Clarification question

Both stages' `clarifications` array uses this item shape:

```json
{
  "type": "object",
  "properties": {
    "question": {"type": "string"},
    "context": {"type": ["string", "null"]},
    "options": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "answer": {"type": "string"},
          "implications": {"type": ["string", "null"]}
        },
        "required": ["answer"]
      }
    }
  },
  "required": ["question"]
}
```

## Intake schema (`intake.yml`, "Create spec from issue" step)

`clarifications` is an array of the shared item shape above, wrapped in a
top-level object (a bare top-level `"type":"array"` schema is rejected by
the API — `research.md`, diagnose precedent). The CLI's `--json-schema`
argument is a single JSON literal with no `$ref` resolution assumed
(matching every existing schema in this repo, none of which use `$ref`), so
the item shape is inlined directly:

```json
{"type":"object","properties":{"clarifications":{"type":"array","items":{"type":"object","properties":{"question":{"type":"string"},"context":{"type":["string","null"]},"options":{"type":"array","items":{"type":"object","properties":{"answer":{"type":"string"},"implications":{"type":["string","null"]}},"required":["answer"]}}},"required":["question"]}}},"required":["clarifications"]}
```

Composed as a static literal directly in the `claude_args:` block (no prior
`run:` step needs to build it — unlike `watchdog.yml`'s `class-vocab`, this
schema has no run-time-varying enum, so it does not need a `Resolve ...`
step of its own). Single-quoted in `claude_args:`, matching the diagnose
precedent's quoting rationale (`research.md`).

## Clarify schema (`clarify.yml`, "Fold answers into the draft spec" step)

Adds the `answered` discriminator (FR-009 decision, `research.md`):

```json
{"type":"object","properties":{"answered":{"type":"boolean"},"clarifications":{"type":"array","items":{"type":"object","properties":{"question":{"type":"string"},"context":{"type":["string","null"]},"options":{"type":"array","items":{"type":"object","properties":{"answer":{"type":"string"},"implications":{"type":["string","null"]}},"required":["answer"]}}},"required":["question"]}}},"required":["answered","clarifications"]}
```

## Agent-facing framing (prompt instructions, both steps)

Both prompts replace their existing "write questionnaire prose to a file"
instruction with:

- Intake step 7 (replacing the current `[NEEDS CLARIFICATION]`-marker
  instruction): "Return your final result as the `clarifications` array
  required by the provided schema: one entry per open question you were
  unable to resolve while specifying, each with `question` (required),
  `context` (the relevant spec section, optional), and `options` (your
  suggested answers, optional — each with `answer` and, optionally,
  `implications`). An empty array means the spec has no open questions. Do
  not also write a questions file yourself — a deterministic step renders
  and posts them from this array."
- Clarify step 6 (replacing the current
  "write to `${{ runner.temp }}/clarify-followup.md`" instruction): "Return
  your final result matching the provided schema: `answered` is `true` if
  the reply (step 2) addressed at least one open question and you proceeded
  to steps 3–5, or `false` if you took the early-STOP path in step 2 (the
  reply answered nothing — your own `gh issue comment` in that step is the
  only issue-facing output for this run; set `clarifications` to `[]`).
  When `answered` is `true`, `clarifications` is the array of questions
  still open after folding in the reply — empty if none remain. Do not
  also write a followup file yourself — a deterministic step renders and
  posts from this array when questions remain."

Both prompts keep every other existing instruction (the file-edit steps,
the PR-description update, the commit/push) unchanged — only the
"how do I hand off open questions" instruction is replaced.

## Read-back: locating the structured result

Both new deterministic steps parse `${{ runner.temp
}}/claude-execution-output.json` — the same artifact `watchdog.yml`'s
`Read back diagnose outcome` and `auto-update-spec-kit.yml`'s `Read back
interpretation` steps already parse — with the identical extraction
idiom:

```bash
agent_ok="$(jq -r '([.[] | select(.type=="result")] | last) as $r
  | if $r != null and $r.is_error == false and $r.subtype == "success"
    then "true" else "false" end' "$file" 2>/dev/null || echo false)"
raw="$(jq -r '[.[] | select(.type=="result")] | last | .result // empty' "$file" 2>/dev/null || true)"
```

`agent_ok != "true"` (step outcome not `success`, missing file, missing
terminal `result` record, or a non-`success` subtype) is a **validation
failure** (FR-002): the workflow step MUST surface this as a run failure
(`::error::` + `exit 1`), matching the existing "Fail on agent API error"
convention both `intake.yml` and `clarify.yml` already apply after their
agent step, extended to also catch a structurally invalid/missing
schema result here — never silently posting nothing while reporting
success.

## Render algorithm

Given a parsed `clarifications` array (already unwrapped from `raw`, e.g.
`jq -c 'if type=="object" and (.clarifications|type)=="array" then
.clarifications else [] end'` — matching the diagnose precedent's
object-unwrap idiom, degrading a non-conforming shape to `[]` only after
the FR-002 validation-failure check above has already passed), render one
`## Question N` block per item (1-indexed, in array order) to the target
temp file:

```markdown
## Question <N>

**Context**: <context, or this line omitted entirely if context is null/absent>

**What we need to know**: <question>

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | <options[0].answer> | <options[0].implications, or "—" if absent> |
| B      | <options[1].answer> | <options[1].implications, or "—" if absent> |
...
| Custom | Provide your own answer | Reply on this issue with your own answer |

**Your choice**: _Reply on this issue_
```

- Option rows are lettered A, B, C... in array order; the `Custom` row is
  always appended last regardless of how many (including zero) options
  were provided (spec.md Edge Case "Question with no options and no
  context": the block is still well-formed with only the `Custom` row).
- `context` absent (`null` or key omitted) → the `**Context**:` line is
  omitted entirely, not rendered empty.
- This reproduces `.claude/skills/speckit-specify/SKILL.md`'s existing
  `## Question [N]: [Topic]` shape minus the `: [Topic]` suffix — FR-010
  requires the `## Question N` heading, the context, the question, and the
  suggested-answer table; the schema carries no separate `topic` field
  (`data-model.md` deliberately omits one — the `question` field alone is
  what a maintainer needs to read), so the heading is `## Question N`
  exactly.
- An empty `clarifications` array renders no blocks at all and the
  deterministic decision step (`contracts/decision-points.md`) does not
  invoke `wing-commander-callout` for the questionnaire branch in that
  case.

The render step is plain `bash`/`jq` (a `printf`/`jq -r` loop over the
array, one block per iteration, appended to the target file) — no new
composite action, no new script under `.specify/scripts/` (`research.md`'s
rendering-location decision).

## Marker cross-check (FR-004–FR-008)

Both decision steps additionally run, against the **post-edit** `spec.md`
(for `clarify.yml`, after the agent's file edits — matching spec 019's
existing ordering discipline, `specs/019-next-step-callouts/contracts/
callout-points.md`):

```bash
if grep -q '\[NEEDS CLARIFICATION:' "$SPEC_DIR/spec.md"; then
  marker=true
else
  marker=false
fi
```

`structured` is derived per `data-model.md`'s Stage outcome table. When
`structured != marker` (and, for clarify, only when the outcome is not
`none` — `research.md`'s cross-check-scope decision), the step appends to
`$GITHUB_STEP_SUMMARY`:

```text
⚠️ clarification-mismatch: structured output reported clarifications=<empty|non-empty> but the colon-form marker scan found <a match|no match> in <spec-dir>/spec.md.
```

The literal token `clarification-mismatch` MUST appear verbatim in that
line — it is what `contracts/watchdog-sentinel.md`'s alternation matches
against. `marker`'s value is never used for anything else (FR-004): the
branch selection in `contracts/decision-points.md` reads only
`structured`.
