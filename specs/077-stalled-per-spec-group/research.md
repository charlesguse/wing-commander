# Phase 0 Research: The Stall Mark Waits Its Turn

Spec.md's own Resolved Clarifications section already closes every
`[NEEDS CLARIFICATION]` marker this feature opened (Q1–Q3, answered on
#581). What remains for this phase is the plan-level design the spec
explicitly defers: "How the prerequisite job is wired, which expressions
carry which values, and what the rewritten comments say are decisions for
the plan stage." Nothing below is a guess at unclarified *behaviour* — it is
the mechanical shape that satisfies FR-001–FR-019 as written.

## D1 — `resolve-identity` is today's identity step, relocated verbatim, not redesigned

**Decision**: The new prerequisite job's single step is `classify-and-announce`'s
current "Resolve PR identity and check qualification" step (lines 464–529 of
`pr-conversation.yml` as of this plan), moved into its own job with no logic
change:

- On an unreadable `default_branch`/`base_ref`/`head_ref` (`gh` returned
  empty for any of the three), it already does exactly what FR-005 asks:
  `::error::`, write `reason`, `exit 1` — no swallowing.
- On a readable-but-non-qualifying head ref, it already does exactly what
  FR-007 asks: `qualifies=false`, empty `slug`/`spec-dir`, a step-summary
  line, **no** `exit 1` — the job stays green.

This means `resolve-identity`'s outputs are `qualifies`, `slug`, `spec-dir`,
`default-branch` (renamed from `steps.identity.outputs.*` to
`needs.resolve-identity.outputs.*` at every call site), plus `reason` for
symmetry with `plan.yml`/`tasks.yml`'s `resolve-spec` job (unread by any
downstream job today, since `classify-and-announce` is skipped outright
whenever `resolve-identity` fails — the `::error::` annotation on the failed
job is the visible signal, matching `resolve-spec`'s own precedent of having
"no addressable destination for the note").

`classify-and-announce` loses this step entirely, and with it the
"Report identity-resolution refusal on the PR" callout that only that step's
`refused` output could trigger — that callout can never fire once the check
it depended on lives in a job that runs *before* `classify-and-announce`
even starts. This is not a silent regression: Story 2 and FR-006 already
specify the replacement path — when `resolve-identity` fails, the survivor
job's stall notice (D2 below) is what tells the maintainer, posted to
`inputs.pr-number` exactly as the deleted callout used to post.

`classify-and-announce`'s job-level `refusal-reason` output
(`${{ steps.identity.outputs.reason || steps.preflight.outputs.reason || steps.meta.outputs.reason }}`)
drops its first term, becoming
`${{ steps.preflight.outputs.reason || steps.meta.outputs.reason }}` — the
preflight and spec-meta refusals are untouched by this feature (FR-014) and
still report themselves in-job exactly as today.

**Why not fold `qualifies`-checking logic differently, or split it into two
jobs (a pure-string one plus an API one)?** Splitting further would add a
second cross-job hop for no behavioural gain — the whole point of
`resolve-identity` existing is that a job-level `concurrency:` block cannot
read a *step* output of its own job, not that any particular sub-computation
is expensive or independently reusable. One job, one step, moved wholesale,
is the smallest change that satisfies FR-001 (declare identity as job
outputs before both `classify-and-announce` and `stalled`) and FR-012 (one
home for the derivation).

**Alternatives considered**:
- *Keep the step in `classify-and-announce` and have `stalled` read
  `needs.classify-and-announce.outputs.spec-dir` directly* — this is exactly
  the shape spec.md's Context section rules out: `classify-and-announce` is
  by construction the job that did not run whenever `stalled` runs, so its
  outputs are unconditionally empty in every case `stalled` needs to handle.
- *Give `resolve-identity` its own `gh` retry loop instead of failing on the
  first empty read* — out of scope; the step it replaces has never retried,
  and adding retry behavior here is an unrelated improvement this feature
  was not asked to make.

## D2 — Permissions: read-only, no secrets, no checkout

**Decision**: `resolve-identity` declares
`permissions: {pull-requests: read, contents: read}` — the minimum GitHub
token scope its two `gh` calls need (`gh pr view` reads pull-request
metadata; `gh repo view --json defaultBranchRef` reads repository metadata).
No `secrets:` are passed to it and it performs no `actions/checkout` step,
matching the Assumptions' description of "a job with no checkout and no
secrets whose only output is the identity" and Gate 80's own treatment of
such a job as inherently unable to push (it has no way to `git push` at
all).

