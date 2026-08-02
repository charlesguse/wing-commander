# Phase 0 Research: Auto-Rebase AI Conflict Resolution on Push-Triggered Rebases

`spec.md` carries no `[NEEDS CLARIFICATION]` markers — the requirements
(FR-001 through FR-012) and Assumptions section are already resolved. Every
decision below is a *technical* design decision planning had to make to
turn those requirements into a concrete change, not an escalated
clarification question, per this pipeline's standing instruction to
proceed rather than block when a spec is otherwise complete.

## R1 — Why push fails and schedule doesn't: `github.event_name` survives a `workflow_call` boundary

**Decision**: Treat "a reusable workflow invoked via `uses:
./.github/workflows/X.yml` sees the *original* triggering event in
`github.event_name`/`GITHUB_EVENT_NAME`, not `workflow_call`" as an
established fact this fix is built on, not a hypothesis to re-verify at
implementation time.

**Rationale**: The bug report itself is the proof. `wing-commander-rebase.yml`
calls the identical `uses: ./.github/workflows/rebase.yml` with identical
inputs regardless of whether `push` or `schedule` fired it — one call site,
one job, no branching on trigger. If `github.event_name` collapsed to a
constant (`workflow_call`) at that boundary, both triggers would fail (or
both would succeed) identically. They don't: the reported defect is
push-specific ("fails immediately... when the calling workflow was
triggered by a push event"), and the spec's own Assumptions section
separately treats the schedule path as "documented as supported" and
distinct from the broken push path. That asymmetry is only possible if
`github.event_name` differs between the two calls at the point
`claude-code-action` reads it — i.e. it propagates the real top-level
event through the `workflow_call` boundary unchanged. This repository's own
`plan.yml`/`tasks.yml` reusable stages independently corroborate the
propagation mechanism: both read `github.event_name` directly (e.g.
`tasks.yml`'s `tasks-approved` job: `if: github.event_name == 'pull_request'
&& ...`) and distinguish `pull_request` from `workflow_dispatch` correctly
at runtime — this only works if the reusable-workflow-called job sees the
real originating event, not a synthetic one.

**Alternatives considered**: Re-verifying this against GitHub's own
documentation/support before designing the fix — not rejected, just
unnecessary as a *planning*-time gate: FR-012 already requires the fix to
be proven against a real induced conflict before this feature is considered
done, which validates the mechanism empirically regardless of how well it's
documented externally.

## R2 — Fix direction: re-dispatch through `workflow_dispatch`, not a new mechanism

**Decision**: On `push`, the wrapper dispatches a fresh run of itself via
`gh workflow run wing-commander-rebase.yml` (`workflow_dispatch`) instead of
calling the reusable stage directly; the dispatched run's `rebase` job then
calls `uses: ./.github/workflows/rebase.yml` exactly as before.
`workflow_dispatch` is chosen because it is already proven, in this exact
repository, to reach a `claude-code-action` step successfully — `plan.yml`,
`tasks.yml`, `implement.yml`, and `finalize.yml`'s wrapper/stage pairs all
run their agent step under a `workflow_dispatch`-originated run today.

**Rationale**: Spec Assumptions name two acceptable directions: "re-dispatching
the push path through an event the agent already supports" or "running the
resolution step by a different mechanism for this one step." The first is
strictly simpler and stays inside FR-006's "wrapper only" scope, because it
reuses a chaining primitive `docs/architecture.md`'s "Identity & chaining"
section already documents as this pipeline's standard answer to "a stage
has no natural GitHub event": *"chaining is explicit via `gh workflow run`
(`workflow_dispatch`), which works regardless of token type."* The default
`GITHUB_TOKEN` is sufficient (the same doc: `GITHUB_TOKEN` events don't
trigger workflows except the documented `workflow_dispatch`/
`repository_dispatch` exceptions) — no App-token elevation needed for the
redispatch call itself, matching the existing `tasks.yml`→`implement`
pattern's own comment: *"Dispatching the implement wrapper uses the default
GITHUB_TOKEN... the wing-commander-bot App token has no actions
permission."*

**Alternatives considered**:
- *"A different mechanism for this one step"* — e.g. peeling the
  conflict-resolution step out of `rebase.yml`'s matrixed `rebase` job into
  a wholly separate reusable workflow reached by its own `workflow_dispatch`
  chain. Rejected: it necessarily touches `rebase.yml` (splitting a step out
  of an existing job, or adding a new job/output the caller must consume),
  which conflicts with FR-006/FR-007's requirement that this stay inside the
  wrapper and not require a published-contract change. It would also
  fragment the existing single-job scope-check/publish/escalate flow
  (rebase.yml's `verify`/`Publish rebased branch`/`Abandon and escalate`
  steps all key off the SAME job's `steps.attempt`/`steps.agent` outputs) —
  splitting the agent step into a different job/workflow run would require
  passing rebase state across a `workflow_dispatch` boundary that has no
  natural way to carry an in-progress `git rebase` working tree.
- *`repository_dispatch` instead of `workflow_dispatch`* — also exempt from
  the token-recursion restriction, but adds a webhook-shaped
  event/payload-type layer with no established precedent anywhere in this
  repository and no advantage over the already-adopted `workflow_dispatch`
  idiom.
- *Converting the wrapper's `push` trigger into a different GitHub event
  entirely (e.g. dropping `push` and relying on `schedule` only)* —
  rejected outright: FR-001 requires the push path specifically to reach
  resolution, and dropping `push` would silently regress the pipeline's
  fastest rebase cadence (today: on every push to main) down to once a
  night, which the spec's Edge Cases ("both triggers present... the
  resolution step must be reachable under both") explicitly forbids.

## R3 — Where the `push`-vs-everything-else split lives: two jobs, not one job with in-line branching

**Decision**: Split the wrapper's single `rebase` job into `redispatch`
(push-only) and `rebase` (schedule/workflow_dispatch-only, unchanged `uses:`
call), rather than keeping one job whose steps conditionally either call
`gh workflow run` or the reusable stage.

**Rationale**: A job's `uses: ./.github/workflows/X.yml` reusable-workflow
call cannot itself be made conditional at the step level — a job that
calls a reusable workflow can only contain that one call (GitHub Actions
requires a `uses:`-calling job to have no other job-level `steps:`). Two
jobs, gated by mutually exclusive `if:` conditions on `github.event_name`,
is therefore the only shape available, and it has a useful side effect:
each job's own `if:` line states machine-checkably (for Gate 6, R7 below)
and human-readably (for anyone reading the file) exactly which events reach
the agent-bearing call and which don't.

**Alternatives considered**: A single job with an early `run:` step that
exits 0 immediately when `github.event_name == 'push'` (skipping the
reusable-workflow call in effect but not in the job graph) — rejected;
GitHub Actions has no "skip the rest of this job but still evaluate a
later `uses:`" primitive mid-job, and simulating one would still require
the job to declare the `uses:` step, which unconditionally runs once the
job starts.

## R4 — Loop-guard placement: `redispatch` only, not `rebase`

**Decision**: The existing `!endsWith(github.actor, '[bot]')` bot-actor
loop guard moves onto the new `redispatch` job's `if:` (combined with
`github.event_name == 'push'`) and is dropped from the `rebase` job
entirely.

**Rationale**: The guard's documented purpose (the wrapper's own header
comment) is "a push made by the pipeline's own App identity... is skipped;
a scheduled run (never a bot actor) always proceeds" — it exists to stop a
bot-authored push to `main` from re-triggering another rebase cycle. That
concern is specific to the `push` event; it has nothing to do with
`schedule` (never a bot actor, the comment already says so) or
`workflow_dispatch` (not "someone pushed" at all — by the time a run
reaches `rebase` via `workflow_dispatch`, it's already past the one place a
bot-loop could start). Keeping the check on `rebase` too would be
redundant at best and, if the redispatching identity is ever itself
considered a "bot actor" by GitHub's actor-naming convention, wrongly skip
a real workflow_dispatch-originated resolution attempt.

**Alternatives considered**: Leaving the guard on both jobs "for safety" —
rejected as redundant given the reasoning above, and because FR-002
requires resolution behavior to be identical across triggers; an
accidentally-tripped actor check on the `rebase` job would silently
reintroduce a trigger-dependent difference the spec explicitly forbids.

## R5 — `rebase` job's `if:`: explicit allow-list, not an exclude-list

**Decision**: `if: github.event_name == 'schedule' || github.event_name ==
'workflow_dispatch'`, not `if: github.event_name != 'push'`.

**Rationale**: Both forms produce identical behavior today (the wrapper's
`on:` only ever declares `push`, `schedule`, and the newly-added
`workflow_dispatch`), but the allow-list form states positively, in the
file itself, exactly which events the agent-bearing call is proven to
support — matching this repository's own established convention (e.g.
`tasks.yml`'s `tasks-approved` job, `plan.yml`'s restart gate) of writing
`github.event_name == '<event>'` checks rather than negations. It also
gives Gate 6 (R7) a simpler, more reliable pattern to extract: an
allow-list's matched-event set *is* the reachable-event set directly,
whereas an exclude-list requires computing a set difference against
whatever the wrapper's `on:` happens to declare — correct either way, but
the allow-list form is less to get right in a regex-based static check.

**Alternatives considered**: The exclude-list form (`!= 'push'`) — not
wrong, and Gate 6 is designed to recognize both forms (research.md R7) so a
future contributor's choice either way still gets checked correctly; the
allow-list is preferred here for self-documentation, not because the
exclude-list would fail the gate.

## R6 — The supported-event set Gate 6 encodes

**Decision**: Encode a fixed, conservative allowlist inside Gate 6 itself:
`issues`, `issue_comment`, `pull_request`, `workflow_dispatch`,
`workflow_run`, `schedule`. `push` is deliberately absent (the confirmed
defect). Any event not on this list — including one that might genuinely
work but has no evidence of it in this repository — is treated as
unsupported until a maintainer adds it here with a reason, not inferred
from documentation this repository doesn't control.

**Rationale**: Spec Assumptions states the supported set is "a known, fixed
list (the settled constraint stated in the request)" and that "the new
static gate encodes that list." The request's own text only confirms one
fact precisely (`push` is unsupported); everything else has to come from
evidence this repository can actually check. Every event on the list above
is exercised against a real `claude-code-action` step by an existing,
currently-working wrapper/stage pair in this repository today: `issues` →
`intake.yml`; `issue_comment` → `clarify.yml`; `pull_request` →
`plan.yml`/`tasks.yml`/`cleanup.yml`; `workflow_dispatch` →
`plan.yml`/`tasks.yml`/`implement.yml`/`finalize.yml`; `workflow_run` →
`watchdog.yml`; `schedule` → `auto-update-spec-kit.yml`'s `evaluate-path`
job (reachable only when `health-check`'s `if: inputs.trigger == 'scheduled'
|| inputs.trigger == 'dispatch'` gate passes, which it does on the
wrapper's own `schedule`-triggered runs). This gives every list entry a
concrete, currently-green production reference rather than an assumption.
FR-010's "forward-looking" requirement is best served by a conservative
allowlist: a wrapper that later declares `pull_request_review`, `release`,
`create`, or any other event this repository has never actually run an
agent step under gets flagged and requires a deliberate addition to this
list (with its own evidence) rather than silently passing on the
possibility that it happens to work.

**Alternatives considered**: A hard-coded denylist of just `push` (the one
event known-bad) — rejected; it satisfies today's defect but not FR-010,
since Acceptance Scenario 4 explicitly requires catching "a *different*
unsupported event... not only push." An allowlist is the only shape that
is forward-looking by construction rather than by remembering to keep
extending a blocklist.

## R7 — Gate 6's job-reachability heuristic

**Decision**: For every job, in every workflow file, that has a step-level
`uses: ./.github/workflows/<stage>.yml` (the exact local-reusable-call
shape Gate 3 already detects), resolve `<stage>.yml` and check whether any
of its jobs contains a step whose `uses:` starts with
`anthropics/claude-code-action` (the same literal marker `release.yml`'s
existing agent-count grep already keys on: `grep -c 'uses:
anthropics/claude-code-action'`). If so, compute that calling job's
*reachable event set* from its own `if:` string (default: the wrapper's
full declared `on:` event set, if `if:` is absent or contains no
recognizable clause) by regex-extracting `github.event_name == '<event>'`
clauses (reachable = exactly the matched set, intersected with the
wrapper's declared events) and `github.event_name != '<event>'` clauses
(reachable = the full declared set minus the matched events); flag any
event in the reachable set that is outside R6's allowlist, naming the
wrapper file and the offending event(s) in the failure output (FR-011).

**Rationale**: This mirrors, deliberately, the static-analysis style
already established by Gates 2/3/5 in this same file — regex/structural
matching over the YAML the gate already parses, not a general GitHub
Actions expression evaluator. A full evaluator would be able to resolve
arbitrary boolean logic (`contains()`, nested `needs.*.outputs`, etc.)
correctly in every case, but nothing else in `lint-workflows.yml` attempts
that, and building one is disproportionate to a check whose job is to
catch the specific, recurring shape this repository's own wrapper
convention produces: an `if:` that either doesn't mention
`github.event_name` at all, or mentions it via a small number of `==`/`!=`
literal comparisons ORed/ANDed together (every existing example in this
repository's wrappers today fits that shape — see the grep evidence
collected for R6). The "no recognizable clause ⇒ assume every declared
event reaches this job" default is the safe direction to fail in: it can
only ever cause a false-flag (a maintainer investigates and finds the job
is actually fine, e.g. gated by something Gate 6 can't parse), never a
false-pass that lets a real unreachable-event defect through undetected —
consistent with a *safety* gate's job being to over-flag rather than
under-flag when its analysis is uncertain.

**Alternatives considered**:
- *Wrapper-file-level check (ignore per-job `if:` entirely; flag whenever
  the wrapper's `on:` set contains an unsupported event and ANY job in the
  file calls an agent-bearing stage)* — rejected. This is exactly the
  design this feature's own fix would fail under: the fixed
  `wing-commander-rebase.yml` still declares `push` in `on:` (the
  `redispatch` job needs it), and a file-level check with no per-job
  reachability analysis would flag the wrapper forever after the fix ships,
  producing a permanent false positive on the very file this feature
  exists to fix.
- *Full GitHub Actions expression parser (real boolean-expression AST,
  handling `contains()`, `needs.*`, arbitrary nesting)* — rejected as
  disproportionate; nothing else in `lint-workflows.yml` does this, it adds
  meaningfully more code and maintenance surface for cases this
  repository's wrapper conventions don't currently produce, and the
  conservative "unparseable ⇒ assume reachable" fallback already covers the
  correctness gap safely (over-flag, never under-flag).

## R8 — Gate 6's scope boundary: the wrapper↔stage pattern only, not every agent-bearing file

**Decision**: Gate 6 only examines files reachable through a
`uses: ./.github/workflows/<stage>.yml` job (Gate 3's existing detection
shape). `claude.yml` (currently `if: false`, fully disabled) and
`claude-code-review.yml` (a standalone PR-review helper that embeds
`claude-code-action` directly, with no wrapper/stage split) are out of
scope.

**Rationale**: The spec's Key Entities define exactly this two-layer shape
— "Auto-rebase wrapper: the repository-owned workflow that triggers the
reusable rebase stage; its declared triggering events determine what event
the stage's agent step observes" — and generalize it in User Story 2 to
"any future wrapper," consistently phrased in terms of a wrapper that
"triggers the reusable stage." `claude.yml`/`claude-code-review.yml` don't
participate in that architecture (constitution VII's wrapper/published-stage
split); they're single-file, self-contained workflows with their own
directly-declared triggers and no resolved stage to check separately. Both
already only declare events already on R6's supported list in practice
(`claude-code-review.yml`: `pull_request`; `claude.yml`: disabled), so
scoping Gate 6 to the wrapper/stage pattern doesn't leave a live gap for
either file today, and it keeps the gate's model exactly matched to what
the spec actually describes.

**Alternatives considered**: Scanning every workflow file for a
`claude-code-action` step directly and checking its own file-level `on:`
regardless of the wrapper/stage split — rejected as broader than FR-008
through FR-011 ask for (they're written entirely in terms of "a wrapper's
resolved stage," not "any file with an agent step"), and it would require
Gate 6 to also reason about `claude.yml`'s `if: false` disablement (a
different kind of gate than an event-type check) to avoid a false positive
there.

## R9 — Documentation updates travel with the code, not deferred

**Decision**: `docs/architecture.md`'s "Rebase" section and
`docs/adoption.md`'s §8 copy-paste wrapper template are updated in the same
change, even though no functional requirement names either file directly.

**Rationale**: `docs/adoption.md` §8 is not just descriptive prose — it is
literally the YAML an adopter copies verbatim into their own repository
("Copy these eight files into `.github/workflows/`"). Left unchanged, it
would keep shipping every new adopter the exact defect this feature fixes,
the moment after this feature ships. `docs/architecture.md`'s "Trigger:
push to main... + nightly schedule" line would become actively wrong
(silent about the new `workflow_dispatch` redispatch hop) the moment the
wrapper changes shape. Both updates are mechanical deltas mirroring the
code change, not new scope.

**Alternatives considered**: Deferring documentation updates to a follow-up
— rejected; this repository's own constitution amendment history
(constitution.md's Sync Impact Reports) treats "the doc is what an adopter
reads" as a reason to update documentation in the same change rather than
defer it, and `docs/adoption.md` §8 specifically is adopter-facing code,
not narrative documentation that can safely lag.
