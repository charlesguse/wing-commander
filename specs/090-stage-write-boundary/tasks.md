# Tasks: No Stage Is Left Holding Work It Cannot Do — The Implement Stage's Write Boundary

**Input**: Design documents from `/specs/090-stage-write-boundary/`
(plan.md, research.md, data-model.md, quickstart.md, contracts/
write-boundary-mechanism.md, contracts/write-boundary-gate.md)

**Tests**: This feature's verification is a deterministic gate script with
checked-in fixtures (Constitution VIII, FR-020), not a conventional test
suite — matching this repository's existing `verify-*.py` convention.
Gate/fixture tasks are listed inline with the implementation task they
verify rather than in a separate TDD phase.

**Gate numbering**: the highest gate number wired into
`.github/workflows/lint-workflows.yml` as of this branch's Setup phase
(T001) was Gate 125 (`grep -oE "Gate [0-9]+" .github/workflows/lint-workflows.yml | sort -t' ' -k2 -n -u | tail -1`),
so this feature's gate is provisionally **Gate 133**. Per spec
059-converged-means-tasks-done's own precedent (its Gate 81 reservation was
overtaken twice by other specs landing first, ending as Gate 99): re-check
this reservation at T001 and, if `main` has since claimed Gate 133, renumber
every "Gate 133" reference below (the `GATE_PREFIX` constant and docstring
in `verify-write-boundary.py`, the step name/self-test in
`lint-workflows.yml`, and every mention in this file) to the next free
number before starting Phase 3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (the stage knows what it may write before it tries), US2
  (work beyond reach is routed, not resurfaced), US3 (the loop's convergence
  verdict is honest about it), US4 (the rule is not re-derived for the next
  unwritable path)

## Path Conventions

GitHub Actions reusable-workflow pipeline, no `src`/`tests` split. Every
path below is relative to the repository root.

