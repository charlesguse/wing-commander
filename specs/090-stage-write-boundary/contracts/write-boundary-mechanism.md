# Contract: The Write Boundary Mechanism

This is the stage-internal contract this feature ships. It widens
`implement.yml`'s and `finalize.yml`'s published `workflow_call` contracts
only by new optional inputs (FR-021) — see "What stays the same" below. It
documents the contract between:

1. `implement.yml`'s `no-write-paths`/`write-boundary-label-prefix` inputs
   and `wing-commander-tool-args`.
2. `wing-commander-tool-args` and both agent prompts (the statement).
3. The checkbox-count composite's `unchecked-items` output and the new
   `wing-commander-write-boundary` composite.
4. The read-back steps' new `routed` output and the new "Route
   out-of-boundary tasks" step.
5. `wing-commander-stage-findings`'s new `finding-kind` input.
6. `finalize.yml`'s new deterministic lookup step and its prompt.

## 1. `implement.yml` — new `workflow_call` inputs

| Name | Required | Default | Description |
|---|---|---|---|
| `no-write-paths` | no | `.claude/` | Comma-separated path prefixes this run's agent may not target with `Edit`/`Write` (FR-002, FR-019). |
| `write-boundary-label-prefix` | no | `route-out-of-boundary` | Label prefix for a routed out-of-boundary task, producing `<prefix>:implement` (FR-007). Distinct from `findings-label-prefix` by design — see §5 and research.md D4. |

`finalize.yml` gains `write-boundary-label-prefix` only (same default), for
its lookup step (§6). It has no `no-write-paths` input — it never
classifies a task, only looks up an already-filed one by fingerprint.

## 2. Composite action: `wing-commander-tool-args` (extended)

**Path**: `.github/actions/wing-commander-tool-args/action.yml` (published
surface).

**New input**: `no-write-paths` (optional, default `""`) — passed straight
through from `implement.yml`'s own input of the same name, unsplit.

**New output**: `write-paths-statement` — composed by the existing
`compose` step, immediately after the `shell_commands` render (action.yml
lines ~186-360), using the same classify/render shape:

- `no-write-paths` empty → `"This run's agent may write any path in the
  checkout."`
- `no-write-paths` non-empty → `"This run's agent may not write: <comma-
  joined, deduped, trimmed list>."`

No existing input, output, or the `shell-commands` render's own text
changes.

**Call sites**: the same two call sites `implement.yml` already has
(`tool-args-cycle` line 849, `tool-args-retry` line 1562) each gain
`no-write-paths: ${{ inputs.no-write-paths }}` in their `with:` block. The
third, read-only call site (line 2336, which denies `Write,Edit` outright)
is unaffected — it needs no write-paths statement because its step cannot
write at all.

## 3. Composite action: `wing-commander-write-boundary` (new)

**Path**: `.github/actions/wing-commander-write-boundary/action.yml`
(published surface — a minor-version addition, same class as
`wing-commander-tasks-checkbox-count`).

**Inputs**:

| Name | Required | Description |
|---|---|---|
| `unchecked-items` | yes | The literal multi-line text `wing-commander-tasks-checkbox-count`'s own `unchecked-items` output already produced for the ref being classified (never re-read from `tasks.md` — data-model.md). |
| `no-write-paths` | yes | Same value as `implement.yml`'s input, unsplit. |
| `spec-dir` | yes | e.g. `specs/090-stage-write-boundary` — for the fingerprint basis and `findings-json` evidence. |
| `tasks-path` | yes | e.g. `specs/090-stage-write-boundary/tasks.md` — the exact repo-relative path fingerprinted (data-model.md). |

**Outputs**:

| Name | Shape | Description |
|---|---|---|
| `findings-json` | JSON array | One entry per out-of-boundary unchecked task, shaped to `.github/schemas/stage-finding.schema.json` (data-model.md). `[]` when none. |
| `all-unchecked-out-of-boundary` | `true`/`false` | `true` iff at least one unchecked line exists and every one classified out-of-boundary. |
| `out-of-boundary-count` | digits | `len(findings-json)`. |

