# Phase 0 Research: Watchdog Precision & Determinism Hardening

`spec.md` carries no literal `[NEEDS CLARIFICATION]` marker. Its own
Assumptions section records that the three biggest judgment calls —
removing rungs 1–2, the 70%/20/10 precision target, and deleting
`specs/023-reliable-diagnose-verdict/` outright — were already answered
on issue #140 before this spec was written. What follows are the
remaining implementation-shape decisions needed to turn the seven named
gaps into something `tasks.md` can build against, grounded in the
current `watchdog.yml` implementation (surveyed below file-by-file) and
in this repository's own prior fix for the identical dedup-fallback bug
(#167/#168, `auto-update-spec-kit.yml`).

## Decision: The precision criterion's numerator is captured by a maintainer-applied disposition label, not new automation

**Decision**: Every pipeline-defect issue the watchdog files already
carries a `pipeline-defect` label and a per-class `🐕 · <class>` label
(`watchdog.yml:2688,2690`). This feature adds two more labels a
maintainer applies by hand when triaging a filed finding:
`disposition:confirmed` (the finding was real) and
`disposition:false-positive` (it wasn't). FR-001's precision criterion —
confirmed-genuine findings over filed findings, over the most recent 20
distinct post-dedup findings, not evaluated until 10 exist — is then a
`gh issue list --label pipeline-defect --label disposition:confirmed`
vs. `--label disposition:false-positive` count a maintainer runs by
hand; the "distinct (post-dedup) findings" denominator is the count of
distinct pipeline-defect issues (not comments), since dedup already
collapses recurrences onto one issue (FR-015's "distinct finding rather
than run" framing).

**Rationale**: Constitution III forbids new dashboards; a label is the
"ordinary GitHub action" this principle asks for. No component of the
watchdog itself can know whether a finding was genuine — only a human
reviewing it can — so this is necessarily a manual disposition, matching
how `SC-001`'s own gap note ("the absence of a labeled corpus... is
itself a gap the precision criterion depends on") frames the problem: the
label *is* the corpus, applied going forward. This also directly answers
the retroactive-scoring edge case: the five known historical false
positives (#102, #104, #105, #112, #125) can be labeled
`disposition:false-positive` after the fact to seed the corpus, per
SC-002.

**Alternatives considered**: A bot-computed precision metric derived from
whether a filed issue was closed-as-not-planned vs. closed-as-fixed —
rejected: issue closure reason conflates "not a real problem" with "was
real but is not worth fixing" and "was real, got fixed, closed normally"
all under ambiguous GitHub semantics, none of which cleanly means
"false positive." An explicit disposition label says exactly what it
means and costs a maintainer one click, the same cost as closing the
issue itself.

## Decision: FR-004/FR-005 attribution invariant extends the existing guard pattern from two collectors to five, using the same execution/ownership checks already proven for `collect-branch-drift` and `collect-spec-meta`

**Decision**: `collect-branch-drift` and `collect-spec-meta`
(`watchdog.yml:706-711`, `724-738`, `828-833`) already implement the
attribution invariant spec 024 asks for — PRs #135 and #137 added it as
one-off guards. The remaining three collectors
(`collect-execution-output`, `collect-step-summary`,
`collect-annotations`) gain the equivalent checks:

- `collect-execution-output` (denied-tool): a denial artifact can only be
  attributable to the inspected run if that run actually executed the
  step that produced it — gains the same `RUN_CONCLUSION` in
  `skipped`/`cancelled` early-exit already used elsewhere. Ownership is
  already implicit (the artifact is downloaded by this run's own id), so
  only the execution check is new here.
- `collect-step-summary` and `collect-annotations`: both already key off
  a specific job within the inspected run (`job`/`job-conclusion`
  fields), so ownership is inherent to the per-job API call; they gain
  the same skipped/cancelled execution check as the other three, applied
  per-job rather than run-wide (a job that itself never ran contributes
  no annotation/summary signal, even if sibling jobs in the same run
  did).

**Rationale**: FR-005 requires the invariant to "apply to every
collector, not to an individually-patched subset." Reusing the exact
condition already validated twice in production (rather than inventing a
new check) is the smallest change that generalizes what #135/#137 already
proved works, and keeps this feature's diff to the three collectors that
lack it rather than touching the two that already have it. Per FR-021's
scope boundary, this suppresses only signals that were never
attributable — a genuinely attributable denied-tool/step-summary/
annotation problem still has `RUN_CONCLUSION` outside
`skipped`/`cancelled`, so recall for real problems is unaffected.

**Alternatives considered**: A single shared bash function/composite step
computing attribution once and gating all five collectors through it —
rejected for this feature's scope: the five collectors read different
API shapes (artifacts vs. per-job summaries vs. annotations vs. branch
state vs. spec-meta) and already duplicate their own fetch logic
independently; a shared attribution helper is a reasonable follow-on
refactor but is not required to satisfy FR-004/FR-005 (which asks that
the invariant be *stated once and applied everywhere*, not that the code
be deduplicated), and inventing shared infrastructure here would exceed
FR-021's scope boundary against changing detection recall.

## Decision: FR-008/FR-009 evidence-validity gate is a deterministic check inserted between `diagnose` and `triage`, not a diagnose-prompt instruction

**Decision**: A new deterministic step in the `triage` job (matrix,
before `Compute fingerprint`) validates, per finding, that
`evidence[].signalId` resolves to a known signal id (already checked,
`watchdog.yml:1917-1921`) **and** that `normalizedFacts`' per-class
required keys (the same per-class key list the fingerprint fallback used
at `1949-1964`: `tool` for `denied-tool`, `branch` for `lost-progress`,
`expected`/`actual` for `stage-mismatch`, etc.) are present and
non-empty. A finding failing this check is suppressed before
fingerprinting/dedup ever run, and is recorded as "suppressed: invalid
evidence" in the lifecycle-issue report rather than filed.

**Rationale**: FR-008 requires the validity condition on the requirement
itself; FR-009 requires the failure mode to be suppression, not filing.
The research report's own finding — a `denied-tool` finding with
`{tool: null, denials: null}` passed the *old* FR-002 requirement exactly
because it only asked that the finding "cite" the run, never that the
cited facts exist — is the fixture this check targets (SC-005). Putting
this in deterministic code rather than strengthening the diagnose
prompt matches the cross-cutting principle FR-012/FR-013 asks to be
written down: judgment that gates a durable action (a filed finding)
belongs in code, not a prompt instruction the model can silently fail to
follow (as it already did for FR-002).

**Alternatives considered**: Tightening the diagnose step's structured-
output JSON schema to make the per-class fields `required` — rejected as
insufficient alone: a schema `required` constraint only guarantees the
key is present, not that its value is non-empty/non-null (`{tool: null}`
satisfies `required: ["tool"]`), so a deterministic post-check is needed
regardless; once that deterministic check exists, it is the enforcement
mechanism and the schema tightening becomes a nice-to-have `tasks.md` can
add for defense in depth but the plan does not depend on it.

## Decision: FR-006/FR-007 deterministic fingerprint drops the model-fact fallback branch entirely; the signal-id basis becomes unconditional

**Decision**: `watchdog.yml`'s `Compute fingerprint` step currently has
two branches (`triage`, lines 1901-2001, per the research survey): a
primary signal-id basis (already deterministic, pure bash/jq/sha256sum
over collector-produced ids) and a fallback to `normalizedFacts`-based
hashing "whenever the Finding cites no usable signal id" — explicitly
commented as drift-prone. This feature deletes the fallback branch.
Given FR-008/FR-009's new validity gate (previous decision), a finding
that reaches fingerprinting always has at least one valid, evidence-
grounded signal id in its `evidence[]` array (a finding with none is now
suppressed for invalid evidence before it gets here), so the fallback's
precondition ("cites no usable signal id") can no longer occur for a
finding that survives to this step.

**Rationale**: FR-007 requires the fingerprint be "derived from the
deterministic collector signals rather than from model-authored
narrative text" — the fallback path's basis is exactly the
model-authored `normalizedFacts` text FR-007 rules out. Removing it
(rather than hardening it further) is possible only because the new
validity gate closes the gap the fallback existed to paper over; without
that gate, deleting the fallback would silently drop findings that
currently degrade to it. This is the necessary ordering: FR-008/FR-009
must land before FR-006/FR-007 can simplify to a single path.

**Alternatives considered**: Keeping the fallback but requiring it to
also hash only from deterministic, pre-validated fields — rejected: once
every finding is guaranteed a valid signal id (previous decision), a
second basis computation is dead code that can only reintroduce the
drift FR-006 is meant to eliminate if it or the validity gate is ever
edited without the other in mind; one code path is strictly safer here.

## Decision: FR-018–FR-020 dedup `unknown` outcome reuses the existing per-class label as the "durable, queryable class attribute" and replaces `gh search issues` with `gh issue list --label`

**Decision**: Every pipeline-defect issue already carries a per-class
`🐕 · <class>` label (`watchdog.yml:1877,2688`) alongside the
`pipeline-defect` label — this already **is** the durable, queryable
class attribute FR-020 asks for; no new label taxonomy is introduced.
The `Dedup search` step (`watchdog.yml:2006-2057`) is rewritten:

```bash
if ! results=$(gh issue list --repo "$GITHUB_REPOSITORY" \
      --label "pipeline-defect" --label "🐕 · ${FINDING_CLASS}" \
      --state all --limit 200 --json number,state,body \
      2>"$RUNNER_TEMP/dedup-list-err.txt"); then
  outcome=unknown
  # surfaced to the lifecycle issue, filing suppressed — see next paragraph
else
  matches=$(printf '%s' "$results" | jq -c --arg fp "$FP" \
    '[ .[] | select(.body | contains("fingerprint=" + $fp)) ]')
  count=$(printf '%s' "$matches" | jq 'length')
  # count==0 -> none, count==1 -> match-open/match-closed by .state,
  # count>1 -> data-integrity (unchanged from spec 015)
fi
```

`gh issue list --label` enumerates within the bounded, strongly-
consistent set of issues carrying that one class label — a direct read,
not a search-index query — and the fingerprint match itself becomes a
local `jq` filter over that bounded result set's bodies rather than a
server-side full-text search. A non-zero exit (network error, rate
limit, or any other lookup failure) sets `outcome=unknown` explicitly,
never `results='[]'`. `unknown` is checked before the act job's rung/
comment/create branches: `[ "$DEDUP_OUTCOME" = "unknown" ]` suppresses
every write for that finding and posts "dedup lookup failed — finding
suppressed, needs a maintainer's manual check" to the lifecycle issue,
distinct in wording from both "passed inspection" and "could not
inspect this run" (FR-005's phrasing is about *collection* failing, not
dedup).

**Rationale**: FR-020 requires "a bounded, strongly-consistent direct
read... within the finding's class," and explicitly notes this "requires
filed findings to carry their class as a durable, queryable attribute" —
already true today, so this is a lookup-mechanism change, not a new
data-model addition. FR-018/FR-019 name `unknown` as a fourth outcome
distinct from `none` that must suppress filing rather than fall through.
The prior fix for the structurally identical bug in
`auto-update-spec-kit.yml` (#167/#168 — a `gh search issues` failure
swallowed by `2>/dev/null || echo '[]'` collapsing into "nothing found,
file it") used exactly this shape: stop assuming absence on failure, and
move to a bounded direct read once the search space is provably small —
here, "small" means "within one class's pipeline-defect issues," which
`--limit 200` comfortably covers for any class this pipeline has
produced findings for to date.

**Alternatives considered**: Keeping `gh search issues` but adding
failure detection only (no change to the lookup mechanism) — rejected:
this would satisfy FR-018/FR-019 alone but not FR-020, which is explicit
that an eventually-consistent index must be replaced with a bounded
direct read *where one is available* — and one is available here, exactly
as it was for #168's fix. A ledger file mapping fingerprint → issue
number (rejected already in spec 015's own research.md, same rationale:
a second source of truth that can desync) is rejected again for the same
reason, doubly so now that a bounded label-scoped read achieves the same
strong consistency without one.

## Decision: FR-014 rung removal deletes the `propose-fix` step, the rung gate, both rung-specific `act`-job PR steps, the guardrail config, and Gate 17 — leaving `triage`/`act` a straight-line path to "file or comment/reopen one issue"

**Decision**: Delete, in `watchdog.yml`: the `triage` job's `Check
fix-class eligibility`, `Resolve propose-fix model`, `Compose tool args
(watchdog.propose-fix)`, `Compute agent turn ceiling (propose-fix)`,
`Propose fix` (and its verdict/log/metrics steps), `Check propose-fix
diff`, `Rung gate`, and `Upload propose-fix diff artifact` steps; the
`act` job's `Download propose-fix diff`, `Commit fix and open PR (rung
2)`, and `Commit fix and open PR (rung 1)` steps; the two `propose-fix-
model`/`propose-fix-max-turns` workflow inputs. `Ensure pipeline-defect
issue (rung 2/3)` is renamed to reflect there is now exactly one
remediation outcome (file/comment/reopen an issue) and its rung-
conditional branches collapse to the dedup-outcome branches alone (none
→ create; match-open → comment; match-closed → reopen + comment; unknown
→ suppress, previous decision). Delete
`.specify/memory/watchdog-guardrails.json`,
`.github/scripts/verify-watchdog-fix-commit.py`, and `lint-workflows.yml`
Gate 17 in full (its subject no longer exists — Constitution VIII).

**Rationale**: FR-014 is explicit: "the watchdog MUST be restated as a
pure reporter whose remediation ladder is detection, dedup, and
issue-filing only," and "no requirement may be left on the books
describing a rung the watchdog no longer has" — the same discipline
applies to code and gates, not just requirement text. `docs/
architecture.md:750-752`'s own admission ("Rungs 1 and 2 have never
fired in production... not evidence that rungs 1 and 2 work") is the
factual basis spec.md's Assumptions cites for why removing this machinery
"loses nothing in practice."

**Alternatives considered**: Leaving the rung machinery in place but
unreachable (e.g., hardcoding `rung=3` after dedup regardless of any diff
attempt) — rejected: this is exactly the shape of "a check that cannot
fail its own subject" Constitution VIII warns against, just inverted (a
capability that can never fire is dead weight a future contributor could
silently re-enable without re-deriving why it was disabled); full removal
is what FR-014 asks for and what SC-009 checks.

## Decision: FR-010/FR-011 self-inspection amendment is a requirement-text change only; no code change is needed

**Decision**: `watchdog.yml`'s self-dispatch-depth logic
(`2545-2586`) and the separate deterministic `wing-commander-8b-
watchdog-self.yml` checker are both already shipped and already satisfy
the *substance* of "unexempted, no special-case softening" — the only
thing wrong is spec 015's FR-021 *text*, which forbids the mechanism
being anything other than identical to other stages' and is thereby
contradicted by the (deliberately different, deterministically stronger)
8b checker. This feature's User Story 5 is satisfied entirely by
rewording FR-021 in `specs/015-pipeline-watchdog/spec.md` and its
`data-model.md`/`contracts/watchdog-workflow.md` cross-references; no
`.github/workflows/*.yml` file changes.

**Rationale**: FR-010/FR-011 both describe a requirement-text amendment
("MUST be amended to require...", "MUST recognize a deterministic
self-checker as valid") — SC-006 confirms success is "the amended
self-inspection requirement is satisfied by the shipped deterministic
self-checker... no requirement left on the books that the code
violates," i.e. success is measured against the *existing* code, not a
new one.

**Alternatives considered**: None — the spec's own framing leaves no
implementation-shape choice here; this section exists to record
explicitly (per this plan's own governing principle, FR-012) that "no
code change" is itself a decision requiring a reason, not a step that
was overlooked.

## Decision: FR-012/FR-013 governing-document placement is a new Principle IX in the constitution, immediately following the same-shaped Principle VIII

**Decision**: `.specify/memory/constitution.md` is currently at version
1.5.0 with eight numbered principles, the most recent of which
(Principle VIII, "A Green Check Means What It Says," added in the same
1.5.0 amendment) is itself a cross-cutting lesson distilled from a
repeated pattern the repository kept rediscovering per-feature before it
was written down centrally — the exact same shape as this decision. This
feature adds **Principle IX**, naming that judgment gating a durable
action (a filed finding, a fingerprint, a dedup outcome, an autonomous
write) belongs in deterministic code, not an agent's prompt, citing this
feature's own five prior fixes (deterministic 8b self-checker, the
already-shipped deterministic rung gate, signal-derived fingerprints,
suppression pushed into collectors, an enum the model cannot leave) as
the worked examples, per Principle I's own "the repo is its own first
example" convention that every principle in this constitution already
follows.

**Rationale**: FR-012 requires the principle be recorded in "the
project's governing documents" — `.specify/memory/constitution.md` is
this repository's sole governing document per its own Governance
section ("This constitution supersedes ad-hoc practice... every spec,
plan, and implementation PR is checked against it"). FR-013 requires it
be "citable by a reviewer" — Principle VIII's own Sync Impact Report
format (a versioned amendment naming prior-art issue numbers) is the
established, already-working citation shape this repository uses for
exactly this purpose; reusing it needs no new convention.

**Alternatives considered**: Folding this into Principle II (Cost-
Conscious Model Tiering) as an addendum, since it's adjacent to "what
should and shouldn't run through a model" — rejected: Principle II is
about which *model tier* a step uses, not about whether a step's
*output* gates a write; conflating the two would make a future reviewer
search the wrong principle when citing this rule, undermining FR-013's
"citable" requirement. A new, dedicated principle is unambiguous.

## Open items intentionally deferred beyond this plan

- The exact wording of the amended FR/SC numbering inside `specs/
  015-pipeline-watchdog/spec.md` (which identifiers are edited in place
  vs. superseded by a new number) is `tasks.md`-level detail; this plan
  fixes which *requirements* change and why, not the final diff text.
- A shared attribution-check helper across all five collectors (noted as
  a rejected alternative above) is not built here; nothing in spec 024
  requires deduplicating the five collectors' independent fetch logic,
  only that each apply the same invariant.
- Whether `disposition:confirmed`/`disposition:false-positive` labels
  should exist as an automated GitHub label-create step (mirroring how
  `pipeline-defect` and `🐕 · <class>` are lazily created on first use,
  `watchdog.yml:2668`) or be created once by a maintainer ahead of time
  is `tasks.md`-level detail; either satisfies FR-001's "computable from
  the filed-finding record."

## SC-002 re-scoring: the five historical false positives against the strengthened requirements (Polish, T053)

Read directly from `gh issue view` on the five filed pipeline-defect
issues the retrospective named:

| Issue | Class | What it actually said | Gap that now suppresses it |
|---|---|---|---|
| #105 | `denied-tool` | Description read "Bash tool was denied 3 times... across turns 28, 116, 118" — readable, but the underlying `normalizedFacts` this finding actually carried was `{tool: null, denials: null}` (research.md's own worked example: the SDK's real `permission_denials` shape was mis-parsed, and the diagnose agent's *narrative* text stayed readable even though the *facts* it was supposed to ground that narrative in were null). | **Empty evidence** — the evidence-validity gate (FR-002/FR-027, T024) now fails this exact shape before fingerprinting ever runs. |
| #112 | `lost-progress` | `branch-drift` reported zero commits on `spec-draft/022-gate-closed-lifecycle`, but the run's real work landed on `spec/022-gate-closed-lifecycle` — a `pull_request`-triggered run reports the *draft* branch as its head, so the collector was measuring a branch the inspected run never owed commits to. | **Unattributable signal** — already the motivating case for `collect-branch-drift`'s ownership check (PR #135), which FR-026 now states as one invariant covering all five collectors rather than a one-off guard. |
| #125 | `stage-mismatch` | A `Wing Commander · 3 plan` run was expected at stage `plan` but recorded as `stalled` — the plan workflow had correctly skipped because the spec was stalled, so "the recorded stage disagrees with the expected one" was the stage gate working, not drift. | **Unattributable signal** — already the motivating case for `collect-spec-meta`'s `skipped`/`cancelled` early-exit (PR #137), generalized by FR-026 the same way as #112. |
| #102 | `step-stalled` (class-hint `null`) | The `rebase / discover` job matched the bare-word `stalled` sentinel in its own log. | **Absent precision bar** — the finding's evidence is genuinely non-empty (a real sentinel match, a real job name) and the job plausibly executed, so neither the evidence-validity gate nor the attribution invariant has grounds to suppress it; only SC-008's disposition-labeling would have flagged this class as precision-eroding over time, which is exactly the measurement spec 015 lacked before this feature. |
| #104 | `token-budget-warning` (class-hint `null`) | The `intake` job's own step summary matched "Turn budget warning" as a sentinel, but a warning being *emitted* is not the same claim as the run being *harmed* by it. | **Absent precision bar** — same reasoning as #102: the evidence is real and attributable, so the finding is a genuine detection of a real-but-not-actionable condition, which only the precision criterion (SC-008), not a pre-filing gate, is positioned to catch and count. |

Three of the three named gap categories (SC-002: "unattributable signal,
empty evidence, or absent precision bar") are each represented by at
least one issue, confirming SC-002's claim that the strengthened
requirements would have suppressed or measurably flagged all five. #102
and #104 are the two cases where "suppressed" is not the right verb —
both cite real, attributable evidence for a condition that genuinely
occurred, so the deterministic gates (evidence-validity, attribution)
correctly let them through; SC-008's precision criterion is what turns
"the model's judgment that this mattered was wrong" from an invisible
cost into a measured one going forward.
