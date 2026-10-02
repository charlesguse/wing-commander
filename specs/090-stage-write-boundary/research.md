# Phase 0 Research: The Implement Stage's Write Boundary

Spec.md's Clarifications section already resolved the three trade-offs the
route agent flagged (the `.claude/` policy itself, leaving `tasks.md`
untouched, and a general per-stage no-write set) on issue #675, and spec.md
carries no `[NEEDS CLARIFICATION]` marker. This phase resolves the *design*
unknowns FR-001 requires and the mechanism choices the spec's Assumptions
section explicitly leaves to the plan, by reading the current shipped
implementation (`implement.yml`, `wing-commander-tool-args`,
`wing-commander-tasks-checkbox-count`, `wing-commander-stage-findings`,
`finalize.yml`, `.claude/settings.json`, `.claude/hooks/
constitution-reminder.sh`) and choosing among the options each leaves open.

## D0: FR-001's observation — the refusal is not explained by this repository's own configuration

**Finding**: Inspecting `main` directly: `implement.yml`'s composed
`default-allowed-tools` for both the cycle arm (line 858) and the retry arm
(line 1566) grant bare `Write,Edit` with no path scoping syntax anywhere in
this repository's tool-grant vocabulary (no `Write(path)`/`Edit(path)`
grant exists anywhere else in this repository either). Neither arm's
`default-disallowed-tools` (line 859, 1567 — both exactly
`WebSearch,WebFetch,ScheduleWakeup,Monitor,SendMessage`) names `.claude/` or
any path. `.claude/settings.json` carries no `permissions.deny` list at all
(only a narrow `permissions.allow` for `gh workflow`/`gh run` read
commands) and its one `PreToolUse` hook, `constitution-reminder.sh`, is
documented in its own header as "Deliberately advisory... it never denies
the tool call," and its `case` statement only ever fires on
`.specify/memory/constitution.md`, never on any other `.claude/` path — it
could not have produced the `T055`/`T053` refusal even if it were not
advisory.

**Decision**: Record the refusal as real and reproducible (spec.md's own
Assumption) but attributable to something outside every artifact this
repository controls — most likely the hosting agent harness's own
protection of the project's control-surface directory, a mechanism this
repository cannot inspect or configure from inside the checkout. FR-002's
policy is adopted as a decision regardless of that mechanism, per spec.md's
Assumptions: "the repository now routes such work by choice rather than
merely by inability, and only that survives a change in the harness."

**Rationale**: FR-001 requires the observation be *made*, not that a
positive in-repo cause be *found* — and it explicitly says "no requirement
below may assume it is" explained by this repository's configuration. The
negative result above (nothing in `implement.yml`'s tool lists, nothing in
`.claude/settings.json`, nothing in the one hook) is the observation.

