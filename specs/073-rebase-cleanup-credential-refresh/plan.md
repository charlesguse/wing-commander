# Implementation Plan: The Last Two Agent Stages Join the Credential Sweep — rebase.yml and cleanup.yml

**Branch**: `spec/073-rebase-cleanup-credential-refresh` | **Date**: 2026-09-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/073-rebase-cleanup-credential-refresh/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Two agent-bearing jobs — `rebase.yml`'s `rebase` and `cleanup.yml`'s
`teardown-done` — mint a bot credential once, run an unbounded
`claude-code-action` step, then keep acting as the bot on the pre-agent
mint. Gate 68 (`verify-post-agent-credential-refresh.py`) cannot see either
job because its subject list is eight hand-typed workflow/job pairs. This
feature gives each job the disposition spec 072's clarified derivation rule
(#549) already decided but never implemented: `rebase.yml`'s `rebase` job
adopts spec 052's full post-agent mechanism (re-mint, remote
re-authentication, agent-ran signal, credential-status, failed-post-agent
step, all four bot-acting arms reading `env.WC_BOT_TOKEN`); `cleanup.yml`'s
`teardown-done` job instead gets a `timeout-minutes: 10` wall-clock bound on
its agent step, recorded as an exemption whose condition Gate 68 asserts
mechanically. Gate 68 itself changes shape to match: its subject set becomes
**derived** (every job in every `.github/workflows/*.yml` file with an agent
step is a subject) rather than hand-typed, checked against a checked-in
floor so a disappearing subject still fails loudly, with `watchdog.yml`'s
`diagnose` and `board-loop.yml`'s five agent steps recorded as the two
further exemptions this derivation surfaces. This resolves #410 item 1
inside this feature, per the clarification on #558, and must not contradict
the derivation-plus-floor shape #549 already decided.

## Technical Context

**Language/Version**: Python 3.11 (gate scripts, `PyYAML`'s `yaml.safe_load`
for static workflow parsing) and Bash (composite action `run:` steps); no
application language — this repository's product is its own GitHub Actions
workflows and the deterministic gates that check them.

**Primary Dependencies**: `PyYAML`; this repository's existing
`.github/scripts/wc_gate_registry.py` (drives `run-local-gates.py`'s
derivation of *which gates to run*, already generic — no change needed for
this feature per Research D-Registry); the six spec-052 composite actions
under `.github/actions/wing-commander-*` that `rebase.yml` newly consumes.

**Storage**: N/A — every artifact this feature touches is a checked-in file
(workflow YAML, a Python gate script, Markdown contracts).

**Testing**: The gate's own `--self-test` mode (in-memory mutations of the
real shipped trees, asserted to fail — no separate fixture files) plus
`python .github/scripts/run-local-gates.py`, the full local PR-time gate
suite this repository's CLAUDE.md requires before every push.

**Target Platform**: GitHub Actions (`ubuntu-latest` runners), both as the
CI environment the gate runs in and as the runtime the workflows it checks
execute on.

**Project Type**: Single project — this is a CI/CD pipeline repository; the
"source" this feature edits is workflow YAML and a gate script, not
application code.

**Performance Goals**: N/A beyond "the gate suite stays fast enough to run
on every PR" — Gate 68 is already a single static YAML parse over a fixed,
small file set; widening the file glob from 8 named paths to
`.github/workflows/*.yml` adds a handful of files, not a complexity class.

**Constraints**: FR-013/SC-007 (byte-identical observable behaviour on the
clean-rebase and normal-teardown paths); FR-015 (no published composite's
input surface widens); FR-014 (existing `if:` gating on `rebase.yml`'s
publish and abandon/escalate arms is preserved verbatim — only the
credential each arm reads and the composites around the agent step change);
Constitution VII (no stage workflow's `workflow_call` input/output/secret
surface changes — this feature adds steps inside two already-published
stage workflows, it does not touch their interface).

