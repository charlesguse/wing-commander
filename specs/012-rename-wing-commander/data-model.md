# Phase 1 Data Model: Rename to Wing Commander

This feature has no application data/storage; "entities" here are the naming
surfaces the spec's Key Entities section defines, made concrete with every
site the research catalog found. This table is the authoritative rename
inventory `tasks.md` will enumerate into individual tasks.

## Entity: Product name (display text)

Human-facing text naming the product itself. Target value: **"Wing
Commander"** everywhere in this category.

| File | Current | New |
|---|---|---|
| `README.md` (title + body prose) | `speckit-action` | `Wing Commander` |
| `.specify/memory/constitution.md` (title) | `Speckit GitHub Action Constitution` | `Wing Commander Constitution` |
| `.specify/memory/constitution.md` (Principle VI prose) | "...never bundled with or resolved from speckit-action..." | "...Wing Commander..." |
| `docs/adoption.md` (title) | `Adopting the speckit pipeline` | `Adopting the Wing Commander pipeline` |
| `docs/setup.md` (intro prose) | `speckit pipeline` | `Wing Commander pipeline` |

**Validation rule** (FR-001, FR-002, SC-001, SC-002): zero remaining
occurrences of "speckit"/"Speckit"/"speckit-action" as the product's own
name in any of the above files after the change; a reader determines the
product name within 10 seconds of opening `README.md`.

**Explicitly excluded** (research.md "historical spec artifacts" decision):
`specs/001-spec-intake/` … `specs/011-security-policy/` — untouched.

## Entity: Internal identifier (machine-referenced, exact-value)

Names other files, workflow steps, or the runtime resolve by exact string
match. Grouped by rename pattern (research.md decisions).

### Reusable stage filenames — drop `reusable-` prefix (FR-009a)

| Old | New |
|---|---|
| `.github/workflows/reusable-intake.yml` | `.github/workflows/intake.yml` |
| `.github/workflows/reusable-clarify.yml` | `.github/workflows/clarify.yml` |
| `.github/workflows/reusable-plan.yml` | `.github/workflows/plan.yml` |
| `.github/workflows/reusable-tasks.yml` | `.github/workflows/tasks.yml` |
| `.github/workflows/reusable-implement.yml` | `.github/workflows/implement.yml` |
| `.github/workflows/reusable-finalize.yml` | `.github/workflows/finalize.yml` |
| `.github/workflows/reusable-cleanup.yml` | `.github/workflows/cleanup.yml` |
| `.github/workflows/reusable-rebase.yml` | `.github/workflows/rebase.yml` |

Cross-reference sites that must update in the same change: each of the 8
wrapper `uses: ./.github/workflows/reusable-<stage>.yml` lines; `README.md`'s
stage table and repository-map; `docs/adoption.md`'s ~10 copy-paste `uses:`
snippets; `docs/architecture.md`'s per-stage section headers; `release.yml`'s
actionlint invocation and `.github/workflows/reusable-*.yml` glob (×2, lines
62 and the invariant-check `grep`/`for f in` loops); each stage's own
self-referential "produced by the X stage (reusable-X.yml)" error strings.

### Wrapper stage filenames — `speckit-` → `wing-commander-` prefix

| Old | New |
|---|---|
| `.github/workflows/speckit-1-intake.yml` | `.github/workflows/wing-commander-1-intake.yml` |
| `.github/workflows/speckit-2-clarify.yml` | `.github/workflows/wing-commander-2-clarify.yml` |
| `.github/workflows/speckit-3-plan.yml` | `.github/workflows/wing-commander-3-plan.yml` |
| `.github/workflows/speckit-4-tasks.yml` | `.github/workflows/wing-commander-4-tasks.yml` |
| `.github/workflows/speckit-5-implement.yml` | `.github/workflows/wing-commander-5-implement.yml` |
| `.github/workflows/speckit-6-finalize.yml` | `.github/workflows/wing-commander-6-finalize.yml` |
| `.github/workflows/speckit-7-cleanup.yml` | `.github/workflows/wing-commander-7-cleanup.yml` |
| `.github/workflows/speckit-rebase.yml` | `.github/workflows/wing-commander-rebase.yml` |

### Action directories — `speckit-` → `wing-commander-` prefix

| Old | New |
|---|---|
| `.github/actions/speckit-context/` | `.github/actions/wing-commander-context/` |
| `.github/actions/speckit-preflight/` | `.github/actions/wing-commander-preflight/` |
| `.github/actions/speckit-metrics-summary/` | `.github/actions/wing-commander-metrics-summary/` |

Cross-reference sites: every `uses: ./.wing-commander-pipeline/.github/
actions/speckit-*` line across the 8 reusable stages (also updates as part
of the `.speckit-pipeline` → `.wing-commander-pipeline` rename below);
`README.md` repository-map; `docs/architecture.md` prose; the 12 occurrences
of the literal step name `"Speckit context"` → `"Wing Commander context"`.

