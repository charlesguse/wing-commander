# Contract: `verify-gh-api-error-capture.py` (Gate 125 — User Story 2)

FR-001/FR-002/FR-005/FR-006/FR-007/FR-008/FR-013/FR-014's enforcement, as a
standalone CLI gate script matching this repository's existing
`verify-*.py` shape (argparse, `--self-test`, a summary line ending in
`N failure(s).`, non-zero exit iff any failure) — modelled directly on
`verify-gh-api-explicit-method.py` (Gate 28).

## Usage

```text
python3 .github/scripts/verify-gh-api-error-capture.py
python3 .github/scripts/verify-gh-api-error-capture.py --self-test
```

No `--root` flag is needed: unlike a directory-walking gate, this scans a
fixed glob set (`.github/workflows/*.yml|yaml`,
`.github/actions/**/action.yml|yaml`) relative to the repository root the
script is invoked from, matching Gate 28's own argument-free live-run form.

## Inputs

The checked-out tree only. No environment variable, no waiver file — the
only sanctioned exception is the FR-008 marker, which lives at the site
itself (data-model.md's `exempt_marker`), never in a separate config.

## Behavior

1. Scans every `.github/workflows/*.yml|yaml` and
   `.github/actions/**/action.yml|yaml` file for a covered capture site
   (`wc_gh_capture.COVERED_GH_SUBCOMMANDS`, today `("api",)` — data-model.md
   `Capture site`).
2. For each, classifies its failure path (data-model.md `Failure path`):
   `exits`, `reassigns`, `loop-exits`, `opted-in` (FR-008 marker present
   with a non-empty reason), or `unsafe`.
3. For each `unsafe` site, emits one `::error::` line naming:
   - the file and line (FR-005's "naming the file, the line"),
   - the captured variable name (FR-005's "and the captured variable"),
   - what the failure path must do instead — one of "reassign `<var>`
     before its next use," "exit the step," or "add
     `# wc-gh-api-error-exempt: <reason>` if retaining the error body is
     deliberate" (FR-005's "stating what the failure path must do
     instead").
4. For each site carrying a marker with no reason after the colon, emits a
   distinct `::error::` naming the site and stating the marker requires a
   reason (FR-008).
5. Prints a summary line:
   `verify-gh-api-error-capture: <n> unsafe capture(s), <m> bare marker(s);
   <n+m> failure(s).`
6. Exit code `1` if any failure was found, else `0`.
7. `--self-test` runs the `CASES`/`MUTATIONS` fixture set (research.md D5,
   data-model.md `self_test_cases`/`self_test_mutations`) and reports
   `[ok]`/`[FAIL]` per case/mutation plus a final count line, exit `1` iff
   any misbehaved.

## Wiring (`lint-workflows.yml`)

Two steps in the existing PR-time job, following the two-step
check-then-self-test convention every numbered gate already uses:

```yaml
- name: "Gate 125 — no gh api capture carries an unhandled error body downstream"
  run: python3 .github/scripts/verify-gh-api-error-capture.py
- name: "Gate 125 self-test — every classification branch, including the #497 shape, fails where it should"
  run: python3 .github/scripts/verify-gh-api-error-capture.py --self-test
```

Gate number per research.md D6 — re-verify against `main` immediately
before landing. No `paths:` filter change: `.github/workflows/**` and
`.github/actions/**` are already listed in the `pull_request` job's
`paths:`.

## Failure message contract (FR-005/SC-006, testable)

Given an unsafe capture site at file `F`, line `L`, variable `V`, the
emitted message MUST contain, in any order:
- the literal string `F`,
- the literal string `L` (as it appears in the message, e.g. `F:L`),
- the literal string `V`,
- one of the literal substrings `reassign`, `exit`, or
  `wc-gh-api-error-exempt` (naming the required fix).

This is asserted directly by the `--self-test` fixtures (each fixture's
expected-failure string checked as a substring of the real output, Gate
28's own `self_test()` pattern), so the contract is enforced by the gate's
own regression suite, not only by this document.

## Self-test coverage (FR-007, SC-003)

At minimum, one fixture per:
- a capture with `if ! x=$(...); then exit 1; fi` (exits — passes),
- a capture with `if ! x=$(...); then x=""; fi` (reassigns — passes),
- a capture inside a loop with `if ! x=$(...); then continue; fi`
  (loop-exits — passes; the real `wing-commander-7-cleanup.yml` shape,
  research.md D1),
- a capture whose failure branch only logs (`echo "::warning::..."` with
  no reassignment/exit/continue) — fails, the #497-review shape FR-007
  names explicitly,
- a bare `x="$(gh api ...)"` with no guard at all — fails,
- a capture inside a pipeline (`gh api ... | jq ...`) with no status test
  — fails (spec.md Edge Case),
- a capture carrying `# wc-gh-api-error-exempt: <reason>` — passes,
- a capture carrying a bare `# wc-gh-api-error-exempt:` with no reason —
  fails, distinctly from the unsafe-site failure,
- a capture of a non-covered subcommand (`gh issue view --jq ...`) with an
  unsafe-looking failure path — does NOT fire this gate at all (FR-013's
  boundary).

Each `MUTATIONS` entry (research.md D5's classifier knobs) must flip at
least one of these fixtures' verdicts, so the gate cannot pass while
checking nothing (constitution VIII).