**Alternatives considered**: Treating the unexplained cause as a blocker
requiring a live probe (dispatching a real cycle against a `.claude/` task
and reading the actual tool-call denial event) before design can proceed —
rejected: spec.md's Assumptions section already accepts the refusal as
given ("The observation is trusted; its *cause* is not assumed... FR-001's
observation therefore still has to be done, but its outcome cannot reopen
FR-002"), so a probe would spend a cycle re-confirming a fact the spec
already treats as settled without changing any downstream decision.

## D1: One `no-write-paths` input, defaulted to `.claude/`, as the single declared definition

**Decision**: Add exactly one new optional `workflow_call` input to
`implement.yml`, `no-write-paths` (string, comma-separated path prefixes,
default `.claude/`). Every site that needs to know the boundary —
`wing-commander-tool-args`'s new statement (D2), the new
`wing-commander-write-boundary` composite's classification (D3), and the
routing label (D4) — receives this same value by parameter, never a second
literal.

**Rationale**: FR-003 requires exactly one definition; FR-019 requires it be
a general declared set, not a `.claude/`-special-case, exposed as a new
optional stage input defaulting to today's sole entry. A single string
input, split on commas at each consuming site the same way
`extra-allowed-tools`/`extra-disallowed-tools` are already split and deduped
by `wing-commander-tool-args`, needs no new input *type* this repository's
composite-action/`workflow_call` surface doesn't already use elsewhere.

**Alternatives considered**:
- A YAML/JSON list input — rejected: every existing tool-list input on this
  contract (`extra-allowed-tools`, `disallowed-tools-override`, etc.) is a
  comma-separated string; a list-shaped input would be the only one of its
  kind on the surface, and `workflow_call` inputs are strings regardless, so
  it would still need string-splitting at the consumer, just with different
  punctuation.
- A repository variable read directly inside `implement.yml` rather than a
  `workflow_call` input — rejected outright by Principle VII: a stage
  workflow "reads no ambient repository state... every knob arrives as a
  declared, typed input"; that is exactly the wrapper/stage split this
  repository already enforces, and `wing-commander-5-implement.yml` is
  where the repo-variable read belongs (mirroring `findings-label-prefix`'s
  own wiring).

## D2: Extend `wing-commander-tool-args`, do not add a second prompt-composition site

**Decision**: Add `no-write-paths` as a new optional input to
`wing-commander-tool-args/action.yml` (default `""`) and one new output,
`write-paths-statement`, composed by the same composite step that already
builds `shell-commands`, using the identical four-shape rendering pattern:
empty → `"This run's agent may write any path in the checkout."`; non-empty
→ `"This run's agent may not write: <list>."`. `implement.yml`'s Tooling
paragraph (cycle: lines 975-990; retry: 1707-1722) gains one more rendered
sentence, `${{ steps.tool-args-cycle.outputs.write-paths-statement }}`,
immediately after the existing shell-commands sentence.

**Rationale**: FR-004 requires the statement be "derived from that run's own
configuration in the same way the Tooling paragraph's shell-command
sentence is derived" — the literal precedent named by the requirement.
`wing-commander-tool-args` is already the one composite that turns this
run's own configured grants into agent-facing prose; a second, parallel
rendering site (e.g. composed inline in `implement.yml`) would immediately
violate FR-003's "exactly one definition" the moment the input's default
changed and one site's copy of the four-shape template drifted from the
other's.

**Alternatives considered**:
- Rendering the statement in the same step that classifies tasks (D3) and
  passing the resulting string back up into the prompt — rejected: that
  composite runs once per read-back (after the agent's turn), not once per
  prompt-composition (before it); the statement has to exist before the
  agent's first tool call, at prompt-render time, which is
  `wing-commander-tool-args`'s existing call site, not the read-back's.
- Hand-writing the sentence as static prompt prose keyed off
  `${{ inputs.no-write-paths }}` directly in `implement.yml`, with no new
  composite output — rejected by FR-005/FR-019: a hand-written `${{ }}`
  interpolation with no shared rendering function is exactly the "hand-
  maintained literal that can drift" FR-004's own wording warns against,
  and it would need its own empty-case branch duplicated wherever it
  appears (twice, cycle and retry), the second-copy problem D1 already
  avoids for the input itself.

## D3: A new composite, `wing-commander-write-boundary`, consuming the existing `unchecked-items` text rather than re-reading `tasks.md`

**Decision**: Ship `.github/actions/_shared/classify-out-of-boundary-tasks.sh`
plus a front-door composite, `wing-commander-write-boundary`. Inputs:
`unchecked-items` (the exact multi-line text `wing-commander-tasks-checkbox-
count`'s own `unchecked-items` output already produces for the pushed tip),
`no-write-paths` (D1's value, unsplit), `tasks-path` (e.g.
`specs/090-.../tasks.md`, for the fingerprint basis). Outputs:
`findings-json` (a JSON array, one entry per out-of-boundary task, shaped to
`.github/schemas/stage-finding.schema.json`), `all-unchecked-out-of-
boundary` (`true`/`false`), `out-of-boundary-count` (digits).

Per-line classification: extract every backtick-quoted, slash-containing,
whitespace-free token from the line's text as a candidate path. A line with
zero candidate tokens, or at least one token that is *not* prefixed by any
entry in `no-write-paths`, falls through untouched (FR-015, and the "task
naming several paths, only one of which is out of reach" edge case — the
in-reach token means real work remains, so the whole task stays ordinary).
A line with one or more candidate tokens, all of them prefixed by an entry
in `no-write-paths`, is out-of-boundary and gets one `findings-json` entry.
`all-unchecked-out-of-boundary` is `true` only when `unchecked-count > 0`
and every unchecked line classified out-of-boundary.

**Rationale**: `wing-commander-tasks-checkbox-count` already reads
`tasks.md` at the tip once per arm and already emits the literal unchecked-
item text (its `unchecked-items` output, added by spec 059 for the
remaining-work report). Spec 090's own Dependencies section states that
composite is "the single home for reading `tasks.md` state... left
unchanged, since FR-010 adds no new `tasks.md` state" — a second `git show`
of the same ref:path from a new composite would be exactly the duplicate
read that note warns against, and folding classification logic into
`count-tasks-checkboxes.sh` would mix two distinct concerns (counting
checkbox state vs. path-matching task text) inside the one file that
script's own header comment already scopes narrowly ("this script is now
the one home both counts... come from" — a claim about checkbox counting
specifically).

**Alternatives considered**:
- Path-matching inside `Read back cycle outcome`'s own shell, inline,
  duplicated in the retry arm — rejected by FR-003/FR-006/CLAUDE.md's
  "Shared logic has exactly one home," the same reasoning D2 applies to the
  statement.
- Using `fnmatch`-style glob matching instead of a plain prefix test —
  rejected as needless generality: FR-019's "next unwritable path is a list
  entry" only requires prefix membership (`.claude/`, `.git/`, or a future
  entry are all directory prefixes), and a glob engine invites patterns
  (`**`, `?`) with no defined meaning for a hand-typed `no-write-paths`
  value and no test in this spec that needs one.
- Treating any line with *zero* candidate paths as out-of-boundary by
  default (a fail-closed reading) — rejected outright by FR-015 and its own
  edge case: "a path-based boundary cannot classify it, and guessing would
  route real work away... It must fall through."

## D4: Routing reuses `wing-commander-stage-findings`, under a second, non-authorizing label prefix and a new `finding-kind` wording input

**Decision**: `implement.yml` calls `wing-commander-stage-findings` a
second time per cycle (step "Route out-of-boundary tasks," beside the
existing "File findings from this run"), with `channel-mode:
structured-array`, `findings-json` set to the carried-through output of D3's
composite, and `label-prefix: ${{ inputs.write-boundary-label-prefix }}`
(new input, default `route-out-of-boundary`) — producing a label
`route-out-of-boundary:implement`, structurally identical to but
namespaced apart from `found-by:implement`. `wing-commander-stage-findings`
gains one new optional input, `finding-kind` (allowed `defect`|
`routed-task`, default `defect`), that swaps its hardcoded "a defect was
filed by the $STAGE stage" recap phrase and "met a defect outside its own
task" label description for routed-appropriate wording ("assigned work the
$STAGE stage could not complete under its write boundary was filed" / "is
outside the $STAGE stage's write boundary") when `routed-task`. Every other
input, output, and the `defect` default's rendered text are unchanged
byte-for-byte.

**Rationale**: `wing-commander-stage-findings` already owns fingerprinting
(FR-008's idempotency, for free), the cap, the dedup call to
`wing-commander-durable-failure-issue`, and — because it already accepts
`lifecycle-issue-number` — the exact per-cycle lifecycle-issue recap comment
FR-009 requires, with zero new comment-composition code. Rebuilding any of
that in a parallel mechanism is the duplication CLAUDE.md's "Shared logic
has exactly one home" section names by its own worked example (a formatter
pasted into every stage vs. living in one composite's output). The distinct
label prefix is the plan's answer to the Assumptions section's explicit
concern: "the routing label does not hand such an item to an agent fixer
that FR-002 forbids to write it" — `route-out-of-boundary:implement` is not
a maintainer-applied label, not `found-by:<stage>`, and not `spec-request`,
so Principle X's board loop may read and triage-propose on it but "never
push for" it (Principle X's own words for any issue outside its three
authorized-entry classes) until a human relabels it — making the routed
item's owner a human by construction, not by trusting the loop's own
shape-classification to notice a `.claude/` path.

**Alternatives considered**:
- Reusing `found-by:implement` verbatim (no new label prefix) — rejected:
  that is exactly the label the board loop already treats as pipeline-
  filed authorization to route into fix/review/merge, and a `.claude/` fix
  is bound by the very FR-002 policy this feature exists to enforce; an
  automated fixer would hit the identical, indistinguishable-from-inside
  refusal D0 observed, one layer later.
- A brand-new filing composite with its own fingerprinting — rejected by
  FR-008 and CLAUDE.md: this would be a second, divergence-prone
  implementation of exactly the anchor/fallback fingerprint rule
  `wing-commander-stage-findings` already has, tested, and caps at 3 slots.
- Leaving `wing-commander-stage-findings`'s wording as "a defect" for
  routed items too, accepting the mismatch — rejected: a maintainer reading
  the label description "met a defect outside its own task" for an item
  that is in fact *assigned work the stage could not perform* is misled
  about why the item exists, which is precisely the "orphan line of prose"
  failure mode User Story 2 exists to end, just relocated into a
  misleading label rather than eliminated.

## D5: Loop termination needs no new logic; only the `reason` narrative and the filing side effect are new

**Decision**: Spec 059's existing hand-off condition (`ok=true`,
`truncated=false`, `converged=false`, `progressed=false`, no `converge:`
commit) already fires the moment the only unchecked task cannot be
advanced — which is exactly the state `all-unchecked-out-of-boundary=true`
describes, since nothing else got ticked. This feature changes only the
`reason` text `Read back cycle outcome`/`Read back retry outcome` compute
for that branch: when `all-unchecked-out-of-boundary=true` at hand-off time,
`reason` names the routed task(s) by id/path instead of using the existing
generic hand-off narrative, and a new step-local boolean, `routed`, is
carried through "Consolidate final outcome" (alongside `progressed`/
`handoff`, the same way spec 059 carries those) so the later "Route
out-of-boundary tasks" step (D4) knows whether to run.

