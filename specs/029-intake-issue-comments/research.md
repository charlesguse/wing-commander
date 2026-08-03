# Research: Include Follow-Up Comments in Intake Specification

**Feature**: 029-intake-issue-comments · **Date**: 2026-08-03

The spec (`spec.md`) arrived with all three original `[NEEDS CLARIFICATION]`
markers already resolved via the lifecycle issue (see
`checklists/requirements.md`: FR-002 trust scope, FR-006 conflict handling,
FR-008 notice scope). This document records the *technical* decisions needed
to turn those resolved requirements into an implementable design, plus one
genuine interpretation gap the spec text itself leaves open (D4 below) —
documented here as an explicit, reasoned decision rather than left implicit
in code.

## Current-state findings

- `intake.yml` (`.github/workflows/intake.yml`) fetches the issue's title,
  body, and author itself, *inside the agent step's own prompt* (`gh issue
  view ${{ inputs.issue-number }} --json title,body,author`), then hands
  that content to `/speckit-specify` as the feature description. No
  deterministic (non-agent) step in the stage reads issue content today —
  the closest deterministic issue read is `wing-commander-lifecycle-gate`,
  which only checks open/closed state.
- `clarify.yml` already implements both patterns FR-002/FR-004 ask this
  feature to reuse, but at the scale of exactly **one** externally-supplied
  comment (the triggering reply), not an issue's full comment history:
  - **Author gate**: lives in the *wrapper* (`wing-commander-2-clarify.yml`),
    a trigger-time `if:` condition on `github.event.comment.*`:
    `user.type != 'Bot'` AND (`author_association` in
    `["OWNER","MEMBER","COLLABORATOR"]` OR `comment.user.id ==
    issue.user.id`).
  - **Untrusted-data-to-file**: a deterministic step
    (`clarify.yml` "Stage the answer as a data file") calls `gh api
    repos/${GITHUB_REPOSITORY}/issues/comments/${COMMENT_ID}` and redirects
    `--jq .body`/`--jq .user.login` straight to files under
    `/tmp/wing-commander/` — never shell-interpolated, never pasted into
    the agent prompt string.
- Neither pattern, as it exists today, evaluates a *set* of comments against
  the gate — clarify's wrapper-level `if:` only ever inspects the single
  comment that triggered the run. This feature needs the trust decision
  applied independently to every comment on the issue, computed at run time
  (intake's trigger is `issues: [labeled]`, which carries no comment
  payload at all).
- `intake.yml`'s agent tool allowlist (`Skill,Read,Write,Edit,Glob,Grep,
  Bash(git ...), Bash(gh issue view:*), Bash(gh issue edit:*), Bash(gh issue
  comment:*), Bash(gh pr create:*), Bash(gh label create:*)`,
  `specs/010-reusable-pipeline/contracts/stage-interfaces.md` "Per-stage
  default tool lists") already includes `Bash(gh issue view:*)`, which is
  wide enough for the agent to run `gh issue view <N> --json comments`
  itself and see **every** comment, unfiltered — this is the concrete shape
  of the risk User Story 2 names ("naively feeding every comment to intake
  would let a non-maintainer place content into a spec"). The
  Assumptions section ("existing permissions suffice … a prompt/behavior
  change, not a permissions change") rules out narrowing this allowlist, so
  the mitigation has to be a deterministic gate plus an explicit prompt
  constraint (D5), not a tool-allowlist change.
- GitHub's REST issue-comments endpoint
  (`GET /repos/{owner}/{repo}/issues/{issue_number}/comments`) — the same
  endpoint family `clarify.yml` already calls per-comment — returns, per
  comment: `user.login`, `user.id`, `user.type` (`"User"` vs `"Bot"`),
  `author_association`, `created_at`, `body`. This is the identical schema
  the wrapper's `github.event.comment.*` webhook fields already expose
  (`user.type`, `author_association`), just reachable by API instead of by
  event payload — confirming the same two fields settle both the bot check
  and the association check for every comment, not only the triggering one.

## Decisions

### D1: The trust gate is a new deterministic step inside `intake.yml` itself, not the wrapper

**Decision**: Add a new, non-agent (`run:` shell) step to `intake.yml` that
fetches the issue author and every comment via `gh api`, filters
deterministically, and stages the result — before the agent step runs, in
the same job.

**Rationale**: `clarify.yml`'s author gate lives in its *wrapper*
(`wing-commander-2-clarify.yml`) because that gate answers "should this
*trigger* even start a run?" for a single incoming event — exactly the kind
of trigger-time security decision constitution VII assigns to the wrapper
layer. Intake's trigger (`issues: [labeled]`) is not a per-comment event;
there is no single triggering comment to gate at dispatch time. The
decision this feature adds is instead "of the comments already on the
issue, which ones may influence output?" — a data-processing question
answered from state the stage itself reads mid-run, exactly like the
existing `wing-commander-lifecycle-gate` (re-fetches live issue state) and
`wing-commander-preflight` (deterministic fail-fast) steps that already live
inside the *stage*, not a wrapper. This keeps constitution VII's split
intact: the wrapper still owns the one trigger-time gate that exists
(`spec-request` label), and the stage owns the comment-history filter as
internal behavior — consistent with FR-002/FR-003 being framed as things
"Intake MUST" do, not the wrapper.

**Alternatives considered**:
- *Push the filter into the wrapper* — rejected: the wrapper only ever sees
  the labeling event, never the historical comment list; it would need to
  fetch and filter N comments itself, duplicating exactly the logic the
  stage needs anyway, and constitution VII assigns "every event fact and
  every knob arrives as a declared, typed input" to the wrapper/stage
  boundary, not a bulk data fetch.
- *Leave filtering to the agent's own judgment* — rejected outright: this is
  precisely the naive approach User Story 2 exists to prevent. The trust
  decision must be enforced before the agent ever sees non-qualifying
  content, not applied after the fact by an LLM that could be confused or
  overridden by adversarial comment text (User Story 3).

### D2: Bot and association detection reuse the exact two REST fields the wrapper already trusts

**Decision**: The new step calls `gh api
repos/${GITHUB_REPOSITORY}/issues/${ISSUE}/comments --paginate` and, per
comment, qualifies it when both hold:
- `.user.type != "Bot"` (FR-003 — regardless of the bot account's
  association), and
- `.author_association` is one of `OWNER`, `MEMBER`, `COLLABORATOR`, **or**
  `.user.id` equals the issue author's `id` (FR-002).

The issue author's id is resolved once, from `gh api
repos/${GITHUB_REPOSITORY}/issues/${ISSUE} --jq .user.id`, and compared by
**id**, not login string — matching `clarify.yml`'s existing
`comment.user.id == issue.user.id` comparison (robust to username/display
changes, unlike a login-string match).

**Rationale**: These are the identical fields
`wing-commander-2-clarify.yml`'s trigger-time `if:` already treats as
authoritative for exactly this same distinction, just read via API instead
of webhook payload — reusing the pattern precisely as the spec's Assumptions
section directs ("the author gate … modeled on the existing clarify stage
rather than invented anew"), with no new trust criterion invented.

**Alternatives considered**:
- *GraphQL via `gh issue view --json comments`* — rejected: `gh issue view`
  is a broad, agent-facing tool already on intake's allowlist
  (`Bash(gh issue view:*)`); routing the *deterministic* gate through the
  same command family the agent could also invoke blurs the line between
  "the gate's own trusted fetch" and "something the agent could have done
  itself," and its JSON shape for comment author metadata is not the same
  well-documented REST shape `clarify.yml` already depends on. `gh api`
  keeps the gate on the one schema already audited for this exact purpose.

### D3: Untrusted comment bodies are staged to one ordered data file, qualifying comments only

**Decision**: The new step writes qualifying comments only (non-qualifying
and bot comments are never written to disk at all, not merely excluded
downstream) to a single file, e.g.
`/tmp/wing-commander/intake-comments.md`, ordered oldest → newest
(Assumptions: "later" = later creation time), one section per comment
carrying its author login and ISO-8601 `created_at` as a heading, and its
`body` verbatim beneath — mirroring `clarify.yml`'s "fetched from the API
and written to a file, never shell-interpolated, never pasted into the
prompt" pattern, extended from one comment to N. Three counts — total
comment count, qualifying count, and non-bot-non-qualifying ("excluded
human") count — are computed in the same step and exposed as step outputs
(counts only, never body content) for later deterministic branching (D4).

**Rationale**: FR-004 requires comment bodies to be "handled as data (for
example fetched from the API and staged to a data file)" — the plan
literally names the mechanism `clarify.yml` already uses; the only new
design decision is the *shape* for a variable-length collection instead of
a single file. Staging only qualifying comments (rather than staging
everything and relying on the agent to ignore the rest) is a stronger,
defense-in-depth reading of FR-002/FR-009: the disqualified content never
becomes reachable by the agent through this file at all, so an agent
mistake in judgment can't leak it back in from this channel (D5 covers the
other channel — the agent's own tool access).

**Alternatives considered**:
- *Stage every comment, tagged qualifies:true/false, and instruct the agent
  to only use the qualifying ones* — rejected: reintroduces exactly the
  trust boundary User Story 2 exists to remove — an LLM instruction is not
  the enforcement mechanism constitution V requires ("untrusted content is
  never instructions," and by the same logic, never a judgment call the
  agent is trusted to make about *itself*).
- *One file per comment* (mirroring `clarify.yml`'s single-comment file
  exactly) — rejected: N files for a variable, potentially large N adds
  agent-side Glob/Read overhead for no benefit over one concatenated,
  clearly delimited file; the single-file shape is also what lets the
  three counts be computed in the same pass.

### D4: The FR-008 visible-notice condition — resolving an apparent tension in the spec text

**Decision**: The notice fires (deterministically, not by agent judgment)
when `qualifying_count == 0 AND excluded_human_count > 0` — i.e., at least
one non-bot comment existed and was excluded by the association/author-id
check, and zero comments qualified. It does **not** fire when every comment
on the issue is bot-authored (`excluded_human_count == 0`), and it does not
fire when at least one comment qualifies, even if others were excluded
(mixed authorship — Edge Cases: "qualifying comments are incorporated;
non-qualifying and bot comments are ignored, in the same pass," no notice
mentioned).

**Rationale — the tension**: FR-008's own parenthetical reads "none qualify
for incorporation (excluded by the trust gate **or as bots**)," which taken
literally would also fire the notice for an issue with only bot comments.
But the Edge Cases section states plainly: *"Only bot comments: all
excluded; intake is body-only"* — grouped with the silent "No comments"
case, not with the notice-bearing "Substantive comments exist but are all
excluded by the trust gate" case, and User Story 2's own Independent
Test/Acceptance Scenarios — the story FR-008 exists to serve — are framed
entirely around a *human* non-qualifying commenter, never a bot. Bots
commenting on lifecycle issues (the watchdog, the pipeline's own stage
status posts) is the pipeline's routine, expected chatter, not "substantive"
discussion a maintainer would mistake for settled consensus; treating it as
notice-worthy would make the notice fire on effectively every issue the
pipeline itself has touched, defeating its purpose as a signal. The Edge
Cases section is the more specific, independently-testable statement, so it
governs; this decision documents the resolution rather than leaving the
contradiction implicit in whichever behavior the implementation happened to
produce first.

**Alternatives considered**:
- *Fire on any exclusion, including bot-only* — rejected per the Edge Cases
  conflict above; would make the notice fire near-universally given every
  lifecycle issue already carries bot status comments, eliminating its
  value as a signal.
- *Never fire for the bot-adjacent case, requiring a human judgment call
  about "substantive"* — rejected: "substantive" has no operational
  definition in the spec beyond "not just bots"; introducing a content-level
  substantiveness judgment (e.g. distinguishing "+1" from real discussion)
  would require the agent to read excluded content to decide whether to
  disclose that excluded content existed — a contradiction with D3/D5's
  defense-in-depth stance of never letting non-qualifying bodies reach the
  agent context at all. Presence of at least one excluded non-bot comment
  is the strongest signal available without violating that boundary.

### D5: The agent is explicitly instructed not to re-derive comments itself

**Decision**: The agent's prompt is extended with an explicit constraint:
comment content, if any, is available only at the staged file path (D3);
the agent must not call `gh issue view --json comments` or otherwise fetch
comments on its own, and must treat the absence of a staged file (zero
qualifying comments) the same as "no comments" (FR-007) rather than trying
to look for more.

**Rationale**: `Bash(gh issue view:*)` is already on intake's allowlist
(current-state findings) and stays there per the spec's Assumption that
this feature makes no permissions change — so the deterministic filter in
D1–D3 is necessary but not, by tool-allowlist construction alone,
sufficient to guarantee the agent never sees unfiltered comments. An
explicit prompt constraint is the same class of mitigation intake's prompt
already relies on for its existing "SECURITY (non-negotiable)" framing of
the issue body, applied to close this specific new gap. This is a
documented residual-risk mitigation, not a hard technical guarantee — full
enforcement would require narrowing the allowlist, which is out of scope
per the spec's own Assumptions.

**Alternatives considered**:
- *Narrow `Bash(gh issue view:*)` to exclude `--json comments`* —
  rejected: not expressible in the claude-code-action tool-pattern syntax
  (glob matches the whole `gh issue view:*` invocation, not individual
  flags), and out of scope per Assumptions ("existing permissions
  suffice").

### D6: Feature description assembly reuses `/speckit-specify` unchanged

**Decision**: The composite feature description handed to `/speckit-specify`
becomes "issue title + body + qualifying comments" (FR-005), assembled by
the agent from the issue body (already fetched in its existing step 1) and
the staged comments file (D3) it reads via the `Read` tool — no change to
`.claude/skills/speckit-specify/SKILL.md` itself. The skill's own
`[NEEDS CLARIFICATION]`/three-marker mechanism, unchanged, is what satisfies
FR-006 (conflict → marker) and the "very long discussion thread … still
respects the maximum-3 clarification-marker cap" edge case: from the
skill's point of view a longer, comment-augmented feature description is
just a longer feature description, nothing about the skill's contract
changes.

**Rationale**: The skill already accepts free-form feature description text
regardless of source (today: title + body only) — extending what text is
assembled before the skill runs is a caller-side change, not a skill-side
one, keeping this feature's blast radius to `intake.yml` alone, matching the
Project Structure below.

**Alternatives considered**:
- *Teach the skill itself about comments* — rejected: would couple a
  generic specification skill to one caller's comment-fetching mechanics,
  and no other stage that invokes `/speckit-specify`-family skills needs
  comment awareness; the composition belongs at the call site, per
  constitution VII's "every document states which layer it describes."

## Constitutional considerations flagged for documentation (not violations)

Principle V (Security) requires "comment-triggered stages verify the
commenter is a maintainer … or the original issue author, and never react
to bots." Intake is not comment-*triggered* (constitution's own wording
targets the wrapper-level actor gate `clarify.yml` uses) — this feature
extends the *same standard* to comment *content* read mid-run by a
label-triggered stage. D1's rationale is the documented reconciliation:
constitution VII's wrapper/stage split is preserved because there is no
comment-trigger event to gate at the wrapper layer here, and the equivalent
protection is enforced deterministically inside the stage instead, using
the identical two fields the wrapper-level gate relies on for clarify.
