# Contract: Resolved Stage Identity

**Owner**: `.github/actions/wing-commander-inspected-run-identity/action.yml`

**Consumers**: `watchdog.yml`'s branch-drift, spec-meta, final-pr-claims,
and spec-collision collectors; the branch-drift push-expected-stage gate
and its implement-only baseline arms; the stage label for the summary
line; the watchdog's own self-inspection cascade guard.

**Not a consumer**: the slug-fallback allowlist inside the same
composite, which per FR-008/FR-002 reads the metrics record's
`spec.identity_is_own` declaration instead (see
`spec-identity-declaration.md`).

## Outputs

| Output | Type | Values |
|---|---|---|
| `resolved-stage` | string | `intake` \| `clarify` \| `plan` \| `tasks` \| `implement` \| `finalize` \| `cleanup` \| `rebase` \| `pr-conversation` \| `` (empty) |
| `resolved-stage-source` | string | `record` \| `name` \| `` (empty) |

## Rule 1 — Precedence is fixed and lives in exactly one step

`resolved-stage` is `record-stage` (the composite's existing output)
whenever `record-stage` is non-empty. Only when `record-stage` is empty
does the composite consult `inputs.run-name` against the name-derived
map in `data-model.md`. A caller MUST NOT re-derive this precedence
itself; every FR-002 consumer site reads `resolved-stage`/
`resolved-stage-source` as a job output, never `run-name` directly.

## Rule 2 — Three states, never collapsed

A consumer comparing `resolved-stage` against its own expected stage(s)
MUST distinguish:

1. `resolved-stage` matches → in scope, collector runs.
2. `resolved-stage` is non-empty and does not match → out of scope,
   silent skip (unchanged from pre-feature behavior).
3. `resolved-stage-source == ''` → not identified. The consumer MUST NOT
   take the state-2 skip path silently; it MUST additionally record a
   `{"collector": "<name>", "outcome": "unresolved"}` entry in
   `collector-outcomes.json` (see `stage-unresolved-reporting.md`).

## Rule 3 — No added download

Computing `resolved-stage`/`resolved-stage-source` MUST NOT issue a
second `gh run download` for the metrics record. It reuses the file(s)
already present at `$RUNNER_TEMP/spec-slug-metrics-record` from the
existing `record-stage` step.

## Rule 4 — `record-stage` is unchanged

`record-stage`'s own value, type, and the signals that key on it
(`tool-denial`'s `{stage, tool}` fingerprint, spec 109 FR-013) are
untouched by this feature. `resolved-stage` is additive.

## Verified by

- The FR-012 gate (`stage-identity-name-gate.md`) asserts no FR-002 site
  other than the `id: name-fallback` step inside this composite compares
  against a reference display name.
- `verify-metrics-record-schema.py`/`verify-metrics-summary-record-
  emission.py` fixtures exercise: record with a stage (source=record),
  record present but `stage_available: false` with a recognised name
  (source=name), no record with a recognised name (source=name), no
  record with an unrecognised name (source=empty).
