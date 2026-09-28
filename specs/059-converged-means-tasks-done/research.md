# Phase 0 Research: Converged Means No Task Is Left

Spec.md carries no `[NEEDS CLARIFICATION]` markers — the owner already
resolved every open trade-off on issue #450 and recorded the resolutions
inline (FR-009, FR-010, FR-011). This research phase instead resolves the
*design* unknowns needed to turn those requirements into a concrete plan,
by reading the current shipped implementation (`implement.yml`, `docs/
architecture.md`, `.github/scripts/verify-truncated-cycle-carry-forward.py`,
`.github/actions/wing-commander-spec-meta/`) and choosing among the options
each one leaves open.

## D1: Reuse the existing Arm-A checked-count delta as the FR-010a progress test

**Decision**: FR-010a's progress test — "a cycle whose checked-task count did
not rise against its own base" — is computed with the identical comparison
`implement.yml`'s truncated-cycle classification already performs today
(lines 1238-1243, the `before_count`/`after_count` grep against
`^\s*- \[[xX]\]` at `$BASE_SHA` and at the pushed tip), just run
unconditionally for every healthy cycle rather than only inside the
`VERDICT == "exhausted"` branch.

**Rationale**: The truncated-classification Arm A already answers exactly
the FR-010a question ("did the checked-task count rise between base and
tip") for a different purpose (exhausted-vs-failed). Spec 040's own carry-
forward logic already trusts this comparison as evidence of real progress.
Reusing it rather than inventing a second progress metric means one
definition of "progress" exists in the stage, not two that could disagree
on the same commit range — the same reasoning FR-007 applies to the
convergence signal itself.

**Alternatives considered**:
- A separate task-identity diff (which specific `T0NN` items flipped)
  — rejected: the spec's own edge case ("the cycle ticks a box and unticks
  another... a cycle whose checked count did not rise counts as no progress
  even though a box moved") explicitly wants the aggregate count, not
  per-task tracking, and per-task tracking would need task IDs to be stable
  and unique, which `tasks.md` does not guarantee.
- Reading `git diff --stat` on `tasks.md` between base and tip — rejected:
  a cycle can rewrite `tasks.md` formatting (re-numbering, re-wording)
  without changing checkbox state, which would falsely register as "progress"
  under a raw diff; this is the same ambiguity `docs/architecture.md:488-490`
  already named as the reason the original design avoided a raw working-tree
  diff.

## D2: One shared script + composite action for checkbox counting, modeled on `wing-commander-spec-meta`

**Decision**: Extract the checkbox read into `.github/actions/_shared/
count-tasks-checkboxes.sh` (the one home) plus a published front-door
composite `.github/actions/wing-commander-tasks-checkbox-count/action.yml`
that stage workflows call via `uses:`. `implement.yml`'s two arms each call
it twice — once at their own base ref, once at the pushed tip — mirroring
how `read-spec-meta.sh` / `wing-commander-spec-meta` is already the sole
reader of `spec-meta.json` for (among other callers) these same two arms.

**Rationale**: `wing-commander-spec-meta` is prior art for exactly this
problem inside this same workflow: a value multiple steps across two arms
need, previously duplicated, now read once. Its own header comment states
the rule this repository already follows — "stage workflows reach it only
through the \[front-door\] composite... `_shared/` is not part of the
adopter-pinned surface" (Constitution VII) — and that Gate 61
(`verify-spec-meta-single-home.py`) fails any other direct read. The new
checkbox count should get the identical shape: a `_shared/` script nothing
outside a composite front door calls directly, and a gate (this feature's
own, see D5) that fails if a third copy of the grep/awk idiom appears
anywhere in `implement.yml`.

**Deviation from the sibling pattern, stated explicitly**: `read-spec-meta.sh`
"never exits non-zero" because a missing `spec-meta.json` is a valid state
(a stage reads "no record" and decides for itself what that means). The new
`count-tasks-checkboxes.sh` does not carry that property: FR-006 requires
that an unreadable `tasks.md` fail the step loudly rather than resolve the
signal in either direction (Principle VIII — a scan that cannot reach its
subject must not report a pass it did not earn). So the new script/composite
exits non-zero (failing the calling step, and therefore the job) when the
ref:path it is given cannot be read as `tasks.md`, rather than returning a
`found=false` output for the caller to interpret.

**Alternatives considered**:
- Inline the counting `awk` directly in each of the four call sites (cycle
  base, cycle tip, retry base, retry tip) — rejected outright by FR-007 and
  CLAUDE.md's "Shared logic has exactly one home": this is the exact shape
  of duplication `read-spec-meta.sh`'s own header comment cites as the
  problem it fixed ("pasted into implement.yml (both read-back steps),
  plan.yml, tasks.yml... a fix... had to land in five places").
- A single composite call per arm that takes both a base ref and a tip ref
  and returns both counts plus a precomputed `progressed` boolean —
  considered and rejected as a simplification that would hide FR-010a's
  "same checkbox forms as FR-004" requirement inside a composite whose
  contract then has to also define "progressed," conflating a read (what
  the file says) with a decision (whether that counts as progress); keeping
  the composite a pure read (counts + unchecked item text, at one ref) keeps
  the progress *decision* in the read-back step next to the rest of FR-002's
  decision table, where FR-003 already requires it to live.

## D3: Fenced-code-block-aware counting via `awk`, not `grep`

**Decision**: The shared script counts `^\s*- \[[ xX]\]` lines with `awk`,
toggling an in-fence flag on lines that start with ``` ``` `` or `~~~`
(after stripping leading whitespace), and only counting checkbox lines seen
while that flag is false. It emits three things per ref: `checked-count`,
`unchecked-count`, and the literal text of every counted unchecked line (for
the issue-comment remaining-work text, D6).

**Rationale**: FR-004 requires recognizing `- [x]`/`- [X]` and leading
whitespace (already handled by the existing regex shape) and *additionally*
requires excluding a `- [ ]` that appears inside a fenced code block or
quoted example (the spec's own edge case: "a naive line match would count
prose as an outstanding task and hold a finished spec in the loop forever").
A single-line regex cannot track fence parity across lines; `awk`'s
line-at-a-time state is the natural fit and is already a tool this
repository's shell steps use elsewhere. `grep -c` (the tool the existing
Arm-A count already uses) has no cross-line state to exclude a fence.

**Alternatives considered**:
- A Python one-liner run inline via `python3 -c` — rejected: every other
  deterministic per-step read in this workflow is bash/awk/grep/jq: adding
  a Python dependency to a hot per-cycle step for one script is an
  inconsistency the gate script (which *is* Python, per this repo's
  existing gate-script convention) does not need to force onto the shipped
  step itself.
- Stripping fenced blocks with `sed`/a preprocessing pass before the `grep
  -c` — rejected as strictly more code than one `awk` pass doing both in a
  single scan, and two tools invite the two counts (checked, unchecked)
  drifting on which strip rule each applies.

## D4: The FR-010 hand-off reuses the existing cap-reached dispatch branch

**Decision**: "Read back cycle outcome" (and its retry twin) gains a new
output, `progressed` (`true`/`false`, from D1), alongside the existing
`ok`/`truncated`/`converged`. "Consolidate final outcome" carries it through
unchanged (same `RETRY_RAN` selection it already applies to the other
outputs). "Dispatch next step" computes the hand-off condition inline —
`ok=true`, `truncated=false`, `converged=false`, `progressed=false`, and no
`converge:` commit landed — and, when it holds, takes the *same* branch it
already takes when the iteration cap is reached with `converged=false`:
post the remaining work, dispatch `NEXT_WORKFLOW` (finalize) with
`converged=false`. No new dispatch branch, no new `workflow_dispatch`
payload field.

**Rationale**: FR-010 says exactly this — "reusing the stage's existing
cap-reached terminal path... with no new dispatch mechanism." The cap-reached
branch already does precisely what the hand-off needs (report remaining
work, hand to finalize, `converged=false`); the only new logic is the
*condition* under which that branch is taken before the cap. This keeps
FR-017's "no `workflow_call` output added or renamed" and "published surface
does not widen" satisfied — `progressed` is a step-local output inside the
job, never a stage `workflow_call` output.

**Alternatives considered**:
- A `**BLOCKED**` marker written into `tasks.md` for human-only leftovers —
  explicitly rejected by the spec itself (FR-010's resolution note: "The
  `**BLOCKED**`-marker design floated with the maintainer before intake is
  explicitly not carried forward").
- Forcing `MAX_ITERATIONS` down to the current iteration when a hand-off is
  detected (so the existing `ITERATION < MAX` check naturally falls into the
  cap branch without a new condition) — rejected: this would mutate a
  `workflow_call` input's effective value from inside the job, which is
  harder to audit from the run's own inputs than an explicit condition, and
  FR-009 states `max-iterations` and its default are untouched by this
  feature.

## D5: A new gate script, sharing `wc_shell_harness.py` with Gate 30 rather than extending it

**Decision**: Ship `.github/scripts/verify-tasks-checkbox-convergence-signal.py`
as a new gate (next sequential number after 80, assigned at
`/speckit-tasks` time) rather than adding scenarios to
`verify-truncated-cycle-carry-forward.py` (Gate 30). Both scripts import the
same `wc_shell_harness.py` (step extraction by name, synthetic bare-repo +
clone workspace, real-bash `run_step` execution, `$GITHUB_OUTPUT` parsing)
and the same `find_step`-by-name approach against the *same* four step
names in `implement.yml` (`Read back cycle outcome`, `Read back retry
outcome`, `Consolidate final outcome`, `Dispatch next step`) that Gate 30
already extracts.

**Rationale**: FR-018 says the gate must drive "the shipped `run:` blocks of
the read-back and dispatch steps... following
`verify-truncated-cycle-carry-forward.py`'s established pattern" — it does
not say *extend* that script. Gate 30's own subject is spec 040's truncated-
cycle classification (its docstring and step name both name that spec); this
feature's subject is a distinct rule (the checkbox-driven convergence
signal, spec 059) that happens to touch two of the same step bodies. Keeping
them as sibling gates, each testing its own contract against its own
fixture table, matches how this repository already handles multiple gates
sharing one subject file (e.g., several `verify-gate-*.py` scripts each
narrowly scoped) — the *shared mechanics* (extraction, synthetic repo,
real-bash execution) already have one home in `wc_shell_harness.py`, so
reusing it from a second script is exactly the pattern CLAUDE.md asks for,
not a violation of it: the harness is the "one home," not any single gate
script built on top of it.

**Alternatives considered**:
- Extending Gate 30 in place — rejected: Gate 30's `CYCLE_SCENARIOS` table
  and its own mutation battery are already large (12 scenarios plus
  retry-isolation and consecutive-truncation checks); folding in a second,
  unrelated rule's fixtures would make one gate responsible for two specs'
  worth of regressions, harder to attribute a red run to the right spec
  when it fails, and risks exactly the "shared job, one failure suppresses
  an unrelated check" shape Principle VIII already forbids ("a gate MUST
  NOT be suppressible by the failure of an unrelated gate that merely
  shares its job" — the inverse failure mode of one gate covering two
  unrelated subjects makes attribution just as hard).

## D6: The remaining-work text is the tip's outstanding-task list, not a converge-commit diff

**Decision**: `remaining` (the text posted to the lifecycle issue) is built
from the literal unchecked task-list lines the checkbox-count script already
emits for the pushed tip's `tasks.md` (D3), not from `git show
$converge_sha -- tasks.md`. The reason narrative (FR-013 — "converge
appended new work," "the cycle ended with tasks outstanding," or both, or
the FR-010 hand-off phrasing) is assembled separately, from the same
booleans the decision table already computes (`converge_sha` present,
`progressed`, `handoff`), and prefixes the task list.

**Rationale**: Scanning the tip's current unchecked items, rather than a
diff, automatically covers both non-convergence reasons without double
listing: a `converge:`-appended phase is, by construction, additional
unchecked lines already present in the tip's `tasks.md`, so listing "every
outstanding item at the tip" already includes them exactly once — there is
no separate "appended items" list to deduplicate against a "pre-existing
items" list. This directly satisfies FR-012 ("MUST NOT render an empty
block, which is what today's extraction... would produce on this path")
and FR-013's no-double-report clause without extra bookkeeping.

**Alternatives considered**:
- Keep the converge-commit diff extraction for the "converge appended"
  reason and add a second, separate tasks.md scan for the "outstanding with
  progress" reason, concatenating both — rejected: this is exactly the
  double-report FR-013 forbids ("must not report the same work twice when
  both fire" — the spec's own edge case, "converge appends a phase whose
  tasks are themselves unchecked. Both reasons fire at once... the comment
  must not report the same work twice").
