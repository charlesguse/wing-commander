# Contract: `wing-commander-chain-stop-notice` composite action

**New published composite** (constitution VII — part of the published
contract from the moment it merges; its own `inputs:`/`outputs:` are a
compatibility surface, resolved the same way every existing composite is,
via the pipeline repository's self-checkout snippet). Location:
`.github/actions/wing-commander-chain-stop-notice/action.yml`.

## Purpose

Encapsulate the three-effect "stage did not start" stall sequence — mark
`spec-meta.json` stalled, flip the `stage:*` label, post the notice — as one
shared shape, called from the abnormal-termination arm of every gated
stage's survivor job (data-model.md's condition table). Deliberately does
**not** handle the refusal note (that stays `wing-commander-callout`,
unchanged, called in-job per research.md D1) and deliberately does **not**
touch `implement.yml`'s existing exhausted-retry notice (research.md D7,
left as its current inline steps).

## Inputs

| Name | Required | Default | Notes |
|---|---|---|---|
| `token` | yes | — | Needs `issues: write` and, when `spec-dir` is set, `contents: write` on the spec branch |
| `issue-number` | yes | — | Where the notice is posted. May be a PR number for pr-conversation's degraded case (research.md D6) — `gh issue comment` accepts either |
| `spec-dir` | no | `""` | Empty means "no record to mark" (research.md D5) — always empty for intake; always empty for any stage where independent identity re-derivation (data-model.md's per-stage table) itself failed |
| `spec-branch` | no | `""` | Required together with `spec-dir`; ignored when `spec-dir` is empty |
| `stage-label` | no | `""` | `stage:<name>` label to remove on a successful mark; empty is valid (nothing to remove, e.g. intake) |
| `run-url` | no | `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}` | Caller may override; the default is always available regardless of any job's outcome |
| `reason` | yes | — | One sentence naming where the run stopped |
| `restart-command` | no | `""` | Fully caller-rendered; empty renders as a generic "re-dispatch this stage" line |

## Outputs

None. This composite is intentionally best-effort (FR-011) — no caller
branches on its result; a caller that wants to know whether the record was
actually marked has no need to, because the notice itself already states
whether the mark succeeded.

## Behavior guarantees

- **Never fails the job it runs in.** Every internal step after the first
  uses `if: always()` relative to the steps before it (mirrors the existing
  `stalled` job's `Report`/`Announce` steps), so a checkout failure or a
  rejected push degrades the notice's wording rather than aborting the
  composite (FR-011, Edge Cases "record cannot be written").
- **Idempotent on the mark.** A record already reading `stage: "stalled"`
  from an earlier failed iteration produces no commit (`git diff --cached
  --quiet` short-circuit, unchanged from today's `stalled` job) and is not
  treated as a failure.
- **Exactly one comment per invocation.** One `gh issue comment` call,
  `--body-file` only (never `--body "$(...)"`, matching
  `wing-commander-callout`'s injection-safety discipline) — this composite
  is the only writer of the abnormal-termination notice; FR-006's global
  at-most-one-notice guarantee is enforced by the *caller* never invoking
  both this composite and the refusal callout for the same run (data-model.md's
  mutually-exclusive survivor-job arms), not by anything inside this
  composite.
- **No new untrusted-content path.** `reason` and `restart-command` are
  always caller-constructed from this repository's own fixed strings and
  declared `workflow_call` inputs (spec-dir, issue-number, iteration) — never
  from `github.event.*` body text.

## Call sites (all seven — six stages, tasks has two entry jobs)

Every call site passes the same shape (data-model.md's condition table
governs *when* the job that calls this composite runs; this contract governs
*what happens once it does*). Gate 28 asserts every one of the seven uses
this composite rather than a bespoke inline reimplementation (FR-017a,
FR-013's fourth required mutation).
