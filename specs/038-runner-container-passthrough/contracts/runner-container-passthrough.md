# Contract: Runner and Container Passthrough

Governs every one of Wing Commander's eleven published `workflow_call`-only
stage workflows (FR-001 through FR-018). Companion to
`specs/010-reusable-pipeline/contracts/stage-interfaces.md`'s "Common
inputs" table, which implementation amends with the rows below (that edit is
scoped to the implementation stage, not this plan's own artifacts — see
`plan.md` Project Structure), and to
`specs/031-stage-environment-binding/contracts/environment-binding.md`,
whose `environment:` mapping-form precedent this contract's `container:`
mechanism follows structurally.

## New stage inputs and secrets (all eleven published stages: intake,
clarify, plan, tasks, implement, finalize, cleanup, watchdog,
pr-conversation, rebase, auto-update-spec-kit — research D1)

| Name | Kind | Type | Default | Required |
|---|---|---|---|---|
| `runner` | input | string | `ubuntu-latest` | never (optional, off by default — FR-001) |
| `container-image` | input | string | `""` | never (optional; off by default — FR-004) |
| `container-registry-username` | secret | — | — | never (`required: false`; meaningful only when `container-image` is non-empty — FR-009) |
| `container-registry-password` | secret | — | — | never (`required: false`; same conditionality) |

No changes to any existing input, secret, `permissions:` block, or output of
any stage — this is a strictly additive interface change (FR-013).

## Binding mechanism (research D2, D3)

Every job in every one of the eleven stage files that has no local `uses:`
(all 33 jobs today) gains:

```yaml
jobs:
  <job-id>:
    runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
    container:
      image: ${{ inputs.container-image }}
      credentials:
        username: ${{ secrets.container-registry-username }}
        password: ${{ secrets.container-registry-password }}
```

