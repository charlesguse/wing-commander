# Contract: the FR-020 gate (`verify-write-boundary.py`)

This is the SC-007 backstop: a future edit that disables the boundary
check, drops the routing call, or lets the prompt statement drift from the
`no-write-paths` input it is supposed to render, fails the PR-time gate
suite by name rather than the next agent run discovering a `.claude/`-shaped
task the hard way again. Gate number is confirmed at implementation time
(research.md D7); this contract does not depend on the exact number.

## Registration

Two steps in `.github/workflows/lint-workflows.yml`, alongside the other
`verify-tasks-*`/`verify-stage-findings-*` gates:

```yaml
- name: Gate NN - the implement stage's write boundary is stated, classified, and routed consistently
  run: python3 .github/scripts/verify-write-boundary.py
- name: Gate NN self-test - write boundary
  run: python3 .github/scripts/verify-write-boundary.py --self-test
```

`run-local-gates.py` needs no separate edit — its gate list is derived from
`lint-workflows.yml` via `wc_gate_registry.pr_time_invocations` (Constitution
VIII: "reachable through the gate registry").

## Inputs (what the gate reads)

- `.github/workflows/implement.yml` and `.github/workflows/finalize.yml`,
  YAML-parsed (never grepped, per Gate 7/23/51's stated rationale).
- `.github/actions/wing-commander-tool-args/action.yml`'s shipped `compose`
  step, executed via `wc_shell_harness.run_step` to obtain the real
  rendered `write-paths-statement` for a table of `no-write-paths` values —
  never a Python re-implementation of the render (mirrors
  `verify-commit-message-scratch-path.py`'s own rule for its composite).
- `.github/actions/wing-commander-write-boundary/action.yml`'s shipped
  `classify-out-of-boundary-tasks.sh`, executed against synthetic
  `unchecked-items` text.
- `.github/actions/wing-commander-stage-findings/action.yml`'s shipped
  fingerprint delegation, and `.github/actions/_shared/
  compute-finding-fingerprint.sh` directly, to prove both call sites (the
  findings composite and `finalize.yml`'s lookup) compute the same value
  for the same input (the single-fingerprint-home claim, D6).
- `implement.yml`'s `Read back cycle outcome`/`Read back retry outcome`
  shipped `run:` bodies, extracted and executed the same way Gate 30/
  `verify-tasks-checkbox-convergence-signal.py` already extract theirs.

## Pass conditions

**(a) Single definition (FR-003).** `no-write-paths` is declared exactly
once as a `workflow_call` input on `implement.yml`, and every consuming
site (`wing-commander-tool-args`'s call, `wing-commander-write-boundary`'s
call, both arms) is wired to `${{ inputs.no-write-paths }}` — never a
second literal default appearing anywhere else in `implement.yml`.

**(b) Statement fidelity (FR-004, FR-005, SC-001, SC-007).** For a fixture
table of `no-write-paths` values (empty; `.claude/`; `.claude/,.git/`), the
shipped `compose` step's rendered `write-paths-statement` states exactly
the given prefixes and no others — the SC-007 drift mutation (hand-editing
the rendered string to add or drop an entry not present in the input)
fails this check.

**(c) Classification correctness (FR-006, FR-014, FR-015).** A fixture
table of unchecked-item texts, each with its expected classification
(out-of-boundary / falls-through), covering every Edge Case in spec.md:

- A single path, fully out-of-boundary → out-of-boundary.
- Several paths, one in-reach → falls through.
- No path in the text → falls through.
- A path only partly matching a prefix (e.g. `.claude-extra/`, not actually
  under `.claude/`) → falls through (prefix match, not substring match).
- The boundary is empty → nothing classifies out-of-boundary, ever.

**(d) Termination and reason (FR-007, FR-010, FR-011, FR-012).** Executing
the shipped read-back `run:` bodies against synthetic repos. `routed` is
derived as `ok && !truncated && all-unchecked-out-of-boundary`, deliberately
NOT gated on spec 059's `handoff` (PR #836 review, item 2) — ticking the
last in-reach task, or a `converge:` commit that re-appends only
out-of-boundary lines, must not block filing work that is already 100%
unreachable:

- Only unchecked task is out-of-boundary, nothing else progressed →
  `handoff=true`, `routed=true`, `reason` names the task.
- Same, but another task also got checked this cycle (`progressed=true`) →
  `handoff=false` (spec 059's own progress test is unaffected) but
  `routed=true`, and `reason` names the out-of-boundary task — progress on
  other work must not suppress filing work that is unreachable regardless.
- A `converge:` commit whose appended lines are all out-of-boundary →
  `routed=true` and `reason` names the task, overriding spec 059's
  "converge appended new work" text rather than being suppressed by it.
- A mixed unchecked set (one out-of-boundary, one ordinary) →
  `all-unchecked-out-of-boundary=false`, `routed=false`, existing narrative
  unchanged.

**(e) No filing on a truncated run (FR-013).** A synthetic truncated cycle
with an out-of-boundary-shaped `tasks.md` at the tip → the "Route
out-of-boundary tasks" step's own `if:` evaluates false; the gate asserts
this by evaluating the compiled `if:` expression against `truncated=true`,
`ok=true`, `routed=true`, never by executing a live filing call.

**(f) Idempotency (FR-008).** The same out-of-boundary unchecked line,
fingerprinted twice (simulating two cycles), produces byte-identical
fingerprints; a line whose text differs by even one character (a re-worded
task) produces a different fingerprint (documented as an accepted, narrow
limitation — research.md does not claim re-wording is detected as "the
same" task).

**(g) Fingerprint single-home (D6).** `compute-finding-fingerprint.sh` is
called by `wing-commander-stage-findings`'s shipped step and by
`finalize.yml`'s shipped lookup step; no third `sha256("anchor|...`-shaped
string literal appears anywhere else in `.github/`.

**(h) Board-loop label separation (research.md D4).** `write-boundary-
label-prefix`'s default (`route-out-of-boundary`) is not equal to
`findings-label-prefix`'s default (`found-by`) and is not the literal
string `spec-request` — a static assertion on the two defaults, failing
loudly if a future edit collapses them.

A fixture or comparison failing any of (a)-(h) fails the gate, naming the
file, step, and scenario — matching Gate 51's `::error file=...::Gate NN:
{msg}` format.

## `--self-test`

Reintroduces, and asserts each one is caught:

1. `no-write-paths` hand-edited to a second literal default inside
   `wing-commander-write-boundary`'s call site, diverging from `implement.
   yml`'s own input default — must fail (a).
2. The rendered `write-paths-statement` mutated to include a prefix absent
   from the input — must fail (b) (the SC-007 drift mutation).
3. The classification rule's prefix-match relaxed to a substring match
   (so `.claude-extra/foo` would wrongly classify under a `.claude/`
   boundary) — must fail (c).
4. The `routed` computation changed to ignore classification entirely
   (e.g. hard-coded `true` whenever `ok && !truncated`, even when
   `all-unchecked-out-of-boundary=false`) — must fail (d)'s mixed-set
   scenario (the SC-007 "disables the boundary check" mutation, read as
   "always routes").
5. The "Route out-of-boundary tasks" step's `if:` guard's `truncated`
   clause removed — must fail (e).
6. `compute-finding-fingerprint.sh` re-implemented inline a second time in
   a copy pasted into `finalize.yml` instead of called — must fail (g).
7. Zero fixtures discovered/executed at all — must fail loudly
   (Constitution VIII's "a gate that cannot reach its subject... MUST fail
   loudly rather than report a pass it did not earn").

## Out of scope for this gate

- Spec 059's own convergence/progress/hand-off fixtures — covered by
  `verify-tasks-checkbox-convergence-signal.py`, not reopened here (this
  gate only executes the *unchanged* decision table as a precondition for
  its own new-branch fixtures, per (d) above).
- `wing-commander-stage-findings`'s `defect`-kind rendered text and its
  pre-existing fingerprinting behavior for `found-by:*` findings — covered
  by `verify-stage-finding-schema.py`/`verify-stage-findings-wiring.py`,
  unaffected by this feature's additive `finding-kind` input.
- Live GitHub API behavior of `gh issue list --search` (text-search
  ranking, rate limits) — this gate executes the deterministic fingerprint
  computation and the `if:`-guard logic only; it does not call the GitHub
  API.
