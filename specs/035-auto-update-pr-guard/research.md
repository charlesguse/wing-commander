# Phase 0 Research: Auto-Update Declines to Re-Propose a Candidate Whose PR Is Already Open

`spec.md` carries no literal `[NEEDS CLARIFICATION]` markers — its one
Clarifications session (2026-08-16) already resolved the three real
ambiguities (guard-only scope, narration cadence, queue-behind
behaviour). What follows are the implementation-shape decisions needed
to turn FR-001..FR-018 into something `tasks.md` can build against,
grounded in what `.github/workflows/auto-update-spec-kit.yml` (2770
lines, 10 jobs) and its executable test harness
(`.github/scripts/auto-update-spec-kit-tests/`) already do today. Each
decision states its rationale and rejected alternatives; decisions not
dictated by the spec text are marked "(made without clarification)" and
are repeated in the transmittal comment on issue #204, per this
pipeline's own convention (precedent: `specs/027-auto-update-spec-kit/research.md`).

## Decision: the guard is a new step inside `evaluate-path`, not a new job

**Decision**: Add a guard step to the existing `evaluate-path` job
(auto-update-spec-kit.yml:697-1083), placed immediately after its
"Resolve entry context" step (`id: entry`, line 781) and before "Fetch
candidate release notes" (`id: notes`, line 826) and "Decide upgrade
path" (`id: decide`, line 846, the first Claude-billed step).

**Rationale**:
- `entry` is the first point in the chain where both entry paths — a
  freshly settled candidate (`needs.settle.outputs.settled == 'true'`)
  and a resumed maintainer decision
  (`needs.comment-reply.outputs.resumed == 'true'`) — have already been
  unified into one `issue-number`/`candidate-version` pair
  (auto-update-spec-kit.yml:781-821). FR-012 requires the guard to cover
  both entry points; placing it here means one implementation satisfies
  FR-012 without re-deriving entry context in a new upstream job.
- `evaluate-path`'s job-level `if:` (line 699-702) is what both entry
  points already converge through to reach the first billed step. A
  guard job placed *before* `evaluate-path` would have to duplicate that
  same two-branch `if:` to run under identical conditions — this file's
  own convention is that later jobs re-derive from `needs.*.outputs.*`
  rather than dual-source a condition (`prepare`, `verify`, `act` all do
  this).
