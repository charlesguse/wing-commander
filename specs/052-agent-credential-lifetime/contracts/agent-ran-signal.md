# Contract: the agent-ran signal and its stall-path consumption

**Files**: all 8 sweep-stage workflows (publication); `implement.yml`,
`finalize.yml`, `clarify.yml`, `intake.yml`, `pr-conversation.yml`,
`tasks.yml` (consumption, via each stage's existing `stalled`/survivor job
and the shared `wing-commander-chain-stop-notice` composite, spec 041).

## Publication (every job with at least one agent step, all 8 stages)

Immediately after each agent step, before the credential refresh
(contracts/wing-commander-context-relay.md), an `if: always()` step:

```yaml
- name: Record agent-ran signal
  if: always()
  id: agent-ran
  shell: bash
  run: |
    echo "ran=true" >> "$GITHUB_OUTPUT"
    echo "conclusion=${{ steps.<agent-id>.conclusion }}" >> "$GITHUB_OUTPUT"
```

The job's `outputs:` block gains:

```yaml
agent-ran:
  value: ${{ steps.agent-ran.outputs.ran }}
agent-conclusion:
  value: ${{ steps.agent-ran.outputs.conclusion }}
```

For a job with more than one agent step (`implement.yml`), each agent
step's own `agent-ran`-shaped step shares neither `id` nor step name
verbatim (`agent-ran-cycle` / `agent-ran-retry` / `agent-ran-progress`) but
all three write to the *same* `$GITHUB_OUTPUT` keys the job output maps
from — the last one to run wins, by construction (research.md D3), which is
what "the most recent agent step that ran" requires.

No field carries model-authored text (FR-014). `conclusion` is one of the
three enum values GitHub Actions itself assigns
(`success`/`failure`/`cancelled`) — never free text, never copied from the
agent's own output.

## Consumption (the six stages with an existing survivor job)

Inside each survivor job's existing "Determine which dependency did not
start" step (spec 041's `id: reason`), one new branch is inserted ahead of
the existing fallback:

```text
when needs.<entry-job>.outputs.agent-ran == 'true':
    reason = "the agent step ran (concluded: <agent-conclusion>) and a
              step after it did not complete"
else:
    # unchanged — today's existing diagnosis, including the distinction
    # between a failed prerequisite job and a skipped one
```

The chain-stop notice's "stage did not start" body (spec 041's rendering,
`wing-commander-chain-stop-notice`) is passed this reason string as-is —
its own template already interpolates `<reason>` freely, so no template
change is needed beyond dropping the hard-coded "No implementation attempt
was made" sentence when `agent-ran == 'true'` (that sentence remains
verbatim for the `agent-ran` unset case — FR-012's "today's diagnosis
unchanged").

### Cancellation (FR-013)

When the job was cancelled after the agent ran, `agent-conclusion` reads
`cancelled` (GitHub Actions sets this on the agent step itself, which the
`Record agent-ran signal` step — itself `if: always()` — reads before the
job's own teardown). The reason string renders "...concluded: cancelled",
which the survivor job's existing `!cancelled()` guard (spec 041 D4) — on
the *job* condition, not this step's `if:` — already prevents from
reaching the notice at all for a run cancelled cleanly; the enum value
exists so a partially-completed cancellation (agent step cancelled, but the
job's later steps still ran long enough to hit a genuine failure before the
run-level cancel propagated) does not get mis-described as "never started."

## Lifecycle-record resume wording (FR-015)

`wing-commander-chain-stop-notice`'s existing `restart-command` input
(caller-rendered per stage, spec 041 D7) is passed a resume-oriented
sentence instead of its current restart-from-zero phrasing when
`agent-ran == 'true'`: the caller (each stage workflow, not the composite)
chooses the string; the composite's own contract is unchanged.

## Not in scope for consumption

`plan.yml` (no survivor job exists — research.md D4) and
`auto-update-spec-kit.yml`'s `e2e-stage` (not part of the
`wing-commander-chain-stop-notice` pattern at all) publish this signal with
no reader. Verified by the new gate's structural check only asserting
*publication* uniformly across all 8, and asserting *consumption* only for
the six named stages (contracts/post-agent-credential-refresh-gate.md does
not cover consumption at all — that is proven by
`.github/scripts/verify-implement-stall-notice-unchanged.py`'s existing
family, extended in the same PR to the new branch, not by the new gate).
