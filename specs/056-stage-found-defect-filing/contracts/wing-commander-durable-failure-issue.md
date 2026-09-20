# Contract: FR-011, FR-012, FR-016 — promoting and extending the durable failure issue

`research.md` D7/D8 explain why this is a promotion-plus-extension rather
than a new composite. This contract documents the delta against
`specs/049-single-home-release-idioms/contracts/durable-failure-issue.md`,
which remains the authority for everything unchanged.

## Move

`.github/actions/_shared/durable-failure-issue/` →
`.github/actions/wing-commander-durable-failure-issue/`. No other
non-underscore composite under `.github/actions/` omits the
`wing-commander-` prefix; this promotion adopts it rather than leaving the
promoted path as the one exception.

## Interface delta

**New inputs**, both optional, both no-op for a caller that omits them:

| name | required | default | description |
|---|---|---|---|
| `marker` | false | `""` | a literal string (e.g. an HTML-comment fingerprint marker) the lookup additionally requires inside a candidate issue's body. Empty means "match on label alone", today's behavior. |
| `state-scope` | false | `open` | `open` \| `all`. Only meaningful when `marker` is set; a caller that omits `marker` MUST NOT set this to `all` (the composite ignores it in that case — label-only lookups stay open-scoped, matching every existing caller). |

**Lookup step, when `marker` is set**:

```
gh issue list --repo "$GITHUB_REPOSITORY" --label "$LABEL" --state "$STATE_SCOPE" \
  --json number,state,body --jq \
  '[.[] | select(.body | contains($marker))] | first // empty'
```

(conceptually — the actual step keeps the existing single-`jq`-call shape,
adding the marker containment check and state field to the query rather
than a second round trip).

**New outcome, `operation: report` only**: when the match found is
`state == "closed"`, the composite does not comment on it (closing FR-012's
"never reopening a settled thread"); instead it creates a new issue exactly
as the no-match path does, except the caller-supplied body additionally
carries a line the caller is responsible for composing that links the
closed issue number back (the composite exposes the matched closed issue's
number via a new output, `matched-closed-issue`, so the caller can compose
that line into its `body-file` *before* invoking the composite for this
finding — the composite does not re-template the body a second time,
preserving its "never templates a body itself" contract).

**New output**: `matched-closed-issue` (empty unless the marker matched a
closed issue and `operation: report`).

Existing outputs (`issue-number`, `action-taken`) gain one new possible
`action-taken` value: `created-linked-closed`.

## Call sites (unchanged, repointed)

- `auto-release.yml`: both `report`-operation sites and the `close`
  operation site repoint their `uses:` to
  `./.github/actions/wing-commander-durable-failure-issue`, passing no
  `marker`/`state-scope` — behavior is byte-identical to before the move.
- `auto-update-spec-kit.yml`: its one `report` site repoints to
  `./.wing-commander-pipeline/.github/actions/wing-commander-durable-failure-issue`,
  same no-`marker` call, same behavior.

## New call site

- `wing-commander-stage-findings` (see
  `wing-commander-stage-findings.md`), which always sets `marker` to the
  finding's fingerprint marker and `state-scope: all`.

## Gate coverage

`verify-single-home-idioms.py`'s `DECLARED_HOMES["failure-issue"]` moves to
the new path in the same PR that moves the directory (research.md D8's
"consequence"); the gate's `check_promotion` pass, which already forbids a
published stage or non-underscore composite from resolving a `_shared/`
path, requires this — a promotion that left the old `DECLARED_HOMES` entry
pointed at the retired `_shared/` path would make the gate flag the new,
correct call sites as violations while missing a straggler still calling
the old path.
