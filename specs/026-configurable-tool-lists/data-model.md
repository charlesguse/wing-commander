# Data Model: Configurable Allowed/Disallowed Tool Lists

**Feature**: 026-configurable-tool-lists

This feature has no application data store — its "entities" are the
configuration values and derived lists that flow through a GitHub Actions
job at run time (`workflow_call` inputs → composite action → composed CLI
flags). Documented here as data shapes/validation rules, mirroring the
spec's Key Entities section.

## Entities

### ToolListInput (per stage, per direction: allowed | disallowed)

The raw consumer-supplied configuration for one direction on one stage.
Exists twice per stage (allowed, disallowed); each instance has an append
field and an override field.

| Field | Type | Default | Notes |
|---|---|---|---|
| `extra` | string (comma-separated tool list) | `""` | FR-001/FR-002. `""` and unset are equivalent — both mean "append nothing." |
| `override` | string (comma-separated tool list, possibly empty) | sentinel `__unset__` | FR-003/FR-004. Distinguishes unset (`__unset__`) from an explicit empty replacement (`""`) per FR-009/D3. |

**Validation rule (FR-010)**: invalid when `extra` is non-empty **and**
`override` is not the sentinel, for the same (stage, direction) pair. The
composite action fails the run before any agent step runs, naming the
stage, direction, and both values.

### StageDefaultToolSet (per agent step, hard-coded)

The pipeline's existing built-in tool lists — unchanged by this feature,
just now treated as an explicit input to the composition step rather than
inlined directly into `claude_args:`.

| Field | Type | Notes |
|---|---|---|
| `stage` | enum: intake, clarify, plan, tasks, implement, finalize, cleanup, rebase, watchdog | Which published stage workflow. |
| `step_id` | string | Distinguishes internal agent steps within a stage (e.g. `implement.cycle`, `implement.retry`, `implement.post-progress-comment`, `watchdog.diagnose`, `watchdog.propose-fix`). Most stages have exactly one. |
| `default_allowed` | list\<string\> | The literal `--allowedTools` value that step already ships with today (see `contracts/stage-default-tool-lists.md`). |
| `default_disallowed` | list\<string\> | The literal `--disallowedTools` value that step already ships with today. |

No new storage: these values remain literal strings passed as composite
action inputs at each agent step's call site, exactly where the raw
`--allowedTools`/`--disallowedTools` strings live today.

### EffectiveToolSet (derived, per agent step invocation)

The output of composition (research.md D4) — what actually reaches
`claude_args:` for that run.

| Field | Type | Derivation |
|---|---|---|
| `effective_allowed` | list\<string\> (deduplicated) | `override` if provided, else `default_allowed ∪ extra_allowed` |
| `effective_disallowed` | list\<string\> (deduplicated) | `(override if provided, else default_disallowed ∪ extra_disallowed) − explicit_allow` |

Where `explicit_allow` is the consumer's own explicit allow contribution for
that direction pairing (`extra_allowed` in append mode, the full
`override` list in override mode) — never `default_allowed`. See research.md
D4 for the full precedence walk-through and worked edge cases.

**Invariant**: when both `ToolListInput` instances (allowed, disallowed)
for a stage are entirely unset, `EffectiveToolSet` is byte-for-byte
identical to today's hard-coded `default_allowed`/`default_disallowed`
(SC-005 — zero behavior change for existing consumers).

### ValidationError

Raised (as a failed GitHub Actions step, not a data object with runtime
identity) when the FR-010 rule is violated. Carries: stage name, direction
(`allowed`/`disallowed`), the `extra` value, and the `override` value, all
surfaced in the `::error::` annotation and `GITHUB_STEP_SUMMARY` per D6.

## Relationships

```
StageDefaultToolSet (1 per agent step, hard-coded)
        │
        ├── combined with ──▶ ToolListInput[allowed]   ─┐
        │                                                ├──▶ EffectiveToolSet
        └── combined with ──▶ ToolListInput[disallowed] ─┘
```

A stage with multiple internal agent steps (only `implement`, today) has
multiple `StageDefaultToolSet` rows but reuses the *same* pair of
`ToolListInput` values (D5) — the consumer's configuration is stage-scoped,
not step-scoped.

## State / lifecycle

No persistent state or state machine — this is a pure, stateless
computation performed once per job run, per agent step, from `workflow_call`
input values already present when the job starts. Nothing is written back
to `spec-meta.json` or any other persisted artifact.
