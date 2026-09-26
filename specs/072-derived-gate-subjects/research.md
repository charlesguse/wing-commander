# Phase 0 Research: Gate 68 Derives Its Own Subjects

All three Clarifications in spec.md already settle the structural rule
(FR-002), the floor-comparison mechanism (FR-004), and the per-workflow
disposition rule (FR-014). What remains for this phase is grounding those
decisions against the actual shipped workflow files — which jobs the
derivation rule will surface, what each newly-surfaced job's disposition
concretely is, and how the gate's internal shape (`SUBJECTS`, the
self-test's `SUBJECT_MUTATIONS`, the three companion maps) changes to stop
being the thing that decays.

No `[NEEDS CLARIFICATION]` marker remains in spec.md; nothing here overrides
a clarification answer — each decision below elaborates one into an
implementable shape.

## D1 — Derivation walks every file under `.github/workflows/*.yml`, not a fixed list

**Decision**: `load_all()`'s `SUBJECTS`-keyed iteration is replaced by a glob
over `.github/workflows/*.yml` (34 files today — the 9 files `SUBJECTS`
already names plus `board-loop.yml`, `cleanup.yml`, `rebase.yml`,
`watchdog.yml`, and 21 more: `auto-release.yml`,
`auto-update-spec-kit-scratch-preflight.yml`, `metrics-persist.yml`,
`private-image-dogfood.yml`, `release.yml`, and the 13 `wing-commander-*.yml`
thin wrapper workflows). Each file is `yaml.safe_load`ed once; a file that
fails to parse or cannot be read fails the gate by name (FR-006), same
severity as today's "named file missing" branch, not a softer warning.

**Rationale**: FR-002's clarification is explicit that scope is not
restricted to a subset of workflow files — "restricting derivation to the
eight sweep-stage files would leave a new workflow file uncovered, the same
hole one level up." A glob over the real directory is also self-updating:
a 35th workflow file added later needs no edit here, which is the whole
point of this feature.

**Alternatives considered**:
- *Keep a hand-typed list of the 12 files known to contain agent steps
  today* — rejected: this is the exact shape of decay FR-001 removes: a
  35th file with a new agent step would need someone to add it to this new
  list too, one layer up from where `SUBJECTS` decayed.
- *Derive from `git ls-files` instead of `glob`* — rejected: adds a
  subprocess dependency for no behavioural difference in a repository whose
  working tree is what CI and `run-local-gates.py` both already operate on;
  `glob` reads the same tree with no new failure mode.

## D2 — A job is a subject iff any of its steps' `uses:` matches the agent action, checked structurally

**Decision**: Reuse the existing `AGENT_ACTION_RE` / `_is_agent_step`
structural check unchanged — a step is an agent step iff its parsed
`uses:` field matches `^anthropics/claude-code-action@`. A job is a subject
iff `job.get("steps")` contains at least one such step. This is already
FR-008-compliant by construction: `yaml.safe_load` only populates `uses:`
from an actual step mapping, so a mention of `claude-code-action` inside a
`run:` string, a YAML comment, or a gate fixture embedded in
`lint-workflows.yml`'s own heredoc self-tests can never populate that field.

A job whose `jobs.<name>` mapping has no `steps` key at all — a
`workflow_call` reference at the job level, e.g. every job in the 13
`wing-commander-*.yml` wrappers (`uses: ./.github/workflows/<stage>.yml`) —
contributes zero derived subjects and raises no error: `job.get("steps") or
[]` already treats "no steps visible" as "zero agent steps found," not as
a parse failure. Verified against the shipped tree: all 13 wrapper
workflows are exactly this shape today, so the clean self-test tree already
exercises this branch on every run, with no synthetic fixture needed for
it.

**Rationale**: FR-002 makes agent-step presence the *whole* condition,
independent of what runs after it — the requirement text is explicit that a
job's disposition (FR-012/FR-013/FR-014) is a separate question decided
*after* the job is already a subject, never a precondition for being one.
Keying off `uses:` alone, rather than off name patterns or comments,
directly satisfies FR-008 and the "comment or documentation fixture" edge
case without new code.

**Alternatives considered**:
- *Match the agent action by a version-pinned regex (`@v1` exactly)* —
  rejected: the spec's own edge case calls this out ("keyed on an exact
  pinned reference would miss a version bump"); the existing
  `^anthropics/claude-code-action@` prefix match (no trailing version
  anchor) already tolerates a version bump, and this feature does not
  narrow it.

## D3 — The floor is a checked-in `{path: [job, ...]}` map compared by containment, not identity

