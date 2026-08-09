# Contract: Autonomy Configuration, Intent Announcement, and Stop (FR-020, FR-023, FR-024)

Implements research.md D9/D10. Ties three requirements together because
they are mechanically one system: what gets announced, whether it waits
for confirmation, and how it can be stopped.

## Autonomy configuration (FR-020)

Two repository variables, read only by `wing-commander-9-pr-conversation.yml`
and passed as `workflow_call` inputs (`contracts/reusable-pr-conversation.md`);
never read by the stage from `vars.*` directly (constitution VII).

| Variable | Default | Meaning |
|---|---|---|
| `WING_COMMANDER_PR_CONVERSATION_CONFIRM_CATEGORIES` | `""` (empty) | Comma-separated `RequestClassification.category` values requiring propose-and-confirm, or the literal `all`. Empty = act-then-report for every category (the spec's stated default). |
| `WING_COMMANDER_PR_CONVERSATION_CONFIRM_ENVIRONMENT` | `pr-conversation-confirm` | Name of the GitHub deployment environment the consumer configures with required reviewers to give the confirm gate teeth. |

`requires-confirmation` (data-model.md) is computed by a deterministic
step in `classify-and-announce` — a plain set-membership check against
`confirm-categories` — **not** by the classify agent step, so autonomy
behavior can never be shaped by PR conversation content (FR-020's explicit
prohibition), even though the *category* it's checked against is
agent-assigned.

## Confirmation mechanism (FR-020's "propose-and-confirm")

`pr-conversation.act`'s job-level `environment:` binds conditionally:

```yaml
environment:
  name: ${{ needs.classify-and-announce.outputs.confirm-environment-for-this-classification }}  # "" when act-then-report
  deployment: false
```

Per `specs/031-stage-environment-binding/contracts/environment-binding.md`'s
empirical basis: an empty `name` is a verified true no-op (item 1), and the
mapping form's `name` accepts an expression (item 2) — so this is the
*entire* mechanism, no new pipeline code beyond computing which string to
put there. A consumer who has not configured required reviewers on the
named environment gets no gate at all, silently — the same documented
pass-through caveat spec 031 already carries for its own binding, restated
here rather than re-solved (constitution VI: this is adopter
configuration, not a pipeline behavior).

**Reject = stop, for free**: a required reviewer rejecting the environment
deployment is GitHub's own native "don't do this" signal — `act` never
runs, and nothing further is needed to honor a maintainer's "no" during
the confirm window; this is not a separate code path from D10's stop
procedure below, since the mutating job simply never started.

## Intent announcement (FR-023)

Posted by `classify-and-announce` (never by `act`, and always before `act`
starts — structurally guaranteed: `act`'s `environment:` binding cannot
even begin evaluating until the prior job completes, and the prior job's
last step is this announcement). One callout per `RequestClassification`
(`contracts/classification-schema.md`'s "multi-classification" note), each
containing:

- the assigned `category` and `summary`,
- the `planned-action` (one sentence — e.g. "re-run implement/converge" /
  "open a spin-off PR to `main`" / "decline: conflicts with constitution
  principle V"),
- the run URL: `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`
  (the exact expression `implement.yml`/`watchdog.yml` already use).

Posted to the PR always; additionally to the lifecycle issue when the
planned action is itself out-of-PR (`contracts/spinoff-routing.md`'s
routes), per FR-013.

## Stop procedure (FR-024)

Two independent paths, both free of any new polling mechanism
(research.md D10):

1. **Direct cancellation**: the maintainer cancels the run at the
   announced URL themselves, via GitHub's own UI/CLI (`gh run cancel`).
   Requires zero pipeline code — GitHub Actions itself marks the run
   cancelled, and `pr-conversation.act` (if it was mid-run) stops wherever
   it was, leaving whatever had already been committed/pushed/created up
   to that point (FR-024's "reports what was already done" is satisfied
   post hoc: a maintainer inspecting a cancelled run sees its log directly
   — no additional pipeline reporting step is required for this path,
   since GitHub's own run page already shows exactly this).
2. **Reply-based stop**: a follow-up comment the classify step tags
   `category: "stop"` triggers a **new** `pr-conversation.yml` run
   (event-triggered like any other comment). That run's `act` job:
   - scans the PR's comment thread (`gh api .../issues/{pr}/comments` and,
     for review-thread stops, `.../pulls/{pr}/comments`) for the most
     recent `IntentAnnouncement` posted by the pipeline's own bot account,
     extracting its embedded run URL → `run-id`;
   - `gh run cancel <run-id>`;
   - if that announcement's `planned-action` was an implement re-trigger
     (`contracts/converge-fold-in.md`), additionally `gh run cancel` the
     dispatched `wing-commander-5-implement.yml` run, found via `gh run
     list --workflow wing-commander-5-implement.yml --branch spec/<slug>
     --status in_progress --json databaseId --jq '.[0].databaseId'`;
   - if `gh run cancel` reports the target run already completed (GitHub
     returns a 409/"already completed" for this), or no in-progress run is
     found at all, replies with `StopRequest.outcome == "already-completed"`
     and a summary of what that prior run's own final reply already
     reported (data-model.md) — never implying the action was prevented
     when it was not (FR-024's second clause, verbatim).

Both paths are themselves subject to the same authorized-actor gate as any
other request (spec.md edge case: "a stop request from a non-authorized
actor... does not stop the run") — the reply-based path goes through the
identical wrapper `if:` and stage-level authorization check
(`contracts/wrapper-gate.md`) as every other classification; there is no
separate, weaker gate for stop requests.