**Rationale**: `resolve-spec` in `plan.yml`/`tasks.yml` uses `permissions: {}`
because it performs no GitHub API call whatsoever (pure string
manipulation over declared inputs) — `resolve-identity` needs the two reads
`{}` would not authorize, so it declares exactly those two scopes and
nothing else, keeping to the least-privilege rule every other job in this
stage already follows.

## D3 — The survivor job's concurrency group: canonical per-spec, with an explicit per-PR fallback

**Decision**: `stalled`'s `concurrency.group` becomes:

```yaml
concurrency:
  group: wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}
  cancel-in-progress: false
```

Two adjacent `${{ }}` expressions, concatenated by GitHub Actions' own
string-interpolation rule (each block is evaluated independently and the
results joined) rather than one large ternary, because the *canonical* half
must be textually identical to the second of Gate 80's three existing
accepted spellings (`wing-commander-${{ needs.<job>.outputs.spec-dir }}`) —
folding it into a single `format(...)` call would produce a group string
that is behaviourally identical but textually a fourth, redundant spelling
of the *same* canonical case, needlessly widening what Gate 80 has to
recognize for the common path.

- **Non-empty `spec-dir`**: `spec-dir` interpolates the same value the
  canonical spelling already produces; the second block evaluates to `''`
  (the `&&`/`||` short-circuits false), so the group is exactly
  `wing-commander-specs/NNN-slug` — the second of Gate 80's three existing
  accepted forms, byte for byte.
- **Empty `spec-dir`** (a non-qualifying PR, or `resolve-identity` failed):
  the first block contributes nothing; the second evaluates to
  `pr-conversation-pr-<pr-number>`, so the group is
  `wing-commander-pr-conversation-pr-<pr-number>` — textually identical to
  `classify-and-announce`'s own existing per-PR group string, so a
  maintainer reading both jobs' concurrency blocks sees one consistent
  per-PR spelling in this file, not two different ones.

**Rationale**: FR-008 forbids the group degenerating to the bare
`wing-commander-` constant (which is exactly what
`wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}` alone would
produce when `spec-dir` is empty — a real trap the second Gate 80 spelling
would otherwise walk straight into for this one job). The fallback must
still be per-PR, not per-specification and not repository-wide, per Q3's
resolution.

**Alternatives considered**:
- *A single `format('wing-commander-{0}', spec-dir != '' && spec-dir ||
  format('pr-conversation-pr-{0}', inputs.pr-number))` expression* —
  behaviourally equivalent, rejected only for the textual-spelling reason
  above: it would require Gate 80 to learn a *new* pattern for the ordinary
  canonical case too, rather than continuing to accept that case under its
  existing, already-battle-tested regex.
- *Fall back to `wing-commander-pr-conversation` (stage-wide, not per-PR)* —
  rejected: this would serialize every stalled run in the repository against
  every other, letting one PR's pending notice be starved by another's
  (#415's mechanism), exactly what FR-008 names as the risk of the
  degenerate constant, one level less severe but the same shape.

`stalled`'s `needs` gains `resolve-identity` (ordered `[verify-image-prerequisites,
resolve-identity, classify-and-announce]`, mirroring `tasks.yml`'s
`[verify-image-prerequisites, resolve-spec, tasks]`), and its `if:` gains an
explicit `needs.resolve-identity.result == 'failure'` arm alongside the
existing `needs.verify-image-prerequisites.result == 'failure'` /
`needs.classify-and-announce.result == 'failure'` /
`needs.classify-and-announce.result == 'skipped'` arms:

```yaml
if: |
  needs.verify-image-prerequisites.result != 'failure' &&
  !cancelled() &&
  ( needs.verify-image-prerequisites.result == 'failure' ||
    needs.resolve-identity.result == 'failure' ||
    needs.classify-and-announce.result == 'failure' ||
    needs.classify-and-announce.result == 'skipped' ) &&
  needs.classify-and-announce.outputs.refusal-reason == ''
