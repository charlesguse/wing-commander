# Feature Specification: An Evidence Gate Grounded in the Cited Signal, Not the Agent's Copy of It

**Feature Branch**: `spec-draft/119-signal-grounded-evidence-gate`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #856 — "watchdog: evidence gate checks the
agent's copy of finding facts instead of the cited signal" (routed from
the board loop, issue #748, as `agent_proposed_spec`; found by the code
review of #744)

## Overview

The watchdog's **Evidence validity gate** (`watchdog.yml`, the step named
`Evidence validity gate` in the `triage` job) is the last deterministic
check standing between a diagnosed Finding and a filed `pipeline-defect`
issue. It asks two questions, and only one of them is grounded in
something the pipeline itself computed:

1. **Does the Finding cite a signal this run actually emitted?** This half
   reads `needs.collect.outputs.signals` — deterministic collector output
   — and is sound.
2. **Does the Finding's `normalizedFacts` carry every key in its class's
   required-key list?** This half reads the diagnose agent's
   `normalizedFacts` object: free-form JSON the model typed.

The second question decides a durable action — whether a real defect
reaches the board at all — from the model's transcription. The only thing
that makes the model copy those facts is a sentence in the diagnose prompt
("a denied-tool Finding must carry both stage and tool, copied from its
signal's facts, or it is dropped as ungrounded"). A prompt instruction the
model silently skips produces no error and no test failure; the Finding is
dropped with a `::warning::` in a job log nobody reads. Constitution
principle IX names this shape exactly — "judgment that gates a durable
action … belongs in deterministic code, not an agent's prompt" — and it
names `normalizedFacts` specifically as the input already shown to drift.

The facts the gate wants already exist deterministically. Every collector
stamps a `facts` object onto the signals it emits, and `Stamp signal ids`
derives a per-kind `identity` projection from those facts, hashes it, and
that hash is the signal id the Finding must cite. The gate is therefore
one dereference away from the real thing and reads a copy instead.

**`normalizedFacts` has no other load-bearing consumer.** It is not hashed
into the fingerprint (the fingerprint is `class | sorted(cited signal
ids)`; the `normalizedFacts` basis was deleted deliberately after it was
shown to drift). It is not rendered into the filed issue body, the
recurrence comment, or the dedup marker — `Ensure pipeline-defect issue`
composes its body from `description`, `evidence` and the canonical
fingerprint facts, and never touches it. Gating is the *only* thing it
does, and the only outcome a slip in it can produce is a lost real
finding. That asymmetry is what makes this worth fixing rather than
tightening the prompt again.

### Why this is spec-shaped and not a one-line plumbing fix

The issue proposes "have the gate read the required keys from the cited
signals' `facts`, or fill `normalizedFacts` from them before checking."
That is straightforward for three of the eleven classes and impossible as
literally stated for six of them, because the gate's required-key
vocabulary and the collectors' fact vocabulary are two different
vocabularies that were never reconciled:

| Finding class | Gate's required keys | What the cited signal's `facts` actually carries |
|---------------|----------------------|--------------------------------------------------|
| `denied-tool` | `stage`, `tool` | `stage`, `tool` — literal match |
| `lost-progress` | `branch` | `branch` (from `branch-drift`) — literal match |
| `token-budget-warning` | `job` | `job` (from `step-summary`) — literal match |
| `stage-mismatch` | `expected`, `actual` | `expected-stage`, `actual-stage` — renamed |
| `cost-line-missing` | `stage`, `expected`, `actual` | `stage`, `run`, `cost-available`, `lifecycle-comment-found` — no `expected`/`actual` |
| `cost-line-malformed` | `stage`, `expected`, `actual` | `stage`, `run`, `observed-text`, `expected-pattern` — near, but renamed |
| `turn-budget-trend` | `stage`, `expected`, `actual` | `stage`, `band`, `counted-turns`, `intended-budget`, `enforced-ceiling` — no `expected`/`actual` at all |
| `narrative-drift` | `stage`, `expected`, `actual` | `pr`, `claim-type`, `claimed-value`, `actual-value` — no `stage` |
| `spec-number-collision` | `spec`, `expected`, `actual` | `number`, `claimants` — no `spec`, no `expected`/`actual` |
| `missing-spec-artifact` | `branch` | no collector emits this class-hint; grounding source unsettled |
| `missing-spec-metadata` | `branch` | no collector emits this class-hint; grounding source unsettled |

For those six-plus classes, today's gate is not checking a transcription
of a fact — it is requiring the model to **invent** a value with no
deterministic source, and suppressing the Finding when it declines to. A
`turn-budget-trend` Finding survives the gate only because the model
guessed words for `expected` and `actual` that no signal contains. So the
fix cannot be a mechanical dereference; the repository has to decide what
the gate's deterministic subject *is* for every class. That is a design
trade-off spanning the collectors, the stamper, the schema and the prompt
— spec-shaped under principle X.

### Scope boundary

This feature changes **what the evidence gate reads and what it requires**,
and the collector/stamper plumbing needed to make that reading possible.
It does not change: the fingerprint basis (`class | sorted(cited signal
ids)`), the dedup lookup, the suppression rules above the gate, or which
classes are issueless. It does not widen the gate's teeth — a Finding that
cites nothing, or cites a signal this run did not emit, must still be
suppressed exactly as it is today.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A real defect is filed even when the agent's copy is incomplete (Priority: P1)

A watchdog run inspects a stage run that was denied a tool. The collector
emits a `tool-denial` signal stamped `facts: {stage: "implement", tool:
"Bash"}`. The diagnose agent correctly classes the Finding `denied-tool`
and correctly cites that signal's id, but its `normalizedFacts` reads
`{tool: "bash"}` — it omitted `stage`. Today that Finding is suppressed
and the denial never reaches the board. After this feature, the gate reads
the grounding facts from the cited signal, sees both required facts
present, and the Finding is filed.

**Why this priority**: This is the reported defect. Every run of the
watchdog is exposed to it, on every class, and its failure mode is silent
— a suppressed real finding looks exactly like a clean run.

**Independent Test**: Drive the shipped `Evidence validity gate` step
directly (the existing `verify-gate-19.py` harness already does this) with
a class, an agent `normalizedFacts` missing a required key, and a cited
signal whose `facts` carry it. The gate must report `valid=true`.

**Acceptance Scenarios**:

1. **Given** a `denied-tool` Finding citing a signal whose facts carry
   `stage` and `tool`, **When** the agent's `normalizedFacts` omits
   `stage`, **Then** the gate passes the Finding and it reaches
   fingerprinting.
2. **Given** the same Finding, **When** the agent's `normalizedFacts` is
   an empty object `{}`, **Then** the gate still passes it — the agent's
   copy is descriptive only and cannot be the reason a grounded Finding is
   dropped.
3. **Given** a Finding of any class in the vocabulary, **When** its cited
   signals carry that class's grounding facts, **Then** the gate passes it
   regardless of what `normalizedFacts` contains.
4. **Given** a `denied-tool` Finding whose agent `normalizedFacts` says
   `{stage: "plan", tool: "bash"}` while the cited signal's facts say
   `{stage: "implement", tool: "bash"}`, **When** the gate runs, **Then**
   the gate's decision rests on the signal's values, not the agent's, and
   the disagreement does not by itself suppress the Finding.

---

### User Story 2 - An ungrounded finding is still suppressed (Priority: P1)

The watchdog diagnoses a Finding whose cited signals do not actually
contain the facts its class is about — or that cites no signal at all.
The gate must still suppress it, exactly as today, and say which grounding
fact was missing from which cited signal.

**Why this priority**: The gate exists because a `denied-tool` finding
shaped `{tool: null, denials: null}` — the shape every historical false
positive carried — used to pass. Moving the gate's subject from the
agent's copy to the signal must not cost it its teeth; a gate that cannot
fail its subject is worse than no gate.

**Independent Test**: Drive the shipped step with a Finding citing a
signal whose facts lack the class's grounding fact, and with a Finding
citing no signal. Both must report `valid=false` with a reason naming what
was missing.

**Acceptance Scenarios**:

1. **Given** a Finding citing no signal id, **When** the gate runs,
   **Then** it suppresses with the existing "evidence is empty" reason.
2. **Given** a Finding citing a signal id this run did not emit, **When**
   the gate runs, **Then** it suppresses with the existing "did not emit"
   reason.
3. **Given** a `denied-tool` Finding citing a signal whose facts carry
   `stage` but no `tool`, **When** the gate runs, **Then** it suppresses
   and the reason names `tool` and the signal it was missing from.
4. **Given** a Finding whose every cited signal carries an empty `facts`
   object, **When** the gate runs, **Then** it suppresses — a Finding must
   still be grounded in something.

---

### User Story 3 - A maintainer adding a class or collector is told at gate time (Priority: P2)

A maintainer adds a new collector, or the `__new__` escape hatch registers
a new finding class. The grounding rule for that class is missing. The
maintainer learns this from the local gate suite before pushing, not from
a `::warning::` buried in a watchdog job log weeks later.

**Why this priority**: The current mismatch — six classes whose required
keys no signal carries — is exactly what a missing check of this kind
produces over time. Consolidating the vocabulary without a gate behind it
lasts until the next collector.

**Independent Test**: Add a class to the finding-class vocabulary with no
grounding rule and run the gate suite; it must fail naming that class.
Mutate an existing class's grounding rule out of the workflow and the
suite must fail.

**Acceptance Scenarios**:

1. **Given** a finding class present in the diagnose schema's vocabulary,
   **When** the gate suite runs and that class has no grounding rule,
   **Then** the suite fails and names the class.
2. **Given** a collector emitting a signal source with no identity
   projection in `Stamp signal ids`, **When** the gate suite runs, **Then**
   the suite fails and names the source (today this is a runtime
   `::warning::` only).
3. **Given** a grounding rule deleted or weakened in the workflow, **When**
   the gate suite runs, **Then** it fails — the rule is mutation-tested,
   not merely read.

---

### Edge Cases

- **A Finding cites several signals of different kinds.** A
  `gate-suite-failure`-shaped Finding may legitimately cite a
  `step-summary` signal and an `annotations` signal together. The gate
  must define whether a grounding fact may be satisfied by *any* cited
  signal or must come from a signal of the kind that matches the class
  [NEEDS CLARIFICATION: see Q2].
- **The Finding's class disagrees with every cited signal's
  `class-hint`.** A `denied-tool` Finding citing only a `step-summary`
  signal is either a model mis-class (suppress) or a legitimate
  cross-signal diagnosis (file).
- **A class the `__new__` hatch just registered.** By construction it has
  no grounding rule on the run that proposes it, because the deterministic
  registration step runs in the same job.
- **A signal source with no identity projection** falls into the stamper's
  `else` branch, where `ident` is "all string facts, lowercased". Its facts
  exist but its identity vocabulary is unbounded.
- **A Finding of an issueless class** (`narrative-drift`) is reported but
  never filed. The gate still runs on it, so a grounding rule is still
  needed for it, or it must be explicitly exempted.
- **`normalizedFacts` disagrees with the signal.** The values differ but
  both are present. Nothing durable rests on the agent's copy, so this
  must not suppress — but a maintainer reading the issue may be misled if
  the copy is surfaced anywhere.
- **Every collector failed** and `evidence-available` is false. Diagnose
  does not run; the gate is never reached. Unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The evidence gate's decision to suppress or pass a Finding
  MUST rest only on data the pipeline computed deterministically — the
  cited signals and their collector-stamped facts — and MUST NOT rest on
  the diagnose agent's `normalizedFacts` object.
- **FR-002**: A Finding whose `normalizedFacts` is missing keys, empty, or
  in disagreement with its cited signals MUST NOT be suppressed for that
  reason alone, provided its cited signals carry the class's grounding
  facts.
- **FR-003**: The gate MUST continue to suppress a Finding that cites no
  signal id, and one that cites an id this run did not emit, with the
  reasons it reports today.
- **FR-004**: Every finding class the diagnose schema can emit MUST have a
  **grounding rule** — a deterministic statement of which facts, on which
  cited signals, ground a Finding of that class. Grounding rules MUST have
  exactly one home in the repository, referenced rather than restated by
  any second consumer.
- **FR-005**: The grounding rules MUST be expressible for every class
  currently in the vocabulary, including the six whose required keys have
  no literal counterpart on their signals' facts (`stage-mismatch`,
  `cost-line-missing`, `cost-line-malformed`, `turn-budget-trend`,
  `narrative-drift`, `spec-number-collision`)
  [NEEDS CLARIFICATION: see Q1 — whether by a key→fact-path mapping, by
  re-founding the gate on the stamper's identity projection, or by
  shortening each class's required list to what its signals carry].
- **FR-006**: When the gate suppresses a Finding, its reason MUST name the
  grounding fact that was absent and the cited signal it was absent from,
  so a maintainer can confirm the suppression from the job log without
  re-running the watchdog.
- **FR-007**: A Finding whose class has no grounding rule MUST be handled
  by a single stated rule rather than falling through to today's implicit
  "at least one non-empty agent fact" behaviour
  [NEEDS CLARIFICATION: see Q3 — file with a warning, or suppress].
- **FR-008**: The gate MUST define whether a class's grounding facts may be
  satisfied collectively across all cited signals or must be satisfied by a
  cited signal whose kind corresponds to the Finding's class
  [NEEDS CLARIFICATION: see Q2].
- **FR-009**: The gate suite MUST fail when a class in the finding-class
  vocabulary has no grounding rule, and when a signal source emitted by a
  collector has no identity projection in the stamper. The second
  condition is a runtime `::warning::` today and MUST become a gate
  failure.
- **FR-010**: The gate suite MUST carry a fixture in which the agent's
  `normalizedFacts` omits a key that the cited signal's facts carry, and
  MUST assert the Finding is passed, not suppressed. This fixture MUST
  cover every class in the vocabulary, not only `denied-tool`.
- **FR-011**: The gate suite MUST carry a fixture in which no cited signal
  carries a class's grounding fact, and MUST assert the Finding is
  suppressed.
- **FR-012**: Each grounding rule MUST be mutation-tested: deleting or
  weakening a rule in the shipped workflow MUST make the gate suite fail.
- **FR-013**: The diagnose prompt's instruction that `normalizedFacts`
  must carry a class's identifying keys "or it is dropped as ungrounded"
  MUST be corrected once it is no longer true, and any workflow comment
  describing the gate's subject MUST be updated in the same change —
  comments in this repository are byte-compared by gates and are treated
  as code.
- **FR-014**: The fingerprint basis (`class` plus sorted cited signal ids),
  the dedup lookup, and the suppression steps above the gate MUST be
  unchanged by this feature.
- **FR-015**: Whatever the gate reads MUST be available to it at the point
  it runs — if it needs the stamper's per-signal identity projection, that
  projection MUST be retained on the signal rather than discarded, as it is
  today.

### Key Entities

- **Signal**: a collector-emitted observation carrying `source`,
  `class-hint`, a collector-stamped `facts` object, and — after `Stamp
  signal ids` — a `signal-kind` and a hashed `id`. The deterministic record
  of what the run actually contained.
- **Signal identity projection**: the per-kind subset of a signal's facts
  that `Stamp signal ids` hashes into the id. Computed today, then
  discarded before the signals leave the collect job.
- **Finding**: the diagnose agent's verdict — `class`, `description`,
  `evidence` (cited signal ids), `normalizedFacts`, `severityHint`.
- **`normalizedFacts`**: the agent's short, human-facing summary of a
  Finding's facts, drawn from a fixed ten-key vocabulary. Currently the
  gate's subject; after this feature, descriptive only.
- **Grounding rule**: the per-class statement of which deterministic facts
  must be present on a Finding's cited signals for it to be filed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero of the gate's suppression decisions depend on the
  diagnose agent's output — demonstrated by the gate producing an
  identical verdict for the same cited signals under an empty, a partial,
  and a fully populated `normalizedFacts`.
- **SC-002**: 100% of the finding classes the diagnose schema can emit
  have a grounding rule, and the gate suite fails if a class is added
  without one.
- **SC-003**: Every class in the vocabulary has at least one fixture
  proving a real finding survives an incomplete agent transcription, and
  at least one proving an ungrounded finding is suppressed.
- **SC-004**: Every grounding rule fails the gate suite when mutated out of
  the workflow — no rule is asserted only by reading.
- **SC-005**: A maintainer reading a suppression message in a watchdog job
  log can name the absent fact and the signal it was absent from without
  opening the run's artifacts.
- **SC-006**: The `verify-gate-19.py` denied-tool dedup fingerprints, and
  the fingerprint step's output, are byte-identical before and after this
  change for an unchanged set of cited signals.

## Assumptions

- The diagnose agent continues to choose the Finding's class and to cite
  signal ids; this feature constrains only what is done with that output,
  not who produces it. The class enum and the signal-id enum in the
  diagnose schema are unchanged.
- `normalizedFacts` remains in the schema and the prompt as a descriptive,
  human-facing field. It is not removed, because the Finding's
  human-readable rendering may want it later, and removing a schema field
  is a wider change than this issue asks for.
- The signals blob already passed between jobs
  (`needs.collect.outputs.signals`) is the gate's source of facts; no new
  artifact or job output is assumed necessary beyond retaining data the
  collect job already computes.
- The existing `verify-gate-19.py` harness — which renders the shipped
  step scripts and runs them under fixtures — is the home for the new
  fixtures, rather than a new standalone gate script.
- Classes whose grounding source is unsettled today
  (`missing-spec-artifact`, `missing-spec-metadata` — no collector emits
  their `class-hint`) are resolved by this feature, either by a grounding
  rule naming the signals that legitimately support them or by the
  no-rule policy of FR-007.
- This change affects behaviour that only runs in Actions, so it is proven
  after merge by re-driving one watchdog run and recording the evidence.

## Clarifications

### Q1: What is the gate's deterministic subject for classes whose required keys have no literal counterpart on the cited signals' facts?

**Context**: FR-005. Six of eleven classes are affected; `turn-budget-trend`
requires `expected` and `actual`, and its signals contain neither.

- **Option A — per-class key→fact-path mapping.** Keep the required-key
  vocabulary; add, in one home, a mapping from each class's keys to the
  fact paths on its signals (`expected` → `expected-stage`, and so on),
  with a synthesised value where no single fact corresponds. *Implication*:
  smallest change to the gate's shape; the mapping is a new thing to keep
  in step with collectors, and the synthesised values for
  `turn-budget-trend` are invented by the mapping rather than by the model
  — deterministic, but still not observed.
- **Option B — re-found the gate on the stamper's identity projection.**
  Stop checking a key vocabulary. Require instead that each cited signal
  carries a complete, non-empty identity projection — the very facts
  `Stamp signal ids` already hashes into the id the Finding cites — and
  retain that projection on the signal so the gate can read it.
  *Implication*: one vocabulary instead of two; the gate's subject becomes
  exactly the fingerprint's subject, which is the invariant that matters;
  the per-class required-key list disappears, and with it the
  class↔signal-kind coupling question becomes explicit rather than
  implied.
- **Option C — shorten each class's required list to what its signals
  carry.** Keep reading keys, but re-derive each class's list from the
  facts its collectors actually stamp, dropping `expected`/`actual` where
  nothing produces them. *Implication*: least new machinery; weakens the
  gate for the classes whose lists shrink, and leaves two vocabularies in
  place to drift again.

### Q2: May a class's grounding facts be satisfied by any cited signal, or only by one whose kind matches the class?

**Context**: FR-008, Edge Cases. A Finding may cite several signals of
different kinds.

- **Option A — any cited signal.** A grounding fact is present if any
  cited signal carries it. *Implication*: permissive; a `denied-tool`
  Finding citing only a `step-summary` signal that happens to carry a
  `stage` fact would pass.
- **Option B — a kind-matched signal.** The class must map to one or more
  signal kinds, and the grounding facts must come from a cited signal of
  such a kind; other cited signals are corroboration. *Implication*:
  strictly stronger; requires a class↔kind map, which the `class-hint`
  field already half-provides; risks suppressing a legitimate
  cross-signal diagnosis where the model chose a class whose kind it did
  not cite.
- **Option C — kind-matched where a mapping exists, any-signal
  otherwise.** *Implication*: no class is blocked on a mapping being
  written, but the strength of the gate then varies per class, which is
  the kind of implicit difference this feature exists to remove.

### Q3: What happens to a Finding whose class has no grounding rule?

**Context**: FR-007. Occurs for a `__new__`-registered class on the run
that proposes it, and for any class added ahead of its rule.

- **Option A — file it, with a warning.** Fall back to "at least one cited
  signal carries a non-empty fact". *Implication*: a genuinely new problem
  type still reaches the board on the run that discovers it; the gate is
  weakest exactly where the vocabulary is least settled.
- **Option B — suppress it, with a warning naming the missing rule.**
  *Implication*: no ungrounded issue is ever filed; a genuinely new problem
  type is lost until a maintainer writes its rule, and the `__new__` hatch
  effectively costs one run.
- **Option C — file it under the no-rule fallback only when the class was
  registered by the `__new__` hatch this run; suppress otherwise.**
  *Implication*: preserves the hatch's purpose while keeping the gate
  strict for the settled vocabulary; one more branch to gate and test.
