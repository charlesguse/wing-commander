# Research: Maintainer Commands and Spec Kit Routing Through PR Conversation

**Feature**: 033-pr-conversation-commands

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — all three raised
during `/speckit-clarify` were resolved before this plan ran (see
`checklists/requirements.md`). The decisions below are planning-level
technical choices (Phase 0), each with alternatives considered, needed to
turn the spec's functional requirements into a design that reuses this
repository's existing architecture rather than inventing new mechanisms.

## D1: New trigger events, no existing precedent

**Decision**: The new wrapper, `wing-commander-9-pr-conversation.yml`, adds
`pull_request_review: [submitted]`, `pull_request_review_comment: [created]`,
and `issue_comment: [created]` (filtered to
`github.event.issue.pull_request != null` — the inverse of
`wing-commander-2-clarify.yml`'s `!github.event.issue.pull_request` guard,
which exists specifically to exclude PR comments from the issue-scoped
clarify stage).

**Rationale**: Grepping every workflow file for `pull_request_review`/
`pull_request_review_comment` found exactly one hit —
`.github/workflows/claude.yml`, a disabled (`if: false`) legacy generic
mentions workflow that predates the pipeline, not a stage or wrapper. No
published stage or wrapper reacts to either event today. FR-018 requires
the stage to accept requests from all three GitHub PR conversation
surfaces (issue-style comments, formal review bodies, inline review-thread
comments), so all three triggers are required; there is no way to satisfy
FR-018 with fewer.

**Alternatives considered**: Polling (a scheduled workflow that scans PRs
for new comments) — rejected: every other comment-driven stage in this
repository is event-triggered, not polled, and polling would add both
latency and cost with no benefit. Reusing `clarify.yml`'s `issue_comment`
trigger alone and asking maintainers to leave PR feedback as issue-style
comments only — rejected: it would silently fail FR-018's "review bodies
and inline review-thread comments" requirement, which is explicit in the
spec's independent tests (User Story 1's test says "leave a review").

## D2: Model tier — sonnet default, opus opt-in, not haiku

**Decision**: `claude-sonnet-5` by default; `claude-opus-5` via a repo
variable (`WING_COMMANDER_PR_CONVERSATION_MODEL`) or a `model:opus` label
on the lifecycle issue, resolved in a `resolve-model` pre-job exactly like
`wing-commander-5-implement.yml`'s existing job of the same name and shape.

**Rationale**: Constitution II reserves haiku for "triage, classification,
labeling, and summaries." This stage's classify+draft step does more than
classify: it judges constitution conflicts (User Story 3), judges "very
small" (User Story 2, Assumptions), drafts issue bodies and PR content, and
decides whether a new-functionality request extends the current spec or
needs its own (FR-006) — decisions closer in weight to planning/
implementation than to labeling. It is not spec/clarify-tier foundational
work either (no new spec content is authored from scratch), so opus-by-
default is not justified. Sonnet, with the same opt-in-to-opus escape
hatch `implement.yml` already offers for hard cases, is the correct tier.

**Alternatives considered**: Haiku (rejected — task weight exceeds triage,
per above; a misjudged constitution-conflict or "very small" call has real
consequences: FR-010, FR-007, SC-003, SC-004). Opus-by-default (rejected —
no foundational-document authoring occurs here the way it does for
spec/clarify; would violate II's cost-consciousness for the common case of
routine in-scope review comments).

## D3: No new composite actions

**Decision**: Reuse all seven existing composite actions as-is. In
particular, `wing-commander-callout` is called with the PR number as its
existing `issue-number` input for PR-thread replies, and — when FR-013
requires it — called a second time with the lifecycle issue number, since
`gh issue comment` (which the composite already wraps) accepts PR numbers
unmodified (PRs are issues in the GitHub REST API).

**Rationale**: None of the seven composites are stage-specific; all are
already resolved generically via the pipeline-repo self-checkout every
stage performs. Renaming or widening `wing-commander-callout`'s
`issue-number` input would be a compatibility-surface change under
constitution VII for no behavioral gain, since the existing input already
does the job.

