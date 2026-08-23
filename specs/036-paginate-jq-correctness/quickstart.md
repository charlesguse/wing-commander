# Quickstart: Validating the Pagination-Shape Fixes and Gate

Prerequisites: repository checkout on this feature's branch, `python3`,
`bash`, `jq`, and `gh` (a real `gh` binary is only needed for `--help`-level
sanity; every test below stubs `gh` for determinism — see
`.github/scripts/auto-update-spec-kit-tests/README.md`). All commands run
from the repository root.

## 1. The static gate detects the historical defect and its own health

```bash
python3 .github/scripts/verify-gate-18.py
```

Expected: every synthetic case passes as documented in
`contracts/pagination-shape-gate.md`'s fixture table — including the
mutation-style regression case where the shipped, already-fixed sites are
fed back through the detector and it stays green, proving the self-test
can tell a real fix from a still-broken one. A non-zero exit here means
Gate 18's detection logic itself is wrong; fix it before trusting any
other result in this quickstart.

## 2. The gate is clean against the repository as it stands after the fix

```bash
python3 .github/scripts/run-local-gates.py
```

This derives and runs every PR-time gate `lint-workflows.yml` invokes,
Gate 18 among them — both halves: the repository scan
(`verify-gate-18-scan.py`) and its self-test (`verify-gate-18.py`). No
separate registration is needed, because `wc_gate_registry.py` reads the
directory rather than a list.

> This was not true when this quickstart was written. The scan was then an
> inline `python3 - <<'PYEOF'` heredoc, which the file-based registry could
> not see, so `run-local-gates.py` reached only the self-test. #213 gave the
> scan a file; step 3 below could not fail until it did.

Expected: clean, once all three broken sites and the two accidentally-safe
sites are rewritten (spec's Acceptance Scenario 3 for User Story 3).

## 3. Reintroduce a broken shape and watch the gate catch it

```bash
git stash
```

Temporarily edit `.github/workflows/watchdog.yml`'s annotation collector
back to the pre-fix shape (`--paginate` with no `--jq`, plus the separate
`jq -c '[...]'` pass), then:

```bash
python3 .github/scripts/run-local-gates.py
```

Expected: Gate 18 fails, naming `watchdog.yml` and the offending line, and
its error text alone (per SC-006) is enough to write the correct form
back.

> Run against this repository before #213, this step reported **all green**
> on a deliberately broken tree — the only Gate 18 piece the runner could
> reach was the self-test, which passes on a broken repository by design
> because it tests the detector against its own fixtures rather than against
> the tree. A drill whose command cannot fail is worth less than no drill:
> performing it produces evidence of the wrong thing. If this step ever goes
> green again, suspect the wiring before the detector.

Restore the file:

```bash
git checkout -- .github/workflows/watchdog.yml
git stash pop
```

## 4. The auto-update sites are covered against a multi-page fixture

```bash
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t1_detect
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t10_notes
```

Expected: both suites pass, including the new >30-release scenarios
(research.md D4) that assert `detect` resolves exactly one, highest,
eligible version and `evaluate-path`'s "Fetch candidate release notes"
step assembles exactly the eligible releases between pinned and candidate
— from a fixture spanning more than one page. Run the full suite to
confirm nothing else regressed:

```bash
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh
```

## 5. The watchdog's annotation collector is covered against a multi-page fixture

```bash
python3 .github/scripts/verify-gate-19.py
```

Expected: every scenario in `research.md` D5 passes — all annotations
from every page reach `signals.json`, annotations from different jobs
don't displace each other, a job with no matching annotations leaves the
evidence set unchanged — and the mutation check at the end (reintroducing
the array-collecting `--jq '[...]'` shape) demonstrates the suite would
have failed before this feature's fix landed.

## 6. Behavior is unchanged for present-day, single-page data (FR-005/SC-007)

```bash
bash .github/scripts/auto-update-spec-kit-tests/run-tests.sh t1_detect
python3 .github/scripts/verify-gate-19.py
```

Both suites' existing (pre-feature) scenarios — the ones that fit within
one page — must still pass unchanged; their expected outputs in
`t1_detect.sh` and `verify-gate-19.py` are not touched by this feature,
only added to.

## 7. Read-outcome reporting (FR-010/FR-016/FR-017)

`verify-gate-19.py`'s fixture set includes a scenario where one of the
annotation collector's `gh api` calls is made to fail (matching the
`GH_STUB_FAIL`-style failure injection `auto-update-spec-kit-tests/gh_stub.py`
already uses). Expected: the collector's emitted `collector-outcomes.json`
entry for `collect-annotations` reads `"outcome": "failed"`, not merely an
empty `signals.json` contribution — confirming a failed read is
distinguishable from an empty one at the point closest to the defect this
feature exists to fix. End-to-end verification of the full `collect` →
`diagnose` wiring (the new `untrusted-collectors` job output actually
reaching the diagnose agent's prompt) is exercised by
`wing-commander-watchdog-test.yml`'s live dispatch, per its existing
failure-injection convention (`docs/agent-friendly-workflows.md`'s
"Keep a manually dispatched test workflow... with a failure-injection
input") — dispatch it against a real run with `WING_COMMANDER_...` inputs
set to force one collector to fail, and confirm the posted verdict names
that collector as untrusted.

## Out of scope for this quickstart

- Exercising the live `spec-kit/releases` endpoint against real upstream
  data — the auto-update harness is deliberately offline (research.md D4).
- Any change in what the `diagnose` agent concludes from a given evidence
  set — this feature does not change that reasoning (Out of Scope), so
  there is nothing new to validate about verdict *content*, only about
  which inputs reach it.
