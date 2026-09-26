# Phase 0 Research: Fine-grained maintainer token for the auto-release end-to-end harness

Input: `spec.md`, already fully clarified (Session 2026-09-25 resolved all
three open questions on lifecycle issue #506; `checklists/requirements.md`
confirms no `[NEEDS CLARIFICATION]` marker remains). This phase resolves
*technical* unknowns — how the existing `verify-e2e` precheck accepts and
verifies the new credential shape — not what to decide, which the spec's
Clarifications session already settled. No decision below reopens Q1–Q3.

Each entry is a Decision / Rationale / Alternatives triad, per the plan
template's format. File:line citations are against `auto-release.yml` and
related files as of `0c12ced` (the branch head this plan starts from).

## D1. Detecting which accepted shape the secret holds (FR-003, FR-007)

**Decision**: detect the shape from the token's own literal prefix before
any network call — GitHub's PAT prefixes are a stable, documented format:
classic personal access tokens begin `ghp_`, fine-grained personal access
tokens begin `github_pat_`. A value matching neither prefix ends the attempt
`fail-infra` with its own distinguishable reason ("the credential's own
format matches neither accepted shape"), which is a sixth branch alongside
FR-008's five, not a collapse into one of them — it is what shape detection
itself produces before any of the five existing checks can even run.

**Rationale**: FR-003's dual acceptance requires the precheck to know which
of the two accepted shapes it is looking at before it can decide which
checks apply (FR-016's Administration-absence bound is fine-grained-only).
A prefix match is a single deterministic string comparison — no API round
trip, no dependency on GitHub's own error text, and it runs before the
credential ever touches the network, so a malformed secret is named as such
rather than surfacing as a confusing authentication failure. It also keeps
Constitution IX intact: nothing about "which shape is this" is left to an
agent's judgment, because no agent is anywhere near this job.

**Alternatives considered**: infer the shape from behavior (e.g., try the
fine-grained-only probes of D5/D6 and see if they even return a coherent
answer) — rejected: behavior-based inference conflates "wrong shape" with
"right shape, wrong permission," which is exactly the FR-008 distinction
this feature must keep sharp, and it would spend an extra round trip to
learn something the literal value already states. Ask the maintainer to
also set a shape-declaring variable — rejected: a second knob that must
agree with the secret's own content is a drift hazard FR-017's whole point
is to avoid, and the prefix already carries the answer.

## D2. Reading a fine-grained credential's expiry (FR-010)

**Decision**: read the `github-authentication-token-expiration` response
header GitHub attaches to any authenticated API response made with a
fine-grained personal access token (present whenever the token carries an
expiry, which FR-002 makes mandatory for this shape); compare it against
"now" plus a configured warning window. The window is a new repository
variable, `WING_COMMANDER_AUTO_RELEASE_E2E_MAINTAINER_TOKEN_EXPIRY_WARNING_DAYS`,
defaulting to 14 when unset, documented in `docs/setup.md` §3 alongside the
canonical statement's rotation guidance (FR-006). A classic token carries no
such header (classic tokens are not required to expire), so "expiry not
observable" is the classic-shape default path FR-010's own wording
("when the credential's expiry is observable") already anticipates — it is
not an error, and it proceeds exactly as specs/055 does today.

**Rationale**: this is the only place GitHub surfaces a fine-grained PAT's
own expiry to the API consumer — there is no separate "describe this
token" endpoint, mirroring the same absence of introspection that D5/D6
below work around. Reusing an existing authenticated call (the precheck
already calls `gh api user`) to read the header costs nothing extra. A
configurable window, rather than a hardcoded one, matches FR-006's
"maintainer should choose" framing and this repository's existing pattern
of a documented default a maintainer can override (e.g.
`WING_COMMANDER_AUTO_RELEASE_E2E_CONTAINER_PAUSED`).

**Alternatives considered**: require the maintainer to record the expiry
date in a repository variable alongside the secret — rejected: a
maintainer-entered date is a second copy of information the token already
carries and can drift from the token's real expiry the moment it's
rotated, which is precisely the kind of un-verified assertion Constitution
VIII exists to forbid. Skip the warning window and only fail on an already-
expired token — rejected: FR-010 explicitly asks for an approaching-expiry
note in the report, not just a hard failure, so a maintainer sees the
rotation coming rather than discovering it the day an attempt starts
failing.

## D3. The existing containment check already generalizes to the new shape (FR-012, FR-013)

**Decision**: keep the existing `user/repos?affiliation=owner,collaborator,
organization_member` read (specs/055 D2, `auto-release.yml`'s
"fixture maintainer identity's credential" step, Gate 67) as the
containment mechanism for both shapes, unmodified in its core comparison
(reachable set == exactly the configured test repository). No new
containment logic is needed for the fine-grained shape.

**Rationale**: a fine-grained PAT's `/user/repos` response is itself
restricted to the token's own selected repository set (the API surface a
fine-grained token can reach is a function of what was granted to it, not
of everything the account owns) — so the same read that reflects "every
repository this classic token's account can reach" today reflects "every
repository this fine-grained token was scoped to" once the shape changes,
with no code difference. This also resolves the Edge Case "a credential
scoped to 'all repositories of this account'": today's invariant (the
reachable set must equal exactly one name, the configured repository) is a
property of what the token actually reaches at call time, not of which
repository-selection option issued it — so a token scoped to "all
repositories" already fails containment the moment the account's own
repository count is ever more than one, which is exactly the failure mode
FR-013 asks to be caught. Nothing about the check needs to know which
selection mode produced the token; it only needs to keep observing the
actual reachable set, which it already does.

