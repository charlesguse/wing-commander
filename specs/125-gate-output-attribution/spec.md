# Feature Specification: Attributable Gate Output in the Local Gate Suite

**Feature Branch**: `125-gate-output-attribution`

**Created**: 2026-09-30

**Status**: Draft

**Input**: Lifecycle issue #878 (routed from the board loop, issue #755).
User description: "`verify-auto-release-e2e-gate-decisions.py` fails
intermittently under the parallel local gate runner. Under
`python .github/scripts/run-local-gates.py` it sometimes fails with
`…/_shared/auto-release-container-evidence-decision.sh: No such file or
directory`. The same run's summary table shows it passing, and it passes
when run alone. That looks like a relative-path or cwd race between
parallel gates. A gate that flakes erodes trust in the suite, and CLAUDE.md
says a failing test is never written off as a flake." Folded in from the
issue's staged comment: an earlier attempt (#862) was closed unmerged
because it corrected a relative path that is not the cause (#863 folded
in). The gate named in the report pins `MODE=default-runner`, so its own
scenario never reaches the line that sources the named script — the
reported error line is not that gate's. The gates that do stage that
script into scratch trees are `verify-auto-release-specs-fallback.py`
(Gate 91) and `verify-gate-106.py`. Because the summary table shows every
gate passing, the stated next step is to capture *which subprocess prints
the line*, and only then decide between fixing a real defect and
attributing or suppressing an expected negative-case message.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Attribute any line the suite prints (Priority: P1)

A maintainer runs the whole gate suite before pushing. The run prints an
error line. Today that line can appear with nothing tying it to a gate:
the suite shows a gate's captured output only when that gate *fails*, so a
line emitted by a passing gate — or by a passing gate's own scratch
subprocess — arrives on the terminal with no name attached. The maintainer
is left guessing which of ~60 gate invocations produced it, and the natural
guess (the gate whose name appears inside the message) was wrong in this
very report.

After this feature, every line the suite displays carries the identity of
the gate invocation that produced it — the same identity the summary table
uses — so the maintainer reads the emitter off the run instead of
bisecting the suite by hand.

**Why this priority**: Without attribution nothing else in this feature can
be decided. The maintainer's own triage names capture as the next step, and
two fix attempts have already been closed unmerged for acting on a guessed
emitter. Attribution is also the whole of the delivered value on its own:
it converts an unexplained line into a located one.

**Independent Test**: Run the full suite with a gate deliberately made to
write a distinctive line to its own stderr while still exiting 0. Confirm
the run names that gate beside that line, and that the name matches the
gate's row in the summary table.

**Acceptance Scenarios**:

1. **Given** a suite run in which one passing gate writes a line to
   stderr, **When** the run completes, **Then** that line is displayed
   with the emitting gate's identity attached, and the identity is
   byte-identical to that gate's label in the summary table.
2. **Given** a suite run in which a passing gate's *child* process (a
   scratch `bash` step it invokes) writes to stderr, **When** the run
   completes, **Then** the line is still attributed to the gate
   invocation that owns that child, not left bare.
3. **Given** a suite run under parallel workers where two gates write to
   stderr at overlapping times, **When** the run completes, **Then**
   neither gate's lines are interleaved into the other's attribution
   block.
4. **Given** a suite run in which no gate writes anything unexpected,
   **When** the run completes, **Then** the only unattributed text is the
   suite's own header, per-gate status lines, summary table and totals
   line.

---

### User Story 2 - Disposition the reported line (Priority: P2)

With attribution in place, the maintainer re-drives the run that produced
`…/_shared/auto-release-container-evidence-decision.sh: No such file or
directory`, reads off the gate invocation that emitted it, and resolves it
according to what it actually is:

- If a gate is reaching for a fixture file that is genuinely absent from
  the tree it staged, the gate is not proving what its name claims and
  must fail rather than pass with a stderr line.
- If the line is an expected message from a gate's own negative-case or
  mutation fixture — a scenario that deliberately runs a step with a file
  missing — it is attributed or suppressed at its source, with the reason
  recorded where the next maintainer meets it.

**Why this priority**: This is the symptom the requester reported. It
depends on US1 for its evidence, and the two candidate dispositions lead to
different changes, which is exactly why capture must come first.

**Independent Test**: Run the suite and confirm the reported message either
no longer appears at all, or appears with its emitting gate named and its
expectedness stated in the same output — and that in neither case does a
maintainer have to read a gate's source to know which it is.

**Acceptance Scenarios**:

