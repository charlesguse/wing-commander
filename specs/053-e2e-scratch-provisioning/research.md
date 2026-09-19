# Phase 0 Research: On-demand E2E scratch repository provisioning

`spec.md` closed every `[NEEDS CLARIFICATION]` marker before this stage
(see `checklists/requirements.md`), so this phase resolves *design*
unknowns — how to build what the spec already decided — not spec ambiguity.
Three edge cases the spec poses without an FR answering them are resolved
here as informed defaults, called out as "Decisions made without
clarification" in the issue comment.

## D1. Script language: bash, not Python

**Decision**: The provisioning entry point and the shared onboarding
library are bash; the new single-home gate is Python.

**Rationale**: `.github/scripts/` already splits cleanly by purpose, not by
preference — static tree-scanning gates (`verify-*.py`) are Python;
anything that makes live `gh`/GitHub API calls (`verify-watchdog-run.sh`,
`verify-cost-report-collector.sh`, every inline step in `auto-release.yml`
and `auto-update-spec-kit.yml`'s `e2e-stage`) is bash using the `gh` CLI
directly. Provisioning is entirely live calls — `gh repo create`,
`gh secret set`, `gh label create`, `gh variable set`, `gh api` for App
installation coverage — so bash matches every existing precedent in this
repository for that kind of work. Only the new SC-007 static-scan gate
(detecting a second copy of the onboarding-element list) matches the
Python `verify-*.py` shape, so it alone is Python.

**Alternatives considered**: A Python CLI using PyGithub or raw REST —
rejected because no script in this repository does that; it would be a new,
unprecedented dependency for no benefit over `gh`, which every reviewer and
every other script already reads fluently.

## D2. One shared library, two callers, not two copies

**Decision**: `.github/scripts/e2e-provisioning/checks.sh` defines one
function per onboarding element (repo exists and reachable, App installation
covers it, Claude credential present, `spec-request` label present, wrapper
set installed, wrapper set pinned to the intended image) plus a `profiles.sh`
data file mapping each `TargetProfile` to the subset of elements it
requires. `provision-e2e-target.sh` (local, privileged) and the generalized
`auto-update-spec-kit-scratch-preflight.yml` (CI, read-only) both source
`checks.sh` and call the same functions.

**Rationale**: FR-008 requires the readiness verdict to be computed by
deterministic code so an agent-driven session and a maintainer invocation
agree; FR-010 requires exactly one home for the onboarding-element logic;
CLAUDE.md's "shared logic has exactly one home" names the mechanism (a
composite action or, for pure shell, a shared script) and the cost of
skipping it (a pasted copy is invisible until the first divergent fix — the
per-run cost line example). The repository already has three independent,
slightly-different copies of "split owner/name, mint a scoped token, check
reachability" (`auto-release.yml`'s `reachable` step, `e2e-stage`'s
`scratch-repo` step, and `auto-update-spec-kit-scratch-preflight.yml`
itself) — this feature must not add a fourth. Consolidating those three
existing copies is explicitly **not** undertaken here: FR-011 keeps
`auto-release.yml`'s and `e2e-stage`'s own reset/scaffold behaviour
unchanged, so their inline reachability steps are left as they are; only the
*new* onboarding-element checking logic this feature adds gets the single
home, and the readiness-check workflow is generalized to use it because
User Story 2 explicitly names extending that one workflow as the intended
shape ("the repository already has this shape for one element... Extending
that to the full onboarding checklist is what makes the P1 output
trustworthy").

**Alternatives considered**: A brand-new `wing-commander-e2e-readiness.yml`
dispatcher left alongside the untouched preflight workflow — rejected
because it creates a second dispatch entry point for the same job
("is this target ready?") the moment the old one is not deleted, which is
exactly the kind of drift-prone duplication CLAUDE.md's rule targets, and
because User Story 2's own wording calls for extending the existing one in
place, not adding a sibling.

## D3. Distinguishing "our scratch target" from "a repository that merely shares the name"

**Decision**: On first successful provisioning of a target, the script sets
the target repository's description to a fixed, recognizable marker string
(e.g. `Wing Commander E2E scratch target — provisioned by
provision-e2e-target.sh, do not use for real work`). Every subsequent
invocation — including the readiness check — treats an *existing* repository
as a convergence candidate only if it either carries that marker already or
is empty (zero commits, no description set by anything else); any other
pre-existing, non-empty, unmarked repository is refused with FR-007's
"cannot establish as a reusable scratch verification target" message,
naming what was found instead of proceeding.

**Rationale**: This is the edge case the spec poses without an FR: "what
distinguishes an existing scratch target from a repository that merely
shares the name?" A description marker is readable by the same `gh repo
view` call every check already makes (no new API surface), is not
mistakable for adopter content (adopters do not run this script against
their production repositories), and is itself an onboarding element the
checks can verify deterministically (FR-008) rather than relying on
heuristics like "no open issues" that a legitimately reused target
(User Story 3) would routinely fail.

**Alternatives considered**: Refusing only on exact self-repository match
(today's `auto-release.yml` behaviour) — rejected as insufficient per the
spec's own edge case, since it does nothing to protect a maintainer's other,
unrelated repository that happens to share a chosen scratch name. A repo
topic instead of a description — rejected only because `gh repo edit
--add-topic` and `gh repo view --json description` are one field simpler
than the topics array for a single marker value.

## D4. Private-registry credentials for the pinned container image (edge case, out of scope)

**Decision**: Provisioning propagates the pinned image *reference* (FR-017)
by writing the target's `WING_COMMANDER_CONTAINER_IMAGE` repository
variable to match this repository's own pinned value (read once, per the
Assumptions section, from this repository's own `vars.WING_COMMANDER_CONTAINER_IMAGE`
so the two cannot drift into a second literal). It does **not** provision or
verify any registry pull credential (`WING_COMMANDER_CONTAINER_REGISTRY_USERNAME`/
`_PASSWORD`) for that image. If the pinned image lives in a private
registry, that surfaces later, at dispatch time, as a pull failure inside
the target's own `verify-image-prerequisites` job — the same failure mode
that already exists today for any adopter who mis-configures those secrets
— not as a provisioning-time readiness element.

**Rationale**: FR-002's enumerated element list is closed ("the repository
itself, the App installation, a Claude credential, the `spec-request`
label, and (for auto-release) the wrapper workflow set and the pinned
container image") and does not name registry credentials; FR-017 itself
only requires the *image reference* to be an onboarding element, not the
credentials needed to pull it. Treating registry credentials as a seventh
element would silently exceed FR-002's scope for a case the clarification
session did not raise (it appears only in the Edge Cases list, unanswered).
This is recorded as a decision made without clarification rather than
folded into FR-017 without a documented reason.

**Alternatives considered**: Adding a `registry-credentials-present` element
gated on the image reference containing a non-default registry host —
rejected as scope creep past FR-002's closed list; can be proposed as a
follow-up issue if it proves necessary in practice.

## D5. Claude credential value comes from the maintainer's local environment, not a prompt

**Decision**: `provision-e2e-target.sh` reads the Claude credential value to
write to the target's secret store from the invoking shell's own
environment — `CLAUDE_CODE_OAUTH_TOKEN` first, then `ANTHROPIC_API_KEY`,
matching the two names `docs/setup.md` already documents — and writes
whichever is present via `gh secret set <NAME> --repo <target>`. If neither
is set, that element is reported not-ready with instructions to export one
and re-run; this is never treated as the FR-015 "declared manual step" (that
term is reserved for the App installation, which is the only step requiring
the GitHub UI).

**Rationale**: FR-013 forbids prompting for *the (provisioning) credential*
and forbids blocking on the declared manual step; it says nothing about
disallowing an environment-variable precondition for a secondary secret,
and an environment variable does not require interactive input or the
GitHub UI, so it introduces no second manual step under FR-015's meaning.

**Alternatives considered**: An interactive prompt — rejected outright by
FR-013. A required CLI flag carrying the secret value in plaintext —
rejected because a command-line argument is visible in shell history and
process listings, which is a weaker posture than an environment variable
for the same value.

## D6. Wrapper workflow set source stays this repository's own checkout

**Decision**: Provisioning copies the same eight
`wing-commander-{1-intake,2-clarify,3-plan,4-tasks,5-implement,6-finalize,7-cleanup,rebase}.yml`
files from this repository's own working tree (the checkout the script runs
against, at the commit the maintainer has checked out) — the same files
`auto-release.yml`'s `scaffold` step already copies from `e2e-source` — doing
the same `uses: ./.github/workflows/<stage>.yml` → pinned cross-repo
rewrite and the two `main`-literal patches, then commits and pushes them to
the target's default branch.

**Rationale**: `auto-release.yml`'s own comment states the rationale this
feature must inherit unchanged: "Copying this repository's own wrapper
files is the single home for that content — there is no second copy to
drift from `docs/adoption.md`." Provisioning must not introduce a bundled
template or a fetched-from-elsewhere copy that could drift from both that
comment's guarantee and `docs/adoption.md`'s copy-pasted blocks.

**Alternatives considered**: Fetching the released tag's wrapper set from
GitHub instead of the local checkout — rejected because a maintainer
provisioning a target to test an *unreleased* change to a wrapper needs the
local, uncommitted-to-`main` version, exactly as `auto-release.yml` needs the
commit under verification rather than the last release.

## Summary of open items for Phase 1

- Data model: `TargetProfile`, `OnboardingElement`, `ReadinessReport`,
  `DeclaredManualStep`, plus the new marker concept from D3.
- Contracts: the CLI's flags/exit codes/report shape, the JSON readiness
  report schema, and the generalized readiness-check workflow's
  `workflow_dispatch` inputs/outputs.
- Quickstart: a runnable walkthrough matching User Story 1's acceptance
  scenarios 1, 3, 4, 5.
