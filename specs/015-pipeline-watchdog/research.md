# Phase 0 Research: Pipeline Watchdog — Run Validation & Triage

`spec.md` carries no literal `[NEEDS CLARIFICATION]` markers, but it
deliberately leaves the *mechanics* of detection, fingerprinting, the
triage ladder, and the guardrail configuration open (its own Assumptions
section frames several of these as "absent a specified scheme" defaults).
What follows are the implementation-shape decisions this plan makes to
turn the spec's functional requirements into something `tasks.md` can
build against, grounded in what already exists in this repository
(`docs/architecture.md`, the eight published stages, `implement.yml`'s
stalled-detection, and `rebase.yml`'s escalation-marker convention).
Several of these are genuine judgment calls the spec text doesn't dictate
a single answer for — each says so explicitly and is called out again in
the plan's transmittal comment on issue #80, per the pipeline's own
convention for undocumented decisions (precedent: `specs/007-cleanup-stage/research.md`'s
`tasks/NNN-slug` branch-deletion finding).

## Decision: The watchdog is a ninth published stage (`watchdog.yml` + wrapper), not a script bolted onto existing stages

**Decision**: Ship `.github/workflows/watchdog.yml` as a tenth
`workflow_call`-only reusable stage (following the exact shape of
`cleanup.yml`/`rebase.yml`: typed inputs, no `github.event.*`/`vars.*`
reads inside the stage body) plus a thin wrapper
`wing-commander-8-watchdog.yml` that owns the triggers, and reuses the
three existing composites (`wing-commander-context`, `wing-commander-preflight`,
`wing-commander-metrics-summary`) via the same self-checkout dance every
other stage already performs.

**Rationale**: Constitution I requires every capability to be built
*through* the pipeline and dogfooded in this repo; constitution VI
requires the same portability contract every other stage already
satisfies (no hardcoded repo, no bundled project content). A new
top-level stage — rather than, say, a `stalled`-job-style addition
bolted onto `implement.yml` — is also the only shape that can satisfy
FR-001 ("inspect pipeline runs... for both succeeded and failed
outcomes") for *every* stage, not just implement, and FR-021
(self-inspection) without a special case, since a dedicated stage can be
triggered by any other stage's completion — including its own.

**Alternatives considered**: A script embedded in each existing stage's
own job (e.g., a `watchdog` job added to every one of the eight stage
files) — rejected: duplicates trigger/detection logic eight times,
can't self-inspect without one of those eight copies watching the
watchdog's own runs (which don't exist in this shape), and contradicts
the single-responsibility split every other stage already follows.

## Decision: Trigger is `workflow_run` on every stage wrapper's completion, plus `workflow_dispatch`, per FR-025

**Decision**: The wrapper (`wing-commander-8-watchdog.yml`) triggers on:

```yaml
on:
  workflow_run:
    workflows:
      - "1 - Intake"
      - "1b - Clarify"
      - "3 - Plan"
      - "4 - Tasks"
      - "5 - Implement"
      - "6 - Finalize"
      - "7 - Cleanup"
      - "Rebase"
      - "8 - Watchdog"      # self-inspection (FR-021/US4)
    types: [completed]
  workflow_dispatch:
    inputs:
      run-id: {required: true}   # the run to (re-)inspect
```

listing every wrapper by its `name:` (workflow_run keys off the display
name, not the file path), including itself.

**Rationale**: FR-025 names exactly these two triggers and explicitly
defers a scheduled sweep. `workflow_run` is the only GitHub-native event
that fires on "a workflow finished" without that workflow needing to
know the watchdog exists (no `next-workflow`-style opt-in wiring inside
each of the eight stage files, which would violate their "no
`vars.*`/chaining beyond declared inputs" contract). Listing the
watchdog's own wrapper name in its own `workflow_run.workflows` list is
what makes self-inspection (FR-021) a natural consequence of the same
mechanism, not a special branch.

**A GitHub-specific caveat this decision inherits**: `workflow_run`
triggers are registered from the *default branch's* copy of the
listening workflow file, and only fire for workflows whose *own*
YAML also lives on the default branch — both true here, since every
wrapper (including the new one) lives in `.github/workflows/` on `main`,
matching the existing rebase/cleanup wrappers' precedent of reacting to
repo-wide events without special per-branch wiring.

**Alternatives considered**: Having each stage `workflow_dispatch` the
watchdog explicitly on completion (the same `next-workflow` idiom
`plan.yml`→`tasks.yml` uses) — rejected: would require touching all
eight existing stage files to add one more optional chained dispatch
input, multiplying this feature's footprint across files it doesn't
otherwise need to change, for a weaker guarantee (a stage that fails
before reaching its own dispatch step never notifies the watchdog at
all — precisely the runs most worth inspecting).

## Decision: Self-dispatch cap is a run counter read from workflow-run history, gated by a repo variable

**Decision**: Before a self-inspection run (triggered by the watchdog's
own `workflow_run` completion) does anything beyond reporting, it counts
how many consecutive prior watchdog runs form an unbroken
self-inspects-self chain — walking `gh run list --workflow "8 - Watchdog"
--json databaseId,event,conclusion,createdAt` backward from the
triggering run while each run's own trigger was itself `workflow_run`
sourced from the watchdog wrapper — and compares that depth against
`vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`). At or
past the cap, the run still performs read-only detection and posts its
finding (never silently drops evidence), but skips every write action
(no auto-fix, no PR, no issue create/reopen/comment beyond the one
lifecycle-issue report) and says so explicitly in that report.

**Rationale**: FR-018 requires a hard cap "so its own actions cannot
trigger an unbounded chain of watchdog runs." Deriving depth from actual
run history (rather than threading a counter through event payloads,
which `workflow_run` doesn't carry as a custom input) needs no new
storage and can't drift from reality the way a marker committed
somewhere could. Continuing to *report* past the cap (rather than
exiting silently) keeps faith with FR-002/FR-022 — the cap bounds
autonomous *action*, not detection.

**Alternatives considered**: A depth counter passed via
`workflow_dispatch` input, with the watchdog re-dispatching itself
explicitly instead of relying on `workflow_run` self-triggering (mirrors
`implement.yml`'s `iteration` re-dispatch idiom) — rejected: it would
mean the watchdog never self-inspects the *ordinary* `workflow_run`
path at all (defeating FR-021's "same trigger mechanism, no special
case" framing) and would require a second, dispatch-only entry point
solely for the self-chain, doubling the trigger surface for one
guardrail.

## Decision: Evidence collection is deterministic bash per source; only diagnosis synthesis uses an LLM

**Decision**: For each of FR-006's five sources, a dedicated
deterministic (no-LLM) collector step normalizes what it finds into one
`signals.json`:

| Source | Collector logic |
|---|---|
| `claude-execution-output-*` artifacts | `gh run download <run-id> -n claude-execution-output-*`; `jq` over the array for `.type` values that represent tool invocations/denials (not just the terminal `"result"` record `wing-commander-metrics-summary` already reads); count denials grouped by tool name |
| Step summaries | `gh api .../actions/jobs/{job_id}` per job in the run, or the job's own `$GITHUB_STEP_SUMMARY` if retrievable via the Actions API; grep for this pipeline's own known sentinel phrases (e.g. "stalled", "rejected", the metrics action's turn-budget warning) |
| Workflow annotations | `gh api .../check-runs/{id}/annotations` (or `gh run view --json` once it exposes annotations) for `failure`/`warning` level entries |
| `spec-meta.json` state vs. expected stage | `git show origin/<branch>:<spec_dir>/spec-meta.json` compared against the stage the just-completed workflow *should* have advanced it to (the same comparison `implement.yml`'s own "Read back cycle outcome" step already makes for its one case, generalized across stages) |
| Branch-vs-origin drift | `git fetch` + `git log <before>..origin/<branch>` commit count, generalizing `implement.yml`'s existing before/after-SHA pattern beyond one cycle |

A single LLM step then reads `signals.json` (never the raw artifact
content directly interpolated into a prompt — FR-023) plus, at its own
discretion via `Read`/`Grep`/`Bash(gh:*)`, the raw evidence it points at,
and produces structured findings.

**Rationale**: FR-011's rung-1 boundary is explicitly "a crisp, testable
rule" — testable rules belong in deterministic code, not LLM judgment,
and the same applies to the two named v1 problem classes (FR-003a/b),
which are pattern matches (denial count per tool name; commit count),
not judgment calls. Reserving the LLM for synthesis — turning normalized
facts into FR-002's human-readable, evidence-citing description — keeps
the one non-deterministic step small, cheap (haiku-tier, see model
decision below), and auditable, matching this repo's existing pattern of
"deterministic steps own every GitHub-observable fact; the agent step
only writes prose" (`specs/007-cleanup-stage/plan.md`'s Summary
describes the identical split for its one agent step).

**Alternatives considered**: One large LLM step given raw artifact/log
access and asked to "find problems" unassisted — rejected: makes FR-011's
crisp rung-1 boundary unauditable (the model's own say-so would decide
both detection *and* eligibility), and reproduces exactly the
class of mistake the motivating incident was: an agent making judgment
calls a deterministic check would have caught earlier and cheaper.

## Decision: Findings are diagnosed by one haiku-tier, read-only, structured-output step; fix diffs (rung 1/2) are a separate sonnet-tier, write-scoped step

**Decision**: Two agent steps, never one:

1. **Diagnose** (`claude-haiku-4-5`, `--allowedTools "Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)"`,
   no write tools, `--json-schema` structured output matching
   `data-model.md`'s Finding shape): reads `signals.json`, decides
   whether each signal rises to a Finding (FR-004's "no detectable
   problem ⇒ record pass, file nothing" is the common case), assigns a
   problem class, writes the evidence-citing description (FR-002), and
   proposes a rung — but the rung it proposes is a *hint*, not the final
   word (see the next decision).
2. **Propose fix** (`claude-sonnet-5`, only invoked for findings whose
   class has a known auto-remediation shape — the FR-011 seed set —
   `--allowedTools` scoped to `.github/workflows/**`, `.github/actions/**`,
   `docs/**`, no `git push`/`gh` access beyond read, writing a diff to the
   worktree that a deterministic step then commits): given one Finding,
   produces the smallest diff that addresses it, or declines (empty
   diff) if it can't confidently produce one — a decline always falls
   back to rung 2/3.

**Rationale**: Constitution II's tiering table names `claude-haiku-4-5`
for "triage, classification, labeling, and summaries" — diagnosis is
exactly that. It names implementation-weight work for `claude-sonnet-5`
(default tier) — generating even a tiny code diff is implementation
work, not classification, and deserves the tier that's actually good at
producing a correct patch. Splitting diagnosis from fix-proposal also
means the (cheap, frequent — runs after *every* stage completion) common
case of "run passed inspection, nothing to fix" never pays for a
sonnet-tier step at all.

**Alternatives considered**: A single sonnet-tier step doing both
diagnosis and fix proposal — rejected on cost grounds per constitution
II (every run of every stage triggers this; most runs have no finding at
all, so paying sonnet-tier cost on every invocation for what's usually a
haiku-shaped classification task is exactly the kind of spend the
tiering principle exists to prevent).

## Decision: Fingerprint is computed deterministically from the diagnosis step's structured fields, never generated by the model itself

**Decision**: The diagnose step's structured output includes a
`class` enum and a small set of `normalizedFacts` (e.g.
`{tool: "WebFetch"}` for a denial-pattern finding, `{branch:
"spec/015-pipeline-watchdog", expectedCommits: 1, actualCommits: 0}` for
a lost-progress finding) — deliberately *not* a fingerprint string. A
deterministic step then computes
`fingerprint = sha256(class + "|" + canonicalized(normalizedFacts))`,
where canonicalization means: sort object keys, lowercase tool/path
values, and drop any field explicitly marked volatile in the per-class
schema (run IDs, timestamps, turn numbers).

**Rationale**: The edge case "fingerprint collision / drift" requires
that "the same problem's evidence shifts slightly between runs" not
change the fingerprint — that's a determinism and normalization
property, which an LLM cannot be trusted to reproduce byte-for-byte
across independent invocations even at temperature-appropriate settings
for classification work. Keeping fingerprinting in deterministic code
also means the fingerprint scheme can be unit-considered and fixed
independently of model behavior, and matches the spec's own "Fingerprint
default" assumption almost verbatim (class + stable normalized
specifics).

**Alternatives considered**: Asking the model to emit the fingerprint
directly — rejected for the reproducibility reason above; two runs
diagnosing the literal same denial pattern could word `normalizedFacts`
differently enough (`"WebFetch"` vs `"webfetch"` vs `"web-fetch tool"`)
for a naive string fingerprint to drift, which is exactly the failure
mode the edge case warns against.

## Decision: Dedup search uses a hidden HTML marker in the issue body, reusing `rebase.yml`'s escalation-comment convention

**Decision**: Every pipeline-defect issue the watchdog creates carries
`<!-- wing-commander-watchdog: fingerprint=<sha256> -->` in its body.
Before filing anything (FR-012), a deterministic step runs
`gh search issues --repo <repo> "wing-commander-watchdog: fingerprint=<sha256> in:body" --state all --json number,state`
(state `all` so both open and closed issues surface in one call). Zero
results ⇒ create (FR-015); one OPEN result ⇒ comment with the fresh
evidence (FR-013); one CLOSED result ⇒ reopen + comment (FR-014). More
than one result (should not happen if the marker is unique per
fingerprint, but is treated as a data-integrity finding in its own
right, reported and left for a human, never auto-merged or
auto-closed).

**Rationale**: `rebase.yml` already establishes exactly this
marker-in-body-plus-search pattern for its own "don't re-escalate an
unchanged stuck rebase" rule (`docs/architecture.md`'s Rebase section);
reusing it is zero new design cost and gives dedup a durable,
human-visible identity (`gh issue view` shows the marker, so a
maintainer auditing why the watchdog treated two comments as "the same
problem" can see the fingerprint directly) rather than an invisible
side-channel store. `gh search issues` covers both states in one call,
so open/closed distinction is a property read off the result, not two
separate queries racing each other.

**Alternatives considered**: A separate ledger file (e.g.
`specs/_watchdog/fingerprints.json`) committed to `main` mapping
fingerprint → issue number — rejected: a second source of truth that can
desync from actual issue state (exactly the failure mode
`specs/007-cleanup-stage/research.md` rejected a similar durable marker
for), and it would need its own write-then-race handling for concurrent
watchdog runs (the "Concurrent watchdog runs" edge case), whereas
`gh search issues` reads live GitHub state that concurrent runs already
serialize through GitHub's own consistency, not this pipeline's.

## Decision: The rung-1/rung-2/rung-3 boundary is a deterministic gate over an actual diff, not a model's stated opinion

**Decision**: Given a finding and (if a fix was attempted) a diff, a
deterministic step computes the final rung, in this order:

1. No diff was attempted or the propose-fix step declined ⇒ **rung 3**
   if no matching pipeline-defect issue exists (dedup search above),
   else the dedup outcome itself (comment/reopen) *is* the action, still
   reported at whatever rung the dedup match implies (an open match ⇒
   effectively rung 2/3's existing item; FR-013/FR-014 apply
   regardless of rung).
2. A diff exists. Check, in order, per FR-011: (a) the diagnose step's
   `class` is in `.specify/memory/watchdog-guardrails.json`'s
   `changeClasses` allowlist; (b) every path in the diff matches that
   class's `pathGlobs`; (c) the diff's changed-line count is
   `<= min(class.maxDiffLines, config.maxDiffLines)`. All three pass,
   the watchdog is not paused (next decision), and the self-dispatch cap
   isn't exceeded ⇒ **rung 1**. Any single failure ⇒ **rung 2**
   (`open a PR carrying the fix`, referencing the pipeline-defect issue
   the dedup step just created/found/reopened — a rung-2 outcome always
   has a pipeline-defect issue by this point, created moments earlier if
   dedup found nothing, satisfying FR-008's "referencing the existing
   pipeline issue").
3. Ambiguous cases (a finding whose severity assessment from the
   diagnose step sits on a boundary the deterministic checks above don't
   resolve on their own, e.g. "large" vs "not large" for routing to rung
   3 vs 2 when no diff was even attempted) resolve to the higher rung —
   FR-010, the edge case, and the spec's own "Tie-break toward humans"
   assumption all state this explicitly, so the implementation's default
   on any unhandled comparison is "more human involvement," never "less."

**Rationale**: FR-011 is explicit that this boundary "MUST be defined by
a crisp, testable rule, because rung 1 writes to the repository
autonomously" — the whole point is that no LLM judgment call gates an
autonomous write. Requiring an actual diff before rung 1 can even be
considered also means the guardrail checks (paths, line cap) are
checking reality, not a plan of what might be touched.

**Alternatives considered**: Trusting the diagnose step's own proposed
rung directly when it happens to agree with the deterministic checks (a
"fast path" skipping the recomputation) — rejected as an unnecessary
special case that reintroduces exactly the trust-the-model failure mode
for zero performance benefit (the deterministic checks are cheap bash/jq
over an already-materialized diff).

## Decision (made without explicit clarification): rung 1 still opens a pull request; "autonomous" describes diagnosis speed, not the merge gate

**Decision**: Rung 1 ("fix a truly minor issue on sight") always ends in
a pull request to `main` — a minimal, single-purpose, auto-generated,
pre-approved-quality PR requiring only a human's merge click, never a
direct commit to `main` and never a bot-initiated merge/approval. What
makes it rung 1 rather than rung 2 is: it is not required to reference
an existing pipeline-defect issue (dedup found nothing — this is the
finding's first occurrence), its diff passed every FR-011 guardrail
check, and its PR body is a short "here's exactly what changed and why"
note rather than the fuller triage writeup rung 2/3 issues/PRs carry.
Rung 2 differs only in that it is *always* tied to a pipeline-defect
issue (either dedup found one, or one was just opened) and carries more
context, since by definition its diff failed at least one rung-1
guardrail and so warrants more human attention before merge.

**Rationale**: Constitution V is explicit and marked NON-NEGOTIABLE:
"Humans merge every PR into `main`; the bot never approves or merges to
`main`" — with no carve-out for small diffs. `spec.md`'s own Assumptions
agree: "the watchdog never merges to `main`." Reading FR-011's
"autonomous write" and rung 1/2's "fix on sight" vs. "open a PR" framing
as *literally* "rung 1 = no PR, direct commit to main" would either
violate the NON-NEGOTIABLE principle outright, or require inventing a
non-`main` target branch that a human never has to act on for the fix to
take effect — no such branch exists in this pipeline's model (everything
that isn't `main` is either a long-lived spec branch or a short-lived
stage branch, neither of which is "where the pipeline's own workflow
files actually run from"). The interpretation adopted here satisfies
every functional requirement's literal text (FR-007 "lightest sufficient
response," FR-011's crisp boundary, FR-020 "every autonomous action... is
recorded") while keeping the constitution's merge rule intact without
exception.

**Alternatives considered**:
- **Direct commit to `main`, no PR at all** — rejected outright: directly
  contradicts the NON-NEGOTIABLE constitution V text quoted above.
- **Direct commit to a branch with GitHub's native auto-merge enabled
  by repo owner opt-in** — considered more seriously (GitHub itself
  performs the merge once checks pass, arguably not "the bot" merging),
  but rejected for v1: it requires a repo-level auto-merge configuration
  and branch-protection required-checks setup this spec doesn't ask for,
  adds a second merge pathway alongside every other stage's plain
  human-click merge, and a human still cannot easily "veto" a check-passed
  auto-merge in the same lightweight way they review-and-close an
  ordinary PR — worse for FR-019's pause/veto guarantee than a PR
  awaiting an explicit click. Left as a possible future enhancement, not
  built here.

## Decision: Guardrail configuration lives in `.specify/memory/watchdog-guardrails.json`; the pause switch and self-dispatch cap are repo variables

**Decision**:

- `.specify/memory/watchdog-guardrails.json` (consuming-repo-owned,
  alongside `.specify/memory/constitution.md` per constitution VI's
  enumerated locations) holds the structured allowlist FR-017 requires:
  ```json
  {
    "maxDiffLines": 5,
    "changeClasses": [
      {"id": "allowlist-grant", "pathGlobs": [".github/workflows/**", ".github/actions/**"], "maxDiffLines": 3},
      {"id": "path-or-typo-correction", "pathGlobs": [".github/workflows/**", ".github/actions/**", "docs/**"], "maxDiffLines": 3},
      {"id": "syntax-fix", "pathGlobs": [".github/workflows/**", ".github/actions/**"], "maxDiffLines": 5}
    ]
  }
  ```
  seeded with FR-011's named v1 classes (allowlist grant, path/typo
  correction, syntax fix) directly addressing the motivating incident.
- `vars.WING_COMMANDER_WATCHDOG_PAUSED` (`true`/unset, default unset ⇒
  not paused) is FR-019's veto switch — a repo variable rather than a
  file, so a maintainer can flip it instantly without a PR-and-merge
  cycle, matching this repo's existing instant-effect gate precedent
  (`vars.WING_COMMANDER_PLAN_REVIEW`/`WING_COMMANDER_TASKS_REVIEW`,
  `specs/014-configurable-gates/`).
- `vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`) is the
  self-dispatch cap from the earlier decision, same instant-effect
  rationale.

**Rationale**: FR-017's allowlist is structured, reviewable, diffable
data a maintainer should be able to see change history for exactly like
the constitution itself — a checked-in file under `.specify/memory/`
fits the portability contract's already-enumerated locations exactly,
with no new top-level convention invented. The pause switch and
numeric cap are single scalars where instant effect (no PR round-trip
to pause a misbehaving watchdog) matters more than diff review, matching
the existing `vars.*` gate precedent this repo already established for
exactly this kind of "maintainer flips a switch without a code change"
knob.

**Alternatives considered**: Folding the pause switch into the same
JSON file — rejected: pausing autonomous fixes is explicitly the
"something is wrong right now, stop" lever (FR-019's "veto or pause");
requiring a PR-and-merge cycle to pull that lever defeats its purpose.

## Decision: Coexistence with `implement.yml`'s stalled job and `cleanup.yml`'s `mark-stalled` is a signal-suppression rule, not a special-cased skip

**Decision**: The lost-progress collector (FR-003b) checks, as part of
its normal signal-gathering, whether the inspected run's own job already
produced the outcome that would make `implement.yml`'s stalled job or
`cleanup.yml`'s `mark-stalled` job fire for the *same* run — concretely:
`spec-meta.json.stage == "stalled"` already, or a `stage:stalled` label
already present, **as of a time at or before this watchdog run started
inspecting**. If so, the lost-progress signal is downgraded to
"already reported by existing automation" and produces no new finding
of that class for that run (FR-024) — but the watchdog still records
that it inspected the run and observed the (already-handled) condition,
so SC-007's "findings appearing on the lifecycle issue" isn't silently
skipped, it's folded into the existing stalled report's trail rather
than duplicated.

**Rationale**: FR-024 requires "complement, not duplicate" — the
cheapest, least-special-cased way to satisfy that is to check the exact
state those two existing jobs are defined to produce (a label and a
`spec-meta.json` field, both already read/write in this repo's other
diagnostics) rather than inventing a new "already handled" marker
distinct from what those jobs themselves already leave behind. This
also naturally covers issue #73's known gap (a stalled condition that
neither job manages to report) — the watchdog's own lost-progress signal
still fires in that case, since neither job's target state was reached,
making the watchdog a genuine complement to #73's sweep proposal rather
than a duplicate of it.

**Alternatives considered**: A hardcoded `if: github.event.workflow_run.name != 'Implement'`
skip for the lost-progress class — rejected: it would blind the
watchdog to exactly the runs most likely to need it (any future stage
that grows its own stalled-detection would need the same hardcoded
exception added by hand, and the *actual* motivating incident here was
specifically an implement run).

## Decision: Model tiering summary

| Step | Model | Constitution II category |
|---|---|---|
| Evidence collectors (bash/jq) | none (deterministic) | n/a |
| Diagnose (findings + fingerprint facts) | `claude-haiku-4-5` | triage, classification |
| Propose fix (rung 1/2 diff) | `claude-sonnet-5` | implementation-weight |
| Fingerprint, rung gate, dedup search, guardrail check | none (deterministic) | n/a |
| Lifecycle-issue / pipeline-defect-issue writes | none (deterministic `gh` calls) | n/a |

Every agent step declares `--model` and `--max-turns`, per constitution
II's blanket rule.

## Open items intentionally deferred beyond this plan

- The exact `signals.json` schema per source and the exact `gh api`
  calls for reading back another run's annotations/step-summary (no
  existing code in this repo does either today, per the survey behind
  this research) are `tasks.md`-level detail, not architecture; this
  plan fixes the *shape* (deterministic collectors → one normalized
  file → one diagnose step) and leaves per-source field lists to task
  breakdown.
- A scheduled catch-up sweep is explicitly out of scope (FR-025); no
  design work for it is done here.
