# Contract: `verify-actions-no-gate-scripts.py` (the new placement gate)

FR-001/FR-006/FR-012/FR-014's enforcement, as a standalone CLI gate script
matching this repository's existing `verify-*.py` shape (argparse,
`--self-test`, a summary line ending in `N failure(s).`, non-zero exit iff
any failure).

## Usage

```text
python3 .github/scripts/verify-actions-no-gate-scripts.py
python3 .github/scripts/verify-actions-no-gate-scripts.py --self-test
python3 .github/scripts/verify-actions-no-gate-scripts.py --root <path>
```

`--root` matches the convention `verify-actions-layer-invariants.py`
already sets (defaults to `.`; used by `--self-test`'s tempdir fixtures,
never by the live CI/local-runner invocation).

## Inputs

None beyond the checked-out tree at `<root>/.github/actions`. No
environment variable, no waiver file — a violation under this gate's rule
has no legitimate exception (research.md D8's "Non-goals" note in
data-model.md); FR-014 requires the `_shared/` carve-out to be the *only*
bounded exception, and it is structural (the walk never reaches that
subtree, contracts/gate-registry-extensions.md), not a waiver a PR could
add to.

## Behavior

1. Calls `wc_gate_registry.unsupported_actions_scripts(root)`.
2. For each result, emits one `::error::` line naming:
   - the offending path,
   - whether it is a `run-tests.sh` harness entrypoint or a standalone
     `verify-*` script (FR-006's "naming the offending path"),
   - the supported location it belongs at instead — computed
     mechanically from the offending path's own composite-directory name
     (e.g. `.github/actions/wing-commander-widget/tests/run-tests.sh` ->
     "belongs at `.github/scripts/wing-commander-widget-tests/run-tests.sh`
     instead" — FR-006's "naming... the supported location under
     `.github/scripts/`"),
   - a pointer to this same file as the canonical explanation (FR-009's
     last sentence — this gate's own docstring carries the "why," so the
     message names its own filename, which Gate 47 also treats as a
     resolvable pointer target — research.md D7).
3. Prints a summary line: `verify-actions-no-gate-scripts: <n> unsupported
   location(s) found under .github/actions/; <n> failure(s).`
4. Exit code `1` if any unsupported location was found, else `0`.
5. `--self-test` runs the fixture set in research.md D8 against a fresh
   `tempfile.mkdtemp()` tree per fixture (the `verify-actions-layer-
   invariants.py` `_write`/`FIXTURES` shape) and reports `[ok]`/`[FAIL]`
   per fixture plus a final `x/y fixtures behaved as specified.` line,
   exit `1` iff any fixture misbehaved.

## Wiring (`lint-workflows.yml`)

Two steps in the existing PR-time job, immediately following Gate 10
(matching the two-step, check-then-self-test shape every numbered gate
already uses):

```yaml
- name: "Gate <N> — no test harness or standalone gate script lives under .github/actions/"
  run: python3 .github/scripts/verify-actions-no-gate-scripts.py
- name: "Gate <N> self-test — a harness or standalone verify-* script under .github/actions/ (outside _shared/), at any depth, is caught; a _shared/ helper is not"
  run: python3 .github/scripts/verify-actions-no-gate-scripts.py --self-test
```

`<N>` per research.md D3. No `paths:` filter change — `.github/actions/**`
is already listed (research.md D1).

## Failure message contract (FR-006/FR-009, testable)

Given an offending path `P` under `.github/actions/`, the emitted message
MUST contain, in any order:
- the literal string `P`,
- the literal substring `.github/scripts/` (the supported location),
- the literal substring `verify-actions-no-gate-scripts.py` (the
  canonical-home pointer target FR-009 requires the message to name).

This is asserted directly by the `--self-test` fixtures (each fixture's
expected-failure string is checked as a substring of the real output, the
same pattern `verify-actions-layer-invariants.py`'s own `self_test()`
already uses), so the contract is enforced by the gate's own regression
suite rather than only by this document.
