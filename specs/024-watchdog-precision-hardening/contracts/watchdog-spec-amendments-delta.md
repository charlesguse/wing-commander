# Contract Delta: Watchdog Job Contract (`watchdog.yml`)

This is a delta against `specs/015-pipeline-watchdog/contracts/
watchdog-workflow.md`, which remains the base contract for the
watchdog's trigger surface and job sequencing. Only the clauses below
change; the trigger contract (wrapper `workflow_run`/`workflow_dispatch`
listing, no `github.event.*`/`vars.*` reads inside the reusable stage,
the `wing-commander-watchdog-<run-id>` concurrency group) is unchanged.

## `collect` — attribution invariant now applies to all five collector steps

**Current contract** (015): "Five deterministic collector steps... each
tolerating 'this source produced nothing for this run' as success." Two
of the five additionally check that the inspected run executed and owned
the measured artifact before emitting a signal (undocumented in the
015 contract text, though shipped — PRs #135/#137).

**Amended contract**: All five collector steps MUST check, before
emitting any signal: (a) the inspected run's relevant scope (the whole
run, or the specific job/artifact the collector reads) did not conclude
`skipped`/`cancelled`, and (b) the evidence read belongs to something the
inspected run itself produced. A collector whose check fails emits no
signal for that condition — this is silent at the signal level (no
`{class-hint: "unattributable"}` marker; simply nothing appended to
`signals.json`), never silent at the report level (the finding, had one
been produced, would never have existed to report).

## `diagnose` — new evidence-validity gate downstream (not a diagnose-step change)

**Current contract** (015): "Zero Findings in the output ⇒ `diagnose`
sets `outcome: passed-inspection`." Findings with empty/malformed
`normalizedFacts` are passed through to fingerprinting/dedup/filing
unchanged.

**Amended contract**: Between `diagnose` and `triage`'s existing steps, a
new deterministic step evaluates each Finding's evidence validity
(data-model.md). A Finding failing this check MUST be marked
`suppressed: invalid-evidence` and MUST NOT proceed to fingerprinting,
dedup, or any write. This is a new gate, not a change to `diagnose`
itself — the agent step's `--allowedTools`, model, prompt framing
(FR-023 untrusted-content handling), and output schema are unchanged.

## `triage` — fingerprint step loses its fallback branch; dedup step's lookup mechanism and outcome set both change; rung gate and propose-fix are removed

**Current contract** (015):
```
2. Fingerprint: sha256(class + canonical(normalizedFacts))
3. Dedup search: gh search issues --state all "wing-commander-watchdog: fingerprint=$FP in:body"
4. Fix attempt (only for findings whose class matches a changeClasses[].id
   in .specify/memory/watchdog-guardrails.json): claude-sonnet-5...
```
(The shipped code had already diverged from this written text to a
signal-id-primary/normalizedFacts-fallback fingerprint scheme — this
delta corrects the contract to match, then further amends it.)

**Amended contract**:
```
2. Evidence validity gate (see diagnose section above) — new, precedes fingerprinting.
3. Fingerprint: sha256(class + "|signals:" + sorted-joined(valid cited signal ids)).
   No fallback branch. A Finding reaching this step is guaranteed by step 2
   to carry at least one valid signal id.
4. Dedup lookup: gh issue list --repo <repo> --label pipeline-defect
   --label "🐕 · <class>" --state all --limit 200 --json number,state,body,
   then a local jq filter for the fingerprint marker in .body.
   Outcomes: none | match-open | match-closed | unknown (lookup itself
   failed — gh issue list exited non-zero) | data-integrity (>1 match).
   unknown MUST suppress filing and MUST NOT share a code path with none.
5. Fix attempt: REMOVED. No propose-fix step, no rung gate, no diff is
   ever produced or evaluated. `.specify/memory/watchdog-guardrails.json`
   no longer exists and is not read by anything in this job.
```

## `act` — collapses to a single remediation branch

**Current contract** (015, `data-model.md`'s Triage decision entity):
four branches (rung 1 PR / rung 2 PR+issue / rung 3 issue / dedup-match
comment-or-reopen).

**Amended contract**: One branch, selected entirely by the dedup
outcome:

```
none          → create pipeline-defect issue (label pipeline-defect + 🐕 · <class>, fingerprint marker in body)
match-open    → comment on the matched issue with fresh evidence
match-closed  → reopen the matched issue + comment with fresh evidence
unknown       → suppress; report "dedup lookup failed — finding suppressed, needs manual check" on the lifecycle issue
data-integrity → report only, no auto action (unchanged from 015)
```

No PR is ever opened by `act`. Every branch above (except the fully
suppressed `unknown` case, which still reports the *failure*, just not
the finding-as-filed) still appends its outcome to the lifecycle issue,
unchanged from 015's FR-022.

## Removed entirely

- The `propose-fix-model`/`propose-fix-max-turns` workflow inputs.
- Every `triage`-job step between "evidence validity gate" and "dedup
  lookup" that existed solely to produce/evaluate/gate a fix diff.
- The `act`-job steps `Commit fix and open PR (rung 1)` and `Commit fix
  and open PR (rung 2)`.
- `.specify/memory/watchdog-guardrails.json` in full.
- `lint-workflows.yml` Gate 17 and `.github/scripts/
  verify-watchdog-fix-commit.py` (Constitution VIII — a gate MUST NOT
  outlive the subject it checks).

## Unchanged

- `verify-image-prerequisites`, `report-unhandled-failure` jobs.
- Self-dispatch-depth check and its write-suppression flag (now
  suppressing the single remaining write path — issue create/comment/
  reopen — instead of a PR path as well).
- Pause switch (`vars.WING_COMMANDER_WATCHDOG_PAUSED`) — still suppresses
  the one remaining write path.
- Coexistence check (`alreadyHandledBy`) — unchanged per FR-021 of this
  feature's own scope boundary.
- Lifecycle-issue reporting shapes for "passed inspection" and "could not
  inspect this run" (FR-004/FR-005 of spec 015) — unchanged; two new
  report shapes are added ("suppressed: invalid evidence,"
  "dedup lookup failed") alongside them, per the amended `data-model.md`.