**Rationale**: FR-010's Acceptance Scenario 1 ("the loop does not dispatch a
further cycle for the sake of that task alone") is already true of the
*existing* hand-off the moment nothing else progresses in the same cycle —
re-deriving a parallel termination condition would risk the two disagreeing
on the same input, the exact duplication Out of Scope explicitly forbids
("Revisiting spec 059's convergence signal, progress test, iteration cap,
or early hand-off for the cases they already cover"). What spec 059's
hand-off does *not* do is say anything distinguishing "stuck" from
"routed," or file anything — that gap is FR-011 and FR-007, both satisfied
by additions alongside the existing decision, not changes to it.

**Alternatives considered**:
- A new `all-out-of-boundary` branch inserted *before* the existing
  hand-off check, short-circuiting it — rejected: this would create two
  paths to the same terminal behavior with two conditions to keep in sync,
  where one falling out of the other (as shown above) already keeps them
  in sync for free.
- Forcing an immediate hand-off on the very first cycle that meets an
  out-of-boundary task, even if that cycle also made other progress
  (`progressed=true`) — rejected by FR-012 ("real progress... MUST still be
  recognized as progress... MUST NOT suppress the existing... early
  hand-off for the cases those already cover") and User Story 3's Scenario
  3; a cycle that both advances other tasks and meets the out-of-boundary
  one should keep looping for the real work, exactly as today.

## D6: One shared fingerprint helper, used by both the findings composite and `finalize.yml`'s lookup

**Decision**: Extract the anchor/fallback fingerprint formula
`wing-commander-stage-findings` already computes inline
(`sha256("anchor|STAGE|norm_path|norm_gate")` /
`sha256("fallback|STAGE|norm_path")`) into
`.github/actions/_shared/compute-finding-fingerprint.sh`, called by that
composite instead of computing the hash inline, and by a new deterministic
step in `finalize.yml`, "Look up routed write-boundary items": for every
unchecked line at the tip, compute the fingerprint it *would* have gotten
from D4's routing call (`file_path` = the spec's own `tasks.md`,
`gate_or_artifact` = the line's literal text, `stage` = `implement`), then
`gh issue list --search '"<!-- wing-commander-finding: fingerprint=<fp>
-->"' --label '<write-boundary-label-prefix>:implement'` to find the
matching issue, if any. The existing remaining-manual-work prompt
(`finalize.yml:722-738`) is extended to render `<task text> — routed, see
<issue url>` for any line this lookup matched, leaving every other line's
handling exactly as today.

**Rationale**: FR-009 already reports the routed item at cycle time via
D4's reused recap comment; SC-005 is a *second*, independent requirement —
the final PR's own remaining-manual-work list must carry the pointer too,
and that list is composed by `finalize.yml`'s agent from `tasks.md` text
alone, with no visibility into what implement's cycles filed. Recomputing
the exact fingerprint deterministically (never trusting the agent to guess
which unchecked line "looks routed") is Principle IX's own rule applied to
this lookup; sharing the formula with `wing-commander-stage-findings` rather
than re-deriving it a second time is CLAUDE.md's "Shared logic has exactly
one home" applied to the one piece of logic this plan would otherwise
duplicate.

**Alternatives considered**:
- Passing the filed issue URLs forward through the `workflow_dispatch`
  payload from implement's job to finalize's — rejected: `finalize.yml`
  runs once at the end of the whole implement⟲converge loop, potentially
  many cycles after a given item was routed, and payload fields are not
  this repository's mechanism for carrying accumulating state across
  dispatches (each dispatch already only carries `converged`); a
  fingerprint-keyed lookup against GitHub Issues is the durable record,
  not a payload field.
- Matching by label alone (`gh issue list --label
  route-out-of-boundary:implement --search "<spec-dir>"`) without the exact
  fingerprint — rejected: a text search for a bare spec-dir string is a
  heuristic that could match an unrelated issue mentioning the same path in
  passing, where the fingerprint marker is an exact, already-tested anchor
  string with no such ambiguity.

## D7: Gate name and placement

**Decision**: Ship `.github/scripts/verify-write-boundary.py` (exact
sequential gate number assigned at `/speckit-tasks` time, per spec
078/059's own precedent for not pinning a number this early), registered in
`lint-workflows.yml` next to the other `verify-tasks-*`/`verify-stage-
findings-*` gates, sharing `wc_shell_harness.py`'s synthetic-repo/step-
extraction machinery the way `verify-tasks-checkbox-convergence-signal.py`
already does.

**Rationale**: FR-020 requires the gate be "reachable through the gate
registry" and "extend the nearest existing harness rather than adding a
parallel one" — `wc_shell_harness.py` is that harness, already proven on
the structurally closest subject (spec 059's read-back steps). A dedicated
script, rather than folding scenarios into `verify-tasks-checkbox-
convergence-signal.py`, keeps this feature's own fixture table and mutation
battery attributable to a run of its own name, matching spec 059's D5
reasoning for why it did not fold into Gate 30 either.

**Alternatives considered**: See spec 059 research.md D5 — the same
reasoning against folding two specs' regressions into one gate applies
here against folding into Gate 30 or into
`verify-stage-findings-wiring.py`, neither of whose subject is this spec's.
