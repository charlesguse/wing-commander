# Quickstart: Validating the `stage:clarify` Label Wiring

This feature has no user-facing UI or CLI — validation means driving the
shipped GitHub Actions steps and the new gate against modelled inputs, the
same way this repository already validates every stage-label flip and
every `verify-*.py` gate (no adopter-facing manual steps beyond what
`docs/setup.md` already documents).

## Prerequisites

- Python 3, `bash`, `git`, `jq`, `gh` on `PATH` (already required by every
  existing `verify-*.py` gate script in this repository).
- No live GitHub API access needed for gates 1-3 below — every scenario is
  modelled locally, matching `wc_shell_harness.py`'s convention (a stubbed
  `gh` on `PATH`).

## 1. Prove Gate 105 catches the exact regression this feature fixes

```bash
python3 .github/scripts/verify-lifecycle-label-taxonomy.py --self-test
```

Expected: PASS on every fixture in contracts/lifecycle-label-taxonomy-
gate.md's required-fixture table, including the pre-change-shaped fixture
(a documented `stage:clarify` with zero apply sites and zero waiver) FAILing
and naming `stage:clarify` — the FR-008 demonstration, permanently pinned
so it cannot silently stop being caught.

```bash
python3 .github/scripts/verify-lifecycle-label-taxonomy.py
```

Expected: PASS against the real, post-change tree — every documented
`stage:*` label (`docs/setup.md`) has a real apply site.

## 2. Prove the pre-change tree actually fails Gate 105 (FR-008's live demonstration)

```bash
git stash push -- .github/workflows/intake.yml .github/workflows/clarify.yml
python3 .github/scripts/verify-lifecycle-label-taxonomy.py
# Expected: FAIL, naming stage:clarify.
git stash pop
```

Record this output in the implementation PR per FR-008 — a gate that cannot
fail its own subject does not satisfy FR-007 (constitution VIII).

## 3. Drive the new `Flip stage label for clarification` step against a stubbed `gh`

Using `wc_shell_harness.py`'s existing `find_step`/stubbed-`gh` pattern
(the same one `verify-clarification-gating.py` already uses to extract and
run these two stages' named steps):

1. Extract `intake.yml`'s `Flip stage label for clarification` step via
   `find_step`. Run it with `NEEDED=true`, a stubbed `gh` recording every
   invocation. Assert: exactly one `gh label create stage:clarify ...
   --force`, one `gh issue edit --add-label stage:clarify`, one
   `gh issue edit --remove-label stage:spec`.
2. Repeat with `NEEDED=false`, `SPECIFIED=true`, `BLOCKED=false`,
   `SPEC_DIR` non-empty. Assert: exactly one `gh issue edit --remove-label
   stage:clarify`, no `stage:clarify` add, no `stage:spec` add.
3. Repeat with the stubbed `gh issue edit --add-label stage:clarify` forced
   to fail (non-zero exit). Assert: the step itself does not fail (exit 0),
   and `$GITHUB_STEP_SUMMARY` contains the `::warning::` line — FR-015's
   "MUST NOT... fail a run" property, proven rather than asserted.
4. Repeat all three for `clarify.yml`'s step, substituting `OUTCOME=needs-
   clarification` / `OUTCOME=ready` (with `BLOCKED=false`) / `OUTCOME=ready`
   with `BLOCKED=true` (assert: no label calls at all) / `OUTCOME=none`
   (assert: no label calls at all).
5. Confirm `verify-clarification-gating.py` (Gate 8) still passes unchanged
   after the new step is added — it does not reference the new step's name,
   so it must neither gain nor lose a finding (research.md D1).

## 4. Drive the amended E2E clarification-label assertion against modelled comment histories

Using a synthetic `comments_json` fixture (matching `auto-release-e2e-
clarify-decision.sh`'s existing test convention):

1. A comment history containing at least one rendered questionnaire
   (`## Question N`) followed by a qualifying reply, and a synthetic
   `timeline` that includes `stage:clarify`. Assert: `questionnaire_posted=
   true`, the loop passes, and the step summary contains the "asserting
   stage:clarify" line.
2. The same comment history, but `timeline` omits `stage:clarify`. Assert:
   `write_verdict fail-wrong-output` naming `stage:clarify` — the case this
   feature is built to catch on a real regression.
3. A comment history with no questionnaire at all (a zero-question spec).
   Assert: `questionnaire_posted=false`, the loop does not require
   `stage:clarify`, and the step summary contains the "skipped" line — the
   impossible-pass regression `auto-release.yml:1143-1147`'s original
   comment recorded must not reproduce.
4. Confirm Gate 66 ("the two e2e gate-decision scripts cover every
   documented branch") still passes unchanged — this feature adds no new
   mode to `auto-release-e2e-clarify-decision.sh`.

## 5. Manual / integration confirmation (documented, not automated by this feature)

This repository's own scratch-repository E2E run (`auto-release.yml`,
`specs/055-unattended-e2e-gates/`) is the only mechanism that proves
clarify-stage behavior in Actions (spec.md Assumptions — this feature adds
no new harness). Recommended before merge:

1. Re-drive one full E2E run (`gh workflow run` on `auto-release.yml`'s
   dispatchable wrapper) after this feature merges. Confirm the scratch
   lifecycle issue's label timeline shows `stage:clarify` applied and later
   removed, `stage:spec` reapplied, and the amended clarification-label
   assertion reports "asserted" (not "skipped") in its step summary —
   recorded on the implementation PR or the lifecycle issue per this
   repository's "prove" step for Actions-only behavior.
2. Confirm `wing-commander-2-clarify.yml`'s trigger fires on a reply while
   the issue carries `stage:clarify` alone (User Story 2, Acceptance
   Scenario 1) — observable in the same E2E run's clarify-stage dispatch.
