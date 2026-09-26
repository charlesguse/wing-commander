# Research: Composite Test Harness Gate Discovery

Input: spec.md's own Clarifications section already resolved FR-001,
FR-011, and FR-012 (option (b): `.github/scripts/` stays the single
discovery root; the three existing harnesses stay put; the enforcement
check's subject is `run-tests.sh` and standalone `verify-*.py`/`verify-
*.sh` at any depth under `.github/actions/`, minus `_shared/`). No
`[NEEDS CLARIFICATION]` marker remains in spec.md. The decisions below fix
the concrete shapes — which file gains which function, what a new gate is
named and numbered, where the one canonical explanation lives — that
tasks.md needs before it can write file-level tasks.

## D1: Four of the spec's fourteen requirements are already true; verify, do not re-implement

**Decision**: FR-002 (composite harnesses run locally with CI's arguments),
FR-003 (an unwired composite harness is reported as orphaned), FR-005
(the local/CI parity check covers composite harnesses), and FR-008 (the
PR-time path filter already triggers on an edit to `.github/actions/**` or
`.github/scripts/**`) require no source change. Confirmed by reading the
shipped code, not by inspection alone (spec.md's own Independent Test
standard):

- `wc_gate_registry.gate_scripts()` already globs
  `.github/scripts/*/run-tests.sh` — every immediate subdirectory of
  `.github/scripts/`, not a named list — so `dispatch-and-wait-tests/`,
  `size-path-backstop-tests/`, and `stage-findings-tests/` (today's three
  composite harnesses, per their own header comments) are already
  discovered, already appear in `pr_time_gates()`/`pr_time_invocations()`
  when `lint-workflows.yml` names them, and already run through
  `run-local-gates.py` with whatever arguments CI passes (FR-002).
  `invocations()` (Gate 10's forward direction) already reports any of the
  three as orphaned the same way it reports an orphaned `verify-*` script,
  because it iterates `gate_scripts()` (FR-003).
- `verify-gate-wiring.check_local_runner_parity()` iterates
  `pr_time_gates()` — the same set — so a composite harness CI runs that
  the tokenizer cannot reproduce already fails today's Gate 10, not only
  after this feature (FR-005).
- `git grep -n 'paths:' -A2 .github/workflows/lint-workflows.yml` shows
  `.github/actions/**` and `.github/scripts/**` both already listed
  (lines 23/28 as of this plan). FR-008 is a verification line in
  quickstart.md, not a task.

**Rationale**: The spec's own Assumptions section states this
("`lint-workflows.yml` already lists ... FR-008 is expected to be
satisfied already and needs verification rather than new plumbing"; "the
three composite harnesses ... pass today and are correctly wired"), and
re-implementing an already-true requirement risks a second, subtly
different definition of "orphaned" or "reproducible" competing with Gate
10's existing one — the opposite of FR-001's single-source-of-truth goal.

**Alternatives considered**: Writing new code for FR-002/003/005 "to be
sure" — rejected; the existing functions are already exercised by real
CI runs against the real tree every day, which is stronger evidence than
a fixture written to simulate the same thing would be. What genuinely has
no fixture today is Gate 10 running *at all* with a synthetic tree (it has
no `--self-test`) — that gap is closed in D6, not by duplicating
`gate_scripts()`.

## D2: The new enforcement gate is a separate script, not a widened `gate_scripts()`

**Decision**: A new script, `.github/scripts/verify-actions-no-gate-
scripts.py`, answers a second, disjoint question — "does anything under
`.github/actions/` look like a test harness or standalone gate script" —
via a new `wc_gate_registry.unsupported_actions_scripts(root=".")`
function. `gate_scripts()` itself is untouched: it still walks
`.github/scripts/` only, so `run-local-gates.py`'s notion of "what is a
gate to run" never widens, which is what FR-001 requires ("`.github/
scripts/` MUST remain the single discovery root").

`unsupported_actions_scripts()` walks exactly `<root>/.github/actions`
(never a broader recursive scan from `<root>`, per the Constraints section
of plan.md) and returns every path matching `run-tests.sh` or `verify-
*.py`/`verify-*.sh` at any depth, excluding anything under `.github/
actions/_shared/`. This is the same "mechanical convention, not a list"
posture `wc_gate_registry.py`'s own docstring already states for the
positive discovery rule — applied here as the negative rule FR-012/FR-014
describe.

**Rationale**: `verify-actions-layer-invariants.py` already exists and
scans every `action.yml` under `.github/actions/**`, but for a different
question entirely — does a composite's *content* read `github.event.*`/
`vars.*`/invoke an agent. That is a content invariant; this feature's rule
is a *placement* invariant (does a file of this shape exist at this path
at all). Folding the two into one script would make a single failing run
ambiguous about which invariant broke, and would force one self-test
fixture set to cover two unrelated concerns. Keeping `gate_scripts()`
itself pure (one discovery root) and adding a second, narrowly-scoped
function it does not call is what keeps FR-001's "single discovery root"
sentence true of the code, not just of the new gate's intent.

**Alternatives considered**: Extending `verify-actions-layer-invariants.py`
with a fourth check — rejected for the reason above. Extending
`gate_scripts()` to also glob `.github/actions/` — rejected outright; that
is precisely the widening FR-001 forbids, since it would make `run-local-
gates.py` try to *execute* whatever it found there rather than fail a gate
that says such a file must not exist.

## D3: Gate number and wiring

**Decision**: The new gate is wired into `lint-workflows.yml`'s existing
PR-time job as `Gate <N> — no test harness or standalone gate script lives
under .github/actions/` plus a `Gate <N> self-test` step, following every
other gate's two-step convention (live check, then `--self-test` against
in-source fixtures). `<N>` is the next unclaimed gate number in `lint-
workflows.yml` at implementation time — 99 as of this plan (the highest
number present is Gate 98) — re-verified against `main` immediately before
landing, since concurrent specs may claim a number first (constitution:
"different specs run in parallel").

**Rationale**: Matches this repository's own numbering convention
(sequential, assigned at the point a gate is wired, never pre-reserved)
and keeps the new check discoverable by `wc_gate_registry.invocations()`
the moment its `run:` line exists, with no separate registration step.

**Alternatives considered**: A named-only gate with no number (like the
existing "E2E provisioning single-home gate" a few steps below Gate 10) —
rejected only as a style preference; either form satisfies FR-001/006, but
a numbered gate matches the majority convention and keeps this feature's
gate cross-referenceable from a lifecycle issue the way "Gate 47" already
is from CLAUDE.md.

## D4: Reverse-direction `.github/actions/` check reuses the existing substring technique — self-checkout resolution comes for free

**Decision**: `wc_gate_registry.py` gains
`referenced_actions_script_paths(root=".")`, a sibling of the existing
`referenced_script_paths()` with one line changed — the regex anchors on
`\.github/actions/[A-Za-z0-9_./-]+` instead of `\.github/scripts/...` —
reusing the same `_run_text()` comment-stripped extraction.
`verify-gate-wiring.py`'s `main()` calls both and reports a failure for
either whose matched path does not exist on disk, in the same loop shape
it already uses for `.github/scripts/` paths.

This closes FR-004 (a `.github/actions/` path a `run:` block names but
that is missing on disk is reported) and FR-013 (the self-checkout prefix
`./.wing-commander-pipeline/.github/actions/<X>` resolves to the same file
as `./.github/actions/<X>`) **with the same mechanism, not two**: the
regex matches the substring starting at `.github/actions/`, so a prefix
before it (`./`, `./.wing-commander-pipeline/`) is simply not part of the
match — both spellings in a `run:` block yield the identical repo-relative
string `.github/actions/_shared/auto-release-verdict.sh`, which either
exists once or is missing once. There is no second, separate "resolve the
prefix" step to write or to get wrong, because the existing pattern never
captured the prefix in the first place (verified against
`.github/workflows/auto-update-spec-kit.yml`, which already names three
`_shared` composites via the `./.wing-commander-pipeline/` form today —
the exact case FR-013's edge case describes).

**Rationale**: `.github/scripts/`'s reverse check already has this
property today (unremarked, because nothing there is reached through the
self-checkout prefix yet); mirroring its exact technique rather than
writing a bespoke prefix-stripping function means FR-013 is proven true by
construction, not by a separate normalisation routine that could itself
drift from the forward walk's rooting rule.

**Alternatives considered**: An explicit `_strip_self_checkout_prefix()`
helper that rewrites `./.wing-commander-pipeline/...` to `./...` before
matching — rejected; it would be a second definition of "which prefixes
are equivalent" alongside the regex's own implicit one, and CLAUDE.md's
single-home rule argues against a second mechanism doing the same job the
substring match already does for free.

## D5: Gate identity moves into `wc_gate_registry.py` as `gate_label()`

**Decision**: `run-local-gates.py`'s inline `label_of(script, args)`
(`os.path.basename(script) + " " + " ".join(args)`) is replaced by a new
`wc_gate_registry.gate_label(script, args, root=".")`, computed from the
script's path *relative to `.github/scripts/`* (e.g.
`dispatch-and-wait-tests/run-tests.sh`, not `run-tests.sh`) joined with
its arguments. `run-local-gates.py` imports and calls it everywhere
`label_of` was used (the final table, the timing cache key, the `--jobs`
filter token, the live-run PASS/FAIL lines).

**Rationale**: FR-007 requires uniqueness "across the whole gate
population... in [the local runner's] output, its timing cache, its
filter arguments, or the wiring gate's attribution of invocations to
files" — four call sites, one fix. Placing the function in
`wc_gate_registry.py` rather than patching `run-local-gates.py` in place
means the identity scheme has one home a future consumer (a second local
runner, a report generator) reuses rather than reimplements, and it sits
beside the other functions that already answer "what distinguishes one
gate from another" (`gate_scripts()`, `invocations()`). `verify-gate-
wiring.py` already attributes invocations by full script path (never
basename), so it needs no call-site change — only the shared function it
will use for its own new self-test fixtures (D6) benefits from living in
one place.

**Alternatives considered**: A suffix disambiguator only when a collision
is detected (e.g. append the parent directory only for colliding
basenames) — rejected; it produces a label whose shape depends on what
else happens to exist in the tree, so the same harness's identity could
change the day an unrelated harness is added elsewhere, which breaks the
timing cache's merge-by-label contract (`run-local-gates.py`'s own
docstring: "a filtered run ... must not evict the timings of the other
fifty-four"). An always-qualified relative path never changes for a given
harness regardless of what else exists.

## D6: `verify-gate-wiring.py` gains `--self-test`; this is where FR-010's fixtures live

**Decision**: `verify-gate-wiring.py` gains a `--self-test` flag (it has
none today — confirmed: Gate 10 runs live against the real tree only,
unlike every `verify-*.py` this feature's other changes touch). Its
`main()` is refactored so every check function already takes an optional
`root` (most already do, via `wc_gate_registry`'s existing `root="."`
parameters); `--self-test` builds several tiny fixture trees under
`tempfile.mkdtemp()` (the same `_write`-into-tempdir shape
`verify-actions-layer-invariants.py` already uses) and asserts:

  - a fixture composite harness at `.github/scripts/<name>-tests/run-
    tests.sh` with no invoking workflow reports as orphaned (FR-003,
    already-true behaviour from D1 — this is the fixture that proves it,
    not new logic);
  - a fixture `run:` block naming a `.github/actions/` script path with no
    file on disk reports as missing (FR-004, D4);
  - a fixture pair of `run:` blocks — one `./.github/actions/_shared/x.sh`,
    one `./.wing-commander-pipeline/.github/actions/_shared/x.sh`, same
    file existing once — reports **one** file, not a spurious second
    "missing" entry (FR-013, D4);
  - a fixture `run-tests.sh` under `.github/actions/` outside `_shared/`,
    invoked once and NOT wired to `lint-workflows.yml`, still reports
    correctly as an ordinary orphan by Gate 10's existing forward check —
    proving Gate 10 and the new placement gate (D2) do not double-report
    or contradict each other for the same file (spec.md Edge Case: "A
    `run-tests.sh` under `.github/actions/` that no workflow invokes
    either... the failure must name placement rather than orphan-hood");
  - a fixture pair of harnesses sharing the basename `run-tests.sh` under
    two different `.github/scripts/<name>-tests/` directories produce two
    distinct `gate_label()` identities (FR-007, D5).

**Rationale**: Principle VIII requires every failure branch a gate ships
to be exercised by a checked-in fixture, "not... a manual demonstration
during development." Gate 10 predates that principle's own ratification
(#158) and has run live-only ever since; this feature is the first to add
new failure branches to it, which is the forcing function to finally give
it the same fixture discipline every other gate already has, rather than
inheriting a live-only gate's blind spot for its own new code.

**Alternatives considered**: Proving the new branches by hand once during
implementation and recording it in the PR description — rejected
explicitly by both the spec (FR-010, SC-005) and the constitution
("evidence for that reviewer, not coverage for the next one").

## D7: One canonical explanation, carried by the new gate's docstring; the three harnesses point at it via Gate 47

**Decision**: The "why a composite's test harness lives under `.github/
scripts/<name>-tests/`, never beside the composite" explanation — both
reasons FR-009 requires (gate discovery reads only that root; test
fixtures stay out of the adopter-pinned composite directories,
constitution VII) — is written once, in `verify-actions-no-gate-
scripts.py`'s own module docstring, the enforcement gate that makes the
rule mechanical. `dispatch-and-wait-tests/run-tests.sh`, `size-path-
backstop-tests/run-tests.sh`, and `stage-findings-tests/run-tests.sh` each
replace their own version of this explanation with a single pointer
comment in the phrasing Gate 47 (`verify-comment-canonical-pointers.py`)
already recognises and resolves: `-- see verify-actions-no-gate-
scripts.py.` A bare `NAME.py` target already resolves under `.github/
scripts/` per Gate 47's own docstring (part (a), added in review #439 for
exactly this "pointer at a gate script's own docstring" shape), and part
(b)'s topic-overlap check is satisfied for free because the pointer sits
in a comment already discussing the same placement rule the target's
docstring states in the same words. The enforcement gate's own failure
message (FR-009's last sentence: "the enforcement gate's failure message
MUST point at the same canonical home") names its own file, which is
inherently the same home the pointers resolve to — no separate
cross-check needed.

**Rationale**: This is CLAUDE.md's "Shared logic has exactly one home"
rule applied to prose rather than shell/jq, and Gate 47 already exists,
already runs in the PR-time suite, and already validates exactly this
pointer shape — reusing it is strictly cheaper and more consistent than
inventing a second canonical-prose mechanism (a doc-comment convention
CLAUDE.md would then also need a paragraph for). Housing the prose in the
enforcement gate's own docstring rather than in CLAUDE.md keeps the
explanation beside the mechanism that makes it true, the same pattern
`wc_gate_registry.py`'s own "THE CONVENTION" docstring section already
sets for the positive discovery rule.

**Alternatives considered**: A new prose section in CLAUDE.md's "Shared
logic has exactly one home" — rejected; that section is about `run:`
blocks, jq programs, and shell helpers pasted across *workflows*, a
different kind of duplication than three files restating the same design
rationale in comments, and conflating the two would blur what CLAUDE.md's
existing section is a checklist for. Leaving each harness's prose as-is
and only adding the new gate — rejected outright; it is exactly the
"second copy... where a rounding fix would have had to land N times"
failure mode CLAUDE.md's own worked example warns about, and FR-009 names
it explicitly.

## D8: Fixtures for the enforcement gate itself

**Decision**: `verify-actions-no-gate-scripts.py --self-test` uses the
same in-tempdir `_write`/`FIXTURES` shape as `verify-actions-layer-
invariants.py`, covering: a `run-tests.sh` directly under `.github/
actions/<composite>/` (fails, names the path and the canonical location);
a `run-tests.sh` two levels deep, e.g. `.github/actions/<composite>/
tests/nested/run-tests.sh` (fails the same way — FR-012's "at any depth");
a standalone `verify-widget.py` and a standalone `verify-widget.sh` under
`.github/actions/<composite>/` (both fail); a helper script under
`.github/actions/_shared/` with a name that would otherwise match (e.g.
`.github/actions/_shared/run-tests.sh`) — NOT flagged, and pinned by its
own fixture so the carve-out cannot silently widen (spec.md Acceptance
Scenario 3, Story 2); a composite with no harness at all (clean pass); and
confirmation the walk is rooted at `<root>/.github/actions` specifically
by asserting a same-shaped violation placed outside that directory (e.g.
at repo root) is correctly ignored — proving the check cannot mistake an
unrelated tree for its subject.

**Rationale**: This is FR-010's list applied to the one gate that owns
FR-006/FR-012/FR-014 directly; D6 covers the fixtures that belong to Gate
10 instead (identity collisions, the reverse-direction and self-checkout
cases, and the orphan/placement non-interference case).

**Alternatives considered**: None — this is the same self-test shape
every sibling gate in this repository already uses; deviating would be
the novelty needing justification, not the reuse.

## D9: No change to `run-local-gates.py`'s WHAT IT DOES NOT RUN carve-out

**Decision**: `run-local-gates.py`'s existing exclusion of gates wired to
a workflow other than `lint-workflows.yml` (its docstring names `verify-
watchdog-run.sh` as the standing example) needs no new logic to also cover
a composite harness wired elsewhere. `pr_time_gates()` already filters by
`workflow in wfs` for `lint-workflows.yml` specifically, so a harness
wired only to some other workflow simply never enters the set — it is not
reported "missing," because the local runner never claimed to cover it.
Spec.md's Edge Case ("A harness wired to a workflow other than the PR-time
lint suite... must not be reported as missing from the local suite") is
satisfied by this existing filter; D6's self-test does not need a fixture
for it beyond confirming (by inspection of `pr_time_gates()`'s existing
behaviour, not new code) that the filter is unconditional on gate *shape*
(script vs. subdirectory harness) as well as gate *name*.

**Rationale**: Avoids writing a defensive fixture for a branch that
cannot exist given `pr_time_gates()`'s current implementation — a filter
by workflow membership, with no special case for harness vs. script.

**Alternatives considered**: none warranted; recorded to keep tasks.md
from generating a task for a gap that reading the code disproves.