**Delegates to**: `.github/actions/_shared/classify-out-of-boundary-tasks.sh`
(the one home of the per-task classification rule — data-model.md's table),
mirroring how `wing-commander-tasks-checkbox-count` delegates to
`count-tasks-checkboxes.sh`.

**Call sites**: cycle arm (`write-boundary-cycle`, fed by
`checkbox-tip-cycle`'s output) and retry arm (`write-boundary-retry`, fed by
`checkbox-tip-retry`'s output), one call each, immediately after their
respective checkbox-count call.

**Failure behavior**: unlike `wing-commander-tasks-checkbox-count`, this
composite never fails the job — a task text it cannot confidently classify
falls through to "ordinary" (FR-015's own conservative default), which is a
valid, expected output, not an error condition.

## 4. Read-back steps: new `routed` output and reason-narrative branch

Step: `Read back cycle outcome` (id `outcome`) / `Read back retry outcome`
(id `retry-outcome`) — unchanged decision table for
`ok`/`truncated`/`converged`/`progressed`/`handoff` (research.md D5; spec
059's own contract, `contracts/convergence-signal.md` §2, is not
reopened).

**New step-local output**: `routed` (`true`/`false`) = `handoff &&
all-unchecked-out-of-boundary`, read from the corresponding
`write-boundary-*` call's `all-unchecked-out-of-boundary` output. Carried
through `Consolidate final outcome`'s existing `RETRY_RAN` selection
alongside `progressed`/`handoff`, together with `findings-json` (carried as
a step output, not re-derived).

**Reason narrative**: when `routed=true`, `reason` names each out-of-
boundary task (from `findings-json`'s `title` fields) and states the loop
is ending here because the only remaining work is outside the stage's write
boundary (FR-011) — replacing, only in this branch, spec 059's generic
hand-off phrasing. When `routed=false`, every existing narrative case is
unchanged.

## 5. Composite action: `wing-commander-stage-findings` (extended)

**New input**: `finding-kind` (optional, allowed `defect`|`routed-task`,
default `defect`).

**Behavior change, `routed-task` only**:

| Rendered text | `defect` (unchanged) | `routed-task` (new) |
|---|---|---|
| Recap phrase (created) | `"a defect was filed by the $STAGE stage"` | `"work the $STAGE stage could not complete under its write boundary was filed"` |
| Recap phrase (commented) | `"a defect met by the $STAGE stage was recorded on an existing issue"` | `"work the $STAGE stage still could not complete under its write boundary was recorded on an existing issue"` |
| `label-description` | `"...the $STAGE stage met a defect outside its own task"` | `"...the $STAGE stage was assigned work outside its write boundary"` |

No other input, output, the fingerprint formula (§ below), the cap, or the
dedup call changes for either kind.

**Internal refactor**: the anchor/fallback fingerprint computation (today
inline, action.yml lines ~307-335) is extracted to
`.github/actions/_shared/compute-finding-fingerprint.sh`; this composite
calls it instead of computing the hash inline. Purely internal — no input
or output name changes.

**Call site** (new, `implement.yml`): "Route out-of-boundary tasks," beside
the existing "File findings from this run" (line ~2260), guarded
`if: !cancelled() && steps.final.outputs.ok == 'true' && steps.final.
outputs.truncated != 'true' && steps.final.outputs.routed == 'true'`
(FR-013's truncated exclusion, plus the `routed` gate):

```yaml
with:
  token: ${{ env.WC_BOT_TOKEN }}
  stage: implement
  enabled: ${{ inputs.findings-filing-enabled }}
  channel-mode: structured-array
  findings-json: ${{ steps.final.outputs.write-boundary-findings-json }}
  finding-kind: routed-task
  spec-dir: ${{ steps.spec.outputs.spec-dir }}
  run-url: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
  lifecycle-issue-number: ${{ inputs.issue-number }}
  label-prefix: ${{ inputs.write-boundary-label-prefix }}
  cap: ${{ inputs.findings-cap }}
```

Reusing `findings-cap`/`findings-filing-enabled` rather than adding parallel
cap/enable inputs — this channel is not configurably distinct along those
axes from the existing findings channel, only along the label/wording axes
§5 already gives it.

## 6. `finalize.yml`: routed-item lookup (new)

**New step**: "Look up routed write-boundary items," deterministic, before
the existing "Summarize change and extract remaining manual work" step
(`finalize.yml:686`). For each unchecked line in the tip's `tasks.md`:
compute its fingerprint via `compute-finding-fingerprint.sh` (same formula,
§5's shared helper: `stage=implement`, `file_path=<spec-dir>/tasks.md`,
`gate_or_artifact=<the line's literal text>`), then
`gh issue list --search '"<!-- wing-commander-finding: fingerprint=<fp>
-->"' --label '${{ inputs.write-boundary-label-prefix }}:implement'
--json url,state`. Emits a mapping (line text → issue URL) for every match.

**Prompt change** (`finalize.yml:722-738`): the existing instruction to
write "every `tasks.md` item that is still unchecked" gains: "For any item
in the lookup mapping below, write `<item> — routed, see <issue url>`
instead of composing your own description of it; write every other item as
today." The mapping itself is rendered into the prompt from the new step's
output, never re-derived by the agent (Principle IX).

## What stays the same (explicitly out of this contract's scope)

- `implement.yml`'s and `finalize.yml`'s `workflow_call` inputs/outputs
  other than the additive inputs named in §1 (FR-021).
- Spec 059's convergence/progress/hand-off decision table
  (`specs/059-converged-means-tasks-done/contracts/convergence-signal.md`)
  — not reopened (research.md D5, Out of Scope).
- `wing-commander-tasks-checkbox-count`'s own contract (Dependencies
  section — left unchanged).
- `wing-commander-stage-findings`'s `defect`-kind (default) rendered text,
  byte-for-byte.
- Any vendored `.claude/skills/speckit-*` artifact (FR-016).
