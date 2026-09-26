# Contract: The E2E clarification-label assertion (`auto-release.yml`, amended)

**Not a new gate** — an amendment to the existing pass-path stage-label-
timeline check inside `auto-release.yml`'s report/verdict script
(lines 1142-1158 today), satisfying FR-005 (comment correction) and FR-021
(the conditional assertion itself), and closing the gap
`specs/055-unattended-e2e-gates/research.md:450-453` records ("the
clarification gate, which today has no assertion at all").

## Purpose

Prove, on the one E2E run this repository already drives end to end
(`specs/055-unattended-e2e-gates/`), that `stage:clarify` actually appears
in a scratch lifecycle issue's label timeline when — and only when — that
run's intake or clarify stage actually posted a clarification questionnaire.
Distinct from the neighboring, already-shipped `clarification_satisfied`
check (lines 1267-1274, "did every open question get a qualifying reply") —
this contract governs the *label*, that one governs the *comment thread*.

## Inputs (reused, not re-derived — research.md D5)

| Signal | Computed by | Moves? |
|---|---|---|
| `timeline` / `timeline_raw` | Existing `gh api issues/<n>/timeline` read | No — stays first |
| `comments_json` | Existing `gh api issues/<n>/comments` read | **Yes** — moved to immediately after the timeline read, before the label-timeline loop |
| `markers_json` | Existing `auto-release-e2e-clarify-decision.sh markers` call over `comments_json` | **Yes** — moved to the same point, right after `comments_json` |
| `author_id`, `clarification_satisfied` | Existing `auto-release-e2e-clarify-decision.sh satisfied` call | No — stays at its current relative position, now consuming the already-computed `comments_json` instead of reading it again |

No new `gh api` call, no new script, no new mode of `auto-release-e2e-
clarify-decision.sh` — this is a reordering of two existing reads plus one
new derived boolean (`questionnaire_posted`) computed from data already in
hand.

## Behavior

```bash
questionnaire_posted="$(printf '%s' "$markers_json" | jq -e 'length > 0' >/dev/null 2>&1 && echo true || echo false)"
stages_to_check="stage:spec stage:plan stage:tasks stage:implement stage:review"
if [ "$questionnaire_posted" = "true" ]; then
  stages_to_check="$stages_to_check stage:clarify"
  echo "clarification-label assertion: asserting stage:clarify in the timeline (a questionnaire was posted this run)." >> "$GITHUB_STEP_SUMMARY"
else
  echo "clarification-label assertion: skipped -- no clarification questionnaire was posted this run." >> "$GITHUB_STEP_SUMMARY"
fi
missing_stage=""
for s in $stages_to_check; do
  if ! printf '%s' "$timeline" | jq -e --arg s "$s" 'index($s) != null' >/dev/null 2>&1; then
    missing_stage="$s"
    break
  fi
done
if [ -n "$missing_stage" ]; then
  write_verdict "fail-wrong-output" "every intermediate stage label present in the issue timeline" \
    "$missing_stage present at some point in the timeline" "timeline=$timeline"
  emit_verdict
  exit 0
fi
```

replacing the current unconditional five-stage loop and its stale comment
(`:1143-1146`).

## Guarantees

- **A definite outcome every run (SC-007).** Exactly one of the two step-
  summary lines above is always written — "asserted" or "skipped," never
  neither. A silent skip (today's actual behavior, with no comment-to-code
  mismatch even acknowledged) is exactly what this replaces.
- **No new impossible-pass mode (FR-021's core requirement).** A zero-
  question E2E run — the harness drafts a spec with no open questions —
  never has `stage:clarify` demanded of it; the pre-existing regression
  `auto-release.yml:1143-1147`'s comment recorded (requiring the label
  unconditionally made a genuine pass impossible) cannot recur, because the
  new condition reads the same "was a questionnaire posted" signal the
  neighboring `clarification_satisfied` check already trusts.
- **One read, two consumers.** Moving `comments_json`'s read earlier
  removes a would-be duplicate rather than adding one — `markers_json` and
  `clarification_satisfied` both consume the same in-memory value.
- **Comment corrected (FR-005).** The replaced comment states the new,
  true, conditional rule — never re-asserts "stage:clarify is never applied"
  after this feature ships it.

## Verification

- `specs/055-unattended-e2e-gates/`'s existing two-script gate-decision
  coverage (Gate 66: "the two e2e gate-decision scripts cover every
  documented branch") already exercises `auto-release-e2e-clarify-
  decision.sh`'s `markers`/`satisfied` modes; this contract adds no new
  mode for that gate to cover.
- Manual/integration confirmation: the next full E2E run this pipeline
  drives after this feature merges is expected to post at least one
  clarification question (per `specs/055`'s own scratch-repository spec
  fixture) and is the live proof that `questionnaire_posted=true` correctly
  demands `stage:clarify` in the timeline — recorded on the implementation
  PR per this repository's "prove" step for behaviour that only runs in
  Actions.

## Non-goals

- Does not touch the `clarification_satisfied` check's own logic or wording
  (lines 1267-1274) beyond having it consume an already-computed
  `comments_json` instead of reading it a second time.
- Does not add a new verdict outcome/schema field — `fail-wrong-output` with
  `stage:clarify` as the named missing stage is already a representable
  outcome of the existing verdict shape.
