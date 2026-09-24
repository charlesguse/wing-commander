# Contract: Gates

Every gate below is registered as a `Gate N — <description>` step in
`.github/workflows/lint-workflows.yml`; `run-local-gates.py` picks each up
automatically by parsing that file (`wc_gate_registry.py`, research.md
D24) — no separate manifest edit.

| Gate | Script | Subject | Fixtures (FR-064) |
|---|---|---|---|
| Eligibility | `verify-board-eligibility.py` | `board_eligibility.py` | maintainer-authored/no-label; maintainer-applied label; bot-applied same label (not admitted); pipeline-only label |
| Triage | `verify-board-triage.py` | `board_triage.py` | 429 present; 429 absent (genuine failure); evidence unavailable; action-bump ahead; pins equal; already-fixed proposal (must not close); action-bump scoped to the cited run's own workflow(s) (#505); cite step reads only the trust-filtered context-file (#505) |
| Route backstop | `verify-board-route-backstop.py` | `board_route_backstop.py` + `wing-commander-size-path-backstop` | under threshold; over threshold; contract-widening; post-push final-diff breach |
| Readiness | `verify-board-readiness.py` | `board_readiness.py` | stale check summary; no checks; open findings; backstop breach; kill switch set; all-clear |
| Review-finding schema | `verify-board-review-finding-schema.py` | `.github/schemas/board-review-finding.schema.json` | one well-formed finding; one omission per required field |

`verify-single-home-idioms.py` gains two `DECLARED_HOMES` entries:
`wing-commander-size-path-backstop` (repointing `pr-conversation.yml`'s
former inline check) and `wing-commander-dispatch-and-wait` (repointing
`auto-release.yml`'s former inline `dispatch-release` correlation block) —
failing if either idiom's logic reappears pasted a second time, or if
either former inline call site still resolves the old path.

## Fixture placement

- Script-level gates' fixtures are checked-in JSON/YAML files beside the
  script under `.github/scripts/tests/board-*/` (matching the existing
  `verify-post-agent-credential-refresh.py` mutation-fixture convention —
  each gate script feeds its own fixtures inline via its own self-test
  entry point, so `python3 .github/scripts/verify-board-*.py` both lints
  live subjects and re-asserts every fixture on every run).
- Composite-level fixtures live under
  `.github/actions/wing-commander-size-path-backstop/tests/` and
  `.github/actions/wing-commander-dispatch-and-wait/tests/`, run via each
  composite's own `run-tests.sh` (matching
  `wing-commander-stage-findings/tests/`).

## Reachability (FR-065)

Every gate above runs the same subject with the same arguments locally
(`python .github/scripts/run-local-gates.py`) as `lint-workflows.yml` runs
in CI — this is automatic once the `Gate N` step is added, per
`wc_gate_registry.py`'s existing parsing of that file.