**Alternatives considered**: A new `wing-commander-pr-callout` composite
mirroring `wing-commander-callout` — rejected as needless duplication once
it was confirmed `gh issue comment` already targets PRs; would also create
two composites to keep in sync forever. Renaming `issue-number` to a
generic `target-number` — rejected: a published composite's input rename
is exactly the kind of surface change constitution VII asks to be
"deliberate... not a convenience," and the existing name already works.

Two genuinely new, narrow capabilities have no composite-action precedent
and are added as stage-internal deterministic steps instead of a new
composite (too specific to this one stage to warrant a shared action):
inline review-thread replies (`POST /repos/{owner}/{repo}/pulls/{pr}/comments`
with `in_reply_to`, for replying inside a review thread rather than the
general PR conversation) and the stop-target scan (D10).

## D4: Identifying the "implementation PR tied to an in-flight spec" (FR-018)

**Decision**: A PR qualifies when its base ref equals the resolved default
branch **and** its head ref starts with the configured `spec-prefix`
(default `spec/`) — never `spec-draft-prefix`, `plan-prefix`, or
`tasks-prefix`. This check runs inside the stage (a preflight-style step),
not the wrapper, mirroring `tasks.yml`'s `mode: approved` pattern of
validating slug/branch shape inside the stage rather than the cheap
event-only wrapper `if:`.

**Rationale**: `finalize.yml` opens exactly one PR shape per spec: head
`spec/<slug>`, base the default branch — and already calls it "the
implementation PR" in its own callout (`pr-label: "the implementation PR"`).
Draft spec PRs are head `spec-draft/<slug>` → default branch; plan/tasks
PRs are head `plan/<slug>`/`tasks/<slug>` → **`spec/<slug>`**, not the
default branch. Base-ref-is-default-branch alone would still admit draft
spec PRs, so both the base and the head-prefix checks are required
together. This also means: after this feature ships, re-opening
`spec-meta.json.stage` from `"review"` back to `"implement"` (D5) does not
change which PR the maintainer is looking at — it is the same open
`spec/<slug>` → default-branch PR throughout, exactly as US1's acceptance
scenario 2 requires ("the updated code is pushed to the existing PR").

**Alternatives considered**: Keying off the `stage:review` label alone —
rejected: labels are mirrored copies (finalize copies the issue's full
label set onto the PR) and can churn or be edited manually; the branch
identity is the authoritative signal the pipeline itself established.
Requiring `spec-meta.json.stage in {"review"}` — rejected as the sole
signal: it would refuse a second re-triggered cycle whose `stage` is
already back to `"implement"` mid-loop, which User Story 1's re-drive
explicitly needs to keep working.

## D5: Folding an in-scope request into converge input (FR-004/FR-005)

**Decision**: The stage's `act` job, for an in-scope-change classification:
(1) checks out `spec/<slug>`; (2) runs a bounded agent step that appends a
new `## Maintainer Feedback (PR #<n>, comment <id>)` section to
`tasks.md`, containing traceable task items derived from the staged,
untrusted request text, committed on its own with a `pr-feedback:`-prefixed
message (distinct from `implement.yml`'s own `converge:` prefix, so the two
signals never collide); (3) reads `spec-meta.json`'s current `iteration`
and rewrites `stage` to `"implement"` (iteration left unchanged — the next
`implement.yml` cycle sets it), committed in the same push; (4) dispatches
`wing-commander-5-implement.yml` via `gh workflow run` with
`spec_dir=<dir> issue=<issue> iteration=<recorded+1>` — the exact,
already-published `workflow_dispatch` signature
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Chaining
payload contract" table documents for this wrapper. **No change to
`implement.yml` or the `/speckit-converge` skill is made.**

