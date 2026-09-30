# Contract: The FR-012 Gate

**New script**: `.github/scripts/verify-no-reference-name-stage-match.py`

**Wired into**: `.github/workflows/lint-workflows.yml` as a new
`Gate <N> — ...` step (N = the next unclaimed gate number at
implementation time; see research.md R9), picked up automatically by
`.github/scripts/run-local-gates.py` via `wc_gate_registry`.

## What it checks

Scans these files for the nine reference display-name literals
(`"Wing Commander · 1 intake"` … `"Wing Commander · 7 cleanup"`,
`"Wing Commander · 9 pr conversation"`, `"Wing Commander · rebase"`, and
`"Wing Commander · 8 watchdog"`):

- `.github/workflows/watchdog.yml`
- `.github/actions/wing-commander-inspected-run-identity/action.yml`

A match used inside a shell conditional (`case ... in`, `if [ ... ]`,
`if [[ ... ]]`) that gates a collector's, gate's, or guard's behavior is
a **violation** unless it occurs inside the step whose `id:` is
`name-fallback` in `wing-commander-inspected-run-identity/action.yml`
(the FR-009 fallback — the one site FR-009a/FR-002 permit).

A bare mention in a comment, a log/summary string, or documentation text
is not a violation — only a match that participates in a conditional's
test expression counts.

## What it additionally checks (SC-008)

Every `uses: ./.github/actions/wing-commander-metrics-summary` block (and
any equivalent local invocation) across all published-stage and
consuming-instrument workflows MUST carry a `spec-identity-is-own:` key
in its `with:` block. A call site missing the key is a violation.

## Failure mode

Fails loudly (non-zero exit, a named finding per file/line) rather than
silently passing when it finds zero matches of either kind for reasons
other than "there are genuinely none" — e.g., it errors (not "0
violations") if either target file cannot be read, or if it cannot find
the `id: name-fallback` step at all (a sign the exception site itself
was renamed or removed without updating this gate), per constitution
VIII's "a gate that cannot reach its subject MUST fail loudly."

## Fixtures (FR-013/SC-006)

Checked-in fixtures under `.github/scripts/fixtures/no-reference-name-
stage-match/` (or inline synthetic strings, matching this repository's
existing gate-script convention) covering:

1. A clean file (today's `watchdog.yml`/`action.yml`, post-implementation)
   — passes.
2. A reference name reintroduced as a `case` condition outside
   `name-fallback` — fails, naming the file and line.
3. A reference name inside `name-fallback` itself — passes (the
   permitted site).
4. A `wing-commander-metrics-summary` call site missing
   `spec-identity-is-own:` — fails.
5. The `name-fallback` step renamed/removed — the gate errors rather
   than silently reporting zero violations.

## Verified by

This gate's own self-test step (`Gate <N> self-test`), matching the
convention every other structural gate in `lint-workflows.yml` already
follows (e.g. Gate 121, Gate 124, Gate 125's paired self-test steps).