- `evaluate-path` already has a `decide-outcome` step (line 934) whose
  `outcome` output is the single switch every downstream job/step reads
  (`prepare`'s gate at 1099-1102: `needs.evaluate-path.outputs.outcome
  == 'clean-bump'`). Giving the guard's decision a new `outcome` value
  (`guard-skip`, see next decision) reuses that existing fan-out for
  free — no new `needs:` edges, no new job-level `if:` on `prepare`,
  `verify`, `e2e-stage`, or `act`.

**Alternative considered and rejected**: A dedicated `guard` job between
`settle`/`comment-reply` and `evaluate-path`. Rejected because it would
(a) duplicate `evaluate-path`'s entry-resolution `if:` and env-var
plumbing, (b) still need a *second* mechanism to suppress
`prepare`/`verify`/`act` (a new `needs.guard.outputs.*` check added to
each of their existing `if:` expressions, widening four job gates
instead of reusing the one `outcome` switch that already exists), and
(c) move the docs/adoption.md job-count table (which lists
`auto-update-spec-kit`'s 7 sequential jobs) for a purely internal
restructuring with no externally visible behaviour difference.

## Decision: a new `guard-skip` sentinel on the existing `outcome` output

**Decision**: `decide-outcome` (auto-update-spec-kit.yml:934-985) gains
a new possible value for `steps.decide-outcome.outputs.outcome`:
`guard-skip`, set whenever the guard step (previous decision) determines
the run should decline. `notes` and `decide` (the Claude-billed step)
both gain `&& steps.guard.outputs.skip != 'true'` on their existing `if:`
conditions, so neither runs when the guard fires — satisfying FR-004's
"skip the judgment ... step" directly, not just its *outcome*.

Because `prepare`'s gate already requires `outcome == 'clean-bump'`
(1099-1102), any other value — including the pre-existing
`needs-migration`/`ambiguous-options` and the new `guard-skip` — already
skips `prepare`, which transitively skips `e2e-stage` and `verify`
(both `needs: prepare`), and `act`'s own `if:` (2059-2064: `pinned-ok ==
'false' || prepare.result == 'failure' || verify.result == 'success' ||
verify.result == 'failure'`) evaluates false when `prepare` and `verify`
are both `skipped` (not `failure`) and health-check passed — so `act`
never runs either. **This is the existing "route to a human, don't
apply anything" machinery `needs-migration`/`ambiguous-options` already
proved out**; `guard-skip` is a third arm of the same switch, not a new
mechanism. `evaluate-path`'s own job therefore still concludes as a
plain success (FR-005) with no new job-level plumbing anywhere in the
chain.

**Alternative considered and rejected**: A separate boolean output
(`needs.evaluate-path.outputs.guard-skipped`) consumed by new clauses
added to `prepare`/`e2e-stage`/`verify`/`act`'s existing `if:`
expressions. Rejected: it widens four job gates instead of one step
gate, and duplicates exactly the suppression `outcome` already performs
— the risk `t7_gating.py`'s `step_scenario` docstring (line 88-93)
explicitly names ("widening the job gate ... admits it to every
pre-existing step too").

## Decision: recognition by marker, candidate-version extraction by branch name

**Decision (made without clarification)**: The guard recognises a
version-bump PR by the existing `<!-- wing-commander-auto-update-spec-kit:
version-bump -->` marker in its body (same string `act`'s "Open
version-bump PR" step already writes at line 2281, and the same
`grep -qF` idiom the `pr-merged` job already uses at lines 2429-2449 to
distinguish it from the revert marker `<!-- wing-commander-auto-update-spec-kit:
revert -->`, line 2192). Once a PR is recognised as ours by its marker,
the guard extracts **which candidate it proposes** from its head branch
name (`auto-update-spec-kit/v$CANDIDATE`, the deterministic naming
`prepare` already uses at line 1194 — this is `spec.md`'s own "Version-bump
branch" Key Entity), via `${headRefName#auto-update-spec-kit/v}`.

**Rationale**: FR-002 requires recognition — *is this PR ours* — to come
from the marker, "never by title or branch name alone," because a title
or branch name alone can't prove authorship (anyone could open a PR
titled or branched to look like one of ours). That constraint governs
recognition, not version extraction from a PR *already* proven to be
ours by its marker. The branch name is deterministic by construction
(one branch per candidate, spec's own Key Entities section), so parsing
it is exact; parsing the free-text sentence in the PR body ("Bumps this
repository's pinned Spec Kit version to v$CANDIDATE", line 2271) would
work today but is one wording change away from silently breaking, with
no test to catch it since nothing else in the file parses that
sentence.

**Flagged for the human** (see issue comment): this specific
extraction source (branch name vs. body text vs. PR title) is not
dictated by spec.md's text and is the one implementation-shape call
this plan makes without clarification — worth a maintainer's explicit
sign-off before `tasks.md` locks it in, since it is easy to change later
(both sources are already present on every PR this feature opens) but
harder to change once tests are written against one of them.

## Decision: at most one match proceeds; more than one is a data-integrity decline

**Decision**: The guard lists every open PR
(`gh pr list --state open --json number,body,headRefName`), filters to
those whose body carries the version-bump marker (excluding revert-marked
PRs per FR-013), and parses each match's candidate version from its
head branch. Then:
- **Zero matches** → guard does not fire; the run proceeds through the
  full chain exactly as today (US1 Acceptance #4).
- **Exactly one match** → skip. If its candidate equals the
  just-settled candidate, narrate as "already proposed" (US1); if it
  proposes a different (necessarily older, since `settle` only reaches
  `evaluate-path` with the *current* latest-observed candidate) version,
  narrate as "queued behind" (FR-011). Both are the same code path with
  a different narration string — FR-003 requires them to be
  *distinguishable in narration*, not handled by different logic.
- **More than one match** → decline and name every matching PR number,
  never choosing one (FR-014). This also covers the case SC-008 treats
  as an invariant ("no point does more than one version-bump PR from
  this feature stand open") failing to hold — a defensive branch for a
  state the guard itself prevents FR-011 from *creating*, but that could
  still arise from a manual `gh pr create` or a race between two
  workflow_dispatch runs.

**Rationale**: This reuses `settle`'s own existing
"count > 1 → decline, name all, never auto-resolve" precedent verbatim
(auto-update-spec-kit.yml:641-644: `nums="$(... | jq -r '[.[].number] |
join(", ")')"`), which is already the file's established idiom for
"more than one candidate for a singleton role is a human problem, not a
branch to pick automatically."

## Decision: `gh pr list` failure is "don't know, don't act" — never `|| echo '[]'`

**Decision**: The guard's `gh pr list` call captures failure explicitly
(`if ! json="$(gh pr list ... 2>err)"; then ...`) and, on failure, sets
`outcome=guard-skip` with a "lookup failed, declining this cycle"
narration and `exit 0` — never proceeding into `notes`/`decide` on an
unknown result, and never treating "the call failed" the same as "zero
matches found."

**Rationale**: This is `settle`'s own explicitly-documented lesson,
copied directly (auto-update-spec-kit.yml:545-571, especially the
comment naming the exact incident: "`2>/dev/null || echo '[]']` ...
makes 'the search broke' and 'no issue exists' the SAME VALUE ... On
2026-08-03 that opened #167, an exact duplicate of #162"). FR-010
states the identical requirement for this feature's own lookup. Because
`evaluate-path` runs under `set -euo pipefail` is not global (individual
steps set their own `set` flags; `decide-outcome` already uses `set
-uo pipefail`, not `-e`, for exactly this reason — line 940), the guard
step follows the same `set -uo pipefail` convention so a failed `gh`
call degrades to a handled branch rather than aborting the step
mid-script.

## Decision: the guard-tracking state extends the existing settle marker, not a new one

**Decision**: FR-007's "last-checked marker" and "one-time narration"
state live as two new sub-fields appended to the *same* settle-tracking
marker `settle` already writes/reads on the tracking issue
(`<!-- wing-commander-auto-update-spec-kit: candidate=X.Y.Z observed=N
[awaiting-decision=true] -->`, data-model.md): `guard-pr=<number>` (the
PR number narrated last, written once when a *new* blocking PR is first
observed) and `guard-checked=<UTC timestamp, date -u
+%Y-%m-%dT%H:%MZ>` (overwritten on every guarded run). The one-time
comment fires only when the current blocking PR's number differs from
the marker's existing `guard-pr` value (a fresh PR, or the first guarded
run ever); the timestamp field is rewritten unconditionally on every
guarded run, using the same `marker_line`/`new_marker`/`sed
"s|$marker_line|$new_marker|"` idiom every other marker write in this
file already uses (lines 677-679, 1069-1073).

**Rationale**: `spec.md`'s Assumptions state "the tracking issue's body
is already edited by the settle step each run, so a per-run last-checked
marker adds no new class of write" — this plan honours that directly by
extending the one marker `settle`'s own data-integrity check already
treats as a singleton (its `count > 1` branch, previous decision),
rather than introducing a second marker namespace that same check would
need to learn about. No genuinely new mechanism exists to model this on
structurally (research confirmed no other stage refreshes a field on
every run regardless of state change — `settle`'s `observed=N` only
increments when the candidate is unchanged, and `awaiting-decision=true`
is set/cleared once each) — the *mechanics* are reused, the *shape*
(a field refreshed every guarded run) is new.

**Alternative considered and rejected**: A separate `WING_COMMANDER_*`
label (e.g. `auto-update:guard-skipped`) as the one-time-narration
dedup signal. Rejected per Out of Scope ("Any new state store, label, or
event subscription") — the PR's own open/closed state and the existing
marker are the only latches this feature is permitted to add.

## Decision: `act`'s own branch/PR guard is independent of `evaluate-path`'s

**Decision**: `act`'s "Open version-bump PR" step (line 2237) gains a
check, before its `git push`, for whether the target branch
(`auto-update-spec-kit/v$CANDIDATE`) already exists on the remote
(`git ls-remote --exit-code origin "refs/heads/$BRANCH"`, the exact
idiom `plan.yml`/`tasks.yml`/`intake.yml`/`cleanup.yml`/`rebase.yml`
already use) and, if it does, whether an open PR already references it
(`gh pr list --head "$BRANCH" --state open --json number`). If either is
true, the step declines: no push, no `gh pr create`, a step-summary line
and an issue callout naming the blocking branch or PR number and the
remedy ("delete branch `$BRANCH` and re-dispatch"), and the step itself
exits 0 (a decline, not a failure — the job still concludes green).

**Rationale**: This is deliberately a *second*, independent check from
`evaluate-path`'s guard, not a reuse of its result. `evaluate-path`'s
guard only ever sees an **open** PR; `act`'s own guard exists for the
residual case US4/edge-cases describes explicitly — a branch left behind
by a *previous* run that failed after pushing, or by a PR that was
*closed* unmerged without its branch being deleted. In that scenario
`evaluate-path`'s guard correctly finds *no* open PR (so the run
proceeds through the full chain, per US3 Acceptance #2) and only `act`
discovers the collision, at the one point in the chain that actually
attempts to write to the shared branch namespace. This is exactly the
spec's Out-of-Scope framing: "a leftover branch remains a hard stop that
a maintainer clears by deleting the branch."

**Alternative considered and rejected**: Force-pushing over the leftover
branch when no PR is open. Explicitly Out of Scope (spec.md) — filed as
a follow-up issue against this spec, not built here (FR-018).

## Decision: draft PRs and revert PRs need no special-case code

**Decision**: No filtering by `isDraft`/draft state. `gh pr list --state
open` already includes draft PRs by default (GitHub's `open` state
covers drafts), so US1's "the open PR is a draft: still open, still
awaiting a human, so it still guards" edge case holds with zero
additional code — worth stating explicitly so a later reader does not
add unneeded `--draft`-aware filtering. Revert-marked PRs are excluded
simply because the guard's marker filter matches the version-bump marker
string specifically, never the revert marker string (FR-013) — the two
markers are already distinct literal strings the file writes at two
different call sites (lines 2192, 2281), so no revert PR is ever a
false positive.

## Decision: test-harness additions land in `t7_gating.py` and `t5_act.sh`; `gh_stub.py` gains `pr list`

**Decision**: FR-016/US5's coverage lands as:
1. **`t7_gating.py`** — new scenarios asserting `evaluate-path`'s guard
   step suppresses `notes`/`decide` (a `step_scenario`, following the
   file's existing `act_steps` pattern at lines 121-141, applied to
   `evaluate-path`'s own steps for the first time — today only `act`
   gets step-level assertions) and that a `guard-skip` outcome yields
   the same downstream `{"prepare": False, "verify": False, "act":
   False}` job-level matrix the pre-existing `ambiguous-options`
   scenario already asserts (lines 209-218), plus the ordinary "no
   matching PR: proceeds" scenario.
2. **`t5_act.sh`** — two new scenarios: "Open version-bump PR" meeting a
   pre-existing remote branch with no open PR (asserts: no push
   happened via `remote_refs()`, no PR created, step exits 0, the
   summary/log names the branch and the remedy), and meeting a
   pre-existing open PR for that branch (same assertions, message names
   the PR instead).
3. **`gh_stub.py`** — a `gh pr list` handler must be added first (a
   concrete, confirmed gap: `cmd == "pr"` at line 256 only implements
   `create`/`view` today; `pr list` falls through to "gh stub: unhandled
   command"). Its shape mirrors `issue list`'s existing filtering
   (`--state`, `--head`, `--json`) against the stub's existing `s["prs"]`
   map, which needs a `state`/`headRefName` field added to the PR record
   `pr create` writes (currently `number/title/body/url/base/head/mergedAt`
   — `head` already exists and doubles as `headRefName`; `state` does
   not exist today and PRs are implicitly always "open" in the stub,
   which is sufficient for every scenario above and requires no closed-PR
   modelling).

**`t9_prepare.sh` is unaffected.** It covers `prepare`'s commit-writing
step, and `prepare` never runs on a guarded cycle (previous decisions) —
confirmed against the file's actual scope (lines 8-227), no new scenario
is needed there for this feature.

## Docs impact (tasks-phase concern, noted here so it is not lost)

- `docs/architecture.md:808-911`'s "Auto-Update Spec Kit" section
  documents the job list and self-recognition markers; it needs a
  bullet on the new guard step and a note in its "Self-recognition"
  paragraph that the guard reads *other* PRs' markers, not just its own.
- `docs/adoption.md:727`'s per-stage job-count table is **unaffected** —
  the guard is a step, not a job, so `auto-update-spec-kit`'s listed job
  sequence and count (7) do not change. This is a direct consequence of
  the "step, not job" decision above, not an oversight.

## Constitution VII compliance check

`auto-update-spec-kit.yml` is confirmed (grep, whole file) to read no
`github.event.*` and no `vars.*` anywhere — it is a `workflow_call`-only
published stage. Every value the guard needs (issue number, candidate
version, the App-installation token) is already available via
`steps.entry.outputs.*` / `steps.ctx.outputs.*` inside the same job, so
the guard introduces no new `github.event.*`/`vars.*` read and stays
fully inside the published-stage contract. `act`'s own branch/PR check
is likewise pure `git`/`gh` reads against already-resolved values
(`needs.prepare.outputs.branch`, `steps.ctx.outputs.token`) — no new
input is added to either workflow's `on: workflow_call` interface.
