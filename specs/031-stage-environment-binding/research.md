# Research: Bind Pipeline Stages to a Deployment Environment

## Context recap

Wing Commander's published contract (constitution VII) is the set of
`workflow_call`-only stage workflows under `.github/workflows/`. Today that
set is ten files: `intake`, `clarify`, `plan`, `tasks`, `implement`,
`finalize`, `cleanup`, `rebase`, `watchdog`, and `auto-update-spec-kit` — see
D1. None of them can be gated by a GitHub deployment environment today,
because `jobs.<job_id>.environment` is a keyword GitHub only accepts inside
the workflow that *owns* the job, and a job whose body is `uses: <reusable
workflow>` cannot set it; `on.workflow_call.inputs` has no analogous
mechanism either. The spec's Overview and issue #171 already established
this as the reason the capability must live in the stage, not the wrapper —
this research does not re-litigate that; it resolves the *how*.

The spec (`specs/031-stage-environment-binding/spec.md`) carries no
`[NEEDS CLARIFICATION]` markers — the checklist confirms this and notes the
source issue's own "Settled decisions" section pre-resolved the areas most
likely to need clarification. The decisions below are therefore
plan-level/implementation-level choices, not spec-clarification substitutes,
except where explicitly marked "decision made without clarification" for
traceability into the issue-#171 comment this plan stage posts.

## Decisions

### D1: Scope is all ten `workflow_call`-only stage files, including `auto-update-spec-kit.yml`

**Decision**: The two new inputs and the `environment:` job block land in
all ten files that declare `on: workflow_call` under `.github/workflows/`:
`intake.yml`, `clarify.yml`, `plan.yml`, `tasks.yml`, `implement.yml`,
`finalize.yml`, `cleanup.yml`, `rebase.yml`, `watchdog.yml`, and
`auto-update-spec-kit.yml`.

**Rationale**: Constitution VII defines the published contract as "the set
of `workflow_call`-only stage workflows (`.github/workflows/<stage>.yml`)" —
a structural definition, not an enumerated list. `auto-update-spec-kit.yml`
matches it (confirmed by grep: `on: workflow_call` at line 31) and runs a
real agent step (`evaluate-path`, `claude-sonnet-5`) — exactly the class of
"spends real money the moment it starts" work this feature exists to gate
(spec Overview). Excluding it would leave one published stage with no way to
gate its own agent spend, contradicting the feature's own motivation for no
reason other than a stale count elsewhere in the repo.