**Scale/Scope**: One gate script rewritten
(`.github/scripts/verify-post-agent-credential-refresh.py`); two stage
workflows edited (`rebase.yml`'s `rebase` job, `cleanup.yml`'s
`teardown-done` job); two workflows gaining a recorded-only exemption entry
with no behavioural edit (`watchdog.yml`, `board-loop.yml`); three existing
contract documents amended in place
(`specs/052-agent-credential-lifetime/contracts/*.md`); one new contract
document (this feature's own, for the derivation/exemption mechanism that
had no prior home because spec 072 never shipped code).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Guide**: Satisfied. The feature is specified, planned, and will be
  implemented through this repository's own pipeline; its lifecycle issue
  (#558) is the worked example.
- **II. Cost-Conscious Model Tiering**: N/A. No agent model, invocation, or
  turn budget changes — this feature only edits credential plumbing and
  wall-clock bounds around existing agent steps.
- **III. Simple, GitHub-Native Interaction**: Satisfied. All status is
  posted to issue #558; no new dashboard or CLI.
- **IV. Automation-First**: Satisfied. No new manual step is introduced;
  the wall-clock bound on `cleanup.yml` is the automated backstop FR-006
  requires, not a human checkpoint.
- **V. Security**: Satisfied, and directly served — the feature closes a
  window where a stale bot credential could be used past the point a
  maintainer would expect it re-established. No PAT is introduced; the App
  installation token remains the sole credential.
- **VI. Portability**: Satisfied. No repository-specific content is
  hardcoded outside `.wing-commander-pipeline`'s existing self-checkout
  convention, which `rebase.yml` and `cleanup.yml` already follow.
- **VII. Two Interfaces**: Directly engaged, no violation. `rebase.yml` and
  `cleanup.yml` are published stage workflows; this feature adds steps
  *inside* their jobs and does not touch either workflow's `workflow_call`
  inputs, outputs, or secrets — the published surface is unchanged. FR-015
  reinforces this for the composites themselves: no composite's declared
  input surface widens.
- **VIII. A Green Check Means What It Says**: This principle is the
  feature's second subject (Gate 68 itself). The derived-subject redesign
  is *because* a hand-typed list let two real defects go unchecked; the
  floor (FR-004 of spec 072) exists specifically so a disappearing subject
  still fails loudly rather than passing over a shrunk world, and every
  exemption's condition must be one the gate asserts mechanically (FR-007
  of this spec), never prose alone.
- **IX. Judgment That Gates a Durable Action Belongs in Deterministic
  Code**: Directly engaged. The exemption record for `cleanup.yml`,
  `watchdog.yml`, and `board-loop.yml` is not a comment a human trusts on
  read — each entry's condition (a wall-clock bound present and under
  threshold; composites present and consumed) is asserted by the gate's own
  code, per FR-006/FR-007.
- **X. Bounded Autonomy**: N/A. This feature is worked through the spec
  lifecycle (intake → plan → ...), not the board loop; `board-loop.yml`
  itself is touched only to record its existing composite adoption as a
  recognized exemption, with no behavioural change to the loop.

No violations. No entries required in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/073-rebase-cleanup-credential-refresh/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── gate-68-derived-subjects.md
├── checklists/
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
.github/
├── workflows/
│   ├── rebase.yml                     # `rebase` job: adopts full post-agent mechanism
│   ├── cleanup.yml                    # `teardown-done` job: gains timeout-minutes: 10 bound
│   ├── watchdog.yml                   # `diagnose` job: exemption recorded, no behavioural edit
│   ├── board-loop.yml                 # exemption recorded, no behavioural edit
│   └── lint-workflows.yml             # Gate 68 registry comment block updated (FR-017 of spec 072)
├── actions/
│   ├── wing-commander-context/                       # consumed by rebase.yml (new call site)
│   ├── wing-commander-refresh-remote/                # consumed by rebase.yml (new call site)
│   ├── wing-commander-agent-ran-signal/               # consumed by rebase.yml (new call site)
│   ├── wing-commander-post-agent-credential-status/   # consumed by rebase.yml (new call site)
│   └── wing-commander-failed-post-agent-step/         # consumed by rebase.yml (new call site)
└── scripts/
    ├── verify-post-agent-credential-refresh.py        # Gate 68: derivation, floor, exemption record
    └── run-local-gates.py                              # unchanged (already derives its gate list)

specs/052-agent-credential-lifetime/contracts/
├── wing-commander-context-relay.md         # gains rebase.yml / cleanup.yml sections
├── post-agent-credential-refresh-gate.md   # "Subject" section rewritten: derived set + floor + exemptions
└── agent-ran-signal.md                     # "Not in scope" section gains rebase.yml's rationale if applicable
```

**Structure Decision**: Single project, no new directories. This feature's
"source code" is entirely GitHub Actions workflow YAML, composite actions
already published by spec 052, and one Python gate script. No
`src/`/`tests/` split applies; the gate script's own `--self-test` is its
test suite, and `specs/052-.../contracts/*.md` remain the single
canonical documentation home per CLAUDE.md's single-home rule — this
feature amends them in place rather than forking a second copy under
`specs/073-.../contracts/`. The one genuinely new contract
(`gate-68-derived-subjects.md`, below) exists because spec 072 decided the
derivation/floor/exemption shape but never shipped the code or the doc for
it; this feature is what actually builds it, so it is this feature's
contract to author.

## Complexity Tracking

*No violations recorded — table intentionally omitted.*