```

This arm is technically implied today by `classify-and-announce`'s own
`needs.resolve-identity.result != 'failure'` toleration clause (D1: a failed
`resolve-identity` always leaves `classify-and-announce` `skipped`, which the
third arm already admits) — it is added explicitly anyway, per FR-005's
"MUST therefore tolerate a failed or skipped prerequisite explicitly" and
because the two jobs' `if:` conditions are edited independently; a future
edit to either one should not have to re-derive that the other's coverage
was implicit. This widened `if:` is the change the Assumptions section flags
for a `review-step-gating` skill pass before merge.

## D4 — `stalled`'s own identity re-derivation is deleted, not merely bypassed

**Decision**: The "Resolve PR identity independently" step (`id: identity`,
`continue-on-error: true`, its own `gh pr view` call) is removed from
`stalled` entirely — not left in place as dead code, not wrapped in an
`if: false`. Every place it fed:

- `spec-dir` / `spec-branch` for the `wing-commander-chain-stop-notice` call
  → `needs.resolve-identity.outputs.spec-dir` /
  `${{ inputs.spec-prefix }}${{ needs.resolve-identity.outputs.slug }}`.
- `issue-number` for the same call → unchanged mechanism (the survivor job
  keeps its own `spec-meta.json` read, per the Assumptions' "only the
  head-ref-to-slug derivation moves"), but the step performing that read is
  now guarded by `if: needs.resolve-identity.outputs.spec-dir != ''` (there
  is nothing to look up when `spec-dir` is empty) and keys its `SPEC_DIR`/
  `SPEC_BRANCH` env off `needs.resolve-identity.outputs.*` instead of
  `steps.identity.outputs.*`. The final call keeps the existing
  `steps.<issue-lookup>.outputs.issue || inputs.pr-number` fallback — unlike
  `tasks.yml`'s equivalent step, which has no such fallback, because
  `tasks.yml`'s `resolve-spec` can only reach `stalled` with an
  already-valid slug (a malformed one is a refusal that suppresses the whole
  job); `pr-conversation`'s `resolve-identity` can legitimately reach
  `stalled` with an *empty* `spec-dir` (Story 2), so the PR-number fallback
  stays load-bearing here.

**Rationale**: FR-016 states this plainly — "The survivor job MUST NOT keep
a second independent head-ref lookup of its own for the record: one home
for the derivation (FR-012) is the point." Leaving the old step in place
(even unreachable) would still count as a second occurrence of the same
slug-derivation logic against FR-012/SC-005's literal text and count.

## D5 — Gate 80 learns exactly one new spelling, matched exactly

**Decision**: `verify-spec-branch-push-concurrency.py` gains a second
compiled pattern, checked as an alternative to (never a replacement of)
`PER_SPEC_GROUP_RE`:

```python
PR_CONVERSATION_STALLED_FALLBACK_GROUP_RE = re.compile(
    r"^wing-commander-\$\{\{\s*needs\.([\w-]+)\.outputs\.spec-dir\s*\}\}"
    r"\$\{\{\s*needs\.\1\.outputs\.spec-dir\s*==\s*''\s*&&\s*"
    r"format\('pr-conversation-pr-\{0\}',\s*inputs\.pr-number\)\s*\|\|\s*''\s*\}\}$"
)
```

The `([\w-]+)` / `\1` backreference requires the *same* `needs.<job>` name
in both halves of the expression — a group that reads `spec-dir` from one
job and gates the fallback on a different job's result is a bug this gate
must still catch, not a spelling it should learn to wave through. The
literal `pr-conversation-pr-{0}` / `inputs.pr-number` text is intentionally
specific to this one job — this is the fourth and last accepted spelling the
spec calls for (FR-018's "the only addition to the accepted set"), not a
general-purpose fourth per-spec-group form other stages could adopt.

`evaluate()`'s single "is this the canonical group or a waiver" branch
becomes "is this the canonical group, this one fallback spelling, or a
waiver" — an `or` added to one `if`, not a rewrite.

**Required self-test additions** (contracts/gate-80-fallback-spelling.md has
the full fixture text):
1. A job declaring the exact fallback spelling above, with no waiver,
   passes.
2. A job declaring the same shape but with mismatched job names in the two
   halves (defeats the backreference) still fails.
3. A job declaring `wing-commander-` alone (the degenerate constant) still
   fails — proving the widening did not loosen the existing floor.
4. A job declaring a near-miss of the fallback literal (e.g.
   `pr-conversation-{0}` without `-pr-`, or `inputs.pr_number`) still fails.

**Rationale**: SC-008 requires this proven "by cases in the gate's own
tests, not by the gate passing over the repository alone" — Constitution
VIII's "every failure branch a gate ships MUST be exercised by a checked-in
fixture" applies with equal force to a newly *accepted* branch: a spelling
Gate 80 now waves through needs its own near-miss counterexample, or the
acceptance itself is unverified.

## D6 — Cross-spec amendments this feature's own requirements require

Both are named in spec.md's scope and FR-004/FR-019; neither is optional
cleanup.

**`specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`**
(FR-004): the Members table gains a row —

| Workflow | Job | Group expression after this change |
|---|---|---|
| `pr-conversation.yml` | `stalled` | `wing-commander-${{ needs.resolve-identity.outputs.spec-dir }}${{ needs.resolve-identity.outputs.spec-dir == '' && format('pr-conversation-pr-{0}', inputs.pr-number) || '' }}` (joined 2026-09-26, #581 — falls back to the per-PR group when `spec-dir` is empty; see the `resolve-identity` job contract) |

— in the same row form the `#397` `stalled`/`stalled-approved` and
`teardown-done`/`teardown-rejected`/`mark-stalled` rows already use. A
second new subsection, "`resolve-identity` job contract (new,
`pr-conversation.yml` only)", is added alongside the existing `resolve-spec`
job contract subsection, documenting the one respect it differs
(contracts/resolve-identity-job.md has the full text — it is not
duplicated here, per this same document's own "not duplicated here: a
hand-maintained second copy is exactly how this table's own list silently
fell out of sync" rule).

**`specs/041-implement-stall-notice/research.md` D6** (FR-019): the
`pr-conversation` row of D6's table —

> `pr-conversation \| pr-number \| spec-dir, issue-number \| independent gh
> pr view on the head ref to recover the spec/NNN-slug branch name, then the
> same spec-meta.json-read meta step already performs, run again here. When
> this re-derivation itself fails, the notice posts to pr-number directly
> ... rather than to an unknown lifecycle issue ...`

— is rewritten to:

> `pr-conversation \| pr-number \| spec-dir (via a derivation-only
> prerequisite job, resolve-identity — no checkout, no secrets, publishes
> identity only), issue-number \| spec-dir and slug are read from
> needs.resolve-identity.outputs.*, computed once, before this stage's entry
> job runs; issue-number keeps its own independent spec-meta.json read in
> this job, keyed off that slug. When resolve-identity itself failed or was
> skipped, spec-dir is empty and the notice posts to pr-number directly ...
> rather than to an unknown lifecycle issue ...`

The decision text immediately above the table (D6's "the survivor job never
reads `needs.<entry-job>.outputs.*` for spec-dir/issue-number/iteration ...
it resolves identity from that stage's own `workflow_call` inputs,
re-deriving anything not directly declared") gains one clause: a
**derivation-only prerequisite job** — no checkout, no secrets, whose only
product is the identity — counts as "the stage's own declared inputs" for
this rule's purpose, since it computes nothing `pr-conversation.yml` itself
does not already declare (`inputs.pr-number`) and runs unconditionally
ahead of the entry job it is not derived *from*. This is Q2's resolution
(FR-016), written into the decision record it amends.

**Why these edits land in the implement stage, not this plan**: this run's
edit scope is `specs/077-stalled-per-spec-group` only; tasks.md (generated
next) carries a task to apply both edits verbatim against the text quoted
above, cross-checked against whatever `specs/013`/`specs/041` read at
implementation time in case either has drifted since this research was
written.

## D7 — Comments rewritten, not merely code

**Decision**: Two comment blocks assert something FR-013 requires becoming
false again once this change lands, and both are rewritten rather than
left stale:

1. `classify-and-announce`'s own concurrency comment ("Serialized per-PR,
   not per-spec-dir: spec-dir isn't knowable until the PullRequestIdentity
   step below runs inside this job ...") — false the moment
   `resolve-identity` publishes `spec-dir` before this job's concurrency is
   even evaluated. Rewritten to state the *actual* reason this job stays
   per-PR: it never itself pushes to `spec/<slug>` — only `act` does,
   through its own group — so ordering it against spec-branch writers would
   buy it nothing.
2. `stalled`'s own header comment and the deleted step's "Independent
   identity re-derivation (research.md D6 ...)" comment — rewritten to
   describe the derivation-only-prerequisite shape (D6 above) in place of
   the independent-re-derivation shape they currently describe.

**Rationale**: this repository's own rule (CLAUDE.md: "Workflow comments are
load-bearing: gates byte-compare and mutate them. Treat comment edits as
code edits and re-run the suite") and FR-013's literal text both require
this; SC-006 names the comment gates specifically as part of the PR-time
gate suite this change must still pass.
