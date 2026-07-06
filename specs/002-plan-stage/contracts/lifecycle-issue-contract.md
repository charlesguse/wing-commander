# Contract: Lifecycle issue effects of the plan stage

Downstream stages and human observers can rely on the following after this
stage runs, regardless of whether the specification originated from an issue
(stage 1) or was hand-submitted:

## Labels

- `spec:NNN-slug` exists and is attached (created here only if the spec had
  no lifecycle issue yet, FR-007; otherwise inherited from stage 1).
- `stage:plan` is attached once the plan PR is verified to exist (FR-006).
- Any prior `stage:spec` / `stage:clarify` label is removed (best-effort;
  absence of the label is not an error).
- On a stalled outcome: `stage:stalled` replaces `stage:plan`.

## Comments

Exactly one comment is posted by this stage per successful planning attempt:
a short summary of the technical approach plus a link to the plan PR
(FR-006). Exactly one additional comment is posted only in the stalled path,
explaining that planning did not complete and how to restart it manually
(FR-012).

## What downstream stages may assume

- If `stage:plan` is present, a plan PR exists (head `plan/NNN-slug`) either
  open or already merged — the stage never applies the label speculatively.
- If `stage:stalled` is present, no plan PR is currently open for this spec,
  and `plan/NNN-slug` must be deleted before planning can restart.
- The lifecycle issue number for any specification the plan stage has
  touched is always resolvable from `specs/NNN-slug/spec-meta.json`'s
  `issue` field — never only from the issue's own labels.