**Rationale**: `/speckit-converge`'s own SKILL.md states its "sole source
of intent" is `spec.md` + `plan.md` + `tasks.md` — it is explicitly "not a
diff tool," has no separate side-channel input, and only ever appends to
`tasks.md`. The only way to hand it new intent without changing its
contract is to already have that intent sitting in `tasks.md` before it
runs — which converge itself would otherwise have had to rediscover
independently, an unreliable path for a maintainer's specific, worded
request. Writing the request directly as a task section makes it visible
to both the next `implement` pass (as unchecked work) and the next
`converge` pass (as a section it will find already reflects the desired
end state, once implemented) with zero interface change to either. The
`spec-meta.json.stage` rewrite is required because `implement.yml`'s own
idempotency guard only accepts a dispatch when
`stage=="implement" && iteration==recorded+1` (verified by reading the
guard's literal condition) — after `finalize.yml` runs, `stage` reads
`"review"`, which would make any re-dispatch a silent no-op without this
rewrite.

**Alternatives considered**: Extending `/speckit-converge`'s prompt or
`implement.yml`'s agent instructions to read a new staged
maintainer-feedback file — rejected: touches a stage this feature does not
otherwise need to change, widening its blast radius and its own
compatibility surface (constitution VII) for no benefit over the
tasks.md-section approach, which needs no interface change at all.
Inventing a new dispatch target/workflow specifically for "re-triggered"
cycles — rejected: `implement.yml`'s idempotency guard already handles
re-entry safely once `spec-meta.json` is correctly set, so a second entry
point would duplicate logic that already exists and works.

## D6: Concurrency / serialization (FR-015)

**Decision**: Both stage jobs (`classify-and-announce`, `act`) declare
`concurrency: group: wing-commander-<spec-dir>, cancel-in-progress: false`
— the exact canonical group `specs/013-serialize-rebase-stages` already
established and every spec-branch-mutating stage (`plan`, `tasks`,
`implement`, `finalize`, `rebase`) already joins.

**Rationale**: The PR this stage reacts to is 1:1 with a `spec-dir`
(D4), so the existing group is already scoped exactly right — a
maintainer's comment folding into converge and a concurrently re-dispatched
`implement.yml` cycle for the same spec cannot both proceed at once,
because they now contend for the identical lock `implement.yml` already
respects. This satisfies FR-015 ("must not corrupt or race the in-flight
loop... queued rather than a conflicting parallel loop") with the same
zero-new-mechanism reasoning `specs/013-serialize-rebase-stages/plan.md`
itself argues for.

**Alternatives considered**: A PR-keyed group
(`wing-commander-pr-<number>`) — rejected: it would let a PR-conversation
`act` job run concurrently with an `implement.yml` cycle it just
dispatched (or an independently-running one), which is exactly the race
FR-015 forbids; the spec-dir-keyed group is required, not merely
sufficient. Clarify's issue-keyed group
(`wing-commander-<issue-number>`) — rejected: clarify never mutates the
spec branch, only the draft spec PR, so its narrower scope doesn't apply
here; this stage does mutate the spec branch.

## D7: Routing a "new functionality" request that warrants its own spec (FR-006)

**Decision**: When the classify+draft agent step decides a request is
distinct enough for its own spec, the stage's `act` job opens a new GitHub
issue (title + body drafted by the same agent step from the maintainer's
request, framed as a normal feature request) and applies the `spec-request`
label the existing `wing-commander-1-intake.yml` wrapper already gates its
own trigger on (`if: github.event.label.name == 'spec-request'`) — using
the stage's own bot token, which already has issue-write permission via
`wing-commander-context`. No new entry point is created; intake picks the
new issue up exactly as if a maintainer had filed and labeled it directly.

**Rationale**: `spec-request` being the maintainer-applied label **is**
intake's documented security gate today; here, the label is being applied
by the pipeline's own bot on behalf of a request that has *already* passed
this stage's own maintainer-authorization gate (FR-019) one level up — the
same "the pipeline automates what a maintainer already asked for" shape
FR-012's permission-request PRs and FR-007's small-change PRs both use
(the bot acts, a human remains the reviewer/approver of the *result*, not
of the triggering decision). Reusing intake's exact entry mechanism means
zero new code path for "how does a spec get created."

**Alternatives considered**: A new dedicated entry point that skips intake
and creates `spec-draft/<slug>` directly — rejected: duplicates intake's
slug-allocation, spec-kit invocation, and draft-PR logic for no benefit,
and would drift from intake's own evolution (e.g. spec 029's comment
folding) over time. Requiring a *human* maintainer to apply the label
after the bot's issue is filed — rejected: FR-006 requires the stage
itself to "create a new lifecycle issue," and this repository's other
spin-off flows (FR-007, FR-012) are similarly bot-initiated with human
review of the *artifact*, not of the initiating action; gating on a
second manual label application here would be an inconsistent extra
step not asked for anywhere else in the spec.

## D8: "Very small" unrelated change (FR-007) — judgment plus a deterministic backstop

**Decision**: The classify+draft agent step makes the first-pass "very
small" judgment (per spec.md's own Assumptions: "an agent judgment with a
conservative bias"), and drafts the change; a deterministic step in `act`
then measures the actual diff the drafted change would produce (files
touched, lines changed) against a small, documented, hardcoded threshold
before opening the PR. Exceeding the threshold re-routes the request to
the new-functionality path (D7) instead of opening the PR — this is what
edge case "an unrelated tiny change turns out not to be tiny once
examined" requires.

**Rationale**: Mirrors `clarify.yml`'s existing shape: an agent makes a
judgment call, and a deterministic step cross-checks the agent's own
output before anything is finalized (there, schema validation against
`[NEEDS CLARIFICATION:]` markers). A single agent-only judgment with no
backstop would let a misjudged "very small" call open an oversized PR with
nothing to catch it — the exact failure SC-004 exists to prevent ("no
large or non-tiny change is shipped as a spin-off PR").

**Alternatives considered**: Agent judgment alone, no backstop — rejected,
directly risks SC-004. A hard, purely deterministic threshold with no
agent judgment at all (e.g. "≤3 files changed" decided before any drafting)
— rejected: it can't evaluate whether a change is *conceptually* entangled
with the current spec's work (the spec's real "small vs. entangled"
distinction), only its size; the two checks are complementary, not
substitutable.

## D9: Autonomy configuration and propose-and-confirm (FR-020)

**Decision**: Two new repository variables, read only by the wrapper:
`WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES` — a comma-separated
list of the action categories (from FR-003's taxonomy) that require
propose-and-confirm, or the literal `all`; empty/unset means act-then-report
for every category (the default). `WING_COMMANDER_PR_CONVERSATION_CONFIRM_ENVIRONMENT`
— the name of a GitHub deployment environment the consumer configures with
required reviewers; default `pr-conversation-confirm`. The stage's `act`
job binds to this environment (via the job-level `environment:` mapping
form, whose `name` may be an expression — confirmed by
`specs/031-stage-environment-binding/contracts/environment-binding.md`'s
empirical basis item 2) **only when** the classify step's chosen category
is in the confirm list; otherwise `environment.name` resolves to `""`, a
verified true no-op (same contract, item 1), and `act` runs immediately.

**Rationale**: Spec 031 already proved, empirically, that an unconditional
job-level `environment:` block with an expression `name` is a real,
GitHub-native wait-for-approval gate that pauses a job before its first
step runs, requires no new pipeline code, and costs nothing when the name
is empty. FR-020 requires "propose-and-confirm for individual action
categories... while still acting immediately on in-PR actions" — that is
precisely "gate this job, sometimes, based on a value known before the job
starts," which is spec 031's whole contract. Building a second mechanism
(a custom wait/poll loop) would duplicate a solved problem and add the one
kind of long-running/polling job no other stage in this pipeline has.

**Alternatives considered**: A JSON config file under `.specify/memory/`
(mirroring `watchdog-guardrails.json`) — rejected: watchdog's guardrails
are read-only bounds on an otherwise-autonomous loop with no natural
GitHub approval point; this feature's confirm gate has a much better fit
(GitHub's own reviewer approval) that a flat repo variable can drive
without inventing a new config-file schema. Per-category individual repo
variables (`..._CONFIRM_SPINOFF_ISSUE`, `..._CONFIRM_SMALL_PR`, ...) —
rejected as unnecessary sprawl; a single comma-separated list matches the
existing `extra-allowed-tools`-style "comma-separated list" convention
already used elsewhere in this pipeline's configuration surface.

## D10: Intent announcement, run link, and the stop mechanism (FR-023/FR-024)

**Decision**: The `classify-and-announce` job posts one callout (via the
existing `wing-commander-callout` composite, D3) stating the assigned
classification, the action about to be taken, and
`${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`
— the exact `RUN_URL` expression `implement.yml`/`watchdog.yml` already
use — **before** the `act` job (the only job with write scope) starts. A
follow-up comment the classify step recognizes as a stop request causes
`act` to: search the PR's own comment thread for the most recent bot-posted
intent-announcement callout, extract the run id from its embedded link,
and call `gh run cancel <run-id>` on it (plus, if that announcement's
action was an implement re-trigger, also cancel the dispatched
`wing-commander-5-implement.yml` run found via `gh run list --workflow
wing-commander-5-implement.yml --branch spec/<slug> --status in_progress`).
If nothing is found in progress, `act` reports what the prior action
already completed, per FR-024's second clause.

**Rationale**: No cancellation precedent exists anywhere in this
codebase (confirmed by grep — every `cancel-in-progress:` hit is the
standard `concurrency:` field, always `false`); this design had to be
built from GitHub-native pieces rather than adapted from an existing
pattern. Using the PR's own comment thread as the lookup for "which run to
cancel" needs no new storage (constitution VI/VII: no new pipeline-owned
state in the consumer repo) and is directly inspectable by a human, in
keeping with constitution III. `gh run cancel` on the maintainer's own
initiative (cancelling the linked run directly, no reply needed) works
today with zero pipeline code, per spec.md's own Assumptions ("this
feature does not introduce a bespoke cancellation surface") — the reply
path above is the one half of FR-024 with no such free ride.

**Alternatives considered**: A long-running job that sleeps and polls for
a stop comment — rejected: no other stage in this pipeline runs a
long-lived polling job (every agent invocation is single-shot and
bounded); it would also keep incurring runner cost while idle, the
opposite of constitution II's cost-consciousness. Persisting the
"currently in-flight run id" to a new file/label — rejected: the PR
comment thread already carries this information once the announcement is
posted, so a second copy would be redundant state to keep in sync.

## D11: Withheld-permission conversation lookup (FR-012)

**Decision**: Permission-request PRs and issues carry a dedicated
`permission-request` label (created on first use, same `gh label create
--force` idiom `intake.yml` already uses for its own labels). Before
opening a new one, the stage searches
`gh search prs --label permission-request --state all` (mirroring
`watchdog.yml`'s existing fingerprint/dedup search pattern, scoped to
pull requests since every permission-request artifact this stage creates
is a PR, never an issue) for a prior discussion whose title/body
plausibly names the same capability; the classify step judges the match
with the conservative bias spec.md's Assumptions already call for ("errs
toward explaining the situation rather than silently re-requesting or
silently doing nothing" — edge case).

**Rationale**: `watchdog.yml` already establishes a "label + `gh search`
fingerprint dedup" pattern in this exact codebase for a structurally
identical problem (has this already been reported/decided?).
Reusing it needs no new tool, no new API surface, and no new mechanism
class.

**Alternatives considered**: Free-text search with no dedicated label —
rejected: far noisier, and without the label there is no reliable way to
distinguish "a PR that happened to mention a permission" from "a PR that
*is* a permission request," undermining the conservative-bias requirement.

## D12: Technical Context choices with no meaningful alternative

**Language, testing tooling, target platform**: unchanged from every other
stage in this repository — GitHub Actions YAML + Bash, `actionlint`/
`yamllint`/`lint-workflows.yml` Gate 7, `ubuntu-latest`. Documented in
`plan.md`'s Technical Context for completeness; no alternative was
seriously considered, since deviating from the rest of the pipeline's
infrastructure stack for one new stage would itself be the violation
constitution VI/VII exist to prevent.
