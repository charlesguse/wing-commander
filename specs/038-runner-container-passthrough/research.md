# Research: Consumer-Chosen Runners and Container Images

## Context recap

Wing Commander's published contract (constitution VII) is the set of
`workflow_call`-only stage workflows under `.github/workflows/`. Verified
today (2026-08-18, by deriving the set the same way `lint-workflows.yml`'s
Gate 6/7 already do — any file declaring `on.workflow_call`, never a
hardcoded list) that set is eleven files carrying 33 jobs, all with a direct
`runs-on:` (none delegate via a local `uses:`): `intake` (1 job), `clarify`
(1), `plan` (2), `tasks` (3), `implement` (2), `finalize` (1), `cleanup` (4),
`watchdog` (5), `pr-conversation` (2), `rebase` (2), `auto-update-spec-kit`
(10). This confirms the spec's own "eleven... thirty-three" count (spec.md
Key Entities) still holds.

The spec (`specs/038-runner-container-passthrough/spec.md`) carries no
`[NEEDS CLARIFICATION]` markers — `checklists/requirements.md` (2026-08-17)
confirms three markers were resolved before intake completed (granularity,
private-registry scope, prerequisite-contract enforcement) and records one
question explicitly deferred to this planning pass: "how a short-lived
registry token is minted/refreshed... is for planning to settle" (spec Edge
Cases). D4 below settles it.

## Decisions

### D1: Scope is all eleven `workflow_call`-only stage files

