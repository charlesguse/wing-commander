# Research: Comment-Triggered Stages Act Only on Maintainers

Every decision below was settled from this repository's precedent or from the owner's answers recorded in spec.md's Clarifications. None is open.

## D1 — Where clarify's own check sits

**Decision**: Add a step right after the pipeline checkout and before "Check lifecycle issue state".
- It reads the triggering comment by its id (`gh api repos/<repo>/issues/comments/<id>`) and outputs `maintainer=true` only when `user.type != "Bot"` and `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`.
- "Check lifecycle issue state" (`id: lifecycle-gate`) and "Note closed lifecycle and stop" both gain `steps.<check>.outputs.maintainer == 'true'`.
- Every later step is already gated on `steps.lifecycle-gate.outputs.is-open == 'true'`, an agent outcome, or a refusal output, so all of them skip.
- The job then succeeds with no reaction, no notice and no draft change.
- A failed API read fails the step and the job, because an unreadable association is never treated as a maintainer.

**Rationale**:
- `stalled` fires when the clarify job is `failure` or `skipped` (clarify.yml, `stalled` job). A refused comment must end the job successfully, or every non-maintainer comment would post a stall notice.
- The check keeps D2 of spec 010: the stage still reads no `github.event` and takes no new input. It reads the same comment it already fetches.
- It also keeps FR-008's silence: the 👀 reaction step is gated on `is-open`, so it skips too.

**Alternatives considered**:
- A new job in front of `clarify`. Rejected: `stalled` treats a skipped `clarify` as stalled, and every job costs at least a billed minute (spec 058).
- A new `actor-association` input. Rejected: it widens the published interface, and an older consumer wrapper would not pass it.
- Failing the job on refusal. Rejected: failure starts `stalled` and watchdog findings.

## D2 — Release classification

**Decision**: Ship in a normal v2.x release (auto-release, "Breaking changes: None").
- `issue-author-id` stays a declared input of `auto-update-spec-kit.yml`, documented as ignored.
- The PR title names the behaviour change so the generated notes show it.

**Rationale** (precedent): spec 095's tightening of a stage default (implement's `no-write-paths` default became `.claude/,.git/`, commit 263c6793, final PR #990) shipped in v2.7.9 with "Breaking changes: None." It has the same shape: a stage refuses more by default, with no input, secret or output removed and no change required of callers. Only v2.0.0 has ever carried breaking notes, and those required callers to change their wrappers. This feature requires no caller change.

**Alternatives considered**: a v3 major. Rejected by that precedent. Consumers on `@v2` would also never receive the rule.

## D3 — Single home of the relay text (FR-008)

**Decision**: Add a new composite, `wing-commander-requester-relay-note`.
- Inputs: `issue-number`, `token` and `body-file`.
- It reads the issue's `author_association`. When the author is not `OWNER`, `MEMBER` or `COLLABORATOR`, it appends one fixed paragraph to `body-file`.
- intake's "Announce clarification needed" and clarify's "Announce remaining clarification questions" call it on their body files before posting.
- If the read fails, it appends the paragraph, because the extra sentence is harmless to a maintainer, while a missing one leaves a requester without guidance.

**Rationale**: CLAUDE.md requires that cross-workflow shell has exactly one home, as a composite under `.github/actions/`. The callout composite is generic and has dozens of callers, so the text does not belong there.

**Alternatives considered**: inline copies in intake.yml and clarify.yml. Rejected by the single-home rule.

## D4 — The shared comment trust filter (FR-003)

**Decision**:
- In `wing-commander-issue-context`, remove `or .user.id == $aid` from the qualifying, excluded and staging filters, and drop the now-unused `AUTHOR_ID` read.
- `issue-raw.json`, the outputs and the staged file format are unchanged.
- intake's callout text becomes "not from a maintainer" (FR-004), and so does the live contract `specs/029-…/contracts/notice-callout.md`.

