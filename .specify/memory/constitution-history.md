# Wing Commander Constitution — Amendment History

The Sync Impact Report of every amendment to
[`constitution.md`](constitution.md), newest first, verbatim. Kept forever.
A new amendment adds its report to the top of this list (below this
header), not to `constitution.md` -- see CLAUDE.md.

<!--
Sync Impact Report — 2026-10-09
Version change: 2.3.1 → 2.4.0 (MINOR: Principle II gains a tier choice — a per-lifecycle `model:haiku` opt-in for implement — and a sentence on trial shadows; it also moves the Haiku tier's identifier from claude-haiku-4-5 to claude-haiku-5-5. Adding an opt-in changes the tiering even though no default moves, so this is MINOR, not PATCH, and the identifier change rides in the same amendment (spec 110 FR-003))
Modified principles: II. Cost-Conscious Model Tiering (the Haiku tier names claude-haiku-5-5; the implement sentence adds the `model:haiku` opt-in — `model:opus` wins when both are present, the escalation retry goes to claude-sonnet-5-5, implement only; a new closing sentence states that a trial shadow declares an explicit Haiku model and turn budget, is bounded and off by default, and acts on nothing, so the diagnose shadow does not read as running against the diagnose carve-out)
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ⚠ docs/setup.md, docs/adoption.md, docs/architecture.md — updated by spec 110's lifecycle PR (FR-004), not by this amendment: the amendment is human-merged on its own (FR-003) and the lifecycle PR carries no `.specify/memory/` edit
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: spec 110 (`specs/110-haiku-5-5-tier-trial`, lifecycle #972). Haiku 5.5 replaces Haiku 4.5 as the current Haiku, and spec 110 measures whether it can take work off Sonnet and Opus through a watchdog diagnose shadow and a `model:haiku` implement opt-in. FR-003 requires Principle II to name the new identifier, describe the opt-in, and say how a trial shadow fits beside the diagnose carve-out, in one MINOR amendment merged by a human that reaches `main` no later than the lifecycle PR. Gate 141 (`verify-haiku-tier-model-id.py`, FR-006) scans this file and fails while it names claude-haiku-4-5.
Worked example: this PR is spec 110's task T004. Its lifecycle PR (finalize PR #982) carries the stage, wrapper and doc changes and Gate 141; with this amendment on `main`, Gate 141 passes there.
Follow-up TODOs: moving any step's default to Haiku on the strength of trial data is a further MINOR amendment and the owner's decision (spec 110 User Story 4). The 2.3.1 report below says claude-haiku-4-5 "is still the current Haiku and stays"; that was true when written and is superseded here.
-->
<!--
Sync Impact Report — 2026-10-05
Version change: 2.3.0 → 2.3.1 (PATCH: clarification — the Opus tier's model identifier moves from claude-opus-5 to claude-opus-5-5 and the Sonnet tier's from claude-sonnet-5 to claude-sonnet-5-5; the tiering itself is unchanged, only which models the tiers name. claude-haiku-4-5 is still the current Haiku and stays)
Modified principles: II. Cost-Conscious Model Tiering (identifiers only — the watchdog diagnose carve-out, the spec/clarify tier, the plan/tasks tier, and the implementation default and opt-in tiers)
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates: none (plan-template's Constitution Check is generic); docs/setup.md, docs/adoption.md and docs/architecture.md updated in same PR
Notes: defaults changed in the same PR: the workflow_call defaults in intake.yml, clarify.yml, plan.yml, tasks.yml, rebase.yml, implement.yml (model, escalation-model), pr-conversation.yml, watchdog.yml (diagnose-model) and auto-update-spec-kit.yml (both model inputs); the in-step fallbacks in lifecycle-review-gate.yml and board-loop.yml (including board-loop's model:opus tier); and the wrapper fallbacks in wing-commander-1/2/3/4/5/9, -auto-update-spec-kit and -rebase (including the model:opus label tiers). These are workflow_call defaults, so adopters pinning a tag are unaffected until they move the pin, and anyone who has set a WING_COMMANDER_*_MODEL repository variable keeps their own value; this repository's own WING_COMMANDER_IMPLEMENT_MODEL (claude-sonnet-5, equal to the old default) was deleted so implement follows the default. Left on the old identifiers on purpose: watchdog.yml's deprecated propose-fix-model default (no step reads it; the input is slated for removal at the next major version), and the historical-tense mentions in wing-commander-8-watchdog.yml's pause comment and docs/architecture.md's pre-spec-024 ladder and fingerprint-drift account, which name the model that actually ran. Opus 5.5 is priced below Opus 5 ($4/$20 vs $5/$25 per MTok) and Sonnet 5.5 matches Sonnet 5 ($2/$10), so the amendment does not raise cost.
-->
<!--
Sync Impact Report — 2026-10-01
Version change: 2.2.0 → 2.3.0 (MINOR: Principle V gains one sentence stating that an automated stage's agent MUST NOT write under `.claude/` with `Edit`/`Write`, for any of its three parts — the vendored `.claude/skills/speckit-*` artifacts under the Spec Kit pin, this repository's own skills, and the control surface (`.claude/settings.json`, `.claude/hooks/`) — denying an agent the ability to rewrite its own permission settings and hooks mid-run, while the deterministic, non-agent writes `auto-update-spec-kit.yml` already performs under `.claude/skills/speckit-*` remain permitted. This is a materially expanded statement of the existing "least-privilege tool allowlist" sentence, not a new principle, so MINOR rather than MAJOR)
Modified principles: V. Security — Untrusted Content Is Never Instructions (one sentence added mid-paragraph, immediately after the existing least-privilege/web-tools sentence; the entry-authorization, actor-check, tool-allowlist, trusted-ref and App-not-PAT rules are otherwise unchanged)
Modified sections: none
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (principle 5's summary sentence now names the stage agent's inability to write its own `.claude/` control surface, beside "least-privilege tools")
  ✅ docs/architecture.md — no change needed (its least-privilege-tools mentions, at the Security-principle summary line and the risk table's "Prompt injection via issue/comment bodies" row, are already generic umbrella statements that this sentence narrows rather than contradicts; neither enumerates specific paths)
  ✅ docs/adoption.md, docs/setup.md — no change needed (docs/adoption.md's "Wrapper security obligations" section already states the generic "least-privilege agent tool allowlists" umbrella; the concrete `no-write-paths`/`write-boundary-label-prefix` input rows spec 090 (`specs/090-stage-write-boundary`) added to its per-stage input tables land with that feature's own implementation, not with this amendment)
  ✅ CONTRIBUTING.md, CLAUDE.md — no change needed (CONTRIBUTING.md's `.claude/skills/speckit-*/` row already tells a human contributor not to hand-edit vendored artifacts, a distinct rule from an automated agent's in-run `Edit`/`Write` boundary; CLAUDE.md carries no merge or tool-allowlist statement this touches)
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: spec 090 (`specs/090-stage-write-boundary`, lifecycle #675) FR-002 requires an automated stage's agent be barred from writing under `.claude/` with `Edit`/`Write`, and FR-018 requires that policy be recorded "where a future change will read it": the boundary's single definition (`no-write-paths`'s own input description on `implement.yml`) and, to the extent it states something about an agent's own control surface the constitution does not already say, the governing document itself. Principles V, VI, VII and IX each state a piece of the surrounding rationale — least-privilege (V), portability of `.specify/`/`.claude/skills/speckit-*` (VI), the published-contract/consuming-instrument split (VII), deterministic gating of durable actions (IX) — but none states this specific "an agent may not write its own control surface" rule, so FR-018's constitution-side leg is genuinely new content, not a restatement.
Worked example: this is the amendment FR-018 requires; the boundary itself is a new optional `no-write-paths` stage input (default `.claude/`) on `implement.yml`, classified and routed by `.github/actions/_shared/classify-out-of-boundary-tasks.sh` and enforced by Gate 133 (`verify-write-boundary.py`), documented in `no-write-paths`'s own input description as the single definition FR-003 requires.
Follow-up TODOs: none.
-->
<!--
Sync Impact Report — 2026-10-01
Version change: 2.1.0 → 2.2.0 (MINOR: Principle X narrows what the pipeline may file for spec-shaped work — a `spec-proposal`, which only the owner promotes by applying `spec-request` — and states that a fix-shaped change the loop's credential cannot push is held for a maintainer rather than re-classed as spec-shaped. No merge class, gate, or kill switch changes; the pipeline loses an act (applying `spec-request`), it gains none)
Modified principles: X. Bounded Autonomy — The Pipeline Works Its Own Board (the spec-shaped sentence: "may only file it as a `spec-request`" becomes "may only file it as a `spec-proposal`", entered into the lifecycle only by the owner's `spec-request`, plus the held-not-re-classed sentence for unpushable fixes; the closing "What stays human" sentence names the promotion of a proposal instead of "every route that reaches `spec-request`")
Modified sections: Development Workflow (the board loop's exits toward the feature lifecycle are a `spec-proposal` the owner may promote, or a closed issue)
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (principle 10's summary says spec-shaped work is filed as a `spec-proposal` only the owner can promote)
  ✅ docs/architecture.md — updated in same PR (the Security bullet names `spec-proposal` and the workflow-scope hold)
  ✅ docs/setup.md — updated in same PR (the `spec-proposal` label row, `board:stalled`'s new trigger, and `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS`)
  ✅ CLAUDE.md — already states the rule for local sessions (board reset PR #892)
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: the board reset of 2026-10-01 (issues #889, #890). The board loop filed every spec-shaped item with the `spec-request` label already applied, and an App-token label event starts intake, so a machine-found defect went straight to a drafted spec and clarify questions for the owner without the owner ever choosing it — 21 lifecycles waited in clarify at once, none of them roadmap work. Separately, the route step counted any workflow edit as a contract change, so in a repository that is mostly workflow YAML nearly every fix (a one-line comment correction included, #749 → #858) became a spec; the real constraint was that the App cannot push workflow files at all. This amendment makes the owner's label the only door into the lifecycle and keeps a push-permission problem out of the spec lane.
Worked example: board-loop.yml's three filing sites (route's spec verdict, fix's post-push breach, readiness's backstop breach) now pass `--label spec-proposal`; route's new `hold` verdict (`board_route_backstop.workflow_push_blocked_paths()`) stalls the issue with a comment naming the workflow files instead of filing anything; Gate 93 recognises both labels at filing sites, and `verify-board-route-backstop.py` holds the hold wiring with fixtures and mutations.
Follow-up TODOs: granting the App Workflows (read and write) and setting `WING_COMMANDER_BOARD_CAN_PUSH_WORKFLOWS` is the owner's decision; until then workflow-file fixes are held. `docs/adoption.md` is unchanged — it describes the published stages, and the board loop is not one. The sentence is scoped to the board loop on purpose: pr-conversation's `new-spec` spin-off (spec 033) still applies `spec-request`, because a maintainer's own PR comment asked for that spec — it is the maintainer's act, relayed.
-->
<!--
Sync Impact Report — 2026-09-29
Version change: 2.0.0 → 2.1.0 (MINOR: Principle X gains a third class of merge the bot may perform — the lifecycle pull request merge, the feature lifecycle's final implementation PR merged by spec 062's lifecycle review gate only while `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` is on, behind eight deterministic gates re-derived at the exact head SHA and the `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` kill switch — and Principle V's merge sentences widen from two classes to three. This adds a third instance of the bounded-merge pattern 2.0.0 established rather than redefining what "the bot never merges" means, so it is a new authorized class under that pattern, not a breaking change to it; with the setting at its default (off), who merges what is unchanged)
Modified principles: V. Security — Untrusted Content Is Never Instructions (two sentences: humans merge every final implementation PR only while `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` is off, and the bot's merges are the three classes X defines, naming the lifecycle pull request merge; the spec PR, plan PR and amendment merges stay human unconditionally, and the entry, actor-check, tool-allowlist, trusted-ref and App-not-PAT rules are unchanged); X. Bounded Autonomy — The Pipeline Works Its Own Board (the dependency-bump class is no longer "the only other" class; a new third paragraph states the lifecycle pull request merge in the fix-PR class's own terms — its eight deterministic gates, its kill switch, the announcement on the lifecycle issue, the squash commit one human action reverts, and the hand-off to a maintainer when a workflow-touching PR needs a scope the credential lacks; the closing "What stays human" sentence moves to the end of that paragraph and now keeps the final PR merge human only while the setting is off)
Modified sections: Development Workflow (finalize's human gate names when the final PR merge may be the lifecycle pull request merge; the board loop's merges are named as the fix-PR and dependency-bump classes, since the third class is the lifecycle review gate's, not the loop's)
Added sections: none
Removed sections: none
Templates requiring updates:
  ✅ .specify/templates/plan-template.md — no change needed (Constitution Check is generic; gates are derived from this file at plan time)
  ✅ .specify/templates/spec-template.md — no change needed (no principle references)
  ✅ .specify/templates/tasks-template.md — no change needed (no principle references)
  ✅ README.md — updated in same PR (principle 5's summary no longer says humans merge every final PR unconditionally; principle 10's "The bot merges two classes only" names the third)
  ✅ docs/architecture.md — updated in same PR (the Security bullet's "merges two classes only (constitution X)" now names the lifecycle pull request merge and its setting, gates and kill switch; the stage diagram's final-PR "human merge" arrow is unchanged, because it describes the default — the setting ships off; see Follow-up TODOs)
  ✅ docs/adoption.md, docs/setup.md — no change needed (verified: neither states which merges the bot may perform; the repository variables that bound the new class belong in docs/setup.md beside the workflow that reads them, which is not yet on `main` — see Follow-up TODOs)
  ✅ CONTRIBUTING.md, CLAUDE.md — no change needed (no merge-authority statement; CLAUDE.md's merge rules concern the board and local sessions)
  ✅ .specify/extensions.yml — absent; no before/after_constitution hooks apply
Motivation: spec 062 (`specs/062-lifecycle-review-gate`, lifecycle #476, finalize PR #648) runs a code review as a gate on the lifecycle's final implementation PR, folds in-scope findings back through implement, and — only when a maintainer sets `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` to `true` — squash-merges that PR once the round comes back clean. Principle V named exactly two classes of bot merge and said a bot merge outside them "violates this principle rather than extending X", and X's closing sentence kept the final PR merge human unconditionally, so the capability could not lawfully ship without both passages moving (spec 062 FR-031). The spec requires the amendment to land as a separate, human-merged PR against `main` (FR-033), stating the class's deterministic gates and kill switch in the same terms the fix-PR class uses (FR-032); its gate `verify-constitution-merge-class-parity.py` (FR-038) fails while `lifecycle-review-gate.yml` carries the `WING_COMMANDER_LIFECYCLE_AUTO_MERGE`-gated `gh pr merge` and Principles V/X still describe two classes — issue #765.
Worked example: this PR is the amendment spec 062 FR-031–FR-033 require, drafted to its `contracts/constitution-amendment.md`. The eight gates X now names are the eight conditions `lifecycle_merge_preconditions.py` evaluates in order (data-model.md §5, built on §4's readiness decision): `checks_green`, `gate_suite_green`, `mergeable`, `reviewed_at_this_head`, `kill_switch_clear`, `round_clean`, `no_open_findings`, `no_unresolved_human_review`. Run against spec 062's `lifecycle-review-gate.yml`, the parity gate fails against the 2.0.0 text and passes against this one. It is itself a merge the new class never reaches: an amendment to this document, merged by a human.
Follow-up TODOs: #765 closes once spec 062's implementation and this amendment are both on `main` and the parity gate runs green there. `WING_COMMANDER_LIFECYCLE_AUTO_MERGE` stays off until both have landed; setting it is a maintainer's act, not this amendment's. Spec 062's implementation (as of its branch at the time of this amendment) does not yet document `WING_COMMANDER_LIFECYCLE_AUTO_MERGE`, `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_PAUSED` or `WING_COMMANDER_LIFECYCLE_REVIEW_GATE_MODEL` in docs/setup.md, nor the lifecycle review gate in docs/architecture.md (including the stage diagram's final-PR merge arrow once the setting can be on); that documentation lands with the workflow, not with this amendment.
-->
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
