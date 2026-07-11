# Research: Reusable Pipeline Extraction

Decisions resolving every open technical question in plan.md's Technical Context.
No NEEDS CLARIFICATION markers remain.

## D1 — Publication mechanism: `workflow_call` reusable workflows, one per stage

**Decision**: Each stage is published as a reusable workflow (`on: workflow_call`)
in this repository's `.github/workflows/`, named `reusable-<stage>.yml`.
Consumers invoke `uses: <owner>/speckit-action/.github/workflows/reusable-<stage>.yml@<ref>`
from a job in their own wrapper workflow.

**Rationale**: Stages are *jobs*, not steps — they carry `permissions`,
job-level `concurrency` (per-spec serialization), conditional jobs (cleanup's
three-way outcome selection), and multi-step sequences with `if: always()`
post-steps (metrics). Only reusable workflows preserve all of that behind a
single `uses:` reference. This also matches the extraction path already
recorded in `docs/architecture.md` ("Reusability roadmap").

**Alternatives considered**:
- *Composite actions per stage* — steps only: cannot declare permissions,
  concurrency, or multiple jobs; every adopter would re-assemble job wiring,
  which is exactly the logic-copying FR-001 forbids.
- *Single dispatcher workflow with a `stage` input* — all-or-nothing surface;
  violates US2 (subset adoption) and makes per-stage permissions impossible.
- *Template repository / copy-on-adopt* — no fix propagation (fails FR-008/SC-004).
- *Rewrite as a JavaScript/Docker action* — a full rewrite with no incremental
  dogfooding path; rejected on scope and risk.

## D2 — Event-agnostic stage interface: all context via `workflow_call` inputs

