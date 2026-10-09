# Quickstart: validating the Haiku 5.5 change

Prerequisites: a checkout of the lifecycle branch; `gh` with workflow-dispatch rights;
the amendment PR (research D5) merged to `main`.

## 1. Tier upgrade (Story 1, SC-001, SC-002)

```bash
python .github/scripts/run-local-gates.py verify-haiku-tier-model-id
grep -rn "claude-haiku-4-5" .github/workflows .github/actions .specify/memory/constitution.md docs
```

Expected: gate passes; grep prints nothing. After merge, dispatch one finalize or
cleanup summary and one implement cycle; the metrics record's top-level `model` is
`claude-haiku-5-5`. Dispatch auto-update-spec-kit's reply path (or inspect its
`--model` line) for T026.

## 2. Diagnose shadow (Story 2, SC-003, SC-004, SC-006, SC-007)

```bash
gh variable set WING_COMMANDER_DIAGNOSE_SHADOW_SINCE --body "$(date +%F)"
gh workflow run wing-commander-8-watchdog.yml -f run-id=<an inspected run id>
```

Expected: the diagnose job has a `claude-haiku-5-5` shadow step; the filed/routed
outcome matches a rerun with the variable deleted; the metrics branch gains a record
with `run.run_label == "diagnose-shadow"` and a `trial.outcome` from the fixed set.
Delete the variable and re-run: no Haiku step runs (SC-006). Set `SINCE` 61 days back:
no Haiku step runs (SC-007).

## 3. Implement opt-in (Story 3)

Apply `model:haiku` to one lifecycle issue; let implement run one cycle. Expected:
resolve-model summary shows `claude-haiku-5-5`, escalation `claude-sonnet-5-5`,
budget 180; the cycle's record has top-level `model` `claude-haiku-5-5`. With
`model:opus` also applied, the cycle runs Opus. pr-conversation on that PR runs on its
usual tier.

## 4. Summary (Story 4, SC-005)

```bash
gh workflow run wing-commander-trial-summary.yml
python3 -I .github/scripts/trial-summary.py --records <path to records.jsonl>
```

Expected: per-step table as in data-model.md; "sample too small" until 200 compared
runs; a Sonnet record with a helper `claude-haiku-5-5` `per_model` entry is not
counted.

## 5. Full gate suite

```bash
python .github/scripts/run-local-gates.py
```
