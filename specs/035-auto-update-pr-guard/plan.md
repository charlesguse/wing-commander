# Implementation Plan: Auto-Update Declines to Re-Propose a Candidate Whose PR Is Already Open

**Branch**: `spec/035-auto-update-pr-guard` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/035-auto-update-pr-guard/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

`auto-update-spec-kit.yml`'s scheduled run currently has no way to ask
"have I already proposed this?" — while a version-bump PR sits open and
unreviewed, every daily run repeats the full chain (one
`claude-sonnet-5` judgment call in `evaluate-path`, a full agent-driven
`e2e-stage` run for minor/major jumps) and then fails at `act`'s push,
because the branch it targets (`auto-update-spec-kit/v$CANDIDATE`,
deterministic per candidate) already exists on the remote as a sibling
commit, not a descendant. This plan adds a guard **step** inside the
existing `evaluate-path` job — placed right after its "Resolve entry
context" step and before its first Claude-billed step — that lists open
pull requests, recognises this feature's own version-bump PRs by their
existing marker (never by title or branch name), and, when a match
exists for the settled candidate or a not-yet-adopted older one, sets a
new `guard-skip` value on the `outcome` output `prepare`'s gate already
switches on. Because `prepare`, `e2e-stage`, `verify`, and `act` already
treat any non-`clean-bump` outcome as "do not run" (the exact machinery
`needs-migration`/`ambiguous-options` proved out in
`027-auto-update-spec-kit`), this reuses existing plumbing end to end —
no new job, no new `needs:` edge, no change to either workflow's
`workflow_call` input/output/secret contract (research.md). The guard
narrates once per blocking PR on the tracking issue and refreshes a
last-checked marker every guarded run, both as new sub-fields on the
marker `settle` already owns (data-model.md) — no new state store, no
new label (Out of Scope). Independently, `act`'s "Open version-bump PR"
step gains its own pre-push check so a *leftover* branch (from a run
that failed after pushing, or a PR closed unmerged with its branch left
behind — a state `evaluate-path`'s guard cannot see, since it only ever
observes *open* PRs) fails with a message naming the blocking branch or
PR and the remedy, instead of a raw non-fast-forward rejection
(FR-015). No force-push is introduced (Out of Scope, filed as a
follow-up issue per the spec's Clarifications). Coverage for both checks
lands in the existing executable scenario harness
(`t7_gating.py`, `t5_act.sh`), which first needs a `gh pr list` handler
added to its `gh` stub (`gh_stub.py`) — confirmed absent today.

## Technical Context

**Language/Version**: Bash (GitHub Actions `run:` steps), YAML (workflow
definitions), `jq` for JSON, Python 3 (`t7_gating.py`'s real-YAML-driven
gating model, `gh_stub.py`'s stateful `gh` stub) — identical toolchain to
every other pipeline stage and to `027-auto-update-spec-kit`'s own test
harness; no new language introduced.

**Primary Dependencies**: GitHub Actions, `gh` CLI (new call this
feature adds: `gh pr list --state open --json number,body,headRefName`,
plus `--head "$BRANCH"` in `act`; every other call — `gh issue
view/edit/comment`, `gh pr create`, `git ls-remote` — already exists
elsewhere in this file and is reused verbatim), `jq`, `git`, the repo's
own `.github/actions/wing-commander-context` and
`wing-commander-callout` composites (reached via the same
pipeline-repo self-checkout every job in this file already performs).
No new external service, no new Claude/agent step — this feature adds
zero billed steps and removes redundant ones.

**Storage**: No new persisted state file, no new label. The guard's
one-time-narration dedup key (`guard-pr=N`) and last-checked liveness
signal (`guard-checked=<UTC timestamp>`) are two new optional sub-fields
appended to the existing settle-tracking marker already embedded in the
singular open tracking issue's body (data-model.md) — the same marker
`027-auto-update-spec-kit`'s `settle` step owns and the same
`count > 1` data-integrity discipline it already applies extends to this
feature's own "more than one matching open PR" case (research.md).

**Testing**: `.github/scripts/auto-update-spec-kit-tests/` — the
executable harness `027-auto-update-spec-kit` built specifically because
a desk-checked `quickstart.md` had already shipped three real defects
undetected (README.md). This feature adds scenarios to `t7_gating.py`
(job/step-level `if:` routing — the skip and proceed decisions) and
`t5_act.sh` (the PR-opening step against a pre-existing branch/PR), and
must first add a `gh pr list` handler to `gh_stub.py` (confirmed: no
`pr list` case exists today — `cmd == "pr"` only implements
`create`/`view`). `run-tests.sh` runs the whole suite in CI via
`lint-workflows.yml` (line 1425) — a hard merge gate, not an optional
check. `t9_prepare.sh` needs no change (`prepare` never runs on a
guarded cycle).

**Target Platform**: GitHub Actions (`ubuntu-latest` runners). No new
trigger — the guard step lives inside the existing `evaluate-path` job,
reachable from both of its existing entry paths (a freshly settled
candidate via `settle`, and a resumed maintainer decision via
`comment-reply`), satisfying FR-012 ("the guard MUST apply to every
entry point ... including a resumed maintainer decision") without a new
`trigger` value on the wrapper (`wing-commander-auto-update-spec-kit.yml`
is unchanged).

**Project Type**: Single project — CI/CD automation under
`.github/workflows/`, editing one existing reusable stage and its
existing test harness. No new files at the workflow level; no
frontend/backend split.

**Performance Goals**: SC-001 (zero Claude-billed stages consumed per
day a version-bump PR stays open — down from two) and SC-002 (zero
failed scheduled runs while a version-bump PR is open) are the entire
point; not latency-sensitive otherwise. The guard step itself is one
`gh pr list` call plus in-process `jq` filtering — bounded, cheap,
already the same shape as `settle`'s existing issue-list lookup.

**Constraints**: Never proceeds into a billed step when whether a
matching PR exists is unknown (FR-010); never treats a lookup failure
the same as "no matches" (research.md, `settle`'s #167-vs-#162 lesson,
reused verbatim); never recognises a PR as its own by title or branch
name alone, only by its existing body marker (FR-002); never conflates
a version-bump PR with a revert PR (FR-013); never silently picks one
match when more than one exists (FR-014); never edits, closes, or
retitles a superseded PR (FR-011, Out of Scope); never force-pushes or
overwrites an existing branch on the consumer repository (FR-018, Out
of Scope — a follow-up issue, not this feature); never adds a
per-run branch or duplicate-PR workaround (FR-017). Least-privilege: the
guard adds no new `permissions:`, no new secret, no new agent step, no
web tool. Only trusted refs are ever checked out (unchanged from
`027-auto-update-spec-kit`).

**Scale/Scope**: One existing workflow file
(`.github/workflows/auto-update-spec-kit.yml`) gains one new step in
`evaluate-path`, one new `outcome` value, and one new pre-push check in
`act`. Zero new workflow files, zero new `.specify/memory/*.json`
config, zero new repository variables or secrets. Three existing test
files change (`t7_gating.py`, `t5_act.sh`, `gh_stub.py`); `t9_prepare.sh`
does not. `docs/architecture.md`'s existing "Auto-Update Spec Kit"
section gains a bullet describing the guard (tasks-phase concern);
`docs/adoption.md`'s per-stage job-count table is unaffected, since the
guard is a step inside an existing job, not a new job (research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: This feature is itself built through the pipeline
  (issue #204 → this spec → this plan → tasks → implementation), fixing
  a defect that `027-auto-update-spec-kit`'s own scheduled run produced
  live against this repository (PR #203) — the dogfooding case constitution I asks for,
  on the pipeline's own maintenance stage. **Pass.**
- **II. Cost-Conscious Model Tiering**: This feature adds **zero** new
  model invocations — its entire purpose is to avoid an existing
  `claude-sonnet-5` call (`evaluate-path`'s "Decide upgrade path") and
  an existing agent-driven `e2e-stage` run when they would be redundant.
  No new `--model`/`--max-turns` surface to declare. **Pass.**
- **III. Simple, GitHub-Native Interaction**: The guard's entire
  narration lives on the same tracking issue every other decision in
  this stage already reports to (FR-006, FR-007) — a maintainer reads
  one place to know whether the pipeline is waiting on them (an open PR
  to review) or on itself (the schedule). No new dashboard, no new CLI,
  course correction remains "merge or close the PR." **Pass.**
- **IV. Automation-First**: The one surviving manual step this feature
  touches — deleting a leftover branch from a closed-unmerged PR — was
  already a pre-existing manual step (Out of Scope explicitly preserves
  it) and this feature makes it *legible* for the first time (FR-015:
  named branch/PR and remedy, replacing a raw push rejection) rather
  than introducing a new one. **Pass.**
- **V. Security (NON-NEGOTIABLE)**: PR bodies read by the guard are
  matched only against a fixed literal marker string (`grep -qF`/`jq
  contains`) — never interpreted as instructions, never fed to an agent
  (the guard step is pure bash/`gh`/`jq`, no `claude-code-action` call
  at all). No new web tool, no new secret, no new `permissions:`. This
  feature never merges, approves, closes, or retitles any PR — it only
  reads open/closed state and PR bodies/branch names it already has
  read access to. Auth via the same `wing-commander-bot` App token every
  other step in this job already mints via `wing-commander-context`.
  **Pass.**
- **VI. Portability**: No new consuming-repo-owned config file, no new
  repository variable. The guard resolves the repository the same way
  every other step in this file already does (`$GITHUB_REPOSITORY`, the
  existing self-checkout at `github.job_workflow_sha`) — nothing new is
  hardcoded. **Pass.**
- **VII. Two Interfaces**: `auto-update-spec-kit.yml` remains
  `workflow_call`-only; the guard step reads no `github.event.*` and no
  `vars.*` — every value it needs (`steps.entry.outputs.*`,
  `steps.ctx.outputs.token`) already exists inside the same job from
  steps that ran before it. Neither workflow's `on: workflow_call`
  input/output/secret list changes (confirmed in
  contracts/auto-update-pr-guard.md) — this feature is entirely an
  internal restructuring of the published stage's own logic, not a
  widening of its surface, which per this principle is "a deliberate
  act rather than a convenience" that this feature deliberately avoids
  needing. **Pass.**

No violations — Complexity Tracking is not needed.

## Project Structure

### Documentation (this feature)

```text
specs/035-auto-update-pr-guard/
├── plan.md                # This file (/speckit-plan command output)
├── research.md            # Phase 0 output (/speckit-plan command)
├── data-model.md           # Phase 1 output (/speckit-plan command)
├── quickstart.md           # Phase 1 output (/speckit-plan command)
├── contracts/               # Phase 1 output (/speckit-plan command)
│   └── auto-update-pr-guard.md
└── tasks.md                # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   └── auto-update-spec-kit.yml           # MODIFIED — evaluate-path job gains a guard step + a
│                                            #            `guard-skip` outcome value; act job gains a
│                                            #            pre-push branch/PR check on "Open version-bump PR"
│                                            #            (wing-commander-auto-update-spec-kit.yml, the wrapper,
│                                            #            is UNCHANGED — no new trigger, no new input)
└── scripts/
    └── auto-update-spec-kit-tests/
        ├── gh_stub.py       # MODIFIED — adds a `gh pr list` handler (confirmed absent today)
        ├── t5_act.sh         # MODIFIED — two new scenarios (pre-existing branch; pre-existing open PR)
        └── t7_gating.py      # MODIFIED — new evaluate-path step_scenario + guard-skip/proceed job scenarios

docs/
└── architecture.md          # Gains a bullet on the guard in the existing "Auto-Update Spec Kit"
                              # section (tasks-phase concern, not this plan, but the target this plan fixes)
```

No `.specify/memory/*.json` file is added or changed — this feature has
no maintainer-tunable knob of its own; its recognition rule (the version-
bump marker) and its narration cadence (FR-007) are fixed by the spec,
not repo-variable-configurable.

**Structure Decision**: Single-project CI/CD feature, no `src/`/`tests/`
split, matching `027-auto-update-spec-kit`'s own footprint and every
prior maintenance-stage feature in this repository. The change is scoped
to one existing workflow file and its existing test harness — no new
workflow file, no new job, no new trigger. `wing-commander-auto-update-spec-kit.yml`
(the thin wrapper) requires no change at all: every value the guard
needs is already available inside the reusable stage from steps that
already run before it.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is not applicable.
