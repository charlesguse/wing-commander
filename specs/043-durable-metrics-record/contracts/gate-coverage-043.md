# Contract: New Gate Coverage for Spec 043

Per constitution VIII ("A Green Check Means What It Says") and FR-039/FR-040,
each gate below is a `verify-*.py`/`.sh` script wired into exactly one
`run:` line inside a PR-triggered job of `lint-workflows.yml`, runs the
same subject with the same arguments locally as in CI
(`run-local-gates.py` picks it up automatically once wired — no second
registration point), and ships with the fixtures listed in data-model.md's
"Gate fixtures" table. Gate numbers are assigned sequentially at
implementation time (research.md R12); this document uses names, not
numbers.

## `verify-actions-layer-invariants` (extends #149's gap)

**Subject**: every `action.yml` under `.github/actions/**`.

**Asserts**: no scanned file reads `github.event.*` or `vars.*` (mirroring
`verify-stage-invariants.py`'s existing regex approach for
`.github/workflows`, applied to the actions directory it doesn't cover
today), and no scanned file contains `uses: anthropics/claude-code-action`
(FR-040a — this feature's own new/changed composites must add no agent
invocation). A waiver mechanism identical to
`stage-invariant-waivers.json`'s (exact file/pattern match, exact count,
stale-checked) applies to any pre-existing, unrelated violation this scan
newly discovers outside this feature's own files — this feature's own
files must have zero violations, not zero *new* violations.

**Fixture** (negative case): a checked-in `action.yml` snippet reading
`vars.SOMETHING` and one invoking `claude-code-action`, asserting the
gate fails and names both.

## `verify-metrics-record-schema`

**Subject**: contracts/metrics-record-schema.md's declared shape, checked
against fixture JSON files.

**Asserts**: a well-formed schema-version-1 fixture validates; a fixture
missing a required field, with a wrong type, or with a renamed field is
rejected and named; the `per_model` sum invariant holds for a multi-model
fixture and is checked (not just present).

## `verify-metrics-schema-version-tolerance`

**Subject**: the persistence workflow's/rollup's schema-version handling.

**Asserts**: a fixture record declaring `schema_version: 2` (unknown) is
retained in a fixture store and excluded from a fixture rollup
computation, without the gate's harness dropping, rewriting, or
erroring on it — driving spec.md's "retain and skip" requirement as a
behavioral test, not a code-review-only guarantee.

## `verify-metrics-persist-retry`

**Subject**: the append-with-retry composite (research.md R6-R8), run
against a local bare git repository fixture.

**Asserts**: two simulated concurrent writers (one push accepted, the
second's initial push rejected by non-fast-forward) both end with all
their records present in the final file after the second writer's retry
loop completes — and that a fixture engineered to reject every attempt
(simulating sustained contention beyond the bound) causes the step to
fail loudly, naming the specific `record_key`s left unwritten, rather
than hang or succeed silently.

## `verify-transcript-retention-declared`

**Subject**: every `upload-artifact` step across `.github/workflows/*.yml`
whose `path` matches the transcript or metrics-record filename pattern.

**Asserts**: `retention-days` is present and equal to `90` at every
discovered site (FR-032/FR-033/SC-010) — discovery-based (glob + parse,
matching `wc_published_stages.py`'s "derive, don't enumerate" convention),
so a new upload site added later without a declared retention period
fails this gate by construction, and the fixed "14 sites" the request
named vs. the measured 16 cannot recur as a silent gap.

**Fixture** (negative case): a workflow snippet with an `upload-artifact`
step matching the transcript pattern and no `retention-days`, asserting
the gate fails and names the exact file/step.

## Wiring assertions common to all five

- `verify-gate-wiring.py` (existing, unchanged) picks up each new script
  automatically once it has exactly one `run:` invocation inside
  `lint-workflows.yml` — no separate manifest edit.
- Each new gate's job in `lint-workflows.yml` carries `!cancelled()` (not
  bare `always()`, matching this repository's existing step-gating
  convention) so an unrelated job's cancellation doesn't suppress it, and
  is not made conditional on any other gate's outcome (constitution VIII:
  "not suppressible by the failure of an unrelated gate that merely
  shares its job").
- Each gate's PR trigger path list includes the files it actually reads —
  in particular, `contracts/metrics-record-schema.md` itself, so a change
  to the documented schema without a matching code change is caught
  (FR-040's explicit callout: "the lint workflow's deliberately literal
  path list does not cover today" any contract/schema document a spec
  adds).
