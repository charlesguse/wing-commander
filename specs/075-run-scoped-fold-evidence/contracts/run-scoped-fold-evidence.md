# Contract: `pr-conversation.yml` — run-scoped fold evidence

Delta against specs/042's `contracts/fold-dispatch-once.md`, which this
feature amends rather than replaces. No declared `workflow_call` input,
output, or secret of `pr-conversation.yml` is added, removed, or renamed.
The job graph from spec 042 (`classify-and-announce` → `act` → both
`dispatch-once` and `report-fold-outcomes`, `needs`/`if: always()`
unchanged) is unchanged; this contract covers what those jobs read as
evidence, not their shape.

## New composite action: `wing-commander-fold-evidence`

`.github/actions/wing-commander-fold-evidence/action.yml` — see
data-model.md §3 for its full input/output contract. Both `dispatch-once`
and `report-fold-outcomes` resolve it via the same self-checkout of this
repository they already perform (`pr-conversation.yml` 2644–2647,
2816–2819) — no new checkout step, no new permission.

## Changed step: `act`'s per-leg commit gains attribution (FR-004, FR-005)

A new step, "Install run-attribution hook for this leg's commits," runs in
the `act` job between the leg's checkout and "Act on this classification."
It is deterministic code, not a prompt instruction — the agent's prompt
(2009–2013) and allowed-tools list are byte-for-byte unchanged from spec
042. Every commit made in that leg's checkout for the rest of the job
carries a `Wing-Commander-Run-Id: <github.run_id>` trailer, regardless of
what the agent's own commit message says.

## Changed step: `dispatch-once`'s dispatch decision and fold list (FR-008, FR-014, FR-015)

| Behavior | Spec 042 | This feature |
|---|---|---|
| Evidence source | Unscoped `git log --grep '^fold(' "$BASE_SHA..$TIP_SHA"` | `wing-commander-fold-evidence`'s `folded-json`, scoped to this run |
| Dispatch condition | `tip != base-sha` | `folded-json` non-empty |
| Fold list named in PR comment | Every `fold(<id>):` commit in the unscoped range | Only this run's own `folded-json` entries |
| Branch moved, nothing of this run's own folded | Dispatches anyway (today's defect, FR-014) | Posts one declined-dispatch notice (data-model.md §6); dispatches nothing |
| Branch did not move at all | Silent (unchanged) | Silent (unchanged) |

## Changed step: `report-fold-outcomes`'s per-leg fold check (FR-001–FR-003)

| Behavior | Spec 042 + #417 | This feature |
|---|---|---|
| Evidence source, per leg id | `git log --grep "^fold($id):" "$range"` | Membership of `id` in `wing-commander-fold-evidence`'s `folded-json`, scoped to this run |
| Job-conclusion read (the #417 caller-prefixed match) | Unchanged | Unchanged |
| Outcome vocabulary and derivation table | Unchanged | Unchanged (data-model.md §5) |

## Behavioral guarantees (per FR)

- **FR-001/FR-002/FR-003**: `report-fold-outcomes`'s cross-check keeps both
  halves independently load-bearing; only the fold-evidence half's *source*
  narrows to this run. A leg with a sibling run's same-id commit and no
  commit of its own still reports "not folded" (job conclusion drives that
  branch of the existing table unchanged).
- **FR-004/FR-005**: the attribution signal is written by a git hook
  installed by a deterministic step, lands in the commit itself (not a
  later artifact), and is therefore present even for a leg cancelled
  immediately after its fold commit landed.
- **FR-006**: two `pr-conversation` runs may overlap on one PR; neither
  gains or loses a concurrency group because of this feature (`act`'s
  `wing-commander-${SPEC_DIR}` group and `dispatch-once`'s shared group,
  both from spec 042, are untouched). Each fold commit is self-identifying
  via its trailer.
- **FR-007**: a commit with no `Wing-Commander-Run-Id:` trailer never
  appears in any run's `folded-json` — there is no fallback to id-matching
  alone (data-model.md §1).
- **FR-008**: `dispatch-once`'s fold list is built exclusively from this
  run's own `folded-json`.
- **FR-009**: `wing-commander-fold-evidence` is the one composite both
  `dispatch-once` and `report-fold-outcomes` call; neither job contains its
  own copy of the range-and-grep logic after this feature ships.
- **FR-012**: in the ordinary single-run case, "tip moved" and "own
  evidence non-empty" agree (research.md D3), so `dispatch-once`'s
  observable behavior is unchanged; `report-fold-outcomes`'s per-leg
  outcomes are unchanged because the only source of any commit in range is
  this run's own legs.
- **FR-013**: a run executes entirely under one version of this workflow
  (Constitution VII); no run's commits are retroactively reinterpreted, and
  no run reports "folded cleanly" off a commit it cannot prove is its own
  (research.md D6).
- **FR-014/FR-015**: covered by the table above.

## What this contract does NOT change

- The classification schema, the fold-route category check, or any
  question/no-action/push-back leg's behavior.
- `act`'s concurrency group, `max-parallel: 1`, or its `environment:`
  confirm-gating.
- The `confirm-timeout-minutes` input or any other spec-042 `workflow_call`
  input.
- `report-fold-outcomes`'s job-conclusion read, including the #417
  caller-prefixed job-name match.
- The "not folded" / "partly folded" outcome vocabulary or its silent-on-
  healthy behavior (US2 AS5).

## Gate 34 extension (FR-009, FR-010, FR-011)

No new gate number. `.github/scripts/verify-fold-dispatch-once.py`'s
existing `STAGE`/`load_steps()`/`find_step` extraction (which reads the
shipped `run:` text of `dispatch-once`'s and `report-fold-outcomes`'s
steps directly out of `pr-conversation.yml`) is joined by a second
extraction of `wing-commander-fold-evidence/action.yml`'s own `runs.steps`
`run:` text, stitched into the same synthetic execution environment so the
harness continues to exercise the exact shipped bash on both sides of the
`uses:` call.

**New scenarios** (`SCENARIOS`, alongside the seven existing ones),
covering FR-010's six enumerated cases:
1. This run's leg succeeded with its own fold commit present, and a
   sibling run's commit under the same id is also present → silent
   (healthy).
2. This run's leg was cancelled with no commit of its own, and a sibling
   run's commit under the same id is present → "not folded."
3. This run's leg succeeded with no commit of its own (sibling or not) →
   "partly folded."
4. A fold commit with no `Wing-Commander-Run-Id:` trailer at all → not
   this run's evidence, regardless of leg id match.
5. This run folded nothing of its own while a sibling run's fold commit
   sits in this run's range → `dispatch-once` dispatches nothing and posts
   the declined-dispatch notice (data-model.md §6).
6. The single-run baseline (no sibling commits at all) → byte-identical
   outcome to spec 042's existing scenario 1 (FR-012).

**New mutation** (`MUTATIONS`, alongside the four existing ones): replace
the `wing-commander-fold-evidence` call with the pre-fix inline
`git log --grep '^fold(' "$BASE_SHA..$TIP_SHA"` (no run-id filtering).
Scenario 2 above must then misreport the sibling's commit as this run's
own (FR-011) — the mutation must be caught, or the gate fails to build.

A sixth check (Gate 34 itself still present and wired, per its own
existing reflexive assertion) needs no new code — it already covers this
extension, since it asserts the gate step exists and is wired, not any
fixed scenario count.
