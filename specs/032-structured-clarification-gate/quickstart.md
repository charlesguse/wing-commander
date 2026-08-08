# Quickstart: Validating Structured Clarification Questionnaires

Validation scenarios for spec 032, cross-referenced to the acceptance
scenarios in `spec.md` and the contracts in
`contracts/clarification-schema.md`, `contracts/decision-points.md`, and
`contracts/watchdog-sentinel.md`. This repo has no unit-test harness for
workflow YAML (`plan.md` Technical Context); validation is a mix of static
contract checks and dogfooded live runs, the same style specs 014/016/017/
018/019 used.

## Prerequisites

- A checkout of this repository (or an adopting repo with its own
  `specify init` output) on a branch containing this feature's changes.
- `gh` CLI authenticated with repo scope, for inspecting issues/PRs/run logs
  and triggering workflow runs.
- (Optional, for the full end-to-end scenarios) A test issue with the
  `spec-request` label to drive a real `intake.yml`/`clarify.yml` run —
  expensive in agent cost, so scenarios below lead with static contract
  checks and mark the one recommended live-run check per user story.

## Scenario 1 — An authored questionnaire is always posted verbatim, never silently dropped (User Story 1, FR-001, SC-001)

**Steps**: Drive `intake.yml` on an issue genuinely ambiguous enough that
the agent authors open questions (or dogfood on a real spec-request issue
whose description leaves real gaps).

**Expected**: The comment posted for "Answer the open clarification
questions" contains exactly the questions the agent's structured
`clarifications` array held — confirm by comparing the posted comment
against the uploaded `claude-execution-output-*` artifact's terminal
`result.clarifications` for that run:

```bash
gh run download <run-id> -n claude-execution-output --dir /tmp/wc-032
jq -r '[.[] | select(.type=="result")] | last | .result.clarifications | length' \
  /tmp/wc-032/claude-execution-output.json
gh issue view <issue-number> --json comments \
  --jq '.comments[] | select(.body | test("Action needed: Answer")) | .body' \
  | grep -c '^## Question'
```