**Decision**: The new inputs, secrets, and job bindings land in all eleven
files that declare `on: workflow_call` under `.github/workflows/`: `intake`,
`clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `watchdog`,
`pr-conversation`, `rebase`, `auto-update-spec-kit`.

**Rationale**: Constitution VII defines the published contract structurally
("the set of `workflow_call`-only stage workflows"), not by an enumerated
list, and every one of these eleven files is a real, callable stage today.
`docs/architecture.md`/`watchdog.yml:2`/`release.yml:3` still say "nine" or
"ten" stages in places — pre-existing documentation drift already noted by
specs/031's own research (its D1) and tracked separately by issue #149; this
plan does not need to fix it, only avoid rediscovering it as new. Unlike
`release.yml`'s Gate 1a/1b (a hardcoded 8-file subset, issue #149), the new
Gate 22/23 this feature adds must derive the stage set the same
structural way Gate 7 already does (FR-014: "Its stage set MUST be derived
from the workflows themselves rather than hardcoded"), so a twelfth stage
added later is covered automatically.

**Alternatives considered**: none — the same reasoning specs/031's D1 already
settled (a structural, not enumerated, definition of "published stage")
applies identically here; there is no version of this feature that excludes
a real stage for any reason other than a stale count elsewhere in the repo.

### D2: Runner selection — one `runner` string input, `runs-on:` via a short-circuit ternary expression

**Decision**: Every job in every one of the eleven files gains:

```yaml
runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
```

with `runner` declared `type: string`, `default: ubuntu-latest`.

**Rationale**: `runs-on:` accepts either a single string label or a YAML
list of labels (conjunction) — but a `workflow_call` input can only ever
carry a string (spec Assumptions: "the only shape that fits a typed
`workflow_call` input"). The requester's own proposed convention — read a
JSON array as multiple labels, anything else as one label — needs a runtime
branch inside a single YAML scalar, which GitHub Actions expressions support
via `&&`/`||`'s short-circuit, non-boolean-coercing evaluation: the
left-hand `startsWith(inputs.runner, '[') && fromJSON(inputs.runner)`
evaluates to the parsed array when the input looks like a JSON array and to
`false` otherwise, and `false || inputs.runner` falls through to the raw
string. This is a widely used community idiom for ternary-style branching in
Actions expressions (there is no dedicated `if`/`else` expression function),
built entirely from documented operators — but the idiom itself, applied to
`runs-on:` specifically, has **not** been empirically run against a live
GitHub Actions job in this planning pass (no live-runner or web access from
this stage). Per FR-018 ("any behavior this feature depends on that is not
documented by GitHub... MUST be traceable... to the recorded evidence"),
this is flagged as a required implementation-time verification (a scratch-run
smoke test, both for a single label and a JSON-array multi-label value)
before the mechanism ships — the same discipline specs/031's D8 applied to
its own actionlint-schema uncertainty, deferred rather than guessed.

**T001 outcome (implementation, 2026-08-18)**: not empirically verified by
this implementation run either. The automated implement stage that wired
this feature runs under a fixed, pre-approved shell-command allowlist that
includes no `gh workflow run`, `gh run view`, or `gh api` — there is no way
for this run to dispatch a `workflow_dispatch` workflow or observe its
result. This is recorded here rather than fabricated: the `startsWith(...)
&& fromJSON(...) || ...` idiom on `runs-on:`, for both a plain-string value
and a single-element JSON-array value, remains an open live-runner
verification that a human (or a future run with broader tool access) must
perform against a scratch adopter repository before this claim can be
treated as proven, per FR-018.

A value that is not a JSON array (e.g. `"self-hosted"`, a bare label with no
brackets) is read as a single label — `startsWith(..., '[')` is `false`, so
`fromJSON` is never evaluated on it (short-circuit), avoiding a `fromJSON`
parse error on a non-JSON string. This directly satisfies the edge case "A
single-label value that looks like a list" only in the sense that the
convention is unambiguous and documented (FR-003) — a label that happens to
start with a literal `[` character is out of scope (GitHub runner label
syntax does not use `[`, so this is not a realistic collision, but
`docs/adoption.md` must state the rule plainly per FR-003/FR-017, not leave
it to be inferred).

**Alternatives considered**:
- Two separate inputs (`runner` for a single label, `runner-labels` for a
  JSON array), letting the adopter pick which to set — rejected: doubles the
  input surface for no behavioral gain, and still needs the same
  `fromJSON`/string branch inside `runs-on:` to merge them, so it does not
  actually avoid the expression this decision already uses.
- A YAML list-typed input — rejected: `workflow_call` inputs support only
  `string`, `number`, or `boolean` (GitHub Actions' own type restriction);
  there is no list-typed input to declare.

### D3: Container image — one `container-image` string input, relying on an **unverified** empty-value no-op

**Decision**: Every job gains a mapping-form `container:` block:

```yaml
container:
  image: ${{ inputs.container-image }}
  credentials:
    username: ${{ secrets.container-registry-username }}
    password: ${{ secrets.container-registry-password }}
```

with `container-image` declared `type: string`, `default: ""`.

**Rationale**: The requester's own framing (spec's "Anything else?" answer:
"I want `container: ${{ inputs.container-image }}` to mean 'no container'
when unset") and the spec's Edge Cases section both anticipate this
mechanism directly. It mirrors specs/031's `environment:` mapping form
exactly — a job-level attribute rendered unconditionally from a
`workflow_call` input, letting an empty value collapse to "as if the key
were absent" with no `if:` needed on the key itself.

**The critical difference from specs/031**: that plan's equivalent decision
(D2) rested on six behaviors *empirically probed* against live GitHub-hosted
runners before the plan was written (charlesguse/wc-env-probe, probed
2026-08-05/06). This plan has **no equivalent probe** — this planning pass
has no ability to trigger a live GitHub Actions run or reach the network, and
inventing the claim that an empty `container:` image is a true no-op would
violate FR-005 ("This MUST be verified against real runners rather than
assumed, and the evidence recorded") and FR-018 exactly as much as skipping
the check entirely. This is recorded here as a **decision made without
clarification, and explicitly without verification**: the design proceeds on
the requester's own stated expectation, but FR-005/SC-002/User-Story-2's
"identical to today" guarantee is not yet proven and must not be treated as
proven by any later stage. **Action for implementation**: before this
feature is considered done, run a live probe (mirroring wc-env-probe's
method) confirming (a) an empty `image` value is a true no-op — no pull, no
container, no failure — for the mapping form specifically, and (b) an empty
`credentials.username`/`password` pair does not itself cause a public-image
pull to fail. If either disproves the hoped-for behavior, the spec's own
Edge Cases section already names the fallback obligation: "the pipeline
needs another way to express 'no container' — and whatever that is must
still leave unset adopters byte-for-byte unchanged" — solving that
contingency is out of this plan's scope unless the probe forces it.

**T001 outcome (implementation, 2026-08-18)**: still not verified. The same
tooling gap recorded against D2 above applies here — this implementation
run has no `gh workflow run`/`gh run view`/`gh api` access, so it could not
dispatch the throwaway probe workflow T001 describes or observe a live
container-less job. The design proceeds on the requester's stated
expectation exactly as this decision already says; the empty-`image`
no-op remains an unproven claim pending a human (or a future run with
broader tool access) running the probe against a scratch adopter repository,
per FR-005/FR-018. Nothing downstream in this implementation treats it as
proven.

**Alternatives considered**:
- Duplicate every job (with/without `container:`) gated by `if:` — rejected
  for the same reason specs/031's D2 rejected the analogous idea for
  `environment:`: it would require a duplicate job definition per job across
  33 jobs, for a behavior GitHub's own key already collapses for free if the
  requester's expectation holds, and duplication itself introduces the exact
  uniformity risk FR-007/FR-014 exist to prevent (two copies drifting apart).
- Deferring container support to only stages that already have a container
  precedent — none exist (research confirmed zero `container:` blocks
  anywhere in the repository today), so there is no narrower rollout that
  reduces risk; the empty-value behavior must be verified for *some* stage
  regardless, and FR-007 requires uniformity once it is verified.

### D4: Registry credentials — two generic secrets, minted by the wrapper, never by a step inside the stage

**Decision**: Two new optional `workflow_call` secrets, `required: false`:
`container-registry-username`, `container-registry-password`. Both forward
verbatim into the `credentials:` sub-keys shown in D3. No new input (secrets
are never inputs — FR-009).

**Rationale — settles the spec's deferred "which side mints" question**: A
job's `container:` (image *and* credentials) resolves before any step in
that job runs (same structural timing class as specs/031's `environment:`
protection rules, research D4 there). Concretely, this means:
- A credential minted by a *step inside the stage* (e.g. an `aws ecr
  get-login-password` call) is always too late — the container has already
  attempted its pull, or failed to, before that step could run. This is the
  exact scenario the spec's Edge Cases section names ("A credential that
  does not exist yet when the job starts... a token minted by a step inside
  the stage is too late") and asks planning to resolve.
- The only place a token-based or cloud-registry credential (ECR, GCR, ACR)
  can be minted in time is the **calling wrapper's own job**, in a step
  before its `uses: .../plan.yml@<ref>` call, passing the minted value in as
  `secrets.container-registry-password` (with `container-registry-username`
  set to whatever fixed or derived username that registry's docker-login
  convention expects — e.g. ECR's fixed `AWS` username with a token
  password). This works uniformly for both a static long-lived pair and a
  freshly minted token: from the stage's perspective, both arrive
  identically as two opaque secret strings — the stage never needs to know
  which kind it received (FR-009a: "the same credential mechanism serves
  them, with no published stage edited or forked").
- "Refreshed for a long stage" (the spec's other named sub-question) is
  therefore also an adopter/wrapper-side concern: a credential minted before
  the call is valid for the lifetime of that one job's container (a docker
  registry credential is consumed once, at pull time, not held open for the
  job's duration), so no in-stage refresh mechanism is needed — only
  wrappers whose *own* job runs long before the call would need to consider
  their token's mint-to-use latency, which is unrelated to this stage's
  design.

**FR-010 (identify the missing credential, not just the raw registry error)
is only partially achievable given the timing constraint above** — see D5,
which is the mechanism that makes any of FR-010 achievable at all.

**Alternatives considered**:
- Provider-specific secrets (`ecr-role-arn`, `gcr-key-json`, etc.), mirroring
  how `use-bedrock`/`aws-role-arn`/`aws-region` give Bedrock its own
  first-class inputs — rejected: FR-009a explicitly requires generality
  ("without editing or forking a published stage") across registries this
  pipeline has no reason to special-case; two opaque secrets already cover
  every registry's docker-login shape (username + password/token), and
  provider-specific minting logic belongs in the adopter's own wrapper, not
  in a stage that must stay registry-agnostic.
- Resolving credentials *inside* the stage via a composite (mirroring
  `wing-commander-bedrock-credentials`, which assumes an OIDC role from
  `aws-role-arn`) — rejected: that composite runs as a *step*, and a step
  cannot run before its own job's `container:` key has already resolved.
  Bedrock's OIDC assumption works because Bedrock is called from *within* an
  agent step, not used to gate the job's own container creation; the two
  problems are not the same shape despite the surface similarity.

### D5: Prerequisite check and credential-failure messaging — one new `verify-image-prerequisites` job per stage file

**Decision**: Each of the eleven stage files gains a new job:

```yaml
verify-image-prerequisites:
  if: inputs.container-image != ''
  runs-on: ${{ startsWith(inputs.runner, '[') && fromJSON(inputs.runner) || inputs.runner }}
  # No container: — this job must run directly on the runner so it can
  # invoke Docker itself, before the real per-job container exists.
  steps:
    - Attempt docker login (only if credentials are non-empty) + docker pull
      of inputs.container-image, capturing failure distinctly from success.
    - On pull failure: fail with a message distinguishing "no credentials
      were supplied for this image" (both secrets empty) from "the registry
      rejected the supplied credentials or image reference" (forwarding
      GitHub/Docker's own error either way) — FR-010.
    - On pull success: run the canonical required-tool check (data-model.md,
      FR-011) inside the pulled image, failing with every missing tool named
      at once, not just the first — FR-011.
```

Every other job in the file that has no other in-stage predecessor (an
"entry" job), or that survives a skipped ancestor via `if: always()` or
similar (Gate 15's own finding: a skip does not propagate through such a
job), gains `needs: [..., verify-image-prerequisites]` and an `if:` that
tolerates a `skipped` result:

```yaml
if: |
  (needs.verify-image-prerequisites.result == 'success' ||
   needs.verify-image-prerequisites.result == 'skipped') &&
  <the job's own existing condition, if any>
```

**Rationale**: This is the only design that satisfies both FR-010 and FR-011
given D4's timing constraint. `verify-image-prerequisites` runs *before* any
agent-bearing job's own container is created (satisfying FR-011's "before
any agent work is started or any cost incurred" and SC-005's "at the start
of the stage") because it is a `needs:` predecessor, and because it does not
itself carry a `container:`, it can run `docker login`/`docker pull` as
ordinary steps and control their error messages — the one thing no step
*inside* a job whose own `container:` already failed could ever do (D4).
Skipping it outright when `container-image` is empty (`if:
inputs.container-image != ''`) means the default path pays no latency, no
extra Docker invocation, and — critically — no new failure mode (FR-006,
FR-011's own "MUST NOT compromise FR-006" clause): a skipped job's `result`
is `'skipped'`, which the tolerant `if:` above treats identically to
`'success'`.

Exact per-file wiring (which job(s) in each of the eleven files count as
"entry" given that file's existing `needs:` graph, and which jobs use
`always()`-style survival per Gate 15's own catalogued example in
`auto-update-spec-kit.yml`'s `evaluate-path`) is deferred to `tasks.md` —
this plan establishes the mechanism and the rule, not the 33-job-by-33-job
enumeration, matching how specs/031 deferred its own exact per-job edit list.

**Rationale for a new job over extending `wing-commander-preflight`**:
`wing-commander-preflight` runs as a *step*, already inside whatever
container the job specifies — so by the time it would run, the pull (and any
credential failure) has already happened or already succeeded; it could
check for tool presence *after* a successful pull, but it structurally
cannot intercept or improve a pull failure (D4), and several jobs across the
eleven files (e.g. `resolve-spec` in `plan.yml`/`tasks.yml`) call no
preflight step at all today because they do no checkout or agent work — a
uniform per-job extension would need to be added to those jobs too, which is
no simpler than the dedicated job this decision already adds. Concentrating
both checks (pull/credential and tool-presence) in one new, always-outside-
any-container job is simpler to reason about and to gate (`lint-workflows.yml`
Gate 23) than splitting the logic across an extended composite plus new
per-job step insertions.

**Alternatives considered**:
- Skip the credential-failure-messaging half of FR-010 entirely and rely on
  GitHub's raw pull error — rejected: FR-010 explicitly requires a message
  "identifying the missing credential as the cause rather than only
  surfacing the registry's raw error," and D4 already shows the raw error is
  the *only* thing available from inside the real job; a dedicated
  pre-check is the only way to add anything beyond that.
- Run the tool-presence check as the real job's own first step (inside the
  already-pulled container) instead of a separate job — viable for FR-011
  alone (the pull already succeeded by then), but does not help FR-010 at
  all (the pull already either succeeded or the job never got this far), and
  still leaves credential-less jobs like `resolve-spec` unchecked unless
  they too gain the step — no simpler than D5's single shared job once both
  requirements are considered together.

### D6: Canonical required-tool list and its drift check (FR-011a)

**Decision**: `verify-image-prerequisites`' tool check (D5) runs against one
canonical list, seeded from what stages and their shared composites actually
invoke today: `git`, `gh`, `jq`, `curl`, `python3`, `bash`. A Node.js runtime
is a further, *inferred* (not directly observed in this repository's own
`run:` blocks) requirement of `anthropics/claude-code-action@v1` itself,
used by every agent-bearing job across all eleven stages — flagged here
rather than silently assumed, since the action's own runtime dependency is
outside this repository's source to grep.

A new PR-time check (part of Gate 23, research D7) cross-references this
canonical list against every `run:` block across `.github/workflows/*.yml`
and `.github/actions/**` for literal invocations of each tracked tool,
failing when a *new* tool name appears in a `run:` block that the canonical
list does not cover — the same "two halves, both needed" discipline Gate 5
already applies to the denied-tool collector (verifying the check's own list
is internally consistent is not enough; it must also still describe what the
pipeline actually uses).

**Rationale**: FR-011a requires the verified list to "stay in agreement with
what the stages and their shared composite actions actually depend on" and
for that agreement to be "machine-checked... rather than maintained by
convention." Seeding the list from a real grep (rather than a guess) and
then checking it on every future PR is the only way to satisfy both halves.

**Decision made without clarification**: the Node.js runtime requirement is
recorded as a known, inferred gap in what this repository's own source can
verify about `claude-code-action`'s dependencies — not resolved here, since
resolving it would require inspecting that action's own implementation,
which is out of this repository's control and out of this plan's scope.
Implementation must decide whether to include `node` in the canonical list
on faith or attempt to verify it some other way; either choice must be
recorded, not silently assumed away.

**Alternatives considered**: relying purely on documentation (FR-017) with
no machine check — rejected outright by FR-011a's own text ("machine-checked
... rather than maintained by convention").

### D7: Gate numbering

**Decision**: Two new `lint-workflows.yml` gates, the next free numbers
after today's highest (Gate 21, confirmed by inventory — no gate ≥ 22
exists yet):

- **Gate 22** — input/binding uniformity: every stage declares `runner`
  (string, default `ubuntu-latest`) and `container-image` (string, default
  `""`) with the contract type/default, and every job with no local `uses:`
  carries the exact `runs-on:` expression from D2 and the exact `container:`
  mapping from D3, forwarding `inputs.runner`/`inputs.container-image` and
  `secrets.container-registry-username`/`secrets.container-registry-password`
  verbatim — the same shape as Gate 7 (specs/031), extended from one binding
  (`environment`) to three (`runs-on`, `container.image`,
  `container.credentials.*`).
- **Gate 23** — `verify-image-prerequisites` wiring: every stage file
  declares the job from D5, every entry job (per that decision's rule)
  depends on it with a skip-tolerant `if:`, and the FR-011a drift check from
  D6 passes.

Both gates need a synthetic-fixture self-test (`.github/scripts/verify-gate-
22.py`, `verify-gate-23.py`), mirroring Gate 7/12/15/16/18's own self-test
discipline — the fleet these gates check is healthy by construction, so a
green run of either says nothing about whether the gate's detection logic
itself works. Writing those scripts is implementation-stage work; this
decision fixes only the gate numbers and their scope so `tasks.md` can
enumerate concretely.

**Rationale**: `release.yml`'s Gate 1a/1b numbering is a separate,
non-colliding namespace local to that file (confirmed: `1a`/`1b`/`2`, not
`22`/`23`); `lint-workflows.yml`'s own Gate-N sequence is the one this
feature's FR-014 (a PR-time check) belongs to, exactly like specs/031's Gate
7 did.

**Alternatives considered**: one combined gate covering both uniformity and
wiring — rejected: Gate 7's own comment explains why Gate 5/6/7's split
exists ("two halves, and both are needed... either half alone can be green
while the collector that actually runs is broken"); uniformity (static,
per-job YAML shape) and wiring (DAG-level `needs:`/`if:` correctness plus a
content-drift check) are different failure classes that deserve independent,
separately-nameable gates, matching how Gate 5's own two halves and Gate
6/7's split already separate "does the shape match" from "does the mechanism
actually work."

### D8: This repository's own wrapper exposure (FR-016, User Story 6)

**Decision**: Every `wing-commander-*.yml` wrapper gains, in its existing
`with:`/`secrets:` block:

```yaml
runner: ${{ vars.WING_COMMANDER_RUNNER || 'ubuntu-latest' }}
container-image: ${{ vars.WING_COMMANDER_CONTAINER_IMAGE || '' }}
secrets:
  container-registry-username: ${{ secrets.WING_COMMANDER_CONTAINER_REGISTRY_USERNAME }}
  container-registry-password: ${{ secrets.WING_COMMANDER_CONTAINER_REGISTRY_PASSWORD }}
```

**Rationale**: This is the exact convention every existing wrapper knob
already follows (`model`, `plan-review`, every branch prefix) — a
`vars.WING_COMMANDER_<KNOB>` read with a literal `||` fallback identical to
today's hardcoded behavior, confirmed by inspecting `wing-commander-3-
plan.yml`'s current `with:` block. Secrets are forwarded directly (never
through `vars.*`, which cannot hold secret values) from equivalently-named
repository secrets, matching how `claude-code-oauth-token`/`anthropic-api-
key`/`speckit-app-private-key` are already forwarded.

**Noted, not required to fix**: neither `use-bedrock`/`aws-role-arn`/
`aws-region` (specs/016) nor `environment`/`environment-deployment`
(specs/031) are wired through any of this repository's own wrapper `with:`
blocks today — those two features are documented as available to adopters
but not dogfooded by this repository's own wrappers. This feature's own
User Story 6 explicitly requires the opposite for `runner`/`container-image`
("this repository's own wrapper workflows MUST expose both controls" —
FR-016), so this plan does not follow the bedrock/environment precedent of
leaving it undogfooded; it is called out here only so implementation does
not mistake the existing gap in those two other features for a pattern to
repeat.

**Alternatives considered**: none — FR-016's requirement and the existing
wrapper convention point at the same design with no tension between them.

## Summary of new stage-input/secret surface (applies uniformly to all eleven stages)

| Name | Kind | Type | Default | Purpose |
|---|---|---|---|---|
| `runner` | input | string | `ubuntu-latest` | FR-001/FR-002/FR-003: single label or JSON-array multi-label conjunction for every job's `runs-on:`. |
| `container-image` | input | string | `""` | FR-004/FR-005: image every job's `container:` runs inside. Empty is intended (not yet verified) to mean no container at all. |
| `container-registry-username` | secret | — | — (`required: false`) | FR-009/FR-009a: registry username, or a fixed value some cloud registries expect (e.g. ECR's `AWS`) paired with a minted token as the password. |
| `container-registry-password` | secret | — | — (`required: false`) | FR-009/FR-009a: registry password or minted token. |

Plus one new job per stage (`verify-image-prerequisites`, D5) and two new
`lint-workflows.yml` gates (22, 23, D7). No changes to any existing input,
secret, `permissions:` block, or output on any of the eleven stages.
