# Data Model: spec 130

## Explanation (first comment)
Parts, in order: `line`, `code`, `issue`, `why_it_matters`, `options`,
`what_this_pr_does`. Each part is `{state: "filled"|"gap", text: str}`.
- `line`: verbatim backlog line, or issue title + `#N` (FR-001a). Fenced.
- `options`: alternatives, or the literal state `follow` ("options follow").
- Gap text names what is missing and why (FR-003a). A part is never absent.
- Attached to one backlog line / issue and one fix PR.

## Review report (review comment)
Parts: `asked`, `checked`, `decided`, `not_decided`, `open`. Same part shape.
- Maps onto spec 127's record: asked <- purpose source; checked/decided/not_decided
  <- purpose answers; open <- open findings (FR-008a).
- Also carries `identifier` (`bl-...` or `#N`), required in the rendered comment (FR-006).

## Fixed-text message (registry entry)
`id`, `source` (file), `variants[]` each with `when`
(`auto_merge` bool, `kill_switch` bool, `pr_class`), `text`, and
`claims[]` (next-action and protection claims) checked against `when`.

## Rendering rules
Lead section = labelled parts, fits one screen; overflow evidence in `<details>`
(FR-018). Total body stays under the existing 57000 UTF-16 budget.

## State
No persisted state beyond comments and the ticked backlog line's one-line record.