**Expected output**: the two counts match — every authored question reached
the issue, none dropped (the #109 class).

## Scenario 2 — A malformed/missing structured output surfaces as a failure, not a silent no-post (User Story 1, FR-002, SC-006)

**Steps**: Static contract check — confirm the validation-failure path
exists and runs before the questionnaire/spec-PR-ready branches:

```bash
grep -n "clarifications" .github/workflows/intake.yml
grep -n "clarifications" .github/workflows/clarify.yml
```

**Expected**: Both files contain a read-back step that checks
`agent_ok`/schema-conformance (per `contracts/clarification-schema.md`'s
read-back idiom) and a corresponding `::error::` + non-zero-exit path that
no "Announce clarification needed" / "Announce spec PR ready" step can run
past. In `clarify.yml` that is one step ("Fail on agent API error",
`exit 1` in place, before the announce steps). In `intake.yml` it is split
— "Validate agent result" emits the `::error::` and publishes `valid`
before the decision step, which is gated on `valid == 'true'` so neither
announce branch can fire; "Fail on invalid agent result" is the job's last
step and turns that verdict into `exit 1`, after the PR-labelling side
effects have run (`contracts/clarification-schema.md`). Live confirmation (optional, requires
simulating a schema violation — not practical to force from a normal run):
inspect a run where `steps.agent.outcome` is not `success`, and confirm the
run itself shows as failed in `gh run view`, not green with an absent
callout.

## Scenario 3 — Zero authored questions post no clarification callout (User Story 1, Acceptance Scenario 3)

**Steps**: Drive `intake.yml` on an issue clear enough that the agent
authors zero questions.

**Expected**:
```bash
gh issue view <issue-number> --json comments \
  --jq '[.comments[] | select(.body | test("Answer the open clarification questions"))] | length'
```
**Expected output**: `0`. The "Review the spec PR" callout is present
instead.

## Scenario 4 — A spec naming the marker token in prose does not trigger a false "open questions" callout (User Story 2, FR-004, SC-002)

**Steps**: Construct (or use this very feature's own `spec.md`, which names
`[NEEDS CLARIFICATION]` and `[NEEDS CLARIFICATION:` in prose repeatedly) a
spec whose body mentions the bare marker token but carries no genuine
unresolved colon-form marker, and confirm the agent reports zero open
questions. Then:

```bash
gh issue view <issue-number> --json comments \
  --jq '.comments[] | select(.body | test("Review the spec PR"))' | wc -l
gh issue view <issue-number> --json comments \
  --jq '[.comments[] | select(.body | test("Answer the open clarification questions"))] | length'
```

**Expected**: The first is `1` (spec-PR-ready callout posted with its PR
link), the second is `0` — the #159 class is eliminated. Confirm the
cross-check still noticed the token by checking the run log (the emitting
step writes the line to both stdout and the step summary — only the stdout
copy is greppable here, and it is what the watchdog collector reads):

```bash
gh run view <run-id> --log | grep -c "clarification-mismatch"
```

**Expected output**: `0` — the colon-form tightening (FR-008) means a bare
prose mention of the token does NOT match the cross-check's colon-form
grep, so no mismatch fires here (spec.md Edge Case "Spec whose prose names
the bare token").

## Scenario 5 — Genuine disagreement is loud (User Story 3, FR-006, SC-004)

**Setup**: Construct a run where the two signals genuinely disagree — the
most reliable static way is a spec with a real `[NEEDS CLARIFICATION:
...]` marker left in place while independently confirming the agent
reports zero `clarifications` (or vice versa; either direction exercises
the same code path).

**Steps**:
```bash
gh run view <run-id> --log | grep "clarification-mismatch"
```

**Expected**: A log line containing the literal token
`clarification-mismatch`, citing both the structured and marker booleans.
Then run `watchdog.yml` against that run:

```bash
gh workflow run watchdog.yml -f run-id=<run-id>
# after it completes:
gh issue view <issue-number> --json comments \
  --jq '.comments[] | select(.body | test("clarification-mismatch|Finding"))'
```

**Expected**: The watchdog surfaces a Finding (or at minimum, the Signal
is visible in its own diagnostic trail — `contracts/watchdog-sentinel.md`'s
Acceptance section) rather than passing the run through as a clean bill of
health.

## Scenario 6 — Clarify's `none` outcome posts neither callout (User Story 4, FR-009, SC-007)

**Steps**: Post a reply to a clarify-triggering comment that answers none
of the open questions (e.g. an unrelated remark), triggering `clarify.yml`.

**Expected**:
```bash
gh issue view <issue-number> --json comments \
  --jq '[.comments[] | select(.body | test("Answer the remaining clarification questions|Review the spec PR"))] | length'
```
**Expected output**: `0` from BOTH deterministic callouts — the only
issue-facing signal for this run is the agent's own early-STOP comment
(unchanged, FR-014):
```bash
gh issue view <issue-number> --json comments \
  --jq '[.comments[] | select(.body | test("clearer answer"))] | length'
```
**Expected output**: `1`.

## Scenario 7 — Clarify's `ready` and `needs-clarification` outcomes are each reached correctly (User Story 4, Acceptance Scenarios 2–3)

**Steps**: Post a reply that resolves every remaining open question,
triggering `clarify.yml`; separately, post a reply that resolves only some.

**Expected** (full resolution): "Review the spec PR" callout posted, no
"Answer the remaining..." callout. **Expected** (partial resolution):
"Answer the remaining clarification questions" callout posted, listing only
the still-open questions (compare against the structured `clarifications`
array the same way Scenario 1 does), no spec-PR-ready callout.

## Scenario 8 — Watchdog sentinel present exactly once, correctly placed (contracts/watchdog-sentinel.md)

**Steps**:
```bash
grep -n "sentinels=" .github/workflows/watchdog.yml
```

**Expected**: Exactly one match, containing
`clarification-mismatch` as the last alternative in the existing
alternation (`contracts/watchdog-sentinel.md`'s diff) — no duplicate
sentinel definitions introduced elsewhere.

## Scenario 9 — No questionnaire is ever synthesized from marker text (FR-007, SC-005)

**Steps**: Static contract check across both changed workflow files:
```bash
grep -n "NEEDS CLARIFICATION" .github/workflows/intake.yml .github/workflows/clarify.yml
```

**Expected**: The only matches are the colon-form cross-check grep lines
(`contracts/clarification-schema.md`) — no code path extracts marker text
into a `clarifications`-shaped value. Cross-check against Scenario 5's
mismatch run: the posted callout (if any) in that run must contain only
the agent's own authored questions, never a marker-derived stand-in
question.

## Scenario 10 — Full lifecycle dogfooded run (thorough, real run — do this at least once before merging)

**Steps**: Trigger a live pipeline run on a throwaway test issue through
`spec-request` with content deliberately ambiguous enough to produce at
least one open question, reply to resolve it, and let the spec proceed.

**Expected**, in order:
1. Intake posts either the clarification-questionnaire callout (Scenario 1
   shape) or the spec-PR-ready callout, decided solely by the structured
   `clarifications` array.
2. If clarification was needed, replying triggers `clarify.yml`; the
   posted follow-up (or `ready`/`none` outcome) matches Scenarios 6/7.
3. No `clarification-mismatch` step-summary line appears on this ordinary,
   well-behaved run (Scenario 5 is the disagreement case, not the norm).
4. The reader-facing `## Question N` blocks match the pre-feature shape
   (FR-010) — a maintainer unfamiliar with this feature's internals should
   notice no difference in what they read, only that the pipeline is now
   more reliable about when it appears. One documented deviation: the
   heading drops the skill's `: [Topic]` suffix, because the schema carries
   no `topic` field (`contracts/clarification-schema.md`).
