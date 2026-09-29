# Contract: Directed Proof Run

This is the mechanism spec.md's Assumptions section says does not exist in
the tree yet ("no way to direct a run at one stage of the board loop
exists today; building it is this feature's work"). During implementation
this contract's content is folded into
`specs/057-autonomous-board-loop/contracts/prove-step.md`'s "Re-drive"
section (FR-019, research.md D9); it lives here first because the plan
stage may only write under `specs/060-self-redrive-concurrency/`.

## What it is

A `workflow_dispatch` of `board-loop.yml` carrying a non-empty
`directed-stage` input. It runs exactly one job of the pipeline
(`select`/`triage`/`route`/`fix`/`review`/`readiness`/`prove-gate`/`prove`)
against a caller-supplied issue (and, for `prove`, PR) rather than one
`select()` chose, and it is the only kind of `board-loop.yml` run permitted
to be in flight at the same time as another `board-loop.yml` run
(research.md D3, FR-002).

## New `workflow_dispatch` inputs (`board-loop.yml`)

| Input | Required | Default | Notes |
|---|---|---|---|
| `directed-stage` | no | `""` | one of the aimable jobs below; `""` means an ordinary run |
| `directed-issue` | no | `""` | the issue number the directed run acts on |
| `directed-pr` | no | `""` | the PR number; only meaningful when `directed-stage == "prove"` |

`attempt-token` (existing input) is unchanged: it still names the
correlation token the caller's `wing-commander-dispatch-and-wait` composite
call uses to find the dispatched run, passed through
`workflow-inputs` alongside the three inputs above.

## Aimable stage set (FR-002, research.md D2)

| Stage | Aimable? | Why |
|---|---|---|
| `select` | No | its job body *is* the item-picking logic; running it directed would either pick nothing or violate FR-002's "MUST NOT select a board item" |
| `triage` | Yes | acts on one given issue; can close it, never opens a PR |
| `route` | No | can push a branch/PR for the size-and-path backstop's post-push breach case |
| `fix` | No | exists to open the fix PR |
| `review` | Yes | acts on one given, already-open PR; posts findings, opens nothing |
| `readiness` | Yes | report-only, never merges (FR-068) |
| `prove-gate` / `prove` | Yes (jointly, as `"prove"`) | the FR-002a-mandated target |

A changed path whose only executor (per the job-uses-graph, research.md
D1) is `select`, `route`, or `fix` renders `directed_stage() == None` —
FR-010a's "no directed run reaches the changed behaviour" — never a
directed run of one of those three, and never a fallback to a whole
iteration (FR-002b).

## Job gating

- `select`: `if: github.event_name != 'pull_request' && inputs.directed-stage == ''`
  (unchanged trigger scope, newly excludes a directed dispatch).
- `triage`/`route`/`fix`/`review`/`readiness`: unchanged `needs: select`
  chain — a skipped `select` skips these by GitHub's own default
  `needs`-implies-`success()` semantics, so no additional `if:` edit is
  required for the ordinary-vs-directed split; each of these still needs
  its own additional `if: inputs.directed-stage == '<own-name>' ||
  inputs.directed-stage == ''` style guard added only for the two
  (`triage`, `review`, `readiness`) that become directed-reachable, so a
  directed `triage` run does not also fall through into `route`.
- `prove-gate`: `if: (github.event_name == 'pull_request' ||
  (github.event_name == 'workflow_dispatch' && inputs.directed-stage ==
  'prove')) && vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'`. Its
  "Resolve the originating issue" step sources `PR_NUMBER`/`MERGED` from
  `inputs.directed-pr` / a live `gh pr view` re-check when
  `github.event_name == 'workflow_dispatch'`, instead of
  `github.event.pull_request.*` — re-deriving from live GitHub state
  exactly as the event path already does, never trusting the dispatch
  inputs blindly.
- `prove`: `if: needs.prove-gate.outputs.eligible == 'true' &&
  vars.WING_COMMANDER_BOARD_LOOP_PAUSED != 'true'` (unchanged condition;
  `prove-gate`'s widened `if:` is what admits the directed path).

## What a directed proof run must never do (checked, research.md D7)

1. Select a board item — enforced by construction (D2 excludes `select`)
   and checked structurally (the aimable-jobs constant excludes it).
2. Open a fix PR — enforced by construction (D2 excludes `fix`/`route`).
3. Race the dispatching run for the same issue as its board item, open a
   second fix PR for it, or close an issue the dispatching run is still
   acting on — `board_eligibility.in_flight_candidate()`'s existing
   exclusion of `step in {"prove", "proven", ...TERMINAL_STEPS}` from
   ordinary selection already forecloses this; D7 adds the fixture that
   exercises it under the new overlap this feature introduces rather than
   leaving it argued only.

## Attribution (FR-011)

Any comment a directed proof run posts to the issue it acts on states that
it is a directed proof run and names the merge/PR it is proving, so a
maintainer reading the issue never mistakes it for an ordinary lifecycle
comment.
