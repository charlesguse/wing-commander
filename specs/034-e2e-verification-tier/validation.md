# Validation record: End-to-End Verification Tier That Actually Verifies the Candidate

This file captures the Polish-phase validation (tasks.md T035/T036) so the
finalize stage can lift it into the feature PR body and the transmittal
comment on lifecycle issue #184. It is authored by the implement stage,
which opens no PRs and posts no issue comments itself — the same precedent
`specs/027-auto-update-spec-kit/validation.md` set for that feature's
T032/T033.

## T035 — full harness run

**Status: NOT RUN in the implement environment — needs a maintainer (or CI)
to execute it.**

`bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh` was attempted
and refused by this headless run's command allowlist (both `bash <script>`
and the direct `./run-tests.sh` form), which permits only the validators
`actionlint`, `yamllint`, `shellcheck`, and `jq`. This is an environment
limitation, not a harness or workflow defect: the suite is executed by
`lint-workflows.yml` in CI, so the feature PR's own checks are the first
place the full run happens.

What *was* verified statically in place of the run:

| Check | Method | Result |
|---|---|---|
| Every step-name glob `t4_verify.sh` extracts resolves to a real step | Step-name inventory of `auto-update-spec-kit.yml` vs. the six `run_step` patterns (`verify__*end-to-end*`, `verify__*combine*`, `e2e-stage__*create-or-reuse-the-scratch-repository*`, `e2e-stage__*read-back-stage-result*`, `issue-closed__*delete-the-scratch-repository*`, `reap-scratch-repos__*sweep-orphaned-scratch-repositories*`) | ✅ all six present |
| The two `grep -c` single-outcome-path assertions (T019) count exactly 1 | `Comment verification failure on the issue` appears once; `Apply the failed label$` (anchored, so the `(prepare failed)` variant is excluded) appears once | ✅ both 1 |
| The read-back step's `find e2e-scratch/specs -mindepth 2 -maxdepth 2 -name spec.md` matches the fixture layout the suite builds (`e2e-scratch/specs/001-throwaway/spec.md`) | Depth arithmetic against the fixture | ✅ matches |
| Harness shell hygiene | `shellcheck t4_verify.sh run-tests.sh lib.sh` | ✅ no new findings — remaining output is pre-existing `SC2012`/`SC2016`/`SC2034`/`SC2148`/`SC2164` style info in `lib.sh`/`run-tests.sh` and the repo-wide `GHA_SUBST` idiom (consumed by `lib.sh`'s `run_step`, so `SC2034` is a false positive) |
| Workflow YAML + embedded `run:` shell | `actionlint` on both workflow files (T034, prior commit) | ✅ clean apart from the repo-wide pre-existing `property "job_workflow_sha" is not defined` |

## T036 — decisions made without clarification, needing maintainer confirmation

Surfaced here (rather than silently assumed) for a maintainer to confirm
**before the first real minor/major candidate reaches this tier**:

1. **`e2e-stage-max-turns` defaults to `20` — an estimate.** research.md
   flags the number as unverified: nobody has measured how many turns one
   `create-new-feature.sh` + write-a-short-spec.md turn actually consumes
   against a real candidate. It is exposed as
   `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MAX_TURNS` so it can be
   raised without a code change. If the cap is too low the stage exhausts
   its turns, `steps.decide.outcome != 'success'`, and the read-back reports
   *"the e2e-stage agent step did not complete … this is a stage/
   infrastructure problem, not a candidate defect"* — deliberately worded
   (FR-021) so this failure mode is distinguishable from a broken candidate
   rather than being misread as one.

2. **`e2e-stage-model` tiering — `claude-sonnet-5`, not `claude-opus-5` —
   was decided without clarification.** research.md's reasoning: constitution
   II reserves `claude-opus-5` for specification and clarification because
   "the spec is the foundation every later stage builds on", and this stage's
   spec is a throwaway smoke-test artifact that is never read by a human and
   never merged. A maintainer who reads constitution II literally (any
   spec-producing stage gets opus) should override via
   `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_STAGE_MODEL`.

3. **The scheduled job's App installation needs a repository create/delete
   grant it does not have today — this is a hard blocker for the three new
   jobs, and a workflow `permissions:` block cannot supply it.** spec.md's
   own Assumptions already state the tier "needs repository create and delete
   rights — a broader grant than the alternatives". `permissions:` can only
   narrow the token an installation already has; repository administration is
   an *installation-level* permission granted out-of-band on the GitHub App.
   Until a maintainer grants it, `e2e-stage`'s "Create or reuse the scratch
   repository" step, the `issue-closed` deletion, and the
   `reap-scratch-repos` sweep will all fail (or silently no-op, in the
   `|| true` deletion paths) against real GitHub. The harness is unaffected —
   every `gh repo create`/`delete`/`list` in the test suite goes through
   `gh_stub.py`'s JSON state file, never a real API call.

## Determinism note (T029, SC-010, FR-020)

Recorded here as well as in `t4_verify.sh`'s header comment: the suite is
deterministic across repeated runs. The AI-driven stage's non-determinism is
fully contained — `t4_verify.sh` never invokes `claude-code-action`; it drives
the deterministic read-back step with a plain `DECIDE_OUTCOME` env var, exactly
as the pre-existing suites drive `evaluate-path`'s own `decide` step. No
scenario added by T002/T008/T023/T024/T026 shells out to a real
`gh repo create`/`delete`/`list`.
