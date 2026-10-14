# Contract: Project path, names and the shared parser

Live contract: gates read it and it is fixed like code.

## Grammar (FR-002)

```
project-path = segment *( "/" segment )
segment      = ALNUM_LC *( ALNUM_LC / "-" )     ; ^[a-z0-9][a-z0-9-]*$
```

Additional rejects: a segment equal to `specs`, a segment matching `^[0-9]{3}-`, total length over 28, absolute paths, `..`, empty segments, uppercase, spaces. No normalisation is performed.

Filesystem rules (checked on the ref the stage works from): the folder is a real directory with no symlinked ancestor. `.specify/`, `.claude/`, `.claude/skills/speckit-*`, `specs/` (if present) and `.specify/memory/constitution.md` are real entries.

## Name forms (FR-011)

| Kind | Root | Subfolder `P` |
|---|---|---|
| branch (spec-draft or spec) | `<prefix><NNN-slug>` | `<prefix>P/<NNN-slug>` |
| implement branch | `<impl-prefix><NNN-slug>-iterN` | `<impl-prefix>P/<NNN-slug>-iterN` |
| label | `spec:<NNN-slug>` | `spec:P/<NNN-slug>` |
| slug | `<NNN-slug>` | `P/<NNN-slug>` |
| spec-dir (repository-relative) | `specs/<NNN-slug>` | `P/specs/<NNN-slug>` |
| spec-dir (project-relative) | `specs/<NNN-slug>` | `specs/<NNN-slug>` |

The label budget: `len("spec:") + len(P) + 1 + len(NNN-slug) ≤ 50`, so `len(NNN-slug) ≤ 44 − len(P)`. Root has no budget check.

## `_shared/project-name.sh` interface

| Subcommand | Input | Output (stdout) | Exit |
|---|---|---|---|
| `validate-path <P>` | candidate path | `project=<P>` | 0 valid; 1 invalid, reason on stderr |
| `check-folder <P>` | validated path | nothing | 0; 1 with the folder and missing piece named |
| `parse <kind> <name>` | `branch`, `label`, `slug` or `spec-dir` plus a name | `project=<P>` and `slug=<NNN-slug>` | 0; 1 on malformed |
| `spec-dir <P> <NNN-slug>` | | `P/specs/<NNN-slug>` | 0 |
| `slug-budget <P>` | | integer | 0 |
| `next-number <P>` | env `SPEC_DRAFT_PREFIX`, `SPEC_PREFIX` | zero-padded number | 0 |
| `validate-prefix <prefix>` | routing prefix | nothing | 0; 1 with the overlapping family named |

Rules: the parser strips the flat prefix first, strips `-iterN`, takes the last segment as `NNN-slug`, and the remainder is `P`. For `slug` and `spec-dir` kinds, the same `(P, NNN-slug)` results as for the matching branch and label.

## Composite `wing-commander-project`

Inputs: `routing-label-prefix`, `issue-number` (intake), or `identity` (later stages: any branch, label, slug or spec-dir). Outputs:

| Output | Meaning |
|---|---|
| `project` | `P`, empty for root |
| `slug` | `NNN-slug` (when known) |
| `spec-dir` | repository-relative |
| `spec-dir-rel` | project-relative |
| `slug-qualified` | `P/<NNN-slug>` |
| `slug-budget` | integer, empty for root |

Failure produces a callout on the lifecycle issue naming the folder and the problem.
