# Quickstart: Validating Watchdog Precision & Determinism Hardening

Prerequisites: a repo checkout with `gh` authenticated as a maintainer,
one or more scratch specifications with runs to inspect, and at least
one pre-existing pipeline-defect issue to exercise dedup/relabeling
scenarios against. This quickstart amends
`specs/015-pipeline-watchdog/quickstart.md`: Scenarios 5–7 there (rung 1
auto-fix, rung-1-boundary fallback, pause switch) are **retired** — there
is no rung 1/2 left to exercise. Scenarios 1–4, 8–14 there still apply
unchanged (detection, clean-run, missing-evidence, self-dispatch cap,
self-inspection, dedup open/closed, concurrency, coexistence, untrusted
content) and are not repeated here. The scenarios below exercise only
what this feature adds or changes.

## Scenario A — Attribution invariant suppresses a signal from a collector that lacked the guard before (US2, SC-003)

1. Trigger a run that is `skipped` or `cancelled` before reaching the
   step that would produce a denied-tool pattern, a step summary
   sentinel, or an annotation (pick whichever of the three
   newly-guarded collectors is easiest to reproduce in a scratch run).
2. Wait for the watchdog to inspect that run.
3. Expected: no finding of that class is reported — `gh issue view
   <lifecycle-issue> --json comments` shows either "passed inspection" or
   a report that omits the condition entirely, never a finding
   attributing a condition to a run that never reached it. Confirm via
   `signals.json` (job logs) that the collector emitted no entry for the
   skipped/cancelled run.

## Scenario B — Evidence-validity gate suppresses a finding with empty cited facts (US4, SC-005)

1. Reproduce (or synthesize, via `workflow_dispatch` against a crafted
   `signals.json`-shaped fixture if the harness supports it) a
   `denied-tool` finding whose `normalizedFacts.tool` is null or empty —
   the exact shape every historical `denied-tool` false positive
   carried.
2. Let the watchdog process it through `triage`.
3. Expected: the finding is suppressed before fingerprinting — the
   lifecycle issue reports "suppressed: invalid evidence," and `gh issue
   list --label pipeline-defect --state all` shows no new issue was
   created for it.

## Scenario C — Deterministic fingerprint: inspecting the same defect twice yields byte-identical fingerprints (US3, SC-004)

1. Reproduce the same genuine finding (e.g. Scenario 1 of the 015
   quickstart — a real denied-tool pattern) from two different scratch
   runs.
2. Capture each run's computed fingerprint from the `triage` job's step
   logs (`Compute fingerprint`).
3. Expected: the two fingerprints are byte-identical strings, and the
   second finding's dedup lookup resolves to `match-open` against the
   first's issue — confirm via `gh issue view <N> --json comments`
   showing exactly one issue with two comments, never two issues.

## Scenario D — Dedup lookup failure suppresses filing instead of creating a duplicate (US7, SC-010)

1. Temporarily break the dedup lookup's `gh issue list` call for a test
   run — e.g. dispatch against a `run-id` while `GH_TOKEN` scope is
   deliberately insufficient for issue reads, or any other reproducible
   way to force the `gh issue list --label pipeline-defect --label
   "🐕 · <class>"` call to exit non-zero.
2. Feed the watchdog a genuine, previously-unseen finding under that
   condition.
3. Expected: `outcome=unknown`; no pipeline-defect issue is created; the
   lifecycle issue reports "dedup lookup failed — finding suppressed,
   needs manual check." Confirm `gh issue list --label pipeline-defect
   --state all` shows no new issue.
4. Restore normal `gh` access and re-run the same finding. Expected:
   `outcome=none`, a new pipeline-defect issue is created normally —
   confirming the fix only changes the *failure* path, not the working
   path.

## Scenario E — Precision criterion is computable and reports not-applicable before 10 findings exist (US1, SC-001, SC-008)

1. On a fresh checkout (or a scratch repo with fewer than 10 historical
   pipeline-defect issues), run: `gh issue list --label pipeline-defect
   --state all --json number,labels,createdAt`.
2. Expected: fewer than 10 results ⇒ per FR-001/the data-model's
   Precision criterion entity, a maintainer computing the criterion by
   hand reports "not applicable," not a 0% or 100% figure.
3. Label at least 10 distinct pipeline-defect issues
   `disposition:confirmed` or `disposition:false-positive` (using the
   five known historical false positives — #102, #104, #105, #112, #125 —
   as seed data per SC-002, plus enough confirmed-genuine issues to reach
   10).
4. Re-run the query, restricted to the most recent 20:
   `gh issue list --label pipeline-defect --state all --limit 20 --json
   number,labels`. Expected: numerator = count with
   `disposition:confirmed`, denominator = 20 (or however many exist
   between 10 and 20), and the fraction is directly computable without
   ambiguity (SC-001).

## Scenario F — No rung machinery remains (US6/FR-014, SC-009)

1. Reproduce any finding that, under spec 015's original rules, would
   have qualified for rung 1 (e.g. a minor allowlist-grant-shaped denied-
   tool fix).
2. Expected: the watchdog files (or comments on) a pipeline-defect issue
   only — no PR is opened at any point, `.specify/memory/
   watchdog-guardrails.json` does not exist in the checkout, and `gh run
   view` for the watchdog's own `triage`/`act` jobs shows no
   propose-fix/rung-gate/commit-and-open-PR steps in the step list.
3. Confirm `lint-workflows.yml` passes with Gate 17 absent from its gate
   registry (not skipped — removed) and that
   `.github/scripts/verify-watchdog-fix-commit.py` no longer exists.

## Scenario G — Self-inspection requirement text matches shipped behavior (US5, SC-006)

1. Read the amended FR-021 (formerly forbidding any special-case path,
   now requiring "unexempted, never skipped or softened") in
   `specs/015-pipeline-watchdog/spec.md`.
2. Trigger `wing-commander-8b-watchdog-self.yml` against a stage-8 run
   that exhibits a detectable problem (reproducing 015 quickstart's
   Scenario 9's setup).
3. Expected: the deterministic self-checker inspects it, exactly as
   before this feature — no behavior changes; the check is that the
   requirement text a reviewer reads next to this run no longer
   contradicts what actually happens.

## Scenario H — Deterministic-judgment principle is citable (US6, SC-007)

1. Read `.specify/memory/constitution.md`'s new Principle IX.
2. Confirm it names, by number, that gating judgment (a filed finding, a
   fingerprint, a dedup outcome, an autonomous write) belongs in
   deterministic code — and that a reviewer could cite "Principle IX"
   against a hypothetical future PR that, say, asks the `diagnose` prompt
   to decide fingerprint uniqueness itself instead of using the
   deterministic step.

## Scenario I — Stale spec directory is gone (FR-017, SC-008)

1. `ls specs/023-reliable-diagnose-verdict/` on the branch this feature
   ships from.
2. Expected: does not exist. `git log --all --oneline -- specs/
   023-reliable-diagnose-verdict/` still shows its history — nothing was
   force-deleted from git, only removed from the working tree going
   forward.

See `contracts/watchdog-spec-amendments-delta.md` for the exact
job-contract deltas each scenario above exercises, and
`specs/015-pipeline-watchdog/contracts/watchdog-workflow.md` plus this
feature's `data-model.md` for the full, current contract each scenario
is checked against.
