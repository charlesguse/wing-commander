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
| Every step-name glob `t4_verify.sh` extracts resolves to a real step | Step-name inventory of `auto-update-spec-kit.yml` vs. the four `run_step` patterns (`verify__*end-to-end*`, `verify__*combine*`, `e2e-stage__*resolve-the-scratch-repository*`, `e2e-stage__*read-back-stage-result*`) | ✅ all four present, asserted by the suite itself (an ambiguous or unmatched glob is a harness FAIL) |
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

3. **~~The scheduled job's App installation needs a repository
   create/delete grant it does not have today~~ — RESOLVED by removing the
   need, not by widening the grant.** The original design had `e2e-stage`
   create a per-run scratch repository and two other jobs delete it. Two
   things killed that:

   - `gh repo create OWNER/NAME` against a **user** account (which
     `charlesguse` is) goes through `POST /user/repos`, documented for OAuth
     and classic-PAT scopes only. A GitHub App installation token — what every
     job here runs under — has no documented way to call it, so the very first
     real minor/major candidate would have failed there. This was not a
     "grant it and it works" blocker; it was unimplementable as specified.
   - `gh repo delete` needs `Administration: write`, which is not scoped to a
     call site: the same token could delete **this** repository from any of the
     pipeline's agent steps. Gate 12 (`lint-workflows.yml`) failed the PR on
     all five `gh repo create`/`delete`/`list`/`clone` call sites for exactly
     this reason, and widening `docs/setup.md`'s App permission list to satisfy
     it would have traded a standing risk for a convenience.

   The scratch repository is now **pre-created by a maintainer** and named in
   `WING_COMMANDER_AUTO_UPDATE_SPEC_KIT_E2E_SCRATCH_REPO`; per-run isolation
   is the branch `auto-update-spec-kit/e2e-<issue>`, force-reset to an empty
   tree before each scaffold. The App needs only `Contents: read and write` on
   that repository — already in its documented grant, so `docs/setup.md`'s
   permission list is unchanged. What a maintainer must still confirm: the
   scratch repository exists and the App is installed on it, **before the
   first real minor/major candidate reaches this tier**. Unconfigured, the
   stage fails and the candidate is not adopted (FR-004) — loudly, naming the
   variable to set, rather than passing unverified.

## T037 — convergence: e2e-stage infra-failure narration gap (FR-021)

Fixed in cycle 3, and re-pointed at the pre-created scratch repository
afterwards: the "Resolve the scratch repository" step fails the step
(rather than silently continuing and unconditionally emitting `full-name`)
when the repository is unconfigured or not visible to the App token.
Separately — and this is the fix that actually closes the gap, since a failure in either that step or the following "Scaffold and
push" step still leaves `steps.readback.outputs.failure-detail` empty
(the read-back step never runs) — the `verify` job's "Combine verification
result" step now synthesizes `"the e2e-stage job did not complete (result:
$STAGE_RESULT) — this is a stage/infrastructure problem, not a candidate
defect."` whenever `STAGE_DETAIL` reaches it empty, instead of falling
through to a blank detail or the bare scratch-repo pointer.
`t4_verify.sh` gained a scenario driving `gh_stub.py`'s existing
`GH_STUB_FAIL` failure-injection (already generic across every `gh`
subcommand, including `repo view`) to confirm the step itself now fails,
and a `combine()` call confirming the composed detail states the stage did
not complete and never carries candidate-artifact wording (e.g. `spec.md`).
Re-linted with `actionlint`/`shellcheck` — no findings beyond the
pre-existing ones already noted below.

## Determinism note (T029, SC-010, FR-020)

Recorded here as well as in `t4_verify.sh`'s header comment: the suite is
deterministic across repeated runs. The AI-driven stage's non-determinism is
fully contained — `t4_verify.sh` never invokes `claude-code-action`; it drives
the deterministic read-back step with a plain `DECIDE_OUTCOME` env var, exactly
as the pre-existing suites drive `evaluate-path`'s own `decide` step. No
scenario added by T002/T008/T023/T024/T026 touches a real repository — and
two of them assert that the stage makes no `repo create`/`repo delete` call
at all.
