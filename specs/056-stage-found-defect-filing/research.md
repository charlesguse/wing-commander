# Research: Stage-Found Defect Filing Through a Deterministic Filing Step

Input: `spec.md` carries no `[NEEDS CLARIFICATION]` markers. The decisions
below are still recorded as research because the spec fixes *what* the
mechanism must do (FR-001..FR-033) without fixing several concrete shapes
the tasks stage needs settled before it can write file-level tasks. Each
entry is a decision this plan makes so implementation does not re-derive
it per stage.

## D1: "Seven stages" maps to six workflow files

**Decision**: The mechanism instruments six published stage workflows —
`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`,
`finalize.yml`. "Converge" (the seventh name in FR-001's list) has no
workflow file of its own: `implement.yml`'s single `implement` job already
runs the implement⟲converge cycle as one agent turn per call (its own
header comment: "Published stage — implement ⟲ converge, ONE iteration per
call"; `spec-meta.json`'s `stage` enum has no `converge` value). Findings
proposed during either phase of that one agent turn share the same
findings channel and are attributed `found-by:implement` — there is no
second workflow, job, or attribution surface to give "converge" that a
maintainer could tell apart from "implement".

**Rationale**: The architecture the spec is instrumenting already collapsed
these two names into one execution unit before this feature existed;
inventing a second attribution identity for a phase that produces one
agent turn, one final message, and one job would be attribution the
runtime cannot actually distinguish.

**Alternatives considered**: Splitting `found-by:implement` and
`found-by:converge` by which named phase inside the single agent turn
produced the finding — rejected because the agent's own prose does not
reliably self-report which phase it was in when it noticed something, and
FR-010 forbids deriving the fingerprint basis (which includes stage) from
that prose.

## D2: Findings channel marker for free-form stages

**Decision**: A free-form-final-message stage (`plan`, `tasks`,
`implement`, `finalize`) carries findings in a fenced block whose info
string is the literal `wing-commander-findings`, containing a JSON array
(possibly empty or absent — no block means zero findings):

    ```wing-commander-findings
    [{"title": "...", "what": "...", "evidence": {...}, "fingerprint_basis": {...}}]
    ```

The filing composite extracts this block from the `.result` field of the
last `type=="result"` entry in the stage's own `claude-execution-output.json`
(the same transcript file every stage already writes and uploads as the
`claude-execution-output` artifact per #312) — never a separate file, per
FR-006's "never a `findings/*.json` file" rule.

**Rationale**: A distinct, greppable info string lets the extraction step
use a plain regex/awk pass over the final message with no ambiguity
against the stage's other prose, and reuses the transcript file every
stage already produces instead of adding a second write surface for a
read-only stage to fail to have.

**Alternatives considered**: An HTML-comment marker (`<!-- wc-findings:
[...] -->`) — rejected, harder to keep valid JSON across an agent's own
line-wrapping of prose; a dedicated fenced-JSON block is the shape
Markdown renderers and `jq`/`sed` extraction both already handle cleanly.

## D3: Findings channel for schema-validated stages

**Decision**: `intake` and `clarify` (the two stages that already pass
`--json-schema` to `claude-code-action`) gain one optional property,
`findings`, on their existing schema's top-level object: an array,
default/absent meaning zero findings. No fenced block is added to these
two stages' final message (FR-007's "MUST NOT be asked to emit a fenced
block as well").

**Rationale**: `plan`/`tasks`/`implement`/`finalize` have no schema to
extend (confirmed: none of the four pass `--json-schema`; their
deliverable is verified by file/commit/PR state, not by parsing the
transcript's JSON), so the two channel shapes split exactly along the
existing schema-validated/free-form line already present in the six
workflows, matching FR-006 exactly.

## D4: The finding schema is a new checked-in JSON file

**Decision**: `.github/schemas/stage-finding.schema.json` is the checked-in
authority FR-008 requires. This is a new directory: the repository's only
two prior `.schema.json` files (`specs/002-plan-stage/contracts/spec-meta.schema.json`,
`specs/053-e2e-scratch-provisioning/contracts/readiness-report.schema.json`)
are spec-scoped documentation, never loaded at runtime by any workflow or
gate. This feature's schema is cross-spec, permanent infrastructure (every
future stage run reads it), so it lives beside the workflows it governs
under `.github/`, not under a `specs/NNN-*/` directory that documents one
feature's history.

**Rationale**: Putting a runtime-loaded, permanent artifact under a
per-spec `specs/` directory would make it look like documentation of this
one feature rather than a piece of the pipeline every later run depends on.

**Alternatives considered**: Embedding the schema inline in the new filing
composite's `action.yml` as a heredoc — rejected; FR-008 says "checked-in
schema", and a schema a reviewer must diff out of a shell heredoc is a
schema a reviewer will stop diffing.

## D5: Validation is hand-written, not a third-party JSON Schema library

**Decision**: The composite's validation step is a small Python script
(`.github/scripts/verify-stage-finding-schema.py`, exposing a
`validate_finding(finding) -> (bool, reason)` used both by the runtime
step and by the FR-030 fixtures) that checks the required fields and types
`stage-finding.schema.json` declares, without a third-party JSON Schema
validator dependency.

**Rationale**: Matches this repository's existing pattern for the only
other runtime-checked structured shape (`verify-metrics-record-schema.py`
hand-checks the metrics record shape without a schema library), and avoids
introducing a new Python dependency into the runner image for one feature.
The checked-in `.schema.json` file stays the documented authority a
reviewer reads; the script is proven to match it by the FR-030 fixture
that feeds it every field the schema requires and confirms each omission
is caught.

## D6: Fingerprint formula

**Decision**: `fingerprint = sha256("<stage>|<file_path>|<gate_or_artifact_name>")`
over the three deterministic fields FR-010 names, lower-hex digest,
mirroring the watchdog's own `sha256sum` fingerprint idiom
(`fp=$(printf '%s|...' ... | sha256sum | cut -d' ' -f1)`). The finding
schema requires these three fields (plus title/what/evidence, which are
not part of the basis) so the fingerprint is computable without touching
the agent's prose.

**Rationale**: Reuses a formula shape this repository already has one
working, reviewed instance of (the watchdog), rather than inventing a
second hashing convention for the same kind of dedup key.

## D7: Dedup and cross-run linking reuse `durable-failure-issue`, extended

**Decision**: The promoted composite (D8) gains two new optional inputs,
`marker` and `state-scope` (`open` \| `all`, default `open` — unchanged for
existing callers that omit `marker`). When `marker` is set:
- the lookup step searches `--state all` instead of `--state open`, and
  additionally greps each candidate's body for the literal `marker` string
  (an HTML-comment fingerprint marker the caller embeds in the body, the
  same idiom the watchdog already uses: `<!-- wing-commander-finding:
  fingerprint=<hash> -->`);
- a match whose issue state is `open` behaves as today (comment, `commented`);
- a match whose issue state is `closed` creates a new issue whose body
  links the closed one (FR-012), `action-taken=created-linked-closed`;
- no match creates fresh, `action-taken=created`, exactly as today.

Existing callers (`auto-release.yml`, `auto-update-spec-kit.yml`) pass no
`marker` and see byte-identical behavior — the single-label, open-only
lookup FR-016 requires to stay unchanged.

**Rationale**: FR-016 requires promoting and reusing the composite, not
duplicating its find-or-create shape a second time, and explicitly permits
adding behaviour the composite lacks as long as existing consumers can
ignore the addition — this is exactly that: an opt-in input, ignored by
every caller that predates this feature.

**Alternatives considered**: Giving the filing step its own bespoke
fingerprint/dedup logic like the watchdog's (which does not call
`durable-failure-issue` at all) — rejected; that would create the second
copy of the find-or-create-under-a-dedup-label idiom FR-032's gate exists
to prevent, and the watchdog's divergence from the composite predates this
feature and is out of scope to unify.

## D8: The promoted composite is renamed to match the published naming convention

**Decision**: `.github/actions/_shared/durable-failure-issue/` moves to
`.github/actions/wing-commander-durable-failure-issue/` (not merely
`.github/actions/durable-failure-issue/`). Every other non-underscore
composite under `.github/actions/` carries the `wing-commander-` prefix
(20 of 20 checked); an underscore-prefixed directory is the only place the
prefix is currently dropped, and Gate 60's promotion-prevention check
already treats "no `wing-commander-` prefix" as one of the signals of an
unpromoted internal path.

**Rationale**: A promoted composite that keeps its unprefixed, internal-era
name is a naming inconsistency the next contributor has to notice by
reading the path rather than by the convention holding without exception.

**Consequence**: `DECLARED_HOMES["failure-issue"]` in
`verify-single-home-idioms.py` moves to the new path in the same change,
and both current call sites (`auto-release.yml`'s two `uses:` sites,
`auto-update-spec-kit.yml`'s one) are repointed at
`./.github/actions/wing-commander-durable-failure-issue` /
`./.wing-commander-pipeline/.github/actions/wing-commander-durable-failure-issue`
respectively, in the same PR (FR-016: "leaving no consumer on the internal
path and no second copy of the idiom anywhere").

## D9: The outstanding-task-item idiom is promoted out of `pr-conversation.yml`

**Decision**: A new published composite,
`.github/actions/wing-commander-outstanding-task-item/`, wraps the single
`gh issue comment "$ISSUE_NUMBER" --body "- [ ] $PHRASE — $ARTIFACT_URL"`
call `pr-conversation.yml` performs inline today (its own header comment
calls this "the ONE shared mechanism every SpinOffArtifact posts through").
`pr-conversation.yml` is repointed at the new composite in the same
change; the new filing composite (D10) is the second caller.

**Rationale**: CLAUDE.md's shared-logic rule ("before pasting a run: block
... into a second workflow, move it instead") applies the moment this
feature's filing step needs the same idiom `pr-conversation.yml` already
has — pasting a second literal `gh issue comment ... "- [ ] ..."` would be
exactly the invisible-until-divergent-fix copy the rule exists to prevent.
It must be a non-underscore, `wing-commander-`-prefixed composite (not
`_shared/`) because its second caller is itself a published composite
resolved by published stage workflows, and Gate 60's promotion-prevention
check already forbids a published composite from resolving anything under
`_shared/`.

**Alternatives considered**: Leaving `pr-conversation.yml`'s inline step as
the only instance and having the new filing composite call
`pr-conversation.yml`'s step directly — not possible; composite actions
cannot invoke a step embedded in a workflow file, only another composite.

## D10: The filing composite

**Decision**: One new published composite,
`.github/actions/wing-commander-stage-findings/`, is the thing each of the
six stage jobs invokes once, after that stage's existing deterministic
read-back. It performs, in order: enable check (no-op if disabled) →
extract raw findings per the stage's channel shape (D2/D3) → validate each
against the schema (D5) → cap enforcement, dropping the excess in proposal
order (D11) → per surviving finding: fingerprint (D6), then
`wing-commander-durable-failure-issue` with `operation: report`,
`label: <label-prefix>:<stage>`, `marker` set to the finding's fingerprint
marker → on `created`/`created-linked-closed`/`commented`, call
`wing-commander-outstanding-task-item` if a lifecycle issue number was
passed in (FR-017/FR-019) → emit a job-summary block naming counts
(proposed/filed/appended/dropped, with drop reasons) per FR-020, and a
step output the stage's own summary step folds into whatever a maintainer
already reads (FR-021).

The composite itself runs `continue-on-error: true` is not sufficient on
its own (a composite's internal `gh` failures need to be caught inside
it); its called-with step in each stage workflow additionally sets
`continue-on-error: true` and `if: ${{ !cancelled() && steps.<read-back>.outcome != 'skipped' }}`
so a cancelled run or a run whose agent step never produced a read-back
does not attempt to file (FR-024).

**Rationale**: One composite gives FR-016/FR-032's single-home rule a
second worked instance for this feature's own filing idiom (proposal →
validate → fingerprint → dedup/file → cross-link is identical work in all
six stages; only the extraction step's channel shape differs, which the
composite branches on via its `channel-mode` input rather than needing six
copies of the surrounding logic).

## D11: Cap ordering

**Decision**: When proposed findings exceed the cap, the first `cap`
findings in the order the agent proposed them (array order in the channel)
are kept; the rest are dropped with reason `cap exceeded`.

**Rationale**: The spec requires only that the ordering be the code's own
and not the agent's choice (FR-013); proposal order is the simplest such
ordering, needs no secondary sort key, and does not privilege one finding
over another by a property (e.g. alphabetical by title) that would read as
the code exercising undisclosed judgment about which findings matter more.

## D12: Enable/label/cap inputs added identically to all six stages

**Decision**: Each of the six stage workflows' `workflow_call.inputs`
gains exactly three new inputs in this release: `findings-filing-enabled`
(boolean, default `true` for `implement.yml`/`finalize.yml`, `false` for
the other four — FR-001), `findings-label-prefix` (string, default
`found-by`), `findings-cap` (number, default `3` — the Assumptions
section's default). Each of the six `wing-commander-<N>-*.yml` wrapper
workflows passes these through as declared inputs (never ambient
repository state, per Principle VII and FR-029) — a future adopter
overriding a stage's filing behaviour edits the wrapper, not the published
stage.

**Rationale**: This is the literal reading of FR-001a/FR-029: the surface
moves exactly once, identically shaped, regardless of which stages default
on. The prompt paragraph (FR-003) and the filing step invocation (D10) are
likewise present in all six stage job definitions unconditionally; only
the composite's own enable check (D10) makes the five off-by-default
stages inert, so FR-031's gate can check for "paragraph and step both
present" uniformly across all six without special-casing the default.

## D13: New gates

**Decision**: Two new gate scripts, registered in `lint-workflows.yml` and
therefore in `run-local-gates.py`:
- `verify-stage-findings-wiring.py` (FR-031): for each of the six stage
  workflows, fails if the findings paragraph is present in the agent
  step's prompt without the `wing-commander-stage-findings` step present
  in the same job, or vice versa — checked for all six regardless of that
  stage's `findings-filing-enabled` default.
- `verify-single-home-idioms.py` gains a new `DECLARED_HOMES` entry for
  `wing-commander-stage-findings` itself and its `outstanding-task-item`
  companion (FR-032), and its existing `failure-issue` entry is repointed
  per D8 — one gate covering both "second copy appears" and "a caller
  still reaches the old `_shared/` path", reusing Gate 60's existing
  promotion-prevention shape rather than writing a third gate for the same
  concern.

**Rationale**: FR-031 and FR-032 name two different failure shapes (prompt
without step / step without prompt, vs. a second copy of an idiom); this
repository's existing Gate 60 already carries the second shape's exact
mechanism (`DECLARED_HOMES` + `check_promotion`), so extending it is
"adding the single-home check to the nearest existing gate" per CLAUDE.md,
rather than a new gate duplicating Gate 60's own logic.

## D14: FR-030 fixtures live beside the composite they exercise

**Decision**: `.github/actions/wing-commander-stage-findings/tests/` (a
`run-tests.sh` harness plus one fixture file per required branch:
malformed proposal, dedup-hit-open, dedup-hit-closed, cap-overflow,
API-failure, no-findings, fenced-block channel, structured-array channel
with the array present, and structured-array channel with the array
omitted) drives the composite's extraction/validation/cap logic directly
against `verify-stage-finding-schema.py`, without invoking `gh` (an
injectable/stubbed `gh` shim covers the dedup and API-failure branches,
the same technique the metrics-summary gate's fixture already uses to
exercise a `run:` block outside a live workflow).

**Rationale**: Matches Principle VIII's requirement that every shipped
failure branch have a checked-in fixture, and keeps the fixtures next to
the composite so a future edit to the composite's branching is caught by
a colocated test rather than a distant gate script guessing at its shape.
