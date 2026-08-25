# Phase 0 Research: The Post-Review Fold Loop

spec.md carries no literal `[NEEDS CLARIFICATION]` markers — all three that
existed during intake were resolved on the lifecycle issue and folded into
the spec itself (checklists/requirements.md's Notes section). What remains
for planning is translating FR-001–FR-021 into concrete edits against the
three files spec.md names: `.github/workflows/pr-conversation.yml`,
`.github/workflows/finalize.yml`, and `.github/workflows/implement.yml`
(plus their published contracts and coverage). Each decision below cites
the exact current structure it changes.

## D1 — Fold-then-dispatch-once: keep the matrix, split dispatch into a new job that runs after it

**Decision**: `pr-conversation.yml`'s `act` job (1308–2283) keeps its
existing shape — a `strategy.matrix` over `classifications`,
`max-parallel: 1`, one leg per classified item, folding its item into
`tasks.md`/`spec-meta.json` exactly as it does today via "Act on this
classification" (1703–1802). What changes: the per-leg step "Dispatch
implement and reply (fold-in routes)" (1982–2046) is split in two. The
*reply* half stays in the leg (renamed "Reply confirming fold-in (no
dispatch)") — it posts a per-item comment confirming the item folded and
will be picked up by the pipeline's next cycle, but never calls
`gh workflow run`. The *dispatch* half moves to a **new job**,
`dispatch-once`, `needs: [classify-and-announce, act]`, `if: always()` (so
it still runs when some legs failed/were cancelled — FR-005a, FR-006),
which checks the branch tip after the whole matrix has finished and issues
**at most one** `gh workflow run` for the entire review.

**Rationale**: The matrix already serializes legs (`max-parallel: 1`,
deliberately — the comment at 1203–1216 says two legs "would race each
other on commit+push"). "Fold ALL legs before ANY dispatch" (FR-001) falls
out for free once dispatch is no longer a per-leg step: by the time
`dispatch-once` runs, every leg has already run to completion (or died
trying), in the matrix's own serial order. This is the smaller of the two
shapes spec.md's own Assumptions section allows ("a single act job over the
classified set, or serialized legs with dispatch deferred to the last") —
it reuses the existing per-leg confirm/environment-gating machinery
(specs/033) untouched, rather than restructuring classification into a
single non-matrix job.

**Alternatives considered**:
- *Collapse the matrix into one job that loops over classifications in a
  single agent invocation* — rejected: throws away the per-leg
  `environment:` binding that gates confirm-required items
  (`matrix['confirm-environment']`, 1393–1395), which cannot be expressed
  for an arbitrary subset of one job's own loop iterations without
  re-inventing what GitHub's matrix+environment combination already gives
  for free.
- *Have the last leg to run perform the dispatch* — rejected: "last" is
  only knowable by an ordinal position in the matrix, which a leg cannot
  itself observe cheaply, and it does not change the actual defect (a
  leg's own job still both folds and dispatches, still joining the group
  its own dispatch creates contention in — see D2). Moving dispatch out of
  every leg into a job that starts only once the matrix has fully
  completed is what removes the contention, not which leg happens to run
  last.

## D2 — Concurrency: `act` keeps the canonical group (FR-004a needs it); `dispatch-once` joins it only after `act` has released it

**Decision**: `act`'s concurrency group is unchanged —
`wing-commander-${SPEC_DIR}` for any run with at least one mutating leg
(1237–1241), the same canonical per-spec group `implement.yml` uses
(`implement.yml:374,1865`). `dispatch-once` also joins that same group
(`concurrency: { group: wing-commander-${{ needs.classify-and-announce.outputs.spec-dir }}, cancel-in-progress: false }`),
but because it `needs: act`, GitHub does not evaluate — let alone attempt
to enter — its concurrency group until `act`'s job has fully finished
(succeeded, failed, or been cancelled) and released its own hold on the
group. There is therefore no window in which `act` (still holding the
slot) and the run `dispatch-once` starts (which will itself try to join
the same slot) are both live at once — the exact shape that let leg 4 and
iteration 3 cancel each other on PR #240.

**Rationale**: `act`'s membership in `wing-commander-${SPEC_DIR}` is not
incidental — it is what makes FR-004a's "wait for the in-flight
implementation cycle" work today (see the T072 comment at 1220–1236,
inherited from specs/033's own D6: "that leg genuinely does need
serializing against plan/tasks/implement/finalize/rebase"). Removing `act`
from that group to stop it contending with its own dispatch would also
remove the wait that makes a review arriving mid-cycle queue instead of
racing it (Edge Case: "An implementation cycle for the same specification
is already running when a review arrives"). Keeping `act` in the group and
only sequencing `dispatch-once` strictly after it — rather than moving
`act` out — satisfies FR-004 ("the act pass MUST NOT contend for the same
serialization slot as the implementation cycle it dispatches") without
touching FR-004a's mechanism at all: they turn out to be the same fix.

**Alternatives considered**:
- *Give `act` a new, review-scoped group distinct from
  `wing-commander-${SPEC_DIR}`* — rejected: this is what the "stop" path
  already does deliberately (1220–1241) for the opposite reason — a stop
  request must NOT wait behind the run it targets. A mutating review
  legitimately does need to wait behind an in-flight cycle (FR-004a), so
  the canonical group is the correct one to keep, not one to escape.
- *Have `dispatch-once` skip the concurrency group entirely, relying on
  `needs: act` alone for ordering* — rejected: `needs:` only orders
  `dispatch-once` after `act`'s own matrix, not against a *second*
  `pr-conversation` run's `act` job for the same spec-dir (e.g. two
  reviews arriving close together — Edge Case "A second review arrives
  while the first is still folding"). Keeping `dispatch-once` in the
  canonical group is what keeps two reviews' dispatches from racing each
  other's `gh workflow run` calls.

## D3 — "Did anything fold" is read from the branch, not aggregated from matrix step outputs

**Decision**: `classify-and-announce` gains one new output, `base-sha` —
captured by a new step near the end of that job (after `identity` has
resolved `spec-dir`/`slug`), reading
`git ls-remote origin "refs/heads/${SPEC_PREFIX}$SLUG" | cut -f1` (empty
string if the branch does not exist yet, which cannot happen here since
`pr-conversation` only runs against a PR whose spec branch already exists).
`dispatch-once` checks out that same ref fresh once `act` has finished and
compares the tip SHA to `base-sha`: unchanged means no leg folded anything
(all held/failed/questions/notes) and nothing is dispatched; changed means
at least one leg committed, and `dispatch-once` reads the current
`spec-meta.json` iteration from that tip to compose its single
`gh workflow run` call.

**Rationale**: GitHub Actions matrix jobs have no native fan-in for step
outputs across parallel (or, here, serialized-but-still-per-instance)
matrix instances — a `needs: act` job cannot read "how many of the five
legs folded" from `act`'s own `outputs:` block. The branch itself is
already the authoritative record of what folded (every leg's fold is a
single commit+push, 1744–1754), so reading its tip once, after the whole
matrix has finished, is simpler and more trustworthy than inventing a
cross-instance aggregation mechanism (e.g. a `GITHUB_STEP_SUMMARY` parse or
a repository-variable counter) that FR-006a's "not suppressible by a dead
leg" concern would apply to as well.

**Alternatives considered**:
- *Each leg appends its own identifier to a job artifact, downloaded and
  unioned by `dispatch-once`* — rejected: a cancelled leg never reaches the
  upload step, so the artifact would only ever prove the healthy subset,
  not the "was anything folded at all" question `dispatch-once` actually
  needs answered, and adds an artifact-storage dependency for a fact
  already visible in git history.
- *Count classifications with `mutated=='true'` via
  `needs.classify-and-announce.outputs.classifications`* — rejected: that
  output is the *pre-run* classification set (what was announced), not
  what actually landed; a leg that was announced then cancelled would
  still count as mutating under this scheme, which is exactly the
  over-counting FR-006a warns against.

## D4 — A held leg does not block dispatch: the existing leg ordering already provides "dispatch what's ready"

**Decision**: No new logic is needed for US1 AS5 ("held items still fold;
dispatch waits for the held leg to resolve") beyond D1/D3 themselves.
specs/033's existing `sort_by` (1203–1216) already orders every
non-confirm-gated leg ahead of every confirm-gated one specifically so a
held leg does not occupy the matrix's single slot before ready items get
theirs. Combined with D1 (`dispatch-once` runs `if: always()` once the
*whole* matrix concludes, whether by success or by one leg's timeout/
cancellation) and D3 (dispatch reads whatever the branch tip shows), a
review with one held leg and two ready ones already dispatches after the
two ready folds land, once the matrix job as a whole finishes — resolved
either by the held leg's approval or by its bound expiring (D5).

**Rationale**: This is the one FR the existing specs/033 architecture
already half-solves; recognizing that avoids adding a second, redundant
"wait for ready items, then dispatch separately from held ones" mechanism
that would have to reimplement what the matrix ordering plus `if: always()`
already gives.

**Alternatives considered**: None — this decision exists to record that no
alternative design was needed, not to choose between competing ones.

## D5 — A held leg's wait is bounded by `timeout-minutes` on the `act` job, a new configurable input

**Decision**: `act` gains `timeout-minutes: ${{ inputs.confirm-timeout-minutes }}`,
a new `workflow_call` input, `confirm-timeout-minutes` (`number`, default
`1440` — 24 hours, chosen to comfortably exceed a maintainer's working day
without leaving a held review pending for days by default; adopter-
configurable per constitution VI/portability). GitHub Actions cancels a
job that exceeds its `timeout-minutes` outright, including one still
waiting on an `environment:` deployment-protection-rule approval — so a
held leg whose confirmer never responds is cancelled by the platform
itself once the bound expires, without any new polling logic. Because
`timeout-minutes` is job-scoped, it applies uniformly to every leg in the
matrix, including non-held ones — which is harmless, since a non-held leg
completes in the run's ordinary timeframe, far under any reasonable bound.

**Rationale**: FR-005a requires the wait be bounded, but nothing in the
spec's Assumptions section prescribes a mechanism. `timeout-minutes` is the
one primitive GitHub Actions offers that terminates a job stuck on an
`environment:` approval without the pipeline needing to poll for it, and
it composes with D6 for free: a leg cancelled this way is indistinguishable,
from `report-fold-outcomes`'s point of view, from a leg cancelled by
concurrency contention — both are "terminated without folding," and both
get FR-006's outcome comment naming the item.

**Alternatives considered**:
- *A deterministic polling step that checks elapsed wall-clock time and
  self-cancels via the GitHub API* — rejected: strictly more code to
  reproduce a bound `timeout-minutes` already enforces natively, and a
  self-cancel-via-API step is itself a step that could fail to run.
- *Bind the timeout to the specific confirm-gated leg only, via a
  per-matrix-instance override* — rejected: GitHub Actions'
  `timeout-minutes` is a job-level key, not overridable per matrix
  instance; applying it job-wide is correct here since non-held legs are
  never at risk of hitting it.

## D6 — Leg-death reporting: a new job cross-references the run's own job conclusions against git evidence, never a value the dead leg would have published

**Decision**: `pr-conversation.yml` gains a second new job,
`report-fold-outcomes`, `needs: [classify-and-announce, act]`,
`if: always()`. It:
1. Assigns each classified item a stable `id` at classification time
   (a small addition to the jq pipeline around 1194–1201:
   `to_entries | map(.value + {id: ("leg-" + (.key | tostring))})`,
   applied before the existing `sort_by`, 1216, so `id` survives
   reordering).
2. Gives the matrix job an explicit per-instance name,
   `name: "act (${{ matrix.id }})"`, so each leg's GitHub Actions job is
   identifiable by `id` in the run's own job list.
3. Fetches this run's own jobs via the paginated
   `gh api repos/$REPO/actions/runs/$RUN_ID/jobs --paginate`
   (Gate 18's established paginated-read shape), reading each `act (leg-N)`
   entry's `conclusion` — a value GitHub itself sets for every job
   including a cancelled one, never a value the leg's own steps had to
   publish (FR-006a).
4. Independently checks the branch (at the tip `dispatch-once` also reads)
   for evidence the item's `id` was actually folded — each leg's fold
   commit message is extended to carry the item's `id`
   (`fold(leg-N): <summary>` instead of today's unlabeled implement-stage
   commit), so a `git log --grep` against the range since `base-sha`
   answers "did this specific item land" without depending on the leg's
   own runtime output either.
5. For every announced (non-`no-action`) item whose job conclusion was not
   `success`, or whose `id` is absent from the fold evidence: posts **one**
   PR comment listing every such item, distinguishing "not folded" (no
   fold evidence) from "partly folded" (fold evidence present, but the
   job's own conclusion was not success — meaning the commit landed but
   something after it, e.g. the confirmation reply, did not complete
   cleanly) — see data-model.md's outcome table. When every announced item
   folded cleanly, the step posts nothing (US2 AS5 — silent on the healthy
   path).

**Rationale**: FR-006a forbids the outcome report depending on "any value
the terminated leg failed to publish." A cancelled leg's own step outputs
are exactly such a value — cancellation can strike at any point, including
before the leg ever wrote anything. Job `conclusion` (set by the GitHub
Actions platform for every job that starts, success or not) and git
history (a durable side effect independent of whether the leg's process
survived to report on itself) are the only two signals that satisfy that
constraint. Cross-referencing both, rather than trusting either alone,
also yields the "not folded" vs. "partly folded" distinction FR-006a's
sibling (US2 AS2) explicitly asks for.

**Alternatives considered**:
- *Have each leg write its own "I folded" marker as its very last step,
  and treat a missing marker as failure* — rejected: this is exactly the
  self-reporting FR-006a excludes — a leg cancelled between the fold commit
  and the marker write would report "not folded" for an item that in fact
  landed, undercutting the "partly folded" distinction entirely.
- *Poll `gh run view` for the leg's own step-level conclusions instead of
  the job-level jobs API* — rejected: step-level status for a matrix leg
  is not separately queryable without first resolving the job id, which
  the jobs API (step 3 above) already returns as part of the same call;
  no extra API surface is needed.

## D7 — Finalize's guard becomes tri-state (none / open / merged-or-closed), not a boolean skip

**Decision**: "Check for an existing final pull request" (`finalize.yml`
542–557, `id: guard`) widens its `gh pr list` call to
`--json number,state,url` and sets a new output, `pr-state`
(`none` | `open` | `merged` | `closed`), instead of the current boolean
`skip`. Every downstream step currently gated on
`steps.diff.outputs.skip != 'true'` (566–586 threads `skip` through as
`steps.diff.outputs.skip`) is regated on
`steps.diff.outputs.pr-state != 'merged' && steps.diff.outputs.pr-state != 'closed'`
— i.e. it now runs for **both** `none` (today's create path, unchanged
behavior) and `open` (the new refresh path). A `merged` or `closed`
`pr-state` reports a distinct message on the lifecycle issue (new step,
gated on exactly those two states) naming which of the two it found
(FR-009, FR-009a), where today's guard only writes a step-summary line and
never reaches the issue at all.

**Rationale**: Today's guard answers one question ("does a PR exist") with
one bit; this feature needs to answer three ("none, open, or done") to
route to create, refresh, or no-op respectively, per FR-008/FR-009/FR-009a.
Reusing the *existing* downstream steps' gating — widening their `if:`
rather than duplicating them into a parallel "refresh" copy — is what
lets D8 below reuse almost all of them unmodified.

**Alternatives considered**:
- *Two separate boolean outputs, `exists` and `is-open`* — rejected:
  `merged` and `closed` still need to be distinguished from each other for
  FR-009 vs. FR-009a's separately-worded reports, so two booleans would
  still need a third signal; one four-valued output is simpler to reason
  about and to gate on.

## D8 — Refresh reuses the create path's own steps by widening their `if:`, rather than duplicating them

**Decision**: "Assemble PR body" (806–849), "Flip stage label" (913–939),
"Commit metadata (stage → review)" (955–971), and "Announce for review"
(944–953) all already do exactly what FR-008 requires on the *create*
path today — they just currently only run once, gated by
`skip != 'true'`, which was only ever true for `none`. Re-gating them
(D7) to also run for `pr-state == 'open'` gets the record commit, the
label restore, and the re-review-adjacent announcement for free on a
refresh, with no new steps for those three effects. Only two steps
change shape rather than gating: "Open the final PR" (860-ish, currently
unconditionally `gh pr create`) becomes "Open or update the final PR" —
branches on `pr-state`: `none` → `gh pr create` exactly as today; `open`
→ `gh pr edit "$EXISTING_PR" --body-file ...` against the PR number the
guard already read. "Assemble PR body" itself gains the machine-owned
region logic (D9) only when `pr-state == 'open'` — the `none` path's body
assembly is unchanged, since there is no prior body to preserve prose
from.

**Rationale**: This is the smallest diff that satisfies FR-008 without
inventing parallel plumbing: the create path already proves each of these
side effects works (they ship today); reusing them for the refresh path
means a regression in, say, the label-restore logic is a single piece of
code to break, not two to keep in sync (the same "don't duplicate what's
already trusted" reasoning D1 applies to `act`'s fold logic, and D8
applies here to finalize's existing steps).

**Alternatives considered**:
- *A parallel "refresh" job, entirely separate from the create job* —
  rejected: doubles the surface FR-016/FR-017 requires stay quiet and
  unchanged on the create path, and risks the two copies drifting (the
  exact failure mode constitution VIII exists to prevent — "a check that
  cannot fail its own subject").

## D9 — The PR body's machine-owned region: HTML-comment delimiters, a regenerated state block, and an append-only fold log — the same idiom `auto-update-spec-kit.yml` and `rebase.yml` already use for machine-owned PR/issue content

**Decision**: "Assemble PR body" writes (or, on refresh, rewrites) a
delimited region:

```
<!-- wing-commander-finalize:state:begin -->
... regenerated state block (branch, iteration, task counts) ...
<!-- wing-commander-finalize:state:end -->

<!-- wing-commander-finalize:fold-log:begin -->
- Fold (2026-08-24, review by @alice, #240): 3 items folded — <summary>.
- Fold (2026-08-25, review by @bob, #248): 1 item folded — <summary>.
<!-- wing-commander-finalize:fold-log:end -->
```

On the `none` path this is written fresh with zero fold-log entries. On
the `open` path, "Assemble PR body" first fetches the existing PR's body
(`gh pr view "$EXISTING_PR" --json body`), preserves everything **outside**
the `state:begin`…`fold-log:end` span byte-for-byte (FR-008b — prose a
human wrote there survives), **discards** whatever currently sits between
the delimiters (regenerating the state block and re-parsing only the
*existing* fold-log entries out of the old fold-log span, via the same
`grep -o`/`sed` extraction idiom `rebase.yml:493–507` and
`auto-update-spec-kit.yml` (marker lines throughout) already use), and
**appends** one new fold-log entry only if this fold has not already been
recorded (D9a, idempotency).

**Rationale**: Neither full regeneration (loses the fold history a
re-reviewing maintainer needs — spec.md's own Assumptions: "a
re-reviewing maintainer reads two things: what is on the branch now, and
what changed in the round they asked for") nor pure append-only (never
refreshes the stale state block) alone satisfies FR-008a; the spec names
both parts explicitly. Delimited HTML comments are this repository's
established idiom for "this region is machine-owned, don't hand-edit it"
(`auto-update-spec-kit.yml`'s per-PR markers, `rebase.yml`'s blocked-branch
marker) — reusing it here rather than inventing a new markup convention
keeps every machine-owned region in the pipeline parseable by the same
grep/sed pattern.

**Alternatives considered**:
- *A single flat marker (state only, no fold log)* — rejected per FR-008a's
  explicit two-part requirement.
- *Store the fold log outside the PR body (e.g. in `spec-meta.json`) and
  render it into the body every time* — rejected: FR-008a specifically
  frames the fold log as PR-body content a maintainer reads in place; a
  second source of truth to keep synced would be exactly the kind of
  drift constitution VIII's prior-art list warns about, for no benefit
  over reading the existing rendered entries back out of the body itself.

### D9a — Idempotent fold-log append: keyed by the branch SHA the fold responded to

**Decision**: Each fold-log entry embeds the branch tip SHA finalize is
refreshing against (`- Fold (<date>, review by <reviewers>, #<issue>) <sha>: ...`,
the SHA rendered short but present in the text so it is greppable).
Before appending, "Assemble PR body" checks whether the most recent
existing fold-log entry already carries the current tip SHA; if so, it
appends nothing (FR-010a — a repeat finalize run with no intervening fold
is a no-op on the body).

**Rationale**: FR-010a requires repeated finalize runs to accumulate
nothing when nothing changed. The branch tip SHA is already unique per
distinguishable state change (spec.md's own working assumption throughout
this pipeline: a commit is the unit of "something happened"), so keying on
it is simpler than introducing a separate fold-counter field.

## D10 — Re-review reviewer identity: captured at fold time into `spec-meta.json`, read by finalize, PR review records as fallback

**Decision**: `spec-meta.json` gains one new field,
`pending_re_review_from` (array of logins, absent/empty by default).
`pr-conversation.yml`'s `dispatch-once` job (D1) — the one place a
review's own `inputs.actor-login` (already an input to the whole workflow,
documented "display only" at line 39) is available *and* known to have
resulted in an actual fold — records that login into this field as part of
the same commit "Act on this classification" already makes (union with any
existing pending entries, so two reviews folded before a finalize run both
get their re-review requested — FR-008's "if several reviewers requested
changes... all of them are asked"). `finalize.yml`'s refresh path reads
this field to request re-review (`gh pr edit "$EXISTING_PR" --add-reviewer <logins>`,
best-effort — failures reported per FR-010b, never failing the job) and
clears it once the request is issued (or attempted), so a second finalize
run with no intervening fold does not re-request (FR-010a). When the field
is absent (a spec whose branch predates this feature, or whose folds all
came from a mechanism that never wrote it), finalize falls back to reading
the PR's own review records
(`gh pr view "$EXISTING_PR" --json reviews --jq '[.reviews[] | select(.state=="CHANGES_REQUESTED") | .author.login] | unique'`)
— satisfying FR-008's "either/or" wording literally, with the lifecycle
record as the primary, more precise source (it names the review that
*actually* triggered *this* fold, where the PR's live review state could
have since changed — dismissed, superseded by a newer review) and the PR's
own records as the documented fallback.

**Rationale**: FR-008 explicitly forbids reading identity "from ambient
event state" but permits either the PR's own review records or the
lifecycle record — and no code anywhere in the pipeline reads PR review
records today (confirmed: zero `reviews`/`requested_reviewers` call sites
repo-wide). Writing the identity once, deterministically, at the moment
it is known with the most precision (the fold that answered it) is more
robust than re-deriving it later from possibly-stale PR state, and gives
finalize a source it can read without a new PR-records API path unless it
needs the fallback.

**Alternatives considered**:
- *Read PR review records exclusively, never write to `spec-meta.json`* —
  rejected: a review can be dismissed or superseded between the fold and
  the finalize run that reports on it, and FR-008's naming ("the review it
  answers") is more precise when captured at the moment the fold actually
  happens rather than reconstructed later from whatever the PR's review
  list looks like by then.

## D11 — Deletion capability: two literal edits to `implement.yml`, both call sites, no new guardrail step

**Decision**: `Bash(git rm:*)` is added to both `default-allowed-tools`
literals: `implement.yml:725` (`implement.cycle`) and `implement.yml:1086`
(`implement.retry`). No third call site exists for convergence — research
confirms both cycle and retry already run `/speckit-converge` as step 3 of
the *same* agent prompt/tool grant (798–803, 1184–1189) — so this single
two-line edit satisfies FR-012 ("the cycle, its retry, and the convergence
pass alike... MUST NOT diverge") by construction, not by separately
editing a third site. `stage-interfaces.md`'s two corresponding table rows
(248–294, `implement.cycle`/`implement.retry`) gain the same grant.

**Rationale**: `git rm` on a tracked file inside the already-checked-out
spec branch is confined the same way every other write verb this stage
grants is confined — by the single-branch checkout (554–561) and the
existing prompt-level "commit and push ONLY to the spec branch" discipline
(806–809, 1192–1195); no *new* guardrail is warranted because none of the
existing write verbs (`Write`, `Edit`, `Bash(git commit:*)`) has one either
— FR-013 requires the removal be "governed by the same constraints," which
this literally is, by sharing the identical tool-composition call site.
`git rm` also naturally refuses to touch an untracked file (it errors,
which the agent already surfaces as "remaining manual work" for any
command it cannot complete) — so FR-011a's "tracked files only" boundary
requires no separate check; it is `git rm`'s own semantics.

**Alternatives considered**:
- *A new composite action wrapping `git rm` with an explicit path-scope
  check* — rejected: no existing write verb has a dedicated wrapper either
  (Write/Edit/git commit are bare tool grants), and adding one here alone
  would be an inconsistent, unrequested hardening of exactly one verb
  while leaving the others as they are — the constraints this feature must
  satisfy already hold without it.
- *Grant `rm` (not `git rm`) for broader deletion power* — rejected
  explicitly by FR-011a and Out of Scope ("A general removal capability...
  deferred until a real task demonstrates the need"); `git rm` is scoped to
  what the repository's git index already tracks, `rm` is not.

## D12 — Contract enforcement: Gate 27 already does what FR-014 requires; no new gate needed for the tool-list widening

**Decision**: No new gate is added for the deletion capability. Gate 27
(`lint-workflows.yml:2730–2734`, `verify-stage-tool-lists.py`) already
parses every `wing-commander-tool-args` call site's literal
`default-allowed-tools` and cross-checks it against
`stage-interfaces.md`'s table; per D11, editing both `implement.yml` call
sites *and* leaving the table stale would make Gate 27 fail on the very
next lint run — this is FR-014's required check, already wired, already
passing today for the existing (unwidened) lists. Editing both the call
sites and the table row in the same change keeps it green.

**Rationale**: Constitution VIII: a gate that already fails its own
subject and is already reachable through the registry is coverage; writing
a second gate to check the same fact again would be exactly the
duplication constitution VIII's own prior-art list warns against
producing drift between two checkers of one fact.

## D13 — Two new gates for the genuinely new behavior: fold-then-dispatch-once/leg-death-reporting, and finalize refresh

**Decision**: Two new `.github/scripts/verify-*.py` gates, numbered from
the next unused slot. `.github/workflows/lint-workflows.yml`'s highest
`Gate N —` in use today is **Gate 33** (`lint-workflows.yml:2836`,
`verify-chain-stop-notice.py`, from specs/041) — gate numbers 22 and 23
are each used twice (an acknowledged, documented collision at
2714–2718), so "highest number in use" (33), not "count of distinct
gates," is the correct anchor. This feature's two new gates are numbered
**34** and **35** here; the actual numbers assigned may drift by the time
this merges (Gate 33's own comment: "gate numbers are assigned at merge
time... drift from plan-time citations is normal/expected") and MUST be
confirmed against the shipped file at implementation time, not assumed
from this document.

- **Gate 34** — `verify-fold-dispatch-once.py`, covering `pr-conversation.yml`'s
  `dispatch-once` and `report-fold-outcomes` jobs (D1, D3, D5, D6) via
  `wc_shell_harness.py` against the shipped `run:` blocks, following the
  env-substitution-for-upstream-outputs shape Gate 14/Gate 30 already
  establish (no need to re-run the classify/announce/agent-fold steps
  themselves — those are proven by specs/033's own Gate 7/Gate 13 coverage,
  unmodified by this feature).
- **Gate 35** — `verify-finalize-refresh.py`, covering `finalize.yml`'s
  tri-state guard (D7) and refresh path (D8/D9/D9a/D10), following
  `verify-stall-restart-runbook.py`'s (Gate 14) real-git-repo-plus-bare-
  remote shape — needed here specifically because the idempotent
  fold-log append (D9a) has a real commit/push and a real existing-body
  read/write side effect that a transcript-only harness cannot exercise
  honestly.

Both are wired into `lint-workflows.yml` by the same filename convention
`wc_gate_registry.py` already uses (Gate 10, unmodified, continues to
assert both directions of "every check is wired" — FR-020). Every `if:`
this feature adds at the job-`needs:` level (`dispatch-once`,
`report-fold-outcomes`, both `if: always()`) uses a status-check function
Gate 15 (the job-suppression gate, FR-021) already recognizes, so Gate 15
itself needs no widening; `finalize.yml`'s new `pr-state`-based
conditions are step-level (`steps.guard.outputs.pr-state`), not job-level
`needs.*` comparisons, so they fall outside Gate 15's `needs:`-graph walk
entirely and likewise require no change there.

**Rationale**: Constitution VIII (every shipped failure branch covered by
a checked-in fixture, not a manual demonstration) and FR-018/FR-019/FR-020
directly require this. Splitting by workflow (one gate per file this
feature changes non-trivially) mirrors the existing one-gate-per-
behavioral-change convention (Gate 25 for lifecycle-gate-retry, Gate 30 for
truncated-cycle-carry-forward, Gate 33 for chain-stop-notice) rather than
one oversized gate spanning both files.

**Alternatives considered**:
- *One combined gate for both workflows* — rejected: `pr-conversation.yml`
  and `finalize.yml` are edited independently (different jobs, different
  files, different fixture shapes — synthetic run-jobs-API responses vs. a
  real git repo), and a single script covering both would fail constitution
  VIII's "triggered by changes to the tree or document it checks" more
  awkwardly than two scripts each scoped to one file's path trigger.