**Note on the "nine" discrepancy**: `docs/architecture.md` ("workflow_call —
nine of them today") and the constitution's Principle VII prose both predate
`auto-update-spec-kit.yml` landing (that stage finalized 2026-08-01, per
`git log`; the constitution's Principle VII section was last amended
2026-07-28). `specs/016-bedrock-support/research.md` similarly said "nine"
for the same reason — it was researched 2026-07-22, also before
auto-update-spec-kit existed. This is pre-existing documentation drift, not
something this feature's scope requires fixing; `release.yml`'s Gate 1a/1b
already have a *known*, separately-tracked version of the same gap (a
hardcoded eight-file list missing `watchdog.yml` and
`auto-update-spec-kit.yml`, tracked by issue #149). This plan does not touch
`release.yml`, `docs/architecture.md`'s stage count, or issue #149 — noted
here only so implementation doesn't rediscover the same drift and treat it
as new.

**Decision made without clarification**: the spec's own Overview and
Assumptions sections list stages by name ("intake, clarify, plan, tasks,
implement, converge, finalize, and the supporting rebase/watchdog stages")
and never mention `auto-update-spec-kit` — an omission, not an exclusion
(the Assumptions section defines "every published stage" as "all published
stage workflows," a structural test the omitted stage still passes). Include
it.

**Alternatives considered**:
- Match the spec's Overview prose literally (9 named concepts, one of which —
  "converge" — is not a separate file at all, it's the loop inside
  `implement.yml`) — rejected: this would silently leave the newest
  agent-running stage ungateable, which is exactly the gap the spec's own
  reasoning (constitution VII, "wrappers can't fix it either") applies to
  identically.

### D2: The binding mechanism is the job-level `environment:` mapping form, added to every job

**Decision**: Every job in every one of the ten files gains:

```yaml
environment:
  name: ${{ inputs.environment }}
  deployment: ${{ inputs.environment-deployment }}
```

No `permissions:` block changes anywhere, no new composite action, no
reordering of existing steps.

**Rationale** — six empirically probed GitHub behaviors, verified 2026-08-05
(items 1–4) and 2026-08-06 (items 5–6) against GitHub-hosted runners on a
public repo
([charlesguse/wc-env-probe](https://github.com/charlesguse/wc-env-probe),
workflows/run IDs/recreate script in that repo's README, per issue #171):

1. **An empty name is a true no-op** — no environment applied, no gate, no
   environment scope, no deployment record, no phantom environment created —
   for both the string and mapping forms. This is the entire basis for FR-003
   and SC-001 (the zero-change guarantee for adopters who leave the input
   unset): the stage workflow does not need an `if:` to decide whether to
   emit the `environment:` key at all — it can emit the mapping form
   unconditionally, every time, for every job, and let GitHub's own behavior
   collapse an empty name to nothing.
2. **The mapping form accepts an expression in `name`**, binding identically
   to the string form — required, since `name` must resolve from a
   `workflow_call` input (`${{ inputs.environment }}`), not a literal.
3. **`deployment: false` is a real, recognized key** that preserves the
   environment binding (and its protection rules) while suppressing the
   deployment record GitHub would otherwise create — confirmed against a
   strict-parser control (an actually-unknown key under `environment:`
   produces a hard `422` from GitHub's own workflow-file validation, and
   `deployment` does not). This directly satisfies FR-008/User Story 3
   without any pipeline-side logic: it is GitHub's own key, not something
   this pipeline emulates.
4. **A name that doesn't exist yet is silently auto-created**, not rejected,
   with no protection rules — confirms FR-007's pass-through-unvalidated
   requirement needs no pipeline-side existence check; GitHub already
   behaves exactly as the spec requires.
5. **`deployment` accepts an expression, and the rendered value is coerced as
   a boolean.** Item 3 verified only a YAML literal, but the block above
   ships `deployment: ${{ inputs.environment-deployment }}` — a rendered
   `false` read as a truthy non-empty string would have kept creating
   deployment records while every stage file still looked correct, defeating
   FR-008/User Story 3 with no adopter-visible error. Probed directly: three
   call sites differing only in how the value arrives (literal `true`,
   literal `false`, input default) all bound to the environment, and exactly
   the two `true` ones produced a record.
6. **A `workflow_dispatch` boolean forwards into a `workflow_call` boolean
   input** and on into `deployment` without a type rejection — the shape an
   adopter's wrapper will actually use.

Items 5 and 6 were probed on 2026-08-06 after code review of the
implementation PR observed that the shipped construct was an untested
*combination* of items 2 and 3 rather than something either one covered. They
did not change the decision; the mechanism is unchanged.

Because none of these six is part of GitHub's officially published Actions
workflow syntax reference as of this planning pass (probed and inferred
behavior, not a documented public contract), FR-013 requires every place in
the implementation that depends on them to carry a comment pointing back to
the probe repo, so a silent upstream change is detectable rather than
discovered as a confusing regression. This plan's own artifacts (this file,
`contracts/environment-binding.md`) are that pointer's first landing place;
implementation must repeat it inline in the YAML.

Using the mapping form for *every* job, unconditionally, also directly
delivers FR-004's "bind every job in that stage file" and User Story 4's
acceptance scenario 2 ("which jobs bind is not a hidden internal rule") —
there is no per-job conditional to get wrong, because every job in a stage
file receives byte-for-byte the same two-line block referencing the same two
inputs.

**Alternatives considered**:
- A `permissions.deployments` based trick (restricting the job's
  `GITHUB_TOKEN` deployments scope to suppress the deployment record while
  keeping protection rules) — this is a mechanism that exists for other,
  unrelated reasons in GitHub Actions, but issue #171's own probe evidence
  already identified and confirmed the simpler, documented-by-behavior
  `deployment: false` key directly on the `environment:` mapping, which
  needs no permissions plumbing and does not risk interacting with any other
  permission the stage already relies on (e.g. `contents: write`,
  `pull-requests: write`). Rejected in favor of the simpler, already-verified
  key.
- Conditionally omitting the `environment:` key via a job-level `if:` when
  the input is empty, rather than relying on the verified empty-name no-op —
  rejected: adds an `if:` to every job for no behavioral gain (verified item
  1 already makes the unconditional mapping form byte-for-byte equivalent to
  omitting the key), and a job-level `if: false`-shaped condition on
  `environment:` itself is not how GitHub's schema works (the key is either
  present with a value or absent — there's no conditional variant of the key
  itself), so this alternative would need a *duplicate* job definition
  (with/without `environment:`) per job, which is far more complex for zero
  benefit.

### D3: Input names, types, and defaults match the source issue's proposed contract verbatim

**Decision**:

| Input | Type | Default |
|---|---|---|
| `environment` | string | `""` |
| `environment-deployment` | boolean | `true` |

Declared under each stage's `workflow_call.inputs:`, not `secrets:` — neither
value is sensitive (an environment name and a boolean are not credentials),
matching how `pipeline-repo`/`default-branch`/`use-bedrock` are already
modeled as plain inputs (`specs/016-bedrock-support/research.md` D6, same
reasoning applies here).

**Rationale**: FR-001/FR-002 require exactly these two inputs, uniformly
named and defaulted, across every stage; the source issue (#171) already
proposed this exact shape ("Matching the `use-bedrock` precedent: optional
inputs, off by default, set in the wrapper's `with:` block"), and no part of
the spec's requirements or acceptance scenarios motivates a different name,
type, or default. `environment-deployment` defaulting to `true` mirrors
GitHub's own default behavior for a bound job (FR-002, "settled decision" 1
in the issue) — an adopter who does nothing extra beyond setting
`environment` gets every protection-rule type working, including custom App
rules that require the deployment object.

**Alternatives considered**: none seriously — the naming and shape question
was the one part of this feature the source issue had already settled before
intake, and nothing discovered during this planning pass contradicts it.

### D4: The binding satisfies FR-005 ("before preflight or agent") structurally, with no code change to preflight

**Decision**: No change to `wing-commander-preflight` or any other shared
composite. `environment:` is a *job* attribute, evaluated by GitHub before
any step in that job runs — including the job's own preflight step, which is
always the first step today. Placing the binding at the job level therefore
satisfies FR-005 by construction; there is no ordering to get wrong, and
nothing to verify beyond "the key is present on the job," which the
consistency check in `quickstart.md` covers.

**Rationale**: This mirrors `016-bedrock-support`'s D7 finding pattern
(confirm an existing structural guarantee rather than build a new
mechanism) — the cheapest, least error-prone way to satisfy a "must happen
before X" requirement is to use a primitive that is *structurally* unable to
happen after X, rather than adding a runtime check that could drift out of
sync with a future step reordering.

**Alternatives considered**:
- A preflight-composite check that fails if the job hasn't already "seen" an
  environment gate — rejected: not expressible (a job cannot introspect its
  own environment-gate status from inside a running step; if the step is
  running, any gate has already resolved), and unnecessary given the
  structural guarantee above.

### D5: Lifecycle reporting (FR-009) needs no code change either

**Decision**: No change to `watchdog.yml` or the lifecycle-issue reporting
path. A job pending environment approval is, in GitHub's own terms, not
`completed` — it is `waiting`. `wing-commander-8-watchdog.yml`'s (this repo's
own wrapper) `workflow_run: [completed]` trigger structurally cannot fire for
a run that is still pending approval, so the watchdog never inspects — and
therefore never reports — a pending gate as a failure. This is the same
"verify an existing structural guarantee" posture as D4, not new suppression
logic.

**Rationale**: FR-009 forbids the pipeline from reporting a pending gate as a
failure, or adding any "waiting for approval" reporting of its own. Both
halves are satisfied by the trigger's own semantics: nothing runs (nothing to
report) while pending, and nothing this feature adds watches for the pending
state either.

**Decision made without clarification**: this reasoning is asserted from
GitHub Actions' documented `workflow_run` event semantics (fires on
`completed`, and a run awaiting environment-protection approval has not
reached a `completed`/terminal `conclusion`), not independently re-verified
against a live pending run in this planning pass (no outbound web access,
and reproducing a real pending-approval run requires the same scratch
adopter repository the spec's Assumptions section already defers protection-
rule verification to). **Action for implementation/verification**: the
scratch-repo manual verification pass called for by the spec's Assumptions
(and this plan's `quickstart.md`) should include watching the lifecycle
issue during a pending window to confirm no comment appears, closing this
gap with a real observation rather than an asserted one.

### D6: No composite-action, secret, or `permissions:` changes anywhere

**Decision**: `.github/actions/wing-commander-preflight`,
`wing-commander-context`, `wing-commander-metrics-summary`,
`wing-commander-bedrock-credentials`, and every other shared composite are
untouched. No stage's `secrets:` block gains an entry. No stage's job-level
`permissions:` block changes.

**Rationale**: D2 already established that the deployment-record control is
a job-level YAML key (`deployment: false`), not a `GITHUB_TOKEN` permission
scope — GitHub creates or withholds the deployment record based on that key,
not on what the job's own token is allowed to do. There is therefore nothing
for a composite action (which runs as *steps*, after the job's own gate has
already resolved) to contribute, and nothing secret about either new input's
value.

**Alternatives considered**: see D2's rejected `permissions.deployments`
alternative — the same reasoning eliminates any composite-action-based
implementation of that alternative too.

### D7: Per-job uniformity is the whole per-stage granularity story; the wrapper supplies the rest

**Decision**: Confirmed no additional design is needed for User Story 4
("per-job granularity from the wrapper") beyond D2's "every job, uniformly."
`tasks.yml` is already called twice by this repo's own
`wing-commander-4-tasks.yml` wrapper — once with `mode: generate` (runs an
agent) and once with `mode: approved` (agent-free, dispatch-only) — so an
adopter who wants to gate only the agent-running call already has the two
call sites needed; they simply pass `environment` on the `generate` call and
omit it on the `approved` call. No stage-side "which job(s) get gated"
selector is needed or wanted (User Story 4 acceptance scenario 2 explicitly
requires uniform per-file application).

**Rationale**: This is a direct reading of the existing `tasks.yml` calling
convention (`docs/adoption.md`'s wrapper 4 example) combined with FR-004; no
new mechanism is needed, only confirmation that the existing two-call shape
already gives adopters the granularity the story asks for.

### D8: Actionlint coverage risk for the new `environment:`/`deployment` key — resolved at implementation time

**Outcome** (2026-08-06, after code review of the implementation PR). The
guess this decision refused to make came out on the strict side: actionlint
1.7.7 **does** reject the key —

```
unexpected key "deployment" for "environment" section. expected one of "name", "url" [syntax-check]
```

— one diagnostic per binding, 30 in total, and none of the ten stage files
produces any other diagnostic. The first fix followed the `job_workflow_sha`
precedent literally and added a second `-ignore` to Gate 1a. Review rejected
that: it suppressed the only automated signal that exists about the key,
would equally have swallowed any *other* diagnostic phrased that way, and
would have gone stale in silence the day actionlint's schema learns the key.

Gate 1a now **counts** the diagnostics instead of ignoring them, in two
passes:

- Pass 1 (schema/syntax only, `-shellcheck= -pyflakes=`) runs over **all ten**
  stage files and requires exactly one `deployment` diagnostic per binding
  present in those files and no other diagnostic at all. Zero diagnostics with
  bindings present is itself a failure — that is the stale-allowance alarm.
  This pass is also the only lint of any kind covering `watchdog.yml` and
  `auto-update-spec-kit.yml`, which hold 14 of the 30 bindings and remain
  outside the shellcheck pass's hardcoded list (issue #149).
- Pass 2 is the pre-existing full lint (shellcheck on) over the eight-file
  subset, with the key ignored there because pass 1 accounts for it.

**What this does and does not detect.** It is a check on *actionlint's*
schema, not on GitHub's. The complementary question — "does GitHub still
accept the key?" — has no PR-time answer, and the obvious route was probed
and disproved on 2026-08-06: `POST /actions/workflows/<path>/dispatches`
returns *"Workflow does not have 'workflow_dispatch' trigger"* for a
`workflow_call`-only file **whether or not it parses**. A deliberately
invalid control (probe H, which registers under its path, proving GitHub
rejected it) and two valid files returned byte-identical 422s. The trigger
check short-circuits ahead of the parser, so the endpoint cannot be used as a
parse gate for reusable workflows — despite being exactly how the
`job_workflow_sha`-era parser messages were originally extracted, which is
what made the idea look sound.

The only detector that works is the registered-name comparison in
`lint-workflows.yml` Gate 1, which reads how GitHub registered each file on
the **default branch** — post-merge, plus nightly. That is a real limit of
this feature's verifiability, not an oversight: no gate can vet these ten
files against GitHub's parser before they land on main.

**Original risk assessment, retained for context:**

**Risk**: `release.yml`'s Gate 1a runs `actionlint` (pinned 1.7.7) over 8 of
the 10 published stage files (the pre-existing hardcoded-list gap from D1's
note; `watchdog.yml` and `auto-update-spec-kit.yml` are not linted by this
gate today, regardless of this feature). `deployment` under `environment:` is
not part of any GitHub-published schema this plan can point to (it is
confirmed only by the probe repo's behavioral evidence, D2) — it is unknown
whether actionlint 1.7.7's schema recognizes `environment.deployment` as a
valid key, silently ignores unknown mapping keys, or rejects the workflow
file outright the way `release.yml`'s existing `-ignore
'property "job_workflow_sha" is not defined'` flag suggests actionlint *can*
be strict about schema surface it doesn't recognize.

**Planning-time decision**: Flagged as an implementation-time verification
step, not resolved here (this planning pass has no outbound network access to run
actionlint against a draft workflow file). **Action for implementation**: the
first task that adds the `environment:` block to a stage file must run it
through the pinned actionlint 1.7.7 (the same tool/version `release.yml`
Gate 1a uses) before considering the change done; if actionlint rejects the
`deployment` key, add an `-ignore` pattern to Gate 1a mirroring the existing
`job_workflow_sha` precedent, scoped narrowly to that one property, and note
the addition in the same PR.

**Rationale for deferring rather than guessing**: `lint-workflows.yml`'s own
guard rail is YAML-parse + `bash -n` only (no schema check), so this repo's
PR-time CI does not itself block on this risk before merge — the exposure is
limited to `release.yml`'s manually-triggered Gate 1a, which only runs when
cutting a release, not on every PR. This gives implementation a real
verification opportunity (run actionlint locally or in a scratch PR before
declaring `environment.deployment` done) rather than forcing a guess now.

## Summary of new stage-input surface (applies uniformly to all ten stages)

| Input | Type | Default | Purpose |
|---|---|---|---|
| `environment` | string | `""` | FR-001/FR-003: name of a deployment environment in the adopter's own repository to bind every job in this stage file to. Empty is a verified true no-op. |
| `environment-deployment` | boolean | `true` | FR-002/FR-008: whether the bound job(s) create a deployment record. `true` mirrors GitHub's own default (every protection-rule type, including custom App rules, works out of the box); `false` keeps the gate but suppresses the record. |

No changes to `secrets:` blocks, `permissions:` blocks, existing inputs, or
outputs on any of the ten stages.