1. **Given** the reported message is traced to a gate whose staged tree is
   genuinely missing the file, **When** that gate runs, **Then** the gate
   exits non-zero and names the missing file and the tree it expected it
   in.
2. **Given** the reported message is traced to a deliberate negative-case
   fixture, **When** that gate runs and passes, **Then** the message is
   either withheld with the rest of that gate's passing output or shown
   with both its gate's identity and a statement that it is expected.
3. **Given** the suite is run ten times with no change to the tree,
   **When** the runs complete, **Then** every run reports the same
   per-gate verdicts.

---

### User Story 3 - Keep a gate's verdict and its output from disagreeing (Priority: P3)

The report's most corrosive detail is not the error line — it is that the
same run's summary table showed the named gate *passing*. A suite whose
printed verdict and printed output can disagree cannot be used as evidence,
which is the failure mode the constitution's "A Green Check Means What It
Says" principle names. After this feature, a run cannot end with an error
line ascribed to a gate the table reports as green, and no two gate
invocations can appear in the table under one identity, which is the other
way a FAIL and a PASS can be read as the same row.

**Why this priority**: It generalises the specific defect into a property
the suite keeps, so the next instance of this class is caught by the suite
rather than by a maintainer noticing an odd line. It is last because it is
worth nothing until US1 makes attribution exist.

**Independent Test**: Construct a run in which two invocations would share
a display identity and confirm the suite refuses rather than printing two
rows under one name; separately confirm a gate whose fixture set has
drifted from what its subject needs is reported as failing, not passing.

**Acceptance Scenarios**:

1. **Given** two gate invocations that would resolve to the same display
   identity, **When** the suite runs, **Then** it fails loudly naming the
   collision instead of printing two rows under one name.
2. **Given** a gate whose staged fixture set no longer matches what its
   subject step reaches for, **When** the suite runs, **Then** that drift
   is reported as a failure.
3. **Given** the same gate set run serially and in parallel, **When** both
   runs complete, **Then** their per-gate pass/fail verdicts are identical.

---

### Edge Cases

- A gate produces no output at all: attribution must report "no output"
  rather than silently dropping the gate's row.
- A gate's grandchild process writes to stderr after the gate itself has
  exited: the run must not end with a line no gate owns. Either the line
  is still attributed to the invocation that spawned it, or the suite
  reports that an unowned line was seen.
- A gate that genuinely fails: its full output must remain shown in
  full, immediately, exactly as it is today — attribution must not reduce
  what a failure shows.
- The same script invoked twice with different arguments (the suite
  already does this deliberately): each invocation is a separate identity
  and a separate attribution block.
- A very large output from one gate: attribution must not make the run
  unreadable, and must not hide a failure's output behind a passing
  gate's volume.
- The `--jobs 1` path carries a documented contract of byte-identical
  output to the pre-parallel script; a change to what a passing gate
  prints has to either honour that contract or retire it deliberately.
- A run interrupted part-way: whatever was already attributed stays
  attributed; no line is re-ascribed to a different gate.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every line of output the suite displays MUST be attributable
  to exactly one gate invocation, identified by the same label that
  invocation carries in the summary table — with the sole exception of the
  suite's own framing text (header, per-gate status lines, table, totals).
- **FR-002**: The suite MUST NOT display any gate-produced text without
  that attribution, including text produced by a gate that passed and text
  produced by a child process a gate spawned.
- **FR-003**: A gate that passes MUST NOT have output that reads as a
  failure emitted bare. Such output is either withheld together with the
  rest of that gate's passing output, or shown with its gate's identity
  attached.
- **FR-004**: A maintainer MUST be able to obtain a passing gate's full
  captured output from a single suite run, without re-invoking that gate
  on its own. [NEEDS CLARIFICATION: is this a new opt-in mode, or a change
  to what the default run prints? The `--jobs 1` path documents a contract
  of byte-identical output to the pre-parallel script, so changing the
  default retires that contract deliberately.]
- **FR-005**: The reported message
  (`…/_shared/auto-release-container-evidence-decision.sh: No such file or
  directory`) MUST be traced to the gate invocation that emits it, and the
  evidence MUST name that invocation and the scenario within it — not a
  gate inferred from the file name in the message.
- **FR-006**: Where the traced message is a gate reaching for a file
  genuinely absent from the tree it staged, that gate MUST fail and name
  both the missing file and the tree it expected it in, rather than emit
  the message and report a pass.
- **FR-007**: Where the traced message is an expected message from a
  gate's own negative-case or mutation fixture, it MUST be attributed or
  suppressed at its source, and the reason recorded at that source.
  [NEEDS CLARIFICATION: suppress at the source so the line stops being
  produced, or keep it visible with attribution and an "expected" marker?
  Suppression yields a quieter run; keeping it visible preserves a signal
  a maintainer may want when a fixture stops behaving.]
