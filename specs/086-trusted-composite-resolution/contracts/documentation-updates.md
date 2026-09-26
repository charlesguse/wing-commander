# Contract: Documentation Updates (FR-014)

One canonical statement, pointers everywhere else — the same discipline
CLAUDE.md's "Shared logic has exactly one home" already requires of
prose, applied here to a prose statement rather than a `run:` block or jq
program.

## Canonical statement — `.github/workflows/board-loop.yml` file header

The existing header (lines 1-13 today) already states why this file is
not a published stage. This feature appends a paragraph stating the
trusted-copy rule itself: every job resolves the loop's own composites
from a checkout of this repository at `github.sha`
(`.wc-pristine-repo`, never `./.github/actions/...` directly), established
before any credential mint and any agent step, gitignored so no `git add`
can stage it into an item's branch, alongside (not instead of) the
existing `$RUNNER_TEMP/wc-pristine` helper-script/schema snapshot (#583) —
naming Gate 99 and Gate 98 as the two halves of the same provenance
property, and pointing at
`specs/086-trusted-composite-resolution/{spec.md,plan.md,research.md}`
the way the existing header already points at spec 057's own documents.

This is the ONE place the rule's rationale is written in prose. Every
other site below points here rather than restating it.

## Pointer sites

| Site | Pointer text (paraphrased; exact wording is an implementation task) |
|---|---|
| Each of the 8 sidecar checkout steps in `board-loop.yml` | A short comment: "see this file's header for why every job does this" — never the full rationale repeated |
| `.github/actions/wing-commander-context/action.yml` header | One sentence appended after the existing "verified self-checkout snippet": board-loop.yml is not a published stage and is not called through this composite's `pipeline-repo`/OIDC mechanism at all — it resolves its own composites the same way, from its own repository at `github.sha`; see board-loop.yml's own header |
| `.github/workflows/lint-workflows.yml`, Gate 98's comment block | One sentence appended: the composite half of this same provenance rule is Gate 99, immediately below |

## What does NOT change

- `wing-commander-lifecycle-gate`'s header (the "like every shared
  composite, this action is resolved from the pipeline repository's own
  checkout at `github.job_workflow_sha`" paragraph) — that statement is
  correct for every *published* stage that calls it, which this feature
  does not touch.
- Any `docs/*.md` file — board-loop.yml carries no `workflow_call` inputs
  before or after this feature (spec 057 FR-062/FR-063), so there is no
  adopter-facing surface for `docs/adoption.md` or `docs/setup.md` to
  document.
- Gate 98's own docstring, allowlist, or self-test (spec.md Out of Scope).

## Verification

`verify-single-home-idioms.py` is not extended by this feature — the
canonical-statement/pointer discipline here is prose, not a shell/jq
idiom that script's `DECLARED_HOMES` mechanism tracks. No new gate checks
the pointer text itself; it is reviewed the same way the rest of this PR
is (Constitution Governance: every PR is checked against the constitution
and, for prose duplication, against CLAUDE.md, during ordinary review).
