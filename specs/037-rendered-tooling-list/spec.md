# Feature Specification: The Prompt's Tooling List States What the Run Actually Permits

**Feature Branch**: `037-rendered-tooling-list`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "The implement stage's prompt states its own shell tooling from a list rendered by the wing-commander-tool-args composite action (`shell-commands`), instead of a hand-maintained copy. That output currently ships undeclared — it is not in the composite's published contract, has no functional requirement, no acceptance criteria, and no test or gate — and its render is wrong or undefined in four ways: it never subtracts the effective disallowed list, it renders nothing for a bare `Bash` grant, it collapses exact-match and prefix grants to the same text, it emits duplicates after unwrapping, and an empty result reaches the model as a dangling em-dash inside a sentence claiming the list is 'exactly' the allowlist and 'authoritative'. Declare the output as part of the published composite contract and specify its render precisely, with executable coverage."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The agent is told the truth about what it can run (Priority: P1)

An implementation run begins. The prompt tells the agent which shell commands it may run, and that statement is derived from the same lists the run enforces — so every command named is one the agent can actually execute, and no command the run denies is named. An agent that reads the statement and acts on it never spends a turn on a command that was going to be refused, and never declines a task step believing a permitted command is unavailable.

**Why this priority**: This is the failure the feature exists to close, and it has already cost a feature. Spec 036 reached a finalize PR with four tasks unrun, its own task list recording that the gate suite it was told to run was "auto-denied" — a stage whose task list said to run a validation suite could not run it. The first repair derived the statement from the allowlist, which fixed the direction that bit; the opposite direction is still open, because the statement is derived from what is allowed without regard for what is denied. A prompt that names a denied command under a sentence claiming the list is authoritative is the same drift the derivation was meant to end, pointed the other way.

**Independent Test**: Drive the shipped composition with a configuration that denies a shell command the stage allows by default, and confirm that command is absent from the statement handed to the agent while the enforced lists themselves are unchanged; then drive it with no configuration at all and confirm the statement names exactly the stage's default shell commands.

**Acceptance Scenarios**:

1. **Given** a consumer denies a shell command that the stage allows by default, **When** the prompt is composed, **Then** that command does not appear in the stated list.
2. **Given** the same configuration, **When** the enforced lists are composed, **Then** they are unchanged by the presence of the statement — the subtraction affects what the agent is told, never what the agent is permitted.
3. **Given** no consumer configuration at all, **When** the prompt is composed, **Then** the stated list names exactly the shell commands the stage grants by default, and no others.
4. **Given** a consumer replaces the allowed list wholesale, **When** the prompt is composed, **Then** the stated list is derived from the replacement, not from the stage's defaults.
5. **Given** a consumer denies a command and separately allows it again, **When** the prompt is composed, **Then** the statement agrees with the enforced outcome rather than with either input alone.

---

### User Story 2 - The statement is well-formed for every legal configuration (Priority: P1)

Whatever tool lists a run is configured with — the stage's defaults, an addition, a wholesale replacement, an unrestricted shell grant, or a list with no shell grant in it at all — the agent reads a complete, accurate sentence about its tooling. It never reads a sentence with a hole where the list should be, and never reads a list that promises more than the grant behind it allows.

**Why this priority**: The statement is a claim made to a model in a headless run that no human reads before it is acted on. A malformed or over-broad claim is not a cosmetic defect: an empty enumeration inside a sentence asserting the list is exact tells the agent that no shell command is permitted in a run where several are, and a grant permitting only an exact command stated as though arguments were permitted sends the agent into refusals it cannot diagnose. Both are latent today only because no consumer has used the configurations that produce them.

**Independent Test**: Drive the shipped composition once per legal configuration shape — unrestricted shell grant, no shell grant, exact-command grant, prefix grant, the same command granted in both forms — and confirm each produces a complete sentence whose content matches what that grant actually permits.

**Acceptance Scenarios**:

1. **Given** an allowlist granting unrestricted shell access, **When** the prompt is composed, **Then** the statement says that any shell command is permitted, rather than enumerating none.
2. **Given** an allowlist with no shell grant of any kind, **When** the prompt is composed, **Then** the statement says that no shell command is permitted, as a complete sentence with no dangling punctuation and no empty enumeration.
3. **Given** a grant that permits only an exact command with no arguments, **When** the prompt is composed, **Then** the statement distinguishes it from a grant that permits the command with any arguments.
4. **Given** the same command granted in both exact and prefix form, **When** the prompt is composed, **Then** the command is stated once, in the form that reflects the broader of the two grants.
5. **Given** any legal configuration whatsoever, **When** the prompt is composed, **Then** the tooling paragraph reads as a grammatical sentence.
6. **Given** an allowlist containing tools that are not shell grants, **When** the prompt is composed, **Then** those tools are not enumerated as shell commands and their absence from the list is not phrased as a denial of them.
7. **Given** a configuration that composes no allowed list at all, **When** the stage runs, **Then** the agent step does not run, and the reason it did not run is that composition produced no list — a configuration that composes a list containing no shell grant still runs the agent, with a statement saying no shell command is permitted.

---

### User Story 3 - An adopter can see every output the composite emits (Priority: P1)

Someone adopting this pipeline reads the composite action's documented interface to understand what it produces and what they can rely on. Every output the action emits is there, with what it contains and what is guaranteed about it. Nothing the action produces is discoverable only by reading its source.

**Why this priority**: The composite action is part of the published contract that adopters pin by release tag, where every output name is a compatibility surface. An output that exists in the source but not in the contract is unowned in both directions: an adopter who finds it and uses it has no promise it will survive a release, and a maintainer changing it has no way to know someone depends on it. This is the constitutional half of the feature, and the reason the rest of it needs a spec at all.

**Independent Test**: Read the composite's published interface and confirm that the set of outputs it documents is exactly the set the action emits; then add an output to the action without documenting it and confirm a check fails.

**Acceptance Scenarios**:

1. **Given** an adopter reads the composite's published interface, **When** they enumerate its outputs, **Then** every output the action emits is listed, with its content and its guarantees.
2. **Given** an adopter reads that interface, **When** they consider overriding a stage's tool lists, **Then** they can predict what the statement will say for their configuration, including which entries it excludes and why.
3. **Given** an output is added to the composite without being declared, **When** the repository's checks run, **Then** a check fails and names the undeclared output.
4. **Given** a declared output is removed from the composite, **When** the repository's checks run, **Then** a check fails — the contract and the action are held in agreement in both directions.

---

### User Story 4 - The behavior cannot regress silently (Priority: P1)

Every guarantee this feature establishes is exercised by an executable test that drives the shipped composition rather than a copy of it. Reverting any one of them fails a test before merge, not months later in a headless run whose prompt nobody reads.

**Why this priority**: The statement's whole value is that it is derived rather than maintained by hand — a derivation nothing checks is a hand-maintained copy with extra steps. This repository has already been taught this twice: a verifier that sat green while checking code that did not ship, and a gate that stopped detecting anything without anyone noticing. The composition has no executable coverage at all today; the original composite was validated once, by hand, at implementation time.

**Independent Test**: Break each guarantee in turn — remove the subtraction, remove the unrestricted-shell case, remove the empty-list fallback, remove the deduplication — and confirm a distinct test fails for each; then confirm the whole suite passes on the finished implementation.

**Acceptance Scenarios**:

1. **Given** the finished implementation, **When** the coverage runs, **Then** every acceptance scenario in User Stories 1 and 2 is exercised against the shipped composition, not a copy of it.
2. **Given** any single guarantee is reverted, **When** the coverage runs, **Then** a test fails and names what broke.
3. **Given** the new coverage exists, **When** the repository's gate registry runs, **Then** the coverage is registered, so a check that stops being run is itself a failure.
4. **Given** the check that holds the contract and the action in agreement, **When** its own self-test runs, **Then** the self-test demonstrates it failing on a known-bad input.

---

### User Story 5 - A maintainer can see what the agent was told (Priority: P3)

A maintainer reading a finished run's own record can see the tooling statement that run handed to its agent, alongside the tool lists it composed. When an agent reports that a command was denied, or declines a task step for want of a tool, the maintainer can tell in one place whether the statement was wrong or the agent was.

**Why this priority**: This is diagnosis, not correctness. Nothing is broken without it, and every guarantee above holds whether or not it ships. It earns its place because the class of defect this feature fixes was found by reading a task list, not a run — the run itself recorded that tool lists had been composed and nothing about what they said.

**Independent Test**: Complete a run and confirm the statement it handed to its agent is recoverable from the run's own record without reading the workflow source.

**Acceptance Scenarios**:

1. **Given** a completed composition, **When** a maintainer reads the run's record, **Then** the tooling statement that run produced is there.
2. **Given** a composition that produced no permitted shell commands, **When** a maintainer reads the run's record, **Then** that outcome is visible as such rather than as a missing entry.

---

