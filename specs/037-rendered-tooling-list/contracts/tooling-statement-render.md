# Contract: The `shell-commands` Render (implementer-facing)

**Feature**: 037-rendered-tooling-list

Corrects and completes the `shell-commands` output contract of
`wing-commander-tool-args` first declared (retroactively, with known
caveats) by #214. At implementation time this document's content replaces
the "Caveats as shipped" block in
`specs/026-configurable-tool-lists/contracts/tool-composition-action.md`
(research.md D10) — it is drafted here, under this feature's own spec
directory, per this plan stage's file-scope constraint.

This is the *implementer-facing* contract for the render algorithm inside
the composite action's shipped shell step, analogous to how
`tool-composition-action.md` is the implementer-facing contract for
composition itself (consumers see `tool-list-inputs.md` and
`stage-interfaces.md` only — see `stage-interfaces.md`'s "What the agent is
*told*" paragraph, updated by the same D10 pass, for the consumer view).

## Inputs to the render

The render step runs *after* spec 026's existing composition (unchanged —
Out of Scope: "Changing how tool lists are composed") and reads only its two
existing outputs:

| Input | Source |
|---|---|
| `effective_allowed` | Already computed, deduplicated, comma-joined — spec 026 D4. |
| `effective_disallowed` | Already computed, deduplicated, comma-joined, already subtracted for `explicit_allow` per spec 026 D4 — that subtraction is unrelated to and independent of this render. |

The render never re-parses `default-*`/`extra-*`/`*-override` inputs
directly, and never mutates `effective_allowed`/`effective_disallowed` —
FR-003's "producing the statement MUST NOT alter the enforced... lists"
holds because the render is a pure read of already-final values.

## Classification (data-model.md `ShellGrant`, research.md D1)

Split each of `effective_allowed`/`effective_disallowed` on `,`, trim, and
classify each entry:

| Entry shape | Form | Command |
|---|---|---|
| `Bash` (bare) | `ANY` | — |
| `Bash(<cmd>:*)` or `Bash(<cmd> *)` | `PREFIX` | `<cmd>`, trimmed |
| `Bash(<cmd>)` (no trailing `:*`/` *`) | `EXACT` | `<cmd>`, trimmed |
| anything else | `NOT_SHELL` | — (excluded from every later step; FR-010) |

## Coverage / subtraction (research.md D2)

For each `ANY`/`PREFIX`/`EXACT` allow grant, find whether any disallowed
grant for the same command (or, for an `ANY` allow, any disallowed grant at
all) *covers* it:

| deny → \ allow ↓ | `EXACT(cmd)` | `PREFIX(cmd)` | `ANY` |
|---|---|---|---|
| `ANY` | covers | covers | covers |
| `PREFIX(cmd)` | covers | covers | does not cover alone |
| `EXACT(cmd)` | covers | does **not** cover | does not cover |

- A covered allow grant is dropped from the statement (not from
  `effective_allowed` — that list is untouched).
- An `ANY` allow grant is covered only by a disallowed `ANY`. A disallowed
  `PREFIX(cmd)`/`EXACT(cmd)` under an `ANY` allow does not cover the whole
  grant; instead it becomes an **exception** (research.md D3) — the command
  is named as denied even though the general grant is unrestricted.
- A deny naming a command absent from the allow side matches nothing and is
  silently ignored (edge case — not an error).

## Broadening and dedup (research.md D4)

Group surviving `PREFIX`/`EXACT` allow grants by command. A command with any
surviving `PREFIX` grant renders as `PREFIX` (bare command text); a command
with only `EXACT` grant(s) surviving renders as `EXACT` (with the
qualifier below). Each command appears exactly once in the rendered output
regardless of how many surviving grants named it (FR-007).

## Rendering (research.md D5) — four complete-sentence templates

Let `entries` be the surviving, broadened, deduplicated commands in
first-seen order (matching `effective_allowed`'s own order), each rendered
as `` `cmd` `` (`PREFIX`) or `` `cmd` (exact command only) `` (`EXACT`), and
let `exceptions` be the surviving-as-exception commands under an `ANY` allow
(same rendering rule, joined the same way).

| Case | Condition | `shell-commands` value |
|---|---|---|
| `EMPTY` | No surviving `ANY`, `PREFIX`, or `EXACT` allow grant | `This run permits no shell command.` |
| `UNRESTRICTED` | Surviving `ANY` allow grant, `exceptions` is empty | `This run permits any shell command.` |
| `UNRESTRICTED_EXCEPT` | Surviving `ANY` allow grant, `exceptions` non-empty | `This run permits any shell command except: ` + `exceptions` joined by `, ` + `.` |
| `ENUMERATED` | One or more surviving `PREFIX`/`EXACT` grants, no surviving `ANY` | `This run permits these shell commands: ` + `entries` joined by `, ` + `.` |

Every value is a single, complete, grammatical sentence ending in a period —
no case produces a bare list, a trailing connective, or an empty
enumeration (FR-008). The value never mentions `NOT_SHELL` (non-shell) tool
entries, and is never phrased as a statement about the agent's *total*
toolset — only about shell commands specifically (FR-010; edge case: "a
configuration that permits no shell commands but permits other tools" must
not read as "the agent has no tools").

## Recoverability from the run's own record (research.md D7)

The same step that computes `shell-commands` appends its literal value to
`$GITHUB_STEP_SUMMARY`, e.g.:

```
**Tooling statement**: This run permits these shell commands: `git status`, `git add`.
```

This is in addition to, not instead of, the existing
`✅ wing-commander-tool-args (<step-label>): composed tool lists.` line.

## Guarantees for consumers

- **SC-001**: for every legal configuration, the commands named are exactly
  the commands the run permits — zero denied commands named, zero permitted
  commands omitted except `NOT_SHELL` entries (which the statement is not
  about) and the documented format limit (a command containing the literal
  `,` separator, unrepresentable in the existing list syntax — inherited,
  not introduced, per Out of Scope).
- **SC-002**: the value is a complete, grammatical sentence for 100% of
  legal configurations, including the empty case.
- **SC-003**: a run with no consumer tool-list configuration renders
  `ENUMERATED` over exactly that step's hard-coded defaults, and
  `effective_allowed`/`effective_disallowed` themselves are byte-identical
  to today's — this render is purely additive to those two existing
  outputs.
- **Callers must not read `shell-commands` as the enforced set.**
  `allowed-tools` and `disallowed-tools` remain the sole enforcement
  surface; this output is prose derived from both of them, after the fact,
  and never the other way around.

## Self-verification (research.md D8)

Every guarantee above is exercised by
`.github/scripts/verify-tooling-statement.py` against the shipped `run:`
block (not a copy), including a mutation-based self-test proving the check
itself fails when a guarantee is reverted (FR-014/FR-015). See
`contracts/contract-agreement-check.md` for the sibling check that keeps
this output *declared*, as distinct from *correctly rendered*.
