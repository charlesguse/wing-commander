# Data Model: 132-workflow-trigger-security

## Analyser pin
- `.github/scripts/zizmor-pin.txt`: `version=1.33.1`, `sha256=<release asset checksum>`.
- Read by the gate (version check) and the CI install step.

## Analyser configuration (`.github/zizmor.yml`)
- `rules.self-repository.disable: true` plus `reason` (required, non-empty).
- `rules.unpinned-uses.config.policies`: `actions/*`, `github/*`, `anthropics/*` → `ref-pin`; `*` → `hash-pin`. This is the trusted-publisher list's one home.

## Accepted-findings record (`zizmor-findings-waivers.json`)
| Field | Rule |
|---|---|
| `file` | repo-relative path, must exist |
| `audit` | zizmor audit id, e.g. `dangerous-triggers` |
| `location` | `workflow`, `job:<id>` or `job:<id>/step:<id-or-name>`; never a line |
| `reason` | non-empty one line |
| `control` | named gate: `author-association`, `label`, `permissions-empty`, or other named control |
| `issue` | `"#N"` open tracker, or null with `permanent: true` and `permanent_reason` (gate 124 schema) |
| `decided_by` | optional provenance |

Validation: each record matches exactly one current finding (else stale); each finding matches at most one record; no duplicate keys.

## Repo-only reusable workflow list (`repo-only-reusable-workflows.json`)
- Array of workflow paths. Each must exist, declare `workflow_call`, and be called only from this repository's workflows.

## Placement (gate-internal)
`{job, step, kind: checkout|artifact|extract|write, repository, ref, path, trust: trusted|untrusted}`. A `./` reference resolves to a path; the gate fails when the path falls inside an untrusted placement.

## Trigger inventory (gate-internal)
Set of event names from `on:` of every `wing-commander-*.yml`, compared with the `wc-event-policy` block in `docs/adoption.md`.
