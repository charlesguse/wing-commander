# Contract: `verify` job's end-to-end tier, `e2e-stage` job, and the scratch-repository lifecycle

This project has no library/API surface; its "interfaces" are the GitHub
Actions job/step contract and the deterministic checks/writes that must run
in order, same as `specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md`,
which this document extends rather than replaces. Everything in that
contract not called out below is unchanged.

## `verify` job — end-to-end tier (replaces the copy-and-check-non-empty step)

Runs only when `needs.prepare.outputs.release-type != 'patch' &&
steps.lightweight.outputs.passed == 'true'` (unchanged gating condition).
In the same isolated worktree the lightweight tier already created
(`$WORKTREE`, `$FEATURE_DIR`):

1. **spec.md non-empty** (new assertion, no new script call — reuses
   lightweight's own `create-new-feature.sh` run): `[ -s "$FEATURE_DIR/spec.md" ]`.
   Fail → `failure-detail` names `spec.md`, plus the FR-008 hint (missing-
   artifact case).
2. **`setup-plan.sh --json`**: run with `SPECIFY_FEATURE_DIRECTORY="$FEATURE_DIR"`
   in `$WORKTREE`. Fail (non-zero exit) → `failure-detail` names
   `setup-plan.sh` and the captured stderr tail (same `tail -c 500` pattern
   the lightweight tier's checks already use). Success → assert
   `FEATURE_SPEC`/`IMPL_PLAN`/`SPECS_DIR`/`BRANCH` are all present and
   non-empty in the JSON, and `[ -s "$IMPL_PLAN" ]` on disk. Either failing →
   `failure-detail` names the missing field or empty file, plus the FR-008
   hint when the cause is the empty-file case.
3. **`setup-tasks.sh --json`**: run with the same `SPECIFY_FEATURE_DIRECTORY`.
   Fail → `failure-detail` names `setup-tasks.sh` and the captured stderr
   tail (this script has no silent-empty path of its own — a failure here
   is always a hard error, so no FR-008 hint variant is needed for this
   check specifically, though the general hint still applies if the root
   cause is a missing `tasks-template.md`, which is exactly what makes this
   script exit non-zero). Success → assert `FEATURE_DIR`/`AVAILABLE_DOCS`/
   `TASKS_TEMPLATE` present, `AVAILABLE_DOCS` is a JSON array (possibly
   empty), `TASKS_TEMPLATE` non-empty and resolves to an existing file.
4. **e2e-stage result** (from the new `e2e-stage` job, `needs: e2e-stage`
   added to `verify`'s existing `needs: prepare`): if
   `needs.e2e-stage.result` is not `success`, or its `passed` output is not
   `true`, `end_to_end.passed=false` with `needs.e2e-stage.outputs.failure-detail`
   carried forward verbatim (already phrased per FR-021's
   completion-vs-shape distinction, research.md).

`end_to_end.passed` is `true` only if all four checks above pass — same
single-boolean combine shape `combine` already expects from specs/027, so
`combine`'s own logic (tier selection, folding `lightweight`/`end-to-end`
into one `passed`/`failure-detail`) requires no structural change, only a
richer `failure-detail` source.

## `e2e-stage` job (new)

```yaml
e2e-stage:
  needs: prepare
  if: needs.prepare.outputs.release-type != 'patch'
  runs-on: ubuntu-latest
  outputs:
    passed: ${{ steps.readback.outputs.passed }}
    failure-detail: ${{ steps.readback.outputs.failure-detail }}
    scratch-repo: ${{ steps.scratch-repo.outputs.full-name }}
  steps:
    # 1. Wing Commander context (bot token) — same pattern every job uses.
    # 2. Create-or-reuse the scratch repository (idempotent: gh repo view
    #    then create-if-absent), named
    #    "${{ github.repository_owner }}/wing-commander-e2e-${{ needs.prepare.outputs.issue-number }}".
    # 3. Clone it locally; run the candidate's own
    #    `uvx --from git+https://github.com/github/spec-kit.git@v${CANDIDATE}
    #    specify init . --ai claude --script sh --ai-skills --here --force`
    #    (same command `prepare` already runs); commit and push the scaffold.
    # 4. claude-code-action@v1 (id: decide), continue-on-error: true, bounded
    #    timeout-minutes, --model ${{ inputs.e2e-stage-model }},
    #    --max-turns ${{ inputs.e2e-stage-max-turns }}, least-privilege
    #    --allowedTools/--disallowedTools (no web tools, no git push),
    #    prompt: a fixed throwaway feature description — never issue/comment
    #    text (no untrusted input to this step at all).
    # 5. Read back stage result (id: readback) — deterministic, never trusts
    #    agent narration: steps.decide.outcome != 'success' OR no non-empty
    #    specs/*/spec.md in the clone -> passed=false with a failure-detail
    #    that states explicitly whether the stage failed to complete or
    #    completed without the documented output (FR-021).
    # 6. Best-effort: if passed, push the produced spec.md to the scratch
    #    repo too (non-gating — failure here does not flip `passed`).
```

`inputs.e2e-stage-model` (default `claude-sonnet-5`, sourced from
`vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL`) and
`inputs.e2e-stage-max-turns` (default `20`) are new `workflow_call` inputs
on `auto-update-spec-kit.yml`, threaded from the wrapper the same way
`inputs.model` already is.

## Scratch-repository deletion — event-driven

`wing-commander-auto-update-spec-kit.yml`'s trigger contract gains:

```yaml
on:
  issues:
    types: [closed]
```

resolved into the existing typed-input shape:

```yaml
with:
  trigger: >-
    ${{ github.event_name == 'schedule' && 'scheduled'
        || github.event_name == 'workflow_dispatch' && 'dispatch'
        || github.event_name == 'pull_request' && 'pr-merged'
        || github.event_name == 'issues' && 'issue-closed'
        || 'comment-reply' }}
  issue-number: ${{ github.event.issue.number || '' }}
```

A new job/branch in `auto-update-spec-kit.yml`, gated on
`inputs.trigger == 'issue-closed'`:

1. Fetch the closed issue's body; verify it carries this feature's own
   settle-tracking marker (specs/027 data-model.md) — a closed issue that
   isn't this feature's own lifecycle issue is a no-op, same
   self-recognition discipline every other trigger already applies.
2. `gh repo delete "${{ github.repository_owner }}/wing-commander-e2e-${{ inputs.issue-number }}" --yes 2>/dev/null || true` —
   idempotent; a repository that was never created (e.g. the run never
   reached `e2e-stage`, or this was a patch-only cycle) is a silent no-op,
   not an error.

## Scratch-repository deletion — scheduled backstop

Added to the existing `scheduled`/`dispatch` entry point, independent of
that day's own detect/settle/verify cycle (runs even when there's nothing
new to check):

1. `gh repo list "${{ github.repository_owner }}" --json name --jq '.[].name' | grep '^wing-commander-e2e-'`
2. For each match, derive `<issue>` from the name suffix; `gh issue view
   <issue> --json state` — state `CLOSED` or the lookup itself failing
   (issue missing) → delete; state `OPEN` → leave alone.

## Self-recognition contract (extends specs/027's)

- `issues: {types: [closed]}` events are only acted upon when the closed
  issue's body carries `<!-- wing-commander-auto-update-spec-kit:
  candidate=X.Y.Z observed=N -->` (specs/027's existing marker) — an
  unrelated closed issue is always a no-op, same rule specs/027's contract
  already states for `pull_request`/`issue_comment` events.
- The scheduled backstop sweep only ever touches repositories whose name
  matches the `wing-commander-e2e-<digits>` pattern exactly — never a
  broader glob that could catch an unrelated repository a maintainer
  happens to have named similarly.

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- No permanent scratch repository — every scratch repository is per-run,
  named per lifecycle issue, and eventually deleted (spec.md Assumptions:
  "No permanent `wing-commander-end-to-end-test` repository is created").
- No second outcome path for a missing-artifact failure — the FR-008 hint
  is narration text inside the same single `failure-detail` string, never a
  separate label, comment kind, or routing branch (FR-006/FR-009).
- The e2e-stage's own generated content is never merged, committed to this
  repository, or otherwise treated as real pipeline output — it exists
  solely inside the disposable scratch repository.
