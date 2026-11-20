# Quickstart: validating the proof list

Prerequisites: a checkout with full history; `python3`, PyYAML.

1. **Gate suite**: `python .github/scripts/run-local-gates.py` — includes `verify-proof-list.py` (fixtures for each of the five states, ties, shared-issue condition, bot/marker rules, set-apart runs, shortening, over-size failure, refusal/pause/incomplete-read) and the single-home check (SC-006).
2. **SC-001 replay**: `python .github/scripts/verify-proof-list.py` replays the checked-in corpus for 2026-10-15…2026-11-16 and diffs against the checked-in expected-differences list; any other difference fails.
3. **Determinism (SC-003)**: the gate builds twice from the same inputs and compares states.
4. **Dry render**: `python .github/scripts/wc_proof_list.py render fixtures/proof-list/<case>.json` prints the section; confirm no verdict wording.
5. **After merge** (`prove-after-merge`): dispatch `wing-commander-proof-list.yml` on `main`, then `gh issue view <Board status #>` and confirm the collapsed section shows a build time; dispatch from another branch and confirm refusal; set `WING_COMMANDER_PROOF_LIST_PAUSED=true` (owner) and confirm the paused notice with last-good date.

See [contracts/proof-list-report.md](contracts/proof-list-report.md) and [data-model.md](data-model.md).
