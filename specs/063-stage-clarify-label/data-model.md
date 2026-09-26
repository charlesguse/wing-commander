# Phase 1 Data Model: The Label Table Tells the Truth — `stage:clarify` Is Either Applied or Retired

This feature introduces no new persisted data store and no `spec-meta.json`
schema change. Every shape below is either an existing GitHub issue label
(already part of this repository's data model; this feature changes *who
writes it*, not its shape), a new checked-in gate/registry file, or an
ephemeral E2E-run signal.

## Lifecycle stage label (existing entity — one new writer pair)

| Field | Type | Meaning |
|---|---|---|
| name | `stage:<name>` string | Exactly one is "current" on a lifecycle issue at a time (spec.md Key Entities) |
| writer | workflow/composite | Which shipped code applies/removes it |

| Label | Applied by (before this feature) | Applied by (after this feature) |
|---|---|---|
| `stage:spec` | `intake.yml:689` (agent prompt) | Unchanged, **plus** `clarify.yml`'s new flip step's `ready` arm (D3) |
| `stage:clarify` | nothing | **New**: `intake.yml`'s new flip step (`needed=true` arm, D2); `clarify.yml`'s new flip step (`needs-clarification` arm, D3) |
| `stage:plan` | `plan.yml:1153`, `:1241` | Unchanged |
| `stage:tasks` | `tasks.yml:1205` | Unchanged |
| `stage:implement` | `implement.yml:2488` | Unchanged |
| `stage:review` | `finalize.yml:1205` | Unchanged |
| `stage:done` | `cleanup.yml:869` | Unchanged |
| `stage:stalled` | `wing-commander-chain-stop-notice/action.yml:146`, `implement.yml:2861`, `cleanup.yml:1563` | Unchanged — and `clarify.yml:1292`'s existing `stage-label: "stage:clarify"` input to that composite starts doing real removal work for the first time, with no code change to the composite itself (specs/041-implement-stall-notice/data-model.md:65) |

## New step: `Flip stage label for clarification` (one per stage)

| Stage | Placement | Reads | Writes |
|---|---|---|---|
| `intake.yml` | Immediately after `Check whether the spec still needs clarification` (`id: clarification`, lines 990-1136), before `Render clarification questionnaire` (1142) | `steps.clarification.outputs.needed`, `.specified`, `.blocked`; `steps.created.outputs.spec-dir`; `inputs.issue-number` | `needed=true`: create+add `stage:clarify`, best-effort remove `stage:spec`. `needed=false && specified=='true' && blocked!='true' && spec-dir!=''`: best-effort remove `stage:clarify` (defensive no-op on a first run — D2). Otherwise: nothing. |
| `clarify.yml` | Immediately after `Determine clarification follow-up outcome` (`id: clarification`, lines 845-932) | `steps.clarification.outputs.outcome`, `.blocked`; `inputs.issue-number` | `outcome==needs-clarification`: create+add `stage:clarify`, best-effort remove `stage:spec`. `outcome==ready && blocked!='true'`: create+add `stage:spec`, best-effort remove `stage:clarify`. `outcome==none` or `ready && blocked=='true'`: nothing. |

Both steps are gated only on `steps.lifecycle-gate.outputs.is-open ==
'true'` — the same top-level guard every other step in each job already
carries. Neither step ever exits non-zero on a label-write failure (FR-015);
the `stage:clarify`/`stage:spec` *add* failure path writes an
`::warning::` line to `$GITHUB_STEP_SUMMARY` instead (research.md D2/D3);
the best-effort *remove* calls keep the existing `2>/dev/null || true`
silent-failure idiom `plan.yml:1154-1155` already established, since a
missing label to remove is the routine case, not a failure worth reporting.

## Gate 99 subjects (new)

### Documented label set

