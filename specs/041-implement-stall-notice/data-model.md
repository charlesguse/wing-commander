# Phase 1 Data Model: An Implement Run That Dies at Entry Still Marks the Record and Says So on the Issue

This feature introduces no new persisted data store. `spec-meta.json`'s
existing schema is unchanged — the `stage` field's value set already includes
`"stalled"` (used today by the exhausted-retry path); this feature causes it
to be written for new *causes*, not new *values*. Every shape below is either
ephemeral (job/step outputs, for the duration of one run) or a rendering
contract (the two notice bodies).

## Refusal signal (new — one per refusal-shaped step)

| Field | Type | Meaning |
|---|---|---|
| `refused` | `"true"` \| unset | Written immediately before the step's own `exit 1`. Unset means either the step succeeded or it never reached this line — treated as "not a refusal" either way (FR-005a: absence is never positive evidence) |
| `reason` | string | One-sentence, human-authored (not user-input-derived — research.md's Constitution Check row) text naming what was missing and, where the step already knows it, who can resolve it. Reuses each step's *existing* error message verbatim (D2) — no new wording invented, only an additional write of the same text to `$GITHUB_OUTPUT` |

Emitted by (Phase 2 tasks generation enumerates the exact call sites per
research.md D10's rule, not a fixed list):
- `wing-commander-preflight`'s `fail()` helper (composite-level outputs,
  since `fail()` is the single step of that composite)
- `implement.yml`'s `Resolve and validate spec identity` (`id: spec`)
- `implement.yml`'s `Verify spec artifacts match the dispatch` (`id: meta`)
- the equivalent preflight/identity-validation steps in clarify, finalize,
  intake, pr-conversation, tasks (discovered per-stage, same rule)

## Entry-job output: `refusal-reason` (new — one per gated entry job)

| Field | Source | Meaning |
|---|---|---|
| `refusal-reason` | `${{ steps.<a>.outputs.reason \|\| steps.<b>.outputs.reason \|\| ... }}` across every refusal-shaped step declared in that job | Empty when the job succeeded, was skipped (job outputs are unconditionally empty for a skipped job — research.md D3), or failed for a reason no step flagged as a refusal. Non-empty only when a refusal-shaped step in *this* job actually ran and refused |

This is an internal job-to-job output within one workflow file — **not** a
`workflow_call` output of the stage (research.md D3, plan.md's Constitution
Check row VII). It does not appear in any stage's published contract.

## Survivor job condition (new/widened — one per gated stage)

| Stage | `needs:` | `if:` |
|---|---|---|
| implement | `[verify-image-prerequisites, implement]` | `!cancelled() && (needs.verify-image-prerequisites.result == 'failure' \|\| needs.implement.result == 'failure' \|\| needs.implement.result == 'skipped' \|\| needs.implement.outputs.final-ok == 'false')` |
| finalize | `[verify-image-prerequisites, finalize]` | `!cancelled() && (needs.verify-image-prerequisites.result == 'failure' \|\| needs.finalize.result == 'failure' \|\| needs.finalize.result == 'skipped')` |
| clarify | `[verify-image-prerequisites, clarify]` | `!cancelled() && (needs.verify-image-prerequisites.result == 'failure' \|\| needs.clarify.result == 'failure' \|\| needs.clarify.result == 'skipped')` |
| intake | `[verify-image-prerequisites, intake]` | `!cancelled() && (needs.verify-image-prerequisites.result == 'failure' \|\| needs.intake.result == 'failure' \|\| needs.intake.result == 'skipped')` |
| pr-conversation | `[verify-image-prerequisites, classify-and-announce]` | `!cancelled() && (needs.verify-image-prerequisites.result == 'failure' \|\| needs.classify-and-announce.result == 'failure' \|\| needs.classify-and-announce.result == 'skipped')` |
| tasks (`generate`) | `[verify-image-prerequisites, tasks]` | same shape, `needs.tasks.*` |
| tasks (`approved`) | `[verify-image-prerequisites, tasks-approved]` | same shape, `needs.tasks-approved.*` |

`implement` is the only row with the fourth arm
(`needs.implement.outputs.final-ok == 'false'`) — the exhausted-retry case,
which only this stage's job graph produces (D7). Every survivor job's steps
additionally split into two mutually exclusive arms by reading
`needs.<entry-job>.outputs.refusal-reason` (empty → abnormal-termination
notice via the new composite; non-empty → this job posts nothing, because
the in-job refusal callout (D1) already did — FR-006's exclusivity holds by
construction, not by a runtime check).

## `wing-commander-chain-stop-notice` composite (new)

| Input | Required | Meaning |
|---|---|---|
| `token` | yes | Write token (issues: write, contents: write) — same App-installation token every composite already receives |
| `issue-number` | yes | Where to post. For pr-conversation's degraded case (research.md D6), this is `pr-number` — the composite does not distinguish an "issue" from a "PR" (both are `gh issue comment` targets) |
| `spec-dir` | no (default empty) | When empty, the record-mark step is skipped and the notice renders the "record could not be updated" wording unconditionally (research.md D5 — this is how intake is handled, and how a genuine checkout/push failure on any other stage is handled) |
| `spec-branch` | no (required together with `spec-dir`) | Branch to check out for the mark (`${{ inputs.spec-prefix }}${{ slug }}`, caller-resolved) |
| `stage-label` | no (default empty) | `stage:<name>` label to remove when the mark succeeds (e.g. `stage:clarify`) — omitted for intake, which has no predecessor stage label to remove |
| `run-url` | no | Defaults to the composite's own `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}` when not supplied — always available regardless of any job's outcome, since it is workflow-run context, not a job output |
| `reason` | yes | One sentence: where the run stopped (dependency name, or "the stage's own first step") |
| `restart-command` | no (default empty) | Fully caller-rendered restart instructions (FR-008 — each stage owns its own restart-iteration math; implement's reuses the existing `recorded_iteration + 1` formula, the other five have no iteration to compute and render a plain re-dispatch command instead) |

| Output | Meaning |
|---|---|
| (none) | Best-effort by design (FR-011) — a caller does not branch on this composite's own success; its internal steps degrade rather than propagate failure upward, mirroring today's `stalled` job's `Report`/`Announce` steps already carrying `if: always()` relative to the mark step |

Internal steps (mirrors today's three-step sequence in `implement.yml`'s
`stalled` job, generalized):
1. **Checkout spec branch** (`if: inputs.spec-dir != ''`) — failure here
   (branch missing, e.g. a force-push race) is caught, not propagated; sets
   an internal `record-status` flag to `unwritable`.
2. **Mark `spec-meta.json` stalled** (`if: inputs.spec-dir != '' &&
   <checkout succeeded>`) — `jq '.stage = "stalled"'`, commit, push.
   Tolerates "nothing to commit" (already-stalled record, as today) as
   success; tolerates a rejected push (also a race) by setting
   `record-status: unwritable` rather than failing the composite.
3. **Flip labels** (`if: always()`) — applies `stage:stalled` always; removes
   `stage-label` only when non-empty and the mark succeeded.
4. **Post the notice** (`if: always()`) — renders one of two bodies (below)
   depending on `record-status`, via the same `--body-file` (never
   `--body "$(...)"`) discipline `wing-commander-callout` already
   establishes.

## Notice content (two new shapes; the existing exhausted-retry body is unchanged and out of scope)

### "Stage did not start" stall notice (abnormal termination, all six stages)

Rendered by the new composite's step 4 when `record-status` is `marked`:

```
⏸️ **<Stage> stalled — the stage did not start**

<reason> ($run-url).

No implementation attempt was made — nothing was escalated, no model tier
was used, and no work was lost. This specification's lifecycle record has
been marked stalled.

$restart-command
```

When `record-status` is `unwritable`:

```
⏸️ **<Stage> stalled — the stage did not start**

<reason> ($run-url).

No implementation attempt was made. **The lifecycle record could not be
updated** — <checkout|push> failed; a maintainer should confirm the spec
branch and the record's `stage` field by hand before restarting.

$restart-command
```

Satisfies FR-007 (names the stop, not an attempt; no model tier; no
escalation claim), FR-008 (restart-command is caller-correct per stage), and
the Edge Cases "record cannot be written" entry (explicit wording, not a
silent omission).

### "Could not start" refusal note (all six stages, in-job)

Posted via the existing `wing-commander-callout` composite, `kind: action`:

```
summary: "This stage could not start — <reason>."
body:    (omitted, or names who can resolve it when the refusing step knows
          — e.g. "Set the ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
          secret." for a credential refusal)
```

No record mark, no label change (FR-005). Renders inside GitHub's
`[!IMPORTANT]` callout box, visually distinct from the plain-text stall
notice above — satisfying User Story 2's "the maintainer can tell the two
apart at a glance."

## Gate registry entries

| Gate | Change | Proves |
|---|---|---|
| 15 (amended) | `NON_SUCCESS_ARM` pattern broadened to `needs.<job>.outputs.<name> == '<value>'`, alongside the existing `.result == '...'` shape; existing fixture `CASES` unchanged, new cases added for the output-based shape and for `stalled`'s actual pre-fix condition | FR-015 (no shape Gate 15 already caught is lost; the shape this feature fixes is detectable going forward) |
| 28 (new) — `.github/scripts/verify-chain-stop-notice.py` | Extracts each of the seven survivor-job `if:` strings (data-model.md's condition table) via a job-aware extension of `wc_shell_harness.py`'s YAML access; evaluates each against a fixture table of `needs.*` result/output combinations; asserts the boolean matches the intended reachability (fires on dependency-failure/job-failure/job-skip/exhausted-retry-flag; does not fire on success, cancellation, or a refusal-flagged failure) | FR-012 (modelled-failure coverage), FR-013 (four required mutations below), FR-014 (the gate's own wiring is checked by the existing `wc_gate_registry.py`/Gate 10 mechanism — no separate reflexive check needed, unlike spec 039's Gate 25, because Gate 10 already covers this uniformly) |

### Gate 28 required mutations (FR-013)

| Mutation | Expected result |
|---|---|
| Remove `!cancelled()` (or `always()`) from a survivor job's `if:`, leaving only the `needs.*` comparisons | Fails — the mutated condition is provably suppressed by GitHub's implicit `success()`, detected the same way Gate 15's own self-test proves its fixtures |
| Narrow a survivor condition so `needs.<entry-job>.result == 'failure'` is removed, leaving only `'skipped'` | Fails — the modelled "entry job itself failed" scenario no longer reaches the notice |
| Widen a survivor condition to also fire when `needs.<entry-job>.result == 'success'` | Fails — the modelled "healthy run" and "refusal" scenarios now wrongly reach the notice, violating FR-004/FR-006 |
| Point one of the six stages' survivor job at a bespoke condition string not matching the shared table | Fails — Gate 28 asserts every one of the seven call sites uses the shape in data-model.md's table, not merely that each independently "looks right" (FR-017a) |
