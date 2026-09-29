# Research: Routed-Original Disposition

Spec.md's own clarification session (Q1–Q3) already resolved the three
questions marked `[NEEDS CLARIFICATION]` during intake/clarify. No marker of
that form remains in spec.md. What follows are the implementation-level
decisions the plan needs that clarify did not need to ask a human about —
each phrased as Decision / Rationale / Alternatives considered, per the
`/speckit-plan` skill's Phase 0 format.

## D0 — spec.md's references to "spec 097" and "spec 100" name specs that do not exist

**Decision**: Treat the Edge Cases section's "spec 097's stop point" and
"spec 100's re-admission semantics" as referring to the behaviour actually
documented in `specs/057-autonomous-board-loop/contracts/board-loop-workflow.md`
(the stop procedure) and `contracts/eligibility-and-selection.md` /
`contracts/labels-and-cross-links.md` (the `board:stalled`-removal
re-admission rule) — the only place in this repository either behaviour is
specified. `specs/` has no `097-*` or `100-*` directory; a repo-wide search
for those numbers matches only spec 108's own spec.md.

**Rationale**: The behaviours spec.md describes are real and are exactly
what spec 057's contracts already say. Blocking planning on this mismatch
would stall a feature the clarify session already approved over what reads
as a stale or forward-referencing issue number, not a substantive ambiguity
— FR-006/FR-014 name the actual mechanism (`board:stalled` removal as sole
re-admission) precisely enough to plan against regardless of which spec
number it's attributed to.

**Alternatives considered**: Halting to ask for clarification — rejected;
this run's deviation rules direct unresolved-but-non-blocking spec issues to
a documented decision plus a findings report, not a stall. Silently
reading past it — rejected; the mismatch is worth surfacing since a future
reader would otherwise search for specs that were never filed. This is
reported in the accompanying `wing-commander-findings` block rather than
fixed here, since correcting spec.md's prose is not this stage's task.

## D1 — Disposition label: reuse the existing `disposition:` prefix

**Decision**: Introduce `disposition:duplicate`, applied to the
originating issue at disposition time. This is the first writer of the
`disposition:` label prefix — `board_eligibility.DISPOSITION_PREFIX` and
its exclusion check have existed since spec 057 but no workflow step has
ever applied a label under that prefix.

**Rationale**: `is_excluded()` already excludes any `disposition:*` label
and the eligibility contract already documents the prefix as marking an
issue "settled" (e.g. `disposition:false-positive`) — "duplicate" is a
natural second member of that same family, needing no new exclusion branch.
Reusing it is also what CLAUDE.md's single-home rule asks for: a second,
parallel "this issue is done for a policy reason" label would duplicate a
mechanism that already exists and is already load-bearing.

**Alternatives considered**: Keep using `board:stalled` on disposed issues
— rejected: FR-006 requires that removing `board:stalled` alone must NOT
re-admit a disposed issue, which only needs special handling at all because
`board:stalled` today IS the sole re-admission signal (contracts/
labels-and-cross-links.md); giving disposed issues a label indistinguishable
from an ordinary hand-over stall would make FR-006's rule impossible to
express without inspecting the marker on every stalled issue instead of the
disposed ones only. A brand-new label prefix — rejected: duplicates
`disposition:`'s existing purpose and exclusion wiring for no benefit.

## D2 — Close mechanism: REST `state_reason: duplicate` via `gh api`

**Decision**: Close the originating issue with
`gh api -X PATCH repos/OWNER/REPO/issues/N -f state=closed -f state_reason=duplicate`,
never `gh issue close --reason duplicate`.

**Rationale**: Already settled in spec.md's Assumptions section: the `gh`
CLI's `--reason` flag support on `issue close` varies by version across the
fleet's runners, while the REST field is stable. Recorded here for
traceability from the code that will implement it.

**Alternatives considered**: `gh issue close -R OWNER/REPO N --reason
duplicate` — rejected per spec.md's own assumption.

## D3 — One shared disposition operation, three call sites

**Decision**: Add one new Python module (paralleling
`board_item_marker.add_stalled_label()`'s shape) that performs the whole
disposition — idempotency pre-check, the REST close, the
`disposition:duplicate` label, the reason comment, and the reciprocal
cross-link comment on the spec-request — and call it identically from the
three sites FR-002 names: route's spec-verdict step, fix's post-push-breach
step, and readiness's backstop-breach step (including the path where
readiness reuses a spec-request the fix job already filed). It replaces,
only at these three sites, the `board_item_marker.add_stalled_label(...,
"board:stalled")` + stall-comment pair that runs there today. The other six
`board:stalled` sites (round-budget exhaustion, gate-red hand-over, review's
three stalls, and any future non-spec-request hand-over) are untouched —
FR-002 names exactly these three, and they are not spec-request sites.

**Rationale**: CLAUDE.md's "shared logic has exactly one home" rule, and
the same reasoning `add_stalled_label()`'s own docstring gives for why
every stall site calls one function rather than repeating the label-then-
comment sequence inline six times: a second, drifted copy is invisible
until the first divergent fix.

