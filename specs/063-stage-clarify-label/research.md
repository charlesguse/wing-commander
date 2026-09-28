# Phase 0 Research: The Label Table Tells the Truth — `stage:clarify` Is Either Applied or Retired

spec.md carries no `[NEEDS CLARIFICATION]` markers — all three open questions
were resolved on lifecycle issue #483 before this plan ran (FR-002 → wire it
up, FR-012 → flip, FR-021 → conditional assertion in scope). Phase 0 resolves
the remaining *design* questions the spec leaves to the plan, including one
decision made without a further clarification round, called out below and
reported on the lifecycle issue per this pipeline's own process.

Every line number below was independently re-verified against `HEAD`
(`0c12ced`) rather than trusted from spec.md's own citations, several of
which have drifted by small amounts since the spec was drafted (e.g.
`intake.yml:711` is now the agent's `stage:spec` add at line 689; the
clarification decision step itself is `intake.yml:990-1136`, not ~711).

## D1 — The label decision is a new, single step per stage, reading the existing decision step's output — never a second read

**Decision**: Each of intake and clarify gains exactly one new deterministic
step, placed immediately after that stage's existing clarification-decision
step, reading only `steps.clarification.outputs.*` (the same outputs
`Render clarification questionnaire` and the two `Announce *` steps already
read) — never a second parse of the agent's structured result.

- **`intake.yml`**: new step **"Flip stage label for clarification"**,
  placed right after `Check whether the spec still needs clarification`
  (`id: clarification`, lines 990-1136) and before `Render clarification
  questionnaire` (line 1142). Reads `steps.clarification.outputs.needed`,
  `.specified`, `.blocked`, `.specified` and `steps.created.outputs.spec-dir`
  — the same four values `Announce clarification needed` (1202-1210) and
  `Announce spec PR ready for review` (1230-1252) already gate on.
- **`clarify.yml`**: new step **"Flip stage label for clarification"**,
  placed right after `Determine clarification follow-up outcome`
  (`id: clarification`, lines 845-932) — `clarify.yml` has zero
  `add-label`/`remove-label` calls today (confirmed by grep), so this is a
  wholly new step, not an edit to an existing one. Reads
  `steps.clarification.outputs.outcome` and `.blocked`.

**Rationale**: FR-013 requires the label decision be "derived from the same
single, schema-validated signal that decides which callout to post, not from
an independently recomputed condition." `needed` (intake) and `outcome`
(clarify) are exactly that signal — `docs/architecture.md:372-374` names
reusing it as "the structural fix for #159," and a second read of
`$RUNNER_TEMP/claude-execution-output.json` would be precisely the
independently-recomputed condition #159 exists to forbid. Placing the new
step immediately after the decision step (rather than folding label logic
into `Render clarification questionnaire` or either `Announce *` step) keeps
`verify-clarification-gating.py` (Gate 8) untouched: Gate 8 extracts and
re-executes `INTAKE_STAGE`/`CLARIFY_STAGE`'s named `decide` step and its
`wanted` output-consuming steps byte-for-byte (`specs/032-structured-
clarification-gate/`); a wholly new step outside that `wanted` list is
outside Gate 8's scope by construction, so it needs no accommodation there.

**Alternatives considered**:
- *Fold the flip into each `Announce *` step* — rejected: `Announce
  clarification needed` and `Announce spec PR ready for review` both call
  the shared `wing-commander-callout` composite via `uses:`, which has no
  hook for an issue-label side effect; adding one would widen a composite
  whose whole job is rendering a comment, for a concern (labels) it has
  never owned.
- *One shared composite action for both stages* — considered and rejected
  for this feature's size: the two stages' branching differs enough
  (intake's is a two-way flip gated on `needed`; clarify's is a three-way
  `case` gated on `outcome`, with a `none` no-op arm intake has no
  equivalent of) that a shared composite would need its own two-mode
  interface for two ~10-line shell bodies — more contract surface than the
  ~20 total lines of duplication it would remove. `wing-commander-chain-
  stop-notice` (specs/041) is the precedent for when a shared composite is
  worth it — six-plus call sites with identical bodies; two call sites with
  different branching is not that case.

