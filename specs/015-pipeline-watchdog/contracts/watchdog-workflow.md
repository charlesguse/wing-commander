# Contract: `watchdog.yml` + `wing-commander-8-watchdog.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract and the deterministic checks/writes that must
run in order. This document is the contract the implementation (tasks
phase, next stage) must satisfy.

## Trigger contract (wrapper only — the reusable stage never reads `github.event.*`)

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
      - "8 - Watchdog"
    types: [completed]
  workflow_dispatch:
    inputs:
      run-id:
        description: "The run ID to (re-)inspect"
        required: true
```

The wrapper extracts `run-id` (`workflow_run.id` or the dispatch input),
`run-name` (`workflow_run.name` or resolved via `gh run view` for the
dispatch path), and passes both as typed inputs to `watchdog.yml`
(`uses: ./.github/workflows/watchdog.yml`, matching every other
wrapper's local-path-calls-published-stage shape). No path filter — this
stage is run-completion-driven, not file-change-driven.

## Job contract (`watchdog.yml`, `workflow_call` only)

Four jobs, sequential (`needs:`), one `concurrency:
wing-commander-watchdog-${{ inputs.run-id }}` group so re-inspection of
the same run never races itself, while different runs' inspections
proceed in parallel:

### `collect`

1. Preflight (`wing-commander-preflight` composite) — same fail-fast as
   every other stage (credential present, spec-kit artifacts present).
2. Resolve the inspected run's spec slug from `head_branch` (best-effort
   for `main`-based runs, e.g. cleanup — see data-model.md); this is a
   read-only lookup, never a refusal gate (unlike every write-capable
   stage's identity check) — a run the watchdog can't tie to a spec can
   still be inspected and reported against its own run URL, just without
   a lifecycle issue to post to (in which case the run's job summary
   carries the report instead, and the job records that no lifecycle
   issue destination exists).
3. Ten deterministic collector steps (one per FR-006 source, research.md
   table, plus the four supervision-gap collectors specs/046-watchdog-
   supervision-collectors added — collect-turn-budget, collect-cost-report,
   collect-final-pr-claims, collect-spec-collision — plus `Collect: cycle
   outcome`, spec 109), each tolerating "this source produced nothing for
   this run" as success, never as a failure — a source being empty is
   data, not an error. All ten MUST check, before emitting any signal, the
   attribution invariant (FR-026): (a) the inspected run's relevant
   scope (the whole run, or the specific job/artifact the collector
   reads) did not conclude `skipped`/`cancelled`, and (b) the evidence
   read belongs to something the inspected run itself produced. A
   collector whose check fails emits no signal for that condition.
4. Emit `signals.json` as a job output / uploaded artifact for `diagnose`
   to consume.

**`Collect: cycle outcome` (spec 109, new)**: downloads the
`wing-commander-cycle-outcome-*` artifact(s) `implement.yml`'s "Record
cycle outcome for watchdog (cycle)"/"(retry)" steps upload — distinct
`-cycle`/`-retry` names, since both can be uploaded within one job run;
the `-retry` one is read when both are present, as a retry's outcome is
the job's final word (contracts/watchdog-dedup-fanout-delta.md in that
feature's own spec directory). A missing artifact (inspected run
predates this feature, is not an implement run, or the upload never
happened) is a successful empty contribution, same attribution guard as
every other collector. Two effects: (1) records `{converged, handoff,
gate-suite-outcome, gate-suite-first-failure}` as `collect` job outputs
for `triage`'s FR-033 condition — never seen by `diagnose`; (2) when
`gate-suite-outcome == "fail"`, appends one `gate-suite-failure` signal to
`signals.json`, visible to `diagnose` exactly like any other collector's
signal.

**Failure mode**: if every collector step fails outright (not "empty,"
but actually errors — e.g. the run's artifacts are expired past
retention), `collect` sets an output `evidence-available: false` and the
workflow skips straight to the "could not inspect" report (FR-005),
never fabricating signals.

### `diagnose` (`needs: collect`, skipped if `evidence-available == false`)

`claude-haiku-4-5`, `--max-turns` bounded,
`--allowedTools "Read,Grep,Bash(gh:*),Bash(git log:*),Bash(git diff:*)"`,
`--disallowedTools "WebSearch,WebFetch,Write,Edit,Bash(git commit:*),Bash(git push:*)"`,
structured output via `--json-schema` matching data-model.md's Finding
array shape. Prompt frames `signals.json` and anything it reads via
`Read`/`Grep`/`gh` explicitly as untrusted data, never instructions
(FR-023) — same framing convention every comment-triggered stage already
uses. Zero Findings in the output ⇒ `diagnose` sets
`outcome: passed-inspection`. Findings with empty/malformed
`normalizedFacts` are still emitted by this step unchanged — validity is
checked downstream (below), not here; `diagnose`'s own `--allowedTools`,
model, prompt framing, and output schema are unaffected by that check.

### `triage` (`needs: diagnose`, one matrix entry per Finding, skipped if `outcome == passed-inspection`)

Per Finding, deterministic (no agent):

1. **Coexistence check** (research.md): if `finding.alreadyHandledBy` is
   set, mark this finding `suppressed` — no evidence-validity/
   fingerprint/dedup step runs for it, but it's still listed in the
   final lifecycle-issue report as "already reported by \<job\>."
2. **Evidence validity gate** (data-model.md): a Finding whose cited
   evidence is empty/unresolvable, or whose `normalizedFacts` is missing
   or empty for its class's identifying keys, is marked
   `suppressed: invalid-evidence` here and MUST NOT proceed to
   fingerprinting, dedup, or any write.
3. **Fingerprint**: `sha256(class + "|signals:" + sorted-joined(valid cited
   signal ids))`. No fallback branch — step 2 guarantees every Finding
   reaching this step already carries at least one valid signal id
   (FR-006/FR-007 of spec 024). Unchanged by spec 109 — kept as the exact-
   citation-set hash the closed-issue reopen path (FR-014) still reads.
3a. **Gate-suite filing condition** (spec 109, FR-033/FR-034 — new, runs
   before dedup): if every one of this finding's valid cited ids has kind
   `gate-suite-failure`, AND `collect`'s cycle-outcome state is present
   with `converged=false` and `handoff=false`, AND neither `spec-meta`
   stage nor the `stalled` label say this cycle stalled: outcome
   `converging-gate-suite`. Suppresses filing; dedup (step 4) does NOT run
   for this Finding; reported under its own wording, never as
   `data-integrity` or `unknown`.
4. **Dedup lookup** (FR-020/FR-029 of spec 024; FR-030–FR-032 of spec 109):
   `gh issue list --repo <repo> --label pipeline-defect --label
   "🐕 · <class>" --state all --limit 200 --json number,state,body,comments`
   (`comments` added by spec 109) — a bounded, strongly-consistent direct
   read scoped to the finding's own class — followed by a local `jq`
   filter over that bounded result set, in order: (a) candidate count ==
   200 (the `--limit` ceiling) ⇒ `unknown` (spec 109: a truncated read is
   not a completed one); (b) the exact `fingerprint=$FP` marker, unchanged
   priority and mechanism — checked ahead of (c) regardless of any open
   candidate's comment count, since it reads only `.body`, never
   `.comments`; (c) any OPEN candidate whose `comments` array length is
   >= 100 ⇒ `unknown` (spec 109, Review Gate Round 3: `gh issue list
   --json comments` is a single un-paginated GraphQL page, so a candidate
   at or past that ceiling may be missing ids recorded only in later
   comments — a `none`/`overlap` computed against it is not trustworthy);
   (d) for OPEN candidates only, an intersection between the finding's
   cited ids and each candidate's matchable id set (data-model.md — body +
   comment `signal-ids=` markers, capped at the 30 most-recently-added
   distinct ids). Outcomes: `none` | `match-open` | `match-closed` |
   `overlap` (spec 109: ≥1 open candidate's matchable set intersects;
   comment lands on the lowest-numbered intersecting candidate, others
   named per FR-031, never on a closed issue) | `unknown` (the `gh issue
   list` call itself exited non-zero, or either truncation case above) |
   `data-integrity` (>1 **exact**-fingerprint match — still an anomaly
   under overlap matching too). `unknown` MUST suppress filing and MUST
   NOT share a code path with `none`.

No fix attempt is ever made — the watchdog is a pure reporter with no
diff-producing step (FR-014 of spec 024).

### `act` (`needs: triage`, one matrix entry per non-suppressed Finding)

Executes exactly what the dedup outcome selected:

- **Dedup miss (`none`)**: create a new pipeline-defect issue carrying
  the Finding's evidence and a new `signal-ids=<cited ids>` marker
  (spec 109) additive alongside the `fingerprint=` marker; comment on the
  lifecycle issue linking it.
- **Dedup hit, open (`match-open`)**: comment the fresh evidence on the
  existing pipeline-defect issue; comment on the lifecycle issue linking
  it.
- **Dedup hit, closed (`match-closed`)**: reopen the existing
  pipeline-defect issue and comment the fresh evidence; comment on the
  lifecycle issue linking it.
- **Overlap match, open (`overlap`, spec 109)**: comment the fresh
  evidence, plus a `signal-ids=` marker and which ids matched/are new
  (FR-034), on the lowest-numbered matching pipeline-defect issue only;
  any other matching issue is named in that comment (FR-031) but never
  written to; comment on the lifecycle issue linking the one issue
  written.
- **Lookup failed or truncated (`unknown`)**: suppress every write for
  this Finding; report "dedup lookup failed — finding suppressed, needs a
  maintainer's manual check" (or the truncation-specific wording, spec
  109) on the lifecycle issue. Checked before, and sharing no code path
  with, the `none` branch above.
- **`data-integrity`**: report only, no auto action (unchanged — still
  reserved for >1 *exact*-fingerprint match).
- **Converging-cycle gate-suite finding (`converging-gate-suite`, spec
  109)**: no write of any kind; reported on the lifecycle issue under its
  own wording (FR-011/FR-019 of this spec, FR-033 of spec 109) — never as
  `data-integrity` or `unknown`, which mean "could not decide" rather than
  "decided this is not a defect."

No PR is ever opened by `act` (FR-014 of spec 024).

Every `act` outcome, plus the `passed-inspection`/`could-not-inspect`
short-circuits from `collect`/`diagnose`, is appended as one comment (or
one comment covering all findings from this run, implementation's
choice) to the run's lifecycle issue — this is the one write every path
through this workflow performs unconditionally (FR-022).

## Self-dispatch cap contract (FR-018, applies to `act`'s one write path only)

Before any write in `act`, if `workflow_run.name == "8 - Watchdog"` (this
is a self-inspection), walk `gh run list --workflow "8 - Watchdog" --json
databaseId,event,createdAt --limit <cap + 5>` backward from the inspected
run, counting a consecutive chain of `event == "workflow_run"` entries.
Depth `>= vars.WING_COMMANDER_WATCHDOG_SELF_DISPATCH_CAP` (default `3`)
⇒ every Finding this run produced is forced to report-only (as if paused,
research.md) regardless of what the dedup outcome would otherwise
select — `collect` and `diagnose` still ran and still get reported, only
`act`'s writes are suppressed.

## Pause contract (FR-019)

`vars.WING_COMMANDER_WATCHDOG_PAUSED == 'true'` ⇒ identical short-circuit
to the self-dispatch cap: `act` performs no write for any Finding, and
the lifecycle-issue report says so explicitly.

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- A scheduled catch-up sweep for missed runs (FR-025 explicitly defers
  this beyond v1).
- Opening a pull request of any kind — the watchdog's entire remediation
  surface is the pipeline-defect issue tracker (FR-014 of spec 024); a
  human decides on and makes any code change a filed finding warrants.
- Detecting problem classes beyond the FR-003 v1 pair with the same
  crisp, pattern-matched confidence — other sources (step summaries,
  annotations, general `spec-meta.json` drift) feed the diagnose step's
  judgment, not a second deterministic pattern matcher, and are
  explicitly accepted as carrying more false-positive risk (FR-006).
- Re-litigating or replacing `implement.yml`'s own stalled-retry logic
  or `cleanup.yml`'s three outcomes — both are unchanged; this stage only
  reads their resulting state to avoid duplicating their reports
  (FR-024).
