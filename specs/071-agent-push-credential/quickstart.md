# Quickstart: Validating the Agent's Own Push Credential Fix

This feature has no user-facing UI — validation means driving the shipped
GitHub Actions structure and the two new gates against modelled cases,
plus one recommended live drill, matching this repository's existing
convention for CI-only features (specs/038, specs/041, specs/052).

## Prerequisites

- Python 3, `bash`, `git`, `curl`, `jq`, `openssl`, `yaml` (PyYAML) on
  `PATH`. `openssl` is the one new dependency this feature adds beyond
  what every existing `verify-*.py` gate already requires — confirm it is
  present on every runner/container image this pipeline's 8 in-scope
  stages target before relying on the credential helper in production
  (research.md D2 explicitly declines to assume this silently).
- No live GitHub API access needed for either gate check itself (Gate 99
  is static YAML inspection; Gate 100 stubs `curl`, per its own contract).

## 1. Run the full PR-time gate suite (per CLAUDE.md)

```bash
python .github/scripts/run-local-gates.py
```

Expected: all gates pass, including the new Gate 99 and Gate 100
(provisional numbers — see contracts/agent-push-credential-gate.md),
once implemented.

## 2. Prove Gate 99 catches every structural care point FR-020/FR-023 name

```bash
python3 .github/scripts/verify-agent-push-credential-helper.py --self-test
```

Expected: PASS on the clean tree; PASS (meaning: correctly fails) on each
of the six mutations in contracts/agent-push-credential-gate.md's table —
a missing credential-helper install, a missing stranded-commit-publish
call, a duplicated minting shell outside its one composite, a credential-
helper call wrongly attached to a non-pushing agent step, and the two
unreachable-subject cases.

## 3. Prove Gate 100 exercises `mint-credential.sh` itself, not just its presence

```bash
python3 .github/scripts/verify-agent-push-credential-shell.py --self-test
```

Expected: PASS on the success path (a stubbed 2xx installation lookup and
token mint produce the exact `username=`/`password=` pair a git
credential helper contract requires); PASS (meaning: correctly fails, i.e.
recognises the expected failure shape) on the stubbed 401 mint and the
unreadable-key-file cases, asserting the `mint failed: <reason>` stderr
signature research.md D6 depends on.

## 4. Confirm the step-gating and container-shell changes pass a second review

Per CLAUDE.md: any change touching `if:`, `continue-on-error:`, or a
`run:` step inside a job carrying a `container:` block gets a pass from
the `review-step-gating` and `container-shell-safety` skills before
merging. This feature adds 16 new call sites across the two composites
(2 per in-scope stage × 8, three of them inside `implement.yml`'s
`container:`-bearing job) — run both skills over the diff before opening
the PR.

## 5. Drive the credential helper's shell directly against a real (throwaway) App installation, no live agent needed

Using `wc_shell_harness.py`'s existing `run_step`/stubbed-environment
pattern:

1. Extract `wing-commander-agent-push-credential`'s setup step and run it
   inside a scratch git checkout with a stale
   `http.https://github.com/.extraheader` entry already present; assert
   that entry is gone afterward and `git config credential.https://
   github.com.helper` names `mint-credential.sh`'s absolute path.
2. With a real (but disposable, scoped-down) App installation's ID/key
   available in a test environment, invoke `mint-credential.sh get`
   directly with a `protocol=https\nhost=github.com\n` stdin payload;
   assert the emitted token, when used immediately with `curl -H
   "Authorization: token <it>" https://api.github.com/repos/<owner>/
   <repo>`, succeeds — proving the mint is not just well-formed but
   actually authenticates (research.md D2's claim, not just its shape).
3. Re-run step 2 a second time in the same shell session; assert the
   installation-id cache file from research.md D3 exists and that the
   second run makes one fewer HTTP call than the first (observable via a
   request-count wrapper around `curl`).

## 6. Confirm the retry-bound prompt paragraph's presence and wording

```bash
grep -A5 "mint failed:" .github/workflows/clarify.yml
```

Expected: the canonical paragraph (research.md D7) is present verbatim,
and every other in-scope stage's `prompt:` block either quotes it
verbatim or is checked by Gate 47
(`verify-comment-canonical-pointers.py`) to point at `clarify.yml`'s copy,
per CLAUDE.md's single-home rule as applied to prompt prose.

## 7. Manual / integration confirmation (documented, not automated by this feature)

A live drill proving the actual defect (a push made after the credential's
one-hour lifetime) is fixed cannot be produced by a fast unit-style test —
it requires a real agent step to run past that lifetime. Recommended
before first release, reusing this repository's on-demand e2e scratch
provisioning (specs/053):

1. Dispatch one stage (e.g. `clarify`, cheaper than `implement`) with an
   artificially inflated turn budget forcing a run past 60 minutes wall
   clock, in a scratch adopter repository.
2. Confirm every `git push` the agent makes succeeds — no `remote: Invalid
   username or token` / `Authentication failed` line anywhere in the
   agent step's own transcript — including at least one push issued after
   the 60-minute mark (User Story 1, Acceptance Scenario 1).
3. Confirm behaviour for a cycle that finishes well inside the hour is
   byte-for-byte unchanged from a `main`-built run of the same stage (User
   Story 1, Acceptance Scenario 2; SC-002).
4. Re-drive the same scenario with the App private key deliberately
   invalidated mid-run (if the test harness can simulate a mint failure —
   e.g. by revoking the test App installation) and confirm: the agent's
   transcript shows at most two further retries of the failing push
   before it moves on (User Story 2, SC-004), and the run's own reporting
   attributes the failure to the credential rather than to the agent or a
   "stage never started" diagnosis (User Story 1, Acceptance Scenario 4;
   FR-006).
5. In `implement.yml` specifically, force a cycle to end with local,
   unpushed commits and no retry agent scheduled (a healthy-but-truncated
   cycle with a simulated late-stage mint failure); confirm the stranded-
   commit publish step (research.md D8) still moves those commits to the
   branch before the job ends (User Story 4, Acceptance Scenario 1).
6. Record the run URL as this feature's proof-after-merge, per CLAUDE.md's
   "a fix to behaviour that only runs in Actions is proven after merge by
   re-driving one run" rule.