**Decision**: `SUBJECTS` (today's hand-typed `{path: [job_names]}`
selection map) is renamed in place to `SUBJECT_FLOOR` and repurposed: it no
longer decides what `scan()` inspects — the glob-and-derive pass in D1/D2
does that — it is now read only for the FR-004 comparison. `SUBJECT_FLOOR`
keeps its current 9-file, per-job content (`tasks.yml`'s two jobs, etc.)
unchanged in shape, and gains four new entries for the jobs D5 below decides
belong in it: `board-loop.yml`'s `triage`/`route`/`fix`/`review`,
`cleanup.yml`'s `teardown-done`, `rebase.yml`'s `rebase`. `watchdog.yml`'s
`diagnose` is *not* added to the floor — see D6: an excluded job's presence
is asserted by the exclusion record, not the floor, matching FR-004's own
text ("including the jobs the exclusion record covers" describes jobs whose
contract-applicability the exclusion record answers; a job structurally
incapable of the defect by a 10-minute bound is not a job whose
*disappearance* this feature needs to detect via the floor's job-existence
check to still be meaningful — the floor and the exclusion record answer
different questions per FR-004's own text, and watchdog's placement in one
without the other is a deliberate, reasoned choice, recorded in D6).

Comparison: `derived_subjects` (the set of `(path, job)` pairs D1/D2
produce) MUST be a superset of `set(SUBJECT_FLOOR)` (flattened to the same
pair shape). A floor member absent from the derived set fails, naming that
`(path, job)`. A derived member absent from the floor is inspected exactly
like any other subject and never fails for that reason alone (FR-004's
second bullet) — this is what makes an un-updated floor fail *safe* rather
than shrinking coverage.

**Rationale**: The clarification under "What is the derived set compared
against" names exactly this shape — "a checked-in floor... derivation MUST
cover every member... and MAY exceed it." Renaming `SUBJECTS` in place
(rather than introducing a second, parallel constant) keeps one map to
maintain instead of two, and keeps every existing `SUBJECTS`-keyed
docstring/comment reference a one-word rename instead of a structural
rewrite.

**Alternatives considered**:
- *A minimum subject count instead of a named floor* — rejected already by
  the clarification itself (tolerates one job disappearing while another
  appears); not re-litigated here.
- *Store the floor as a separate JSON/YAML data file instead of a Python
  literal* — rejected: every other structural constant in this gate
  (`STALL_REASON_JOBS`, `FAILED_STEP_REQUIRED_JOBS`,
  `REQUIRED_PER_AGENT_STEP_COMPOSITES`) is a Python literal in the same
  file, self-tested by the same `--self-test` mutation harness that
  `copy.deepcopy`s the loaded tree; a second file format would need its own
  parse-failure handling for no behavioural gain.

## D4 — The exclusion record is a checked-in `{(path, job): reason}` map, consulted after derivation, before the credential checks

**Decision**: A new module-level constant, `EXCLUSIONS: Dict[Tuple[str,
str], str]`, maps an excluded `(path, job)` pair to a one-line, human-facing
reason. `scan()` partitions each derived subject into exactly one of:
inspected-by-the-credential-checks (checks 1/2/6/9 in the gate's own
numbering), or excluded-with-a-reason. `check_job()` gains an `excluded:
Optional[str]` parameter: when set, it skips checks 1/2/6/9 (the
freshness-across-the-agent-step checks the exclusion reason makes moot) but
still runs checks 3 (tolerance) and 7 (failed-post-agent-step, where that
job is also named in `FAILED_STEP_REQUIRED_JOBS`) unconditionally — those
two check a property of the step itself or of a *different* job's contract,
never the credential-freshness property the exclusion concerns (mirroring
how `AGENTLESS_JOBS` already keeps checks 3/5 live today for
`tasks-approved`).

A derived subject that is neither in `EXCLUSIONS` nor passes the credential
checks fails the gate (FR-013) by the same failure messages checks 1/2/6/9
already produce today — no new failure class, since an unexcluded subject
is simply inspected.

**Rationale**: FR-012/FR-013 require the exclusion to be "an explicit,
checked-in act, never the absence of an entry." A dict keyed by the exact
`(path, job)` pair the derivation rule already produces is the smallest
structure that satisfies "explicit act" without inventing a second job
identity scheme.

**Alternatives considered**:
- *Encode the exclusion as a sentinel job name in `SUBJECT_FLOOR` itself
  (e.g. a magic suffix)* — rejected: conflates two independent questions
  (FR-004's "is this job still here" vs FR-012's "does the contract apply
  to it") into one map, which is exactly the ambiguity FR-004's own
  clarification text warns against.

## D5 — Disposition of the four newly-surfaced workflows, assessed against FR-014's rule

FR-014's rule: a job whose agent step carries no wall-clock bound *and* is
followed by a step that acts as the bot adopts the contract; every other
agent-bearing job is excluded with its reason recorded. Assessed against
the shipped tree (2026-09-26, `main` tip `91e23d4`):

| Workflow | Job(s) | Agent step(s) | Wall-clock bound? | Bot-acting step follows? | Disposition |
|---|---|---|---|---|---|
| `watchdog.yml` | `diagnose` | `Diagnose` | Yes — `timeout-minutes: 10` on the step itself (`watchdog.yml:2290`) | n/a | **Excluded** (FR-014's own stated example) |
| `board-loop.yml` | `triage` | `Triage-propose` | No | Yes — relay (`wing-commander-context`) and `wing-commander-post-agent-credential-status` already follow it | **Adopt** — already carries relay + credential-status; missing only `wing-commander-agent-ran-signal` (grep over the file finds zero calls to that composite anywhere) |
| `board-loop.yml` | `route` | `Route-propose` | No | Same as `triage` | **Adopt** — same gap (missing agent-ran-signal) |
| `board-loop.yml` | `fix` | `Fixer` | No | Yes — relay, `wing-commander-refresh-remote` (this job pushes a fix branch), and credential-status already follow it | **Adopt** — same gap |
| `board-loop.yml` | `review` | `Reviewer`, `Review-fixup` (two agent steps in one job) | No | Yes — relay, `wing-commander-refresh-remote`, and credential-status already follow each | **Adopt** — same gap, for both agent steps' own windows |
| `cleanup.yml` | `teardown-done` | `Completion summary` | No | Yes — `Close lifecycle issue and flip label` (GH_TOKEN), `Delete pipeline branches` (`git push origin --delete` over the credential the earlier `actions/checkout@v5` steps persisted) both still read the pre-agent `steps.ctx.outputs.token` mint | **Adopt** — none of the relay/refresh/signal/credential-status machinery exists in this job today |
| `rebase.yml` | `rebase` | `Resolve conflicts` | No | Yes — `Publish rebased branch` (`git push --force-with-lease`), `Abandon and escalate` (`gh issue edit`/`gh label create`), `Announce the rebase escalation` (callout `token:`) all read the pre-agent `steps.ctx.outputs.token` mint | **Adopt** — same gap as `cleanup.yml`, plus a git remote push that needs `wing-commander-refresh-remote` |

Six of the seven newly-surfaced jobs adopt the contract; one (`watchdog.yml`
`diagnose`) is excluded. `board-loop.yml`'s four jobs need only the missing
`wing-commander-agent-ran-signal` call added at each agent step's own
window (research.md's `agent-ran-signal.md` contract, spec 052) — they
already carry the rest. `cleanup.yml`'s `teardown-done` and `rebase.yml`'s
`rebase` need the full treatment: a post-agent `wing-commander-context`
re-mint, every post-agent `GH_TOKEN`/`token:`/`github_token:` reference
switched from `steps.ctx.outputs.token` to `env.WC_BOT_TOKEN`, a
`wing-commander-refresh-remote` call (both jobs persist a git-remote
credential via `actions/checkout@v5`'s `token:` and later `git push`),
`wing-commander-agent-ran-signal`, and `wing-commander-post-agent-
credential-status`. This is genuine production code, not only a gate
change — User Story 3 exists precisely because turning derivation on
surfaces real, uncovered jobs, not only a hypothetical future one.

**Note on a stale precedent**: `specs/052-agent-credential-lifetime/
research.md`'s D5a states `rebase.yml`/`cleanup.yml`'s agent steps "each
carr[y] its own `timeout-minutes: 10`," matching `auto-update-spec-kit.yml`'s
excluded jobs. Neither file contains a `timeout-minutes` key anywhere today
(`grep -rn timeout-minutes` over both returns nothing) — D5a's factual
premise for those two files does not hold against the current tree, and
this feature's own FR-014 does not rely on it: the clarification and FR-014
above assess `cleanup.yml`/`rebase.yml` fresh, structurally, and reach
"adopt," not "exclude." This discrepancy in spec 052's own research.md is
outside this feature's scope to correct and is reported separately.

**Rationale**: FR-014 requires the assessment be done, not merely asserted;
the table above is that assessment, grounded in the shipped file content
rather than repeated from the spec's own prose summary (which already
independently reaches the same "adopt all but watchdog" conclusion by a
different route — Overview's "post-agent contract adopted?" column reads
"none" for all three non-`watchdog` rows, i.e. not yet, not "structurally
exempt").

**Alternatives considered**:
- *Exclude `cleanup.yml`/`rebase.yml` on spec 052's D5a precedent* —
  rejected once the shipped files were actually read: the precedent's
  premise (a 10-minute bound) is not present, and the spec's own
  clarification already directs a fresh per-job assessment rather than
  inheriting a different feature's exclusion.

## D6 — `watchdog.yml`'s `diagnose` exclusion is recorded once, in `EXCLUSIONS`, not floored

**Decision**: `EXCLUSIONS[(".github/workflows/watchdog.yml", "diagnose")]`
records the `timeout-minutes: 10` reason FR-014 states. `diagnose` is not
added to `SUBJECT_FLOOR`: the floor's job is to fail when a job the
repository is "known to contain" disappears from derivation (FR-004), and
an excluded job's exclusion reason (a wall-clock bound intrinsic to the
step) does not depend on the job continuing to exist — if `diagnose` were
ever deleted outright, nothing in this feature's contract is left unproven
by its absence, unlike a floored, adopting job whose disappearance would
silently shrink real coverage. Flooring it anyway would cost nothing today
but would misstate what the floor is for.

**Rationale**: Keeps the floor's meaning single-purpose (detects a
disappearing *covered* subject) and the exclusion record single-purpose
(records why a *present* subject's contract doesn't apply), matching
FR-004's own distinction between the two mechanisms.

**Alternatives considered**:
- *Floor every derived subject, excluded or not, for uniformity* —
  rejected: SC-004 only requires the floor to answer "is this job still
  here" for jobs whose disappearance would be a coverage regression; an
  excluded job's disappearance is not one, and flooring it would make a
  future "why is this excluded job on the floor" question with no answer.

## D7 — Companion maps: derive nothing new; each remaining hand-kept map gets its own stated reason (FR-015)

**Decision**: None of the three companion maps changes shape; each gains
(or already carries) an explicit reason for staying hand-kept:

- `STALL_REASON_JOBS` and `FAILED_STEP_REQUIRED_JOBS` are keyed to the
  *survivor/stalled* job or the *entry* job of a stage, not to the
  agent-bearing job the D1/D2 derivation rule selects — deriving them would
  need a second structural rule (e.g. "the job named `stalled` that
  `needs:` a subject job"), which is itself exactly the kind of hand-kept,
  undecayed-until-proven convention this feature is not scoped to design or
  prove correct for a second time. Reason recorded in-place as a comment
  addition to both maps: "keyed to a different job than the agent-step
  subject derivation selects; deriving this would need its own structural
  rule, out of scope for this feature (spec 072 item 1)."
- `REQUIRED_PER_AGENT_STEP_COMPOSITES` is not a job-selecting map at all —
  it is a fixed list of composite-name conventions checked at every derived
  subject's own agent-step window. Nothing to derive; already reasoned in
  its existing docstring.
- `NO_REMOTE_REFRESH_JOBS` is a genuine, small, per-job judgment ("this job
  never persists a git-remote credential") that cannot be derived from
  agent-step presence — gains two additions from D5's table
  (`board-loop.yml`'s `triage`/`route`, which push no branch) and confirms
  `cleanup.yml`'s `teardown-done` and `rebase.yml`'s `rebase` are *not*
  members (both push via a persisted checkout credential, per D5), each
  with the existing one-line reason convention this map already uses.

**Rationale**: FR-015 offers two satisfying outcomes — derive, or state a
reason — and only one of the three maps has anything derivable about it in
this feature's scope; forcing derivation onto the other two would add a
second, undertested structural rule for a shape this feature was not asked
to redesign.

**Alternatives considered**:
- *Derive `STALL_REASON_JOBS`/`FAILED_STEP_REQUIRED_JOBS` from a
  `needs:`-graph walk* — rejected as out of scope: correct today with zero
  drift incidents recorded against it (unlike the `SUBJECTS` list this
  feature replaces, which spec.md's Overview table shows already drifted
  four times), and a `needs:`-graph walk is a materially different, riskier
  piece of structural inference than "does this job's own steps contain an
  agent step."

## D8 — Self-test: three retired mutations get one-for-one floor-mismatch replacements; two new mutations cover FR-009's remaining minimums; one new mutation covers FR-013

**Decision**:

| Retired `SUBJECT_MUTATIONS` entry | Replacement | Why it is a like-for-like swap |
|---|---|---|
| `mut_nonexistent_ninth_file` (pointed the old `SUBJECTS` dict at a 9th nonexistent file) | `mut_floor_names_nonexistent_file` — add a `(path, job)` pair naming a nonexistent workflow file to `SUBJECT_FLOOR` | Both assert "the gate notices a named subject it cannot reach"; only the map being mutated changes (`SUBJECT_FLOOR` now, not the selection map) |
| `mut_zero_files` (emptied the old `SUBJECTS` dict) | `mut_derivation_yields_zero_subjects` — patch the glob step to return no files, confirm `scan()` reports the "misconfigured, zero subjects" failure | Same end state (nothing to inspect); this mutation now also satisfies FR-009's "a derived set emptied" minimum directly, so it is not a separate, fourth mutation |
| `mut_nonexistent_job_in_existing_file` (pointed the old `SUBJECTS` dict at a job absent from a real file) | `mut_floor_names_nonexistent_job` — add a `(existing path, nonexistent job)` pair to `SUBJECT_FLOOR` | Same assertion, same map swap as the first row |

Two further mutations satisfy FR-009's remaining minimums, neither a
replacement of a retired one:

- `mut_agent_step_reference_respelled` — respell one real agent step's
  `uses:` to a reference the `AGENT_ACTION_RE` prefix match no longer
  matches (e.g. `anthropics/claude-code-action-v2@v1`), on a job distinct
  from the one `mut_job_loses_agent_step` already targets (avoids two
  mutations asserting the identical code path with the identical fixture).
  Satisfies FR-009's third named minimum directly.
- `mut_excluded_job_removed_from_exclusions` — delete
  `watchdog.yml`/`diagnose`'s entry from `EXCLUSIONS` and confirm the gate
  then fails: with the exclusion gone, `diagnose` is inspected under the
  full checks, and (per D5's table) it has no relay/refresh/signal/
  credential-status machinery at all, so it fails immediately. Proves the
  exclusion record is load-bearing (FR-013), not decorative.

`mut_job_loses_agent_step` (existing) needs no code change but its
docstring/assertion gains one sentence: under derivation this mutation now
fails via the *floor* branch (the job silently drops out of the derived set
entirely, and the floor still names it) rather than via `check_job`'s old
"expected at least one agent step, found none" branch — same mutation,
same failing outcome, different internal code path, which is exactly
FR-010's "keep it working against the derived set" option rather than the
"replace it" option.

Net mutation count after this feature: 3 retired, 3 replacements (one
doing double duty for an FR-009 minimum), 2 pure additions — up from
today's shipped count, never down, satisfying SC-005.

**Rationale**: FR-010 forbids deleting a mutation without a same-branch
replacement; FR-011 (a mutation that stops changing anything must itself
fail loudly) is unaffected — none of these mutations touch code this
feature does not itself introduce or repoint, so the existing
`if mutated == base` guard covers them for free.

**Alternatives considered**:
- *Keep `SUBJECTS` as a second, still-hand-typed selection map purely so
  the three old mutations need no change* — rejected: this is the
  literal shape SC-004 forbids ("zero workflow paths or job names are
  enumerated by hand... for the purpose of selecting subjects"); keeping a
  dead selection map around to avoid updating three mutations would satisfy
  the letter of FR-010 while violating SC-004 outright.

## D9 — `--self-test` output and FR-007's "reader can name every inspected file/job" requirement share one code path

**Decision**: `scan()` gains a `report_subjects: bool` parameter (default
`False` for the existing failure-only behavior); `main()`'s non-self-test
path calls it with `report_subjects=True` and prints the derived
`(path, job)` set (sorted, one per line) to the job summary/stdout
alongside the existing failure lines, on both a passing and a failing run.
`--self-test` does not print this list (it runs many mutated trees, not the
one shipped tree a reader would want named).

**Rationale**: FR-007 requires this on every run, not only a failing one;
piggybacking on the same `scan()` call `main()` already makes (rather than
a second derivation pass) keeps the printed set and the actually-inspected
set structurally the same list, so they cannot drift from each other the
way a hand-maintained "gates covers: ..." comment could.

**Alternatives considered**:
- *A separate `--list-subjects` mode* — rejected: FR-007 asks for this on
  every run "so a reader can confirm coverage without re-deriving it" —
  gating it behind a second flag means the default CI run (what a PR author
  actually sees) still doesn't show it, reintroducing the same "have to go
  read the source" gap FR-007 exists to close.
