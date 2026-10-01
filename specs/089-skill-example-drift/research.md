# Research: The Worked Example Outlives Its Code

Phase 0 output. The spec's own three clarification questions already fixed
the remedy *shape* (a blocking gate over the concrete quote, a waiver file
on the `*-waivers.json` precedent, scoped to the one existing claim). What
is left for this phase is *how* — script name, gate number, extraction
technique, and how the waiver's stale-check works. None of these are
[NEEDS CLARIFICATION] markers in spec.md; the checklist notes say so
explicitly ("no script name, gate number, or comparison technique — those
remain plan's to choose").

## D1: Gate identity — script name and number

**Decision**: `.github/scripts/verify-skill-board-loop-concurrency-claim.py`,
registered as **Gate 125** (the next free number; none of 1-124 is unused —
confirmed by scanning every `Gate \d+` occurrence under `.github/scripts`
and `.github/workflows/lint-workflows.yml`).

**Rationale**: Follows the existing one-script-per-gate convention
(`wc_gate_registry.py`'s `verify-*.py` rule) rather than folding into Gate
101 (`verify-concurrency-guarantee-statement.py`), which checks a
*different* pairing — the FR-016 guarantee sentence's textual identity
across `board-loop.yml`'s comments, `board-loop-workflow.md`, and
`concurrency-groups.md`. This feature's subject is a *different* pair
(`spec-cross-reference/SKILL.md`'s Over-rated example vs. `board-loop.yml`'s
actual per-job `concurrency:` values) and a *different* property (not
prose-identity of a sentence, but the structural facts FR-012 lists: group
membership, `cancel-in-progress`, and non-membership of every other group).
Reusing Gate 101 would conflate two independently-driftable pairings behind
one pass/fail line, which is exactly the kind of unreachable-subject risk
Principle VIII calls out.

**Alternatives considered**: Extending Gate 101 to also read the skill —
rejected because Gate 101's own docstring frames it as a pure textual
restatement check (`_normalize` strips backticks and collapses whitespace;
it never inspects an actual `cancel-in-progress:` value), and FR-012 needs
real structural comparison, not prose matching. A generic
"skill-vs-workflow claim" registry covering every skill — rejected per
FR-011 and the spec's own Scope section: build the one gate the one claim
needs, extend later if a second claim appears.

**Provisional numbering note**: Per `verify-single-home-idioms.py`'s own
precedent (its docstring records being renumbered 53→60 across concurrent
spec branches), 125 is what is free *today*; if another spec's PR claims it
first, this feature's implement stage takes the next free number at that
time and updates this note's cross-references accordingly — not a design
change, a rebase mechanic.

## D2: Waiver file

**Decision**: `.github/scripts/skill-example-drift-waivers.json`, shaped
exactly like `single-home-waivers.json`/`stage-invariant-waivers.json`
(`$comment` header explaining the check and the stale-check property, a
`waivers` array of `{file, check, ..., issue|permanent, reason}` objects).
Ships with an **empty `waivers` array** — `board-loop.yml` on `main` matches
the skill's Over-rated example today (the spec's own Assumptions section),
so no divergence exists at merge time to waive.

**Rationale**: FR-013 names this precedent explicitly. Gate 124
(`verify-waiver-citations.py`) already discovers any `.github/scripts/*-waivers.json`
by glob — no registration step needed for the schema half. The *stale
in both directions* half (FR-014) is this feature's own gate's
responsibility, the same way `verify-single-home-idioms.py` and
`verify-stage-invariants.py` each re-check their own waiver entries against
live structural facts rather than delegating that to Gate 124 (which only
checks the citation schema and, in `--check-open` mode, that a cited issue
is open — it has no notion of what a "single-home" or "concurrency-claim"
entry's subject even is).

**Waiver identity shape**: one entry per divergent *property* (job×group
membership, a specific job's `cancel-in-progress`, or an unexpected job in
the directed-proof group) rather than one entry per PR, so Gate 125 can
mechanically re-derive "does this entry's named divergence still exist?"
without parsing free-text `reason` prose. See contracts/skill-drift-gate.md
for the exact field shape.

## D3: Extracting the skill's claim without over-fitting its wording

**Decision**: Gate 125 reads the Over-rated bullet's paragraph in
`spec-cross-reference/SKILL.md` (bounded the same way Gate 101 bounds a
blockquote: from a fixed anchor phrase to the next paragraph break) and
extracts only the backtick-quoted tokens inside it: the job-range pair
(`` `select` ``...`` `readiness` ``), the ordinary group name
(`` `wing-commander-board-loop` ``), and the directed group name
(`` `wing-commander-board-loop-directed-proof` ``). Everything between and
around those tokens is prose the gate does not parse.

**Rationale**: FR-009 forbids firing on a reflow or typo fix. Backtick-quoted
identifiers are already this repository's convention for "this token is a
literal that must resolve" (Gate 47 does the same move for filenames). A
prose-similarity or full-sentence diff (Gate 101's approach) would be
*more* sensitive to wording than FR-009 allows, since Gate 101's subject is
a sentence meant to be verbatim-identical across three sites — this
feature's subject is a worked example that is free to be reworded so long
as the concrete tokens still name true facts.

**Alternatives considered**: Verbatim sentence match against a canonical
string (Gate 101's technique) — rejected, over-constrains prose FR-005
wants to stay a natural worked example, not a copy of a contract's
boilerplate. A full NLP/semantic diff — rejected as exactly the kind of
judgment Principle IX reserves for deterministic code, not a heuristic that
could silently misjudge "still true."

## D4: What "every job that can select an item or open a fix PR" means mechanically

**Decision**: Gate 125 treats
`specs/060-self-redrive-concurrency/contracts/concurrency-groups.md`'s
"Groups, per job" table as the authoritative list of which jobs are
select-capable / fix-PR-capable and what group each expects — it does not
hand-maintain a second copy of that classification. Concretely: the six
jobs the table lists as unconditionally `wing-commander-board-loop` with
`cancel-in-progress: false` (`select`, `triage`, `route`, `fix`, `review`,
`readiness`) are the "select-through-readiness" set the skill's job-range
token must span; `prove-gate`/`prove` are the two jobs the table splits
between the ordinary and directed-proof groups; every other job name
`board-loop.yml` declares (currently only `resolve-model`) MUST carry no
`concurrency:` block matching either group, or the gate fails loudly (a
selecting/fix-opening job placed outside the classification the contract
already governs would itself be a spec-060 contract violation, not merely
a skill-staleness one, and either way the reader should see it).

**Rationale**: Avoids a second hand-maintained job list drifting from
`concurrency-groups.md`'s own table the way the *skill* already drifted
from `board-loop.yml` — the defect this feature exists to stop, reproduced
one file over. `concurrency-groups.md` is already the canonical source
Gate 101 diffs `board-loop.yml`'s comments against; reading its table
(rather than re-deriving classification from board-loop.yml's job names by
guesswork) keeps the "single home" rule intact per CLAUDE.md.

**Alternatives considered**: Inferring the select/fix-PR-capable set purely
from `board-loop.yml`'s own structure (e.g., "every job with a `gh issue
comment`/`gh pr create` step") — rejected as exactly the kind of
heuristic-over-code-shape judgment the constitution's Principle IX and this
skill's own subject matter (over-rating a finding by code shape alone)
warn against beyond what a maintained, human-reviewed table already gives
for free.

## D5: Structural comparison against `board-loop.yml` itself

**Decision**: Gate 125 parses `board-loop.yml`'s real `concurrency:` blocks
(group expression + `cancel-in-progress` value), not merely their preceding
comments (which is all Gate 101 reads). For the six unconditional jobs it
requires literal `group: wing-commander-board-loop` and
`cancel-in-progress: false`. For `prove-gate`/`prove` it requires the
conditional expression to resolve to `wing-commander-board-loop-directed-proof`
exactly when `directed-stage` is set and to `wing-commander-board-loop`
otherwise (matched structurally against the known `${{ (... directed-stage
!= '') && 'wing-commander-board-loop-directed-proof' ||
'wing-commander-board-loop' }}` shape already in the file, not a generic
expression evaluator).

**Rationale**: FR-012 explicitly requires checking `cancel-in-progress`,
not merely group *names* — a name-only comparison is the edge case the
spec calls out by name ("The concurrency block keeps its group name but
flips `cancel-in-progress` to `true`"). Reading the actual `concurrency:`
mapping (via a small PyYAML-assisted or regex walk keyed to each job's own
block, mirroring `board_prove.py`'s existing job-block-scanning style)
rather than the comment text is what makes that edge case fail loudly
instead of passing on an unchanged comment above a changed value.

## D6: The skill's own prose needs one addition to be gate-checkable on `cancel-in-progress`

**Decision**: Record, for the implement stage, that the Over-rated
example's current wording ("every job that can select an item or open a
fix PR ... joins `wing-commander-board-loop`, and the only run allowed to
overlap them is a directed proof run in
`wing-commander-board-loop-directed-proof`...") states group membership but
never states the queuing/`cancel-in-progress` property FR-012 requires the
gate to check. FR-005 requires the skill to stay a concrete, checkable
illustration — a property the gate enforces but the prose never asserts
would be checked "behind the reader's back." Implement MUST add one clause
to the Over-rated paragraph naming the queuing property (e.g., "...and each
queues rather than races or cancels a same-group run") so the concrete
claim being gated is the concrete claim a reader actually reads. This is a
small wording addition, not a rewrite — FR-004 (follow the code, don't
anticipate it) and FR-005 (stay concrete) both still hold; this is the
minimum the two together require.

**Rationale**: Without this, Gate 125 would be checking a property the
skill's own text is silent on, which reintroduces exactly the "check that
proves something the reader can't see" shape Principle VIII warns against
at the reader-legibility level (distinct from the gate's own
mechanical-failure legibility, which FR-006 covers).

## D7: Waiver stale-check semantics

**Decision**: Gate 125 computes the *actual* divergence set on every run
(zero or more of: a specific job missing from the expected group, a
specific job's `cancel-in-progress` wrong, an unexpected job present in
either group, the skill's job-range token not spanning the expected set,
the skill missing the directed-group token, `board-loop.yml` or the
skill file missing entirely). For each waiver entry in
`skill-example-drift-waivers.json`, it checks that entry's declared
property is a member of the current divergence set:

- Present in both → waived; the run does not fail for that property, but
  still reports it as "waived: <property>, see #<issue>" so a human skim
  is not silent about degraded coverage (mirrors
  `verify-single-home-idioms.py`'s treatment of its own waivers).
- Declared but absent from the current divergence set (the skill was
  brought back into agreement, or `board-loop.yml` reverted) → the gate
  FAILS, naming the stale entry, per FR-014 and Acceptance Scenario 5.
- A divergence exists with no matching waiver entry → the gate FAILS,
  blocking, per FR-010.

**Rationale**: This is the same "stale in both directions" shape
`single-home-waivers.json`'s own header describes (a pattern matching
nothing fails; a count that drifted fails) applied to this feature's own
divergence vocabulary instead of a regex/count pair — FR-014's explicit
requirement, demonstrated per SC-007.

## D8: Triager legibility (FR-008, SC-004, User Story 3)

**Decision**: Two additions, both textual, both inside
`spec-cross-reference/SKILL.md`:

1. One sentence immediately after the Over-rated example's paragraph:
   "This claim is mechanically checked against `board-loop.yml` by Gate 125
   (`python3 .github/scripts/verify-skill-board-loop-concurrency-claim.py`);
   run it to settle whether this example is still current before trusting
   it to downgrade a finding." This is the one-command answer Story 3
   needs, and it does not depend on spec 060's history — the command
   either passes or names the mismatch.
2. Gate 125's own PASS output names which properties it checked and that
   they currently hold (mirroring Gate 101's `[ok] ...` lines), so running
   it is legible without reading the script's source.

**Rationale**: FR-008 requires this to work "with no history with spec
060." A reader who runs the named command gets a yes/no answer either way,
which is the exact one-command bar SC-004 sets. This does not violate Gate
47 (the "-- see" pointer convention) because Gate 47 only scans
`.github/workflows/*.yml` comments — a `.claude/skills/**.md` sentence
naming a script by its literal, resolvable path is checked for real by
Gate 125 failing loudly if the script ever moves (D1's provisional-numbering
note already anticipates a rename needing this sentence updated too).

## D9: Self-test fixtures (FR-007, SC-005)

**Decision**: Gate 125 ships a `--self-test` mode following the
`verify-*-selftest`-in-CI convention every other structural gate in this
suite uses (Gate 24, Gate 101's sibling gates, `verify-single-home-idioms.py
--self-test`). Fixtures are small synthetic SKILL.md-shaped and
board-loop.yml-shaped text fragments (not the real files, so the self-test
never depends on either file's current wording) covering, each in both a
passing and a failing direction:

- a job present in the expected group with `cancel-in-progress: false`
  (pass) vs. absent from it (fail, D5);
- `cancel-in-progress: false` (pass) vs. `true` (fail, the spec's own edge
  case);
- an unexpected job inside `wing-commander-board-loop` or the directed
  group (fail) vs. none (pass);
- the skill's job-range token spanning the expected set (pass) vs. a
  narrower or wider range (fail);
- `board-loop.yml` (or the skill file) missing entirely → fails loudly
  naming the missing subject, never a silent pass (the "renamed or split"
  edge case);
- a wording-only change to surrounding prose (reflow, typo) with every
  backtick token unchanged → still passes (FR-009);
- a waiver entry whose named divergence is present → passes (waived) vs.
  absent → fails (stale, D7/FR-014).

**Rationale**: SC-005 requires both the passing suite and a demonstrated
failing mutation for each of the subject files. Synthetic fragments (rather
than mutating a full copy of the real 4000+-line `board-loop.yml`) keep the
fixtures readable and independent of unrelated drift elsewhere in that
file, the same tradeoff `verify-board-prove.py`'s own fixture style already
makes for its non-real-tree assertions.
