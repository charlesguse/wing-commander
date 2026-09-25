# Feature Specification: A Stage-Finding Dedup Key That Does Not Drift With Agent Wording

**Feature Branch**: `076-stable-finding-dedup-key`

**Created**: 2026-09-25

**Status**: Draft

**Input**: Lifecycle issue [#569](https://github.com/charlesguse/wing-commander/issues/569) — "stage findings: the dedup fingerprint hashes gate_or_artifact verbatim, so one punctuation change files a twin instead of appending", routed from the board loop out of originating issue [#424](https://github.com/charlesguse/wing-commander/issues/424)

## Context

Spec 056 gave every stage a mouth: an agent that meets a defect outside its
own task describes it, and a deterministic step files it. FR-011 of that
spec promised the other half — the same defect met again appends to the
issue already open rather than opening a twin. The dedup key that promise
rests on is a fingerprint over the stage, a file path, and a one-line name
for the thing that is wrong (`gate_or_artifact`). Both of the latter are
free text the agent phrases fresh on every run.

Five runs of one stage against one deliberately planted defect, recorded on
#424, show what that costs:

| run | title the agent wrote | the name the agent wrote | result |
|---|---|---|---|
| 3 | Constitution Principle III name contradicts its own body text | `Principle III: Test-First (NON-NEGOTIABLE)` | filed an issue |
| 4 | Constitution Principle III name contradicts its own body text | `Principle III. Test-First (NON-NEGOTIABLE)` | filed a twin |
| 5 | Constitution Principle III name contradicts its own body text | `Constitution Principle III (Test-First (NON-NEGOTIABLE))` | filed a third twin |

The lookup itself is sound — searching for run 3's marker returns run 3's
issue. Only the key moved. A first fix normalised the value before hashing
(lowercase, punctuation and spacing collapsed), which closes the gap
between runs 3 and 4 and is already on main. Run 5 proves it is not
enough: normalisation erases punctuation, case and spacing, and cannot
erase a word the agent adds. The title, which nothing in the spec
constrains, was byte-identical across all three runs; the field the spec
chose as the key was not.

The unit harness cannot see any of this. Its fixtures hand the filing step
a fixed name, so dedup is proven for identical input and never for the
input an agent actually produces twice.

Two things follow. First, this is a Principle IX problem, not a prompt
problem: the prompt already asks the agent for "a stable name (a heading, a
job name, a gate name), never a sentence" and the agent still varied it on
every attempt. A prompt instruction is a request the model can silently
fail; the key has to be something code can either compute or check.
Second, choosing the replacement key is a trade-off the owner has to
settle, because every candidate trades dedup precision against how much
agent wording the key still trusts — which is why this reached the spec
pipeline instead of a local fix PR.

Scope note: the board loop's own code-review findings (spec 057) carry the
same `fingerprint_basis` shape and file the same way, so whatever key this
feature settles on has an obvious second consumer. Whether it takes it in
this release is an open question below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The same defect met twice reaches one issue (Priority: P1)

A stage meets a planted defect, describes it, and an issue is filed. The
pipeline runs again — a later iteration, a re-drive, a different spec
touching the same file — and the same stage meets the same defect and
describes it again, in its own fresh words. No second issue appears. The
open issue picks up a line saying the defect was seen again in this run,
and the maintainer scanning the board sees one item, not a column of
identical ones.

**Why this priority**: This is the promise FR-011 of spec 056 already
made and the pipeline does not keep. Until it is kept, the board's signal
degrades with every iteration: the more the pipeline runs, the more twins
bury the defects a maintainer has not yet seen.

**Independent Test**: Drive the same stage three times against one planted
defect, with nothing between the runs that would make the agent phrase its
description identically, and confirm exactly one issue exists afterwards
carrying two "seen again" references.

**Acceptance Scenarios**:

1. **Given** two runs of one stage meeting one defect in one file, where
   the agent's free-text description of that defect differs between the
   runs in punctuation, capitalisation, spacing, and at least one added or
   dropped word, **When** both runs complete, **Then** exactly one issue
   exists and the second run is recorded on it as an append.
2. **Given** two runs of one stage meeting two genuinely different defects
   in one file, **When** both runs complete, **Then** the two defects are
   distinguishable on the board — the maintainer can read both
   descriptions and act on each — however many issues that takes.
