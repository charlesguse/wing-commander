# Phase 0 Research: Rename to Wing Commander

The feature spec contains no `[NEEDS CLARIFICATION]` markers — the Assumptions
section already resolves the questions a reviewer would otherwise raise (target
name, slug, `.speckit-pipeline/` scoping, vendored-command exemption). This
document records those resolutions plus the additional technical decisions
needed to scope an exhaustive, dangling-reference-free rename across ~40
tracked files, in the standard research format.

A repo-wide catalog of every `speckit`/`Speckit`/`speckit-action` occurrence
(outside `.speckit-pipeline/`, `.git/`, and this feature's own spec artifacts)
was built by reading every matching file; its findings are summarized as
decisions below and structured in `data-model.md`.

## Decision: Target names

- **Decision**: Display name `Wing Commander`; slug `wing-commander`
  (already the repository directory/name — `git remote -v` confirms the
  GitHub repository has already been renamed to `charlesguse/wing-commander`
  at the platform level, ahead of this in-repo text catch-up).
- **Rationale**: Directly from spec Assumptions.
- **Alternatives considered**: None — fixed by the spec.

## Decision: Historical spec artifacts (specs/001–011) are out of scope

- **Decision**: `specs/001-spec-intake/` through `specs/011-security-policy/`
  (every already-shipped feature's `spec.md`, `plan.md`, `research.md`,
  `data-model.md`, `contracts/`, `quickstart.md`, `tasks.md`) are **not**
  rewritten. They keep their "speckit"/"Speckit GitHub Action" references
  as-written.
- **Rationale**: These are point-in-time engineering records of decisions
  already implemented and merged, not current product-identity surfaces a
  new visitor reads to learn the product's name (spec User Story 1's
  "README," "PR titles/status comments," and "documentation" language
  targets forward-facing surfaces). Rewriting merged historical planning
  docs to retroactively use a name that didn't exist when those decisions
  were made would misrepresent the record, is unbounded busywork
  disproportionate to a branding change, and contradicts the Assumption that
  "no functional behavior of the pipeline changes." `docs/*.md`,
  `README.md`, `.specify/memory/constitution.md`, and the workflow/action
  YAML are the live, currently-read surfaces and remain fully in scope.
- **Alternatives considered**: Rewrite all historical spec docs for
  consistency — rejected as scope creep with no user-facing benefit and a
  real risk of silently corrupting historical rationale (e.g., `research.md`
  decisions that quote literal old filenames/strings that existed at the
  time).

## Decision: Reusable workflow filenames drop the `reusable-` prefix entirely (FR-009a)

- **Decision**: `reusable-intake.yml` → `intake.yml`, `reusable-clarify.yml`
  → `clarify.yml`, `reusable-plan.yml` → `plan.yml`, `reusable-tasks.yml` →
  `tasks.yml`, `reusable-implement.yml` → `implement.yml`,
  `reusable-finalize.yml` → `finalize.yml`, `reusable-cleanup.yml` →
  `cleanup.yml`, `reusable-rebase.yml` → `rebase.yml`. No product-name prefix
  is added back — FR-009a is explicit that dropping `reusable-` is not
  "replace its speckit portion," and these filenames never contained
  "speckit" in the first place (their `speckit-N-*.yml` *wrappers* are the
  ones carrying brand text — handled separately below).