## D2 — Intake's flip: two-way, gated exactly like the two existing `Announce *` steps

**Decision**: `Flip stage label for clarification`'s body (intake.yml):

```bash
if [ "$NEEDED" = "true" ]; then
  gh label create "stage:clarify" --color 1D76DB --description "Open clarification questions" --force
  if ! gh issue edit "$ISSUE" --add-label "stage:clarify"; then
    echo "::warning::wing-commander intake: could not add stage:clarify to issue #$ISSUE (the clarification questionnaire was still posted)." >> "$GITHUB_STEP_SUMMARY"
  fi
  gh issue edit "$ISSUE" --remove-label "stage:spec" 2>/dev/null || true
elif [ "$SPECIFIED" = "true" ] && [ "$BLOCKED" != "true" ] && [ -n "$SPEC_DIR" ]; then
  gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
fi
```

gated `if: steps.lifecycle-gate.outputs.is-open == 'true'` (same top-level
guard every other step in this job shares). The `elif` branch's three
conditions are exactly `Announce spec PR ready for review`'s own guard
(`needed == 'false' && specified == 'true' && blocked != 'true' &&
steps.created.outputs.spec-dir != ''`, minus the redundant `needed ==
'false'` already implied by the `if`/`elif` split) — a defensive, silent,
best-effort `stage:clarify` removal for a label intake itself never applies
on a first run (intake's own agent step, line 689, already applies
`stage:spec` unconditionally before this step runs — FR-023's ordering).
It exists only so a retried or unusual intake run leaves no stray
`stage:clarify` behind (Edge Cases: "applying a label that is already
present, or removing one that is already absent, must be a no-op").

**Rationale — the visible-failure asymmetry (FR-015)**: the `stage:clarify`
*add* is the meaningful, run-defining write (FR-010) and gets a visible,
non-fatal failure path (`::warning::` to the step summary, never `exit 1`)
so a label-API hiccup cannot silently leave the issue mislabeled with no
record. The `stage:spec` *removal* stays silent-best-effort
(`2>/dev/null || true`), matching `plan.yml:1154-1155`'s existing precedent
for the same reason: removing a label that may already be absent is not
informative, and `gh issue edit --remove-label` exits non-zero exactly when
there is nothing to report. Neither branch uses `exit 1` or omits an
explicit failure handler for the add call, which is the concrete mechanism
satisfying FR-015's "MUST NOT... fail a run whose spec commits are already
on the branch" — a bash `run:` step in this repository's Actions runners
executes under `bash -eo pipefail` by default, so an unguarded `gh issue
edit --add-label` that fails would fail the whole step (and, absent
`continue-on-error`, the job) with nothing about the questionnaire or the
spec commits changing — a strictly worse outcome than one warning line.

**Alternatives considered**:
- *`continue-on-error: true` on the whole step* — rejected: too blunt: it
  would also swallow a genuine script bug (bad quoting, undefined `$ISSUE`)
  with no visible signal at all, where the explicit `if ! ...; then warn;
  fi` shape reports exactly the one failure mode FR-015 is about (the
  label API call itself) and lets anything else in the step still fail loud.

## D3 — Clarify's flip: three-way `case` on `outcome`, `ready` arm additionally gated on `blocked`

**Decision**: `Flip stage label for clarification`'s body (clarify.yml):

```bash
case "$OUTCOME" in
  needs-clarification)
    gh label create "stage:clarify" --color 1D76DB --description "Open clarification questions" --force
    if ! gh issue edit "$ISSUE" --add-label "stage:clarify"; then
      echo "::warning::wing-commander clarify: could not add stage:clarify to issue #$ISSUE (the follow-up questionnaire was still posted)." >> "$GITHUB_STEP_SUMMARY"
    fi
    gh issue edit "$ISSUE" --remove-label "stage:spec" 2>/dev/null || true
    ;;
  ready)
    if [ "$BLOCKED" != "true" ]; then
      gh label create "stage:spec" --color 1D76DB --description "Spec drafted / awaiting review" --force
      if ! gh issue edit "$ISSUE" --add-label "stage:spec"; then
        echo "::warning::wing-commander clarify: could not add stage:spec to issue #$ISSUE (the spec PR was still announced ready)." >> "$GITHUB_STEP_SUMMARY"
      fi
      gh issue edit "$ISSUE" --remove-label "stage:clarify" 2>/dev/null || true
    fi
    ;;
  none|*)
    ;;
esac
```

gated `if: steps.lifecycle-gate.outputs.is-open == 'true'`. `outcome=none`
(`answered != true`, line 866) is a genuine no-op for labels — Edge Cases'
"second clarification round" scenario and #366's comment
(`clarify.yml:1057-1065`) both establish that `none` is the agent's own
early STOP with nothing folded into the spec, so the issue's stage is
unchanged either way.

**Rationale for the `ready` arm's extra `blocked` guard**: unlike intake
(D2, where `blocked` cannot be true when `needed=true`, only ever inside the
`else` branch that also computes `outcome`), clarify's `blocked=true`
(line 928) is set *after* `outcome` already reads `ready` (line 873) — the
marker cross-check runs inside the same `else` block, so `outcome=ready &&
blocked=true` is a real, reachable combination, exactly mirroring `Announce
spec PR ready for review`'s own two-condition guard (`outcome == 'ready' &&
steps.clarification.outputs.blocked != 'true'`, line 1046). Flipping the
label back to `stage:spec` on a blocked `ready` would restore the "awaiting
review" label over a spec.md the cross-check just refused to announce as
reviewable — the same silent-loss shape FR-013/FR-002's "structural fix for
#159" exists to prevent, now applied to the label instead of the callout.

**Alternatives considered**: none distinct from D2's — the `add`/`remove`
visibility asymmetry and the create-before-add pattern (D4) are identical
in shape; only the branch count and the extra `blocked` guard differ, both
required directly by clarify's own decision step's shape.

## D4 — Create-before-add applies to both new labels, not just `stage:clarify`

**Decision**: Every `gh issue edit --add-label` this feature introduces is
preceded by its own `gh label create ... --force` in the same step — for
`stage:clarify` (both stages) and, in clarify's `ready` arm, for
`stage:spec` too, even though `stage:spec` is documented as maintainer-
created (`docs/setup.md:175`) and normally already exists by the time
clarify runs.

**Rationale**: `plan.yml:1149-1151`'s own comment states the rule generally
— "single-stage adopters have no label taxonomy" — not narrowly for
`stage:plan`. The Edge Cases entry ("An adopter repository with no label
taxonomy at all... A new `--add-label` that assumes the label exists fails
the step on those repositories") makes no exception for a label a maintainer
was told to pre-create; the E2E scratch repository this pipeline drives
against itself is exactly such a from-scratch adopter (`specs/055-
unattended-e2e-gates/`), and `stage:spec` there is created lazily by
whichever earlier step first applies it, not by a human running
`docs/setup.md`'s script. `gh label create --force` is idempotent (creates
if absent, silently updates color/description if present, never errors) —
the redundant call against a repository that already has the label costs
one fast, harmless API round-trip.

## D5 — FR-005/FR-021: the label-timeline comment is corrected, and the assertion is made conditional by reusing the E2E harness's existing marker read, moved earlier

**Decision**: `auto-release.yml`'s pass-path stage-label-timeline check
(lines 1142-1158) is restructured in two ways:

1. **The stale comment (FR-005)** — lines 1143-1146, *"stage:clarify is
   never applied as an issue label by any stage workflow ... requiring it
   here made a genuine pass impossible"* — is replaced with one stating the
   post-change truth: `stage:clarify` is applied while questions are open
   and cleared when they are answered, so it belongs in the timeline
   **only on a run that actually posted a questionnaire** — a zero-question
   spec never carries it, which is why the check below is conditional
   rather than unconditional (FR-021's own rationale, restated at the
   comment's new home).
2. **The read this needs already exists, just later in the file (FR-021)**
   — `auto-release-e2e-clarify-decision.sh markers` (the exact predicate
   `specs/055`'s research.md D12 names as "the single home" for "did a
   clarification-question marker comment ever appear") is already computed
   at line 1275, from `comments_json` read at lines 1244-1250 — both
   *after* the label-timeline check at line 1142. This plan moves the
   `gh api .../comments` read and the `markers_json="$(... markers ...)"`
   computation to immediately after the existing `timeline`/`timeline_raw`
   read (before line 1142), so `markers_json` is available to gate the
   label-timeline loop. The `clarification_satisfied="$(... satisfied
   "$author_id" ...)"` check (line 1267-1274, which additionally needs
   `author_id`) stays at its current relative position, now consuming the
   already-computed `comments_json` rather than reading it a second time —
   a strict simplification, not a new read.
