# Contract: `verify-gh-error-stub-conformance.py` (Gate 126 — User Story 3)

FR-009/FR-010/FR-011/FR-012/FR-015's enforcement, as a standalone CLI gate
script matching this repository's existing `verify-*.py` shape.

## Usage

```text
python3 .github/scripts/verify-gh-error-stub-conformance.py
python3 .github/scripts/verify-gh-error-stub-conformance.py --self-test
```

## Inputs

The checked-out tree only: `.github/scripts/verify-*.py|.sh` and
`.github/scripts/*/run-tests.sh` (via `wc_gate_registry.gate_scripts()`),
`.github/workflows/*.yml|yaml` and `.github/actions/**/action.yml|yaml`
(to extract each harness's own subject block, per research.md D7).

## Behavior

1. **Derive the retrofit set** (data-model.md `Retrofit set`): for each
   `wc_gate_registry.gate_scripts()` entry whose source defines a
   `gh`-stubbing constant fed to `wc_shell_harness.run_step` (structural
   detection — a string assigned to a variable whose name matches
   `STUB_GH*` by convention, or more robustly, any script that imports
   `wc_shell_harness` and constructs a fake `gh` executable on a stub
   `PATH`), extract that harness's own subject `run:` text via its
   existing `find_step`/`extract_quoted_var` call and scan it with
   `wc_gh_capture`'s scanner (the same one User Story 2's gate uses). A
   harness is a **member** iff that scan finds at least one covered
   capture site in its own subject text.
2. **Check each member's stub arms** (data-model.md `Stub arm`): for each
   `gh`-error-simulating arm in a member's source (a branch that exits
   non-zero, matched by pattern against a covered capture's command), fail
   if that arm's body is not a call to
   `wc_shell_harness.gh_error_stub_arm(...)` — emit an `::error::` naming
   the gate script and the offending arm (FR-011: "naming the gate
   script").
3. **Check for a second literal copy anywhere** (FR-010): scan every
   `.github/scripts/**/*.py` file other than `wc_shell_harness.py` itself
   for the canonical JSON-error-body literal shape (a string containing
   both `"message"` and `"status"` keys matching the pattern
   `wc_shell_harness`'s own template uses). Fail on any match, naming the
   file and line — independent of whether that file is in the derived
   retrofit set, since a hand-rolled duplicate is a violation regardless
   of which gate wrote it (research.md D8).
4. Prints a summary line: `verify-gh-error-stub-conformance: <n> retrofit
   member(s) checked, <f> non-conforming stub(s), <d> duplicate literal(s);
   <f+d> failure(s).`
5. Exit code `1` if any failure was found, else `0`.
6. `--self-test` covers: the retrofit-set derivation against fixture
   harness/workflow pairs (a harness whose subject block has a covered
   capture is selected; one whose subject block has none is not); a
   fixture stub arm that hand-writes the JSON/stderr literal (fails,
   naming the fixture gate); a fixture stub arm that calls
   `gh_error_stub_arm(...)` (passes); a fixture duplicate literal placed
   outside `wc_shell_harness.py` (fails); and a mutation of a real
   member's shipped block — dropping a variable reset from the block
   `verify-auto-release-specs-fallback.py` executes — that makes *that
   harness's own self-test* fail where it passed before, proving the
   stub's FR-009 shape is load-bearing, not decorative (SC-004).

## Wiring (`lint-workflows.yml`)

```yaml
- name: "Gate 126 — every gh-error-simulating stub in a covered-capture harness uses the one shared home"
  run: python3 .github/scripts/verify-gh-error-stub-conformance.py
- name: "Gate 126 self-test — retrofit-set derivation, non-conforming stubs, and duplicate literals are each caught"
  run: python3 .github/scripts/verify-gh-error-stub-conformance.py --self-test
```

Gate number per research.md D6 — re-verify against `main` immediately
before landing.

## Failure message contract (FR-011/SC-005, testable)

- A non-conforming stub's message MUST contain the offending gate script's
  path and the literal substring `gh_error_stub_arm` (naming what it
  should have called instead).
- A duplicate-literal message MUST contain the offending file's path and
  the literal substring `wc_shell_harness.py` (naming the one home).

## SC-004's cross-harness proof, concretely

`verify-auto-release-specs-fallback.py`'s own `--self-test` (unchanged
interface) is the mechanism SC-004 exercises: after this feature migrates
its two stub arms onto `gh_error_stub_arm(...)` (research.md D9), a
mutation that removes a variable reset from `auto-release.yml`'s shipped
`specs/` fallback block still makes that harness's own self-test fail —
proving the migration did not weaken the stub's realism, only its
provenance.