**Alternatives considered**: add a second, shape-specific containment path
that inspects the token's declared repository selection directly —
rejected: GitHub exposes no such introspection for a PAT (see D5/D6's same
constraint), so there is nothing to read that the existing behavioral check
does not already observe more reliably. Trust the fine-grained shape's own
scoping and skip the containment read for it — rejected explicitly by the
spec's Assumptions ("kept rather than deleted... it is what turns the
scoping claim into an observation") and by User Story 3/Constitution VIII;
this feature does not weaken FR-012 for either shape.

## D4. Distinguishing "reached nothing" from "could not observe" (FR-013, User Story 3)

**Decision**: capture the exit status of the `gh api "user/repos?..."`
call separately from its output, rather than folding a transport/auth
failure into the same `2>/dev/null` swallow the pipeline through `sort -u`
uses today. A non-zero exit from the `gh api` call itself (network error,
malformed token, or — the case this feature newly makes possible — a
fine-grained token whose selected permissions don't even allow listing
its own repositories) produces a `fail-infra` verdict whose observed text
says containment could not be established, distinguishable from the
existing "reached 0 repositories" text, which remains reserved for a call
that *succeeded* and returned an empty set.

**Rationale**: this is a real, pre-existing gap the current step's `||
true` idiom papers over — before this feature, a classic token could
plausibly always list something (`repo` scope implies at least the token's
own account's repositories), so the ambiguity was theoretical; a
fine-grained token's narrower, per-repository-selected permission model
makes "the token cannot enumerate its own reachable set" a real
possibility for the first time, and Acceptance Scenario 3 of User Story 3
requires the two outcomes be distinguishable. Constitution VIII: a
containment check that reports "reached 0 repositories" when it actually
observed nothing at all is exactly the vacuous-pass shape (here, a
vacuous-*fail*-that-reads-like-a-different-fail) the principle forbids —
same text for two different root causes is a legibility defect even
though both are already `fail-infra`.

**Alternatives considered**: leave the existing swallow-and-count logic
unchanged and accept that both cases render as "reached 0 repositories" —
rejected by FR-013's explicit wording and by User Story 3's third
Acceptance Scenario. Treat every empty result as "could not determine"
— rejected: it would misreport an account that genuinely, successfully,
reaches nothing (a real containment problem, at that — an account invited
nowhere at all) as a transport failure, losing information the current
text already conveys correctly for that case.

## D5. Verifying the fine-grained shape carries no Administration permission (FR-016)

**Decision**: probe a read-only, list-shaped REST endpoint that GitHub's
own fine-grained PAT permission model gates behind the repository
**Administration** permission — `GET /repos/{owner}/{repo}/collaborators`
is such an endpoint. A fine-grained token that can list collaborators
carries Administration and fails the precheck with its own distinguishable
`fail-infra` verdict (FR-008's "the credential grants Administration
permission" branch, separate from every other branch); one that gets
rejected (GitHub's fine-grained tokens return a 403 with a body naming the
missing permission, distinct from the account's own `viewerPermission`,
which stays ADMIN by construction — FR-016 — regardless of what the token
itself is scoped to) passes this check. This probe runs only on the
fine-grained branch (D1); a classic credential is never subjected to it,
matching FR-003's stated asymmetry.

**Rationale**: GitHub does not publish an endpoint that returns "here is
the permission set this PAT was granted" the way a GitHub App installation
token's own installation record does — the only way to observe what a
fine-grained token can do is to attempt an act gated specifically by the
permission in question and read whether it was accepted or rejected. This
is the same "verified rather than merely asserted" posture the spec's own
Context section calls for (line 39), applied to the one permission this
feature must prove is *absent* rather than present. Listing collaborators
is read-only, has no side effect, needs no fabricated resource id, and is
one of the endpoints GitHub's own fine-grained-PAT permission-requirements
reference assigns to Administration specifically, so a pass/fail on it is
a direct read of that one permission and nothing else.

**Alternatives considered**: read `viewerPermission` via `gh repo view`
(the existing D2-from-055 call) and treat ADMIN as a failure — rejected:
after the FR-002 transfer, the *account* is ADMIN on the repository by
construction (ownership), so this field reports the account's role, not
the token's own granted permission, and would fail every fine-grained
credential unconditionally, defeating the very feature this plan builds.
Attempt a genuinely destructive Administration-gated call (e.g. read
branch protection, or the repository's own settings) — rejected as a
riskier probe than listing collaborators for no additional signal; a
read-only, always-safe-to-call endpoint is preferable whenever the
permission mapping offers one.

## D6. Verifying the fine-grained shape carries the two write permissions it needs (FR-007)

**Decision**: probe Issues:write and Pull-requests:write the same way as
D5 — by attempting a write-shaped call gated by that specific permission
against a resource id chosen to certainly not exist (a very large integer,
e.g. issue/PR number `999999999`), and reading GitHub's response: a
fine-grained token lacking the permission is rejected before the resource
lookup even happens, distinguishably from "permission present, resource
absent." The existing `viewerPermission` WRITE-or-higher check (specs/055
D2) is retained for the classic shape, where it remains the authoritative
permission proof exactly as it is today, but is downgraded to a cheap
reachability/authentication check (not a permission proof) on the
fine-grained shape, per D5's reasoning that `viewerPermission` reflects the
account's role, not the token's.

**Rationale**: the two acts the harness actually performs — commenting on
an issue, merging a pull request — are exactly Issues:write and
Pull-requests:write in GitHub's fine-grained permission model (FR-002,
FR-007). Probing against a resource that is certain not to exist means the
probe is free of any real side effect and free of any dependency on
finding a real target in the (freshly reset) test repository at precheck
time — the precheck runs before the reset step, so no fixture-scoped
resource is even guaranteed to exist yet. The permission-before-lookup
ordering this probe relies on is the same GitHub behavior D5's collaborator
probe already depends on (a fine-grained PAT's rejection is a property of
the grant, not of what it's pointed at), so this is not a second unproven
assumption, just the same one applied to a different permission and a
different resource shape (write vs. list).

**Alternatives considered**: skip the up-front write-permission proof for
the fine-grained shape and let the first real gate-driving act (the
clarification reply) fail naturally if the grant is missing — rejected for
the same reason specs/055 D2 rejected it for the classic shape: it would
surface as a late, spend-incurring `fail-gate-stall` rather than a
zero-cost `fail-infra`, which is exactly what FR-007's "before any
gate-driving spend" and SC-002's "zero gate-driving agent cost" forbid.
Perform the probe against a real, disposable resource created for the
purpose — rejected: creating something (even to delete it immediately
after) is an avoidable side effect and a race against the reset step that
a nonexistent-id probe does not have.

## D7. Enforcing "exactly one canonical statement" across four non-workflow sites (FR-017, FR-018)

**Decision**: `docs/setup.md` §2's existing secret row remains the
canonical statement, rewritten (not duplicated) to state the dual-accepted
shape, the fine-grained shape's scope/permissions/expiry/rotation, and the
Administration bound (FR-016/FR-020). The other three sites the spec names
— `auto-release.yml`'s comment block above the credential step, the
precheck's own expectation text (the `fail-infra` verdict's `expected`
field content, and Gate 67's scenario descriptions), and
specs/055-unattended-e2e-gates' superseded D1/D2 and Clarifications session
— become pointers at it. A **new** gate script enforces this, rather than
extending Gate 47 (`verify-comment-canonical-pointers.py`): Gate 47's own
docstring states its scope is "`#` comments in .github/workflows/*.yml" —
it validates that a pointer found there resolves and is on-topic, but it
never scans `docs/*.md` or `specs/*/research.md` as a pointer *source*, so
a contradicting sentence reintroduced in `docs/setup.md` or in specs/055's
research.md would not be caught by it even though its target-resolution
logic already understands `.md` targets. The new gate instead follows the
narrower, topic-specific pattern this repository already uses for a single
cross-cutting statement (e.g. Gate 72's FR-003 paragraph/step pairing): it
knows the small, fixed set of phrases that would contradict the canonical
statement (e.g. an unqualified "not fine-grained" or "never fine-grained"
claim, or "classic PAT... the only accepted shape") and asserts every
occurrence outside `docs/setup.md`'s canonical row either is absent or
carries an explicit pointer (`-- see docs/setup.md` / `(see docs/setup.md)`)
to it, and that specs/055's own superseded text carries the FR-019
annotation rather than having been silently rewritten.

**Rationale**: FR-017's four named sites span two file types Gate 47 does
not treat as pointer sources at all (`docs/*.md`, `specs/*/research.md`),
so satisfying FR-018 ("a gate MUST fail when a statement contradicting the
canonical one reappears anywhere in the repository") requires either
widening Gate 47's declared, documented scope — a generic mechanism this
repository has deliberately kept narrow and grounded in the filesystem
(Gate 47's own docstring, part (c)) — or a second, topic-scoped gate that
does not have to be generic because it is checking one specific, named
claim. This repository already prefers the second shape for a single
cross-cutting statement over generalizing an existing generic gate (Gate
72 versus Gate 47's own pointer mechanism are two different gates for two
different kinds of "one statement, many sites" problem). A topic-specific
gate is also simpler to keep honest under Constitution VIII: its own
mutation is "reintroduce one of the known-contradicting phrases without a
pointer," which is exactly what SC-004 asks to be demonstrably catchable.

**Alternatives considered**: widen Gate 47 to also scan `docs/*.md` and
`specs/*/*.md` as pointer sources — rejected: Gate 47's overlap-based
pointer-validation logic (part (b) of its docstring) is designed for
workflow-to-workflow and workflow-to-script prose; applying it repo-wide
would very likely surface unrelated false positives across every other
`-- see` and `(see ...)` phrase already living in `specs/**/*.md` and
`docs/**/*.md` files that have nothing to do with this feature, which is a
blast radius this plan's own scope (FR-021: touch nothing beyond this
feature's files) does not justify taking on. Rely on code review alone to
catch drift — rejected outright by FR-018's own text, which requires a
gate, and by this repository's own experience (spec's User Story 4
motivation: the classic-PAT claim already drifted into four places once
without one).

## D8. Ownership transfer and its fallout are a maintainer runbook, not new code (FR-002, Edge Case "Ownership move fallout")

**Decision**: no workflow code performs or verifies the repository
transfer, the wing-commander App reinstallation, the Claude credential
re-secreting, the container-image variable re-pointing, or the
`spec-request` label re-application that follow it. These are stated as an
ordered maintainer prerequisite in `quickstart.md`, and a partially-moved
fixture is caught by checks this repository already has for each piece
individually — `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` pointing at a
now-stale `OWNER/NAME` surfaces as the existing "test repository
reachability" `fail-infra` branch (`auto-release.yml`'s "Confirm the test
repository is reachable" step, unchanged), and a missing App installation
surfaces as the existing "wing-commander App installation" `fail-infra`
branch — rather than by a new, feature-specific check duplicating logic
that already fires correctly for exactly this failure mode.

**Rationale**: this mirrors specs/055 D3's own precedent (FR-013's
self-repository refusal needed no new code because the job's existing
sequencing already achieved it) applied to a different kind of
already-covered ground: every piece of "ownership move fallout" the spec's
Edge Cases list is, individually, a configuration state this job already
detects and names, because each of those five things (`OWNER/NAME`, App
install, Claude secret, container variable, label) is already a documented
prerequisite for *any* onboarded test repository (docs/adoption.md's
onboarding checklist), transfer or not. Writing a second, transfer-specific
check would duplicate a comparison that can only ever produce an answer
the existing per-piece checks already produce, which is exactly the
pasted-copy shape CLAUDE.md's "shared logic has exactly one home" section
warns against.

**Alternatives considered**: a single new precheck step that verifies all
five pieces moved together atomically before the job proceeds — rejected
as redundant per the above, and because it would need its own definition
of "moved together," which the existing per-piece checks already supply
compositionally (each one fails on its own the moment its own piece is
missing, which is sufficient — the job never needs all five to have moved
in lockstep, only for each to be correct by the time its own step runs).
