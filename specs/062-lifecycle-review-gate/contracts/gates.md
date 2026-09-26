# Contract: Gates

Every gate below is registered as a `Gate N — <description>` step in
`.github/workflows/lint-workflows.yml`; `run-local-gates.py` picks each up
automatically by parsing that file (`wc_gate_registry.py`) — no separate
manifest edit. 98 is the highest gate number in use at plan time
(confirm the actual next-free numbers at implementation time, matching
spec 042's own precedent for this note).

| Gate | Script | Subject | Fixtures |
|---|---|---|---|
| Lifecycle readiness | `verify-lifecycle-readiness.py` | `lifecycle_readiness.py` | stale check summary; no checks; not mergeable; already reviewed at this SHA; kill switch set; all-clear |
| Lifecycle merge preconditions | `verify-lifecycle-merge-preconditions.py` | `lifecycle_merge_preconditions.py` | round not clean; unresolved human review; head SHA moved since round; all-clear |
| Constitution merge-class parity | `verify-constitution-merge-class-parity.py` | `lifecycle-review-gate.yml` + `.specify/memory/constitution.md` | merge code present, constitution silent (fail); constitution names the class, no merge code (pass); neither present (pass); both present (pass) |
| Fold-wiring | `verify-lifecycle-review-gate-fold-wiring.py` | `lifecycle-review-gate.yml`'s `disposition` job | fold-commit call present without a matching findings-partition step (fail, mirrors Gate 72's per-step-not-whole-file-scan discipline); both present together (pass) |

`verify-single-home-idioms.py` gains three `DECLARED_HOMES` entries:
`wing-commander-fold-commit` and `wing-commander-fold-dispatch`
(repointing `pr-conversation.yml`'s former inline `act`/`dispatch-once`
bodies) and `wing-commander-post-review-comment` (repointing
`board-loop.yml`'s former inline `gh api .../reviews -f event=COMMENT`
call) — failing if any of the three idioms' logic reappears pasted a
second time, or if either former inline call site still resolves the old
path.

## Fixture placement

- Script-level gates' fixtures are checked-in JSON files beside each
  script under `.github/scripts/tests/lifecycle-readiness/` and
  `.github/scripts/tests/lifecycle-merge-preconditions/`, matching
  `verify-board-readiness.py`'s existing `tests/board-readiness/`
  convention — each script's own `--self-test` entry point loads and
  asserts against them.
- Composite-level fixtures live under
  `.github/actions/wing-commander-fold-commit/tests/`,
  `.github/actions/wing-commander-fold-dispatch/tests/`, and
  `.github/actions/wing-commander-post-review-comment/tests/`, run via
  each composite's own `run-tests.sh` (the
  `wing-commander-stage-findings/tests/` convention).
- `verify-constitution-merge-class-parity.py`'s fixtures are inline
  synthetic YAML/Markdown snippets (the same shape
  `verify-board-readiness.py::check_no_merge_invariant`'s own self-test
  already uses for a raw-text scan), not a checked-in file, since the
  fixture text is short and the point being proven (regex fires/does not
  fire) does not benefit from a separate file.

## Reachability (constitution VIII, FR-037)

Every gate above runs the same subject with the same arguments locally
(`python .github/scripts/run-local-gates.py`) as `lint-workflows.yml` runs
in CI — automatic once each `Gate N` step is added, per
`wc_gate_registry.py`'s existing parsing of that file. Each ships paired
with a `--self-test` invocation proving the detector fires on its own
synthetic defect and stays silent on a clean fixture, matching every
existing gate's two-step registration shape.
