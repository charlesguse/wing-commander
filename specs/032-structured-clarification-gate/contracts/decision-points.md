# Contract: Per-Stage Decision-Point Migration

This is the per-stage migration contract for spec 032 — every existing
grep-decision site FR-003/FR-004/FR-011 covers, its current behavior, and
its new structured-output-decides shape. `contracts/clarification-schema.md`
defines the schema and render algorithm this file's steps consume;
`contracts/watchdog-sentinel.md` defines the sentinel-set addition FR-012
depends on. `wing-commander-callout`'s own interface
(`.github/actions/wing-commander-callout/action.yml`) is unchanged by this
feature — every row below keeps its existing invocation shape, only the
`if:` condition and the `body-file:` content's origin change.

## `intake.yml`

| Step (current name) | Current behavior | New behavior |
|---|---|---|
| "Create spec from issue" (agent step) | Step 7 instructs the agent to write `## Question N` prose to `${{ runner.temp }}/intake-clarification.md` when markers remain, or nothing otherwise | Gains `--json-schema` (intake schema, `contracts/clarification-schema.md`); step 7 instructs the agent to return the `clarifications` array instead of writing a file |
| "Check whether the spec still needs clarification" (`id: clarification`) | `grep -q '\[NEEDS CLARIFICATION' "$SPEC_DIR/spec.md"` → `needed=true\|false`, gated on a discoverable spec dir | Reads back the agent step's structured result (`contracts/clarification-schema.md`'s read-back idiom); `needed` = `clarifications` array non-empty. Gated on `valid == 'true'` instead of on a discoverable spec dir — the decision no longer reads `spec.md`, and skipping it when the branch push failed would silently drop an authored questionnaire. Runs the colon-form cross-check against post-agent `spec.md` when a spec dir exists; on mismatch, writes the `clarification-mismatch` line to stdout AND `$GITHUB_STEP_SUMMARY`. `needed` is decided ONLY by the structured array (FR-004) |
| *(new)* "Render clarification questionnaire" | — | New step, gated on `needed == 'true'`: renders `${{ runner.temp }}/intake-clarification.md` from the structured `clarifications` array per `contracts/clarification-schema.md`'s render algorithm, replacing the file the agent used to author itself |
| "Announce clarification needed" | `if: steps.clarification.outputs.needed == 'true'`, `body-file: ${{ runner.temp }}/intake-clarification.md` | Unchanged invocation shape; `if:` condition unchanged (still keys off `needed`); the file it reads is now deterministically rendered, not agent-authored |
| "Announce spec PR ready for review" | `if: steps.clarification.outputs.needed == 'false'` | Still the negation of the same `needed` output, so it can never be suppressed by an independently-computed condition (closing the #159 mutual-exclusivity failure mode); `&& steps.created.outputs.spec-dir != ''` is added because `needed` is no longer itself gated on a discoverable spec, and this callout must not announce a spec PR that does not exist |
| "Fail on agent API error" → "Validate agent result" + "Fail on invalid agent result" | Checks `steps.agent.outcome == 'success'` and a non-empty `.result.is_error` sentinel | Extended per `contracts/clarification-schema.md`'s validation-failure contract: a `success` step outcome whose terminal result is missing the required `clarifications` key, or fails schema validation, is also a failure (FR-002). Split in two so intake's side effects survive a dropped result: "Validate agent result" runs before the clarification step (so it can never read a coerced empty array), emits the `::error::` and publishes `valid`, exiting 0; the job's last step turns `valid != 'true'` into `exit 1`, after "Resolve created spec" and "Label spec PR to match the issue" have run |

## `clarify.yml`

| Step (current name) | Current behavior | New behavior |
|---|---|---|
| "Fold answers into the draft spec" (agent step) | Step 6 instructs the agent to write to `${{ runner.temp }}/clarify-followup.md`: which questions were resolved, or the still-open questions if markers remain; step 2's early-STOP path posts its own `gh issue comment` and writes no file | Gains `--json-schema` (clarify schema, `contracts/clarification-schema.md`); step 6 instructs the agent to return `{answered, clarifications}` instead of writing a file; step 2's early-STOP path is unchanged (FR-014) except its "STOP" now additionally means "return `answered: false, clarifications: []`" rather than "write no file" |
| "Determine clarification follow-up outcome" (`id: clarification`) | `[ ! -f "$followup" ]` → `none`; else grep on post-edit `spec.md` → `needs-clarification` / `ready` | Reads back the structured result. `answered == false` → `outcome=none` (no cross-check run — `research.md`'s scope decision). `answered == true`: `outcome` = `needs-clarification` / `ready` from `clarifications` emptiness; cross-check runs here and writes `clarification-mismatch` to stdout AND `$GITHUB_STEP_SUMMARY` on disagreement |
| *(new)* "Render clarification questionnaire" | — | New step, gated on `outcome == 'needs-clarification'`: renders `${{ runner.temp }}/clarify-followup.md` from the structured `clarifications` array (same render algorithm as intake's; the "which questions were resolved" narrative line the agent used to write is dropped — the rendered block lists only the still-open questions, matching what row 3 already posts today per `specs/019-next-step-callouts/contracts/callout-points.md` row 3) |
| "Announce remaining clarification questions" | `if: steps.clarification.outputs.outcome == 'needs-clarification'`, `body-file: ${{ runner.temp }}/clarify-followup.md` | Unchanged invocation shape and `if:` condition; file content now deterministically rendered |
| "Announce spec PR ready for review" | `if: steps.clarification.outputs.outcome == 'ready'`, `body-file: ${{ runner.temp }}/clarify-followup.md` (a "which questions were resolved" summary) | `if:` condition unchanged. `body-file:` becomes optional/omitted when `clarifications` is empty and there is no resolved-questions narrative to show — OR retains a short deterministic "all clarification questions are resolved" line if the call site still wants body content; either choice is a rendering detail `tasks.md` may finalize, NOT a decision-branch change (FR-011: this callout must never be suppressed by the questionnaire branch, and both outcomes here derive from the same `answered`/`clarifications` read, never from an independent condition) |
| "Fail on agent API error" | Same shape as `intake.yml`'s | Same extension as `intake.yml`'s row above, applied to the clarify schema's required keys (`answered`, `clarifications`). NOT split like intake's: clarify has no side-effect steps after this gate that a dropped result would strand, so it keeps the single in-place `exit 1` |

## Contract clauses

- Every `if:` condition in both tables above keys off a single upstream
  output (`needed` for intake, `outcome` for clarify) that is itself
  derived from ONE structured-output read, never from two independently
  computed conditions — this is the structural fix for #159 (mutually
  exclusive branches computed from disagreeing sources can no longer arise,
  because there is only one source).
- The colon-form marker cross-check (`contracts/clarification-schema.md`)
  runs in the SAME step that computes `needed`/`outcome`, immediately after
  the structured-output read, so the mismatch warning and the branch
  decision are always evaluated against the identical snapshot of
  `spec.md`. It is skipped — never the step around it — when no spec
  directory was resolved, since only the cross-check reads a file.
- No step in either table gains `Write`/`Edit` in its `--allowedTools` — the
  render step is a `run:` (bash/jq) step, not an agent step, and needs none.
- No step in either table changes `wing-commander-callout`'s own interface
  or any other existing label mutation (`spec:<slug>`, `stage:spec` in
  intake; none in clarify) — those stay exactly as they are today.
- Sites explicitly **not** in this table: `intake.yml`'s "Post
  excluded-comments notice" (spec 029, unrelated condition) and step 2's
  "issue does not contain a discernible feature request" early-exit
  (unaffected — gated out before a spec directory exists, per
  `research.md`) are unchanged by this feature.
