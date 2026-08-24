<!--
Sync Impact Report — 2026-08-23
Version change: 1.5.1 → 1.6.0 (MINOR: new principle added — IX. Judgment That Gates a Durable Action Belongs in Deterministic Code, requiring that judgment gating a filed finding, a fingerprint, a dedup outcome, or a write live in deterministic code rather than an agent's prompt, because a prompt instruction can be silently unfollowed with no error while code that computes the same input the same way every time cannot)
Modified principles: none
Modified sections: none
Added sections: Principle IX. Judgment That Gates a Durable Action Belongs in Deterministic Code
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (the numbered principle list gains 9)
  ✅ docs/architecture.md, docs/adoption.md, docs/setup.md — no change needed (verified: none enumerates the full principle list; each cites individual principles by numeral only, and IX is appended rather than renumbering)
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: spec 024 (Watchdog Precision & Determinism Hardening) closed five named gaps in the watchdog's own specification, and every one of them was the same shape wearing a different hat — a `denied-tool` finding shaped `{tool: null, denials: null}` passed FR-002 because a prompt asked for citation, not validity; a fingerprint drifted because its basis was model-authored prose a prompt could phrase two ways; a dedup lookup's failure was swallowed into "nothing found" because nothing deterministic distinguished "searched and found none" from "could not search." Each fix moved the gating judgment from a prompt instruction into code that computes the same answer from the same input every time. This is the same lesson Principle VIII already generalized for gates that cannot fail their own subject — a repeated pattern the repository kept re-deriving per-feature before writing it down centrally — applied one layer earlier, to the judgment a gate is built to check in the first place.
Worked example: this PR applies the principle five times inside spec 024 itself — the deterministic `wing-commander-8b-watchdog-self.yml` self-checker, standing in place of a prompt instruction to "check yourself too"; the watchdog's rung gate, already deterministic code (not a prompt) before this same PR retired the rung ladder it gated, itself prior art that the pattern predates its own naming; fingerprints derived from deterministic collector signal ids rather than model-authored `normalizedFacts` text, once the prose-authored basis was shown to drift; false-positive suppression pushed into the collectors that observe the world, rather than left to `diagnose`'s judgment over signals it cannot re-verify; and the `__new__` finding-class escape hatch, where the model proposes a name but a deterministic step — never the model — resolves and registers it.
Follow-up TODOs: none
-->
<!--
Sync Impact Report — 2026-08-23
Version change: 1.5.0 → 1.5.1 (PATCH: clarification — the Operational Constraints spec-kit pin no longer restates the version as a literal; it names the machine-readable source the auto-update stage maintains)
Modified principles: none
Modified sections: Operational Constraints — the spec-kit pin bullet
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/*.md — no change needed (no version references)
  ✅ README.md, CONTRIBUTING.md, docs/adoption.md, docs/setup.md — updated in the same PR: every "pinned v0.12.4" literal now points at the same source
Notes: PR #203 (merged 2026-08-23) moved the pin 0.12.4 → 0.16.4 in init-options.json and the preflight action, as the auto-update stage is specified to; it left seven prose mentions behind, this line among them, because the stage was never asked to maintain prose. Rather than teach it to, the prose stops carrying a number: a literal that nothing maintains is a stale literal waiting to happen.
-->
<!--
Sync Impact Report — 2026-08-22
Version change: 1.4.1 → 1.5.0 (MINOR: new principle added — VIII. A Green Check Means What It Says, requiring that a gate be able to fail its own subject: reachable through the gate registry, same subject and arguments locally as in CI, triggered by the tree or document it checks, loud rather than vacuous when it cannot reach that subject, not suppressible by an unrelated gate sharing its job, and every shipped failure branch covered by a checked-in fixture)
Modified principles: none
Modified sections: none
Added sections: Principle VIII. A Green Check Means What It Says
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (verified: its Constitution Check is the generic placeholder "[Gates determined based on constitution file]", so gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (verified: zero references to the constitution or to any principle)
  ✅ .specify/templates/tasks-template.md — no change needed (verified: zero references to the constitution or to any principle)
  ✅ .specify/templates/commands/*.md — directory does not exist in this repo; nothing to check
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
  ✅ README.md — updated in same PR (the numbered principle list gains VIII)
  ✅ docs/architecture.md, docs/adoption.md — no change needed (verified: both cite principles by numeral — II, V, VII — and VIII is appended, so nothing renumbers). No docs/quickstart.md exists.
Motivation: commit e24a7e4 ("four gates that could not fail their own subject") named the theme in its own first line — "each of these is a check whose green result did not mean what its output said" — and a review of the branch that followed found six more instances of the same class in eight findings. The repository keeps rediscovering this per feature and restating a local version of it each time: specs/036 FR-009, specs/037-rendered-tooling-list FR-015, and specs/039 FR-011 are three phrasings of one rule, while specs/026 had no version of it at all, which is why the tool-list table went a year with nothing holding it to the shipped call sites (#147). A cross-cutting invariant restated per spec is a cross-cutting invariant that new work is born exempt from; the constitution is where it belongs, because Governance already checks every spec, plan, and implementation PR against this file.
Worked example: the same PR that carries this amendment's sibling fixes applies the principle six times — Gate 26 gaining `!cancelled()` so an unrelated Gate 1 failure cannot suppress it; run-local-gates.py deriving each gate's ARGUMENTS from lint-workflows.yml, not just its path, after the bare invocation was found running verify-versioning-refs.py's live-network check where CI runs `--self-test`; verify-gate-18-scan.py gaining a repository-root guard so it can no longer report "0 failure(s)" having scanned nothing; Gate 27's collector gaining .yaml discovery and duplicate-label detection, each with a fixture; Gate 12's category C gaining five call-site fixtures that make permanent a branch previously proven only by a since-reverted manual experiment; and lint-workflows.yml's PR trigger gaining specs/**/contracts/** so the two gates whose subject is a contract document actually run when it changes.
Follow-up TODOs: none
-->
<!--
Sync Impact Report — 2026-08-09
Version change: 1.4.0 → 1.4.1 (PATCH: clarification — the Opus tier's model identifier moves from claude-opus-4-8 to claude-opus-5; the tiering itself is unchanged, only which model the "Opus tier" names)
Modified principles: II. Cost-Conscious Model Tiering (identifier only — spec/clarify tier, and the implementation opt-in tier)
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates: none (plan-template's Constitution Check is generic)
Notes: the watchdog diagnose carve-out added in 1.3.0 already named claude-opus-5, so after this amendment every Opus reference in the repository is on one identifier. Defaults changed in the same PR: intake.yml, clarify.yml (model), implement.yml (escalation-model), and the three wrapper fallbacks in wing-commander-1-intake.yml, wing-commander-2-clarify.yml, wing-commander-5-implement.yml (including the model:opus label tier). These are workflow_call defaults, so adopters pinning a tag are unaffected until they move the pin; anyone who has set WING_COMMANDER_SPEC_MODEL / _IMPLEMENT_MODEL / _IMPLEMENT_ESCALATION_MODEL keeps their own value.
-->
<!--
Sync Impact Report — 2026-07-28
Version change: 1.3.0 → 1.4.0 (MINOR: new principle added — VII. Two Interfaces, naming the split between the published stage contract and this repository's own consuming instrument, and requiring that any stage-layer deviation be a registered, machine-checked exception rather than a code comment)
Modified principles: none
Modified sections: none
Added sections: Principle VII. Two Interfaces — The Published Contract and the Consuming Instrument
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR: the Status section now states the two-layer split its stage/wrapper table already implied; the numbered principle list gains VII (and VI, missing since 1.2.0); and the repository map's published-stage list adds watchdog — it had named the same eight files release.yml Gate 1b greps, omitting the ninth
  ✅ .specify/templates/commands/*.md — directory does not exist in this repo; nothing to check
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
  ✅ docs/architecture.md — updated in same PR. Its "Stage workflows never read github.event.* or vars.*" claim was an assertion of fact and was false: watchdog.yml reads vars.* in 15 places. Now states the rule ("are required not to") and records the one deviation, why the release-time gate never saw it, and #149. Also corrects two stale counts in the same paragraph (nine published stages, eleven wrappers — it said eight of each). Deferring this was the original plan; a parallel /speckit-constitution run made the better case that the constitution and the docs must not contradict each other for even one merge, since the doc is what an adopter reads.
Worked example: PR #151 (merged) applies this principle before it was ratified — the watchdog's pause kill switch moved from the published stage's write gate, where it stopped writes but not work, to the two wrapper workflows that own the trigger, where it stops the run outright (constitution I: the repo is its own first example). #151 also removed the stage-side read, which #152 restores as a deprecated shim: that read ships in v2.1.0, so dropping it is a breaking change, and it is not worth a major for one of the stage's fifteen vars.* reads when the watchdog rework will remove all fifteen together. The principle governs where the gate BELONGS, not how fast the old one is torn out — the wrapper gate is the fix; the shim is a compatibility cost with a scheduled end.
Follow-up TODOs: #149 (extend the existing release.yml Gate 1b — move it to PR time, cover all nine stages, replace the brace-expansion omission with a declared waiver)
-->
<!--
Sync Impact Report — 2026-07-25
Version change: 1.2.1 → 1.3.0 (MINOR: Principle II gains a carve-out — the watchdog's diagnose step leaves the triage/haiku tier for claude-opus-5, and gets its own WING_COMMANDER_DIAGNOSE_MODEL override instead of sharing WING_COMMANDER_SUMMARY_MODEL; motivation in issue #124, run 30161188955 exhausted its turn budget at 21 turns and produced no verdict)
Modified principles: II. Cost-Conscious Model Tiering
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates: none (plan-template's Constitution Check is generic)

Sync Impact Report — 2026-07-24
Version change: 1.2.0 → 1.2.1 (PATCH: clarification — branch prefixes documented as consumer-configurable with defaults; no principle changed)
Modified principles: none
Modified sections: Operational Constraints — "Branch conventions" now names all five default prefixes (adds tasks/) and states they are consumer-configurable via repository variables (spec 018)
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ docs/setup.md — updated in same feature (adds the five WING_COMMANDER_*_PREFIX repository-variable rows)
  ✅ docs/adoption.md — updated in same feature (prefixes described as configurable-with-defaults)
  ✅ docs/architecture.md — updated in same feature (branch-prefix contract now configurable-with-default)
  ✅ specs/010-reusable-pipeline/contracts/stage-interfaces.md — updated in same feature (prefix inputs documented)
Follow-up TODOs: none
-->
<!--
Sync Impact Report — 2026-07-05
Version change: 1.1.0 → 1.2.0 (MINOR: new principle added)
Modified principles: none
Added sections: Principle VI. Portability — The Consuming Repository Owns Its Artifacts
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is
     generic; gates are derived from this file at plan time, no principle list to sync)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (adoption contract + roadmap sections)
  ✅ docs/architecture.md — updated in same PR (reusability contract cites VI)
  ✅ docs/setup.md — updated in same PR (adoption prerequisite)
Follow-up TODOs: none
-->
# Wing Commander Constitution

## Core Principles

### I. Guide — The Repo Is Its Own First Example
Every capability of the pipeline is built *through* the pipeline as soon as the pipeline can build it. Each feature begins life as a GitHub issue, becomes a spec under `specs/`, and flows through the same stages we ship to users. Documentation must always be able to point at a real spec, real PRs, and a real lifecycle issue in this repository as the worked example. If a change cannot be dogfooded yet (bootstrap phase), the reason is recorded in the PR description.

### II. Cost-Conscious Model Tiering
Every automated Claude invocation declares an explicit model, chosen by task weight: `claude-haiku-4-5` for triage, classification, labeling, and summaries — except the watchdog's `diagnose` step, which despite looking like classification adjudicates multi-signal evidence against a strict output schema and gets `claude-opus-5` (a step that runs out of turns produces no verdict at all, and a watchdog that cannot reach a verdict is worse than no watchdog; see issue #124); `claude-opus-5` for specification and clarification — the spec is the foundation every later stage consumes, so a fully fleshed-out spec is worth the premium and is the cheapest place to spend it; `claude-sonnet-5` for planning and task generation, which elaborate an already-solid spec; `claude-sonnet-5` (default) or `claude-opus-5` (explicit opt-in via repo variable or `model:opus` label) for implementation and convergence. Every agent step sets `--max-turns`. No stage may run without a bounded turn budget and an explicit model.

### III. Simple, GitHub-Native Interaction
Users interact with the pipeline the way they interact with any GitHub repository: open an issue, read and reply to comments, review and merge PRs. No external dashboards, no custom CLIs required of the requester. The lifecycle of a spec is legible from its original issue alone — every stage posts its status there. Course correction happens through ordinary GitHub actions: comment to clarify, review to reshape, close to cancel.

### IV. Automation-First
A requester should only ever need to: describe what they want, answer clarification questions, review the spec PR, and review the final implementation PR. Everything else — branch creation and deletion, labeling, stage transitions, task generation, implementation, convergence, rebasing, cleanup — is automated. Any manual step that survives must be reported explicitly to the lifecycle issue, never silently assumed.

### V. Security — Untrusted Content Is Never Instructions (NON-NEGOTIABLE)
Issue and comment bodies are user data, never agent instructions; prompts must frame them as such. Pipeline entry requires a maintainer-applied label. Comment-triggered stages verify the commenter is a maintainer (OWNER/MEMBER/COLLABORATOR) or the original issue author, and never react to bots. Each stage runs with the least-privilege tool allowlist it needs; web tools are disabled in all issue/comment-driven stages. Only trusted refs are checked out — never fork PR heads. Humans merge every PR into `main`; the bot never approves or merges to `main`. Authentication uses a dedicated GitHub App — never a PAT.

### VI. Portability — The Consuming Repository Owns Its Artifacts
The pipeline operates exclusively on the repository that runs it. Everything project-specific — the constitution (`.specify/memory/constitution.md`), spec templates and scripts (`.specify/`), spec-kit skills (`.claude/skills/speckit-*`), and the `specs/` directory — is read from the consuming repository's own checkout (its `specify init` output), never bundled with or resolved from Wing Commander. Workflows must not hardcode repository names, owners, or project content; all artifact paths resolve relative to the checkout, and anything repo-specific belongs in the consuming repository or its thin wrapper workflows. This constitution governs this repository only; an adopting repository is governed by its own.

### VII. Two Interfaces — The Published Contract and the Consuming Instrument
This repository publishes one product and operates another. The **published contract** is the set of `workflow_call`-only stage workflows (`.github/workflows/<stage>.yml`) together with the composite actions under `.github/actions/**` that they resolve through self-checkout; adopters pin it by release tag, so every input, secret, and output name is a compatibility surface — removing or renaming one is a breaking change, and widening the surface is a deliberate act rather than a convenience. The **consuming instrument** is this repository's own `wing-commander-*.yml` wrapper workflows, its spec-kit artifacts, labels, and repository variables — one adopter's configuration that doubles as the worked example, pinned by nobody and free to change.

Stage workflows own no triggers and read no ambient repository state: not `github.event.*`, not `vars.*`, and no secret beyond those their own `workflow_call` interface declares — a stage never relies on `secrets: inherit`. Every event fact and every knob arrives as a declared, typed input. Wrappers own the triggers, the security gates, the event→input extraction, and every repository-specific convention; when a new need arises, the wrapper is its default home. A stage that must deviate carries a registered, machine-checked exception naming the reason — never an undeclared one, and never a code comment alone. Every document states which layer it describes.

### VIII. A Green Check Means What It Says
A check that cannot fail its own subject is a liability, not coverage: it reads as evidence while proving nothing, and it displaces the scrutiny a maintainer would otherwise have applied. Every instance this repository has found was found by accident — a maintainer noticing a stall, a drill performed by hand — never by another check. Therefore: every gate MUST be reachable through the gate registry, and MUST run the same subject with the same arguments locally as it does in CI. Every gate MUST be triggered by changes to the tree or document it checks. A gate that cannot reach its subject — the wrong working directory, an empty file list, an unresolvable reference — MUST fail loudly rather than report a pass it did not earn. A gate MUST NOT be suppressible by the failure of an unrelated gate that merely shares its job. Every failure branch a gate ships MUST be exercised by a checked-in fixture; a manual demonstration during development is evidence for that reviewer, not coverage for the next one. Prior art: #139 and #158 (a verifier that sat green while checking a filter that did not ship), #169, #213, #215, #229, #147.

### IX. Judgment That Gates a Durable Action Belongs in Deterministic Code
Judgment that gates a durable action — a filed finding, a fingerprint, a dedup outcome, a write — belongs in deterministic code, not an agent's prompt. A prompt instruction is a request the model can silently fail to follow; it produces no error, no test failure, and no signal that the gate was ever skipped. Code that computes the same input the same way every time is the only form of that judgment a reviewer, a test, or a future maintainer can verify without re-reading the model's reasoning. This does not forbid a model from proposing a class, a description, or a diagnosis — it forbids trusting the model's own judgment on whether that output is well-formed enough, novel enough, or safe enough to act on. Prior art (spec 024's own worked examples): the deterministic `wing-commander-8b-watchdog-self.yml` self-checker, standing in place of a prompt instruction to "check yourself too"; the watchdog's rung gate, already deterministic code (not a prompt) before spec 024 retired the rung ladder it gated; fingerprints derived from deterministic collector signal ids rather than model-authored `normalizedFacts` text, once a prompt-authored fingerprint basis was shown to drift; false-positive suppression pushed into the collectors that observe the world, rather than left to `diagnose`'s judgment over signals it cannot re-verify; and the `__new__` finding-class escape hatch, where the model proposes a name but a deterministic step — never the model — resolves and registers it.

## Operational Constraints

- Spec artifacts live in `specs/<NNN-slug>/` (spec.md, plan.md, tasks.md, spec-meta.json, checklists/). `spec-meta.json` is the machine-readable source of truth for a spec's lifecycle state.
- Branch conventions: the pipeline's default branch prefixes are `spec-draft/<NNN-slug>` (draft spec PRs to main), `spec/<NNN-slug>` (long-lived per-spec integration branch), and `plan/<NNN-slug>`, `tasks/<NNN-slug>`, `impl/<NNN-slug>-iterN` (stage work branches). Each prefix is consumer-configurable via a repository variable, defaulting to the literal shown (see docs/setup.md).
- The implement ⟲ converge loop is capped (default 5 iterations); the final converge report is always posted to the lifecycle issue.
- Concurrent specs are supported: stages of one spec serialize via a per-spec concurrency group; different specs run in parallel.
- Spec-kit is pinned. The pinned version is the `speckit_version` in `.specify/init-options.json`, mirrored as `SPECKIT_SUPPORTED_VERSION` in `.github/actions/wing-commander-preflight/action.yml`; the auto-update stage moves both, and no prose in this repository restates the number. Upgrades re-verify `.specify/scripts` behavior before adoption.

## Development Workflow

Stages and their gates: intake (`/speckit-specify`, human gate = maintainer label + spec PR review) → plan (`/speckit-plan`, human gate = plan PR review) → tasks (`/speckit-tasks`, auto-committed by default, configurable to PR) → implement ⟲ converge (`/speckit-implement`, `/speckit-converge`, machine gate = tasks.md unchanged after converge) → finalize (human gate = final PR review) → cleanup (automated). A stage may only start when its predecessor's gate has passed.

## Governance

This constitution supersedes ad-hoc practice in this repository. Every spec, plan, and implementation PR is checked against it during review; violations must be fixed or the constitution amended first. Amendments arrive as ordinary PRs that modify this file, state the motivation, and bump the version below (semver: breaking principle changes = MAJOR, new principles/sections = MINOR, clarifications = PATCH).

**Version**: 1.6.0 | **Ratified**: 2026-07-04 | **Last Amended**: 2026-08-23
