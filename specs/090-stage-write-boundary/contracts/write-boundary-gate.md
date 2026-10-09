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
- A path that CONTAINS the boundary prefix without starting with it (e.g.
  `src/.claude/nested/thing.md`) → falls through — the fixture that
  actually distinguishes prefix-match from substring-match, since the
  `.claude-extra/` fixture above never contains the literal boundary text
  at all and would pass a substring-match mutant too.
- The boundary is empty → nothing classifies out-of-boundary, ever.
- `.claude/settings.json` (a task that would widen the stage's own grants)
  → out-of-boundary, asserted explicitly rather than left to fall out of
  the prefix comparison by coincidence (PR #836 review, item 8).

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
- The same mixed set on a cycle that progressed (`handoff=false`,
  `routed=false`) → the real Route step's `if:` fires at and past the
  iteration cap and not below it, and the shipped dispatch step takes the
  terminal "Iteration cap reached" hand-off at the cap and redispatches
  below it, so the last cycle files the out-of-boundary task and no
  earlier one does (the `iteration >= max` disjunct; code review of #836).

**(e) No filing on a truncated run (FR-013).** A synthetic truncated cycle
with an out-of-boundary-shaped `tasks.md` at the tip → the "Route
out-of-boundary tasks" step's own `if:` evaluates false; the gate asserts
this by evaluating the compiled `if:` expression against `truncated=true`,
`ok=true`, `routed=true`, never by executing a live filing call.

**(f) Idempotency (FR-008, SC-004).** The same out-of-boundary unchecked
line, fingerprinted twice (simulating two cycles), produces byte-identical
fingerprints; a line whose text differs by even one character (a re-worded
task) produces a different fingerprint (documented as an accepted, narrow
limitation — research.md does not claim re-wording is detected as "the
same" task). SC-004's full "two cycles → one issue" claim is proven
jointly with Gate 71 (`stage-findings-tests/run-tests.sh`), which already
drives `wing-commander-durable-failure-issue`'s real marker-based dedup
and proves a second report carrying the same marker is commented onto the
existing issue rather than creating a second one, generically for every
finding-kind — re-testing that nested `uses:` chain here would be a second
copy of Gate 71's own test infrastructure. This gate only asserts that
Gate 71's step is still wired, so a future removal does not silently break
the chain without failing anything.

**(g) Fingerprint single-home (D6).** `compute-finding-fingerprint.sh` is
called by `wing-commander-stage-findings`'s shipped step and by
`finalize.yml`'s shipped lookup step; no third `sha256("anchor|...`-shaped
string literal appears anywhere else in `.github/`.

**(h) Board-loop label separation (research.md D4).** `write-boundary-
label-prefix`'s default (`route-out-of-boundary`) is not equal to
`findings-label-prefix`'s default (`found-by`) and is not the literal
string `spec-request` — a static assertion on the two defaults, failing
loudly if a future edit collapses them.

**(i) Enforcement parity (FR-004, FR-005, Principle V/IX; PR #836 review,
item 3).** For the same `no-write-paths` fixture table as (b), the
`compose` step's composed `disallowed-tools` output actually contains one
`Edit(<prefix>**)`/`Write(<prefix>**)` pair per prefix — the stated
boundary must be the SAME one the agent's tool grant enforces, never just
prose.

**(j) Finalize lookup failure handling (PR #836 review, item 5).** The
shipped "Look up routed write-boundary items" step, driven with a stubbed
`gh` that fails its one `gh issue list` call, degrades to an empty mapping
(never fails the job) AND emits an `::warning::` annotation — a silent
"(none)" is the same failure (d) exists to catch, one layer further out.

**(k) Prompt interpolation and Route step wiring (PR #836 review, item
4).** Both the cycle and retry prompts actually interpolate their own
`write-paths-statement` output; the "Route out-of-boundary tasks" step's
`findings-json` is wired from `steps.final.outputs.write-boundary-
findings-json` and its `finding-kind` is the literal `routed-task` — none
of these four facts had ever been asserted, so any one could be silently
deleted with every other pass condition still green.

The same pass condition also requires a step named "Flag failed
out-of-boundary routing on lifecycle issue", keyed on the Route step's
`outcome == 'failure'`, on non-zero `dropped-api-failure`,
`dropped-malformed` and `dropped-cap` outputs, and on an `outcome ==
'success'` that filed and appended nothing (a crash in the composite's
prepare step reports all-zero counts) -- the five OR-joined under one
`!cancelled()`, so any one of them fires it, and evaluated to stay quiet
on a successful route (`filed=1` or `appended=1`, every drop count 0) and
to fire on one that filed nothing -- and
posting through
`wing-commander-callout` to `inputs.issue-number` -- the Route step is
`continue-on-error` and its composite always exits 0, reporting an API
error, a malformed entry or a task over the per-run cap only in those
counts, so without it an unfiled task ends the loop with nothing on the
lifecycle issue (Maintenance backlog #889; FR-007).

**(m) Label prefix single home (Maintenance backlog #889).** `implement.
yml`'s `write-boundary-label-prefix` default is the one home of the
routed-item label prefix. `finalize.yml`'s input default, `wing-commander-
write-boundary-lookup`'s `label-prefix` default, and both wrappers'
`vars.WING_COMMANDER_WRITE_BOUNDARY_LABEL_PREFIX || '<default>'` fallbacks
each equal it, and no other standalone occurrence of that value (quoted,
`=`-assigned, a YAML value, a `${VAR:-<value>}` fallback or a bare shell
argument -- anything but an `id:` value or a `steps.<id>` reference)
appears in a workflow, composite action or `_shared/` script.

A fixture or comparison failing any of (a)-(m) fails the gate, naming the
file, step, and scenario — matching Gate 51's `::error file=...::Gate NN:
{msg}` format.

## `--self-test`

Each mutation re-runs the REAL pass-condition function it targets against
the mutated input (PR #836 review, item 4) — never a parallel hand-rolled
assertion that could drift from, or simply not notice the deletion of, the
normal-mode check it stands in for. Reintroduces, and asserts each one is
caught:

1. `no-write-paths` hand-edited to a second literal default inside
   `wing-commander-write-boundary`'s call site, diverging from `implement.
   yml`'s own input default — re-runs (a) against the mutated text, must
   fail.
2. The rendered `write-paths-statement` mutated to include a prefix absent
   from the input — re-runs (b) against the mutated compose step, must
   fail (the SC-007 drift mutation).
3. The classification rule's prefix-match relaxed to a substring match —
   re-runs (c) against the mutated script, must fail (via the
   `src/.claude/nested/thing.md` fixture, the one that actually
   distinguishes prefix-match from substring-match).
4. The `routed` computation changed to ignore classification entirely
   (e.g. hard-coded `true` whenever `ok && !truncated`, even when
   `all-unchecked-out-of-boundary=false`) — re-runs (d) against the
   mutated cycle step, must fail on the mixed-set scenario (the SC-007
   "disables the boundary check" mutation, read as "always routes").
5. The "Route out-of-boundary tasks" step's `if:` guard's `truncated`
   clause removed — re-runs (e) against the mutated text, must fail.
6. `compute-finding-fingerprint.sh` re-implemented inline a second time in
   a copy pasted into the lookup composite instead of called — re-runs (g)
   against the mutated file content, must fail.
7. Zero fixtures discovered/executed at all — must fail loudly
   (Constitution VIII's "a gate that cannot reach its subject... MUST fail
   loudly rather than report a pass it did not earn").
8. The RETRY arm's `routed` condition hard-coded to `if false` — re-runs
   (d) against the mutated retry step, must fail on the retry scenario
   (RETRY_STEP was loaded into the gate's own step cache but, before this
   mutation existed, no scenario had ever exercised it).
9. Either prompt's `write-paths-statement` interpolation deleted (cycle and
   retry, checked separately) — re-runs (k) against the mutated text, must
   fail both times.
10. The Route step's `findings-json` input replaced with the literal
    `'[]'` — re-runs (k) against the mutated text, must fail.
11. The compose step's `Edit()`/`Write()` glob-deny append stripped, so
    `write-paths-statement` still renders but the composed
    `disallowed-tools` list no longer enforces it — re-runs (i) against
    the mutated compose step, must fail (PR #836 review, item 13).
12. The shared fingerprint helper's anchor-branch hash input salted with a
    fresh value on every call, breaking its determinism — re-runs (f)
    against the mutated script, must fail (PR #836 review, item 13).
13. `write-boundary-label-prefix`'s default collapsed onto
    `findings-label-prefix`'s default — re-runs (h) against the mutated
    text, must fail (PR #836 review, item 13).
14. The Route step's `fromJSON(inputs.iteration) >=
    fromJSON(steps.cap.outputs.max)` disjunct dropped — re-runs (d)'s
    iteration-cap scenario against the mutated text, must fail (code
    review of #836; the gate's own mutation 19, since its numbering and
    this list's have drifted apart).
15. `finalize.yml`'s `write-boundary-label-prefix` default drifted from
    `implement.yml`'s — re-runs (m) against the mutated text, must fail.
16. A third literal copy of the default pasted into another workflow —
    re-runs (m) against the mutated text, must fail.
17. The failed-routing flag step's `if:` no longer keyed on the Route
    step's failure — re-runs (k) against the mutated text, must fail.
18. The failed-routing flag step's `if:` stripped of its
    `dropped-api-failure` clause — re-runs (k) against the mutated text,
    must fail.
19. The failed-routing flag step's clauses AND-joined instead of
    OR-joined — re-runs (k) against the mutated text, must fail.
20. An unquoted copy of the default passed as a `with:` value in another
    workflow — re-runs (m) against the mutated text, must fail.
21. The failed-routing flag step's `if:` stripped of its filed-nothing
    clause — re-runs (k) against the mutated text, must fail.
22. A `${VAR:-<default>}` shell fallback copy of the default in a
    `_shared/` script — re-runs (m) against the mutated text, must fail.
23. A copy of the default under a hyphenated `*-id:` key (e.g.
    `issue-id:`), which must not be discounted as a step `id:` — re-runs
    (m) against the mutated text, must fail.

## Out of scope for this gate

- Spec 059's own convergence/progress/hand-off fixtures — covered by
  `verify-tasks-checkbox-convergence-signal.py`, not reopened here (this
  gate only executes the *unchanged* decision table as a precondition for
  its own new-branch fixtures, per (d) above).
- `wing-commander-stage-findings`'s `defect`-kind rendered text and its
  pre-existing fingerprinting behavior for `found-by:*` findings — covered
  by `verify-stage-finding-schema.py`/`verify-stage-findings-wiring.py`,
  unaffected by this feature's additive `finding-kind` input.
- Live GitHub API behavior of `gh issue list` (rate limits, pagination) —
  this gate stubs `gh` for (j) and executes the deterministic fingerprint
  computation and the `if:`-guard logic only; it never calls the real
  GitHub API.