3. **The loop itself** gains a conditional fifth stage:
   ```bash
   stages_to_check="stage:spec stage:plan stage:tasks stage:implement stage:review"
   questionnaire_posted="$(printf '%s' "$markers_json" | jq -e 'length > 0' >/dev/null 2>&1 && echo true || echo false)"
   if [ "$questionnaire_posted" = "true" ]; then
     stages_to_check="$stages_to_check stage:clarify"
     echo "clarification-label assertion: asserting stage:clarify in the timeline (a questionnaire was posted this run)." >> "$GITHUB_STEP_SUMMARY"
   else
     echo "clarification-label assertion: skipped -- no clarification questionnaire was posted this run." >> "$GITHUB_STEP_SUMMARY"
   fi
   for s in $stages_to_check; do
     ...
   done
   ```
   satisfying SC-007's "reports a definite outcome... in every run" —
   asserted or explicitly skipped, both written to the step summary, never
   a silent skip indistinguishable from today's missing assertion.

**Rationale**: FR-021 requires the assertion be "conditional on that run's
intake having actually posted a questionnaire, read from the same
clarification-needed signal FR-013 names." The E2E harness runs outside the
stage workflows themselves (it drives them over the GitHub API from
`auto-release.yml`, a different workflow entirely), so it cannot read
`steps.clarification.outputs.needed` directly — `specs/055`'s own
established pattern for this exact problem is `auto-release-e2e-clarify-
decision.sh`'s `markers` mode, which independently detects a posted
questionnaire from the issue's comment history using the same marker
convention (`## Question N`) the render step emits. Reusing it here rather
than inventing a second "was a questionnaire posted" detector is the
literal CLAUDE.md "single home" rule already cited by the comment at line
1233 for the neighboring `satisfied` check ("the single home CLAUDE.md
requires, not re-derived here a second time — maintainer feedback on PR
#389"); duplicating that detection a second way for the label check would
repeat exactly the mistake that comment records fixing.

**This decision is made without further clarification** (spec.md leaves
FR-021's *mechanism* open, only its outcome) and is reported on the
lifecycle issue: reordering an existing, already-tested read earlier in a
588-line inline script carries real regression risk in a script this
security- and evidence-sensitive, so it is called out explicitly rather
than left implicit in a diff.

**Alternatives considered**:
- *A second, independent `gh api .../comments` read placed directly above
  the label-timeline loop, left duplicated* — rejected: doubles a paginated
  API read `auto-release.yml` already treats as expensive enough to guard
  with `fail_infra_on_read` (lines 1244-1249), and reintroduces exactly the
  "the marker predicate... re-derived here a second time" defect the
  existing comment at line 1233 already fixed once for the neighboring
  check.
- *Assert `stage:clarify` unconditionally, now that it has a writer* —
  rejected outright: this is the literal `auto-release.yml:1143-1147`
  regression FR-021 exists to not reproduce, restated for the label instead
  of the comment-reply gate; the E2E harness's own zero-question runs
  (a spec with no discernible open question) never enter the clarify state.

## D6 — Documentation sites corrected (FR-006), verbatim where the fix is mechanical

**Decision**: every FR-006 site gets the direction-A-consistent text, no
site invents new prose beyond what the flip requires:

| Site | Change |
|---|---|
| `docs/setup.md:146` (table row) | Unchanged text ("Spec has open clarification questions") already reads correctly under Direction A; no edit needed — confirmed by reading it fresh rather than assumed from the Overview table's framing. |
| `docs/setup.md:175` (creation script) | Unchanged — the label still needs pre-creating for adopters who skip the E2E-only create-before-add path (D4) on their very first run. |
| `docs/architecture.md:355-357` | Unchanged — already reads "`stage:spec` or `stage:clarify`," the correct Direction-A trigger set; this line was already accurate before this feature (only the code was missing, not the doc). |
| `docs/architecture.md:372-374` | Gains one clause naming the label write as a second consumer of the same single derived output, alongside the callout — "Both callouts, and the stage-label write that now accompanies them, key off a single output..." |
| `docs/adoption.md:229` | Unchanged — byte-identical to the shipped `wing-commander-2-clarify.yml:25` condition already (verified by direct comparison); FR-003's "MUST agree" acceptance criterion is already satisfied today and stays satisfied, since this feature does not touch the trigger condition on either side. |
| `docs/adoption.md:1125` (intake "Side effects" row) | `spec:NNN-slug` + `stage:spec` labels" gains ", flipped to `stage:clarify` while clarification questions are open" so the row states the conditional outcome, not just the unconditional one. |
| `docs/adoption.md:1163` (clarify "Side effects" row) | Gains "; `stage:clarify` applied on a follow-up question, or flipped back to `stage:spec` when the spec is ready for review" — today's row lists no label effect at all, because clarify never wrote one. |

**Rationale**: FR-006 lists exactly these sites; nothing here is inference
beyond confirming, by reading each one, whether Direction A actually
requires new prose or the existing prose was already accurate (two of six
sites need no edit — recorded above rather than silently assumed, since an
unnecessary edit is itself a drift risk this repository's "load-bearing
comments" convention warns about).

## D7 — Gate 105: a new, self-contained script — not a refactor of Gate 90

**Decision**: FR-007's gate ships as a new, self-contained
`.github/scripts/verify-lifecycle-label-taxonomy.py` (next available gate
number: **99** — the highest in `lint-workflows.yml` today is Gate 98,
`verify-board-loop-helper-provenance.py`, confirmed by reading every
`name: "Gate NN` line in the file, not merely a prior spec's citation).
It does **not** import from or refactor `verify-board-label-creation.py`
(Gate 90, 1201 lines) — the closest existing precedent for "derive an
applied-label set from every workflow and composite action's `gh issue
edit`/`gh issue create` calls, robust to `;`/`&&`/`|`/`$(...)`
segmentation and blind to read-only `--label` filters."

**Rationale**: Gate 90's segmentation logic (`_line_segments`,
`_labels_applied_in_segment`, `_iter_applies`, `_unquote`,
`_labels_in_value`) is real, tested, and exactly the shape FR-007's
"applied label set" side needs — but it is private to that script (no
`wc_`-prefixed shared module exists for it; `wc_gate_registry.py`'s own
`WHY THIS EXISTS` doc states the convention explicitly: `wc_*.py` is the
*only* recognized shared-module shape, and every other `verify-*.py` in
this repository that reuses logic across gates does so through one). Most
gates in this repository (the majority of the ~50+ `verify-*.py` scripts)
are self-contained rather than importing a sibling gate directly, and the
few that do share (e.g. `verify-gate-15.py`, `verify-chain-stop-refusal-
exclusion.py`) share through a `wc_*` module built for that specific
narrow concern (a GHA expression evaluator, a lint-source extractor) — not
by importing another gate's whole module. Extracting Gate 90's scanner into
a new `wc_label_apply_scan.py` shared module, refactoring Gate 90 itself to
consume it, is a real option but widens this feature's blast radius onto a
gate (90) with 1201 lines and 20+ self-tests that this feature has no other
reason to touch, for a scope Gate 105 needs only a subset of (Gate 90 is
job-scoped and create-before-apply-ordered; Gate 105 is repo-wide and
existence-only — "does *some* site create this label before *some* site
applies it," with no job-boundary requirement, since FR-001 only asks
whether a writer exists at all). Gate 105 therefore reimplements the same
segmentation *shape*, scoped to what it needs (existence, not ordering),
as a same-file scanner — the size cost is small (a few hundred lines
against Gate 90's 1201, most of it in Gate 90's per-job walk this feature
does not need) against the regression risk of touching Gate 90's fixtures
for a concern it was not built to check.

**What Gate 105 actually checks** (data-model.md and contracts/lifecycle-
label-taxonomy-gate.md detail the mechanism):
- **Documented set**: every backtick-quoted `stage:[a-z-]+` token appearing
  anywhere in `docs/setup.md` (table rows, the creation script, and prose
  such as "`stage:stalled` labels are created on the fly") — deliberately
  not scoped to the table alone, so `stage:stalled` (documented only in
  prose, per the Overview table in spec.md) is not silently excluded.
- **Applied set**: every literal `stage:[a-z-]+` token passed to
  `gh issue edit --add-label`/`--remove-label`, `gh issue create --label`/
  `-l`, or a REST `-f "labels[]=..."` call, across every `.github/workflows/
  *.yml` and every `.github/actions/**/action.yml`, using the same
  segmentation rules Gate 90 established (comment stripping, `;`/`&&`/`||`/
  `|`/`$(` splitting, backslash-continuation joining, quote handling) —
  reimplemented locally rather than imported (this decision).
- **Exemption registry** (FR-007's second half): `.github/scripts/
  lifecycle-label-taxonomy-waivers.json`, structurally identical to
  `stage-invariant-waivers.json` (Gate 31's registry) — `{file, check,
  pattern, count, reason, issue}` per entry, stale-checked in both
  directions (a waiver whose label now has a writer fails the gate; a
  waiver whose documented-but-unwritten label count changed fails the
  gate). A missing file means zero waivers, matching Gate 31's own
  `load_waivers()` convention — Direction A leaves this feature with zero
  live exemptions (every `stage:*` label has a writer after this change),
  so the registry ships either absent or with an empty `"waivers": []`
  list; Acceptance Scenario 3's exemption mechanism is proven by Gate 105's
  own `--self-test` fixture, not by a live entry this feature has no
  reason to add.
- **Failure mode (FR-008)**: run against the pre-change tree (this
  feature's own `git stash`/pre-PR state), the gate names `stage:clarify`
  as documented with zero apply sites and zero waiver — this is FR-008's
  required demonstration, recorded in the implementation PR, not asserted
  in prose here.

## D8 — Wiring: one `lint-workflows.yml` step, no manifest edit anywhere else

**Decision**: Gate 105 is wired by adding exactly one `run:` step to
`lint-workflows.yml` (`run: python3 .github/scripts/verify-lifecycle-label-
taxonomy.py`), following the `Gate 98`/`Gate 98 self-test` two-step pattern
already established for the newest gates in this file. No other file needs
editing for wiring purposes.

**Rationale**: `wc_gate_registry.py`'s own module docstring states the
mechanism precisely: `.github/scripts/verify-*.py` "MUST be invoked by a
workflow" and is discovered by **filename glob**, never a maintained list;
`verify-gate-wiring.py` (Gate 10) and `run-local-gates.py` both derive their
gate sets from `wc_gate_registry.py`'s `gate_scripts()`/`invocations()`
walk over every workflow's `run:` blocks. FR-009's three requirements
("wired into `lint-workflows.yml`," "discovered by `verify-gate-wiring.py`
(Gate 10)," "invoked by `run-local-gates.py`") are three observable
consequences of one mechanical fact, not three separate registration steps
— confirmed by reading `wc_gate_registry.py` directly rather than assuming
Gate 10 needs its own edit the way `#149`'s original release.yml Gate 1b
list did (the defect that motivated `wc_gate_registry.py`'s existence in
the first place). `check_subject_triggers()` (part of Gate 10) additionally
requires that any `docs/*.md`/`specs/*/contracts/*.md` string constant
appearing in the new gate's source be covered by `lint-workflows.yml`'s
`pull_request.paths:` filter — `"docs/setup.md"` is already listed there
(confirmed by reading the filter directly), so Gate 105's own `docs/
setup.md` literal needs no filter edit either, as long as the string
appears as an actual Python string constant (not only in a comment) in the
new script's source, per `_string_constants`'s AST-based reader.
