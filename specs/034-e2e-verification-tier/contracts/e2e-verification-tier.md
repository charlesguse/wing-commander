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
    scratch-branch: ${{ steps.scratch-repo.outputs.branch }}
  steps:
    # 1. Wing Commander context (bot token) — same pattern every job uses.
    # 2. RESOLVE (never create) the scratch repository: inputs.e2e-scratch-repo
    #    must be non-empty and visible to `gh repo view`, else the step fails
    #    with a reason naming the variable to set or the App installation to
    #    add. Branch for this run:
    #    "auto-update-spec-kit/e2e-${{ needs.prepare.outputs.issue-number }}".
    # 3. Clone it over an explicitly tokenised URL (this is a DIFFERENT
    #    repository from the one actions/checkout credentialed), reset the
    #    branch to an EMPTY tree (orphan + clear), then run the candidate's own
    #    `uvx --from git+https://github.com/github/spec-kit.git@v${CANDIDATE}
    #    specify init . --ai claude --script sh --ai-skills --here --force`
    #    (same command `prepare` already runs); commit and force-push it.
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
`vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL`),
`inputs.e2e-stage-max-turns` (default `20`) and `inputs.e2e-scratch-repo`
(default empty, sourced from
`vars.WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`) are new
`workflow_call` inputs on `auto-update-spec-kit.yml`, threaded from the
wrapper the same way `inputs.model` already is.

## Scratch-repository lifecycle — a maintainer's, not the pipeline's

This feature creates no repository and deletes none, so there is no
`issues: [closed]` trigger, no `issue-closed` job, and no scheduled reaping
sweep. Two facts forced that (spec.md Assumptions):

- `POST /user/repos` — the endpoint `gh repo create OWNER/NAME` reaches for a
  **user**-owned account, which `charlesguse` is — is documented for OAuth and
  classic-PAT scopes only. A GitHub App installation token, which every job
  here runs under, has no documented way to call it.
- `gh repo delete` needs `Administration: write`. That grant is not
  per-call-site: the same App token could delete **this** repository, at all
  fourteen of the pipeline's agent steps. Gate 12 (lint-workflows.yml) fails
  closed on both call sites for exactly this reason.

Per-run isolation is therefore the **branch**, not the repository:

1. `auto-update-spec-kit/e2e-<lifecycle-issue-number>` — deterministic from
   the issue number, so no name-to-issue mapping is stored anywhere.
2. Reset to an empty tree before every scaffold and force-pushed, so nothing
   a previous cycle (or the repository's own README) left behind can satisfy
   the read-back's non-empty-`spec.md` assertion.
3. Left in place afterwards. It is the maintainer's inspection surface, and
   the next run for the same issue overwrites it.

Permissions used: `Contents: read and write` on the scratch repository (the
App must be installed on it) — already in the App's documented grant, so
`docs/setup.md`'s permission list is unchanged by this feature.

## Self-recognition contract (extends specs/027's)

- Branch names this feature writes match
  `auto-update-spec-kit/e2e-<digits>` exactly, inside the one configured
  scratch repository — it never force-pushes a branch it did not derive from
  its own lifecycle issue number, and never touches any other repository.

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- No repository creation or deletion of any kind, and no repository-
  administration permission on the App — see the lifecycle section above.
- No second outcome path for a missing-artifact failure — the FR-008 hint
  is narration text inside the same single `failure-detail` string, never a
  separate label, comment kind, or routing branch (FR-006/FR-009).
- The e2e-stage's own generated content is never merged, committed to this
  repository, or otherwise treated as real pipeline output — it exists
  solely on the scratch repository's per-run branch.
