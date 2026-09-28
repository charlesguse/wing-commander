# Data Model: Composite Test Harness Gate Discovery

This feature persists nothing new (research.md: no storage layer beyond
`run-local-gates.py`'s pre-existing, machine-local timing cache). Every
entity below is a shape read back from the checked-out tree — workflow
YAML, action YAML, and the `.github/actions/`/`.github/scripts/`
directory structure — at gate-run time, giving each of spec.md's Key
Entities a concrete, code-level shape.

## Gate

A check the wiring rule applies to and `run-local-gates.py` can run.

| Field | Type | Source | Notes |
|---|---|---|---|
| `script` | string | `wc_gate_registry.gate_scripts()` | repo-relative, forward slashes, e.g. `.github/scripts/dispatch-and-wait-tests/run-tests.sh` — unchanged by this feature |
| `args` | tuple of string | `wc_gate_registry.pr_time_invocations()` | one entry per distinct call site; a gate CI invokes twice with different flags yields two `(script, args)` pairs |
| `identity` | string | **new**: `wc_gate_registry.gate_label(script, args)` | `script`'s path relative to `.github/scripts/` (not `os.path.basename`), joined with `args` — the fix for FR-007. Unique across the whole population by construction, since two distinct files cannot share a repo-relative path |

## Discovery root

The one directory prefix the naming convention applies to.

| Field | Type | Notes |
|---|---|---|
| `SCRIPTS_DIR` | constant `".github/scripts"` | unchanged — FR-001 keeps this the only root `gate_scripts()` walks |

## Composite test harness

The entrypoint of a test suite whose subject is a composite action's own
shipped shell.

| Field | Type | Source | Notes |
|---|---|---|---|
| `path` | string | `gate_scripts()` subset matching `.github/scripts/*/run-tests.sh` | today: `dispatch-and-wait-tests`, `size-path-backstop-tests`, `stage-findings-tests` (three composite harnesses per their own header comments — `auto-update-spec-kit-tests` and `e2e-provisioning-tests` also match this glob shape but their subject is workflow-embedded shell, not a composite `action.yml`, so they are outside FR-009/FR-011's "composite harness" scope even though `gate_scripts()` does not and should not distinguish them) |
| `subject_composite` | string | the harness's own `ACTION_YML` constant, e.g. `wing-commander-dispatch-and-wait` | read by the harness itself when it extracts a step's `run:` text to execute — not modelled by any gate script; recorded here for traceability only |

## Unsupported location

Any path under `.github/actions/`, outside `.github/actions/_shared/`,
holding a `run-tests.sh` or a standalone `verify-*` script. The
enforcement gate's only subject.

| Field | Type | Source | Notes |
|---|---|---|---|
| `path` | string | **new**: `wc_gate_registry.unsupported_actions_scripts(root=".")` | repo-relative; walk rooted at `<root>/.github/actions` only (research.md D2 Constraints) |
| `shape` | enum: `harness` \| `standalone-verify` | derived from filename (`run-tests.sh` vs. `verify-*.py`/`verify-*.sh`) | both shapes fail the same way (FR-006) |
| carve-out | — | any path with `.github/actions/_shared/` as a prefix | excluded before `path` is ever produced — FR-014: the carve-out is part of the walk's own boundary, never a second list of exempt files |

## Gate identity

The handle a gate is listed, reported, filtered, and cached by.

| Field | Type | Notes |
|---|---|---|
| `label` | string | `gate_label(script, args)` (research.md D5) — read by `run-local-gates.py`'s final table, `--jobs` filter matching, and the timing-cache key; and available to `verify-gate-wiring.py`'s new self-test fixtures (D6) for asserting uniqueness |
| uniqueness invariant | — | no two `(script, args)` pairs across the whole gate population may produce the same `label` — true by construction once `label` is derived from a full, repo-relative, necessarily-distinct `script` path rather than `os.path.basename(script)` |

## Wiring

The two-directional relationship between gates on disk and the `run:`
blocks that invoke them.

| Field | Type | Source | Notes |
|---|---|---|---|
| `forward[script]` | list of workflow paths | `wc_gate_registry.invocations()` | unchanged — already covers composite harnesses under `.github/scripts/*/run-tests.sh` (research.md D1); an empty list is a forward-direction failure (orphan) |
| `reverse[".github/scripts/..."]` | list of workflow paths | `wc_gate_registry.referenced_script_paths()` | unchanged |
| `reverse[".github/actions/..."]` | list of workflow paths | **new**: `wc_gate_registry.referenced_actions_script_paths()` | same substring-match technique as the `.github/scripts/` reverse check (research.md D4); a path present here with no file on disk is a reverse-direction failure (FR-004); the self-checkout prefix `./.wing-commander-pipeline/.github/actions/<X>` and the direct `./.github/actions/<X>` form both normalise to the same key, since only the `.github/actions/...` suffix is ever captured (FR-013) |

## Non-goals / explicitly out of scope for this data model

- No new persisted record, schema, or JSON file. `.github/scripts/
  single-home-waivers.json` and sibling waiver files are Gate 47's and
  other gates' pre-existing mechanisms; this feature adds no waiver
  concept of its own (a violation under FR-012 is always a hard failure —
  there is no legitimate case to waive, unlike `verify-actions-layer-
  invariants.py`'s `EXPRESSION_INVARIANTS`, which admits narrow, reasoned
  exceptions).
- No state transitions. Every entity above is recomputed fresh on each
  gate run from the checked-out tree; nothing here is stateful across
  runs except the pre-existing, out-of-scope timing cache.
