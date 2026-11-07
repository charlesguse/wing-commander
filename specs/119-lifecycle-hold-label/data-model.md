# Data Model: Lifecycle Hold Label

No new persisted state (FR-018). The label is the only hold state.

## Lifecycle hold
- Representation: label `lifecycle:held` (configurable) on the lifecycle issue.
- Read result `HoldState` = `clear | held | unreadable` (`unreadable` is
  treated as held, reported distinctly).
- Transitions: `clear → held` (set: analyze decide, strict stop, by hand);
  `held → clear` (maintainer removes label only). `set` on `held` is a no-op
  that still posts its reason.

## Fold-analyze input (`fold-input.json`, built by deterministic code)
| Field | Meaning |
|---|---|
| `fold_base_sha`, `fold_head_sha` | Range of the fold's own commits |
| `added_tasks[]` | `{id, line}` from tasks.md diff over that range only; `id` = the fold title line |
| `spec_md` | spec.md text on the lifecycle branch |
| `constitution` | constitution.md text from the default branch |
| `principles[]` | Principle headings extracted from the constitution |

## Fold-analyze verdict (agent output, JSON schema)
```
{ "objections": [ { "task": string, "constitution_conflict": boolean,
                    "principle": string|null, "reasoning": string } ] }
```
Decide result: `{ hold: bool, held_items[], recorded_items[], status:
ok|agent-failed|malformed }`. `hold` only if `constitution_conflict`, the
principle is in `principles[]`, and `task` is in `added_tasks[]`.

## Drop command (parsed from a maintainer comment)
`{ comment_id, titles[] }` — titles are exact fold title lines. Outcomes per
title: `removed | unknown | not-fold-task | already-checked | already-absent`;
whole comment `non-maintainer` if the author check fails.

## Drop commit
Single commit touching only tasks.md; trailers `Wing-Commander-Drop:
<comment-id>` and the removed titles. Verified at derivation time against the
comment (see research D8).

## Dismissed fingerprint (derived, not stored)
`dismissed = { fp | every unchecked fold task whose title maps to fp has been
removed by a verified drop commit }`; tasks checked off, reworded or removed
by other commits never count.

## Release plan (label-removed trigger output)
`{ due: bool, reason, spec_dir, issue, iteration }`; due iff issue open, not
parked, not `stage:stalled`, spec branch exists, spec-meta stage in
`tasks | implement`.
