# Phase 0 Research: Single home for the auto-release / auto-update shared idioms

Spec has no `[NEEDS CLARIFICATION]` markers. This document records the
design decisions a plan has to make that the spec leaves to implementation
judgment, each grounded in a fact gathered from the current tree (not
guessed), so a later stage can build against it without re-deriving the
same research.

## D1. Where the three shared definitions live

**Decision**: Three composite actions under `.github/actions/_shared/`:
`_shared/scoped-app-token/action.yml`, `_shared/orphan-branch-reset/action.yml`,
`_shared/durable-failure-issue/action.yml`.

**Rationale**: FR-022 requires composite shape in an underscore-prefixed
internal location, extending the existing `_shared/` convention (today it
holds one plain script, `.github/actions/_shared/count-turns.sh`) from
scripts to composites. Two composites in this repo already wrap a `uses:`
step the way the token mint needs to: `wing-commander-context/action.yml`
(mints the shared-context App token via `actions/create-github-app-token@v3`)
and `wing-commander-chain-stop-notice/action.yml` (wraps
`actions/checkout@v5`). Neither is underscore-prefixed today because
neither was previously restricted to internal use; this feature is what
establishes that a composite *can* live under `_shared/` and still wrap a
`uses:` step, which a plain script cannot.

**Alternatives considered**: A single mega-composite exposing three
operations via an `operation:` input was rejected — FR-005 requires each
definition parameterised for exactly its own call sites' differences, and
the three idioms have disjoint parameter sets (token mint takes an
owner/name pair; orphan reset takes a repo + branch + bot identity; failure
issue takes a label + title/body + a report-or-close mode). Folding them
into one action.yml would force every caller to pass inputs the operation
it invokes doesn't use, which FR-005 explicitly forbids ("MUST NOT require
a caller to pass a parameter no call site varies").

## D2. Call-site path convention

**Decision**: `auto-update-spec-kit.yml` (a `workflow_call`-only published
stage) consumes each composite as
`uses: ./.wing-commander-pipeline/.github/actions/_shared/<name>`, the same
self-checkout-then-relative-path convention its other ~40 composite calls
already use (canonical snippet: `wing-commander-context/action.yml:1-23`).
`auto-release.yml` (a schedule/`workflow_dispatch` wrapper, i.e. the
"consuming instrument" of constitution VII, confirmed by its three
`actions/checkout@v5` steps checking out this repository directly, no
`repository:` override) consumes each composite as
`uses: ./.github/actions/_shared/<name>` — no self-checkout hop, because it
already runs inside this repository's own checkout.

**Rationale**: This is the existing, load-bearing distinction between the
published contract and the consuming instrument (constitution VII). Giving
`auto-release.yml` a self-checkout it doesn't need would add a step with no
purpose; giving `auto-update-spec-kit.yml` a bare `./.github/actions/...`
path would break for every adopter that pins the stage by tag, since that
path resolves against the *adopter's* workspace, not this repository's.

**Alternatives considered**: Making both composites resolve through
`.wing-commander-pipeline/` uniformly (i.e. adding a self-checkout to
auto-release.yml) was rejected as an unrequired behaviour change to a
workflow that already works, and the spec's "behaviour-preserving by
default" assumption disallows unforced changes.

## D3. Fail-infra verdict helper shape and location

