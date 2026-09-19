# Quickstart: Validating Credential Lifetime Across Long Agent Cycles

This feature has no user-facing UI — validation means driving the shipped
GitHub Actions structure and the new gate against modelled cases, plus one
recommended live drill, matching this repository's existing convention for
CI-only features (specs/038, specs/041).

## Prerequisites

- Python 3, `bash`, `git`, `jq`, `gh`, `yaml` (PyYAML) on `PATH` — already
  required by every existing `verify-*.py` gate script in this repository.
- No live GitHub API access needed for the gate check itself (static YAML
  inspection over the checked-out tree).

## 1. Run the full PR-time gate suite (per CLAUDE.md)

```bash
python .github/scripts/run-local-gates.py
```

Expected: all gates pass, including the new Gate 67 (provisional numbering
— see contracts/post-agent-credential-refresh-gate.md), once implemented.

## 2. Prove Gate 67 catches every care point FR-020/FR-021 name

```bash
python3 .github/scripts/verify-post-agent-credential-refresh.py --self-test
```

Expected: PASS on the clean tree; PASS (meaning: correctly fails) on each
of the five required mutations in
contracts/post-agent-credential-refresh-gate.md's table — a stale
credential reference, a missing refresh before a second agent step, a
missing `continue-on-error: true` on a declared-observability step, and the
two unreachable-subject cases.

## 3. Confirm the observability tolerance and step-gating changes pass a second review

Per CLAUDE.md: any change touching `if:`, `continue-on-error:`, or a
failing step gets a pass from the `review-step-gating` skill before
merging. This feature touches `continue-on-error:` at 12 call sites
(data-model.md) and adds several new `if: always()` steps — run that skill
over the diff before opening the PR.

## 4. Drive the credential relay's shell directly (no live token needed)

Using `wc_shell_harness.py`'s existing `run_step`/stubbed-environment
pattern (already established for other composites' `run:` blocks in this
repository):

1. Extract `wing-commander-context`'s new relay step and run it with a
   fixed `TOKEN` value; assert `$GITHUB_ENV` gained exactly one
   `WC_BOT_TOKEN=<value>` line.
2. Run it a second time with a different `TOKEN` value inside the same
   simulated environment file; assert a step reading `env.WC_BOT_TOKEN`
   afterward observes the *second* value — this is the mechanism research.md
   D1 depends on (later `$GITHUB_ENV` writes win for subsequent steps), and
   it is the one Actions runner behaviour this feature is not otherwise
   able to unit-test without simulating the file format directly.
3. Extract the "Refresh authenticated spec-branch remote" step and run it
   inside a scratch git repository with an `origin` remote already
   configured with a stale credential in its URL; assert `git remote
   get-url origin` reflects the new token afterward and the working tree
   (an uncommitted file placed in the scratch repo before the step runs) is
   untouched — proving research.md D2's "cannot discard a commit or a
   staged change" claim, not just asserting it.

## 5. Confirm the stall-path wording change on a forced failure

Reusing `verify-implement-stall-notice-unchanged.py`'s existing harness
pattern (the pinned-steps gate this feature must not regress — research.md
notes the interaction explicitly): model a survivor job's "Determine which
dependency did not start" step with `needs.<entry-job>.outputs.agent-ran`
set to `'true'` and a `conclusion` of `failure`; assert the rendered reason
string names the post-agent step and does not contain the literal phrase
"the implement stage failed before it could run its own steps". Repeat with
`agent-ran` unset; assert the literal phrase is unchanged from today.

## 6. Manual / integration confirmation (documented, not automated by this feature)

A live drill proving the actual 401 defect is fixed cannot be produced by a
fast unit-style test — it requires a real agent step to run past the
credential's one-hour lifetime. Recommended before first release:

1. Dispatch one stage (e.g. `clarify`, cheaper than `implement`) with an
   artificially small effective credential lifetime or an artificially
   inflated turn budget forcing a run past 60 minutes wall clock, in a
   scratch adopter repository (per this repository's on-demand e2e scratch
   provisioning, specs/053).
2. Confirm every post-agent step in the run log succeeds (no `HTTP 401` in
   any step's log), the "Report over-budget agent run" step (if it fires)
   is shown tolerated (yellow, not red, in the Actions UI) rather than
   stranding steps below it, and the lifecycle issue receives an accurate
   comment.
3. Re-drive the same scenario with the App credential deliberately revoked
   mid-run (if the test harness can simulate a mint failure) and confirm
   the failure surfaces as a named credential failure, not a false "stage
   did not start" or a false agent-failure report (US1 Acceptance Scenario
   4).
4. Record the run URL as this feature's proof-after-merge, per CLAUDE.md's
   "a fix to behaviour that only runs in Actions is proven after merge by
   re-driving one run" rule.