Derived from `docs/setup.md` (the whole file, not the table alone — D7):
every backtick-quoted token matching `` `stage:[a-z-]+` ``, deduplicated.
At HEAD this yields exactly eight: `stage:spec`, `stage:clarify`,
`stage:plan`, `stage:tasks`, `stage:implement`, `stage:review`,
`stage:done`, `stage:stalled` (the last documented only in the "created on
the fly" prose at `docs/setup.md:158-160`, not a table row).

### Applied label set

Derived from every `.github/workflows/*.yml` and `.github/actions/**/
action.yml`: every literal `stage:[a-z-]+` token passed as an argument to
an ADD-shaped call — `gh issue edit --add-label`, `gh issue create
--label`/`-l`, or a REST `-f "labels[]=..."` call — reusing Gate 90's
segmentation *rules* (comment stripping, `;`/`&&`/`||`/`|`/`$(` splitting,
backslash continuation, quote handling) reimplemented locally (research.md
D7), never a read-only `--label` filter argument to `gh issue list`/`gh
search`. A bare `--remove-label` site does **not** put a label in this set
on its own (Phase 7 convergence fix): `plan.yml:1155`/`:1241`'s
pre-existing, unrelated best-effort `--remove-label "stage:clarify"` lines
otherwise satisfied this set for a label nothing ever added, which would
have let Gate 99 PASS against the pre-change tree instead of FAILing as
FR-008 requires.

### Exemption registry: `.github/scripts/lifecycle-label-taxonomy-waivers.json`

| Field | Required | Meaning |
|---|---|---|
| `file` | yes | Where the documented-but-unwritten label is declared (always `docs/setup.md` for this taxonomy) |
| `check` | yes | Fixed string `"stage-label-writer"` — the property being waived |
| `pattern` | yes | The exact `stage:<name>` label this entry exempts |
| `count` | yes | Number of documented mentions this waiver covers (stale-checked: a changed mention count fails the gate) |
| `issue` | yes | Tracking issue for the exemption |
| `reason` | yes | Free text — why no workflow writes this label on purpose |

Structurally identical to `stage-invariant-waivers.json` (Gate 31) —
`REQUIRED_WAIVER_FIELDS`-style shape check, stale-checked in both
directions, missing file == zero waivers. Direction A leaves zero live
entries at merge time (every documented `stage:*` label has a writer);
Gate 99's `--self-test` proves the mechanism (Acceptance Scenario 3) via a
synthetic fixture, independent of whether the real file holds any entries.

### Gate 99 verdict

| Outcome | Condition |
|---|---|
| PASS | Every documented `stage:*` label is either in the applied set or covered by a shape-valid, non-stale waiver |
| FAIL, names the label | A documented `stage:*` label is in neither the applied set nor the waiver registry |
| FAIL | A waiver's `pattern` matches a label that now has a writer (stale — the deviation it covered no longer exists) |
| FAIL | A waiver's `count` no longer matches the live count of documented mentions (stale — either direction) |

Gate 99 run against the pre-change tree (this PR's own parent commit) is
FR-008's required demonstration: PASS on every label except `stage:clarify`,
which FAILs with zero apply sites and zero waiver — recorded in the
implementation PR per FR-008, not asserted here.

## E2E clarification-label assertion (`auto-release.yml`, amended — no new entity)

| Signal | Source | Used for |
|---|---|---|
| `timeline` | `gh api issues/<n>/timeline` (existing, unmoved) | The list of `stage:*` labels ever applied to the E2E issue this run |
| `comments_json` | `gh api issues/<n>/comments` (existing call, **moved earlier** — research.md D5) | Both the (unmoved) `clarification_satisfied` check and the (newly early) `markers_json` computation |
| `markers_json` | `auto-release-e2e-clarify-decision.sh markers` over `comments_json` (existing script, existing mode, **called earlier**) | Whether a clarification questionnaire was ever posted this run — the FR-021 conditioning signal |
| `questionnaire_posted` | `markers_json | length > 0` | Gates whether `stage:clarify` joins `stages_to_check` |

| `questionnaire_posted` | `stages_to_check` | Step summary line |
|---|---|---|
| `true` | `stage:spec stage:plan stage:tasks stage:implement stage:review stage:clarify` | "clarification-label assertion: asserting stage:clarify in the timeline (a questionnaire was posted this run)." |
| `false` | `stage:spec stage:plan stage:tasks stage:implement stage:review` (unchanged from today) | "clarification-label assertion: skipped -- no clarification questionnaire was posted this run." |

Satisfies SC-007 (a definite outcome, asserted or explicitly skipped, every
run) and FR-021's last sentence (a silent skip is indistinguishable from no
assertion at all — this one is never silent).

## Documentation sites (FR-006) — no new entity, six sites, two require no edit

See research.md D6 for the full table and the rationale for the two sites
(`docs/setup.md:146`, `docs/architecture.md:355-357`) that already read
correctly under Direction A and are left untouched.
