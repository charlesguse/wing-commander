# Contract: Spin-Off Routing (FR-006, FR-007, FR-008, FR-011, FR-012)

Covers every route that produces an artifact **outside** the current PR.
Every route in this document ends the same way: an `OutstandingTaskItem`
posted to the lifecycle issue (FR-008/FR-013), via the existing
`wing-commander-callout` composite (`kind: action`, `pr-url` pointing at
the new artifact) — never optional, never left to the agent's own
discretion to remember.

## `new-functionality` (FR-006, research.md D7)

`RequestClassification.fold-target` decides the route:

- **`current-spec`**: no new artifact. `pr-conversation.act` posts a PR
  reply summarizing how the request extends the current spec
  (`drafted-content.spec-amendment-note`) and — since this is
  conceptually the same "extend the work already in progress" shape as an
  in-scope change — routes the actual work through the identical
  `converge-fold-in.md` mechanism (the amendment becomes a
  `## Maintainer Feedback` task section, same as any in-scope change).
  Recorded on the PR only; **not** an outstanding task item, since nothing
  was created outside the PR (FR-013's "implementation-detail discussion
  stays on the PR" — extending the current spec's own scope is not
  "larger than the PR").
- **`new-spec`**: `pr-conversation.act` opens a new GitHub issue
  (`drafted-content.issue-title`/`.issue-body`) and applies the
  `spec-request` label (research.md D7) — the same label
  `wing-commander-1-intake.yml` already gates its own trigger on, so intake
  picks the new issue up with no new entry point. This **is** a
  `SpinOffArtifact` (`kind: new-lifecycle-issue`) — outstanding task item
  required.

## `small-unrelated-change` (FR-007, research.md D8)

1. Measure `drafted-content.file-changes` (files touched, lines changed)
   against a hardcoded threshold — proposed default: **≤ 3 files, ≤ 40
   changed lines** (documented here as the contract's normative default;
   an implementation-stage task may tune the exact numbers, but the
   *existence* of a deterministic ceiling, not agent judgment alone, is
   the contract).
2. **Within threshold**: open a PR to the default branch
   (`drafted-content.pr-title`/`.pr-body`, the diff itself), independent
   of `spec/<slug>` (branches from the default branch, not from the spec
   branch — this change has nothing to do with the in-flight spec).
   `SpinOffArtifact` (`kind: small-unrelated-pr`) — outstanding task item
   required, plus a reference on the *current* PR (FR-007: "reference that
   PR from both the current PR and the current lifecycle issue").
3. **Exceeds threshold**: re-route as `new-functionality` /
   `fold-target: new-spec` instead (edge case: "an unrelated tiny change
   turns out not to be tiny once examined") — never opened as a PR once
   the backstop trips, regardless of what the classify step judged.

## `manual-step-permission` (FR-011, FR-012, research.md D11)

Three sub-outcomes, chosen by `drafted-content`'s shape
(`contracts/classification-schema.md`):

- **Performed** (`{performed: true, outcome}`): the step described was
  something `pr-conversation.act`'s own tool allowlist already covers
  (e.g. a `gh` operation); executed, outcome reported on the PR. Not a
  spin-off artifact (nothing created outside the PR).
- **Cannot perform, no permission gap** (`{performed: false, reason}`):
  reported on the PR with the reason (FR-011's second clause). Not a
  spin-off artifact.
- **Needs a permission the stage lacks** (`{needs-permission, pr-title, pr-body}`):
  first, search `gh search prs --label permission-request --state all`
  for a `WithheldPermissionConversation` plausibly matching
  `needs-permission` (data-model.md). If `match-confidence == "confident"`:
  reply linking that prior conversation instead of opening anything new —
  **not** a new spin-off artifact (the existing conversation already is
  one, and is not re-recorded). Otherwise (`uncertain`/`none`, conservative
  bias — research.md D11): open a one-off permission-request PR to the
  default branch, labeled `permission-request` (created via `gh label
  create --force` on first use, same idiom every other stage's own labels
  already follow). `SpinOffArtifact` (`kind: permission-request-pr`) —
  outstanding task item required. The PR itself proposes only what git can
  express (a documentation/config diff describing the needed capability
  and why); an actual grant (e.g. a GitHub App permission scope) remains a
  human action outside git, exactly as "the bot never merges to `main`"
  already establishes for every other spin-off PR this stage opens.

## `push-back` (FR-010)

No artifact at all — a PR reply naming
`RequestClassification.constitution-conflict` and declining. Never a
spin-off (nothing is created); never folded into converge (the request is
not honored, not deferred).

## Outstanding task item format (FR-008, shared by every `SpinOffArtifact` above)

One `wing-commander-callout` (`kind: action`) on the lifecycle issue per
artifact, in the same "outstanding task" phrasing pattern the constitution
already asks every stage to use for a surviving manual step (constitution
IV: "Any manual step that survives must be reported explicitly to the
lifecycle issue, never silently assumed"):

```
- [ ] <artifact kind, human phrase> — <url> (from PR #<pr-number>)
```

Rendered as an unchecked list item so it visually persists as "still
outstanding" until a human closes the linked issue/PR — the lifecycle
issue's own body or a dedicated comment section accumulates these across
multiple PR-conversation cycles for the same spec (exact placement — a
running section appended to vs. one comment per artifact — is an
implementation-stage decision; either satisfies FR-008's "cannot be
ignored" as long as the item persists visibly rather than scrolling off in
a single ephemeral comment).
