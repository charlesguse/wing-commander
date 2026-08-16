# Contract: PR guard additions to `auto-update-spec-kit.yml`

This project has no library/API surface; its "interface" is the GitHub
Actions job/step contract this feature modifies. This document is the
contract the tasks phase and implementation must satisfy — it changes
**no** input, output, or secret on either workflow's `on: workflow_call`
interface (`.github/workflows/auto-update-spec-kit.yml`,
`.github/workflows/wing-commander-auto-update-spec-kit.yml`); both stay
byte-identical at the trigger-contract level documented in
`specs/027-auto-update-spec-kit/contracts/auto-update-spec-kit-workflow.md`.

## `evaluate-path` job: new guard step, new `outcome` value

Inserted between the existing `entry` step (line 781) and `notes` step
(line 826):

```yaml
- name: Guard against an already-open version-bump PR
  id: guard
  env:
    GH_TOKEN: ${{ steps.ctx.outputs.token }}
    CANDIDATE: ${{ steps.entry.outputs.candidate-version }}
    ISSUE: ${{ steps.entry.outputs.issue-number }}
  run: |
    set -uo pipefail
    # "don't know means don't act" (research.md) — never `|| echo '[]'`.
    if ! prs_json="$(gh pr list --repo "$GITHUB_REPOSITORY" --state open \
          --json number,body,headRefName 2>"$RUNNER_TEMP/guard-err.txt")"; then
      echo "skip=true" >> "$GITHUB_OUTPUT"
      echo "reason=lookup-failed" >> "$GITHUB_OUTPUT"
      exit 0
    fi
    matches="$(printf '%s' "$prs_json" | jq -c '[
      .[] | select((.body // "") | contains("<!-- wing-commander-auto-update-spec-kit: version-bump -->"))
          | {number: .number,
             candidate: (.headRefName | sub("^auto-update-spec-kit/v"; ""))} ]')"
    count="$(printf '%s' "$matches" | jq 'length')"
    if [ "$count" -eq 0 ]; then
      echo "skip=false" >> "$GITHUB_OUTPUT"
    elif [ "$count" -gt 1 ]; then
      echo "skip=true" >> "$GITHUB_OUTPUT"
      echo "reason=multiple-matches" >> "$GITHUB_OUTPUT"
    else
      echo "skip=true" >> "$GITHUB_OUTPUT"
      matched_candidate="$(printf '%s' "$matches" | jq -r '.[0].candidate')"
      if [ "$matched_candidate" = "$CANDIDATE" ]; then
        echo "reason=already-open" >> "$GITHUB_OUTPUT"
      else
        echo "reason=queued-behind" >> "$GITHUB_OUTPUT"
      fi
    fi
    echo "matches=$matches" >> "$GITHUB_OUTPUT"
```

`notes` and `decide` (the Claude-billed step) each gain
`&& steps.guard.outputs.skip != 'true'` on their existing `if:`.

`decide-outcome` (line 934) gains, ahead of its existing `RESUMED`
branch, a `steps.guard.outputs.skip == 'true'` branch that sets
`outcome=guard-skip` and forwards `steps.guard.outputs.reason`/`matches`
as its own outputs — no new job output is declared; `outcome` already
flows to `prepare`'s gate.

A new step, gated on `steps.decide-outcome.outputs.outcome ==
'guard-skip'`, writes the step summary (FR-006) and — only when
`reason` is `already-open` or `queued-behind` **and** the marker's
existing `guard-pr` sub-field differs from the matched PR number — posts
one `wing-commander-callout` comment (`kind: info`) and rewrites the
marker's `guard-pr`/`guard-checked` sub-fields (FR-007). The
`multiple-matches` reason follows `settle`'s own precedent: a warning
every run, no marker write, no dedup (research.md).

## Downstream jobs: unchanged `if:` expressions, changed effective behaviour

`prepare` (needs `evaluate-path`, gate: `outcome == 'clean-bump'`),
`e2e-stage` (needs `prepare`), `verify` (needs `prepare`/`e2e-stage`) and
`act` (needs `health-check`/`evaluate-path`/`prepare`/`verify`) require
**no code change** — `guard-skip` is simply one more `outcome` value
their existing gates already treat as "not clean-bump" / "prepare did
not succeed." This is the load-bearing reason the guard is implemented
as an `outcome` value rather than a new job output (research.md).

## `act` job: new pre-push guard on "Open version-bump PR"

```yaml
- name: Check for a pre-existing branch or pull request
  id: preflight
  if: needs.health-check.outputs.pinned-ok != 'false' && needs.prepare.result == 'success' && needs.verify.outputs.passed == 'true'
  env:
    GH_TOKEN: ${{ steps.ctx.outputs.token }}
    BRANCH: ${{ needs.prepare.outputs.branch }}
  run: |
    set -uo pipefail
    if git ls-remote --exit-code origin "refs/heads/$BRANCH" >/dev/null 2>&1; then
      existing_pr="$(gh pr list --repo "$GITHUB_REPOSITORY" --head "$BRANCH" \
        --state open --json number --jq '.[0].number // empty' 2>/dev/null || true)"
      echo "blocked=true" >> "$GITHUB_OUTPUT"
      if [ -n "$existing_pr" ]; then
        echo "reason=pr #$existing_pr already proposes this candidate" >> "$GITHUB_OUTPUT"
      else
        echo "reason=branch $BRANCH already exists with no open PR — delete it and re-dispatch" >> "$GITHUB_OUTPUT"
      fi
    else
      echo "blocked=false" >> "$GITHUB_OUTPUT"
    fi
```

"Open version-bump PR" (line 2237) gains
`&& steps.preflight.outputs.blocked != 'true'` on its existing `if:`. A
new step, gated on `steps.preflight.outputs.blocked == 'true'`, writes
the step summary and an issue callout naming the branch or PR and the
remedy (FR-015), and the job still concludes as a success — a decline is
not a failure.

## Test-harness contract (`FR-016`)

- `gh_stub.py` gains a `gh pr list` handler (`--state`, `--head`,
  `--json` filters) over its existing `s["prs"]` map — a prerequisite
  for every scenario below, since none exists today (research.md).
- `t7_gating.py` gains: a `step_scenario` for `evaluate-path` (new —
  today only `act` gets step-level assertions) asserting the guard step
  suppresses `notes`/`decide` when `steps.guard.outputs.skip == 'true'`;
  a `scenario` asserting `guard-skip` yields the same
  `{"prepare": False, "verify": False, "act": False}` matrix the
  pre-existing `ambiguous-options` case already asserts; and a
  `scenario` asserting the ordinary "no match" case proceeds exactly as
  today.
- `t5_act.sh` gains two scenarios: a pre-existing remote branch with no
  open PR, and a pre-existing remote branch with an open PR — both
  assert zero push (`remote_refs()` unchanged), zero new PR created, the
  step exits 0, and the summary names the blocking branch/PR and the
  remedy.

Every new/changed `run:` step keeps this file's existing conventions:
`set -uo pipefail` (never bare `set -e` on a step that must degrade
gracefully rather than abort), the `marker_line`/`|| true` idiom for any
`grep -o` against a body that might not match, and the
`"<job>: <what happened>"` `GITHUB_STEP_SUMMARY` prefix.