3. **Given** a finding routed to an already-open issue, **When** the
   maintainer opens that issue, **Then** the later run's own description
   of the defect is available there, not only a bare link to the run.
4. **Given** one stage meeting a defect and a different stage meeting the
   same defect, **When** both runs complete, **Then** they are keyed
   apart, because a finding's label and attribution are per-stage.

---

### User Story 2 - The key is computed or checked, never taken on trust (Priority: P1)

Whatever the key is made of, a reviewer can re-derive it from the run's
inputs and get the same answer. Nothing in the key is a value the pipeline
accepted from the agent without either computing it itself or checking it
against something on disk. When a proposed finding carries a key component
the pipeline cannot verify, that is a malformed proposal and the pipeline
says so with a log line, rather than filing under a key that will not
match next time.

**Why this priority**: Constitution Principle IX: the agent proposes, code
decides. A key hashed from unverified prose looks deterministic — the same
string always hashes the same — while being, in practice, a coin flip on
every run. This story is what makes the dedup behaviour in User Story 1
testable at all.

**Independent Test**: Feed the filing step fixtures directly, with no agent
running: two findings whose key components differ only in phrasing produce
one key; two findings naming genuinely different subjects produce two; a
finding whose key component cannot be verified against the file it names is
handled by the stated fallback and the reason is recorded.

**Acceptance Scenarios**:

1. **Given** a proposed finding whose key component the pipeline can check
   against the file the finding names, **When** the check fails, **Then**
   the finding is not filed under that component and the run records why.
2. **Given** any filed finding, **When** its key is recomputed from the
   run's recorded inputs, **Then** the value is identical.
3. **Given** the filing step's own test fixtures, **When** they are
   inspected, **Then** at least one pair exercises the wording variance an
   agent actually produced (punctuation, case, and a differing word), not
   only byte-identical input.

---

### User Story 3 - A defect with nothing quotable still reaches the board (Priority: P2)

Some defects have no anchor to quote: a file that should exist and does
not, a registry entry that was never added, a gate that is missing rather
than wrong. The stage that meets one of these still has something worth
filing. It reaches the board under a key the pipeline can stand behind, and
a maintainer reading the resulting issue can tell the several defects
apart even when they share that key.

**Why this priority**: Without this story, tightening the key trades one
failure (twins) for a worse one (silence). A defect dropped for lacking a
quotable anchor is a defect nobody ever sees.

**Independent Test**: Feed the filing step a finding about a file that does
not exist in the tree and confirm it is filed or appended — not silently
dropped — and that the resulting issue carries the finding's own full
description.

**Acceptance Scenarios**:

1. **Given** a finding whose subject cannot be anchored to text in the
   named file, **When** the filing step runs, **Then** the finding still
   reaches the board and the run summary records which route it took.
2. **Given** a second, different finding that falls to the same fallback
   key as a first, **When** a maintainer opens the resulting issue,
   **Then** both descriptions are readable there in full.

---

### User Story 4 - The change is provable without a five-run drill (Priority: P3)

The behaviour is demonstrated by checked-in fixtures a reviewer can run
locally in seconds, and the documents that define the key — the data model
that states the fingerprint rule, and the sentence in every stage's prompt
that tells the agent what the field is for — say the same thing as the
code.

**Why this priority**: The defect was found only because a human ran the
same drill five times by hand. The next drift should fail a gate instead.

**Independent Test**: Run the repository's local gate suite on a tree where
the key rule has been changed in the code but not in the data model, or
not in the prompt sentence, and confirm a gate fails.

**Acceptance Scenarios**:

1. **Given** the key rule stated in the data model, **When** it is compared
   against the rule the filing step applies, **Then** any divergence fails
   a gate.
2. **Given** the sentence in each stage's prompt describing what the agent
   must supply, **When** the required content of the key changes, **Then**
   a stale copy of that sentence fails a gate rather than surviving
   unnoticed.

---

### Edge Cases

- A finding whose key component is verifiable but matches many places in
  the named file — the key must still be deterministic.
- A finding about a file that is renamed between two runs: the key moves,
  and a twin is filed. This is out of scope; the spec records it as a
  known limit rather than solving rename tracking.
- An issue filed under the key rule in force before this change: its stored
  marker no longer matches, so the next encounter files a new issue once.
- A finding whose key would collide with a genuinely unrelated defect met
  by the same stage in the same file — the maintainer must be able to tell
  them apart from the issue body alone.
