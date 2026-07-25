# Contract: `wing-commander-lifecycle-gate` (new composite action)

A new shared composite under `.github/actions/wing-commander-lifecycle-
gate/`, following the same authoring pattern as every existing composite in
this repository (`wing-commander-preflight`, `wing-commander-context`,
`wing-commander-callout`): pinned by the caller's own pipeline-repository
checkout at `github.job_workflow_sha` (never assumes it lives in the
workspace-root repository), single responsibility, no hidden state.

## Purpose

Answer exactly one question — "is this lifecycle issue currently open?" —
by re-fetching it live from the GitHub API, so every comment-/label-/
PR-merge-/dispatch-triggered stage entry point can decline to act on a
closed lifecycle issue at the trigger layer (FR-001, FR-002), consistently
(FR-004), and so that the decision reflects the issue's state *at the
moment the stage would act* rather than a stale event payload (FR-005,
spec.md's "race at close time" edge case).

## Inputs

| Input | Required | Description |
|---|---|---|
| `issue-number` | yes | The lifecycle issue to check |
| `token` | yes | A token with at least `issues: read` (the calling job's `github.token` is sufficient — this composite runs before any stage mints its GitHub App token, by design, so it does not depend on that later step) |

## Outputs

| Output | Values | Meaning |
|---|---|---|
| `state` | `OPEN` \| `CLOSED` | Raw value from `gh issue view "$ISSUE" --json state --jq .state`. **Uppercase** — `gh --json` reads through GitHub's GraphQL API, not REST, so it reports `OPEN`/`CLOSED`, not `open`/`closed` (`cleanup.yml`'s "Idempotency check" compares against `CLOSED` for the same reason) |
| `is-open` | `"true"` \| `"false"` | `"true"` iff `state` is `OPEN`, `"false"` iff `CLOSED`, compared case-insensitively — the value every subsequent step's `if:` reads |

## Behavior

1. Run `gh issue view "$ISSUE_NUMBER" --json state --jq .state` using the
   supplied `token`. No other issue field is read (labels/commenter
   identity stay the existing who/what gates' responsibility — this
   composite only ever answers the state question).
2. Set `is-open` accordingly, matching the returned state
   case-insensitively against `open` and `closed`. This step performs no
   write and has no side effect of its own — posting the FR-012 decline
   note is the **calling job's** responsibility (via a sibling
   `wing-commander-callout` step gated on this composite's own output), not
   this composite's, keeping its contract to "read state, report it" only.
3. This step does **not** tolerate its own failure silently (unlike
   `wing-commander-preflight`'s deliberately fail-fast posture for
   load-bearing values) — if `gh issue view` fails (e.g. the issue does not
   exist), the step fails loudly with `::error::`, since a stage cannot
   safely default to either "open" or "closed" when it cannot determine
   the truth; this mirrors every other load-bearing lookup in this
   codebase (e.g. `clarify.yml`'s "Verify spec identity" step) rather than
   introducing a new fail-open or fail-closed default.
4. The same refusal-to-default applies to a state value that is neither
   `open` nor `closed`: the step fails loudly rather than treating the
   unrecognized value as "closed". An `else`-branch default is what turned
   a one-word casing mistake into a silent pipeline-wide outage — all five
   gated stages declined every trigger while still reporting success,
   because "not the string I expected" and "this lifecycle is closed" were
   the same branch.

## Caller contract (every affected reusable workflow)

Each calling job:

```yaml
- name: Check lifecycle issue state
  id: lifecycle-gate
  uses: ./.wing-commander-pipeline/.github/actions/wing-commander-lifecycle-gate
  with:
    issue-number: ${{ inputs.issue-number }}   # or the spec-meta.json-derived value for tasks-approved
    token: ${{ github.token }}

- name: Note closed lifecycle and stop
  if: steps.lifecycle-gate.outputs.is-open != 'true'
  uses: ./.wing-commander-pipeline/.github/actions/wing-commander-callout
  with:
    token: ${{ github.token }}
    issue-number: ${{ inputs.issue-number }}
    kind: info
    summary: "This lifecycle issue is closed — no action was taken."
```

Every step from `wing-commander-preflight` onward in that job gains
`if: steps.lifecycle-gate.outputs.is-open == 'true'`, ANDed with any
`if:` it already has (contracts/lifecycle-gate-points.md enumerates the
exact step list per workflow).

## Non-goals

- Does not check who commented or what labels the issue carries — those
  gates are unchanged and stay exactly where they already live (wrapper
  `if:` conditions for clarify/intake; spec.md Assumptions).
- Does not itself post the decline note — kept as a separate, reusable
  `wing-commander-callout` call so this composite's contract stays
  single-purpose and its output is independently testable.
- Does not cache or memoize state across steps or jobs — every call is a
  fresh read, by design (research.md R3).
- Does not change `wing-commander-preflight`'s contract or add a network
  call to it — it remains pure shell, no network, exactly as documented in
  its own header.

## Permissions

Requires only `issues: read` on the supplied token to check state, and
`issues: write` (already granted at job level everywhere it is used, for
the pre-existing `wing-commander-callout` calls) to post the decline note.
No new permission scope beyond what each calling job already has.