**Rationale**: the composite is the single home for the filter (its header, #499), so one edit covers intake and the board loop.

## D5 — The e2e clarify decision (FR-005)

**Decision**:
- Remove the author clause from `_shared/auto-release-e2e-clarify-decision.sh`, together with its author-id parameter.
- Remove auto-release.yml's two reads of the issue author id (the lazy resolution and its `fail_infra_on_read` path).
- Update the script's contract (`specs/055-…/contracts/gate-decision-scripts.md`) and its gates.

**Rationale**:
- The script is internal; auto-release is its only caller, and Gate 60 keeps published stages from resolving it.
- The e2e posts its answers with the maintainer token, so its verdicts do not change.
- Removing the read also removes one way the e2e can fail on infrastructure.

**Alternatives considered**: keep the parameter and ignore it. Rejected, because it leaves a dead API read that can fail the e2e.

## D6 — Clarify's agent grant (FR-007)

**Decision**:
- Remove `Bash(gh issue view:*)` from clarify's `default-allowed-tools`.
- The prompt's "not needed and not granted" sentence becomes accurate and stays.
- A consumer's `extra-allowed-tools` can still add it; docs/adoption.md says why not to.

**Rationale**: precedent recorded in spec.md's Clarifications (spec 051 contract row 8; #499).

## D7 — The regression gate (FR-010)

**Decision**: Add a new gate, `verify-maintainer-only-comments.py`, registered in lint-workflows.yml with the next free gate number at build time (Gate 179, after main and open PRs took 172 and 174). Its checks:
- (a) in every wrapper triggered by `issue_comment`, `pull_request_review` or `pull_request_review_comment`, no job `if:`, step `if:`, step `env:` value or `with:` value compares or passes an identity (`.user.id`, `issue-author-id`, `commenter-id ==`, actor or author ids, and any read of the issue's author except its kind, `issue.user.type`);
- (b) clarify.yml has the D1 check step before `lifecycle-gate`, both D1-gated steps carry its condition, and every later step skips for a refused comment (only the two argument-composing steps run ungated);
- (c) the issue-context filters contain no identity clause;
- (d) the Spec Kit updater's comment-reply `if:` compares no id;
- (e) the e2e decision script has no author clause;
- (f) clarify's allowed tools contain no `gh issue view`;
- (g) both clarification-question callouts are preceded, in the same job and under the same `if:`, by the relay composite on the same body file;
- (h) single home of the relay paragraph: its text appears only in the new composite, under `.github/` and in the live docs and contracts (i) reads, compared on letters and digits alone, so a re-wrapped or re-quoted copy is still found. Each sentence of 30 or more letters and digits is probed on its own (its first 60), so a copy of any one sentence is found too;
- (i) no live doc or contract in the gate's list (spec 130's T001 inventory, plus the docs and contracts its review passes found) writes an identity comparison (FR-009, SC-005);
- (j) pr-conversation.yml's stage-side "Authorized-actor gate" step admits by `inputs.actor-association` alone, with no identity in its `if:`, `env:` or `run:` (FR-010 names stages too);
- (k) single home of the relay step's comment: its key sentence appears only in clarify.yml, which carries Gate 47's `requester-relay-note` canonical marker, and intake.yml points at it;
- (l) no workflow, composite or live doc or contract describes the issue's author in prose as admitted next to the maintainer set;
- (m) `contracts/comment-author-rule.md`'s "Where it is enforced" table has a row naming every comment-triggered wrapper in `.github/workflows` (added after review pass 6).

Two harnesses also run the shipped shell against a stub `gh`: the D1 check step, and the relay composite.

Each check has a mutant that reintroduces what it forbids, and the self-test counts a mutant as caught only when its own check reports it. docs/reference.md lists loops, defaults and switches, not gates, so it gains no row (T003).

**Rationale**: CLAUDE.md says to add the "single home" check to a gate, because a rule with no gate behind it lasts only until the next session.