added unconditionally — no `if:` on either key, no per-job selection, no
distinction between agent-bearing and agent-free jobs (FR-007, User Story 4
acceptance scenario 1 analog: "which jobs move is not a hidden internal
rule"). Byte-for-byte identical across all 33 jobs — Gate 22 (below) checks
this directly.

**A job whose body is a local `uses: ./.github/workflows/<other>.yml` call
is exempt** — `runs-on:`/`container:` are illegal on such a job (they belong
to the *called* workflow's own jobs), the identical carve-out Gate 7 already
applies for `environment:`. No job in any of the eleven stages is shaped
this way today (research D1's inventory), so this exemption is currently
theoretical but must be preserved for any future stage that adds one.

### Runner selection: single label vs. multi-label conjunction (FR-002, FR-003)

- A `runner` value that does **not** start with `[` is read as one label:
  `runs-on: my-runner-label`.
- A `runner` value that starts with `[` is parsed as JSON
  (`fromJSON(inputs.runner)`) and applied as a **list of labels** — GitHub's
  own conjunction semantics for a `runs-on:` list (a runner must carry
  *every* named label): `runs-on: [self-hosted, linux, x64]`.
- This is the entire convention. There is no third form, no partial-array
  syntax, and no pipeline-side validation that the JSON actually parses —
  a malformed JSON-looking string (starts with `[` but is not valid JSON)
  fails at GitHub's own expression-evaluation time with GitHub's own error,
  not a pipeline-authored one (FR-008: pass-through, unvalidated).

**Not yet empirically verified** (research D2): the `startsWith(...) &&
fromJSON(...) || ...` idiom's behavior on `runs-on:` specifically has not
been run against a live GitHub Actions job in this planning pass. FR-018
requires this contract to be traceable back to recorded evidence once that
verification happens — implementation must record the result (success or a
needed mechanism change) here or in a linked follow-up, the same way
specs/031's contract records its own probe evidence inline.

**Still unverified after implementation (2026-08-18)**: the implement stage
that wired this feature has no `gh workflow run`/`gh run view`/`gh api`
access under its fixed tool allowlist, so it could not dispatch T001's
throwaway probe workflow or observe the result. See research.md D2's T001
outcome note. A human (or a future run with broader tool access) must still
perform this probe against a scratch adopter repository before this claim
is treated as proven.

### Container image: empty means no container (FR-004, FR-005)

**Not yet empirically verified** (research D3, restated here as the
contract's own central open question): whether an empty `image:` value in
the mapping form above is a true no-op — no pull, no container, no
container-related step or failure — is the entire premise User Story 2's
"zero-change guarantee" rests on, and it is asserted here only as the
requester's own stated expectation (spec's "Anything else?" answer), not as
verified fact. **This is the single highest-risk unverified claim in this
contract.** Implementation must probe it (mirroring
[charlesguse/wc-env-probe](https://github.com/charlesguse/wc-env-probe),
specs/031's own evidence source) before this feature is considered done, and
record the outcome — including the contingency spec.md's Edge Cases section
already names if the probe disproves the hoped-for behavior: "the pipeline
needs another way to express 'no container' — and whatever that is must
still leave unset adopters byte-for-byte unchanged."

**Still unverified after implementation (2026-08-18)**: the same tooling
gap noted above (no `gh workflow run`/`gh run view`/`gh api` access) applies
here too — see research.md D3's T001 outcome note. The design proceeds on
the requester's stated expectation only; this remains an unproven claim
pending a human (or a future run with broader tool access) running the
probe.

## Timing invariant — why credentials and the prerequisite check cannot live inside the real job (research D4, D5)

A job's `container:` (image *and* credentials) resolves before any step in
that job runs — the same structural timing class as specs/031's
`environment:` protection rules. Two consequences follow directly, both
load-bearing for this contract's shape:

1. **A credential minted by a step inside the stage is always too late.**
   Token-based and cloud-registry (ECR/GCR/ACR) credentials MUST be minted
   by the **calling wrapper**, in a step before its `uses:` call, and passed
   in as `secrets.container-registry-password` (FR-009a). The stage never
   mints, refreshes, or manages a credential's lifecycle.
2. **No step inside the real job can improve a failed pull's error message
   or check the image's tool contents before the job's own steps begin** —
   by the time any step of that job runs, the pull has already succeeded (in
   which case the image's contents ARE inspectable) or already failed (in
   which case nothing runs at all). This is why the prerequisite check and
   the credential-failure message (below) live in a *separate* job.

## The `verify-image-prerequisites` job (research D5) — FR-010, FR-011

Every stage file gains one new job:

```yaml
verify-image-prerequisites:
  if: inputs.container-image != ''
  runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
  # Deliberately no container: — this job must run directly on the runner
  # so it can invoke Docker itself, before the real per-job container is
  # created by any other job in this file.
  steps:
    # 1. Attempt registry login (only if both credential secrets are
    #    non-empty) and pull inputs.container-image.
    # 2. On failure: fail the job with a message distinguishing "no
    #    credentials were supplied" (both secrets empty) from "the
    #    registry rejected the supplied credentials or image reference"
    #    (forward the raw error either way) — FR-010.
    # 3. On pull success: check the pulled image for every tool in the
    #    canonical required-tool list (data-model.md), failing with every
    #    missing tool named at once — FR-011.
```

Skipped outright (`if: inputs.container-image != ''` evaluates false) when
no image is named — zero added latency, zero added Docker invocation, zero
new failure mode on the default path (FR-006; FR-011's own "MUST NOT
compromise FR-006" clause).

Every other job in the stage file with no other in-stage predecessor (an
"entry" job), or that survives a skipped ancestor via `if: always()` or
equivalent (the same class of job Gate 15 already catalogues —
`auto-update-spec-kit.yml`'s `evaluate-path` is the repository's own
existing example of this shape), gains:

```yaml
needs: [..., verify-image-prerequisites]
if: |
  (needs.verify-image-prerequisites.result == 'success' ||
   needs.verify-image-prerequisites.result == 'skipped')
  <combined with the job's own existing condition, if any>
```

A downstream job that already depends (directly or transitively) on an
entry job wired this way needs no separate wiring of its own — GitHub's
ordinary `needs:` skip-propagation already gates it, exactly as it gates
today's `if: inputs.merged`-style conditions. Only jobs whose own survival
logic (`always()` or similar) would otherwise defeat that propagation need
the explicit tolerant `if:` above.

**Cost note**: when an image IS named, this job pulls it once; the real
containerized job(s) that follow pull the same image again (GitHub does not
share a pull across jobs, even on the same runner, in the general case).
This is an accepted, documented cost of being able to satisfy FR-010/FR-011
at all — not something this contract attempts to optimize away.

## Image prerequisite contract — canonical tool list (FR-011, FR-011a)

The list `verify-image-prerequisites` checks against a named image:

| Tool | Basis |
|---|---|
| `git` | Direct invocation in all eleven stage files beyond `actions/checkout`. |
| `gh` | Direct invocation (issue/pr/api/run/repo/workflow/release subcommands) in all eleven stage files and the `wing-commander-callout`/`wing-commander-lifecycle-gate` composites. |
| `jq` | Used in `wing-commander-context`, `wing-commander-lifecycle-gate`, `wing-commander-metrics-summary`, `wing-commander-preflight`, ten of eleven stage files, and `lint-workflows.yml` itself. |
| `curl` | Direct invocation in the majority of stage files. |
| `python3` | A real, direct dependency of a published stage today — `watchdog.yml`'s `act` job invokes it directly, not just tooling/CI scripts. |
| `bash` | Every `run:` step across every stage and composite assumes it. |
| `node` (Node.js runtime) | *Inferred*, not directly observed in this repository's own source — `anthropics/claude-code-action@v1` (used by every agent-bearing job across all eleven stages) is a JavaScript action, which implies a Node.js runtime requirement this repository's own grep cannot confirm or deny (research D6). Implementation must decide how to treat this entry and record the decision. |

Kept in agreement with reality by Gate 23 (below), not by convention alone
(FR-011a).

## Pass-through, no validation on adopter-chosen values (FR-008)

The pipeline performs no existence check, allowlist, or format validation on
`runner` or `container-image`, and requires no new GitHub App permission to
support either. The **only** validation this feature performs anywhere is
the prerequisite check's inspection of the pulled image's *contents* — never
the adopter's reference string, label name, or credential values themselves.

## Per-stage-call granularity (FR-007)

Binding applies uniformly to every job in a stage file — there is no
per-job internal selector, mirroring specs/031's identical granularity
decision (its research D7) for the same structural reason: `tasks.yml`,
called twice by `wing-commander-4-tasks.yml` (`mode: generate` and `mode:
approved`), already gives an adopter who wants to run only the agent-running
call on self-hosted infrastructure the two call sites needed — they set
`runner`/`container-image` on the `generate` call and leave the `approved`
call at its defaults. No stage-side "which job(s) move" selector is needed
or wanted (FR-007: "no hidden per-job rule about which jobs move").

## PR-time enforcement — Gate 22 and Gate 23 (research D7) — FR-014, FR-015

**Gate 22** (`lint-workflows.yml`, next free gate number after today's
highest, 21): for every workflow declaring `on.workflow_call` — derived,
never listed, so a twelfth stage file cannot be born exempt — asserts both
`runner` and `container-image` are declared with the contract types and
defaults, and that every job with no local `uses:` carries the exact
`runs-on:` expression and `container:` mapping from this contract,
forwarding every named input/secret verbatim. Mirrors Gate 7's shape
(specs/031) extended from one binding to three.

**Gate 23**: every stage file declares `verify-image-prerequisites`
(skip-conditioned on `container-image`), every entry job (per the rule
above) depends on it with a skip-tolerant `if:`, and the canonical
required-tool list (Image prerequisite contract, above) is not missing any
tool a `run:` block anywhere in the repository actually invokes (FR-011a's
drift check).

**Registered exceptions** (FR-015): none exist yet at plan time. A job that
must deviate — mirroring Gate 7's one existing `pr-conversation.act`
exception (`docs/adoption.md:704-712`) — carries a registered reason in the
gate's own exception table, checked by the same mechanism, never an
undeclared deviation and never a code comment alone (constitution VII).

Both gates need a synthetic-fixture self-test
(`.github/scripts/verify-gate-22.py`, `verify-gate-23.py`), run against
synthetic stage fixtures each carrying one known defect, mirroring Gate
7/12/15/16/18's self-test discipline — writing those scripts is
implementation-stage work; this contract fixes their scope so `tasks.md` can
enumerate concretely.

## Non-goals (unchanged from the spec's Assumptions/Edge Cases, restated for
this contract's boundary)

- **Runner groups.** Out of scope — a different targeting shape than a
  label list; documented, not silently unsupported.
- **Non-Linux runners.** Accepted by the input, will fail in the steps
  (every stage's steps are Linux shell scripts) — a documented non-goal,
  not a validated one.
- **Per-job targeting within one stage call.** Deferred; the design leaves
  it addable later as an additive, non-breaking change (FR-007) — the
  `tasks.yml` two-call precedent already covers the motivating case.
- **The remaining container settings** — volumes, ports, environment
  variables, extra options, service containers — and validating that a
  named runner label or image actually exists. Out of scope; pass-through
  matches Actions' behavior everywhere else in this pipeline.
- **Reporting a prerequisite-check or credential failure to the lifecycle
  issue thread beyond the job's own log/summary.** No new lifecycle-issue
  reporting path is added by this feature.
