# Contract: `Flip stage label for clarification` (new step, intake.yml and clarify.yml)

**Not a new published composite** (constitution VII) — a new inline step
inside each of two existing published stages (`intake.yml`, `clarify.yml`).
It reads and writes nothing beyond the two stages' existing declared
`workflow_call` inputs (`issue-number`) and the App-installation token every
step in these jobs already has; no `workflow_call` input, output, or secret
of either stage changes (FR-016-equivalent constraint, restated here from
constitution VII though this feature's spec does not number it separately).

## Purpose

Make the `stage:clarify` label a real, pipeline-written signal (FR-010,
FR-011, FR-012) derived from the exact same single decision each stage
already computes for its callout (FR-013), positioned so the flip is
visible in the issue's label state before anything downstream (the spec
PR's mirrored labels, FR-023) reads it.

## Preconditions (per call site)

| Stage | Precondition |
|---|---|
| `intake.yml` | Runs after `steps.clarification` (the decision step) and after the agent's own `stage:spec` add (line 689, inside the earlier agent step) — never before either |
| `clarify.yml` | Runs after `steps.clarification` (the decision step); the issue already carries either `stage:spec` (first clarification round, or an issue mid-clarification when this feature merged — FR-004) or `stage:clarify` (a later round) |

## Behavior — intake.yml

```bash
if [ "$NEEDED" = "true" ]; then
  gh label create "stage:clarify" --color 1D76DB --description "Open clarification questions" --force || echo "::warning::wing-commander intake: could not create the stage:clarify label (the clarification questionnaire will still be posted)." >> "$GITHUB_STEP_SUMMARY"
  if ! gh issue edit "$ISSUE" --add-label "stage:clarify"; then
    echo "::warning::wing-commander intake: could not add stage:clarify to issue #$ISSUE (the clarification questionnaire was still posted)." >> "$GITHUB_STEP_SUMMARY"
  fi
  gh issue edit "$ISSUE" --remove-label "stage:spec" 2>/dev/null || true
elif [ "$SPECIFIED" = "true" ] && [ "$BLOCKED" != "true" ] && [ -n "$SPEC_DIR" ]; then
  gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
fi
```

`if: steps.lifecycle-gate.outputs.is-open == 'true'`. Env: `NEEDED =
steps.clarification.outputs.needed`, `SPECIFIED =
steps.clarification.outputs.specified`, `BLOCKED =
steps.clarification.outputs.blocked`, `SPEC_DIR =
steps.created.outputs.spec-dir`, `ISSUE = inputs.issue-number`.

## Behavior — clarify.yml

```bash
case "$OUTCOME" in
  needs-clarification)
    gh label create "stage:clarify" --color 1D76DB --description "Open clarification questions" --force || echo "::warning::wing-commander clarify: could not create the stage:clarify label (the follow-up questionnaire will still be posted)." >> "$GITHUB_STEP_SUMMARY"
    if ! gh issue edit "$ISSUE" --add-label "stage:clarify"; then
      echo "::warning::wing-commander clarify: could not add stage:clarify to issue #$ISSUE (the follow-up questionnaire was still posted)." >> "$GITHUB_STEP_SUMMARY"
    fi
    gh issue edit "$ISSUE" --remove-label "stage:spec" 2>/dev/null || true
    ;;
  ready)
    if [ "$BLOCKED" != "true" ]; then
      gh label create "stage:spec" --color 1D76DB --description "Spec drafted / awaiting review" --force
      if ! gh issue edit "$ISSUE" --add-label "stage:spec"; then
        echo "::warning::wing-commander clarify: could not add stage:spec to issue #$ISSUE (the spec PR was still announced ready)." >> "$GITHUB_STEP_SUMMARY"
      fi
      gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
    fi
    ;;
  none|*)
    ;;
esac
```

`if: steps.lifecycle-gate.outputs.is-open == 'true'`. Env: `OUTCOME =
steps.clarification.outputs.outcome`, `BLOCKED =
steps.clarification.outputs.blocked`, `ISSUE = inputs.issue-number`.

## Guarantees

- **Never fails the job.** Every `--add-label` failure path is caught
  explicitly (`if ! gh ...; then warn; fi`); the `stage:clarify`-creating
  `gh label create` call is guarded with `|| echo "::warning::..." >>
  "$GITHUB_STEP_SUMMARY"` so a create failure cannot abort the step under
  the step's default `bash -eo pipefail` before the questionnaire is
  rendered or announced (maintainer feedback on PR #651: this step runs
  before `Render clarification questionnaire`/`Announce remaining
  clarification questions`, neither of which is gated `!cancelled()`); no
  branch calls `exit 1`. A checked-in fixture proves this per stage
  (quickstart.md §2).
- **Idempotent.** `gh label create --force` never errors on an existing
  label; `gh issue edit --add-label` on an already-present label is a
  no-op; `gh issue edit --remove-label` on an absent label exits non-zero,
  caught by `2>/dev/null || true` (Edge Cases: "applying a label that is
  already present, or removing one that is already absent, must be a
  no-op").
- **At most one current `stage:*` label at a time (FR-012).** Every add is
  paired with a same-step, same-branch removal of the label it replaces —
  never an add alone.
- **No new untrusted-content path.** `$NEEDED`/`$OUTCOME`/`$SPECIFIED`/
  `$BLOCKED` are this repository's own step outputs, computed from the
  agent's *schema-validated structured result* (already trusted for the
  callout decision), never from `github.event.*` comment body text.
- **Ordering (FR-023, intake only).** This step runs after `intake.yml`'s
  agent-prompt `stage:spec` add (line 689) and before `Label spec PR to
  match the issue` (line 1256, unchanged) — verified by the step's fixed
  position in the job (data-model.md), not by a runtime check. `clarify.yml`
  has no PR-label-mirror step, so no equivalent ordering constraint applies
  there.

## Non-goals

- Does not touch `plan.yml`'s existing two `--remove-label "stage:clarify"`
  cleanup lines (`:1155`, `:1241`) — they start doing real work once this
  step ships, unchanged themselves.
- Does not touch `clarify.yml:1292`'s `stage-label: "stage:clarify"` input
  to `wing-commander-chain-stop-notice` — it starts removing a real label
  once this step ships, unchanged itself (specs/041's composite contract is
  untouched).
- Does not change `wing-commander-2-clarify.yml`'s trigger condition
  (`:25`) or its `docs/adoption.md:229` copy — both already admit
  `stage:clarify`; this feature is what makes that disjunct reachable for
  the first time (User Story 2), not a change to the condition itself.