### Runtime-only identifiers — renamed for FR-005/FR-008 consistency

| Old | New | Where |
|---|---|---|
| `.speckit-pipeline` (self-checkout `path:`) | `.wing-commander-pipeline` | all 8 reusable stages' checkout step + every `uses: ./.speckit-pipeline/...` reference + `docs/architecture.md` |
| `speckit-<stage>` concurrency group prefix | `wing-commander-<stage>` | `reusable-intake.yml`, `-plan.yml`, `-tasks.yml`, `-finalize.yml`, `-implement.yml`, `-cleanup.yml`, `-rebase.yml`, `release.yml`; documented in `docs/adoption.md` |
| `speckit-pipeline-ref` (OIDC audience) | `wing-commander-pipeline-ref` | all 8 reusable stages |
| `<!-- speckit-rebase: blocked ... -->` marker | `<!-- wing-commander-rebase: blocked ... -->` | `reusable-rebase.yml` (writer and reader, same file) |

### Vendored Spec Kit artifacts — exempt, no rename (FR-003, FR-009)

| Path | Why exempt |
|---|---|
| `.claude/skills/speckit-*/SKILL.md` (10 files) | Spec Kit's own command interface; `metadata.author: "github-spec-kit"` |
| `.specify/scripts/bash/*.sh`, `.specify/templates/*.md` | Reference `/speckit-*` commands as Spec Kit's own convention |
| `.specify/workflows/speckit/workflow.yml`, `workflow-registry.json` | `source: "bundled"`, `author: "GitHub"` |
| `.specify/integrations/speckit.manifest.json`, `.specify/init-options.json` | `specify init`-written installation record |

**Validation rule** (FR-005, FR-006, FR-008, FR-009, SC-003, SC-004): after
the rename, every `uses:`/`path:`/filename cross-reference resolves (a
pipeline dry-run on a sample issue completes with zero failures caused by a
mismatched name); a repository-wide search for each old identifier's exact
string returns zero hits outside the exempt list and the excluded historical
`specs/001-011` directories.

## Entity: Attribution reference

Mentions of Spec Kit or Claude Code framed as an underlying dependency.
**Not modified.** Representative examples confirmed correctly framed today
and left as-is: `README.md`'s "powered by GitHub spec-kit and Claude Code";
`docs/adoption.md`'s "Your own spec-kit artifacts. Run `specify init`...";
`.specify/memory/constitution.md`'s "Spec-kit is pinned (currently
v0.12.4)..."; `docs/setup.md`'s "The pipeline pins spec-kit v0.12.4...".

**Validation rule** (FR-003, FR-004): these strings are byte-identical
before and after the change — the rename's diff must not touch them.

## Entity: Downstream consumer

An external repository pinning this project's reusable workflows or
`pipeline-repo` default by name/ref.

**Breaking-change surface** (FR-007, FR-010) — ships behind a new major
`v2` tag per `specs/010-reusable-pipeline/contracts/versioning.md`; `v1`
stays immutable and unaffected:

| Old interface name | New interface name (v2 only) |
|---|---|
| `SPECKIT_APP_ID` | `WING_COMMANDER_APP_ID` |
| `SPECKIT_APP_PRIVATE_KEY` | `WING_COMMANDER_APP_PRIVATE_KEY` |
| `SPECKIT_TASKS_REVIEW` | `WING_COMMANDER_TASKS_REVIEW` |
| `SPECKIT_IMPLEMENT_MODEL` | `WING_COMMANDER_IMPLEMENT_MODEL` |
| `SPECKIT_MAX_ITERATIONS` | `WING_COMMANDER_MAX_ITERATIONS` |
| `uses: charlesguse/speckit-action/.github/workflows/reusable-<stage>.yml@v1` | `uses: charlesguse/wing-commander/.github/workflows/<stage>.yml@v2` |

**Redirect-backed, non-breaking today**: `charlesguse/speckit-action` paths
already resolve via GitHub's rename redirect (repo renamed to
`charlesguse/wing-commander` at the platform level, confirmed via `git
remote -v`) — no adopter action is required to keep `@v1` pins working, but
migration guidance still tells them to repoint since a redirect is not a
permanent guarantee (see contracts/rename-migration.md).

**Non-breaking, docs-only**: `speckit-bot` suggested GitHub App name →
`wing-commander-bot` — new adopters only; existing Apps are keyed by App ID,
not display name, and need no change.

**Validation rule** (FR-007, SC-005): zero undocumented breaking changes —
every row in the first table above appears in the `v2` release's mandatory
Breaking-changes notes and in `docs/adoption.md`'s migration section.
