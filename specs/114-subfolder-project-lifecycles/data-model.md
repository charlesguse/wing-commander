# Data Model: Subfolder Project Lifecycles

No new storage. These are the entities the pipeline derives and the rules that bind them.

## Project

| Field | Rule |
|---|---|
| `path` (`P`) | Empty for the root. Otherwise `^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)*$`, ≤ 28 chars, no `specs` segment, no `^[0-9]{3}-` segment. |
| folder | Real directory on the ref, no symlinked ancestor. |
| `.specify/`, `.claude/` (with `skills/speckit-*`), constitution | Real entries, not symlinks. |
| `specs/` | Real entry when present. A new project's first lifecycle has none. |

Nesting: a project inside another is a distinct project. The enclosing project's `.claude/` is denied to the nested lifecycle's agents (FR-022).

## Routing label

`<routing-label-prefix><P>`, for example `node:ideas/alpha`. The prefix is shaped `^[a-z0-9][a-z0-9-]*:$`, must not overlap pipeline families or entry labels, and `len(prefix) + 28 ≤ 50`. Read only by intake, from live labels. The count decides the result.

| Count | Result |
|---|---|
| 0 | Root project |
| 1 | That project, after path validation |
| ≥ 2 | Refuse, callout on the lifecycle issue, create nothing |

## Lifecycle identity

The tuple `(P, NNN-slug)`. `NNN-slug` matches `^[0-9]{3}-[a-z0-9-]+$`. For a subfolder project, `len(NNN-slug) ≤ 44 − len(P)`.

| Carrier | Form (root form in parentheses) |
|---|---|
| spec-draft branch | `<spec-draft-prefix>P/<NNN-slug>` (`<prefix><NNN-slug>`) |
| spec branch | `<spec-prefix>P/<NNN-slug>` |
| implement branch | `<impl-prefix>P/<NNN-slug>-iterN` |
| label | `spec:P/<NNN-slug>` (`spec:<NNN-slug>`) |
| repository-relative spec dir | `P/specs/<NNN-slug>` (`specs/<NNN-slug>`) |
| project-qualified slug | `P/<NNN-slug>`: plan→tasks hand-off, plan and tasks restart `slug` |
| `spec_dir` input | `P/specs/<NNN-slug>`: implement, finalize and fold-cycle-guard restarts and hand-offs |
| per-spec concurrency group | `wing-commander-<repository-relative spec dir>` |
| intake concurrency groups | `wing-commander-intake` or `wing-commander-intake/P`, plus `wing-commander-intake-issue/<N>` when routing is on |

## spec-meta.json (unchanged schema)

`spec_dir` = project-relative `specs/<NNN-slug>`, never carrying `P` (FR-008). `spec_branch` = real branch name, a historical pointer that may stop resolving. Other fields unchanged, including `stage`, `issue` and `spec_branch`.

Validity: located at `P/specs/<NNN-slug>/spec-meta.json`, valid only if `spec_dir == specs/<NNN-slug>` for that same `<NNN-slug>`. A copy-out to a repository root keeps the file valid with no edits.

## Parser outputs

`project-name.sh parse <kind> <name>` prints `project=<P>` and `slug=<NNN-slug>`, or exits non-zero with a reason. Kinds are `branch`, `label`, `slug` and `spec-dir`.

## Numbering

`next(P) = 1 + max(NNN)` over:

- directories `P/specs/NNN-*`, and
- refs exactly matching `refs/heads/<spec-draft-or-spec-prefix>P/NNN-*`. For the root, only refs with no `/` after the prefix.

The empty set gives `001`.

## Containment sets (derived from P)

- Deny Edit/Write: `.claude/`, `.git/`, `E/.claude/` for every proper ancestor `E` of `P`, `P/.claude/`, `P/**/.claude/`.
- Allow-confinement (post-agent diff): every changed path starts with `P/`.
- Runner-temp: outside the checkout, never in the diff.
