# Wing Commander Constitution — Amendment History

The Sync Impact Report of every amendment to
[`constitution.md`](constitution.md), newest first, verbatim. Kept forever.
A new amendment adds its report to the top of this list (below this
header), not to `constitution.md` -- see CLAUDE.md.

<!--
Sync Impact Report — 2026-09-19
Version change: 1.6.1 → 2.0.0 (MAJOR: Principle V's merge sentence is redefined — it read "Humans merge every PR into `main`; the bot never approves or merges to `main`" and now names the two classes of merge the bot may perform — the bounded fix-PR merge and the verified dependency-bump merge — that new Principle X defines behind deterministic gates; every other merge stays human. V's entry sentence widens for the board loop: a maintainer's authorization is a label, the maintainer's own authorship, or the pipeline's own filing under a label only it applies. Redefining a sentence of a NON-NEGOTIABLE principle is a breaking governance change under this document's own semver rule, however narrow what it newly permits)
Modified principles: V. Security — Untrusted Content Is Never Instructions (two sentences: the entry sentence names what counts as a maintainer's authorization for the board loop, and the merge sentence names the two merge classes the bot may perform; the actor checks, the tool allowlists, the trusted-ref rule and the App-not-PAT rule are unchanged)
Modified sections: Development Workflow (gains the board loop as a second track beside the feature lifecycle, with its machine gate named)
Added sections: Principle X. Bounded Autonomy — The Pipeline Works Its Own Board
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (principle 5's summary no longer says "humans merge everything"; the numbered list gains 10)
  ✅ docs/architecture.md — updated in same PR (the Security bullet "Humans merge every PR into main. The bot cannot approve or merge." now states the V/X split; the stage diagram's three "human merge" arrows are unchanged, because the spec, plan and final PR merges stay human)
  ✅ docs/adoption.md, docs/setup.md — no change needed (verified: each restates the maintainer-applied entry label for intake, which this amendment leaves as it was; the widened entry sentence concerns only the board loop)
  ✅ CONTRIBUTING.md — no change needed (no merge-rule statement)
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: this repository's issue board is worked by hand in a fixed order — triage against current `main`, route by shape, fix, review, merge, prove — written down in CLAUDE.md's "Working the issue board" (#310) after the same six steps had been re-derived session after session. Every step already runs somewhere in the pipeline: the watchdog files and deduplicates issues, stage 10 routes a maintainer's review into fold-in legs, opens size-backstopped fix PRs to `main` and spins off `spec-request` issues, and lint-workflows with the registered gate suite decides green. What no stage could do was close the loop, because V's sentence forbade the bot every merge to `main`, so the owner's local sessions stayed the only place a bounded fix could finish. The board shows the cost: fix PRs #401 and #403 carry no review objects on GitHub at all — their reviews happened in local sessions, invisible to the board (III). The pipeline has been trusted since spec 033 to open PRs to `main` and since spec 055 to merge inside a disposable test repository; this amendment states the bounds under which it may merge one class of PR into this repository's own `main`, and keeps every other merge human.
Worked example: issue #408 — a scheduled stage that picks up the next open issue and works it through the six steps — is the first feature to be specified under Principle X, and it cannot be specified without it: intake would otherwise draft a spec that contradicts V. This PR carries no code; the feature is built through the pipeline (I), and its own spec, plan and final PRs are ones the humans merge. Issue #412 — every stage files the bugs it meets through a deterministic step — is the loop's feed and carries no dependency on this amendment.
Follow-up TODOs: #408 decides, through the clarify stage, the sweep cadence, the fix→review round cap, the reviewer's model tier, and whether a patch-level Spec Kit jump — which spec 034's tier verifies without the end-to-end stage — qualifies for the dependency-bump merge; #412 decides how a stage files the bugs it meets, and needs nothing from this document. Spec 027 FR-017's sentence that the auto-update stage never merges its own PR stays true of the stage and needs no edit; only its intent that a human merges every upgrade is superseded, for verified upgrades, by X.
-->
<!--
Sync Impact Report — 2026-09-14
Version change: 1.6.0 → 1.6.1 (PATCH: clarification — Principle VII gains one sentence stating that underscore-prefixed directories under `.github/actions/` are internal to this repository and are not part of the published, adopter-pinned surface, and that promoting one to the published surface later is a deliberate act in a future release, not a rename)
Modified principles: VII. Two Interfaces — The Published Contract and the Consuming Instrument (one sentence added; no other change)
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — no change needed (does not enumerate `.github/actions/` subdirectory naming)
  ✅ docs/architecture.md, docs/adoption.md, docs/setup.md — no change needed (none claims every composite under `.github/actions/` is published; this PATCH only makes the existing published/internal split explicit for the underscore-prefixed case)
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: specs/049-single-home-release-idioms found that `auto-release.yml` had re-typed three of `auto-update-spec-kit.yml`'s shared shell idioms instead of consuming a shared definition, and consolidating them into composite actions under `.github/actions/_shared/` exposed a gap this principle did not close: nothing on record said an underscore-prefixed directory is internal rather than merely unpublished-so-far, leaving it one accidental rename away from becoming an adopter-pinned surface by convention rather than by decision.
Worked example: this PR is the worked example — `.github/actions/_shared/scoped-app-token`, `.github/actions/_shared/orphan-branch-reset`, and `.github/actions/_shared/durable-failure-issue` are the first composite actions (not plain scripts) to live under `_shared/`, and Gate 60's promotion-prevention check enforces the amended sentence mechanically: a `workflow_call` stage or a non-underscore composite resolving a `_shared/` path fails the gate.
Follow-up TODOs: none
-->
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