**Decision**: A plain shell script, `.github/actions/_shared/auto-release-verdict.sh`,
not a composite action. Given `outcome`, `head`, `failing_check`,
`expected`, `observed`, `evidence_url` as positional/env arguments, it
prints the same JSON object today's `write_verdict` (poll step,
`auto-release.yml:497-506`) produces. Each of the 14 call sites keeps its
one-line `echo 'verdict<<AUTO_RELEASE_VERDICT_EOF' ... echo 'AUTO_RELEASE_VERDICT_EOF'`
`GITHUB_OUTPUT` framing (that framing is step-output plumbing, not part of
the verdict's shape) and replaces its inline `jq -n '{...}'` with
`bash "$GITHUB_ACTION_PATH_STATIC/.github/actions/_shared/auto-release-verdict.sh" ...`
— in practice `bash .github/actions/_shared/auto-release-verdict.sh ...`,
since `auto-release.yml` runs from a plain repository checkout with no
`GITHUB_ACTION_PATH` of its own (that variable only exists inside a running
action).

**Rationale**: FR-008 requires one helper covering all eleven current
construction sites (fourteen once the two idiom-adjacent sites inside
`reachable`/`reset` inherited from D1's composites are also counted — see
data-model.md). The helper needs no `uses:` step (it is pure `jq`), so a
composite action would add `action.yml` ceremony (checkout of nothing,
`runs.using: composite` wrapping one `run:` step) for no benefit over a
script invoked the same way `_shared/count-turns.sh` already is
(`bash "$path/to/script.sh" args`, output captured by the caller). This is
also *not* one of the three FR-022 "shared definitions" — it is internal to
one workflow, not cross-workflow — so it is not bound by FR-022's
composite-shape requirement; it follows the plain-script precedent instead.

**Alternatives considered**: A composite action wrapping the same `jq`
call was rejected for the ceremony reason above. Leaving `write_verdict`/
`emit_verdict` as step-scoped bash functions and re-declaring them at each
of the 14 sites was rejected — that is the status quo FR-008 exists to end
(a bash function defined in one step's `run:` block does not exist in the
next step's shell).

## D4. Durable-failure-issue: one composite, two operations

**Decision**: `_shared/durable-failure-issue/action.yml` takes an
`operation` input (`report` or `close`) alongside `label`, `label-color`,
`label-description`, `title` (report only), `body`/`body-file` (report
only), and `close-comment` (close only). Both operations share one
open-issue-by-label lookup step; `report` idempotently creates the label
then comments-if-found/creates-if-not; `close` looks up and closes if
found, no-ops if not.

**Rationale**: The spec's own Assumptions section states the definition
"covers close-on-success as well as create-or-comment, since both
workflows need both halves and splitting them would leave half the idiom
duplicated" — i.e. FR-003 wants one entity, not two composites that happen
to share a lookup. `auto-release.yml`'s three report sites and one close
site all resolve through this one action.yml. Of `auto-update-spec-kit.yml`'s
four `auto-update:failed` sites, only one — the rollback site, "File or
update the auto-update:failed issue (rollback)" — matches the composite's
report contract (lookup by label, comment-if-found, create-if-not) and
resolves through it; the other three do not implement that shape and are
deliberately left calling their own narrower logic — see D5.

**Alternatives considered**: Two composites (`_shared/durable-failure-issue-report`,
`_shared/durable-failure-issue-close`) were considered and rejected per the
Assumptions text above — it names splitting as the anti-goal, not just a
style preference.

## D5. Resolving the divergence: does the shared close-on-success apply to `auto-update-spec-kit.yml`?

**Decision**: No behaviour change, and only a partial resolution through
the shared composite. Of `auto-update-spec-kit.yml`'s four
`auto-update:failed` sites, only the rollback site ("File or update the
auto-update:failed issue (rollback)") resolves through
`_shared/durable-failure-issue` with `operation: report` — its shape
(lookup by label, comment-if-found, create-if-not) matches the composite's
report contract exactly. The other three do not implement that shape and
are deliberately left calling their own narrower logic, per FR-007's
no-regression rule:
- "Label the issue as failed" and "Label the issue as failed (prepare
  failed)" each label a specific, already-known issue via
  `gh issue edit --add-label`, with no lookup-by-label search — there is
  no "find or create" decision for the composite to make on their behalf.
- "Post closing summary (revert)" looks up by label (matching the
  composite's own lookup) but must never create an issue when none is
  open — the opposite of the report operation's create-if-not-found
  behaviour, and not what the `close` operation does either (`close`
  closes the found issue; this site instead posts a comment and leaves it
  open).

None of the four is changed to call `operation: close` — the composite's
`close` operation exists because `auto-release.yml` uses it, and is
available to any future caller, but FR-007 ("MUST NOT regress the
behaviour that has run in production") forbids retrofitting a close call
`auto-update-spec-kit.yml` never had.

**Rationale**: Current behaviour (confirmed by reading the workflow) is
deliberate: `auto-update:failed` is closed only by a human, because a
revert having happened is itself the durable signal the label exists to
preserve (`auto-update-spec-kit.yml:2970-2971`, in-repo comment: "This
issue stays open and flagged — a rollback is itself the failure this
feature wants visible"). Consolidating the *mechanism* must not average
away this deliberate difference in *policy*, and must not force a site
into the shared shape when its own logic is narrower by design.

**Alternatives considered**: none — the spec's Edge Cases section
("`auto-update-spec-kit.yml`'s copies are the proven ones... every
divergence between the pair has to be resolved deliberately and recorded,
not averaged") directly names this as the resolution rule, not a decision
with real alternatives.

## D6. `wing-commander-callout` stays separate

**Decision**: The durable-failure-issue composite does not fold in
`wing-commander-callout` (the existing comment-rendering composite used at
2 of `auto-update-spec-kit.yml`'s 4 sites). Sites that today call
`wing-commander-callout` for the human-facing summary comment keep doing
so, wired to also call the new composite for the label/lookup/create
machinery; the two sites that bypass `wing-commander-callout` today
(Site 1, Site 4) are unaffected by that choice — they still write their own
comment bodies, and only their label/lookup/create-or-comment/close
plumbing consolidates.

**Rationale**: The spec's Assumptions section is explicit: "The
`auto-update-spec-kit.yml` sites that already reuse `wing-commander-callout`
for the failure comment keep doing so; FR-003 covers the label/lookup/
create/close machinery, not the comment rendering."

## D7. Enforcement gate: structural scan, not comment-pointer scan

**Decision**: A new gate script, `.github/scripts/verify-single-home-idioms.py`
(next available gate number: **Gate 52** — the highest registered gate in
`lint-workflows.yml` today is Gate 51, specs/047-rate-limited-verdict).
Modeled on `verify-metrics-summary-record-emission.py`'s
`case_cost_line_formatter_has_exactly_one_home()` (literal-fragment scan
across every `.github/workflows/*.yml` and everything under
`.github/actions/` outside the declared home), extended to four subjects
(three idioms + the verdict shape) and to structural (not just literal)
detection for the token-mint idiom specifically.

**Rationale**: FR-023 requires "a structural scan... not merely an
assertion that the two known consumers call the shared definitions, which
could not have failed for the case that produced this issue" — i.e. the
gate must be able to catch a *third*, unknown site pasting the idiom, which
rules out an allowlist-of-two-call-sites check. Gate 47
(`verify-comment-canonical-pointers.py`) is prior art for *comment*
duplication (pointer resolution + vocabulary overlap) but the three idioms
here are *code* duplication — a re-paste would carry no comment at all —
so the metrics-summary gate's literal-fragment-scan shape is the closer
match, per CLAUDE.md's own citation of both as prior art.

Per-idiom detection basis:
- **Orphan-branch reset**: literal-fragment scan for the co-occurrence of
  `checkout --quiet --orphan`, `git rm -rq --cached`, and the
  `find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf` clause — three
  fragments that only appear together in this idiom's own shell, verified
  by reading both current copies (auto-release.yml:268-276,
  auto-update-spec-kit.yml:1836-1850).
- **Durable failure issue**: literal-fragment scan for the co-occurrence of
  `gh label create` with `--force` and a `gh issue list ... --label
  "..." --state open --json number --jq '.[0].number // empty'` shaped
  lookup, outside the declared composite.
- **Fail-infra verdict**: literal-fragment scan for a `jq` program whose
  text contains all six field names (`outcome`, `verified_head`,
  `failing_check`, `expected`, `observed`, `evidence_url`) together,
  outside `_shared/auto-release-verdict.sh` and the one framing site that
  calls it.
- **Scoped App-token mint + reachability check**: this one needs
  structural, not purely literal, detection, because
  `actions/create-github-app-token@v3` alone is legitimate elsewhere
  (`wing-commander-context/action.yml:62-67`, no reachability re-check
  follows it — that is a different, allowed idiom: minting *a* token, not
  minting-then-re-verifying-a-second-repo). The gate parses each
  workflow/composite's YAML (the way `lint-workflows.yml`'s own inline
  gates already do) and flags a job that contains BOTH (a) a step with
  `continue-on-error: true` invoking `uses: actions/create-github-app-token@*`
  and (b) a later step in the same job reading that step's `.outcome`
  output — the two-clause signature that makes this idiom what it is,
  distinct from a bare token mint.

**Alternatives considered**: An AST/byte-diff comparison against the
canonical composite's own source was rejected as both more complex to
implement correctly (parsing shell, not YAML, to diff) and less resilient
to legitimate small variation (e.g. a caller's own env var names) than a
distinctive-fragment scan, which is exactly why the metrics-summary gate
(prior art, already reviewed and merged) uses fragments over diffing.

## D8. Waiver file: reuse the stage-invariant-waivers.json shape verbatim

**Decision**: `.github/scripts/single-home-waivers.json`, same schema as
the existing `.github/scripts/stage-invariant-waivers.json` (Gate 31's
waiver file): a `"waivers"` list, each entry `{file, check, pattern, count,
issue, reason}`, stale-checked in both directions (a waiver matching zero
findings fails the gate; a waiver whose matched count differs from its
declared `count` fails the gate).

**Rationale**: FR-026 requires a registered waiver file, never a code
comment, and this repository already has exactly this mechanism, reviewed
and battle-tested (`verify-stage-invariants.py:362-477`, the "a waiver
cannot outlive its reason, and it cannot quietly widen" design). Building a
second, differently-shaped waiver mechanism for Gate 52 when one already
exists and fits would itself violate CLAUDE.md's "shared logic has exactly
one home" — the pattern, not just the idioms, gets one home.

**Alternatives considered**: An inline `# gate52-waiver: reason` comment
convention was rejected — FR-026 explicitly forbids honouring a waiver
expressed as a comment.

## D9. Promotion-prevention scan (FR-025)

**Decision**: The same Gate 52 script also scans every
`workflow_call`-only stage workflow (using the existing
`wc_published_stages.py` discovery helper already used by Gate 31/48) and
every composite action directly under `.github/actions/*` whose directory
name does not start with `_` (i.e. the published surface) for any
`uses:`/sourced-script reference resolving into an `_shared/` path — either
`./.wing-commander-pipeline/.github/actions/_shared/...` or
`./.github/actions/_shared/...`. A hit fails the gate.

**Rationale**: FR-025 requires this fail specifically for "a `workflow_call`
stage workflow or a published composite action" resolving an internal
helper — reusing the existing published-stage/composite discovery avoids
re-deriving what counts as "published" a second time (that logic already
exists for Gate 31/48's own invariant checks).

## D10. Constitution VII amendment (FR-024)

**Decision**: A PATCH-level clarification bump (1.6.0 → 1.6.1) to
Principle VII, adding one sentence: underscore-prefixed directories under
`.github/actions/` are internal to this repository and are not part of the
published, adopter-pinned surface; promoting one later is a deliberate act
in a future release, not a rename. Carries the repository's usual Sync
Impact Report comment block.

**Rationale**: FR-024 itself calls this "a clarification bump" ("the
amendment is a clarification bump carrying the repository's usual Sync
Impact Report, so the carve-out is a stated rule rather than a remembered
one"), and the Assumptions section confirms: "a clarification of the
existing two-interface split rather than a new principle... does not
retire or redefine any other principle." Per Governance's own semver rule
("clarifications = PATCH"), this is 1.6.1, not a MINOR bump — no new
principle or section is added, an existing one gains one sentence.

## D11. Record corrections are metadata edits, not new commits into #317

**Decision**: `docs/architecture.md` (FR-017) and
`specs/045-auto-release-verified-head/tasks.md` T023 (FR-018) are ordinary
file edits landing in spec 049's own PR. Spec 045's finalize narrative
(FR-019) is not a repository file — it is the body of merged PR #317
(confirmed: `<!-- wing-commander-finalize:narrative:begin -->...:end -->`
markers inside `gh pr view 317`'s body, merged 2026-09-14T03:03:22Z, state
MERGED), so its correction is a `gh pr edit 317 --body ...` metadata edit
in a later implementation task, not a commit. This does not touch #317's
merged commit history, matching the spec's own Assumption ("Correcting
spec 045's records is a forward correction. It does not touch the merged
commit history of #317").

**Rationale**: Directly verified against `origin/main`: no `shell_exempt`
entry for `auto-release.yml` exists in `.github/scripts/verify-stage-shell-lint.py`
(`SHELL_EXEMPT` contains exactly `watchdog.yml`, `auto-update-spec-kit.yml`,
`pr-conversation.yml`) or in `release.yml`, contradicting both T023's
current text and PR #317's narrative, which both claim the registration
happened. `docs/architecture.md` has zero mentions of `auto-release` today
(confirmed by full-file grep), confirming FR-017's premise.

## D12. Gate 12 / Gate 15 correction content for FR-019

**Decision**: The corrected finalize-narrative text states plainly that CI
on PR #317 failed Gate 12 and then Gate 15 before going green, rather than
"all gate suite checks passing" — no further investigation into *why* those
gates failed is in scope; the correction's job is accuracy about outcome,
not a retrospective on root cause (spec's own framing: "the finalize
narrative repeats the claim and additionally states 'all gate suite checks
passing' when CI had failed Gate 12 and then Gate 15" — the spec already
establishes this as fact, not something this plan needs to re-derive).

**Rationale**: FR-019 only requires the claim be checkable against what CI
actually did, not a postmortem. Re-deriving *why* two long-superseded CI
runs failed would be effort spent outside SC-007's bar ("every claim...
checkable against the merged tree").
