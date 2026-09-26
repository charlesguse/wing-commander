# Implementation Plan: Fine-grained maintainer token for the auto-release end-to-end harness

**Branch**: `spec/066-fine-grained-maintainer-token` | **Date**: 2026-09-26 | **Spec**: [specs/066-fine-grained-maintainer-token/spec.md](./spec.md)

**Input**: Feature specification from `/specs/066-fine-grained-maintainer-token/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

`auto-release.yml`'s `verify-e2e` job authenticates the fixture maintainer
identity with a classic PAT whose "contained to the test repository alone"
property rests on the account's own memberships, because a fine-grained PAT
cannot be scoped to a repository the account merely collaborates on
(specs/055-unattended-e2e-gates D1). This plan transfers the disposable test
repository to the machine account (a one-time maintainer act, not new code),
which lets a fine-grained token be issued self-scoped to that one
repository, and extends the existing "Confirm the fixture maintainer
identity's credential" step so containment becomes a property the credential
carries rather than one the account's memberships merely happen to produce
today. The precheck detects which of the two accepted shapes
(research.md D1) the secret holds from the token's own literal prefix — a
deterministic string match, never an API round trip — and applies the
shape-specific checks FR-003/FR-016 require: the classic path is unchanged
from specs/055; the fine-grained path additionally probes, via accept/reject
behavior against fixed REST endpoints (research.md D5/D6), that the token
carries Issues and Pull-requests write and carries no Administration
permission, and reads the token's own expiry from a response header GitHub
attaches to fine-grained credential requests (research.md D2) to satisfy the
new expiry warning/rejection requirement. The existing repository-reachable-
set containment check (specs/055 D2, gate 67) is reused for both shapes with
one correctness fix — a `gh api` transport failure must stop being
indistinguishable from "reached zero repositories" (research.md D4) — rather
than replaced, because it already generalizes to a fine-grained token's own
narrower `/user/repos` view (research.md D3). A single new gate enforces
FR-017/FR-018's "one canonical statement" requirement across the four sites
the spec names (docs/setup.md, the workflow comment, gate 67's own
expectation text, and specs/055's superseded decision), which sit outside
existing Gate 47's workflow-comment-only scope (research.md D7). No published
stage workflow changes, and no adopter-facing surface changes (FR-021):
every touched file is this repository's own wrapper, its `.github/scripts/`
gates, and its documentation.

## Technical Context

**Language/Version**: Bash (POSIX-ish, matching the rest of `auto-release.yml`) driven from GitHub Actions YAML; `jq` for JSON construction/inspection; Python 3 for the gate scripts under `.github/scripts/` (matching the existing `verify-auto-release-credential-step.py` / `verify-comment-canonical-pointers.py` pattern).

**Primary Dependencies**: GitHub CLI (`gh`) against the test repository's REST/GraphQL surface (`gh repo view`, `gh api user`, `gh api user/repos`, and the new permission-probe calls of research.md D5/D6); the existing `_shared/auto-release-verdict.sh` helper (unchanged shape, FR-021); no new external dependency.

**Storage**: N/A — all credential state is GitHub-native (the secret's own literal value, GitHub's REST response headers, and the account's repository memberships); nothing is persisted to this repository's own tree beyond the workflow/script/doc changes themselves.

**Testing**: Python fixture-style unit tests under `.github/scripts/`, extending the existing `verify-auto-release-credential-step.py` (Gate 67) with both credential shapes' scenarios and a stubbed `gh` covering the new probe calls, plus a new gate script for FR-017/FR-018's canonical-statement sweep — both wired into `lint-workflows.yml`'s gate registry and picked up automatically by `run-local-gates.py` (Constitution VIII: same subject, same arguments, locally and in CI). Every new failure branch ships a checked-in fixture and a mutation that must break at least one assertion (FR-015).

**Target Platform**: GitHub Actions hosted runner (`ubuntu-latest`), inside the existing `verify-e2e` job of `auto-release.yml` — schedule/`workflow_dispatch`-only, unchanged.

**Project Type**: Single project — this is a CI/CD workflow feature (GitHub Actions YAML + shell + Python gate scripts), not an application with a src/tests split.

**Performance Goals**: N/A (not a request-serving system); the relevant budget is that every new check runs before any gate-driving spend (FR-007/FR-008), adding at most a handful of read-only API calls to a job that already makes several.

**Constraints**: No modification to any published stage workflow or to the documented adopter-facing wrapper set (FR-021, Constitution VII); no verdict schema change (FR-021, specs/045/055's six-field shape is reused unmodified); the credential itself must never appear in any verdict, log line, or step output, and neither may the machine account's login unredacted (FR-009, the exact defect Gate 67 already exists to catch — specs/055 review #396); dual acceptance (FR-003) must not let a classic credential silently gain or lose any check it has today, and must not apply the Administration-absence bound to a shape that cannot satisfy it (FR-016); every one of FR-008's five distinguishable failure names must remain distinguishable after the shape branch is added.

**Scale/Scope**: One step ("Confirm the fixture maintainer identity's credential") in one job of one workflow gains shape-detection and shape-conditional branches; one existing gate script (Gate 67) gains scenarios and mutations for both shapes; one new gate script enforces the single-canonical-statement requirement; `docs/setup.md` §2's existing secret row becomes the canonical statement (rewritten, not duplicated) and may gain one new §3 repository-variable row for the expiry warning window (research.md D2); `specs/055-unattended-e2e-gates/research.md` and its Clarifications session gain an annotation pointing at this feature's decision, preserved as history (FR-019) rather than rewritten. No new jobs, no new workflows, no new composite actions resolved by any published stage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Guide — repo is its own first example | This feature is itself specified, planned, and implemented through the pipeline (spec/plan/tasks/implement on issue #506). No violation. |
| II. Cost-Conscious Model Tiering | No new Claude/agent invocation is introduced — every shape-detection, permission-probe, and containment decision is deterministic shell/Python (research.md D1/D3/D4/D5/D6, Constitution IX), not a model call. N/A, not a violation. |
| III. Simple, GitHub-Native Interaction | Unaffected — this feature changes only an internal verification job's own credential handling, not how a requester interacts with the pipeline. |
| IV. Automation-First | Advances this principle: rotation stays a secret-only maintainer act (SC-003, FR-006) with no workflow change, and the one manual step this feature adds — the one-time repository transfer and its fallout (App reinstall, secret/variable re-pointing) — is stated explicitly as a maintainer prerequisite (Edge Case "Ownership move fallout"; quickstart.md Prerequisites), never silently assumed. |
| V. Security — untrusted content is never instructions; humans merge to `main`; the bot never merges to `main` | Unaffected by this feature's own change: the fixture maintainer identity still only ever authenticates against the disposable test repository (never this repository, FR-004), and still never touches `main` of any repository the pipeline itself governs. This feature narrows blast radius further — a self-scoped, expiring, Administration-bounded credential is a strictly tighter guarantee than specs/055 shipped, not a widening of what the identity can do. Reviewed, no violation. |
| VI. Portability | Unaffected — nothing here is read from or resolved into a consuming repository; this is entirely this repository's own wrapper-level verification. |
| VII. Two Interfaces | The only files touched are the consuming instrument (`auto-release.yml`), this repository's own `.github/scripts/` gates and `lint-workflows.yml` registry, and its own documentation (`docs/setup.md`, `specs/055-.../research.md`). No published `workflow_call` stage or `.github/actions/**` composite resolved by an adopter's pipeline changes. FR-021 satisfied by construction. |
| VIII. A Green Check Means What It Says | Central to FR-015/FR-018: Gate 67's mutation-tested pattern is extended, not replaced, for the new shape and probe branches, and the new canonical-statement gate must itself demonstrably fail on a fixture that reintroduces a contradicting statement (research.md D7, contracts/canonical-statement-gate.md). The `gh api` exit-status fix (research.md D4) is itself an instance of this principle: today's containment check cannot currently tell "reached nothing" from "could not observe," which is exactly the vacuous-pass shape this principle forbids. |
| IX. Judgment That Gates a Durable Action Belongs in Deterministic Code | Every new decision this feature adds — which shape a token is, whether a probe response means "granted" or "not granted," whether the reachable set equals the configured repository — is a fixed string/status-code comparison in shell or Python, never a model's judgment call. No agent participates in `verify-e2e` at all, unaffected by this feature. |
| X. Bounded Autonomy — The Pipeline Works Its Own Board | N/A — this issue needed the owner's own trade-off decisions (Q1–Q3, already answered on issue #506 before this plan started) and was correctly routed as `spec-request` under CLAUDE.md's routing rule, not board-loop work. |

No entries required in Complexity Tracking — no principle is violated. The
dual-acceptance branching FR-003 requires is spec-mandated complexity, not a
plan-introduced one, and is bounded to a single step.

## Project Structure

### Documentation (this feature)

```text
specs/066-fine-grained-maintainer-token/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command)
│   ├── credential-precheck.md
│   └── canonical-statement-gate.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── auto-release.yml          # MODIFIED: "Confirm the fixture maintainer identity's
│   │                               #   credential" step gains shape detection and the
│   │                               #   shape-conditional branches of contracts/credential-precheck.md;
│   │                               #   its comment block becomes the pointer to docs/setup.md,
│   │                               #   not a restatement (FR-017)
│   └── lint-workflows.yml        # MODIFIED: registers the new canonical-statement gate
├── actions/
│   └── _shared/
│       └── auto-release-verdict.sh   # UNCHANGED — no new outcome value, no schema change (FR-021)
└── scripts/
    ├── verify-auto-release-credential-step.py    # MODIFIED: scenarios and mutations for
    │                                               #   both credential shapes and every new probe
    └── verify-<canonical-statement-gate>.py       # NEW — contracts/canonical-statement-gate.md
                                                     #   (numbered at implementation time; Gate 99
                                                     #   is the next free slot as of this plan)

docs/
└── setup.md                       # MODIFIED: §2's existing secret row becomes the canonical
                                     #   statement (dual shape, expiry, rotation, the
                                     #   Administration bound); §3 gains the expiry-warning-window
                                     #   variable row if research.md D2's default is not hardcoded

specs/055-unattended-e2e-gates/
├── research.md                    # MODIFIED: D1/D2 gain an annotation pointing at this
│                                    #   feature's decision — preserved as history, not rewritten (FR-019)
└── spec.md                        # MODIFIED: the Clarifications session gains the same
                                     #   annotation, same reason

specs/066-fine-grained-maintainer-token/
├── plan.md               # This file
├── research.md            # Phase 0 output
├── data-model.md          # Phase 1 output
├── quickstart.md          # Phase 1 output
└── contracts/             # Phase 1 output
    ├── credential-precheck.md
    └── canonical-statement-gate.md
```

**Structure Decision**: Single project — this feature has no application
source tree, only workflow/script/doc edits inside the paths above. Nothing
under `.github/workflows/<stage>.yml` (the published contract) or
`docs/adoption.md` (the adopter-facing surface) changes, per FR-021 and
Constitution Principle VII; every touched path is either this repository's
own consuming-instrument wrapper, its own `.github/scripts/` gate suite, or
this-repository-only documentation and spec history.

## Complexity Tracking

*No entries — the Constitution Check above found no violation requiring
justification.*