**Alternatives considered**: Inline the close+label+comment sequence at
each of the three sites — rejected, exactly the pattern CLAUDE.md's shared-
logic section warns against, and the one Gate 93 check 3 already polices
for the spec-request-create side of these same sites. A composite action
instead of a Python module — rejected: the disposition needs the same
idempotency pre-check (read current labels/state before acting) that
`board_spec_request_body.py` and `board_item_marker.py` already do in
Python, and keeping it as a script keeps it unit-testable the way those
are, independent of a `.github/actions/*/action.yml` wrapper (which can
still shell out to it, matching how `board_item_marker.py` is invoked today).

## D4 — Idempotency: pre-check before acting, not a retry-safe API call alone

**Decision**: The disposition operation reads the originating issue's
current state and labels first. If it is already closed and already
carries `disposition:duplicate`, it returns success without re-closing,
re-labelling, or re-commenting. The already-closed-for-another-reason edge
case (a maintainer closed it mid-run) is treated as "close already
satisfied" — the operation still adds the label and posts the reason/link
comment if they are not already present, but never re-attempts a `gh api`
close call GitHub would 422 on if the state transition is a no-op, and
never fails the job over it.

**Rationale**: FR-009's idempotency requirement and the edge case "the
originating issue is already closed when a site reaches its disposition
step" both require this; unlike label-add (`gh issue edit --add-label`,
naturally idempotent) or the close call itself (closing an already-closed
issue is a no-op on GitHub's side), *posting a comment* is not idempotent —
running the same `gh issue comment` twice doubles it. A pre-check is the
only way to keep the comment side idempotent too.

**Alternatives considered**: Rely on GitHub's own idempotent close
behaviour and skip the pre-check — rejected: it does not cover the comment,
which is the part FR-009 explicitly calls out ("without ... posting a
duplicate comment").

## D5 — Two-way cross-link: extend the existing composite's use, not its shape

**Decision**: `wing-commander-outstanding-task-item` (contracts/
labels-and-cross-links.md's "ONE shared mechanism") continues to post the
existing `"Routed to spec-request"` checklist item on the originating issue.
The disposition operation additionally invokes the same composite a second
time, posting on the **spec-request** issue with a new phrase (e.g. "Filed
for the routed original") linking back to the originating issue's URL. This
is a new row in the same table, not a new link format.

**Rationale**: FR-004 requires both issues to link to the other "through
the loop's existing single cross-link mechanism rather than a second
hand-written link format." Today only the originating issue gets a real
checklist-item link; the spec-request gets only a plain-text, non-checklist
footer sentence from `board_spec_request_body.py` ("Originating issue:
<url>") that was never meant as the reciprocal link — it exists so the
spec-request's *body* carries provenance, not so a reader can click through.
Posting a second checklist-item comment via the same composite gives the
spec-request a link in the same shape a reader already recognizes from every
other artifact the loop cross-links.

**Alternatives considered**: Treat the existing footer sentence as
satisfying FR-004's reciprocal link — rejected: it is prose inside the
initial body, easy to miss, and not the composite's own recognizable
checklist format; FR-004 says "the loop's existing single cross-link
mechanism," which is the composite, not a bespoke footer line. Add a new
composite — rejected, no new shape is needed.

## D6 — Re-admission: a carve-out in `is_excluded()`, not a second flag

**Decision**: `board_eligibility.is_excluded()` gains one carve-out,
checked only when an issue is OPEN and carries `disposition:duplicate`: if
the issue's newest loop-authored marker records the new terminal step this
plan adds for disposition (see data-model.md's Board Item Marker changes)
and that marker's linked spec-request issue currently resolves CLOSED, the
issue is NOT excluded on `disposition:duplicate` grounds (it still excludes
normally if the linked spec-request is still OPEN). No separate "already
re-admitted once" counter is needed: once `select()` picks the issue back
up and the loop posts a fresh marker for it (triage/route), the newest
marker's step is no longer the disposal step, so the carve-out's own
condition stops matching on the very next run — "at most once per reopen"
falls out of the existing newest-marker-wins model for free.

**Rationale**: `is_excluded()` already returns `True` on `state == CLOSED`
before it reaches any label check, so a disposed issue that stays closed
needs no new code at all — FR-005 is already satisfied by the exclusion
list's existing first branch. The only genuinely new behaviour is what
happens when a maintainer reopens it (FR-006): reopening does not by
itself clear `disposition:duplicate` (GitHub does not clear labels on
reopen), so without a carve-out the reopened issue would stay excluded
forever on that label alone, which is the opposite of what a maintainer's
reopen is supposed to do. Gating the carve-out on the *linked spec-request's
current state* (not merely "was disposed") is what implements the spec's
last sentence of FR-006 and Edge Cases' "closed without its work landing"
interaction: reopening while the spec-request is still open must not file a
second one.

**Alternatives considered**: A dedicated `board:reopened-duplicate` label a
human or a webhook applies — rejected: adds a second label and a second
write path for the same fact the marker + `disposition:duplicate` + live
spec-request state already encode; violates D1's reasoning a second time.
An explicit "reopen count" field on the marker — rejected: unnecessary once
the newest-marker-wins property already yields "at most once" for free.

## D7 — FR-008 (stop-request effectiveness) needs no change to the stop-check composite

**Decision**: `wing-commander-board-stop-check` and its six call sites are
left as they are. Verified by reading the composite in full: it reads an
issue's comments unconditionally (its only closed-issue special case,
`check-issue-closed`, is an opt-in used solely by `prove`, defaulting off
everywhere else) — a closed issue remains fully commentable and its
comments remain fully readable, so a maintainer's stop request posted on a
disposed-but-still-mid-flight originating issue (the post-push-breach and
readiness-breach cases, where the fix PR can still be open after the
backstop fires) continues to be found exactly as before. Once the board
loop's own involvement with the item ends (its only exits are a
spec-request or a closed issue, per the constitution's Development
Workflow section), later stop requests belong on the spec-request /
lifecycle issue, which the separate feature-lifecycle pipeline already
reads for its own stop/pause handling — not a board-loop concern.

**Rationale**: Changing working code without a defect to fix violates
CLAUDE.md's minimalism expectation and this constitution's Principle VIII
spirit (a check that cannot fail its subject is a liability; the inverse —
changing code a check already covers, without a reason — is needless
churn). FR-014's documentation update is where readers are told which
issue to use going forward; that is a docs change, not a code change.

**Alternatives considered**: Add `check-issue-closed: true` to the fix/
readiness call sites so a disposed-but-still-active item auto-pauses —
rejected: this would stop the post-breach fix/readiness chain from ever
finishing a PR that was intentionally left open by the breach path itself,
contradicting the User Story text ("leave the branch/PR open").

## D8 — FR-017's "closed with no merged final PR" signal: `spec-meta.json`'s `stage`, not GitHub PR-merge inference

**Decision**: The scheduled scan (a new step in the `select` job, sibling
to its existing FR-010b orphan-detection step) identifies a spec-request
issue this loop filed by its `spec-request` label and bot authorship, finds
the `specs/<NNN-slug>/spec-meta.json` whose `issue` field names it, and
treats "closed with no merged final PR" as: the issue is CLOSED and that
spec-meta.json's `stage` never reached the finalize stage's terminal
completion value.

**Rationale**: `spec-meta.json` is already "the machine-readable source of
truth for a spec's lifecycle state" per this constitution's Operational
Constraints, and every stage of the lifecycle (including this plan stage,
per its own instructions) writes to it directly. Reading it is a single
deterministic field comparison, matching Principle IX's preference for
judgment gated on deterministic code over inferring the same fact from
GitHub's timeline/cross-reference API, which does not reliably distinguish
"closed by a merged PR's closing keyword" from "closed manually while a PR
happened to be open" without extra heuristics.

**Alternatives considered**: Infer from the GitHub issue timeline whether a
merged PR's `Closes #N` closed it — rejected as noisier and dependent on
convention (a final PR that does not use a closing keyword, or is merged
after the issue was already closed by hand) rather than the field the
finalize stage is already the authoritative writer of.

## Technical Context (for plan.md)

- **Language/Version**: Python 3.11 (repository convention for
  `.github/scripts/*.py`) + Bash (workflow `run:` steps) + YAML
  (`board-loop.yml`, contracts).
- **Primary Dependencies**: GitHub CLI (`gh`), `jq`, PyYAML (already a
  dependency of `verify-issue-context-single-home.py`). No new third-party
  dependency.
- **Storage**: N/A — GitHub issues/comments/labels are the durable state;
  `spec-meta.json` is read (D8), not written, by this feature.
- **Testing**: This repository's own fixture-harness convention — checked-
  in good/bad synthetic fixtures asserted by each script's own
  `--self-test` mode (no pytest), run via
  `python .github/scripts/run-local-gates.py`.
- **Target Platform**: GitHub Actions (`ubuntu-latest`), triggered by
  `board-loop.yml`'s `schedule`/`workflow_dispatch` and `pull_request`
  events.
- **Project Type**: Single project — CI/automation tooling, not a
  frontend/backend split.
- **Performance Goals**: N/A — hourly-cron and event-driven, not
  latency-sensitive; no new agent/LLM invocation is added (disposition is
  deterministic code, Principle IX), so no new cost-tier decision applies.
- **Constraints**: Must not widen the published stage-workflow contract
  (spec.md Assumptions; Principle VII) — this feature touches only
  `board-loop.yml`, its composites/scripts, and this consuming repository's
  own docs/contracts, never `.github/workflows/<stage>.yml`. The App
  token's `issues: write` scope already covers `gh issue close`/`edit` at
  these jobs (already used elsewhere in `board-loop.yml`, e.g. `prove`'s
  closes).
- **Scale/Scope**: Three call sites in one workflow file; one gate check
  extended (Gate 93 check 3, FR-012/FR-013); one new shared script/
  composite; one new `select`-job scan step (FR-017); doc/contract updates
  to `docs/setup.md` and `specs/057-autonomous-board-loop/contracts/*.md`
  (FR-014 — those contracts remain live per CLAUDE.md, since Gate 93 and
  `verify-board-eligibility.py` read the behaviour they describe).
