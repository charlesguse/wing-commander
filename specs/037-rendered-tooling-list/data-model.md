# Data Model: The Prompt's Tooling List States What the Run Actually Permits

**Feature**: 037-rendered-tooling-list

Like spec 026, this feature has no application data store — its "entities"
are values computed inside one GitHub Actions composite-action step at run
time, plus the two documentation artifacts User Story 3/4 add. Documented
here as data shapes and derivation rules, mirroring the spec's Key Entities
section and building directly on
`specs/026-configurable-tool-lists/data-model.md`'s `EffectiveToolSet`
(unchanged by this feature — see research.md D2).

## Entities

### ShellGrant (derived, per entry in `effective_allowed`/`effective_disallowed`)

One classified entry from the composed lists spec 026 already produces.
Existing entries are unchanged; this feature adds the classification.

| Field | Type | Notes |
|---|---|---|
| `form` | enum: `ANY`, `PREFIX`, `EXACT`, `NOT_SHELL` | research.md D1. `ANY` = bare `Bash`. `PREFIX(cmd)` = `Bash(cmd:*)` / `Bash(cmd *)`. `EXACT(cmd)` = `Bash(cmd)`. `NOT_SHELL` = any other tool entry (`Read`, `Skill`, ...) — excluded from every downstream step. |
| `command` | string \| null | The bare command text for `PREFIX`/`EXACT` (matcher wrapper and trailing `:*`/` *` stripped); null for `ANY` and `NOT_SHELL`. |
| `source_list` | enum: `allowed`, `disallowed` | Which composed list (spec 026's `effective_allowed`/`effective_disallowed`) the entry came from. |

### CoverageResult (derived, per allow grant)

Whether an allow `ShellGrant` survives after checking it against every
`disallowed` `ShellGrant` for the same command (research.md D2's table;
`ANY` allow checked against every disallowed grant, not just same-command
ones — see `StatementCase` below).

| Field | Type | Notes |
|---|---|---|
| `allow_grant` | ShellGrant | The candidate. |
| `covering_deny` | ShellGrant \| null | The first disallowed grant whose scope is a superset of `allow_grant`'s scope, or null if none covers it. |
| `survives` | boolean | `covering_deny == null`. A grant with `survives = false` is subtracted from the statement entirely; the enforced `effective_allowed`/`effective_disallowed` lists are untouched (research.md D2 — this is a read, never a write). |

### StatementCase (derived, one per composition)

Which of research.md D5's four sentence templates applies, computed after
`CoverageResult` filtering and per-command broadening (D4).

| Value | Condition |
|---|---|
| `EMPTY` | No surviving allow grant of form `PREFIX`/`EXACT`, and no surviving `ANY` grant either (an `ANY` allow is itself covered when a disallowed `ANY` grant exists — D2's ANY-covers-ANY cell). |
| `UNRESTRICTED` | A surviving `ANY` allow grant exists, and no disallowed grant of any command survives as an exception (D3). |
| `UNRESTRICTED_EXCEPT` | A surviving `ANY` allow grant exists, and one or more command-specific disallowed grants do not themselves cover `ANY` (D3) — those commands are named as exceptions. |
| `ENUMERATED` | One or more surviving `PREFIX`/`EXACT` command grants, no surviving `ANY` allow grant. |

### CommandStatementEntry (derived, one per distinct command in the `ENUMERATED`/`UNRESTRICTED_EXCEPT` case)

The per-command rendering unit after D4's broaden-and-dedupe pass.

| Field | Type | Notes |
|---|---|---|
| `command` | string | Bare command text. |
| `broadest_surviving_form` | enum: `PREFIX`, `EXACT` | `PREFIX` if any surviving grant for this command is `PREFIX` (research.md D4); `EXACT` only if every surviving grant for this command is `EXACT`. |
| `rendered_text` | string | `` `command` `` for `PREFIX`; `` `command` (exact command only) `` for `EXACT`. |

### ToolingStatement (the output, `shell-commands`)

The final value emitted via `$GITHUB_OUTPUT` and appended to
`$GITHUB_STEP_SUMMARY` (research.md D7). One per `wing-commander-tool-args`
invocation (i.e. per internal agent step, on a multi-step stage).

| Field | Type | Notes |
|---|---|---|
| `case` | StatementCase | Selects the sentence template. |
| `entries` | list\<CommandStatementEntry\> | Populated for `ENUMERATED` (the permitted commands) and `UNRESTRICTED_EXCEPT` (the excepted commands); empty for `EMPTY`/`UNRESTRICTED`. |
| `text` | string | The complete, grammatical sentence (research.md D5's four templates), always ending in a terminal period, never dangling punctuation or an empty enumeration (FR-008). This is the literal value of the `shell-commands` output. |

**Invariant**: `text` is derived solely from `effective_allowed` and
`effective_disallowed` (spec 026's existing, unmodified computation) — never
written back to them, and byte-identical run over run for byte-identical
composed lists (FR-003, SC-003).

### DeclaredOutput (per output the composite documents)

One row of `tool-composition-action.md`'s Outputs table — the "published
contract" User Story 3/FR-011 requires. Existing entries (`allowed-tools`,
`disallowed-tools`) already conform; `shell-commands`'s row is corrected by
this feature (research.md D10) to describe the fixed render rather than the
"caveats as shipped."

| Field | Type | Notes |
|---|---|---|
| `name` | string | Output key, matches an `action.yml` `outputs:` entry. |
| `description` | string | What the output contains and what is guaranteed about it (FR-011). |

### EmittedOutput (derived, per output the shipped `run:` block actually writes)

Parsed from the `echo "<name>=<value>" >> "$GITHUB_OUTPUT"` lines in the
composite's shipped script (the same extraction research.md D8/D9 both use).

| Field | Type | Notes |
|---|---|---|
| `name` | string | Output key as written to `$GITHUB_OUTPUT`. |

**Contract-agreement invariant (FR-012, User Story 3 Acceptance 3-4)**: the
set of `DeclaredOutput.name` (from both `action.yml`'s `outputs:` block and
`tool-composition-action.md`'s table) and the set of `EmittedOutput.name`
are identical, in both directions. A name in one set but not the other fails
the new check (research.md D9) and is named in its failure message.

## Relationships

```
EffectiveToolSet (spec 026, unmodified)
        │  allowed, disallowed lists
        ▼
ShellGrant[] (D1 classify) ──┐
        │                    │ same-command lookup
        ▼                    │
CoverageResult[] (D2 subtract, using disallowed ShellGrant[]) ◀┘
        │  survives == true
        ▼
CommandStatementEntry[] (D4 broaden + dedupe by command)
        │
        ▼
StatementCase (D3/D5 select template)
        │
        ▼
ToolingStatement.text  ──▶ $GITHUB_OUTPUT (shell-commands)
                       ──▶ $GITHUB_STEP_SUMMARY (D7, US5)
                       ──▶ implement.yml prompt (D6, both cycle and retry)

action.yml outputs: block ──┐
                             ├──▶ contract-agreement check (D9) ──▶ pass/fail
tool-composition-action.md ─┤
     Outputs table          │
                             │
shipped run: block's        │
$GITHUB_OUTPUT writes ──────┘
```

## State / lifecycle

No persistent state — `ToolingStatement` is recomputed once per job run per
internal agent step, purely from that run's `workflow_call` inputs (via
spec 026's `EffectiveToolSet`), exactly like the lists it is derived from.
Nothing is written back to `spec-meta.json` or any other persisted artifact;
its only two destinations are the run's own transient outputs
(`$GITHUB_OUTPUT`, `$GITHUB_STEP_SUMMARY`) and the prompt text sent to the
agent for that run.

`DeclaredOutput`/`EmittedOutput` agreement is checked once per CI run of
`lint-workflows.yml` (research.md D9), not per pipeline stage run — it is a
repository-development-time gate, not a runtime computation.
