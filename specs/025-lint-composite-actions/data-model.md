# Phase 1 Data Model: Lint Composite Action Scripts

This feature adds no runtime application data — the "entities" here are the
shapes the guard's Python script reads from and writes to a pull request's
checkout and its annotations. They extend the spec's own Key Entities
section with the concrete fields each shape carries inside
`.github/workflows/lint-workflows.yml`'s check step.

## Script Source (new abstraction, not a new file)

The check step already handles one script source (reusable-workflow job
steps); this feature adds a second. Both are walked by the same code path
(research.md R1), described here as a single shape with two instances rather
than two separate schemas, since FR-004 requires them to be treated
identically.

| Field | Reusable-workflow instance | Composite-action instance |
|---|---|---|
| Discovery glob | `.github/workflows/*.yml` (unchanged) | `.github/actions/**/action.yml` and `.github/actions/**/action.yaml`, recursive (FR-008) |
| Parsed document | `yaml.safe_load(f)` — a workflow document | `yaml.safe_load(f)` — a composite action document |
| Step list location | `doc.get("jobs", {})[jname].get("steps", [])` — per job | `(doc.get("runs") or {}).get("steps") or []` — the action's own single list |
| Step identity in annotations | `{jname} / {step name or "step N"}` | `{step name or "step N"}` (no job dimension — a composite action has one flat step list, not jobs) |
| Parse-failure handling | `::error file={f}::YAML parse failure: {e}`, counts as a failure (existing) | Same message/counting, applied to this glob's files too (FR-009, research.md R3) |
| Actions/workflows with no scripts to check | A job with no `run:` steps contributes nothing (existing) | An action with no `runs.steps` (empty list, or a container/JavaScript action with no `steps:` key at all) contributes nothing (FR-008 Edge Cases, research.md R4) |

## Embedded Script (existing entity, unchanged shape)

Defined in spec.md's Key Entities as "a shell script block inside a step...
that the guard neutralizes for interpolation and then syntax-checks." This
feature does not change the shape of an Embedded Script or its processing —
it changes *where* the guard looks for step lists that might contain one
(Script Source, above). Once a `run:` value is found, whether the step came
from a workflow job or a composite action, it goes through the identical
sequence already in the file:

1. `re.sub(r"\$\{\{[^}]*\}\}", "EXPR", run)` — expression-interpolation
   neutralization (FR-004, spec User Story 1 Acceptance Scenario 3).
2. `subprocess.run(["bash", "-n"], input=script.encode(), ...)` — syntax
   check only, no execution (FR-006's documented limitation).
3. On non-zero exit: one `::error file={f}::{step-identity}: {stderr}`
   annotation, and the shared `failures` counter increments.

## Trigger Scope (existing entity, extended)

`on.pull_request.paths` in `lint-workflows.yml` is the guard's activation
condition. This feature adds one entry:

| Before | After |
|---|---|
| `[".github/workflows/**"]` | `[".github/workflows/**", ".github/actions/**"]` |

A pull request matching either glob (or both) triggers the `lint` job
(FR-002, User Story 2). The `push`/`schedule`/`workflow_dispatch` triggers
that feed Gate 1 (the `registered` job) are untouched — Gate 1's
workflow-registration-name check does not apply to composite actions (spec
Assumptions, research.md R5).

## No new persisted entity, no new external write surface

The extension writes to the same two destinations the existing gates already
use: `::error`/`::warning` annotations on the pull request's checks, and
`sys.exit(1 if failures else 0)` as the job's pass/fail signal. Nothing is
written to `GITHUB_STEP_SUMMARY`, no artifact is uploaded, and no comment is
posted — matching the existing "Parse YAML and bash -n every run block"
step's behavior exactly.