- **FR-008**: The suite MUST report the same per-gate pass/fail verdicts
  for the same gate set and unchanged tree, both across repeated runs and
  between serial (`--jobs 1`) and parallel (`--jobs N>1`) execution.
- **FR-009**: Each gate invocation the suite runs MUST have a display
  identity distinct from every other invocation in the same run. If two
  invocations would share one, the suite MUST fail loudly naming the
  collision rather than print two rows under one name.
- **FR-010**: A gate whose staged fixture set has drifted from what its
  subject reaches for MUST be reported as failing rather than passing.
  [NEEDS CLARIFICATION: does this feature cover only the gates named in
  the report (Gate 91 and Gate 106), or every gate in the suite that
  stages fixtures into a scratch tree? The narrow reading fixes the
  reported instance; the broad reading makes the class unrepeatable but is
  a materially larger change.]
- **FR-011**: A failing gate's output MUST continue to be displayed in
  full, at the moment its result is known, with no reduction in what is
  shown today.
- **FR-012**: The suite MUST NOT end a run reporting a gate as passing
  while also displaying an error line attributed to that same gate; such a
  state MUST be reported as a suite failure naming the gate.
- **FR-013**: Every failure branch this feature introduces MUST be
  exercised by a checked-in fixture, so the gate that enforces it can be
  shown to fail its own subject.

### Key Entities

- **Gate invocation**: one (script, arguments) pair the suite runs as its
  own process. The unit everything here attributes to; two invocations of
  the same script with different arguments are two invocations.
- **Gate identity**: the display name an invocation carries. Must be the
  same string in the live status line, the attribution block, the summary
  table and the timing cache, and unique within a run.
- **Captured output**: everything an invocation and its descendants wrote
  to stdout and stderr, held against that invocation's identity rather
  than merged into the run's stream.
- **Run verdict**: the per-gate pass/fail set the suite reports, plus the
  totals line. Must agree with the displayed output and be independent of
  worker count.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any line of output a suite run displays, a maintainer
  can name the emitting gate invocation from that same run's output, with
  no further runs and no reading of gate source.
- **SC-002**: Ten consecutive full-suite runs on an unchanged tree report
  identical per-gate verdicts — zero gates that pass in one run and fail
  in another.
- **SC-003**: Zero occurrences, across those ten runs, of a displayed
  error or diagnostic line whose emitting gate is unnamed.
- **SC-004**: The specific message the report names either appears zero
  times, or appears only with its emitting gate named and its expectedness
  stated in the same output.
- **SC-005**: Removing a required fixture file from any gate covered by
  FR-010 causes that gate to be reported FAIL; it is reported PASS in zero
  such trials.
- **SC-006**: A serial run and a parallel run of the same gate set report
  identical per-gate verdicts.
- **SC-007**: Zero runs end with a gate reported as passing while an error
  line attributed to that gate is displayed.
- **SC-008**: A maintainer who sees an unexplained line resolves it to its
  gate in one run, replacing the multi-run bisection that has so far
  consumed two closed-unmerged attempts.

## Assumptions

- The single local entry point stays `python .github/scripts/run-local-gates.py`,
  and the set of gates it runs and the subject each gate checks are
  unchanged by this feature. This is about what the suite *reports*, not
  about what it checks.
- "Attributable" means named by the same identity the summary table uses.
  A run that prints a temp path or a scenario name but not a gate identity
  does not satisfy it, because the reported confusion came precisely from
  reading a file path as a gate name.
- The gate named in the report is not the emitter. The spec treats the
  maintainer's triage as the current best evidence and requires FR-005's
  capture to confirm or refute it, rather than assuming either.
- The cwd/relative-path race in the original report is a hypothesis, not a
  finding: the suite's own documentation records an audit concluding no
  gate calls `os.chdir` and every gate uses a freshly minted scratch
  directory. The feature therefore does not assume a race exists, and
  FR-008's determinism requirement holds whether or not one is found.
- The machine-local timing cache is a scheduling hint only; changing or
  discarding it must not change any verdict, so it is out of scope except
  as an input FR-008 must hold across.
- Expected negative-case output from a gate's own fixtures is legitimate
  and must not be eliminated by making fixtures weaker; only its
  presentation is in scope.
- The behaviour under test runs locally and in CI through the same
  invocations, so evidence for this feature can be gathered locally
  without a live Actions run.
