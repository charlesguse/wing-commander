# Contract: Watchdog Sentinel-Set Addition

Normative contract for FR-012 / SC-004 (User Story 3). Defines the single
edit to `watchdog.yml`'s step-summary sentinel set and the guarantee it
provides — no other watchdog code changes.

## The edit

`.github/workflows/watchdog.yml`, `Collect: step summaries` step
(`id: collect-step-summary`, ~line 618):

**Superseded 2026-08-08 — do NOT extend the `sentinels=` alternation.** The
original edit added `clarification-mismatch` to that bare-word list, and
that made the signal unreachable:

```
match_line="$(printf '%s' "$runtime" | grep -Eim1 "$sentinels" || true)"
                                            ^^^ first match in the WHOLE job log
```

`-m1` yields **one** sentinel line per job. The clarification steps run at
the very end of their job, and `denied` — already in the alternation — matches
any line where the agent discusses a permission denial, which `intake.yml`'s
prompt actively coaches it to do. Any such line earlier in the job masked
the clarification signal permanently. A sentinel another sentinel can
silence is not a safety net.

`docs/agent-friendly-workflows.md` already prescribed the fix: *"match only
an unmistakable emitted token (`WC-SENTINEL: stalled`) that cannot appear in
unexecuted source text."* So these two are **emitted-token** sentinels, kept
out of the bare-word alternation entirely:

```diff
- sentinels='stalled|rejected|turn budget warning|could not inspect|denied|abandon'
+ sentinels='stalled|rejected|turn budget warning|could not inspect|denied|abandon'
+ token_re='WC-SENTINEL: [a-z][a-z0-9-]*'
```

with a second pass in the same loop emitting **one signal per distinct
token per job**, so no token can mask another. The bare-word pass keeps its
`-m1` cap: those are ordinary English words that occur incidentally in agent
output, and uncapping them would flood the diagnose step.

Note `token_re` cannot self-match its own source line — after
`WC-SENTINEL: ` it requires `[a-z]`, and the source has `[`. That property is
deliberate and matches the care the surrounding collector already takes.

| Token | Emitted when | Means |
|---|---|---|
| `clarification-mismatch` | The structured decision and the colon-form `[NEEDS CLARIFICATION:` marker scan disagree about the same `spec.md` | One of the two views of "does this spec have open questions" is wrong. In the dangerous direction (structured empty, markers present) the emitting step ALSO sets `blocked=true` and fails the run — the sentinel reports, the veto acts |
| `clarification-orphaned` | `specified == true` and `clarifications` is non-empty, but "Resolve created spec" found no `spec-draft/NNN-*` branch | The questionnaire is posted (deliberately — dropping it is the silent loss this feature removes) against a spec the rest of the pipeline cannot resolve, so the clarify loop that should consume the reply may not be reachable |
| `clarification-unclaimed-spec` (intake only) | `specified == false` and "Resolve created spec" DID resolve a spec dir | The mirror image of `clarification-orphaned`, and the only combination that suppresses both arms of the split: `specified` gates the spec-PR announcement, so nothing is posted at all. Either the agent authored the spec and mis-set the discriminator — an unannounced spec PR now sits in the review queue — or a stale `spec-draft/NNN-*` branch from an earlier run on this issue survived and every later spec-dir read belongs to that run. Reported, not vetoed: there is no readiness claim being made to block, and `specified` still decides (FR-004). If that spec.md *also* carries markers, the existing cross-check veto fires on top and the run goes red |

All three are emitted by the same step under the same stdout+summary
discipline, in the form `⚠️ WC-SENTINEL: <token> — <human-readable detail>`.
The collector needs no edit for any of them: its emitted-token pass matches
`WC-SENTINEL: [a-z][a-z0-9-]*` generically and yields one signal per distinct
token per job, so a new token is a workflow-side change only.

## Why this is sufficient

That step already scans each job's **runtime log output** (explicitly
excluding echoed step source — the step's own comment documents a
2026-07-24 false-positive audit that traced 7 false findings to matching
against a step's own script text) for a case-insensitive match against the
`sentinels` alternation, and forwards a matching line as a `step-summary`
Signal with `matched-sentinel` and `matched-line` facts. `contracts/
clarification-schema.md`'s cross-check step writes a line containing the
literal token `clarification-mismatch` **both** to `$GITHUB_STEP_SUMMARY`
and to stdout, and the stdout copy is what makes this contract hold:
`$GITHUB_STEP_SUMMARY` is a file rendered on the run summary page, and
GitHub does NOT mirror writes to it into the job log. A summary-only write
would be invisible to the collector — doubly so because the collector
strips `##[group]`/`##[endgroup]` blocks, which is the only place the step's
own script source (and therefore the literal token) would otherwise appear
in the log. With the stdout copy, the sentinel scan finds the line the same
way it already finds every other sentinel today (FR-006's step-summary
requirement is satisfied by the summary write, FR-012's watchdog
requirement by the stdout write; both carry the identical text).

No change is needed to:
- The `Stamp signal ids` step's `step-summary` signal-kind mapping
  (`.github/workflows/watchdog.yml`, `Stamp signal ids` step) — it already
  maps ANY `step-summary`-sourced signal generically by `{job,
  matched-sentinel}` identity, with no per-sentinel special case.
- The `diagnose` step's finding-class vocabulary or prompt — a
  `clarification-mismatch` signal reaches `diagnose` as an ordinary
  `class-hint: null` step-summary signal, and the existing prompt
  instruction ("a signal with `class-hint: null`... needs your own judgment
  to decide whether it describes a genuine problem worth a Finding... weigh
  the job-conclusion and matched-line facts") already covers it without
  modification — the intake/clarify jobs conclude `success` even when they
  emit this warning (the mismatch is logged, not fatal, per FR-006's
  "while still letting the structured output decide the branch"), so the
  diagnose agent will see a `job-conclusion: success` alongside the matched
  line quoting the specific disagreement, exactly the shape its existing
  instructions already reason about for other non-fatal sentinels.
- Finding-class labels — `clarification-mismatch` becomes a Finding's
  `class` only if the diagnose agent judges it worth one, using the
  existing `🐕 · <type>` label registry and `__new__` escape hatch
  unchanged (no new label is pre-created by this feature).

## Acceptance (User Story 3, SC-004)

Given a run of `intake.yml` or `clarify.yml` that emitted a
`clarification-mismatch` line to stdout and the step summary (`contracts/
clarification-schema.md`), a subsequent `watchdog.yml` pass over that run:

1. `Collect: step summaries` matches the sentinel and produces a Signal
   with `facts.matched-sentinel: "clarification-mismatch"`.
2. `diagnose` receives that Signal among its evidence and may produce a
   Finding citing it.
3. The watchdog's existing reporting steps (`Report "findings"` /
   propose-fix machinery) proceed exactly as they do for any other Finding
   — no new code path.

This closes the loop `spec.md`'s User Story 3 describes: "the watchdog
missed both original instances precisely because nothing compared the
spec's content against the callout that was posted" — after this feature,
something does compare them (the cross-check), and the watchdog is now
wired to see the result.