### Edge Cases

- **A grant permitting only an exact command** (no arguments) versus one permitting the command with any arguments: both authorize the same words, but only one authorizes them with an argument. Stating them identically advertises capability the exact grant denies. No such grant exists in the pipeline's own lists today, so this is reachable only through consumer configuration — which is exactly the surface this feature is declaring.
- **An unrestricted shell grant**: legal, and the most permissive configuration a consumer can supply. It currently produces the same statement as the most restrictive one — that no shell command is permitted.
- **A deny that overlaps an allow without matching it entry-for-entry** (a command permitted with any arguments, and one specific invocation of it denied): the command remains largely permitted, so it is still stated; only a deny that covers the allow entirely removes it from the statement.
- **A deny naming a command that is not granted at all**: nothing to subtract, and the statement is unchanged. It is not an error.
- **The same command granted twice in different forms**: the enforced list holds both entries legitimately; the statement must not enumerate the command twice.
- **A configuration that permits no shell commands but permits other tools**: the agent still has tools and must not be told otherwise; only the shell claim is empty.
- **An entirely empty allowed list**: the agent step does not run at all. The condition that skips it means the composition did not produce a list, and must keep meaning exactly that — it is not a proxy for whether the statement is empty, and nothing may come to depend on it as one.
- **A grant whose command contains the character that separates entries in a tool list**: not expressible in the existing list format, and this feature does not make it so. The statement inherits that limit rather than appearing to transcend it.
- **A stage other than the implement stage adopting the same statement**: the output is available to every stage that composes tool lists. Only one states its tooling today; the guarantees must not assume a single consumer.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An agent prompt that states which shell commands the run permits MUST derive that statement from the tool lists the same step enforces, never from a separately maintained copy.
- **FR-002**: The stated list MUST exclude every shell command that the same run's composed disallowed list denies in full.
- **FR-003**: Producing the statement MUST NOT alter the enforced allowed or disallowed lists. A run supplied with no tool configuration MUST enforce lists byte-identical to those it enforces today.
- **FR-004**: The statement MUST distinguish a grant that permits a command with any arguments from one that permits only the exact command, so an agent cannot infer argument capability the grant withholds.
- **FR-005**: A grant of unrestricted shell access MUST be stated as permitting any shell command, not as an absence of permitted commands.
- **FR-006**: When a configuration permits no shell command at all, the statement MUST say so explicitly.
- **FR-007**: A command that would be stated more than once MUST be stated once, reflecting the broader of the grants behind it.
- **FR-008**: The tooling statement MUST be a grammatical, complete sentence for every legal configuration, with no dangling punctuation and no empty enumeration.
- **FR-009**: The prompt MUST NOT claim more about the stated list than the composition guarantees. Any claim that the list is exact or authoritative MUST hold for every legal configuration, or MUST be narrowed to the claim that does.
- **FR-010**: Entries that are not shell grants MUST be excluded from the statement, and the statement MUST be phrased so that their absence from it is not read as their denial.
- **FR-011**: Every output the composite action emits MUST be declared in its published contract, stating what the output contains and what is guaranteed about it.
- **FR-012**: An output that the composite emits without declaring, or declares without emitting, MUST fail an automated check that names the discrepancy.
- **FR-013**: The published per-stage tool-list documentation MUST state what the statement includes and excludes, so an adopter configuring their own lists can predict what their agent will be told.
- **FR-014**: Every guarantee in FR-001 through FR-010 MUST be exercised by executable coverage that drives the shipped composition rather than a copy of it; reverting any one of them MUST fail a test.
- **FR-015**: The new coverage and the new check MUST be registered in the repository's existing gate registry, so that a check which stops being run is itself a failure, and the check MUST carry a self-test demonstrating it failing on a known-bad input.
- **FR-016**: The condition that skips an agent step when composition produced no allowed list MUST continue to mean only that, and MUST NOT be relied upon to indicate whether the tooling statement is empty.
- **FR-017**: This feature MUST NOT change any published stage's declared inputs or secrets, MUST NOT change the composed allowed or disallowed lists for any configuration, and MUST NOT change adopter-visible behaviour other than the wording of the tooling statement and the newly declared output.
- **FR-018**: The tooling statement produced for a run MUST be recoverable from that run's own record.

### Key Entities