- **Rationale**: FR-009a is unambiguous. Every cross-reference site the
  catalog found (all 8 wrapper `uses:` lines, `README.md`'s stage table,
  `docs/adoption.md`'s 10 copy-paste `uses:` snippets, `docs/architecture.md`'s
  per-stage headers, `release.yml`'s actionlint/grep glob `reusable-*.yml`,
  and each file's own self-referential "produced by the X stage
  (reusable-X.yml)" error strings) moves in lockstep as part of the same
  atomic change — task generation will enumerate each site individually.
- **Alternatives considered**: Keep `reusable-` and only swap in
  product branding elsewhere — rejected; FR-009a explicitly overrides this.

## Decision: Wrapper workflow filenames take the `wing-commander-` prefix

- **Decision**: `speckit-1-intake.yml` → `wing-commander-1-intake.yml`
  … `speckit-7-cleanup.yml` → `wing-commander-7-cleanup.yml`,
  `speckit-rebase.yml` → `wing-commander-rebase.yml`.
- **Rationale**: These are this product's own numbered lifecycle-stage
  entry points (dogfooded locally via `uses: ./.github/workflows/reusable-
  <stage>.yml`, per `contracts/versioning.md` from spec 010) — exactly the
  "wrapper workflow filenames" FR-009 calls out for rename. Keeping a
  product-identifying prefix (vs. dropping it like the reusable stages)
  preserves the numbered-lifecycle readability the current names have in
  the Actions UI and `README.md`'s stage table.
- **Alternatives considered**: Drop the prefix here too (`1-intake.yml`) —
  rejected; unlike the published `reusable-*.yml` stages (an external
  interface where FR-009a applies literally), these wrapper files are purely
  this repository's own entry points, so there is no requirement forcing
  prefix removal, and keeping a namespaced prefix avoids collision with
  generic top-level workflow filenames like `release.yml`.

## Decision: Action directories take the `wing-commander-` prefix

- **Decision**: `.github/actions/speckit-context/` →
  `.github/actions/wing-commander-context/`, `speckit-preflight/` →
  `wing-commander-preflight/`, `speckit-metrics-summary/` →
  `wing-commander-metrics-summary/`. The literal Actions step name
  `"Speckit context"` (12 occurrences across the reusable stages) becomes
  `"Wing Commander context"`.
- **Rationale**: FR-009 explicitly lists "action directories." Every
  `uses: ./.speckit-pipeline/.github/actions/speckit-*` reference across the
  8 reusable stages, plus the `README.md` repository-map lines and
  `docs/architecture.md` prose naming these directories, are cross-reference
  sites that move together.
- **Alternatives considered**: None — directly required by FR-009.

## Decision: Internal runtime identifiers rename for full consistency, decoupled from the untracked `.speckit-pipeline/` scratch directory

- **Decision**: The literal *string* `.speckit-pipeline` used as the
  self-checkout `path:` value inside every `reusable-*.yml`/`wing-commander-
  *.yml` file (and its cross-references in `speckit-context`'s header
  comment and `docs/architecture.md`) is renamed to `.wing-commander-
  pipeline`. Likewise the concurrency-group prefix (`speckit-intake`,
  `speckit-plan-...`, `speckit-release`, etc. → `wing-commander-intake`,
  `wing-commander-plan-...`, `wing-commander-release`), the OIDC audience
  string `speckit-pipeline-ref` → `wing-commander-pipeline-ref`, and the
  rebase escalation marker `<!-- speckit-rebase: blocked ... -->` →
  `<!-- wing-commander-rebase: blocked ... -->` (parsed only by this
  repo's own `rebase.yml`, so both the writer and reader change together in
  the same commit).
- **Rationale**: These are all "internal identifiers" per FR-009's
  definition in Key Entities ("machine-referenced name... that other parts
  of the system... resolve by exact value") and none of them fall under the
  spec's vendored-Spec-Kit exemption (FR-003/FR-009). Leaving a stray
  `speckit-` prefix on some but not others would violate FR-005's "every
  reference to a name that is changed MUST be updated everywhere" and
  FR-008's "renamed vs. intentionally unchanged must be unambiguous," even
  though these particular identifiers are invisible in the product's
  human-facing surfaces (they only ever appear in Actions-run logs and one
  parsed HTML comment).
- **Important scope note**: This decision is about the *string* that appears
  in tracked YAML/docs. It is unrelated to the spec Assumption that the
  currently-present *untracked* `.speckit-pipeline/` directory in a given
  checkout is out of scope — that assumption exists so this feature's own
  implementation doesn't try to edit or delete that harness-scratch
  artifact. Once the tracked `path:` value changes, any *future* checkout
  will simply materialize a directory named `.wing-commander-pipeline/`
  instead; no separate action is needed on the untracked directory itself.
- **Alternatives considered**: Leave these internal-only strings alone
  since they're invisible to end users — rejected; FR-005/FR-008 don't
  carve out an "invisible so it's fine" exception, and the actual
  implementation cost of updating them is a mechanical find/replace inside
  files already being touched for other reasons in the same stage.

## Decision: `.specify/workflows/speckit/` and `speckit.manifest.json` are vendored Spec Kit artifacts — exempt

- **Decision**: `.specify/workflows/speckit/workflow.yml`, `.specify/
  workflows/workflow-registry.json`'s `"speckit"` entry (`source: "bundled"`,
  `author: "GitHub"`), and `.specify/integrations/speckit.manifest.json`
  (Spec Kit's own `specify init`-written installation record, key
  `"integration": "speckit"`) are not renamed.
- **Rationale**: Same exemption class as the `/speckit-*` skill files under
  FR-003/FR-009 — these are shipped verbatim by the upstream Spec Kit tool
  (`specify init`), not authored by this product. Their content self-
  attributes to GitHub/Spec Kit (`author: "GitHub"`), and they are
  regenerated/re-verified whenever spec-kit is upgraded (constitution
  Operational Constraints: "Spec-kit is pinned... upgrades re-verify
  `.specify/scripts` behavior before adoption"). Renaming a vendor's own
  bundled filenames would break that upgrade path and misattribute
  authorship.
- **Alternatives considered**: Rename the `.specify/workflows/speckit/`
  folder despite vendored contents, since the bare word "speckit" as a
  folder name would otherwise be caught by a naive rename sweep — rejected;
  the folder name mirrors the vendor's own `id: "speckit"` workflow
  identifier inside the file it contains, so renaming just the folder while
  the content still self-identifies as `"speckit"` would create a
  mismatched, confusing reference rather than resolve one.

## Decision: `speckit-bot` GitHub App suggested name — docs-only, non-breaking

- **Decision**: `docs/setup.md`'s walkthrough instructs new adopters to name
  their GitHub App `wing-commander-bot` instead of `speckit-bot`; all cross-
  references (`README.md`, `docs/adoption.md`, `docs/architecture.md`
  section header, and the `Checkout ... as speckit-bot` step names across
  every reusable stage) are updated to match. No migration action is
  required or suggested for existing adopters' already-created Apps.
- **Rationale**: A GitHub App's identity for authentication purposes is its
  App ID / installation, not its display name — renaming the suggested name
  in documentation does not break any existing adopter's already-configured
  App (FR-007's backward-compatibility bar is trivially met: nothing
  changes for existing installs). This is purely a display-text update
  (FR-001/FR-002), not an internal identifier with a resolvable exact value.
- **Alternatives considered**: Also publish migration guidance telling
  existing adopters to rename their App — rejected as unnecessary; renaming
  is optional cosmetic housekeeping for the adopter, not something this
  rename requires or should imply is required.

## Decision: `SPECKIT_*` secrets/vars rename ships as a documented breaking major release (FR-007, FR-010)

- **Decision**: `SPECKIT_APP_ID` → `WING_COMMANDER_APP_ID`,
  `SPECKIT_APP_PRIVATE_KEY` → `WING_COMMANDER_APP_PRIVATE_KEY`,
  `SPECKIT_TASKS_REVIEW` → `WING_COMMANDER_TASKS_REVIEW`,
  `SPECKIT_IMPLEMENT_MODEL` → `WING_COMMANDER_IMPLEMENT_MODEL`,
  `SPECKIT_MAX_ITERATIONS` → `WING_COMMANDER_MAX_ITERATIONS`. This ships
  behind a new major floating tag (`v2`), per the existing release contract
  (`specs/010-reusable-pipeline/contracts/versioning.md`): the immutable
  `v1.x.x` tags and floating `v1` tag are never touched, so every adopter
  currently pinned to `@v1` (or an exact `v1.y.z`) keeps working with the
  old `SPECKIT_*` names unchanged. Adopters who choose to move to `@v2` (or
  a new `v2.0.0`) must rename their repository secrets/variables per a
  migration table published in the release's required Breaking-changes
  notes and in `docs/adoption.md`.
- **Rationale**: FR-009 requires renaming internal identifiers "consistently
  everywhere," and these are internal identifiers under the Key Entities
  definition, but they are also load-bearing external interface names an
  adopter's own wrapper YAML and repository settings reference by exact
  string — a silent rename would break every existing adopter's next run.
  FR-007/FR-010 both require that a consumer-breaking rename be either
  backward-compatible or explicitly documented as breaking with migration
  guidance; `release.yml`'s existing `breaking: true` / `breaking-notes`
  input and versioning contract already implement exactly this mechanism
  (immutable major tags, mandatory Breaking-changes release-notes section),
  so this decision reuses that mechanism rather than inventing a new one.
- **Alternatives considered**: (a) Leave the secret/var names unchanged
  since they're internal to adopters' configuration — rejected; it would
  leave "SPECKIT" branding permanently embedded in every adopter's repo
  settings, contradicting FR-002/SC-001's "no human-facing surface..." bar
  (repo secrets/variables lists are human-facing to the adopter's own
  maintainers). (b) Support both old and new names simultaneously (dual-read
  fallback) inside the reusable stages — rejected; the constitution's
  published-stage interface rules (`release.yml`'s invariant-check gate)
  forbid reading configuration outside declared `secrets:`/`inputs:`, and a
  silent dual-read would hide the rename instead of documenting it,
  violating FR-010's explicit-migration-guidance requirement.

## Decision: Outward-facing repo/action reference rename ships in the same `v2` release, documented as redirect-backed

- **Decision**: The hardcoded `pipeline-repo` input default in all 8
  reusable stages, the `release.yml` invariant-check grep pattern (currently
  `charlesguse/speckit-action`), the `git tag` annotation messages, and every
  `docs/adoption.md`/`docs/setup.md` copy-paste `uses: charlesguse/speckit-
  action/...@v1` example are updated to `charlesguse/wing-commander`. This
  ships in the same `v2` breaking release as the secret/var rename (both are
  part of one coordinated "adopters on `@v2` must update two things"
  migration note) rather than as a separate release.
- **Rationale**: FR-010 requires this rename and requires it be handled per
  FR-007 (backward-compatible or documented breaking change). `git remote
  -v` confirms GitHub has already renamed the repository at the platform
  level, and GitHub repository renames install an automatic redirect from
  the old `owner/old-name` path — so an adopter still pinned to
  `charlesguse/speckit-action/.github/workflows/intake.yml@v1` continues to
  resolve without action, making this specific change backward-compatible
  in practice today. However, GitHub's redirect is not a permanent
  guarantee (it can be reclaimed if a third party later creates a
  repository at the old path), so the migration guidance still tells
  adopters to repoint to `charlesguse/wing-commander` at their convenience
  rather than treating the redirect as a reason to skip documentation.
- **Alternatives considered**: Treat this as fully backward-compatible and
  skip migration notes entirely — rejected; SC-005 requires zero
  *undocumented* breaking changes, and relying silently on a redirect that
  could theoretically lapse is not the same as documenting the change.

## Decision: Labels require no rename

- **Decision**: No pipeline label (`spec-request`, `stage:*`, `model:opus`,
  `spec:<slug>`, `rebase:blocked`) is renamed.
- **Rationale**: The catalog confirmed none of the existing label strings
  contain "speckit"/"Speckit" branding — they are already product-name-
  neutral. FR-009 lists labels among the categories to check, not a
  guarantee that every category has work; this one has none.
- **Alternatives considered**: None needed.

## Decision: `SECURITY.md` and `lint-workflows.yml` require no change

- **Decision**: Both files were independently verified to contain zero
  "speckit"/owner-name references and need no edits.
- **Rationale**: `SECURITY.md` uses generic security-policy language;
  `lint-workflows.yml` lints via a generic `.github/workflows/*.yml` glob
  that keeps working under any filenames chosen above.
- **Alternatives considered**: None needed.

**Output**: All decisions above resolve every scoping question the spec
leaves implicit. No `[NEEDS CLARIFICATION]` markers remain. The full old→new
identifier mapping and per-surface status (rename / exempt / no-change) is
captured in `data-model.md`; the adopter-facing migration contract is captured
in `contracts/rename-migration.md`.
