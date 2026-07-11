# Contract: Versioning & Releases

Governs how published stages reach adopters (FR-008, SC-004; spec
clarification session 2026-07-11).

## Tags

| Ref | Mutability | Meaning |
|---|---|---|
| `vX.Y.Z` | Immutable once published | Exact release; adopters pinning it change only by editing their pin |
| `vX` (floating major) | Created at the first release of major X, then force-moved on every **non-breaking** release within major X | Adopters tracking it receive fixes automatically, zero changes on their side |
| `main` | Moving | Unreleased head — publisher dogfooding and early adopters at their own risk |

Rules:
- A breaking change to any published stage interface (removing/renaming an
  input, secret, or output; changing a default in a behavior-altering way;
  changing a stage's preconditions incompatibly) ships **only** behind a new
  major tag. The previous floating major tag never advances onto it.
- Additive changes (new optional inputs, new stages) are minor; fixes are patch.
  Both advance the floating major tag.
- Release notes MUST contain an explicit **Breaking changes** section (may
  state "none") so breakage is identifiable *before* upgrading (FR-008,
  edge case 2).

## Release automation (`release.yml`)

Manually triggered (`workflow_dispatch`: `version`, `breaking: bool`) —
tag creation is deliberate, not per-merge:

1. Lint gate: `actionlint` over all `reusable-*.yml` must pass.
2. Create annotated tag `vX.Y.Z` at `main`.
3. Create-or-advance the floating tag for the release's **own** major:
   force-move `vX` for a non-breaking release; create it when the release
   starts a new major (including the very first release — `v1.0.0` creates
   `v1`). If `breaking`: require the version to start a new major; the
   previous major's floating tag is never touched.
4. Create the GitHub Release with generated notes + the Breaking-changes
   section from the dispatch input / PR labels.

## What a version pins

An adopter's `uses: <owner>/speckit-action/.github/workflows/reusable-<stage>.yml@<ref>`
pins the *entire* stage behavior at that ref: workflow body **and** the shared
composite actions, because stages check out their own repository at the
running workflow's exact commit (`github.job_workflow_sha`, with an
OIDC-claim fallback where that context is empty — research D3 validation
note). There is no path by which a pinned adopter receives newer internal
logic; if the commit cannot be determined, the stage fails rather than
guessing a branch.

## Publisher self-reference (dogfooding)

This repository's wrappers call stages by **local path**
(`uses: ./.github/workflows/reusable-<stage>.yml`) — the same `workflow_call`
interface adopters use, resolved at the running commit. Consequences:

- Every dogfooded lifecycle run exercises unreleased head (edge case 5), so
  interface breakage is discovered here before any tag moves (US3, SC-003).
- `github.job_workflow_sha` resolves to the same commit for local calls, so the
  composite-resolution path is identical to the adopter path.
- The transition period in which this repo references unreleased versions is
  permanent by design and documented (spec assumption 7).