**Shared subject warning** (mirrors spec 059's tasks.md): Phases 4 and 5
both edit the SAME two steps in `.github/workflows/implement.yml` (`Read
back cycle outcome`, `Read back retry outcome`) plus `Consolidate final
outcome`, because the plan's decision table (data-model.md) is one coherent
unit split across FR groups, not independent code paths. Land and checkpoint
each phase in order rather than working US2 and US3 concurrently against
those steps.

---

## Phase 1: Setup

- [x] T001 Confirm the gate-number reservation above is still accurate:
  `grep -oE "Gate [0-9]+" .github/workflows/lint-workflows.yml | sort -t' ' -k2 -n -u | tail -1`
  must show Gate 125. If a higher gate now exists, shift every "Gate 133"
  reference in this file, and in the files T012/T034/T035 create, to the
  next free number before starting Phase 3.

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: the single declared `no-write-paths` definition (FR-003), the
per-task classification composite (consumed by US2 and US3), and the shared
fingerprint helper (consumed by US2's routing call and US3's finalize
lookup) all have to exist, callable in isolation, before any user-story
phase wires them into `implement.yml`'s or `finalize.yml`'s actual flow.

- [x] T002 [P] `.github/workflows/implement.yml`: add two new optional
  `workflow_call` inputs to the `inputs:` block, next to `findings-cap`
  (~line 229-235): `no-write-paths` (`type: string`, `required: false`,
  `default: ".claude/"`, description per contracts/write-boundary-mechanism.md
  §1 — "Comma-separated path prefixes this run's agent may not target with
  Edit/Write (FR-002, FR-019)") and `write-boundary-label-prefix` (`type:
  string`, `required: false`, `default: "route-out-of-boundary"`,
  description noting it is distinct from `findings-label-prefix` by design —
  see research.md D4). This is the one declaration FR-003 requires; every
  other site below reads `${{ inputs.no-write-paths }}` / `${{
  inputs.write-boundary-label-prefix }}`, never a second literal default.
- [x] T003 [P] `.github/workflows/finalize.yml`: add the same
  `write-boundary-label-prefix` optional input (identical default,
  identical description) to its `inputs:` block. `finalize.yml` gets no
  `no-write-paths` input — it never classifies a task, only looks up an
  already-filed one by fingerprint (contracts/write-boundary-mechanism.md
  §1).
- [x] T004 [P] `.github/workflows/wing-commander-5-implement.yml`: wire
  `no-write-paths: ${{ vars.WING_COMMANDER_IMPLEMENT_NO_WRITE_PATHS ||
  '.claude/' }}` and `write-boundary-label-prefix: ${{
  vars.WING_COMMANDER_WRITE_BOUNDARY_LABEL_PREFIX || 'route-out-of-boundary'
  }}` into the `uses: ./.github/workflows/implement.yml` call's `with:`
  block, mirroring `findings-label-prefix`'s existing wiring at
  `wing-commander-5-implement.yml:99-100`.
- [x] T005 [P] `.github/workflows/wing-commander-6-finalize.yml`: wire
  `write-boundary-label-prefix: ${{
  vars.WING_COMMANDER_WRITE_BOUNDARY_LABEL_PREFIX || 'route-out-of-boundary'
  }}` into the `uses: ./.github/workflows/finalize.yml` call's `with:`
  block, mirroring `findings-label-prefix`'s existing wiring at
  `wing-commander-6-finalize.yml:44-45`. Reads the SAME repo var as T004 —
  one var, two wrappers, never a second var name (FR-003's rule extended to
  the wrapper layer).
- [x] T006 Create `.github/actions/_shared/classify-out-of-boundary-tasks.sh`
  (research.md D3, data-model.md's classification table) — the one home of
  the per-task boundary check. Invocation shape mirrors
  `count-tasks-checkboxes.sh`'s convention: reads the unchecked-items text
  (the exact multi-line value `wing-commander-tasks-checkbox-count`'s own
  `unchecked-items` output already produces), a `no-write-paths` value
  (comma-separated, unsplit), a `tasks-path` (e.g.
  `specs/090-stage-write-boundary/tasks.md`), and a `spec-dir`. Per unchecked
  line: extract every backtick-quoted, slash-containing, whitespace-free
  token as a candidate path (contracts/write-boundary-mechanism.md, research
  D3's exact extraction rule). A line with zero candidate tokens, or with at
  least one candidate token not prefixed by any `no-write-paths` entry
  (PREFIX match only — `.claude-extra/foo` must NOT match a `.claude/`
  boundary, since it is not actually under `.claude/`), falls through
  untouched (FR-015). A line whose every candidate token IS prefixed by a
  `no-write-paths` entry is out-of-boundary: emit one JSON object per such
  line, shaped to `.github/schemas/stage-finding.schema.json` — `title`
  names the task and path; `what` states it is outside the stage's write
  boundary and why; `evidence.file_paths` = `[<tasks-path>]`;
  `evidence.detail` = the literal task line plus the out-of-boundary
  path(s); `fingerprint_basis.file_path` = the same `<tasks-path>`;
  `fingerprint_basis.gate_or_artifact` = the literal unchecked line text,
  verbatim (data-model.md's "Each findings-json entry", the anchor that
  keeps two specs meeting the same `.claude/` path from colliding onto one
  fingerprint). Emit `findings-json=<JSON array>`,
  `all-unchecked-out-of-boundary=true|false` (`true` iff at least one
  unchecked line exists and every one classified out-of-boundary), and
  `out-of-boundary-count=<digits>` as `key=value`/heredoc-marker lines for
  the caller to relay into `$GITHUB_OUTPUT` (the same convention
  `count-tasks-checkboxes.sh` already uses). Unlike that script, this one
  MUST NOT exit non-zero for a task it cannot confidently classify — falling
  through to "ordinary" is a valid, expected output (FR-015), not an error
  condition; only a genuinely malformed invocation (missing required arg)
  should fail loudly.
- [x] T007 Create
  `.github/actions/wing-commander-write-boundary/action.yml` — the
  published front-door composite (contracts/write-boundary-mechanism.md §3),
  mirroring `wing-commander-tasks-checkbox-count/action.yml`'s shape.
  Inputs: `unchecked-items` (required), `no-write-paths` (required),
  `spec-dir` (required), `tasks-path` (required). Outputs: `findings-json`,
  `all-unchecked-out-of-boundary`, `out-of-boundary-count` — each a direct
  passthrough of T006's script output. Its single step calls
  `classify-out-of-boundary-tasks.sh` via
  `$GITHUB_ACTION_PATH/../_shared/...` (mirroring
  `wing-commander-tasks-checkbox-count/action.yml:57`) and appends its
  output straight to `$GITHUB_OUTPUT`. Header comment records the
  Constitution VII minor-version-addition note (plan.md's Complexity
  Tracking table).
- [x] T008 `.github/actions/wing-commander-stage-findings/action.yml`:
  extract the anchor/fallback fingerprint computation currently inline in
  the "Extract, validate, cap, and prepare findings" step's Python
  (`normalize_basis` ~line 269-272, `verify_anchor` ~line 274-301, and the
  two `hashlib.sha256("anchor|...`/`"fallback|...` calls ~line 318-328) into
  `.github/actions/_shared/compute-finding-fingerprint.sh` (research.md D6)
  — callable standalone with `stage`, `file_path`, and `gate_or_artifact`
  arguments, returning the same fingerprint the inline code produces today
  byte-for-byte. Change the "prepare" step to call this script instead of
  computing the hash inline. This is a pure internal refactor: no input,
  output, or rendered-text change for the existing `defect`-kind behavior —
  confirm with `python .github/scripts/run-local-gates.py` that
  `verify-stage-finding-schema.py`/`verify-stage-findings-wiring.py` (the
  gates covering this composite's existing contract) still pass unchanged.

**Checkpoint**: `wing-commander-write-boundary` and
`compute-finding-fingerprint.sh` are each callable in isolation against a
scratch input before any workflow logic in `implement.yml`/`finalize.yml`
depends on them; `wing-commander-stage-findings`'s existing behavior is
unaffected.

---

## Phase 3: User Story 1 - The stage knows what it may write before it tries (Priority: P1) 🎯 MVP

**Goal**: the rendered implement prompt states, before the agent's first
tool call, exactly which paths its `Edit`/`Write` tools may not target —
derived from `no-write-paths` the same way the existing Tooling paragraph's
shell-command sentence is derived from the composed tool lists (FR-004).

**Independent Test**: read the rendered implement prompt for one run with no
other context and answer "may this run's agent edit
`.claude/skills/spec-cross-reference/SKILL.md`?" correctly, then confirm the
answer matches what the run actually permits.

**Depends on**: Phase 2 (the `no-write-paths` input T002 declares).

- [x] T009 [US1] `.github/actions/wing-commander-tool-args/action.yml`: add
  a new optional input `no-write-paths` (default `""`) and a new output
  `write-paths-statement`. In the existing `compose` step, immediately
  after the `shell_commands` render (~line 355-366), add the identical
  four-shape rendering pattern (contracts/write-boundary-mechanism.md §2,
  data-model.md's "Write-paths statement"): split `no-write-paths` on
  commas, trim, dedupe, drop empties, preserving first-seen order — empty
  result → `"This run's agent may write any path in the checkout."`;
  non-empty → `"This run's agent may not write: <comma-joined list>."`.
  Emit `write-paths-statement=<sentence>` alongside the existing
  `shell-commands` output. No existing input, output, or the
  `shell-commands` render's own text changes.
- [x] T010 [US1] `.github/workflows/implement.yml`: add
  `no-write-paths: ${{ inputs.no-write-paths }}` to both `tool-args-cycle`'s
  (~line 848-864) and `tool-args-retry`'s (~line 1561) `with:` blocks. The
  third, read-only tool-args call site (~line 2336, which denies
  `Write,Edit` outright) is unaffected — leave it untouched, per
  contracts/write-boundary-mechanism.md §2.
- [x] T011 [US1] `.github/workflows/implement.yml`: add
  `${{ steps.tool-args-cycle.outputs.write-paths-statement }}` to the cycle
  prompt's Tooling paragraph (~line 975), immediately after the existing
  `Tooling: ${{ steps.tool-args-cycle.outputs.shell-commands }}` sentence.
  Mirror for the retry prompt's Tooling paragraph (~line 1707) using
  `steps.tool-args-retry.outputs.write-paths-statement`.
- [x] T012 [US1] Create `.github/scripts/verify-write-boundary.py` (Gate
  126, contracts/write-boundary-gate.md), modeled on
  `verify-tasks-checkbox-convergence-signal.py`'s structure: import
  `ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout` from
  `wc_shell_harness`; a `GATE_PREFIX = "Gate 133"` constant; a
  `STEPS_CACHE`/`load_steps()` populating it from the exact shipped step
  names this gate drives (`Compose tool args` — both `wing-commander-tool-
  args`'s own step and its two `implement.yml` call sites — `Read back
  cycle outcome`, `Read back retry outcome`, `Route out-of-boundary tasks`
  once it exists, `Look up routed write-boundary items` once it exists).
  This first pass covers only pass conditions (a) and (b) from
  contracts/write-boundary-gate.md: (a) single definition — `no-write-paths`
  is declared exactly once as a `workflow_call` input on `implement.yml`,
  and both consuming call sites (T010's two `tool-args-*` `with:` blocks)
  read `${{ inputs.no-write-paths }}`, never a second literal default
  anywhere else in `implement.yml`; (b) statement fidelity — for a fixture
  table of `no-write-paths` values (empty; `.claude/`; `.claude/,.git/`),
  the shipped `compose` step's rendered `write-paths-statement` states
  exactly the given prefixes and no others. Wire it into
  `.github/workflows/lint-workflows.yml` immediately, next to the other
  `verify-tasks-*`/`verify-stage-findings-*` gates, as two steps: `"Gate 133
  — the implement stage's write boundary is stated, classified, and routed
  consistently"` (bare `run: python3 .github/scripts/verify-write-
  boundary.py`) and `"Gate 133 self-test — write boundary"` (`run: python3
  .github/scripts/verify-write-boundary.py --self-test`) — Gate 10 requires
  every check script be named by some `run:` line or it is reported
  orphaned; do not leave it unwired even mid-feature. The `--self-test` flag
  can exit 0 with zero reintroduced mutations for now — T034 fills it in.
- [x] T013 [US1] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 133's (a)/(b) fixtures and every pre-existing gate pass.

**Checkpoint**: An agent in an implement cycle can now answer "may I write
this path?" for every path in the checkout from its prompt alone (SC-001).
User Story 1 is independently shippable here — even with no routing
mechanism yet, the stage stops discovering its boundary by refusal.

---

## Phase 4: User Story 2 - Work beyond the stage's reach is routed, not resurfaced (Priority: P1)

**Goal**: an unchecked task whose named path lies outside the write
boundary is filed, by deterministic code, as exactly one tracked item under
a pipeline-owned label the board loop does not treat as fix-shaped
authorization — never left to resurface every cycle or evaporate into
prose.

**Independent Test**: drive one cycle against a `tasks.md` containing a
task whose path is outside the stage's write boundary, and confirm that
after the run there is exactly one tracked, labelled item naming that task
and its path, and that a second cycle over the same `tasks.md` does not
produce a second one.

**Depends on**: Phase 2 (T006/T007's classification composite, T008's
fingerprint helper) and Phase 3 (this phase's read-back changes sit beside
US1's, in the same steps).

- [x] T014 [US2] `.github/workflows/implement.yml`, cycle arm: add a new
  step `write-boundary-cycle`, `uses: ./.wing-commander-pipeline/.github/
  actions/wing-commander-write-boundary`, immediately after `Count tasks.md
  checkboxes at tip (cycle)` (id `checkbox-tip-cycle`, ~line 1263-1269),
  same `if:` guard. Inputs: `unchecked-items: ${{
  steps.checkbox-tip-cycle.outputs.unchecked-items }}`,
  `no-write-paths: ${{ inputs.no-write-paths }}`,
  `spec-dir: ${{ steps.spec.outputs.spec-dir }}`,
  `tasks-path: ${{ steps.spec.outputs.spec-dir }}/tasks.md`.
- [x] T015 [US2] `.github/workflows/implement.yml`, retry arm: mirror T014
  — add `write-boundary-retry` immediately after `Count tasks.md checkboxes
  at tip (retry)` (id `checkbox-tip-retry`, ~line 1959-1961).
- [x] T016 [US2] `.github/workflows/implement.yml`, both `Read back cycle
  outcome` (~line 1278-1456) and `Read back retry outcome` (~line
  1966-...): after the existing `handoff` computation (~line 1413-1415),
  add a new step-local output `routed = handoff && all-unchecked-out-of-
  boundary`, reading `steps.write-boundary-cycle.outputs.all-unchecked-out-
  of-boundary` (resp. `write-boundary-retry`) — data-model.md's "Routed
  flag" / research.md D5. Also carry `steps.write-boundary-cycle.outputs.
  findings-json` (resp. retry) through as a new step output,
  `write-boundary-findings-json`, unmodified — never re-derived. Emit both
  alongside the existing `echo "handoff=$handoff"` line.
- [x] T017 [US2] `.github/workflows/implement.yml`, `Consolidate final
  outcome` (~line 2164-2244): carry `routed` and `write-boundary-findings-
  json` through the existing `RETRY_RAN` selection (same shape as the
  existing `progressed`/`handoff` selection at ~line 2189/2191) and add
  them to the output-emission block (~line 2233-2244). These remain
  step-local outputs, never `workflow_call` outputs of `implement.yml`
  (mirrors spec 059's own scope note for `progressed`/`handoff`).
- [x] T018 [US2] `.github/actions/wing-commander-stage-findings/action.yml`:
  add a new optional input `finding-kind` (allowed `defect`|`routed-task`,
  default `defect`). When `routed-task`, swap the three hardcoded strings
  contracts/write-boundary-mechanism.md §5 tables — the "created" recap
  phrase (`"a defect was filed by the $STAGE stage"`, ~line 453/561/660) →
  `"work the $STAGE stage could not complete under its write boundary was
  filed"`; the "commented" recap phrase (~line 458/566, `"a defect met by
  the $STAGE stage was recorded on an existing issue"`) → `"work the $STAGE
  stage still could not complete under its write boundary was recorded on
  an existing issue"`; the `label-description` (~line 403/515/615, `"...the
  $STAGE stage met a defect outside its own task"`) → `"...the $STAGE stage
  was assigned work outside its write boundary"`. `defect`'s rendered text
  (the default) must stay byte-for-byte unchanged — verify with
  `verify-stage-finding-schema.py`/`verify-stage-findings-wiring.py`. No
  other input, output, the fingerprint formula (now T008's shared helper),
  the cap, or the dedup call changes for either kind.
- [x] T019 [US2] `.github/workflows/implement.yml`: add a new step "Route
  out-of-boundary tasks" beside the existing "File findings from this run"
  (~line 2260-2274), guarded
  `if: ${{ !cancelled() && steps.final.outputs.ok == 'true' &&
  steps.final.outputs.truncated != 'true' && steps.final.outputs.routed ==
  'true' }}` (FR-013's truncated exclusion, plus the `routed` gate),
  `uses: ./.wing-commander-pipeline/.github/actions/wing-commander-stage-
  findings`, with: `token: ${{ env.WC_BOT_TOKEN }}`, `stage: implement`,
  `enabled: ${{ inputs.findings-filing-enabled }}`,
  `channel-mode: structured-array`,
  `findings-json: ${{ steps.final.outputs.write-boundary-findings-json }}`,
  `finding-kind: routed-task`, `spec-dir: ${{ steps.spec.outputs.spec-dir
  }}`, `run-url: ${{ github.server_url }}/${{ github.repository
  }}/actions/runs/${{ github.run_id }}`,
  `lifecycle-issue-number: ${{ inputs.issue-number }}`,
  `label-prefix: ${{ inputs.write-boundary-label-prefix }}`,
  `cap: ${{ inputs.findings-cap }}` (contracts/write-boundary-mechanism.md
  §5 — reusing `findings-cap`/`findings-filing-enabled` rather than adding
  parallel inputs, since this channel is not configurably distinct along
  those axes).
- [x] T020 [US2] Extend Gate 133 (`verify-write-boundary.py`) with pass
  condition (c), classification correctness, driving T006's shipped script
  directly: a single path, fully out-of-boundary → out-of-boundary; several
  paths, one in-reach → falls through; no path in the text → falls through;
  a path only partly matching a prefix (`.claude-extra/foo` against a
  `.claude/` boundary) → falls through (prefix match, not substring); the
  boundary is empty → nothing classifies out-of-boundary, ever. Cover every
  Edge Case spec.md names for this rule.
- [x] T021 [US2] Extend Gate 133 with pass conditions (f) idempotency and
  (g) fingerprint single-home: the same out-of-boundary unchecked line,
  fingerprinted twice via T008's shared helper (simulating two cycles),
  produces byte-identical fingerprints; a line reworded by even one
  character produces a different fingerprint (documented as an accepted,
  narrow limitation — re-wording is not detected as "the same" task); grep
  `.github/` for any second `sha256("anchor|...`/`sha256("fallback|...`-
  shaped string literal outside `compute-finding-fingerprint.sh` and its
  two callers (the findings composite, and — once T027 lands —
  `finalize.yml`'s lookup step) and assert none exists.
- [x] T022 [US2] Extend Gate 133 with pass condition (e), no filing on a
  truncated run: build a synthetic truncated cycle (`ok=true,
  truncated=true`) with an out-of-boundary-shaped `tasks.md` at the tip,
  and assert the "Route out-of-boundary tasks" step's own `if:` expression
  evaluates false when `truncated=true` even with `routed=true` — evaluate
  the compiled `if:` expression directly, never a live filing call
  (FR-013).
- [x] T023 [US2] Extend Gate 133 with pass condition (h), board-loop label
  separation: a static assertion that `write-boundary-label-prefix`'s
  default (`route-out-of-boundary`) is not equal to `findings-label-
  prefix`'s default (`found-by`) and is not the literal string
  `spec-request` — failing loudly if a future edit collapses them
  (research.md D4, Assumptions section).
- [x] T024 [US2] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 133's US2 fixtures ((c), (e), (f), (g), (h)) plus every pre-existing
  gate — including `verify-stage-finding-schema.py`/`verify-stage-findings-
  wiring.py`, unaffected by T018's additive `finding-kind` input — pass
  together.

**Checkpoint**: an out-of-boundary task now produces exactly one tracked,
labelled item under `route-out-of-boundary:implement` (distinct from
`found-by:implement`), idempotent across cycles and reruns (SC-004). User
Story 2 is independently testable here, on top of US1.

---

## Phase 5: User Story 3 - The loop's convergence verdict is honest about it (Priority: P1)

**Goal**: when the only remaining unchecked work is out-of-boundary, the
loop terminates in one cycle (no further iteration dispatched for that
work alone) and its reason narrative — both the lifecycle-issue comment and
the final PR's remaining-manual-work list — names the routed work instead
of reading as either "converged" or "stalled".

**Independent Test**: with one out-of-boundary task and every other task
checked, confirm the loop terminates without exhausting its iteration
budget, and that its terminal report distinguishes "all in-reach work is
done, one item was routed out" from both "converged" and "stalled".

**Depends on**: Phase 4 (the `routed`/`write-boundary-findings-json` values
this phase's reason narrative and finalize lookup both consume). Loop
termination itself needs NO new logic here — spec 059's existing hand-off
condition (`ok=true, truncated=false, converged=false, progressed=false, no
converge: commit`) already fires the moment the only unchecked task cannot
be advanced, which is exactly what `all-unchecked-out-of-boundary=true`
describes; this phase only changes what the `reason` text says for that
branch, per research.md D5. Do not re-derive or short-circuit spec 059's
`converged`/`progressed`/`handoff` decision table (Out of Scope).

- [x] T025 [US3] `.github/workflows/implement.yml`, both `Read back cycle
  outcome` and `Read back retry outcome`'s existing reason-narrative branch
  (~line 1421-1438, and its retry mirror): when `routed=true` (T016's new
  output), set `reason` to name each out-of-boundary task (from
  `write-boundary-findings-json`'s `title` fields) and state that the loop
  is ending here because the only remaining work is outside the stage's
  write boundary — replacing, ONLY in this branch, the existing generic
  hand-off phrasing (`"the cycle checked nothing new, so the loop is ending
  here rather than dispatching another cycle"`). Every other `reason` case
  (converge-appended, outstanding-with-progress, failed, truncated,
  cap-reached) is unchanged (FR-012's "must not suppress the existing...
  hand-off for the cases those already cover" — the other direction: a
  cycle where `progressed=true` still uses the unchanged narrative,
  because `handoff` (and therefore `routed`) requires `progressed=false`).
- [x] T026 [US3] Extend Gate 133 with pass condition (d), termination and
  reason, executing the shipped read-back `run:` bodies against synthetic
  repos: only unchecked task is out-of-boundary, nothing else progressed →
  `handoff=true, routed=true`, `reason` names the task; same, but another
  task also got checked this cycle (`progressed=true`) → `handoff=false,
  routed=false`, `reason` is spec 059's existing "outstanding with
  progress" narrative, unchanged (proving FR-012 the other way — progress
  must still win); a mixed unchecked set (one out-of-boundary, one
  ordinary) → `all-unchecked-out-of-boundary=false`, `routed=false` even at
  hand-off time, existing narrative unchanged.
- [x] T027 [US3] `.github/workflows/finalize.yml`: add a new deterministic
  step "Look up routed write-boundary items", before "Summarize change and
  extract remaining manual work" (~line 686). For each unchecked line in
  the tip's `tasks.md`: compute its fingerprint by calling T008's
  `compute-finding-fingerprint.sh` directly (never through the stage-
  findings composite) with `stage=implement`,
  `file_path=<spec-dir>/tasks.md`, `gate_or_artifact=<the line's literal
  text>`; then run
  `gh issue list --search '"<!-- wing-commander-finding: fingerprint=<fp>
  -->"' --label '${{ inputs.write-boundary-label-prefix }}:implement'
  --json url,state`. Emit a mapping (line text → issue URL) for every
  match, as a step output the next step's prompt can render (contracts/
  write-boundary-mechanism.md §6, data-model.md's "Routed-item lookup").
- [x] T028 [US3] `.github/workflows/finalize.yml`: extend the "Summarize
  change and extract remaining manual work" prompt (~line 732-738) with:
  "For any item in the lookup mapping below, write `<item> — routed, see
  <issue url>` instead of composing your own description of it; write
  every other item as today." Render T027's mapping into the prompt from
  its step output — never let the agent re-derive which unchecked line
  "looks routed" (Principle IX).
- [x] T029 [US3] Extend Gate 133 with a fixture for SC-005: a synthetic
  `tasks.md` with one routed (fingerprint-matching, per T027's formula)
  unchecked line and one ordinary unchecked line → T027's lookup mapping
  contains only the routed line's fingerprint match, and the rendered
  prompt instruction references it by URL; the ordinary line is untouched.
- [x] T030 [US3] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 133's US3 fixtures ((d), SC-005) plus every pre-existing gate pass.

**Checkpoint**: a `tasks.md` whose only unchecked item is out-of-boundary
terminates the loop in one cycle (SC-003), reported as neither converged
nor stalled (FR-011), and the final PR's remaining-manual-work list points
at the tracked item rather than losing it as an orphan line (SC-005). All
three P1 stories are shippable here.

---

## Phase 6: User Story 4 - The rule is not re-derived for the next unwritable path (Priority: P2)

**Goal**: prove, with a fixture rather than a mechanism change, that adding
a second unwritable path is a `no-write-paths` list entry the statement,
the classification, and the routing label all pick up automatically.

**Independent Test**: introduce a second unwritable path and confirm that
the boundary statement, the routing, and the report all cover it with no
change to the mechanism itself.

**Depends on**: Phases 3-5 (this story adds no new code path — it verifies
a property Phases 3-5's implementation must already satisfy by
construction, per the same reasoning spec 059's US2 phase used).

- [x] T031 [US4] Extend Gate 133 with a second-path fixture: drive the
  shipped `compose`/classification/lookup bodies with
  `no-write-paths=".claude/,.git/"` and confirm (i) the rendered
  `write-paths-statement` states both prefixes, (ii) a task naming a
  `.git/`-prefixed path classifies out-of-boundary exactly as a
  `.claude/`-prefixed one does, and (iii) the routing label carries no
  path-specific text — all with zero changes to `classify-out-of-boundary-
  tasks.sh` or `wing-commander-tool-args`'s `compose` step beyond what
  Phases 2-3 already shipped.
- [x] T032 [US4] Confirm (read-only; no code change unless a gap is found)
  that `no-write-paths` has exactly one declared definition per FR-003 and
  pass condition (a): `implement.yml`'s own `workflow_call` input is the
  sole default; `wing-commander-tool-args`'s call site (T010) and
  `wing-commander-write-boundary`'s call site (T014/T015) both read `${{
  inputs.no-write-paths }}`; `grep -n '"\.claude/"' .github/workflows/
  implement.yml .github/actions/wing-commander-tool-args/action.yml
  .github/actions/wing-commander-write-boundary/action.yml` shows the
  literal default exactly once (the `workflow_call` input declaration in
  T002).
- [x] T033 [US4] Run `python .github/scripts/run-local-gates.py`; confirm
  Gate 133's US4 fixture passes alongside every prior phase's.

**Checkpoint**: the next unwritable path this repository identifies is a
list entry on `no-write-paths`, never a second mechanism (FR-019).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T034 Add a `MUTATIONS` table to Gate 133 (mirroring
  `verify-tasks-checkbox-convergence-signal.py`'s `_mut_*`/`MUTATIONS`
  pattern, FR-020, SC-007), reintroducing and asserting each one is caught
  by `--self-test` (contracts/write-boundary-gate.md's 7-item list): (1)
  `no-write-paths` hand-edited to a second literal default inside
  `wing-commander-write-boundary`'s call site, diverging from
  `implement.yml`'s own input default — must fail (a); (2) the rendered
  `write-paths-statement` mutated to include a prefix absent from the
  input — must fail (b), the SC-007 drift mutation; (3) the classification
  rule's prefix-match relaxed to a substring match (so `.claude-extra/foo`
  would wrongly classify under a `.claude/` boundary) — must fail (c); (4)
  the `routed` computation changed to ignore `handoff` (hard-coded `true`
  whenever `all-unchecked-out-of-boundary` alone is true, even with
  `progressed=true`) — must fail (d)'s second scenario, the SC-007
  "disables the boundary check" mutation read as "always routes"; (5) the
  "Route out-of-boundary tasks" step's `if:` guard's `truncated` clause
  removed — must fail (e); (6) `compute-finding-fingerprint.sh`
  re-implemented inline a second time, pasted into `finalize.yml` instead
  of called — must fail (g); (7) zero fixtures discovered/executed at all
  — must fail loudly (Constitution VIII). Guard each mutation the way
  `verify-tasks-checkbox-convergence-signal.py`'s `main()` already does: if
  the mutation's target text no longer exists in the current shipped step,
  error "mutation inapplicable" rather than silently pass.
- [x] T035 Add a `check_gate_wired()` self-test to Gate 133 (mirroring Gate
  99's): confirm the "Gate 133 — ..." step exists in `.github/workflows/
  lint-workflows.yml`, is not `if: false`, and its `run:` line names
  `verify-write-boundary.py`'s exact path.
- [x] T036 Record FR-002's policy decision — "no agent write under
  `.claude/`, for any of its three parts (vendored `speckit-*`, this
  repository's own skills, the control surface); deterministic non-agent
  writes (`auto-update-spec-kit.yml`) unaffected" — where a future change
  will read it (FR-018): first check whether `.specify/memory/
  constitution.md`'s Principles V, VI, VII, or IX already say this (they
  currently state the general least-privilege/portability/two-interfaces/
  deterministic-judgement rules but not this specific "agent may not write
  its own control surface" rule); if genuinely new, use the
  `speckit-constitution` skill to amend the constitution, following
  CLAUDE.md's process — the Sync Impact Report the skill writes at the top
  of `constitution.md` moves to the top of
  `.specify/memory/constitution-history.md`'s list in the same commit,
  leaving only a one-line pointer in `constitution.md` itself. Also record
  the decision in `no-write-paths`'s own input description on
  `implement.yml` (T002), the single definition FR-003 requires.
- [x] T037 Update `docs/adoption.md`'s per-stage input tables: add
  `no-write-paths` and `write-boundary-label-prefix` to `implement.yml`'s
  table, and `write-boundary-label-prefix` to `finalize.yml`'s table
  (FR-018, FR-021) — same defaults as T002/T003.
  Confirm no existing input, secret, or output row in either table changed
  name or default.
- [x] T038 Comment on issue #675 recording SC-006: spec 060's `T055` was
  completed by hand in #490 (FR-002's prescribed outcome for a `.claude/`
  task); this feature's routing mechanism is proven on the T055-shaped
  fixture in Gate 133 (T020) rather than on `T055` itself, since `T055` is
  already checked in `specs/060-self-redrive-concurrency/tasks.md`. No code
  change to `T055`'s own content is required (Out of Scope).
- [x] T039 Run `python .github/scripts/run-local-gates.py` for the full
  suite: confirm Gate 133 (complete scenario table across (a)-(h) plus the
  7-item mutation battery) and every other gate pass together (SC-007).
- [ ] T040 Replay a `T055`-shaped fixture end-to-end against the real
  workflow file (quickstart.md's live-replay section): seed a throwaway
  spec branch's `tasks.md` with one checked-off task and one unchecked task
  naming a `.claude/skills/...` path; dispatch `implement.yml` by hand;
  confirm the rendered prompt states the write boundary before the agent's
  first tool call, the agent does not attempt the out-of-boundary edit, the
  cycle ends without exhausting the iteration budget, a new issue appears
  labeled `route-out-of-boundary:implement`, the lifecycle issue's recap
  comment names it, a second dispatch against the same unchanged `tasks.md`
  files no second issue, and `finalize.yml`'s remaining-manual-work list
  renders the task as `<task text> — routed, see <issue url>`. NOT DONE at
  tasks-authoring time — this run's permitted command list has no `gh
  workflow run`/`gh run view`, only `gh issue view`/`gh issue comment`/`gh
  pr view`/`gh pr list`/`gh issue list`. Needs a human or a
  differently-scoped session post-merge, per CLAUDE.md's rule that
  behaviour which only runs in Actions is proven after merge by re-driving
  one run and recording the evidence on the PR or issue.

**Checkpoint**: `python .github/scripts/run-local-gates.py` exits 0; the
constitution and `docs/adoption.md` describe the shipped boundary; SC-006 is
recorded on the lifecycle issue; the live replay is queued for a
post-merge session.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup — BLOCKS every user story
  (the shared `no-write-paths` input, classification composite, and
  fingerprint helper every later phase wires in).
- **User Story 1 (Phase 3)**: depends on Foundational. This is the MVP.
- **User Story 2 (Phase 4)**: depends on Foundational (T006/T007/T008) and
  sits beside Phase 3's read-back edits in the same steps.
- **User Story 3 (Phase 5)**: depends on Phase 4 (`routed`/`write-boundary-
  findings-json`, the values this phase's reason narrative and finalize
  lookup consume).
- **User Story 4 (Phase 6)**: depends on Phases 3-5 — it verifies
  properties their implementation must already satisfy; no new code path.
- **Polish (Phase 7)**: depends on all four stories being complete —
  T034's mutation battery targets scenarios every prior phase added.

Unlike a fully independent-stories feature, Phases 4 and 5 are **not**
parallelizable against each other: both edit `Read back cycle outcome`,
`Read back retry outcome`, and `Consolidate final outcome`. Land and
checkpoint each phase in the order above.

### Within Each Phase

- T002/T003/T004/T005 (Foundational, different files) can run in parallel.
- T006 and T008 (different scripts, no shared state) can run in parallel;
  T007 depends on T006 existing.
- T014/T015 (US2, cycle vs. retry arm, same file) touch non-overlapping
  line ranges and can run in parallel with care about merge conflicts on
  adjacent step insertions — the same caution spec 059's tasks.md gives
  T004/T006.
- Gate-extension tasks (T012, T020-T023, T026, T029, T031, T034-T035) touch
  one file (`verify-write-boundary.py`) sequentially within a phase — do
  not parallelize two gate-extension tasks against the same file.

### Parallel Opportunities

- T002, T003, T004, T005 (Foundational) touch different files.
- T006 and T008 (Foundational) touch different files.
- T014 and T015 (US2 composite call sites) touch the same file but
  non-overlapping line ranges.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (the shared input/composite/helper —
   blocks everything, even though US1 itself only consumes the input).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run `python .github/scripts/run-local-gates.py`;
   this alone satisfies SC-001/SC-002 — the boundary is knowable in
   advance, so a refused `Edit`/`Write` becomes a defect in the statement
   rather than a discovery.

### Incremental Delivery

1. Setup + Foundational → the classification composite and fingerprint
   helper exist and are callable.
2. Add User Story 1 → the prompt states the boundary; the core discovery
   problem (spec 060's `T055`/`T053`) stops recurring.
3. Add User Story 2 → an out-of-boundary task is filed, once, under a
   non-authorizing label — the loss User Story 2 exists to end.
4. Add User Story 3 → the loop terminates honestly instead of grinding to
   the iteration cap, and the final PR's remaining-manual-work list points
   at the tracked item instead of losing it as prose.
5. Add User Story 4 → proven, not merely asserted, that the next unwritable
   path is a list entry.
6. Polish → the mutation battery, the constitution/docs corrections, the
   SC-006 recap comment, and the post-merge live replay proof.

Every story after US1 narrows or extends behaviour US1's statement makes
visible; none is safe to ship ahead of US1's Foundational dependency, and
US2 should not be deferred past a single PR from US3 — shipping US1 alone
leaves the exact loss (an out-of-boundary task grinding the loop to its cap
and evaporating into PR-body prose) that this feature exists to end.
</content>

## Maintainer Feedback — Gate number collision (PR #836 review, item 1)

- [x] Renumber to **Gate 133** in `verify-write-boundary.py`: the `:2` docstring, the `:49` `GATE_PREFIX` constant, and the `:307`/`:788` `STEP_LABEL "gate126"` values
- [x] Renumber in `lint-workflows.yml` `:4657-4669`: the comment and both step names; rewrite the "128, not the 126" rationale text to refer to 133
- [x] Renumber the reference in `_shared/compute-finding-fingerprint.sh`:14
- [x] Renumber the reference in `wing-commander-stage-findings/action.yml`:285
- [x] Renumber the reference in `finalize.yml` ~:708
- [x] Fix `constitution-history.md`:25 — the Sync Impact Report is new in this PR, so fix the number before merge rather than treat it as historical
- [x] Renumber all 23 occurrences in `tasks.md`, and optionally the placeholders in `contracts/write-boundary-gate.md` and `quickstart.md` (no placeholders found in either file)
- [ ] Update the PR body's gate-number references (PR #836's body; this run's permitted `gh` commands are only `gh issue view`/`gh issue comment`, no `gh pr` verb, so this is left for a human or a differently-scoped session)

## Maintainer Feedback — routing never fires when converge commits or the last in-reach task ticks (PR #836 review, item 2)

- [x] In `implement.yml`'s "Read back cycle outcome" (~:1459-1468) and "Read back retry outcome" (~:2184-2189), derive `routed` from `all-unchecked-out-of-boundary && ok && !truncated` and no in-reach progress this cycle, instead of requiring spec 059's `handoff` (which requires no `converge:` commit)
- [x] Treat a `converge:` commit whose appended lines are all out-of-boundary as not disqualifying `routed`
- [x] File out-of-boundary tasks whenever the loop ends for any reason (iteration cap or stall reached), not only on the routed hand-off path (routed is now derived from `ok`/`truncated`/classification alone, so it fires on every cycle/retry read-back that sees an all-out-of-boundary unchecked set, not only spec 059's narrow handoff path)
- [x] Add a Gate 133 fixture reproducing the shipped read-back step with every unchecked task under `.claude/` plus one `converge:` commit that re-appends it, asserting the fix now routes instead of `handoff=false routed=false reason="converge appended new work"` (scenario 4, via the new `build_converge_scenario` harness helper)
- [x] Add a Gate 133 fixture for a cycle that ticks the last in-reach task (`progressed=true`) on what turns out to be the final iteration, asserting the out-of-boundary task is still filed instead of reaching the PR as orphan prose (SC-005) (scenario 2, updated in place -- same fixture shape the ask describes)

## Maintainer Feedback — write boundary is stated but not enforced (PR #836 review, item 3)

- [x] In `wing-commander-tool-args`'s `compose` step, derive the disallowed `Edit`/`Write` tool-list entries (e.g. `Edit(X**)`/`Write(X**)`) from `no-write-paths`, so the rendered "may not write: X" statement and the composed tool grant share one source (new Gate 133 pass condition (i) asserts the parity)
- [x] Add the prompt sentence User Story 1 Acceptance Scenario 2 needs: instruct the agent to leave an out-of-boundary task unchecked rather than attempt it, since such tasks are routed deterministically

## Maintainer Feedback — Gate's --self-test is vacuous and misses real regressions (PR #836 review, item 4)

- [x] Rewrite each `check_mutation_N` in `verify-write-boundary.py` (:764-894) to re-run the real matching `check_*` pass condition against the mutated input and assert it fails, not merely assert the mutation changed the text (currently deleting the `check_statement_fidelity`/`check_termination_and_reason` calls from `main()` still passes `--self-test`)
- [x] Add retry-arm scenarios: `RETRY_STEP` is loaded but never exercised, and condition (a) doesn't check the write-boundary-cycle/-retry call sites — extend it to cover them
- [x] Assert both prompts (cycle and retry) actually interpolate `write-paths-statement`
- [x] Assert the Route step's `findings-json` and `finding-kind: routed-task` wiring
- [x] Confirm, as a regression check, that each of these now fails the gate: the retry arm's routed condition hard-coded to `if false`; either prompt's `write-paths-statement` interpolation deleted; the Route step's `findings-json` set to `'[]'`
- [x] Extend condition (f) beyond proving the hash is deterministic to also prove SC-004's "two cycles → one issue" (proven jointly with Gate 71's own dedup test; this gate asserts that Gate 71 step is still wired, rather than re-testing its nested `uses:` chain as a second copy)

## Maintainer Feedback — finalize's routed-item lookup fails silently and mismatches the filer (PR #836 review, item 5)

- [x] In `wing-commander-write-boundary-lookup/action.yml`:62, stop swallowing `gh issue list` failures into "(none)" via `2>/dev/null || true`; emit `::warning::` on failure so a routed item doesn't silently reach the PR as orphan prose
- [x] Reuse the filer's existing list-by-label-then-client-side-`contains(marker)` lookup instead of relying on unproven full-text search over an HTML-comment marker
- [x] Add gate coverage exercising this lookup path, since the gate currently stubs `gh` and never tests it (new pass condition (j), plus the existing SC-005 fixture's stub now simulates a real `gh issue list --json number,url,body` call)

## Maintainer Feedback — routing can be silently disabled or truncated (PR #836 review, item 6)

- [x] Make the "Route out-of-boundary tasks" step run regardless of `findings-filing-enabled`, or give routing its own enablement toggle, so disabling defect filing doesn't also silently disable FR-007 routing while the loop still reports "routed"
- [x] Surface `findings-cap`'s clamp-to-3 limit so a 4th out-of-boundary task in one cycle isn't silently dropped (FR-007/SC-005)

## Maintainer Feedback — filed routed-item text contradicts itself (PR #836 review, item 7)

- [x] In `classify-out-of-boundary-tasks.sh` (~:103), reword the body from "is **inside** the implement stage's write boundary" to "is on the implement stage's no-write list", matching the title's "outside" framing

## Maintainer Feedback — .claude/settings.json edge case needs an explicit fixture (PR #836 review, item 8)

- [x] Add a dedicated Gate 133 fixture for the `.claude/settings.json` edge case (a task that would grant the stage the very permission it lacks), per spec.md's Edge Cases, rather than relying on it merely falling out of the prefix comparison

## Maintainer Feedback — write-boundary composite can skip the read-back on crash (PR #836 review, item 9)

- [x] Add failure handling (e.g. `continue-on-error` plus an explicit downstream guard) to the `wing-commander-write-boundary` step so a classifier crash doesn't skip the subsequent "Read back cycle/retry outcome" steps, which currently rely on implicit `success()`
- [x] Make the composite's header comment ("never fails the job") true in practice
- [x] Apply the same fix to finalize's new checkbox-count step
- [x] Get a pass from the `review-step-gating` skill per CLAUDE.md, since this touches an `if:`/failing-step surface (Gate 24 clean; manual stranded-step check found no step reading `.outcome`/`.conclusion` of any of the three newly-tolerant steps, and every downstream consumer reads only `.outputs.*`, which degrade to empty/false -- "not applicable" -- never a false positive signal)

## Maintainer Feedback — duplicated prose violates single-home rule (PR #836 review, item 10)

- [x] In `wing-commander-stage-findings/action.yml` slots 1 and 2, replace the newly pasted-in-full label-description comment with a pointer back to the canonical copy, per CLAUDE.md's "Shared logic has exactly one home" rule (Gate 47 enforces the pointer)
- [x] Fix `finalize.yml`'s new comment, which cites a "Check out the spec branch" step that doesn't exist; the real step is named "Checkout spec branch as wing-commander-bot"

## Review Gate Round 1 Findings

- [x] Review finding: Dispatch decision never reads the new routed output, so FR-010 termination doesn't happen

  implement.yml's terminal dispatch step only checks CONVERGED/TRUNCATED/HANDOFF, so when a cycle has handoff=false but routed=true (the last in-reach task just ticked, remaining work is out-of-boundary), it falls into the ITERATION<MAX branch and redispatches another cycle instead of terminating, contradicting the reason text it just printed and FR-010's own wording.

  - .github/workflows/implement.yml

  Detail: env block for "Post progress comment and dispatch next step" never receives ROUTED/PRIMARY_ROUTED/RETRY_ROUTED; the CONVERGED/TRUNCATED/HANDOFF/ITERATION<MAX if-chain has no routed branch; verify-write-boundary.py gate (d) scenario 2 exercises handoff=false, routed=true but only asserts the reason text, not the dispatch outcome

  Fixed: "Dispatch next step" now reads `ROUTED: ${{ steps.final.outputs.routed }}` and its `elif [ "$HANDOFF" = "true" ]` branch became `elif [ "$HANDOFF" = "true" ] || [ "$ROUTED" = "true" ]`, terminating via `post_handoff_remaining_work` (with a routed-specific message when `$ROUTED = true`) instead of falling into the `ITERATION < MAX` redispatch branch. Gate 133's scenario 2 now also drives the real "Dispatch next step" body and asserts it hands off to the next-workflow rather than redispatching; mutation 11 reintroduces the regression and confirms the gate catches it.

- [x] Review finding: Classifier's prefix match isn't normalized the same way enforcement's glob-deny is

  classify-out-of-boundary-tasks.sh compares raw unnormalized no-write-paths prefixes with startswith, while wing-commander-tool-args/action.yml normalizes each prefix to end in exactly one slash before building the Edit/Write deny glob, so a no-trailing-slash path (e.g. "specs") over-matches in the classifier (routing specs-legacy/notes.md though it isn't actually denied) and a tasks.md line written with a leading "./" under-matches, letting the agent keep retrying a denied edit every cycle.

  - .github/actions/_shared/classify-out-of-boundary-tasks.sh
  - .github/actions/wing-commander-tool-args/action.yml

  Detail: classify-out-of-boundary-tasks.sh ~line 93 token.startswith(prefix) vs wing-commander-tool-args/action.yml ~lines 403-407 trailing-slash normalization before Edit()/Write() glob construction; no fixture in verify-write-boundary.py's CLASSIFY_FIXTURES/ENFORCEMENT_FIXTURES tests a prefix without a trailing slash

  Fixed: classify-out-of-boundary-tasks.sh now normalizes each no-write-paths prefix to end in exactly one trailing slash (mirroring the composite's own glob normalization) and strips a leading "./" from each candidate token before comparing. New CLASSIFY_FIXTURES cover a no-trailing-slash boundary (`specs` vs `specs-legacy/notes.md` vs `specs/foo.md`) and a leading-"./" token; a new ENFORCEMENT_FIXTURES entry proves the enforcement side already normalized `specs` to `specs/**`. Mutation 12 reintroduces the un-normalized comparison and confirms the gate catches it.

- [x] Review finding: Routed-issue lookup's gh issue list has no --limit, silently caps at 30 against a repo-lifetime label

  wing-commander-write-boundary-lookup/action.yml's gh issue list call for route-out-of-boundary:implement has no --limit, and that label accumulates every routed issue across the repo's whole lifetime (not per-spec), so once more than 30 such issues exist, lookups for older fingerprints silently return no match and finalize.yml composes orphan prose instead of pointing at the already-tracked issue.

  - .github/actions/wing-commander-write-boundary-lookup/action.yml

  Detail: ~line 73: gh issue list --repo "$GITHUB_REPOSITORY" --label "${LABEL_PREFIX}:implement" --state all --json number,url,body, no --limit flag; label is global per wing-commander-stage-findings/action.yml's label = "{LABEL_PREFIX}:{STAGE}"

  Fixed: both wing-commander-write-boundary-lookup's and wing-commander-durable-failure-issue's marker-scoped `gh issue list` calls now carry an explicit `--limit 1000`. (The `gh issue list` call itself stays inline in each composite's own step rather than moving into a `_shared/` script, per Gate 12's own rule that a `_shared/*.sh` script making a `gh` call is unresolvable and fails the gate — see the next finding.) check_finalize_lookup now asserts `--limit` appears in the recorded `gh` call; mutation 13 reintroduces its absence and confirms the gate catches it.

- [x] Review finding: write-boundary-mechanism contract documents wiring the shipped code deliberately changed

  The live contract (fixed like code per CLAUDE.md) still states routed = handoff && all-unchecked-out-of-boundary and a per-line gh issue list --search lookup and enabled wired to findings-filing-enabled, but the shipped code deliberately decouples routed from handoff, hardcodes enabled: "true", and uses a list-by-label-then-client-side-contains lookup instead — each change made explicitly in response to this PR's own review items 2 and 6, leaving the contract pointing at the regressions already fixed.

  - specs/090-stage-write-boundary/contracts/write-boundary-mechanism.md
  - .github/workflows/implement.yml
  - .github/actions/wing-commander-write-boundary-lookup/action.yml

  Detail: contract §4 line ~102 (routed formula), §5 line ~148 (enabled wiring), §6 lines ~171-174 (search-based lookup) vs shipped implement.yml routed computation comment "deliberately NOT gated on spec 059's handoff" and lookup action's label-list+contains() strategy

  Fixed: contract §4 now states `routed = ok && !truncated && all-unchecked-out-of-boundary`, deliberately NOT gated on `handoff`, and documents the Dispatch-step fix above; §5's call site now shows `enabled: "true"` with the rationale (never `findings-filing-enabled`); §6 documents the list-by-label-then-client-side-match strategy (bounded `--limit`, inline `gh` call per Gate 12, shared `match-issue-by-marker.sh` for the jq filter only) instead of the old per-line `--search` lookup.

- [x] Review finding: compute_fingerprint() can crash the findings loop instead of degrading one finding

  Unlike every other fallible operation in the prepare-findings step, compute_fingerprint() calls the new shared fingerprint script with subprocess.run(check=True) and no try/except, so a nonzero exit there raises past any survivors already processed earlier in the same run, silently dropping all of them down to the generic 'no state was recorded' note instead of degrading just the one finding.

  - .github/actions/wing-commander-stage-findings/action.yml

  Detail: ~line 313, inside the "for i in range(MAX_SLOTS)" loop; contrast with finalize.yml's own caller of the same script which tolerates a failed/empty fingerprint line without check=True

  Fixed: compute_fingerprint() now catches CalledProcessError/KeyError/ValueError and returns (None, False) instead of raising; the per-slot loop treats fp is None as a malformed-and-dropped finding (added to dropped_malformed/notes, survivor-N-present=false) and continues to the next slot rather than crashing the whole step. New stage-findings-tests fixture (case_fingerprint_script_crash_drops_only_that_finding) drives the real prepare step with one finding whose fingerprint script call is made to fail and one that succeeds, asserting the step still exits 0, state is recorded, the broken finding is dropped, and the other finding still files.

- [x] Review finding: Routed-issue dedup jq re-pastes an existing composite's lookup pattern instead of a shared helper

  wing-commander-write-boundary-lookup/action.yml's marker-matching jq filter (list by label, then select body contains marker) is a near-verbatim re-paste of wing-commander-durable-failure-issue/action.yml's existing dedup jq program, violating CLAUDE.md's single-home rule for cross-workflow jq even though this same PR already created two _shared/ scripts for its other logic.

  - .github/actions/wing-commander-write-boundary-lookup/action.yml
  - .github/actions/wing-commander-durable-failure-issue/action.yml

  Detail: write-boundary-lookup ~lines 85-88 jq '[.[] | select(.body != null and (.body | contains($marker)))] | first.url // empty' vs durable-failure-issue ~lines 165-166 near-identical jq, not factored into .github/actions/_shared/

  Fixed: extracted the marker-match jq filter into `.github/actions/_shared/match-issue-by-marker.sh`; both composites now call this one script instead of each pasting the jq filter. (An earlier draft also factored the `gh issue list` call itself into a `_shared/` script, but Gate 12 explicitly fails any `gh` call inside `.github/actions/_shared/*.sh` since it cannot resolve that script's token statically — the listing call stays inline in each composite, matching/match-issue-by-marker.sh carries no `gh` call of its own.)

## Review Gate Round 2 Findings

- [x] Review finding: finalize.yml lookup step lacks the continue-on-error its sibling got

  The new "Look up routed write-boundary items" step in finalize.yml has no continue-on-error, unlike the "Count tasks.md checkboxes at tip (finalize)" step immediately above it and the analogous write-boundary-cycle/-retry steps in implement.yml, which were all given this exact protection in response to review-gate-round-1 item 9's finding about classifier/composite crashes skipping downstream implicit-success() steps.

  - .github/workflows/finalize.yml

  Detail: finalize.yml:722 "Look up routed write-boundary items" step has no continue-on-error, while the sibling step directly above it (checkbox-tip-finalize, ~line 703) explicitly added continue-on-error citing "PR #836 review, item 9", and implement.yml's write-boundary-cycle/-retry steps got the same fix for the identical crash-skips-downstream-success()-gated-step risk. The downstream "Summarize change and extract remaining manual work" step (~line 737) is gated only on an implicit success(), with no always()/!cancelled(), so any crash in this composite (not just the internally-handled `gh issue list` failure, which is already caught) fails the whole finalize job and skips the PR's own summary/remaining-manual-work report for the entire run.

## Phase 8: Convergence

- [x] T041 Correct plan.md's Summary (~line 22-26) where it states "Loop
  termination itself needs no new logic — spec 059's existing hand-off
  (`progressed=false` and no `converge:` commit) already stops the loop the
  moment the only unchecked task cannot be advanced" per plan: termination
  decision (contradicts). Review Gate Round 1 finding 1 found the opposite
  was true — the shipped "Dispatch next step" required a real fix (reading
  a new `ROUTED` value and OR-ing it into the termination branch) because
  `handoff=false, routed=true` was falling into the iteration-redispatch
  branch instead of terminating — and Maintainer Feedback item 2 then
  deliberately decoupled `routed` from spec 059's `handoff` entirely
  (`routed = ok && !truncated && all-unchecked-out-of-boundary`, no longer
  gated on `handoff`/`progressed`/"no converge: commit"). The Summary no
  longer describes the shipped mechanism. Update it, and check whether the
  Project Structure section's touch-point list (~line 99-134) should name
  the "Dispatch next step" edit it currently omits.


## Maintainer Feedback — constitution Sync Impact Report order/version drift (PR #836 review, item 11)

- [x] Move this PR's Sync Impact Report in `.specify/memory/constitution-history.md` (~:29) to the top of the list, above #901's 2026-10-01 report — currently it sits below that report even though both claim the same "2.1.0 → 2.2.0" range
- [x] Change this PR's report's Version line to `2.2.0 → 2.3.0` (matching `constitution.md:60`'s already-correct "2.3.0") and refresh its date to match when this PR's amendment actually lands

## Maintainer Feedback — out-of-boundary tasks in a mixed remainder are never filed (PR #836 review, item 12)

- [x] `implement.yml`: always pass `write-boundary-findings-json` through to the "Route out-of-boundary tasks" step regardless of `routed`/`handoff` (the write-boundary composite's `findings-json` output already lists only out-of-boundary entries) -- already unconditional (`steps.final.outputs.write-boundary-findings-json` is emitted by "Consolidate final outcome" regardless of `routed`); confirmed and left unchanged
- [x] Change the "Route out-of-boundary tasks" step's `if:` guard (implement.yml:~2411) to `!cancelled() && ok && !truncated && findings-json != '[]' && (routed || handoff || iteration >= max)`, so a mixed unchecked set (some out-of-boundary, some ordinary) still gets its out-of-boundary tasks filed even when the loop stalls or hits the cap instead of reaching a clean routed hand-off (FR-007)
- [x] Add a Gate 133 fixture reproducing the mixed-stall scenario (`routed=false, handoff=true`, one out-of-boundary task and one ordinary task both unchecked) and assert the out-of-boundary task is now filed

## Maintainer Feedback — three check families have no mutation coverage (PR #836 review, item 13)

- [x] Add a mutation to the `run_mutations` table in `verify-write-boundary.py` (~:1401) for pass condition (i) enforcement parity: strip the `Edit(…)`/`Write(…)` append from the `wing-commander-tool-args` compose step and re-run `check_enforcement_parity`, asserting it now fails
- [x] Add a mutation covering pass condition (f) idempotency: break the shared fingerprint helper's determinism (or its call site) and assert the idempotency check now fails
- [x] Add a mutation covering pass condition (h) label separation: collapse `write-boundary-label-prefix`'s default onto `findings-label-prefix`'s default and assert the label-separation check now fails

## Phase 9: Convergence

- [x] T042 Correct data-model.md's `routed`-flag formula (~line 101, still
  `routed = handoff && all-unchecked-out-of-boundary`), the FR-012
  paragraph (~line 117-121, still claiming `routed` cannot be true when
  `progressed=true`), the "Routed finding" entry's "Computed/filed by"
  guard text (~line 131-132, still `routed == 'true' && truncated !=
  'true'` only), and the relationships diagram (~line 170, still showing
  `all-unchecked-out-of-boundary, handoff ─▶ routed`) to describe the
  shipped mechanism: `routed = ok && !truncated &&
  all-unchecked-out-of-boundary`, deliberately NOT gated on `handoff`
  (Maintainer Feedback item 2), and the "Route out-of-boundary tasks"
  step's broadened guard, `!cancelled() && ok && !truncated &&
  write-boundary-findings-json != '[]' && (routed || handoff ||
  iteration>=max)` (Maintainer Feedback item 12) per data-model.md:
  Routed flag / FR-012 / Routed finding (contradicts)

## Review Gate Round 3 Findings

- [x] Review finding: In-flight dedup loop treats a None fingerprint as a real dedup key

  The in-flight findings loop in wing-commander-stage-findings/action.yml calls compute_fingerprint() and uses its result as a dedup marker without checking for None, unlike the survivors loop added in the same diff which explicitly guards `if fp is None`

  - .github/actions/wing-commander-stage-findings/action.yml

  Detail: Around line 445 (in-flight loop) vs the None-guard added around lines 488-497 for the survivors loop; if compute-finding-fingerprint.sh crashes for two distinct in-flight findings, both get marker fingerprint=None and the second is silently treated as a duplicate of the first, dropping a real defect from the lifecycle-issue checklist with no dropped-malformed note

  Fixed: the in-flight loop now checks `if fp is None` before computing a marker, dropping only that finding with a `"dropped (malformed, in-flight): ..."` note instead of letting a shared `fingerprint=None` marker collide two distinct broken findings into one. New stage-findings-tests fixture (`case_in_flight_fingerprint_crash_does_not_collide_two_findings`) drives two in-flight findings whose fingerprint script both fail, asserting both are recorded as dropped (malformed) and neither is treated as a duplicate of the other.

- [x] Review finding: No-write-path prefix normalization duplicated between classifier and enforcement

  classify-out-of-boundary-tasks.sh's normalize_prefix (Python) and wing-commander-tool-args/action.yml's compose step (bash) independently reimplement the same trailing-slash/leading-./ canonicalization, kept in sync only by comments claiming parity, not a shared helper or formula-level gate

  - .github/actions/_shared/classify-out-of-boundary-tasks.sh
  - .github/actions/wing-commander-tool-args/action.yml

  Detail: classify-out-of-boundary-tasks.sh lines ~86-97/92-124 vs wing-commander-tool-args/action.yml lines ~696-702; a future edge case (multiple leading './', trailing '//', different separators) can diverge between classification and enforcement with no gate catching it, violating FR-004/FR-005's 'stated boundary is the enforced boundary' guarantee and CLAUDE.md's single-home rule

  Fixed: extracted the trailing-slash canonicalization into `.github/actions/_shared/normalize-write-path-prefix.sh`. `classify-out-of-boundary-tasks.sh` now normalizes `NO_WRITE_PATHS` through this one helper in bash before handing the result to its Python classifier (whose own `normalize_prefix()` was deleted); `wing-commander-tool-args/action.yml`'s compose step calls the same helper when building each `Edit()`/`Write()` deny glob. Gate 133's mutation (12) now targets the shared helper (both `check_mutation_12` and `_mut_drop_prefix_normalization` updated accordingly, copying a mutated helper beside a copy of the classifier so its relative `BASH_SOURCE` lookup still resolves) and still fails classification (c) when the normalization is dropped. `run_compose()`'s harness now sets `GITHUB_ACTION_PATH` to the real `wing-commander-tool-args` composite directory, matching how Actions sets it in production and how `wing-commander-write-boundary-lookup`'s own harness call already did.

- [ ] Review finding: finding-kind branching hand-duplicated across three survivor slots

  The new finding-kind: defect|routed-task input is implemented as inline if/ternary branches repeated identically in all three survivor slots of wing-commander-stage-findings/action.yml instead of callers passing pre-rendered phrase strings

  - .github/actions/wing-commander-stage-findings/action.yml

  Detail: Around lines 507, 524-538, 549, 566-580, 591, 608-622; a third finding-kind or a wording tweak needs 6 copy-pasted edits, and a missed one leaves one slot stale with no gate to catch it, bakes write-boundary vocabulary into a composite meant to stay generic

- [ ] Review finding: Gate 12 token-resolution comment duplicated without a canonical pointer

  The explanation for why gh issue list must stay inline (never moved to _shared/) is independently reworded in both wing-commander-durable-failure-issue/action.yml and wing-commander-write-boundary-lookup/action.yml, with neither comment pointing at the other, violating CLAUDE.md's single-canonical-comment rule

  - .github/actions/wing-commander-write-boundary-lookup/action.yml
  - .github/actions/wing-commander-durable-failure-issue/action.yml

  Detail: write-boundary-lookup/action.yml ~lines 808-814 vs durable-failure-issue/action.yml ~lines 322-326; a future change to the Gate 12 rationale has two copies to update and nothing fails if only one is updated

- [ ] Review finding: Per-unchecked-line fingerprint lookup re-reads and re-normalizes tasks.md

  wing-commander-write-boundary-lookup/action.yml's lookup loop invokes compute-finding-fingerprint.sh once per unchecked tasks.md line, each call forking bash->python3 and re-reading/re-normalizing the whole file even though its content is identical across iterations

  - .github/actions/wing-commander-write-boundary-lookup/action.yml
  - .github/actions/_shared/compute-finding-fingerprint.sh

  Detail: Loop around lines 829-842 calling verify_anchor() in compute-finding-fingerprint.sh; for K unchecked lines this pays O(K) redundant file reads, regex normalization passes, and process forks on every finalize run while the lifecycle is open

- [ ] Review finding: run_cycle_step/run_retry_step near-identical copy-paste in gate test harness

  verify-write-boundary.py's run_cycle_step and run_retry_step duplicate the same setup and env-dict construction, differing only in a result key, which step is looked up, and one extra env key

  - .github/scripts/verify-write-boundary.py

  Detail: Around lines 1474-1513; a future fix to shared env-building logic (as already happened once with WRITE_BOUNDARY_ALL_OOB) must be pasted into both functions or they silently diverge

- [ ] Review finding: Lost watchdog.yml cross-reference when raising issue-list limit

  The deleted comment in wing-commander-durable-failure-issue/action.yml explicitly tied --limit 200 to watchdog.yml's own dedup bound; the replacement raises the limit to 1000 and only cross-references wing-commander-write-boundary-lookup, dropping the watchdog.yml parity note entirely

  - .github/actions/wing-commander-durable-failure-issue/action.yml
  - .github/workflows/watchdog.yml

  Detail: Around line 329; watchdog.yml still uses --limit 200 (lines ~3469,3484) with its own truncation-risk warning, but nothing now points at this composite's now-independent 1000 limit if watchdog's bound changes

- [ ] Review finding: Duplicate import subprocess in stage-findings python heredoc

  A new `import subprocess` was added at the top of the python heredoc in wing-commander-stage-findings/action.yml while a pre-existing `import subprocess` lower in the same block was left in place

  - .github/actions/wing-commander-stage-findings/action.yml

  Detail: Around line 365; harmless no-op re-import but a trivial cleanup a reviewer has to puzzle over
