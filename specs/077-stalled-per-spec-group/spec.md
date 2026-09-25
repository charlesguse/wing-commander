# Feature Specification: The Stall Mark Waits Its Turn — pr-conversation's Survivor Job Joins the Per-Spec Concurrency Group

**Feature Branch**: `077-stalled-per-spec-group`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue [#581](https://github.com/charlesguse/wing-commander/issues/581), routed from the board loop's work on [#437](https://github.com/charlesguse/wing-commander/issues/437) — "join stalled's spec-meta push to the per-spec concurrency group"

## Context

Since #397 every job in this repository that can write a specification's
working branch `spec/NNN-slug` shares one concurrency group,
`wing-commander-<spec-dir>`, with `cancel-in-progress: false`. That is the
single-file guarantee that keeps the rebase stage's force-push from landing
in the middle of a running implement cycle. The rule is written into
`specs/013-serialize-rebase-stages/contracts/concurrency-groups.md` ("Any
future published stage that checks out and publishes to a specification's
working branch MUST declare ... in this same form") and it is enforced:
Gate 80 (`.github/scripts/verify-spec-branch-push-concurrency.py`) lists
every job that can push and requires the canonical group or a written
waiver in `.github/scripts/spec-branch-push-waivers.json`.

One job is waived rather than compliant.

### The waived job

`.github/workflows/pr-conversation.yml`'s `stalled` job is the stage's
**survivor job** (specs/041-implement-stall-notice): it runs when the
stage's entry job `classify-and-announce` failed or never started, and its
purpose is to leave a record — a `stage: "stalled"` mark written into
`spec-meta.json` on `spec/NNN-slug`, plus a notice on the lifecycle issue —
so a stalled run is visible instead of silent. The mark is pushed through
the `wing-commander-chain-stop-notice` composite, which runs `git push`.

That push is a spec-branch write, but the job sits in a PR-keyed group:

```
concurrency:
  group: wing-commander-pr-conversation-pr-${{ inputs.pr-number }}
  cancel-in-progress: false
```

so it is unordered against a rebase, an implement cycle, or a fold running
on the same branch from the per-spec group — the same shape as #397. The
waiver in `spec-branch-push-waivers.json` says so in as many words and
records the residual as tracked on #437.

### Why it could not join

The waiver also states the mechanical reason, and it is a real one. The
`stalled` job resolves the specification's identity in a step of its own
(`steps.identity`): it calls `gh pr view` for the PR's head ref, strips the
`spec/` prefix to get the slug, and derives `specs/<slug>`. GitHub Actions
evaluates a job's `concurrency.group` **before any of that job's steps
run**, so the group expression cannot read `steps.identity.outputs.spec-dir`.
The only way a job-level group can carry a derived value is to read it from
a *prerequisite job's* output — and the job that publishes `spec-dir` today,
`classify-and-announce`, is by construction the job that did not start
whenever `stalled` runs.

The same comment block is stamped on `classify-and-announce` itself
(`.github/workflows/pr-conversation.yml`, the `concurrency:` block): "Serialized
per-PR, not per-spec-dir: spec-dir isn't knowable until the
PullRequestIdentity step below runs inside this job."

### The shape that already exists

`plan.yml` and `tasks.yml` solved exactly this problem. Each has a tiny
`resolve-spec` prerequisite job — no checkout, no secrets, `permissions: {}`
— whose only work is to derive `slug`/`spec-dir` and publish them as **job**
outputs, which the downstream job's `concurrency.group` can then read
(`wing-commander-${{ needs.resolve-spec.outputs.spec-dir }}`, one of the
three spellings Gate 80 accepts). The `resolve-spec` job contract is written
into `concurrency-groups.md` alongside the group string itself.

`pr-conversation.yml` is the one stage that has not been given that shape.
Its situation differs from `plan.yml`'s in one respect that matters:
`plan.yml` receives `head-ref`/`slug` as declared `workflow_call` inputs and
derives the slug by pure string manipulation, while `pr-conversation.yml`
receives only `pr-number` and must ask the GitHub API for the head ref
before it can derive anything.

### Two properties the change has to preserve

Both are load-bearing and both are stated in existing specs, so this
feature is as much about *not* breaking them as about joining the group.

1. **A stalled run is never silent.** Spec 041's FR-003 rests on the
   survivor job identifying its subject "from the stage's own declared
   inputs, which are present regardless of how far the run got," and its D6
   table records the pr-conversation fallback explicitly: when identity
   re-derivation fails, the notice posts to `pr-number` directly, because
   `pr-number` is the one identifier guaranteed present. The current
   `steps.identity` honours this by being `continue-on-error: true` — a
   failed lookup leaves `spec-dir` empty and the notice still lands on the
   PR. A new prerequisite job sits *upstream* of the survivor job, so its
   own failure or skip is a new way for the notice to be lost.

2. **A non-qualifying PR gets no reply at all.** FR-018 of the
   pr-conversation spec makes silence the correct behaviour for a PR whose
   head ref is not `spec/NNN-slug`. This is why `plan.yml`'s `resolve-spec`
   shape cannot be copied verbatim: that job exits non-zero when the slug
   does not parse ("refusing to guess"), which is right for `plan.yml`,
   where a malformed slug is an error, and wrong here, where a non-spec head
   ref is an ordinary, expected event.

### Scope

One stage file, one waiver entry, and the contract that governs them.
`clarify.yml`'s `stalled` waiver stays: that job has the same wiring but its
target branch does not exist yet at the clarify stage, so it is waived for a
different reason that this feature does not address.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A stall mark never lands mid-rebase (Priority: P1)

A maintainer's review arrives on an implementation PR while a rebase or an
implement cycle is already running on `spec/077-some-feature`. The
pr-conversation stage's entry job dies before it can classify anything — a
runner failure, a revoked token, a transient API outage. The survivor job
takes over and writes the stall mark onto the specification's working
branch. Today that write is unordered against the cycle already holding the
branch: either the mark or the cycle's own push can be lost. After this
change the survivor job waits for the per-specification slot like every
other writer, and its mark lands cleanly once the holder finishes.

**Why this priority**: It is the defect. Everything else in this feature
exists to make this one change safe.

**Independent Test**: Gate 80 is run against the repository with the
`pr-conversation.yml`/`stalled` waiver deleted; it passes, meaning the job's
declared group is one of the three canonical per-spec spellings. Separately,
the job's group expression is read and compared against the group every
other writer of that branch declares.

**Acceptance Scenarios**:

1. **Given** the `pr-conversation.yml`/`stalled` waiver has been removed from
   `.github/scripts/spec-branch-push-waivers.json`, **When** Gate 80 runs
   over the repository, **Then** it reports no failure for that job.
2. **Given** an implement cycle for `specs/077-some-feature` is holding
   `wing-commander-specs/077-some-feature`, **When** a pr-conversation run
   for a PR on `spec/077-some-feature` reaches its survivor job, **Then**
   the survivor job queues for that same group rather than pushing
   concurrently.
3. **Given** the survivor job has joined the group, **When** the
   `concurrency-groups.md` members table is read, **Then** it lists the
   `pr-conversation.yml`/`stalled` row with the canonical group expression,
   in the same form as the `tasks.yml` and `cleanup.yml` rows added for
   #397.

---

### User Story 2 - A stalled run still reports itself when identity cannot be resolved (Priority: P1)

The same stage stalls, but this time the GitHub API is rate-limited and the
head ref for the PR cannot be read at all. The maintainer who left the
review must still learn that the stage did not start. Today the survivor
job tolerates the failed lookup, posts its notice to the PR number, and the
chain-stop composite takes its "record could not be updated" branch because
`spec-dir` is empty. That behaviour must survive the introduction of a
prerequisite job that can itself fail.

**Why this priority**: A concurrency fix that trades a rare lost push for a
routinely lost stall notice is a net regression. Spec 041 exists precisely
because silent stalls are the worst failure mode this pipeline has.

**Independent Test**: The survivor job's `if:` condition and its post target
are read against the three upstream states (prerequisite succeeded, failed,
skipped) and checked to admit the job in every case where it is admitted
today.

**Acceptance Scenarios**:

1. **Given** the new prerequisite job fails or is skipped, **When** the
   stage's entry job also fails or is skipped, **Then** the survivor job
   still runs and still posts a stall notice.
2. **Given** identity could not be resolved, **When** the survivor job posts
   its notice, **Then** it posts to the PR number, exactly as it does today.
3. **Given** identity could not be resolved, **When** the chain-stop notice
   composite is invoked, **Then** it receives an empty `spec-dir` and takes
   its existing "record could not be updated" branch rather than pushing to
   a guessed branch.

---

### User Story 3 - A PR the stage does not act on stays silent (Priority: P2)

A maintainer comments on an ordinary PR — a docs fix on a `fix/` branch, a
plan PR, a spec-draft PR. The pr-conversation stage does not act on those,
and FR-018 makes complete silence the correct outcome: no reply, no
comment, no notice. Adding a prerequisite job that must decide something
about every PR before the stage's first real job starts must not turn that
silence into a failed job, an error annotation, or a stray comment.

**Why this priority**: A regression here is loud and affects every PR
conversation in the repository, not only stalled ones, but it does not lose
data the way Story 2's does.

**Independent Test**: The new prerequisite job's behaviour is exercised
against head refs that are not `spec/NNN-slug` — a `fix/` branch, a
`plan/` branch, a `spec-draft/` branch — and checked to complete without
error and without producing any comment.

**Acceptance Scenarios**:

1. **Given** a PR whose head ref is not `spec/NNN-slug`, **When** the new
   prerequisite job runs, **Then** it completes without failing the run and
   without posting anything.
2. **Given** that same PR, **When** the entry job evaluates qualification,
   **Then** it reaches the same verdict it reaches today, and the stage
   stops silently.

---

### User Story 4 - The identity derivation has one home (Priority: P3)

Today the `spec/NNN-slug` head-ref prefix strip and the slug-format check
exist twice in `pr-conversation.yml` — once in the entry job's identity step
and once in the survivor job's — and a third time as the prefix-exclusion
chain that distinguishes an implementation PR from a plan, tasks, or
spec-draft PR. A future correction to the slug pattern has to land in each
copy, and nothing fails on a drifted copy. Consolidating the derivation
into the prerequisite job removes the duplication as a side effect of the
fix.

**Why this priority**: A real maintenance win and the repository's stated
"shared logic has exactly one home" rule, but it is cleanup: the pipeline is
correct without it.

**Independent Test**: The stage file is searched for the head-ref prefix
strip and slug-format check; each appears once.

**Acceptance Scenarios**:

1. **Given** the change is complete, **When** `pr-conversation.yml` is
   searched for the slug derivation, **Then** it appears in exactly one job.
2. **Given** the entry job now reads the slug from the prerequisite job,
   **When** every downstream reference to the entry job's identity outputs
   is enumerated, **Then** each still resolves to the same value it resolves
   to today.

---

### Edge Cases

- **The prerequisite job cannot reach the GitHub API.** The head ref is
  unknowable, so the group string is unknowable. The survivor job must
  still run and still report (Story 2); see FR-005 and the open question
  Q1.
- **The head ref is not a spec branch.** `spec-dir` is legitimately empty.
  A group expression built from an empty `spec-dir` degenerates to
  `wing-commander-`, a repository-wide group that would serialize unrelated
  survivor jobs against one another; see FR-008 and the open question Q3.
- **Two pr-conversation runs stall for the same specification at once.**
  Both survivor jobs now request the same per-spec slot. With
  `cancel-in-progress: false` the second queues behind the first rather
  than being dropped, so both marks land in order.
- **The stage stalls while the specification's branch has been deleted.**
  The push cannot land. The chain-stop composite's existing
  "record could not be updated" branch handles this; joining a concurrency
  group does not change it.
- **The entry job refused with a stated reason.** The survivor job is
  suppressed today by the `refusal-reason == ''` guard, because the entry
  job already posted a refusal note. That suppression must be unchanged.
- **A waiver outlives its exemption.** Gate 80 stale-checks every waiver: a
  waiver naming a job that no longer exists or no longer pushes fails the
  gate. Leaving the `pr-conversation.yml`/`stalled` waiver in place after
  the job joins the group therefore fails the gate on its own.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pr-conversation stage MUST declare the specification's
  slug and spec directory as outputs of a job that runs before both its
  entry job and its survivor job, so that a job-level concurrency group can
  read them.
- **FR-002**: The survivor job's `concurrency.group` MUST be the canonical
  per-specification group in one of the three spellings
  `concurrency-groups.md` and Gate 80 recognise, so that its spec-branch
  write is ordered against every other writer of that branch.
- **FR-003**: The `pr-conversation.yml`/`stalled` entry MUST be removed from
  `.github/scripts/spec-branch-push-waivers.json` in the same change, since
  Gate 80 fails a waiver that outlives its exemption.
- **FR-004**: `specs/013-serialize-rebase-stages/contracts/concurrency-groups.md`
  MUST record the survivor job as a member of the canonical group, in the
  same row form used for the members added for #397.
- **FR-005**: The survivor job MUST still run, and still post a stall
  notice, whenever it runs today — including when the new prerequisite job
  fails or is skipped. A stalled run MUST NOT become silent as a result of
  this change. [NEEDS CLARIFICATION: how is that guaranteed when the
  prerequisite job itself cannot resolve identity — does the prerequisite
  job never fail and emit empty outputs, or does the survivor job's
  admission condition tolerate a failed prerequisite explicitly?]
- **FR-006**: When the specification's identity cannot be resolved, the
  stall notice MUST post to the PR number and the chain-stop notice MUST
  receive an empty spec directory, preserving today's
  "record could not be updated" behaviour.
- **FR-007**: A pull request the stage does not act on MUST continue to
  produce no reply, no comment, and no failed job. The new prerequisite job
  MUST NOT treat a non-spec head ref as an error.
- **FR-008**: The survivor job MUST NOT join a concurrency group that
  serializes runs belonging to different specifications. [NEEDS
  CLARIFICATION: when the spec directory is empty — a non-qualifying PR, or
  a failed lookup — a group built from it degenerates to the constant
  `wing-commander-`, shared by every such run repository-wide. Is that
  acceptable, or must the empty case fall back to a distinct per-PR group?]
- **FR-009**: The entry job's qualification verdict — the comparison of the
  PR's base ref against the repository default branch and the exclusion of
  plan, tasks, and spec-draft head refs — MUST reach the same result for
  every PR that it reaches today.
- **FR-010**: Every existing reference to the entry job's identity outputs,
  in its own steps and in every downstream job, MUST continue to resolve to
  the same values, so that no behaviour outside the concurrency group and
  the derivation's location changes.
- **FR-011**: The entry job's loud-failure behaviour on an unreadable API
  response MUST be preserved: an API failure MUST NOT be reported as "this
  PR is out of scope," and MUST NOT let a maintainer's request vanish with
  no reply and no error.
- **FR-012**: The derivation of the slug from the PR's head ref MUST exist
  in exactly one place in the stage file after this change.
- **FR-013**: The comments that today explain why the entry job and the
  survivor job are serialized per-PR rather than per-specification MUST be
  rewritten to state what is true after the change. A comment that asserts
  `spec-dir` is unknowable before the entry job's steps run is false once a
  prerequisite job publishes it.
- **FR-014**: The survivor job's existing suppression when the entry job
  refused with a stated reason MUST be unchanged.
- **FR-015**: `clarify.yml`'s `stalled` waiver MUST be left in place; it is
  waived for an unrelated reason — the specification's working branch does
  not exist yet at that stage.
- **FR-016**: The survivor job MUST resolve the identity it puts in the
  stall record without depending on a value the stage's entry job would
  have published, since that job is by construction the one that did not
  run. [NEEDS CLARIFICATION: spec 041's FR-003/D6 currently requires the
  survivor job to re-derive identity itself rather than read
  `needs.<entry-job>.outputs.*`. Does reading a dedicated prerequisite
  job's outputs satisfy that rule — amending D6 to admit a derivation-only
  prerequisite — or must the survivor job keep its own independent lookup
  for the record while using the prerequisite's value only for the group
  string?]
- **FR-017**: No new `workflow_call` input may be added to the
  pr-conversation stage, and no adopter's wrapper workflow may need editing
  to receive this fix.

### Key Entities

- **Specification identity**: the slug `NNN-slug` and the spec directory
  `specs/NNN-slug` for the specification a pull request belongs to, derived
  from the PR's head ref `spec/NNN-slug`. The value the concurrency group
  string is built from.
- **Per-specification concurrency group**: `wing-commander-<spec-dir>` with
  `cancel-in-progress: false` — the single slot every job that writes a
  specification's working branch must hold while it writes.
- **Stall record**: the `stage: "stalled"` mark written into the
  specification's `spec-meta.json` on its working branch, plus the notice
  posted to the lifecycle issue or, when identity is unknown, to the pull
  request itself.
- **Push waiver**: an entry in `spec-branch-push-waivers.json` naming a file
  and job, what it pushes, and why that is not a spec-branch write. Gate 80
  stale-checks each one.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Gate 80 passes over the repository with zero waivers for the
  pr-conversation survivor job — the count of waived spec-branch writers
  drops by exactly one, and no other waiver is added.
- **SC-002**: Every job in the repository that can write a specification's
  working branch and is not waived for an unrelated reason declares the
  canonical per-specification group; the pr-conversation survivor job is
  among them.
- **SC-003**: For all three upstream outcomes of the new prerequisite job
  (success, failure, skipped), the survivor job's admission condition
  evaluates to the same verdict it evaluates to today for the same entry-job
  outcome — verified case by case, not by inspection of the happy path
  alone.
- **SC-004**: A pull request the stage does not act on produces zero
  comments and zero failed jobs, unchanged from today.
- **SC-005**: The slug derivation from a head ref appears exactly once in
  the stage file, down from three occurrences.
- **SC-006**: The full PR-time gate suite passes, including the comment
  gates that byte-compare workflow prose, after the comments explaining the
  concurrency choice are rewritten.
- **SC-007**: A re-driven pr-conversation run on a real stalled PR records
  its stall mark on the specification's working branch with no lost push,
  evidenced on the pull request or the lifecycle issue.

## Assumptions

- The prerequisite job follows the shape `plan.yml` and `tasks.yml` already
  ship — a job with no checkout and no secrets whose only output is the
  identity — adapted for the one API read `pr-conversation.yml` needs
  because it receives only a PR number.
- The entry job keeps its per-PR concurrency group. It does not write the
  specification's working branch itself, so the per-spec group buys it
  nothing, and per-PR serialization of conversation classification is the
  behaviour adopters have today.
- The entry job's identity step keeps its id and its output names, so that
  downstream references to it need no edits.
- The survivor job's lifecycle-issue lookup — reading `spec-meta.json` for
  the issue number — stays in the survivor job; only the head-ref-to-slug
  derivation moves.
- `clarify.yml`, `intake.yml`, and every other currently waived job is out
  of scope. This feature removes exactly one waiver.
- No change to what the stall notice says. The wording, the restart command,
  and the agent-ran/agent-conclusion branches are untouched.
- The three group spellings Gate 80 accepts are the complete set; this
  change uses the `needs.<job>.outputs.spec-dir` spelling rather than
  proposing a fourth.

## Open Questions

Three questions remain unresolved in the requirements above. They are
recorded here so the clarify stage can close them before planning.

- **Q1 (FR-005, FR-016)**: When the new prerequisite job cannot resolve
  identity — a rate-limited or failing API read — what happens to the
  survivor job? Options: the prerequisite job never fails, emitting empty
  outputs so the survivor job runs and falls back to the PR number as it
  does today; or the survivor job's admission condition tolerates a failed
  prerequisite explicitly; or the loss of the notice in that case is
  accepted.
- **Q2 (FR-016)**: Does a derivation-only prerequisite job satisfy spec
  041's rule that the survivor job never reads identity from another job's
  outputs, or must the survivor job keep its own independent lookup for the
  record and use the prerequisite's value only for the concurrency group?
- **Q3 (FR-008)**: What group does the survivor job join when the spec
  directory is empty?

---

*This specification describes the behaviour required. How the prerequisite
job is wired, which expressions carry which values, and what the rewritten
comments say are decisions for the plan stage.*
