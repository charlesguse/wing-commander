# Research: One read-only inspection policy for stage tool allowlists

Each decision below resolves one design question the spec (#338) left to the
plan stage — either because the spec named the destination but not the
mechanism, or because it explicitly deferred the question (see spec
Assumptions). No `[NEEDS CLARIFICATION]` markers were present in spec.md, so
this document contains no clarification-driven decisions — only planning
decisions that turn the spec's FRs into a shape tasks.md can execute.

## D1 — Where the policy text lives, and what it says

**Decision**: The policy is a new top-level section in
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`, placed
immediately before "## Per-stage default tool lists" (the table it governs),
titled "## Read-only inspection policy". It states, in order:

1. The inspection primitive set: `Bash(grep:*)`, `Bash(head:*)`,
   `Bash(tail:*)`, `Bash(sort:*)`, `Bash(uniq:*)`, `Bash(wc:*)`,
   `Bash(cut:*)` — the set `plan.*`/`tasks.*` already ship (FR-003).
2. The compound/pipe/redirect rule (FR-002): each command in a `|`, `;`, or
   `&&` chain is matched against the allowlist separately; an output
   redirect (`>`, `>>`) or a `cd … &&` prefix is denied regardless of list
   contents, because these are matched as their own (denied-by-default)
   shape, not as the primitive that follows them.
3. The definition of "read-capable stage" (FR-005, D2 below).
4. A pointer to the composite action's `shell-commands` render as the single
   place this guidance reaches an agent (FR-004) — this document states the
   policy once; the render conveys it once; no third copy is authored.
5. A one-line pointer to this feature's occurrence-disposition table
   (contracts/inspection-policy.md, D8) for anyone asking "was occurrence X
   on #266 covered by this."

**Rationale**: FR-001 requires the policy live in the record that already
owns the per-stage lists, with every other mention pointing at it. This
document is that record (Gate 27's `TABLE_DOC` constant already names it as
the single source Gate 27 compares against), and it is the file every prior
spec that touched a stage's tool list (026, 037, 044) has edited in place —
adding a new document would create a second thing Gate 27 would need to
learn to read, for no benefit FR-001 asks for.

**Alternatives considered**: A new standalone `specs/051-*/contracts/inspection-policy.md`
as the actual policy home, with stage-interfaces.md pointing at it — rejected
because FR-001 is explicit that the policy "MUST live in the record that
already owns the per-stage lists," not in this feature's own directory (which
stops being read once the feature ships, unlike the evergreen contract).
This feature's own `contracts/inspection-policy.md` instead holds the diff
this plan will hand to tasks.md — the review copy, not the shipped one — as
is standard practice for `/speckit-plan` contracts under a feature's own
`specs/NNN-*/contracts/`.

## D2 — Definition of "read-capable stage" (FR-005)

**Decision**: A stage's internal agent step is "read-capable" for this policy
if its job is open-ended repository inspection in service of authoring or
modifying an artifact — it is expected to explore the tree to decide what to
read next, not just replay a fixed, small set of `git log`/`git diff`/`git
show` calls whose shape never varies by run. Concretely:

- **Read-capable** (gains the inspection set per FR-003):
  `intake`, `clarify`, `plan.direct-commit`, `plan.pr`,
  `tasks.direct-commit`, `tasks.pr`, `implement.cycle`, `implement.retry`.
- **Deliberately minimal, not read-capable** (unchanged by this feature,
  per the spec's own edge-case list): `implement.post-progress-comment`,
  `finalize`, `cleanup`, `rebase`, `watchdog.diagnose`,
  `pr-conversation.classify`. Each of these already carries a fixed,
  narrow allowed list the table marks or should mark "(deliberately
  read-only)" and none of the nine recorded occurrences came from one of
  them.
- **Out of scope either way**: `pr-conversation.act` (a write step — not a
  read-only inspection step in the sense this policy governs, and it
  produced no recorded occurrence; FR-017/"Out of Scope" bar touching it
  here).

**Rationale**: This is exactly the split the spec's edge cases draw by name;
it is restated here as a rule ("open-ended exploration in service of
authoring" vs. "fixed narrow replay") rather than only as an enumeration, so
Gate 27's new check (D7) has a criterion it can apply to a stage not yet
invented, per Constitution IX — the judgment must be code-checkable, and an
enumeration alone would need silent updating by hand every time a stage is
added, the same failure mode #266 already demonstrated once.

**Alternatives considered**: "Read-capable = has any Bash grant at all"
(named explicitly in the spec's edge cases as the wrong reading) — rejected
because it would force the inspection set onto `implement.post-progress-comment`,
`finalize`, `cleanup`, and `rebase`, each of which is deliberately narrow and
none of which recorded an occurrence.

## D3 — How the compound/pipe/redirect rule reaches the agent (FR-002/FR-004)

**Decision**: Extend `wing-commander-tool-args`'s existing `shell-commands`
output with one more sentence, appended after the existing rendered
statement, stating the compound/pipe/redirect rule and the built-in-tools
expectation:

> "Each command in a pipeline or `;`/`&&` chain is checked separately, and a
> `>`/`>>` redirect or a `cd … &&` prefix is denied regardless of this list —
> use the Read/Grep/Glob tools, or a single command, for anything multi-step."

This is a **static** sentence (not derived from the composed lists the way
the rest of `shell-commands` is) — it states a fact about how the tool-check
layer matches commands, true for every stage and every consumer
configuration, so it does not need per-run computation the way the permitted-
command list does. It is appended unconditionally, even to the
`allowed-tools == ""`/"no shell command" case, since the rule about
compound-command matching applies with equal force to a run that has zero
shell grants (a consumer could still add one via `extra-allowed-tools`).

**Rationale**: FR-004 requires this guidance to "reach the agent from the
same single home as the permitted-command list and cannot drift per
workflow" — the composite's existing `shell-commands` output is that single
home today (spec 037's own contract), so extending it, rather than inventing
a second output or a second composite, keeps exactly one thing to render and
one thing Gate 21 has to check. Every stage prompt already interpolates
`steps.<id>.outputs.shell-commands` into one `Tooling: …` sentence
(`plan.yml:717`, `tasks.yml:702`, `implement.yml:768`, etc.), so extending the
string means every consuming prompt gets the new guidance with a one-line
diff per call site (the interpolation, not the wording) — nothing to author
per stage.

**Alternatives considered**: A second composite-action output
(`compound-command-rule`) rendered alongside `shell-commands` — rejected as
an unforced second thing to wire into five workflows and two gates for text
that never varies by configuration; a static sentence costs nothing to keep
in sync and one still lives in exactly one file (`action.yml`).
Hand-pasting the sentence into each of the five stage prompts instead of the
composite — rejected outright: this is the literal "shipped twelve times, a
rounding fix would have had to land twelve times" failure this repository's
own CLAUDE.md names.

## D4 — Consolidating the four "Shell constraints in this headless run" prompt blocks

**Decision**: Partial consolidation, scoped to what the spec's FR-002/FR-004
actually require. The pipe/chain/redirect bullet inside each of the four
existing "Shell constraints" blocks (`intake.yml`, `plan.yml` ×2, `tasks.yml`
×2, `implement.yml` ×2) becomes redundant with D3's new sentence in the
tooling statement and is deleted from all seven call sites; the remaining
bullets in each block (variable-expansion rejection, environment-assignment
prefix, `.specify` scripts not executable, Grep/Glob over shell loops, no
redirection, `gh auth status` uninformativeness, "denial is not a hint to
retry") are **not** merged into one file — GitHub Actions has no
template-include mechanism for a `prompt:` string, so the only way to give
five workflows one literal copy of prose is a composite-action output (as
D3 does for the one sentence FR-004 actually requires) or a script that
writes the prompt file, neither of which this feature's scope (FR-002/FR-004
alone) justifies for bullets that are already accurate. Each remaining copy
is instead individually corrected for the inaccuracies FR-012/FR-013 name
(D6), so all four say a true thing rather than saying the same true-or-false
thing.

**Rationale**: The spec's own Assumptions section is explicit that "whether
those four copies are consolidated is a design question for the plan stage,
not a requirement here" — it is in scope only "to the extent the policy
changes what it says." FR-002/FR-004 change exactly one bullet's content
(and that bullet moves to the composite render, per D3); the rest of the
block is CI-environment mechanics unrelated to the inspection policy, so
consolidating it is exactly the kind of unrequested refactor this
repository's engineering norms (and CLAUDE.md's "don't add abstractions
beyond what the task requires") caution against doing inside a fix PR.

**Alternatives considered**: Leaving the redundant pipe/chain/redirect bullet
in place alongside D3's new sentence — rejected: two statements of the same
rule in one prompt is the "restated per site" pattern CLAUDE.md's canonical-
pointer rule exists to prevent, and Gate 47
(verify-comment-canonical-pointers.py) covers *comments*, not prompt prose,
so nothing else would catch the two copies drifting.

## D5 — The implement-only gate-suite self-check (FR-009/FR-009a)

**Decision**:

- **Command**: `python .github/scripts/run-local-gates.py` with its default
  (parallel) `--jobs`, not `--jobs 1` — the script's own docstring records
  the suite at ~1599s serial vs. its parallel design intent, and the spec's
  "roughly three and a half minutes" figure is achievable only under the
  default parallel scheduler, not the serial fallback.
- **Placement**: one new `run:` step in `implement.yml`'s `implement.cycle`
  job, after the existing `Install actionlint for the agent` step and before
  the `Compose tool args (cycle)` step, so its pass/fail is knowable before
  the agent step runs (and its output can be summarized to the agent as
  context) — mirroring where `actionlint`/`yamllint`/`shellcheck` already sit
  relative to the agent step in this same job. The identical step is added to
  `implement.retry` for symmetry with every other cycle-vs-retry duplication
  in this file (research.md of specs/026 D5 already treats the two as
  independently-composed siblings).
- **Timeout**: an explicit `timeout-minutes` on the step, generous enough to
  absorb container/runner variance over the ~3.5-minute measured figure —
  10 minutes, matching the existing order-of-magnitude headroom this
  workflow already gives its lint step relative to actionlint's own
  sub-minute typical run.
- **Preflight** (FR-009a): a step immediately before the gate-suite run that
  checks for `python3 -c "import yaml"` (pyyaml — most `verify-*.py` gates
  import it directly), `command -v jq`, and `command -v actionlint` (already
  installed unconditionally by the existing "Install actionlint for the
  agent" step in this same job, so this leg of the preflight is a
  non-degrading confirmation, not a new install). A missing prerequisite
  sets a step output consumed by the gate-suite step's own `if:` — the run
  is skipped, not denied or failed, and a line is appended to
  `$GITHUB_STEP_SUMMARY` naming the missing tool, per FR-009a's "degrade to
  a note" requirement. This mirrors the existing `wing-commander-preflight`
  pattern of "check first, name what's missing, do not fail the job."
- **Allowlist**: `implement.cycle`/`implement.retry`'s default-allowed-tools
  gains `Bash(python .github/scripts/run-local-gates.py:*)` — the gate suite
  is invoked by a deterministic `run:` step, not by the agent's own Bash
  call, mirroring how `actionlint`/`yamllint`/`shellcheck` are separately
  granted to the agent for its own use on files it touches. Unlike those
  three, the full gate suite is not something the agent is expected to
  invoke arbitrarily (it is one fixed pre-push check, not a per-file lint),
  so the grant exists for FR-009's own deterministic step to use — the tool
  args composite always composes the step's own allowlist even for the
  `run:` steps that precede the agent step, since the whole job shares one
  `claude_args` value.

**Rationale**: FR-009's "under an explicit timeout" and FR-009a's
"prerequisites present... degrade to a note" are concrete enough to decide
now rather than leave to tasks.md; doing so here means tasks.md writes code
against a fixed contract instead of re-deriving these numbers.

**Alternatives considered**: Running the suite inside the agent's own Bash
call (granting `Bash(python .github/scripts/run-local-gates.py:*)` for the
agent to invoke itself, as the recorded #266 occurrence shows intake trying)
— rejected: the FR-009a preflight-and-degrade contract is a deterministic
judgment (Constitution IX) about whether to run at all, which a prompt
instruction cannot guarantee is honored before the agent tries the command
anyway. A `run:` step run unconditionally before the agent step, gated on
the preflight's own output, is the only form where "missing prerequisite ⇒
no denial, no failure" is actually enforced rather than requested.

## D6 — Deterministic leftovers (FR-011, FR-012, FR-013)

**Decision**:

- **FR-011**: Add `Bash(printenv SPECIFY_FEATURE_DIRECTORY)` to `intake`'s
  default-allowed-tools, matching `plan.*`/`tasks.*` literally.
- **FR-012**: `intake.yml` does not (and, per D2/D6, will not) export
  `SPECIFY_FEATURE_DIRECTORY` — intake computes a *new* spec directory whose
  slug the agent itself chooses mid-run (per its own prompt step 3: "the
  skill auto-generates the spec directory"), so there is nothing to export
  before the agent runs, unlike plan/tasks/implement which consume an
  *existing* spec directory decided before their agent step starts. The
  "Shell constraints" block's "the variable is already exported for you"
  sentence is therefore scoped out of intake's copy specifically (removed
  from that one bullet in intake.yml's block only) rather than made true by
  adding an export that cannot exist yet. The printenv grant from FR-011
  still lands (parity with plan/tasks, per FR-011's own text), so a curious
  agent that tries it gets an accurate empty result rather than a denial —
  the "second wasted turn" the spec's edge case warns about is a wasted
  *read*, not a wasted *denial*, which this repository's own turn-budget
  language treats as the lesser failure.
- **FR-013**: Remove `Bash(gh auth status)` from `plan.*`/`tasks.*`
  default-allowed-tools. The "Shell constraints" block's existing sentence
  ("`gh auth status`... will not explain [a denial]") remains true whether
  or not the command is granted, so it is kept as-is — it now describes a
  command that is denied for a stated reason (not useful for the one thing
  an agent would reach for it) rather than a granted-but-useless one.

**Rationale**: FR-011/FR-012 are explicitly deterministic ("no decision
needed" per the spec's own section heading) except for the one judgment call
FR-012 leaves open — export vs. scope the sentence — which D6 resolves in
favor of scoping, since exporting is not actually possible before the
agent's own slug choice. FR-013 says "one of the two goes" without naming
which; removing the grant (rather than the prompt sentence) is chosen
because the sentence is *advisory and true regardless of the grant*
("won't help you debug a denial"), while the grant's only demonstrated use
was exactly the debugging attempt the sentence already says won't work — the
grant has no other recorded purpose in either stage's prompt.

**Alternatives considered**: For FR-012, exporting an empty-string
placeholder in intake so the printenv call "succeeds" with an explicit empty
result — rejected as adding a step for a call the agent has no reason to
make (intake's prompt never tells it to read `SPECIFY_FEATURE_DIRECTORY`;
FR-011's grant exists only for cross-stage parity, not because intake needs
the read). For FR-013, keeping the grant and deleting the prompt sentence —
rejected because the sentence is the one piece of shared guidance across
all four "Shell constraints" copies (D4) that is unconditionally true and
cheap to keep; removing it would leave three of the four remaining copies
(plan ×2 keeps it if kept, but tasks/implement/intake also carry the same
sentence) inconsistent with each other for no benefit.

## D7 — Extending Gate 27 and Gate 21 (FR-014/FR-015/SC-003)

**Decision**: Two new checks land in `verify-stage-tool-lists.py` (Gate 27),
alongside its existing table-vs-call-site comparison, each with the
self-test's existing mutation-injection pattern:

1. **Inspection-set completeness**: for every table row whose `step-label`
   is one of D2's read-capable set, the documented allowed list must be a
   superset of the seven-primitive inspection set, OR the row's disallowed
   cell / a recorded adjacent note must name the exception. A read-capable
   row missing a primitive with no recorded exception is a failure naming
   the row and the missing primitive(s) — this is FR-003's "record in its
   table row why it does not" made mechanical.
2. **Repository-guidance reconciliation** (FR-010/FR-015): a small,
   versioned list of (command, stages-that-must-permit-it) pairs — sourced
   from `CLAUDE.md`'s "Before pushing" section post-FR-009b scoping (just
   `python .github/scripts/run-local-gates.py` → `implement.cycle`,
   `implement.retry`) — is checked against the same parsed table, failing if
   a named command is not in the documented allowed list for a stage
   `CLAUDE.md` addresses. This list is intentionally small and hand-authored
   in the gate script (mirroring how Gate 27 already hand-authors
   `TABLE_DOC`/`COMPOSITE` as constants) rather than parsed out of
   `CLAUDE.md`'s prose, because "which command a repository instructs an
   agent to run" is exactly the kind of judgment Constitution IX says
   belongs in code a reviewer can read, not a regex over free text that
   would silently stop matching the day someone rewords a sentence.

`verify-tooling-statement.py` (Gate 21) gains one new case (D3's static
sentence appears, unconditionally, appended to every rendered
`shell-commands` value including the empty case) and one new mutation
(deleting the appended sentence from the action's `run:` block must turn the
new case red), following the file's existing `CASES`/`MUTATIONS` list
pattern exactly.

**Rationale**: FR-015 says the gate is "added to the nearest existing gate
rather than as a free-standing check where one already covers the artifact"
— Gate 27 already reads exactly the table and call sites this policy governs,
and Gate 21 already reads exactly the composite's rendered output D3
extends, so both new checks are additions to those two scripts' existing
`run()`/`CASES` rather than new gate numbers. Constitution VIII requires
every failure branch to ship with a checked-in fixture; Gate 27's
`_mutations()`/`self_test()` and Gate 21's `MUTATIONS`/mutation-loop already
exist as the place such fixtures go, and tasks.md will add one mutation per
new failure mode to each, following the existing structure verbatim.

**Alternatives considered**: A brand-new `verify-inspection-policy.py` gate —
rejected per FR-015's explicit instruction and because it would need to
re-parse the same table and the same call sites Gate 27 already parses,
recreating the exact "two copies, one stale" failure mode Gate 27's own
docstring names as the reason it exists.

## D8 — Occurrence disposition table (FR-016/SC-001)

**Decision**: `contracts/inspection-policy.md` (this feature's own contracts
directory) carries a table mapping each of the nine recorded #266
occurrences to the decision that resolves it — D1-D7 above, or "denied on
purpose" for the one occurrence (`implement`'s `git stash; actionlint …;
git stash pop`) that the spec's edge cases already name as a correct denial
(compound-command shape aside, `git stash`/`git stash pop` are not on
implement's allowed list and are not added by this feature — the fix for
*that* occurrence is the compound-command rule telling the agent not to
chain, not a new grant). This table is what SC-001 and the #266-closing
comment (SC-007) quote.

**Rationale**: FR-016 requires recording, per occurrence, which decision
resolves it, "including occurrences resolved as 'denied on purpose'... so the
fingerprint can be closed against evidence rather than closed as stale." A
single table in this feature's contracts directory is the natural home,
since it never needs updating again after this feature ships (unlike
stage-interfaces.md's policy prose, which is evergreen).

## D9 — SECURITY.md / write-surface record (FR-006/FR-008)

**Decision**: No edit to `SECURITY.md` (specs/011-security-policy). FR-008's
recording obligation is conditional ("should a later change add a
`gh api`-equivalent grant") and does not apply here: this feature grants no
`gh api`-equivalent to any stage, and explicitly records `watchdog.diagnose`'s
pre-existing `Bash(gh:*)` grant as pre-existing-and-untouched (a sentence in
the stage-interfaces.md policy section, D1 item 4, and its own table
footnote already does this — unchanged by this feature).

**Rationale**: Constitution V and FR-006/FR-008 are about *widening* a write
surface; a feature that only routes reads away from `gh api` has nothing to
record.
