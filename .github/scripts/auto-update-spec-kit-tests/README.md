# auto-update-spec-kit behavioral tests

Executable coverage of `specs/027-auto-update-spec-kit/quickstart.md`'s
15 scenarios, plus the job-level `if:` routing that decides which scenario a
run actually takes.

## Why this exists rather than a desk-check

`quickstart.md` describes its scenarios as things a maintainer stages by hand
against a scratch environment (a deliberately broken candidate, a simulated
upstream release, a fork with a lowered pin). That is expensive enough that it
was never done, and the three defects these tests were written to reproduce
would all have fired on the stage's very first scheduled run:

1. `health-check`'s rollback lookup passed its revision *after* `--`, so
   `git log --follow` saw two pathspecs and exited
   `fatal: --follow requires exactly one pathspec`. A trailing `|| true`
   swallowed it, so a rollback target was never found and the revert PR that
   FR-006/FR-007 promise could never open.
2. The lightweight verification tier called `check-prerequisites.sh --json`
   without `--paths-only`, which hard-requires `plan.md` — a file
   `create-new-feature.sh` does not create. The tier could never pass, in
   `health-check` *or* `verify`.
3. The end-to-end tier prefixed an already-absolute `FEATURE_DIR` with
   `$WORKTREE`, so its `cp` always failed on the doubled path.

Defects 1 and 2 compound: `health-check` fails every scheduled run, the whole
detect/settle/evaluate chain skips, `act` takes the rollback branch, finds no
target, and files an `auto-update:failed` issue — daily, forever, while never
being able to adopt anything.

## Running them

```sh
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh          # all suites
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t2_settle # one suite
```

Requires `bash`, `git`, `jq`, and `python3` with PyYAML — all present on
`ubuntu-latest`. On Windows, Git Bash plus a `jq.exe` on `PATH` works; the
runner prints a download one-liner if `jq` is missing.

Nothing here touches the network, the real repository, or GitHub. Exit code is
non-zero if any assertion fails, so CI fails on a regression.

## How it works

The workflows keep all their logic in embedded `run:` blocks, so the tests
execute those blocks directly rather than re-implementing them:

- `extract.py` parses the two workflow YAMLs and writes every `run:` block to
  its own `.sh` under a scratch dir. The scripts under test are therefore
  always the shipped ones — this harness cannot drift from the workflow the
  way `verify-denied-tool-collector.sh` drifted from `watchdog.yml`.
- `subst.py` substitutes `${{ ... }}` expressions per scenario. Anything a
  scenario leaves unset renders as the empty string, which is what Actions
  does for a skipped job's outputs.
- `gh_stub.py` is a `gh` replacement backed by a JSON state file, with real
  issue/PR/label/comment semantics, so the settle state machine and the
  act/comment-reply branches genuinely mutate state and can be asserted on.
  It shells out to the real `jq` for `--jq` filters.
- `lib.sh` gives each step a real `$GITHUB_OUTPUT` / `$GITHUB_STEP_SUMMARY` /
  `$RUNNER_TEMP`, and `read_output.py` parses outputs the way the runner does,
  including the `<<HEREDOC` multiline form these workflows use.
- `t7_gating.py` reads the job-level `if:` expressions **verbatim from the
  YAML** and evaluates them against each scenario's job-result matrix. It
  never retypes an expression, so it cannot silently test a stale copy.

Suites:

| suite | covers |
|---|---|
| `t1_detect.sh` | Scenarios 1, 2, 7 — eligibility, semver ordering, prerelease exclusion, release-type classification, live upstream data |
| `t2_settle.sh` | Scenarios 2, 3, 4, 11, 12 — the settle state machine's six branches |
| `t3_healthcheck.sh` | Scenarios 6, 8 — lightweight tier against real `.specify` scripts, worktree isolation, rollback target from git history |
| `t4_verify.sh` | Scenarios 5, 6, 7 — tier selection and result combination; plus (specs/034) the deeper tier's per-script assertion chain (`spec.md`/`setup-plan.sh`/`setup-tasks.sh`) against real fixture worktrees, the e2e-stage read-back's completion-vs-shape distinction, the FR-008 missing-artifact narration hint, and the scratch repository being resolved rather than provisioned (configured / unconfigured / malformed `OWNER/NAME` / scratch-token mint failed or empty / not visible to the token, plus a direct assertion that no `repo create` or `repo delete` call is ever made) |
| `t5_act.sh` | Scenarios 5, 6, 8, 10 — revert PR, version-bump PR, failure flagging, against a real git remote whose `origin` is credential-less exactly as the runner's is |
| `t6_reply.sh` | Scenarios 9, 12, 13, 14, 15 — self-recognition, maintainer gate, fail-safe read-backs, prompt-injection safety |
| `t7_gating.py` | every scenario's job routing, plus the wrapper's pause kill-switch |
| `t8_scaffold.sh` | e2e-stage's scaffold step run repeatedly against one scratch repository — the branch is reset to a single orphan commit each time, whatever the scratch repository's default branch happens to be; plus the agent stage's project-root resolution, run against the real pinned scripts in a nested consumer/scratch layout |