- **Tool grant**: one entry in a composed allowed or disallowed list. A grant may name a non-shell tool, an unrestricted shell, a shell command permitted with any arguments, or a shell command permitted exactly as written.
- **Enforced lists**: the composed allowed and disallowed lists actually handed to the agent. They are the authority on what runs; the statement describes them and never substitutes for them.
- **Tooling statement**: the sentence in an agent prompt naming the shell commands that run permits. Derived from the enforced lists, and true of them for every legal configuration.
- **Declared output contract**: the published record of every output the composite action emits, which an adopter may pin against and a maintainer may not silently widen.
- **Contract agreement check**: the automated check that holds the declared outputs and the emitted outputs in agreement, in both directions.

## Out of Scope

- **Changing how tool lists are composed.** Append, replace, sentinel handling, and the rule that an explicit allow beats a default deny are settled by spec 026 and are untouched. This feature adds a statement derived from the result; it does not add a composition mode.
- **Implementing enforcement.** Denial is enforced by the agent engine's own precedence between the two lists. The statement describes that outcome and never becomes the mechanism.
- **Whether stage-scoped tool additions should be targetable at individual steps within a stage.** A consumer's addition reaches every agent step in a stage, including ones whose own grant is deliberately small — documented behaviour, and a genuine tension with least privilege, but a question about the composition interface rather than about the statement derived from it. Settled outside this feature: stage-scope is retained and the widening accepted, with the condition for revisiting named (`specs/026-configurable-tool-lists/research.md`, D5, revisited 2026-08-16).
- **Extending the repository's token-permission gate to grants supplied at a reusable-workflow call site.** A real coverage gap in a different gate, with a different owner and a different fix. Filed as issue #215.
- **Making the entry separator escapable** so a grant may contain it. A limit of the existing list format, inherited rather than introduced here.
- **Wiring the statement into stages that do not state their tooling today.** The output must not assume a single consumer, but adding consumers is not part of this feature.
- **Any change to what the implement stage's prompt says beyond its tooling paragraph.**

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across every legal tool-list configuration, the commands named in the tooling statement are exactly the shell commands the run permits: zero named commands that the run denies, and zero permitted commands omitted apart from the documented exclusions.
- **SC-002**: The tooling statement is a complete, grammatical sentence in one hundred percent of legal configurations — including the configurations that permit no shell command, one of which produces a sentence fragment today.
- **SC-003**: A run supplied with no tool configuration enforces tool lists byte-identical to today's, and reaches the same outcome — zero behavioural change for an adopter who configures nothing.
- **SC-004**: The number of outputs the composite emits without declaring is zero, down from one today.
- **SC-005**: Adding an undeclared output to the composite, or removing an emitted one, causes a check to fail before merge.
- **SC-006**: Removing, disabling, or breaking the new check or the new coverage causes a check to fail.
- **SC-007**: Reverting any single guarantee this feature establishes fails a distinct test that names it.
- **SC-008**: An adopter reading only the published documentation can state, for a tool-list configuration of their own, what their agent will be told about its shell tooling.
- **SC-009**: A maintainer can recover the tooling statement a completed run handed to its agent from that run's own record, without reading the workflow source.
- **SC-010**: A run whose task list names a validation command that the run permits no longer reports that command as unavailable — the condition that left spec 036 with four tasks unrun does not recur in either direction.

## Assumptions

- The agent engine denies a tool when the disallowed list names it, regardless of the allowed list — the precedence the existing composition already relies on. This feature describes that outcome accurately; it does not change or re-implement it.
- Spec 026's composition semantics are correct and stay as they are, including the documented property that a composed allowed list may still contain an entry the consumer separately denied. That property is why the statement needs a subtraction of its own rather than a change to the composition.
- The statement is about shell commands specifically. Non-shell tools are conveyed to the agent by the tool interface itself and do not need enumerating in prose; the statement's wording is what must keep that distinction clear.
- Subtraction is decided per grant: a deny removes a command from the statement when it denies everything the corresponding allow permits. A deny that removes only part of what an allow permits leaves the command stated, because it remains permitted in general. No configuration in the repository exercises either case today.
- The repository already has a gate registry, a precedent for gates carrying their own self-tests, and a harness pattern that extracts a shipped step and runs it against controlled inputs. This feature joins those arrangements rather than establishing new ones.
- No new credential, permission, or token scope is required; nothing about what the agent may do changes, only what it is told.
- The implement stage is the only consumer of the statement today. The wrapper-side grant that made the statement's accuracy matter — this repository's own addition of its gate suites — stays as it is, and reaches every agent step in that stage, which is settled and documented behaviour rather than an open question.
- The one output the composite emits without declaring is the only such case; the check required here will confirm that rather than assume it.
