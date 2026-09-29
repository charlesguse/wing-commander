# Quickstart: Validating the Agent's Own Push Credential Fix

This feature has no user-facing UI — validation means driving the shipped
GitHub Actions structure and the two gates against modelled cases, plus
one recommended live drill, matching this repository's existing
convention for CI-only features (specs/038, specs/041, specs/052).

**Superseded 2026-09-29** (tasks.md T057, Maintainer Feedback): the
originally shipped mechanism — a `git credential.helper` minting a fresh
App installation token on demand (`wing-commander-agent-push-credential`,
`mint-credential.sh`) — was deleted as a security defect before merge (it
staged the App's own private key where a running agent step could reach
it). The remedy that actually shipped accepts that an agent's own
mid-cycle pushes may still fail past the credential lifetime and
guarantees only that every commit the agent creates reaches the spec
branch via a deterministic post-agent step
(`wing-commander-publish-stranded-commits`), authenticated with a
credential the agent never saw. Every section below describes that
shipped remedy, not the deleted one.

## Prerequisites

- Python 3, `bash`, `git`, `jq` (PyYAML) on `PATH` — the same set every
  existing `verify-*.py` gate already requires. No new tool dependency:
  the shipped remedy's only new shell (`wing-commander-publish-stranded-
  commits/action.yml`) is plain `git`, and neither `curl` nor `openssl`
  is invoked anywhere this feature added.
- No live GitHub API access needed for either gate check itself (Gate 122
  is static YAML inspection; Gate 123 drives a real local git repository,
  no network calls).

## 1. Run the full PR-time gate suite (per CLAUDE.md)

```bash
python .github/scripts/run-local-gates.py
```

Expected: all gates pass, including Gate 122 and Gate 123. Both were
renumbered more than once as other specs landed first on the numbers this
branch provisionally claimed (see contracts/agent-push-credential-gate.md
for the full history); Gate 123 was retired once, when its original
subject (`mint-credential.sh`) was deleted, then reused for a new,
unrelated behavioural check (T070) rather than left reserved.

## 2. Prove Gate 122 catches every structural care point FR-020/FR-023 name

```bash
python3 .github/scripts/verify-agent-push-credential-helper.py --self-test
```

Expected: PASS on the clean tree; PASS (meaning: correctly fails) on
every mutation `verify-agent-push-credential-helper.py`'s own self-test
applies — the App private key handed to an untrusted consumer (at step,
job, or workflow level, including bracket-syntax secret references and
staging outside the 8 named SUBJECTS files), a missing stranded-commit-
publish call, a duplicated JWT-signing shell anywhere in the repository,
the retry-bound prompt paragraph attached to a non-push-capable step, and
the two unreachable-subject cases.

## 3. Prove Gate 123 drives the stranded-commit-publish count against a real repository

```bash
python3 .github/scripts/verify-stranded-commit-publish-shell.py --self-test
```

Expected: PASS on all three scenarios (everything already pushed directly
by the agent, two commits stranded locally, no remote-tracking ref to
compare against) driven against a real bare `origin` plus a clone; PASS
(meaning: correctly fails) on the self-test mutation that reverts the
origin-ref comparison to `before-sha..HEAD` unconditionally, which must
break the "everything already pushed" scenario.

## 4. Confirm the step-gating and container-shell changes pass a second review

Per CLAUDE.md: any change touching `if:`, `continue-on-error:`, or a
`run:` step inside a job carrying a `container:` block gets a pass from
the `review-step-gating` and `container-shell-safety` skills before
merging. This feature adds one or more `wing-commander-publish-stranded-
commits` call sites to each of the 8 in-scope stages, including two inside
`implement.yml`'s `container:`-bearing job (`cycle` and `retry`) — run
both skills over the diff before opening the PR.

## 5. Confirm the retry-bound prompt paragraph's presence and wording

```bash
grep -A4 "is a credential problem this pipeline is already handling" .github/workflows/clarify.yml
```

Expected: the canonical paragraph (research.md D7, minus the mint-failure
clause the T057 redesign made moot) is present verbatim, and every other
in-scope stage's `prompt:` block either quotes it verbatim or is checked
by Gate 47 (`verify-comment-canonical-pointers.py`) to point at
`clarify.yml`'s copy, per CLAUDE.md's single-home rule as applied to
prompt prose.

## 6. Manual / integration confirmation (documented, not automated by this feature)

A live drill proving the actual defect (a push made after the credential's
one-hour lifetime) is fixed cannot be produced by a fast unit-style test —
it requires a real agent step to run past that lifetime. Recommended
before first release, reusing this repository's on-demand e2e scratch
provisioning (specs/053):

1. Dispatch one stage (e.g. `clarify`, cheaper than `implement`) with an
   artificially inflated turn budget forcing a run past 60 minutes wall
   clock, in a scratch adopter repository.
2. Confirm the agent's transcript shows no more than two further retries
   of a failing push once it meets the credential-expiry signature (User
   Story 2, SC-004), and that it commits its work locally and continues
   rather than spending further turns on a push that cannot succeed.
3. Confirm every commit the agent created — whether or not its own push
   of it succeeded — reaches the spec branch before the job ends: the
   "Publish stranded commits (post-agent)" step's own `commits-published`
   output is nonzero and its `push-ok` output is `true` when the agent
   met the credential-expiry signature; both are absent/zero when the
   agent finished well inside the hour (User Story 1, Acceptance
   Scenarios 1 and 2; SC-001, SC-002).
4. Confirm behaviour for a cycle that finishes well inside the hour is
   byte-for-byte unchanged from a `main`-built run of the same stage
   (User Story 1, Acceptance Scenario 2; SC-002).
5. In `implement.yml` specifically, force a cycle to end with local,
   unpushed commits and no retry agent scheduled (a healthy-but-truncated
   cycle); confirm the stranded-commit publish step still moves those
   commits to the branch before the job ends (User Story 4, Acceptance
   Scenario 1).
6. If the test harness can simulate the publish step's own mint failing
   or being throttled (e.g. by revoking the test App installation
   immediately before that step runs), confirm the run's own reporting
   attributes the failure to the publish step rather than to the agent or
   a "stage never started" diagnosis (FR-006) — a scenario distinct from
   step 2 above, since the publish step's mint and the agent's own
   mid-cycle pushes are now independent failure points.
7. Record the run URL as this feature's proof-after-merge, per CLAUDE.md's
   "a fix to behaviour that only runs in Actions is proven after merge by
   re-driving one run" rule.