**Decision**: Published stages never read `github.event`. Every fact a stage
needs (issue number, spec dir/slug, head/base refs, merged flag, iteration,
comment id, …) is a declared input. The wrapper owns the trigger, the gate
conditions, and the event→input extraction. Where extraction is more than a
one-line expression (e.g., slug from a `spec-draft/NNN-slug` head ref;
cleanup's outcome selection), the *derivation lives inside the reusable
workflow* — the wrapper passes raw event facts (`head_ref`, `base_ref`,
`merged`) and the stage derives/validates internally, so wrappers stay
logic-free (SC-003).

**Rationale**: A called workflow sees the *caller's* event payload, so today's
`github.event`-reading logic would technically still work — but only for the
exact trigger this repo uses, which is precisely what FR-002 forbids
("no published stage may require ... this project's label taxonomy or gate
sequence"). Inputs make each stage triggerable from any event, `workflow_dispatch`,
or even another workflow (US2 acceptance 1 & 3).

**Alternatives considered**:
- *Keep event parsing in stages* — couples every stage to this repo's trigger
  shapes; fails US2.
- *Publish separate "extractor" composite actions for wrappers to call* — moves
  stage logic back into wrapper territory and doubles the published surface;
  the raw-facts-in, derive-inside pattern achieves the same with less API.

## D3 — Cross-repo internals: self-checkout at `github.job_workflow_sha`

**Decision**: Inside a reusable workflow, shared composite actions
(`speckit-context`, `speckit-metrics-summary`, new `speckit-preflight`) are
reached by first checking out the pipeline repository itself into a
subdirectory, pinned to the exact commit of the running workflow file:

```yaml
- uses: actions/checkout@v4
  with:
    repository: ${{ inputs.pipeline-repo }}   # default: the publishing repo
    ref: ${{ github.job_workflow_sha }}
    path: .speckit-pipeline
    persist-credentials: false
- uses: ./.speckit-pipeline/.github/actions/speckit-context
```

`pipeline-repo` is a defaulted input so forks that republish under another
name work without editing workflow bodies (constitution VI's "no hardcoded
repository names" honored in spirit; the default names the publisher, which is
pipeline mechanics, not project content).

**Rationale**: Relative `uses: ./.github/actions/...` inside a called workflow
resolves against the **caller's** workspace — in an adopting repo those paths
don't exist. Referencing `owner/repo/path@main` re-introduces version skew
(an adopter pinned to `v1.2.3` would silently get `main`'s composites, breaking
FR-008's pinning guarantee); stamping exact refs at release time requires
error-prone release tooling that rewrites workflow bodies.
`github.job_workflow_sha` is documented to hold "the commit SHA for the
reusable workflow file" for jobs using a reusable workflow — the composites are
therefore always the *same commit* as the stage logic, for exact tags, the
floating tag, and this repo's local-path dogfood calls alike. Zero release-time
rewriting.

**Alternatives considered**:
- *Reference composites as `owner/repo/path@vN`* — needs release-time ref
  stamping inside workflow bodies; skew bugs when a stamp is missed.
- *Inline the composites into every reusable workflow* — 8× duplication of the
  App-token and metrics logic; the maintenance cost FR-001 exists to eliminate.
- *Publish composites as their own versioned repo* — more moving parts, same
  skew problem.

## D4 — Credential contract: both secrets optional, fail-fast preflight, Claude Code precedence

**Decision**: Every agent-running stage declares two optional secrets,
`claude-code-oauth-token` and `anthropic-api-key`. A deterministic preflight
step (new `speckit-preflight` composite) fails the job **before any agent
step** when both are empty/absent, naming the two exact secret names (FR-004,
SC-005). When at least one is present, *both* are passed through to
`anthropics/claude-code-action` (`claude_code_oauth_token` /
`anthropic_api_key` inputs); when both are set, the API key wins — this is not
pipeline logic but Claude Code's own documented authentication precedence
(`ANTHROPIC_API_KEY` outranks `CLAUDE_CODE_OAUTH_TOKEN`), which the spec
clarification chose to defer to. Docs state the rule and link the upstream
precedence documentation.

**Rationale**: Passing both through and inheriting the tool's precedence means
zero selection logic to maintain and no behavior divergence from what adopters
read in Claude Code's own docs (spec clarification, session 2026-07-11).
A preflight that only checks non-emptiness costs nothing and cannot false-fail;
deeper validity checks (expired token) are intentionally out of scope — the
agent step's own auth failure covers those, still before any *successful*
billable work.

**Alternatives considered**:
- *Pipeline-defined precedence (OAuth first)* — contradicts the underlying
  tool's documented order; two sources of truth. Rejected by clarification.
- *Error when both set* — hostile to adopters migrating between plans. Rejected.
- *Single generic `claude-credential` secret + type input* — obscures which
  credential is in use; both upstream action inputs exist, use them.

**Verification posture** (spec clarification): OAuth path is continuously
verified by this repository's dogfooding; the API-key path ships implemented
and code-reviewed, with live verification deferred to adopter feedback.

## D5 — Configuration surface: typed `workflow_call` inputs with tiered defaults

**Decision**: Everything `vars.*`-driven today becomes a declared input with a
default equal to today's default: `implement-model` (`claude-sonnet-5`),
`max-iterations` (`5`), `tasks-review` (`auto`), plus per-stage `model` and
`max-turns` overrides where a stage has exactly one agent step. Inputs are the
*only* configuration channel of a published stage; this repo's wrappers wire
its existing `vars.SPECKIT_*` variables into those inputs, preserving current
behavior. The `model:opus` label opt-in remains wrapper-side (it is lifecycle
convention, not stage logic): the wrapper reads the label and passes the model
input.

**Rationale**: `vars` in a called workflow resolve from the *caller's*
repository — relying on them would work but makes the configuration surface
invisible (undeclared, untyped, undocumented in the workflow signature).
Declared inputs are self-documenting (FR-006, FR-010) and validated by GitHub.

**Alternatives considered**:
- *Keep reading `vars.SPECKIT_*` inside stages* — implicit contract, no
  defaults visible in the interface, name collisions in adopter repos.
- *A config file in the consumer repo (`.speckit.yml`)* — new parsing surface
  and drift risk; inputs already do this natively.

## D6 — Versioning, releases, and the publisher's own reference

**Decision**: Releases are git tags `vX.Y.Z` plus a floating major tag `v1`
advanced only for non-breaking releases (spec clarification). A new
`release.yml` workflow automates: validate `reusable-*.yml` lint, create the
exact tag from `main`, force-move the major tag, and generate release notes
with an explicit **Breaking changes** section (FR-008). Breaking changes ship
only behind a new major tag (`v2`). **This repository's wrappers call stages by
local path** (`uses: ./.github/workflows/reusable-<stage>.yml`) — the identical
`workflow_call` interface (same inputs, same secrets), resolved at the running
commit, so every dogfooded run exercises unreleased head (edge case: "test an
unreleased stage change") and interface breakage surfaces here before any tag
moves (US3, SC-003).

**Rationale**: Exact-plus-floating tags are the GitHub Actions ecosystem norm
adopters already expect (clarification, option A). Local-path self-reference is
the only arrangement where dogfooding validates changes *before* release; the
spec's assumptions explicitly accept the publisher referencing unreleased
versions. The interface FR-007 demands be shared is the `workflow_call`
contract, which local-path calls exercise byte-identically.

**Alternatives considered**:
- *Publisher pins `@v1` like adopters* — changes only validated *after*
  tagging; inverts dogfooding (fixes would ship untested, then break this repo).
- *Exact tags only, no floating major* — rejected by clarification.
- *Manual tagging* — automation-first (constitution IV) says no.

## D7 — Prerequisite detection: deterministic preflight, per-stage precondition checks

**Decision**: The `speckit-preflight` composite gains a spec-kit check used by
every stage after consumer checkout: `.specify/` present, `.claude/skills/speckit-*`
present for the skill the stage runs; failure message names the missing piece
and points to `specify init` + the adoption doc (FR-009). Stages with
predecessor dependencies additionally verify their concrete preconditions
before any agent step (e.g., plan requires `spec.md` + `spec-meta.json`; tasks
requires `plan.md` and `spec-meta.json.stage == "plan"`), reusing the refusal
patterns the stages already have today, but with messages that name the
providing stage rather than assuming this repo's lifecycle.

**Rationale**: Fail-fast with guidance is already the pipeline's idiom
(slug-refusal steps); extending it to environment prerequisites satisfies
FR-009/edge case 1 at near-zero cost and keeps SC-005's "before billable work"
guarantee uniform.

**Alternatives considered**:
- *Let the agent discover missing artifacts* — burns turns and produces
  confusing mid-run failures; exactly what edge case 1 forbids.
- *Version-checking spec-kit compatibility* — spec-kit records no reliable
  machine-readable version marker in consumer repos beyond
  `.specify/init-options.json` (not guaranteed present); presence checks +
  documented pinned-version prerequisite (docs) is the v1 posture.

## D8 — Documentation set

**Decision**: New `docs/adoption.md` is the canonical adopter guide:
prerequisites (own `specify init` output, credentials from the adopter's
Claude plan, GitHub App one-time setup), a minimal full-pipeline example
(copy-paste wrapper set), and a per-stage reference (inputs/secrets/outputs/
preconditions per stage — generated from contracts/stage-interfaces.md), plus
the credential precedence rule and wrapper-side security guidance (label gates,
commenter checks — constitution V obligations that move to wrappers).
`README.md`'s "adopt it today" section drops the copy-files step for a
version-pinned wrapper reference; `docs/setup.md` gains the API-key
alternative as first-class; `docs/architecture.md`'s "Reusability roadmap"
section is rewritten as current-state.

**Rationale**: FR-010 enumerates exactly this content; splitting adopter docs
from this repo's own setup keeps SC-001's under-60-minute path free of
publisher-only noise.

**Alternatives considered**: Single mega-README — fails the 60-minute test on
findability alone.
