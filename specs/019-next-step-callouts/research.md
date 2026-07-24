# Phase 0 Research: Clear Next-Step Callouts in the Lifecycle Issue

`spec.md` has no `[NEEDS CLARIFICATION]` markers. The decisions below are
implementation-level choices the spec deliberately leaves open (its
Assumptions section explicitly defers "the distinction... is conveyed by
human-visible convention in comment content" without naming the convention,
and defers whether a new shared code path is introduced) that this plan must
pin down before `tasks.md` can be generated. None of these required a
clarification round with the requester — each follows directly from FR-004,
FR-011, FR-012, and constitution III/IV — but they are genuine judgment
calls, so each is called out in the "Decisions made without clarification"
section of the plan-completion issue comment.

## Current-state findings (grounding for every decision below)

A full audit of every comment-posting site in `.github/workflows/*.yml`
found:

- **No shared comment-posting helper exists.** Every `gh issue comment` call
  is inlined per-workflow, either as a deterministic bash step or as an
  instruction inside a Claude agent prompt (`intake.yml`'s "ready for
  review"/clarification comment, `clarify.yml`'s restatement comment).
- **The only per-stage differentiator today is an icon prefix**
  (📝/📐/📋/🏗️/🐕/✅/⚠️/❌/⏸️/🔁/🚫), which signals *which stage* posted, never
  *whether the reader must act* — undocumented anywhere, and already
  inconsistent stage-to-stage (confirmed: no doc defines an action-required
  vs informational taxonomy today).
- **The implementation/finalize-phase PR is opened with zero issue comment
  announcing it** (`finalize.yml`, "Open the final pull request" step) — the
  only issue-facing signal is the `stage:review` label and a
  remaining-manual-work comment that never mentions the PR. This is the
  confirmed root cause of User Story 1's core gap.
- **The spec-phase "ready for review" comment is freeform agent text**
  (`intake.yml` step 7: "post a comment linking the PR and stating the spec
  is ready for review") — no enforced heading or convention, so its
  wording/shape can drift run to run.
- **The clarification-needed comment has an enforced heading on first post**
  (`intake.yml`: `"## 🔍 Clarification needed"`) **but not on restatement**
  (`clarify.yml` step 6's "still-open questions" restatement has no required
  heading) — an existing inconsistency this feature should also close.
- **Remaining-manual-work is posted byte-for-byte identical to the PR body's
  list**, with no "this is a human to-do" framing and no timing annotation
  anywhere — confirmed gap for User Story 3 / FR-006 / FR-007.
- **Only `implement.yml` has a retry-loop stall state** (its "Report stalled
  on lifecycle issue" step, the richest existing pattern: banner + reason +
  collapsible agent transcript + a full restart runbook). `plan.yml` and
  `tasks.yml` are single-shot agent stages with no equivalent stall state.
  `finalize.yml` has two flat one-line failure comments (⚠️ anomaly, ❌
  failed). `rebase.yml` has a blocked-escalation comment with its own HTML
  dedup marker (`<!-- wing-commander-rebase: blocked ... -->`). `cleanup.yml`
  has a "draft rejected, resubmit when ready" comment that is functionally
  an action-required moment (the requester must decide whether to
  resubmit) even though it isn't a failure.

## Decision: One new shared composite action, `wing-commander-callout`, is the single implementation of the action-required/informational convention

**Decision**: Add `.github/actions/wing-commander-callout/action.yml`,
following the same self-checkout composite-action pattern already
established by `wing-commander-context` and `wing-commander-preflight`
(`.wing-commander-pipeline` checkout, referenced by every stage via
`uses: ./.wing-commander-pipeline/.github/actions/wing-commander-callout`).
It takes a `kind` (`action` | `info`), an `issue-number`, a `summary` line, an
optional `body` (a file path or literal markdown), an optional `pr-url` +
`pr-label`, and an optional `timing` string, and posts exactly one comment in
the fixed envelope defined in `contracts/callout-format.md`.

**Rationale**: FR-004/FR-011 require the convention to be "consistent...
across every human-action moment the pipeline can reach" and "learnable once
and trusted thereafter." The current-state findings show the icon convention
that exists today drifted specifically *because* it was reimplemented inline
in each of ~8 workflow files with no shared source of truth. A single
composite action is the only way to guarantee SC-003 ("no ambiguous cases")
holds for every future stage too, not just the ones touched by this feature —
matching the precedent `wing-commander-preflight` already set for
deterministic, reusable, cross-stage behavior (research for specs 014/017/018
all reused it rather than duplicating a check).

**Alternatives considered**:
- *Leave posting inline per-workflow, but document a convention in prose
  (e.g. in `docs/architecture.md`) that each stage's bash/prompt must
  follow.* Rejected — this is exactly the status quo for the icon
  convention, and it has already drifted (clarify.yml's restatement comment
  lacks the heading intake.yml's first post requires). A convention with no
  single enforcement point cannot guarantee SC-003.
- *A shared bash script (`.specify/scripts/bash/post-callout.sh`) invoked via
  `run:` instead of a composite action.* Rejected — this repo's shared,
  cross-stage, deterministic logic already lives in `.github/actions/*`
  composites (not `.specify/scripts/bash`, which is spec-kit's own generic
  tooling per constitution VI); a script would need duplicated
  `source`/`chmod` boilerplate in every stage where a composite `uses:` step
  is already the established idiom.

## Decision: The visual convention is GitHub's native Markdown alert syntax — `[!IMPORTANT]` for action-required, plain text for informational

**Decision**: An action-required callout's body is wrapped in a GitHub
Alert block:

```markdown
> [!IMPORTANT]
> **Action needed: <summary>**
>
> <body...>
>
> 👉 **PR:** <pr-url> (<pr-label>)
> **When:** <timing>
```

(The `PR:` and `When:` lines are omitted when no `pr-url`/`timing` is given,
per FR-008.) An informational message is posted as plain markdown text with
no alert wrapper — it keeps whatever per-stage icon/heading it already uses
(FR-005 only requires it not *claim* action, which none of the existing
informational messages do).

**Rationale**: GitHub renders `[!IMPORTANT]` (and the four other alert
types) as a distinctly colored, boxed callout in both issue comments and PR
bodies, on every GitHub surface (web, mobile, API-rendered markdown) with
zero custom tooling — this is the single strongest option for SC-002 ("can
correctly identify... in under 15 seconds") because the reader doesn't have
to *read* the convention to notice it, they see a colored box. It is also
the most direct application of constitution III (GitHub-native interaction,
no external dashboard): the "dashboard" the reader needs is a rendering
feature GitHub already ships. Because only the action-required path gets the
alert box, "informational vs action-required" becomes a single binary visual
signal (boxed vs not-boxed) layered on top of, not replacing, today's
per-stage icon identity — so this feature does not need to touch the ~15
existing purely-informational comment sites to satisfy FR-004/FR-005.

**Alternatives considered**:
- *A custom heading convention* (e.g. `## 🔴 ACTION NEEDED` vs `## ℹ️ FYI`).
  Rejected — text headings are exactly what the existing, already-drifted
  icon convention already tried, and a heading is easy to skim past in a
  busy issue; GitHub's native alert box cannot be skimmed past.
- *A dedicated label per action-required comment* (e.g. `needs-human`).
  Rejected — FR-010 explicitly forbids relying on a label as the mechanism
  that makes the next step legible; a label may exist as a complement
  (existing `stage:review`/`stage:stalled` stay), but the comment itself
  must carry the meaning.
- *HTML comment markers for every callout* (mirroring `rebase.yml`'s
  existing `<!-- wing-commander-rebase: blocked ... -->` dedup marker).
  Rejected as the *general* mechanism — FR-012 already resolves the
  "which callout is current" question by being append-only (most recent
  wins), so no dedup marker is needed for that purpose. `rebase.yml` keeps
  its existing marker for its own, unrelated purpose (skip-if-unchanged
  dedup across watchdog-triggered re-runs), which the new composite action
  passes through untouched in `body`.

## Decision: The composite action owns the envelope; agents keep authoring freeform body content, but a deterministic step always decides `kind` and posts

**Decision**: Wherever a callout's body content is naturally freeform
(clarification questions, the remaining-manual-work list, a change
narrative), the agent step keeps writing that content to a temp file exactly
as `finalize.yml`'s "Summarize change and extract remaining manual work"
step already does today — no change to what the agent decides or how it's
prompted for *content*. A new deterministic bash step immediately after
reads that file, decides `kind` from a simple, non-agent-judged condition
(does `spec.md` still contain `[NEEDS CLARIFICATION]`? is
`finalize-remaining.md` non-empty? did `gh pr create` succeed?), and invokes
`wing-commander-callout`. No agent step gains `gh issue comment` in its
`--allowedTools` for any of the five FR-011 moments after this feature ships
where a deterministic condition is available; agents keep that tool only for
comments outside FR-011's scope (e.g. intake's "could not produce a spec"
early-exit, clarify's "reply doesn't answer the question" early-exit).

**Rationale**: The current-state findings show today's inconsistency (the
enforced-heading-on-first-post-but-not-restatement gap, the fully freeform
"ready for review" wording) stems precisely from leaving the choice of
envelope to agent judgment inside a prompt instruction. SC-003 requires zero
ambiguous cases on *every* run, not most — only a deterministic step can
guarantee that, since an LLM's exact phrasing is not literally deterministic
run to run even with a strongly-worded prompt. This mirrors
`finalize.yml`'s own existing split (agent decides remaining-work *content*,
deterministic step decides how to post it) and simply extends that already-
validated pattern to the two comments that don't yet have it
(`intake.yml`'s ready-for-review/clarification comment, `clarify.yml`'s
restatement).

**Alternatives considered**: Keep comments agent-posted but add a strongly
worded prompt instruction naming the exact required heading string.
Rejected — this is what `intake.yml` already does for the clarification
heading, and `clarify.yml`'s restatement (a near-identical prompt written
later) already shows the drift risk: a second prompt describing "the same"
convention in different words produced a different (weaker) requirement.
Prompt-level enforcement cannot give the same guarantee a shared code path
can.

## Decision: Map every FR-011 moment to a call site (scope of touched workflows)

**Decision**: Route these nine existing comment sites through
`wing-commander-callout`, per the full mapping in
`contracts/callout-points.md`:

| # | Site | Today | New `kind` |
|---|---|---|---|
| 1 | `intake.yml` spec PR ready | freeform agent text | `action`, pr-url=draft PR |
| 2 | `intake.yml` clarification needed | agent text, partial heading | `action`, no pr-url |
| 3 | `clarify.yml` still-open restatement | freeform agent text, no heading | `action`, no pr-url |
| 4 | `clarify.yml` spec ready after answers | freeform agent text | `action`, pr-url=draft PR (same template as #1) |
| 5 | `finalize.yml` final PR opened | **no comment at all** | `action`, pr-url=final PR — the core gap fix |
| 6 | `finalize.yml` remaining manual work (non-empty) | unlabeled task dump | `action`, timing="after this PR merges" |
| 6b | `finalize.yml` remaining manual work (empty) | `"No manual work remains."` | `info` |
| 7 | `finalize.yml` ⚠️/❌ anomaly/failure | flat one-liner | `action` |
| 8 | `implement.yml` stalled runbook | richest existing pattern, own ⏸️ icon | `action`, body = existing runbook content verbatim |
| 9 | `rebase.yml` blocked escalation | own icon, own dedup marker | `action`, body includes the existing dedup marker unchanged |
| 10 | `cleanup.yml` draft-rejected notice | 🚫, informational-shaped but functionally action | `action` (resubmit is the reader's choice, per spec Edge Cases "action already handled") |

**Rationale**: This is the literal enumeration of FR-011's "the two PR
review gates... residual manual work, clarification-needed prompts, and
failure/stall states requiring human intervention," grounded in the
current-state audit above — every row is either a confirmed missing callout
(row 5, User Story 1's core gap) or a confirmed inconsistent/unlabeled one.
`plan.yml`'s existing ⚠️ gate-mode-fallback comment and `watchdog.yml`'s
finding comments are deliberately **not** migrated by this feature (see next
decision) to keep scope bounded to what `spec.md` actually describes.

**Alternatives considered**: Migrate every existing comment site, including
purely informational ones (stage-started, converged, watchdog
passed-inspection). Rejected — FR-005 only requires informational messages
not *claim* action, which they already don't; rewriting ~15 unrelated sites
is scope `spec.md` never asks for and multiplies the diff without changing
any observable behavior FR-001–FR-012 measure.

## Decision: `plan.yml`/`tasks.yml` gate-mode-fallback warnings and `watchdog.yml` finding comments are out of scope

**Decision**: `plan.yml`'s `WING_COMMANDER_PLAN_REVIEW` invalid-value
warning (line 433) and `watchdog.yml`'s finding/passed-inspection comments
are not migrated to `wing-commander-callout` by this feature.

**Rationale**: The plan-review warning is a same-run, self-correcting notice
("defaulted to enabled") with no separate action for the reader to take
beyond what the (already-announced) plan-PR review callout already covers —
it is closer to a footnote on an existing action than a new one. Watchdog's
findings are a distinct, already-specified subsystem (spec 015) whose
"Action:" line and autonomous-fix-PR flow have their own contract
(`specs/015-pipeline-watchdog/contracts/`); folding watchdog into this
feature's scope would mean amending a second spec's contract inside this
plan, which `spec.md` does not ask for and no acceptance scenario here
exercises. A future feature can extend `wing-commander-callout` to watchdog
once/if that need is explicit.

## Decision: No new labels

**Decision**: This feature adds no new GitHub label. Existing `stage:*`
labels (`stage:review`, `stage:stalled`, etc.) are unchanged.

**Rationale**: `spec.md`'s Assumptions section explicitly allows labels to
"continue to exist and complement callouts" while FR-010 forbids relying on
one as the mechanism — the comment itself, not a label, is what this feature
must add. Introducing a new label (e.g. `needs:human`) would be a second,
redundant signal for something the callout comment already makes
unambiguous, adding label-taxonomy surface `spec.md` never asks for.

## Decision: Injection safety — callout body content is always passed by file, never string-interpolated into a shell command

**Decision**: `wing-commander-callout` accepts `body` as either a literal
short string (for one-line summaries the calling workflow already controls,
e.g. `"No manual work remains."`) or a `body-file` path; when a `body-file`
is given, the action uses `gh issue comment --body-file` (never
`--body "$(cat file)"` shell-interpolated). Every existing caller already
follows this pattern for agent-authored content (`finalize.yml`'s
`finalize-remaining.md`, `implement.yml`'s `/tmp/stall-comment.md`); this
decision keeps it as a hard contract of the new composite action rather than
leaving it to each caller to remember.

**Rationale**: Constitution V (untrusted content is never instructions)
already governs how agent-authored text is *generated*; this decision
closes the adjacent shell-injection risk of how that text is *posted* —
agent-authored markdown (which could coincidentally contain shell
metacharacters, e.g. a task description with a backtick) must never be
interpolated into a bash command string. `--body-file` sidesteps this
entirely, matching the existing safe callers.
