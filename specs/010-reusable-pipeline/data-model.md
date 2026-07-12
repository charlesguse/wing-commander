# Data Model: Reusable Pipeline Extraction

No databases are involved; the "data model" is the set of durable contracts
between publisher, published stages, and consuming repositories.

## Entity: Published stage

One reusable workflow file, `.github/workflows/reusable-<stage>.yml`, in the
publishing repository.

| Field | Description | Constraints |
|---|---|---|
| `id` | Stage name: `intake`, `clarify`, `plan`, `tasks`, `implement`, `finalize`, `cleanup`, `rebase` | Fixed set; filename `reusable-<id>.yml` |
| `ref` | The version the consumer resolved: exact tag, floating major tag, branch, or local path (publisher only) | Consumer-chosen; see Release |
| `inputs` | Declared `workflow_call` inputs — event facts + configuration, all typed, config inputs defaulted | Authoritative interface; stages never read `github.event` (research D2) |
| `secrets` | Declared secrets: credentials (see Adopter credentials) | Optional individually; preflight enforces the credential invariant |
| `outputs` | Declared `workflow_call` outputs where a successor needs a value | Minimal; most effects are side effects in the consumer repo |
| `side effects` | Branches, commits, PRs, labels, comments — always in the **consuming** repository | Never touches publisher content (FR-005) |
| `preconditions` | Spec-kit presence + stage-specific predecessor artifacts | Checked deterministically before any agent step (research D7) |

**Validation rules**: `on:` contains only `workflow_call`. No `vars.*` reads.
No `github.event` reads. Every agent step declares `--model` and `--max-turns`
(constitution II) sourced from inputs/defaults. Every agent step is preceded by
the preflight and followed by the metrics summary step.

**State transitions**: none — stages are stateless executors. Lifecycle state
lives in `spec-meta.json` (below), which stages read/advance exactly as today.

## Entity: Consumer wrapper

A workflow in the adopting repository (this repository included) that calls a
published stage.

| Field | Description | Constraints |
|---|---|---|
| `trigger` | `on:` events, entirely adopter-chosen | Never dictated by the stage (FR-002) |
| `gates` | `if:` conditions — labels, actor checks, branch guards | Adopter-owned; security guidance documented (constitution V obligation) |
| `extraction` | Event→input wiring (`github.event.*` expressions, `vars.*` → inputs) | Expressions only — zero stage logic (SC-003) |
| `stage ref` | `uses:` line naming stage + version | Publisher's own wrappers use local path (research D6) |
| `secrets wiring` | Maps repo secrets to stage secret names | Adopter supplies all credentials |

## Entity: Adopter credentials

| Credential | Secret name (stage interface) | Required | Notes |
|---|---|---|---|
| Claude OAuth token | `claude-code-oauth-token` | one-of | From `claude setup-token` (subscription plans) |
| Claude API key | `anthropic-api-key` | one-of | From Claude Console (metered) |
| GitHub App ID | `speckit-app-id` | yes (stages that push/comment) | Adopter's own App (setup doc) |
| GitHub App private key | `speckit-app-private-key` | yes (same stages) | Adopter's own App |

**Invariant** (FR-003/FR-004): at least one Claude credential non-empty, else
deterministic preflight failure naming both secret names before any agent work.
When both set: API key wins (Claude Code documented precedence — spec
clarification 2026-07-11).

## Entity: Release

| Field | Description | Constraints |
|---|---|---|
| `exact tag` | `vX.Y.Z` on the publishing repo | Immutable once published |
| `floating major tag` | `v1` (then `v2`, …) | Force-moved only for non-breaking releases within the major |
| `notes` | Release notes | MUST contain an explicit Breaking-changes section (empty allowed) (FR-008) |

**State transitions**: draft → tagged (`vX.Y.Z` created) → major-tag advanced
(non-breaking only). Breaking change ⇒ new major tag; previous major tag never
moves to a breaking commit.

## Entity: Consumer spec-kit artifacts (existing contract, unchanged)

The adopting repository's own `specify init` output and specs:
`.specify/` (memory/constitution.md, templates, scripts),
`.claude/skills/speckit-*`, `specs/NNN-slug/` with `spec.md`, `plan.md`,
`tasks.md`, `checklists/`, and `spec-meta.json`
(`{issue, spec_dir, feature_num, stage, iteration, spec_branch}` — the
machine-readable lifecycle source of truth). This layout is the shared contract
extraction does **not** change (spec assumption 5); stages resolve all of it
relative to the consumer checkout (constitution VI).

## Relationships

```
Publisher repo ──publishes──▶ Published stage ──versioned by──▶ Release
Consumer wrapper ──uses @ref──▶ Published stage
Consumer wrapper ──supplies──▶ Adopter credentials ──consumed by──▶ Published stage
Published stage ──reads/writes──▶ Consumer spec-kit artifacts (consumer checkout only)
Published stage ──self-checkout @job_workflow_sha──▶ shared composite actions (research D3)
Publisher repo ──is also a──▶ Consumer (wrappers via local path)   [dogfooding, US3]
```