- The cap on findings filed per run interacting with appends: an append is
  not a new issue, and the run summary must not report it as one.
- Two stages of one pipeline run meeting the same defect in the same file
  in the same run.
- A key component containing only characters that the pipeline's
  normalisation removes, leaving an empty value.

## Requirements *(mandatory)*

### The key itself

- **FR-001**: A finding's dedup key MUST NOT change when the agent
  re-describes the same defect in different words. Specifically, two
  descriptions of one defect that differ in punctuation, capitalisation,
  spacing, or in words added or dropped around the same subject MUST
  produce the same key.
- **FR-002**: The key MUST remain deterministic and re-derivable: given the
  run's recorded inputs, a reviewer recomputing the key MUST get the same
  value.
- **FR-003**: The key MUST continue to be scoped by the stage that found
  the defect, so two stages meeting one defect do not collide.
- **FR-004**: The key's composition MUST be settled as follows.
  [NEEDS CLARIFICATION: which keying strategy? The evidence on #424
  eliminates "normalised agent prose" and leaves four candidates, each a
  different trade between precision and trusted wording: (a) key on stage
  plus file path only, with the append carrying the later finding's full
  text — no agent wording in the key at all, at the cost of two distinct
  defects in one file sharing one issue, and one board item per
  (stage, file) rather than per defect; (b) key on stage, file path, and a
  normalised title — the field that was byte-identical across all three
  observed runs, but still agent wording; (c) require the agent to supply a
  value it can only copy, not phrase — an exact heading, job name, or gate
  name — and reject a value that does not occur verbatim in the named
  file, with a stated fallback for defects that have no quotable anchor;
  (d) a fixed enumeration of artifact kinds, as the watchdog's finding
  class became after #118/#120/#122. The lifecycle issue records the
  maintainer's recommendation as (c) with (a)'s append-with-full-text as
  the fallback, but the routing note records it as the owner's call.]
- **FR-005**: No component of the key may be a value the pipeline accepted
  from the agent without either computing it itself or checking it against
  a file in the tree. A component that cannot be computed or checked MUST
  NOT enter the key.
- **FR-006**: A proposed finding carrying a key component the pipeline
  checks and rejects MUST NOT be filed under that component, and the run
  MUST record the rejection with the finding's title and the reason,
  consistent with spec 056's existing drop-with-a-log-line discipline.

### Not losing findings to the tighter key

- **FR-007**: A finding that cannot supply a verifiable key component MUST
  still reach the board — filed or appended — rather than being discarded.
  [NEEDS CLARIFICATION: what is the fallback route for an unanchorable
  finding? Candidates: fall back to the stage-plus-file-path key of
  FR-004(a) so the finding lands on (or appends to) the file-level issue;
  or treat the absence of an anchor as a distinct key component of its own
  so unanchorable findings do not merge with anchored ones; or file it
  under a "needs triage" key that a maintainer sweeps. This question only
  has force if FR-004 resolves to a strategy with a verifiable component.]
- **FR-008**: When a later encounter appends to an issue already open, the
  append MUST carry the later finding's own description of the defect — its
  title and what is wrong — not only a reference to the run. This is what
  keeps a coarser key readable: several distinct defects sharing one key
  remain individually legible from the issue body.
- **FR-009**: The per-run cap on findings MUST continue to count filings
  and appends as spec 056 defines them, and the run summary MUST continue
  to distinguish filed from appended.

### Proving it

- **FR-010**: The filing step's checked-in fixtures MUST include at least
  one pair of findings that describe one defect in wording an agent
  actually varied — differing in punctuation, in capitalisation, and in at
  least one word — and assert that the pair produces a single key; and at
  least one pair naming genuinely different subjects that asserts two keys.
  Fixtures that hand the step byte-identical input MUST NOT be the only
  evidence of dedup.
- **FR-011**: A fixture MUST cover the FR-007 fallback route, so the
  unanchorable case is proven by the harness and not only by reasoning.
- **FR-012**: The key rule MUST be stated in exactly one canonical place in
  the specification artifacts of spec 056 (its data model, beside the
  existing fingerprint definition), and the repository's existing
  single-home discipline MUST be extended so a divergence between that
  statement and the filing step's behaviour fails a gate.
- **FR-013**: The sentence in each stage's agent prompt that describes what
  the agent must supply for the key MUST be updated to match the settled
  rule, in one canonical copy with the other call sites pointing at it, per
  this repository's canonical-comment discipline.

### Compatibility and reach

- **FR-014**: Issues filed under the previous key rule will not match under
  the new one. The change MUST record this consequence where a maintainer
  will meet it (spec 056's data model), and MUST NOT attempt to rewrite
  markers on already-filed issues as part of this feature.
- **FR-015**: The scope of this change across the repository's two
  finding-filing consumers MUST be settled.
  [NEEDS CLARIFICATION: does the board loop's code-review finding key
  (spec 057, `board-review-finding.schema.json`) adopt the same rule in
  this release, or does this feature change stage findings only and leave
  the board loop's separate key to a later change? The two share a
  proposal shape and both file to the board, so a split leaves two rules
  live at once; taking both widens the change to a second workflow and a
  second fixture set.]
- **FR-016**: Whatever the settled rule, the pipeline MUST NOT gain any
  new grant that lets an agent file an issue directly — the agent still
  proposes and code still decides.

### Key Entities

- **Stage Finding**: the agent's proposal — a title, a statement of what is
  wrong, evidence paths, and the components of the dedup key. Unchanged in
  purpose; this feature changes what the key components are and what
  validation they must pass.
- **Dedup Key**: the derived value that decides file-vs-append. Today a
  hash over the stage, a normalised file path, and a normalised free-text
  name. This feature redefines its composition under FR-004.
- **Key Anchor**: a value the pipeline can check against the tree rather
  than trust — for example a heading or name that must occur verbatim in
  the file the finding points at. Exists only if FR-004 resolves to a
  strategy that has one.
- **Filed Finding Issue**: the durable board item, carrying the key as a
  marker in its body. Unchanged in shape; this feature changes which
  encounters land on the same one and what an append must contain.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Three consecutive runs of one stage against one planted
  defect, with the agent free to phrase its description afresh each time,
  produce exactly one board item — one filing and two appends. Today the
  same drill produces three.
- **SC-002**: Two findings describing one defect whose key components
  differ in punctuation, capitalisation, and one added word produce one key
  in the checked-in fixtures; two findings naming different subjects
  produce two.
- **SC-003**: 100% of key components that the pipeline cannot compute or
  verify are kept out of the key, verifiable by inspecting the filing
  step's inputs against its key computation.
- **SC-004**: No finding that would have reached the board under the old
  rule is silently discarded under the new one: every proposal that passes
  schema validation is filed, appended, or dropped with a recorded reason.
- **SC-005**: A maintainer opening any issue that carries more than one
  encounter can read each encounter's own description of what is wrong
  without opening a run transcript.
- **SC-006**: A change to the key rule in the filing step that is not
  reflected in the canonical statement of that rule fails a gate in the
  repository's local gate suite.
- **SC-007**: The dedup behaviour can be demonstrated in under one minute
  from a clean checkout by running the checked-in fixtures, with no agent
  run and no scratch repository.

## Assumptions

- The normalisation already merged (lowercase, non-alphanumeric runs
  collapsed, trimmed) stays in place and applies to whatever string
  components the settled key retains; this feature builds on it rather
  than reverting it.
- The marker-in-body lookup that reads the key back from an open issue is
  sound and is not changed by this feature — the evidence on #424 shows the
  lookup returning the right issue when the key matches.
- Losing the match on issues filed before this change is acceptable: each
  affected defect files one new issue on its next encounter and then dedups
  normally. No migration of existing markers is in scope.
- File renames between runs are out of scope; a defect whose file moves is
  expected to file a new issue.
- The cap, the labels, the attribution line, the outstanding-task
  cross-link, and the run summary defined by spec 056 are unchanged except
  where FR-008 and FR-009 name a change.
- This feature does not widen which stages file findings, nor change the
  enabled/disabled defaults spec 056 set per stage.
- The stage prompt sentence about the key is treated as code, per this
  repository's rule that workflow comments and prompt prose are
  gate-compared.

## Dependencies

- Spec 056 (`056-stage-found-defect-filing`) defines the filing step, the
  schema, the fingerprint, and the FR-011 append promise this feature is
  keeping. Its data model is the canonical home for the key rule.
- Spec 057 (`057-autonomous-board-loop`) is the second consumer of the
  proposal shape and the board that suffers the twins; FR-015 decides
  whether it is in scope here.
- The normalisation change already on main is a prerequisite and remains
  useful under every candidate strategy.
