# Contract: `workflow_call` Tool-List Inputs (consumer-facing)

**Feature**: 026-configurable-tool-lists

This is the draft of the addition to `specs/010-reusable-pipeline/contracts/
stage-interfaces.md`'s "Common inputs" table (research.md D7 — carried over
verbatim at implementation time). It is normative for every published stage
that runs an agent: `intake`, `clarify`, `plan`, `tasks`, `implement`
(covers converge), `finalize`, `cleanup`, `rebase`, `watchdog`.

## New inputs (added to every agent-running stage's `workflow_call.inputs`)

| Input | Type | Default | Purpose |
|---|---|---|---|
| `extra-allowed-tools` | string | `""` | FR-001. Comma-separated tool list, same syntax as the pipeline's own `--allowedTools` values (e.g. `Bash(gh pr view:*),Read`). Added to the stage's default allowed tools — union, not replacement. Unset/empty = no addition (SC-005). |
| `extra-disallowed-tools` | string | `""` | FR-002. Comma-separated tool list. Added to the stage's default disallowed tools — union, not replacement. Unset/empty = no addition (SC-005). |
| `allowed-tools-override` | string | `__unset__` (sentinel — see below) | FR-003. When set to any value other than the sentinel default (including `""`), replaces the stage's default allowed tools entirely. `""` means "replace with nothing" (an explicit, intentional empty list), distinct from leaving the input unset. |
| `disallowed-tools-override` | string | `__unset__` (sentinel — see below) | FR-004. Same semantics as `allowed-tools-override`, for the disallowed list. |

**Why a sentinel default instead of `""`**: GitHub Actions resolves an
unset optional string `workflow_call` input to the same value as an
explicitly-passed `""` — there is no native "not provided" for strings.
FR-009 requires the pipeline to tell "not provided" (keep defaults) apart
from "explicitly empty" (an intentional replace-with-nothing). `__unset__`
is reserved for this purpose; it is not a legal tool name and a consumer
should never pass it deliberately. See research.md D3.

## Semantics

- **Backward compatibility (FR-005, SC-005)**: a consumer who sets none of
  these four inputs observes byte-for-byte identical `--allowedTools`/
  `--disallowedTools` values to today, on every stage.
- **Append vs. replace are per-direction, independent choices**: a single
  stage invocation may append on `allowed` while replacing `disallowed`, or
  any other combination — the four inputs are evaluated independently in
  pairs (`extra-allowed-tools`+`allowed-tools-override`,
  `extra-disallowed-tools`+`disallowed-tools-override`).
- **Conflict is an error, not a merge (FR-010)**: supplying both
  `extra-allowed-tools` and a non-sentinel `allowed-tools-override` (or the
  disallowed equivalent) fails the stage before any agent step runs, naming
  the stage, the direction, and both values supplied.
- **Explicit allow beats default deny (FR-011)**, **explicit deny beats
  default allow** (User Story 2 Acceptance #2): see research.md D4 for the
  exact composition rule; both are handled by the same subtraction rule,
  not special-cased.
- **Stage-scoped, not step-scoped (D5)**: on stages with more than one
  internal agent step (currently only `implement`, whose cycle/retry/
  post-progress-comment steps have different defaults — see
  `stage-default-tool-lists.md`), the same four inputs apply to *every*
  internal step of that stage, each composed against that step's own
  defaults. A replacement that omits a tool one of those internal steps
  needs is the consumer's responsibility (FR-012), exactly as for the
  stage's primary work.
- **Tool name syntax is not validated by this feature**: values are passed
  through to `anthropics/claude-code-action@v1`'s own `--allowedTools`/
  `--disallowedTools` parsing; a malformed tool pattern surfaces as that
  action's own error, not a pipeline-specific one (spec Assumptions).
- **These composed lists also drive a stage's stated-tooling output, where
  one exists**: on stages whose prompt states its own shell tooling
  (`implement.yml`), that statement is rendered from the same composed
  allowed/disallowed lists these four inputs produce — see
  [tool-composition-action.md#outputs](tool-composition-action.md#outputs).

## Example (wrapper/consumer usage)

Appending one tool to the `clarify` stage while keeping every default:

```yaml
uses: ./.github/workflows/clarify.yml
with:
  # ...existing inputs...
  extra-allowed-tools: "Bash(npm run lint:*)"
```

Replacing `watchdog`'s `propose-fix` step's allowed tools entirely (the
consumer accepts full responsibility for including everything that internal
step needs, per FR-012/D5):

```yaml
uses: ./.github/workflows/watchdog.yml
with:
  # ...existing inputs...
  allowed-tools-override: "Read,Grep,Glob,Edit"
```

Both `extra-allowed-tools` and `allowed-tools-override` set on the same
stage/direction — rejected before any agent runs (FR-010):

```yaml
with:
  extra-allowed-tools: "Bash(npm run lint:*)"
  allowed-tools-override: "Read,Grep"
# => stage fails fast: "extra-allowed-tools and allowed-tools-override
#    were both supplied for stage 'clarify' — choose one."
```
