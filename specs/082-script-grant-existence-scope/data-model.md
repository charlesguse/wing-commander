# Data Model: Every Granted Script Is Checked, Not Just The `.specify` Ones At Composite Call Sites

This feature has no runtime data store — its "entities" are the workflow
structures the check reads and the one JSON file it reads and cross-checks.
This document names each one's shape, where it lives, and what keeps it
honest, so tasks.md can be written against fixed structures rather than
re-deriving them from the spec's Key Entities prose.

## 1. Grant (existing entity, generalized)

One `--allowedTools`/`default-allowed-tools`/`extra-allowed-tools` entry
shaped `Bash(<optional interpreter+flags> <command-or-path><optional trailing
argument>:*)`, e.g. `Bash(python3 -I .wing-commander-pipeline/.github/scripts/git_read.py:*)`.

| Field | Value |
|---|---|
| Interpreter prefix | Optional: `bash`, `sh`, `python`, `python3`, each optionally followed by zero or more `-flag` tokens (research.md D1) |
| Path prefix | Optional leading `./` |
| Token | The command or path proper — what remains after the above two are stripped |
| Trailing argument | Optional, e.g. ` --json` before the wildcard |
| Classification | **path** (leading `./` or contains `/`) or **bare command** (neither) — research.md D1, FR-003 |
| Expression check | If the *raw, unstripped* grant string contains `${{`, the grant is skipped before classification (research.md D5, FR-008) |

**Checked by**: the widened `check_script_grants`-equivalent function in Gate
27, for every path-classified, non-expression grant found at any of the three
surfaces below.

## 2. Grant site (existing entity, extended with two new shapes)

Where a grant's literal text is written. Three shapes, per FR-004:

| Surface | Identity (research.md D3) | Has `step-label`? | Collector |
|---|---|---|---|
| `wing-commander-tool-args` composite call | `step-label` | Yes | `collect_sites` (existing, unchanged) |
| Reusable-workflow caller | `<workflow file>:<job> (<extra-allowed-tools\|allowed-tools-override>)` | No | new collector (research.md D2) |
| Bare `claude-code-action` `claude_args` | `<workflow file>:<job>:<step name>` | No | new collector (research.md D2) |

A `Bash(<path>)` grant written anywhere else under `.github/workflows/` is
not a grant site this feature recognizes (FR-004's closing sentence) — the
three collectors above are exhaustive for this feature's scope.

**Checked by**: a shared `_load_workflows(root)` loader (research.md D2)
feeds all three collectors from one glob-and-parse pass, catching
`yaml.YAMLError` per file (research.md D6, FR-009) rather than letting one
malformed workflow abort collection for every other file.

## 3. Absent-by-design record / waiver file (new entity)

`.github/scripts/script-grant-waivers.json` — new file, alongside (not
merged into) the repository's existing `single-home-waivers.json`/
`stage-invariant-waivers.json`/`spec-branch-push-waivers.json`, because its
schema is deliberately different (research.md D4): those three are
pattern+count-shaped; this one is exact-path-shaped, per FR-006's explicit
rejection of a prefix/pattern/glob/constant substitute.

| Field | Type | Meaning |
|---|---|---|
| `path` | string | The exact granted path, already stripped of any interpreter prefix and leading `./` — the same string the check would otherwise try to resolve |
| `issue` | string | The tracking issue for why this path is expected to be absent |
| `reason` | string | Human-readable explanation of why the path cannot exist in a checkout |

**Shipped contents** (research.md D0): exactly two entries —
`.wing-commander-pipeline/.github/scripts/git_read.py` and
`e2e-scratch/.specify/scripts/bash/create-new-feature.sh`.

**Checked by**:
- Forward direction (FR-006): a grant's classified path not found on disk is
  looked up in this file's path set before being reported as a failure.
- Reverse direction (FR-007): every entry's `path` is independently checked
  against the tree; one that *does* resolve is reported as a staleness
  failure, so the record cannot outlive its reason.

## 4. Per-stage default tool list / documented table row (existing entity, unaffected)

Unchanged from specs/010/026/051: Gate 27's existing comparison between
`wing-commander-tool-args` call sites and `stage-interfaces.md`'s table rows.
Per the spec's own Assumptions, this feature does not add rows to that table
for the two new surfaces — they are not part of the composite's published
default-list contract, so nothing here changes shape or size.

**Checked by**: `compare()`, `check_inspection_set()`, `check_mandated_commands()`
— all three unchanged by this feature.

## 5. Self-test mutation (existing entity, extended)

Gate 27's `_mutations()`/`_collector_fixtures()`/inline mutation blocks in
`self_test()`. This feature adds six new mutation-style assertions (research.md
D9), each following the file's existing shape: a synthetic or in-memory-
mutated input, a call to the function under test, and an assertion that the
returned failure list contains exactly the expected substring (or, for the
two "raises nothing" cases, is empty).

| New mutation | Exercises |
|---|---|
| Non-`.specify` missing script at a composite site | Generalized classifier + composite surface (unchanged collector) |
| Missing script via reusable-workflow-caller fixture | New collector 2 |
| Missing script via bare-`claude_args` fixture | New collector 3 |
| Bare command grant | Classifier's "no `/`, no `./`" branch |
| Expression-valued grant | D5's raw-string `${{` check, ahead of classification |
| Stale waiver entry | D4's reverse-direction waiver check |

**Checked by**: `--self-test`'s own exit code (0 only if every mutation is
caught for the expected reason, per the file's existing `bad` counter
convention).