## Mutation results

A suite that cannot fail is not a gate, so each assertion set was checked
against a deliberately broken workflow. Every mutant below is caught:

| mutant | caught by |
|---|---|
| rollback lookup's rev moved back after the `--` | `t3` (1) |
| `--paths-only` dropped from `check-prerequisites.sh` | `t3` (3) |
| absolute `FEATURE_DIR` re-prefixed with `$WORKTREE` | `t4` (2) |
| `settle` stops incrementing the observed counter | `t2` (2) |
| `act` merges its own PR (constitution V) | `t5` |
| pr-merged self-recognition guard always matches | `t6` (5) |
| maintainer gate widened to accept `NONE` | `t7` (1) |
| the deleted `else`/`printf` placeholder fallback reintroduced (specs/034 FR-004) | `t4` (2, source-inspection `check_not_contains`) |
| a per-script assertion silently skipped (e.g. `setup-tasks.sh`'s field-shape check dropped) | `t4` (3, wrong-shape mutants fail to fail) |
| the e2e-stage result reported but not folded into `combine`'s gating | `t4` (6, e2e-stage gating failure asserted against `combine`'s output) |
| repository provisioning reintroduced, or the `issue-closed`/`reap-scratch-repos` jobs brought back (specs/034 FR-023) | `t4` (7, zero-`repo create`/`repo delete` assertion) and `t7` (structural no-such-job assertions) |
| the scaffold's detach-and-delete dropped, so `--orphan` collides with the branch `git clone` checked out | `t8` (6, all on the second and third run — the first still passes, which is the whole point) |
| `SPECIFY_INIT_DIR` dropped from the agent step, so the stage verifies the consumer checkout instead of the scratch clone | `t8` (2 wiring assertions; the behavioural half asserts the unfixed resolution directly, so it holds either way) |
| the read-back's `\|\| true` dropped, so `find` on a missing directory aborts the step | `t4` (5 — the step stops reporting at all, taking the pre-existing S5 assertions with it) |
| either `act` push reverted to `git push origin`, which cannot authenticate under `persist-credentials: false` | `t5` (18, both step exit codes 128 — the production code) |

Two mutants deserve singling out, because they are about the harness rather
than the workflow — both are cases where the fixture was kinder than the
runner, so a real defect passed here and fired in production.

`t5` built its fixture with `git clone <path>`, which leaves an `origin` that
needs no credentials. The runner's `origin` needs them and does not have them:
every checkout in the workflow sets `persist-credentials: false`. So
`git push origin` passed here for as long as the suite existed and died with
exit 128 the first time `act` ever reached a push (run 31910291963) — the last
step of the last job, after five earlier blockers had kept anything from
getting that far. The fixture now points `origin` at a credential-less URL that
resolves to nothing and the App-token URL at the bare repo, so which URL
carries the push is what is actually under test.

`run_step` executed steps as `bash <file>` until the e2e-stage
read-back died in production at a `find` whose directory was missing — a case
`t4` Scenario 5 **already covered and passed**, because the runner uses
`bash -e {0}` and this harness did not. Restore `bash <file>` and reintroduce
that workflow defect and the suite goes green again (104/0 on `t4`), which is
the drift in miniature: assertions that cannot fail are not assertions. The
`-e` is therefore load-bearing, not tidiness.

Re-run one with, e.g.:

```sh
sed -i 's/--json --paths-only/--json/' .github/workflows/auto-update-spec-kit.yml
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t3_healthcheck   # must fail
git checkout .github/workflows/auto-update-spec-kit.yml
```

## Contract check on the pinned Spec Kit scripts

`t3_healthcheck.sh` copies this repository's **real** `.specify/scripts/bash/`
into its fixture, so it doubles as a contract check: if a future Spec Kit bump
changes what `create-new-feature.sh` or `check-prerequisites.sh` emit, this
suite fails on the PR that bumps it rather than at 07:13 UTC some morning.
That is exactly the class of breakage defect 2 was.
