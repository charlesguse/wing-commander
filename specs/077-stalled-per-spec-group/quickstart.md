# Quickstart: Validating the Stalled Survivor Job's Concurrency Group

This feature has no user-facing UI or CLI — validation means running the
gate this repository already uses to enforce the per-spec concurrency
contract, plus modelling the survivor job's admission condition and,
post-merge, re-driving one real run (SC-007).

## Prerequisites

- Python 3, `pyyaml` on `PATH` — the same dependencies
  `.github/scripts/verify-spec-branch-push-concurrency.py` already requires.
- No live GitHub API access needed for steps 1–3; step 4 requires a real
  dispatch against this repository (or a scratch adopter) after merge.

## 1. Prove Gate 80 accepts the new group and still rejects a degenerate one

```bash
python3 .github/scripts/verify-spec-branch-push-concurrency.py --self-test
```

Expected: every existing case still passes (Constitution VIII — nothing
this gate already caught stops being caught), plus the six new cases from
[contracts/gate-80-fallback-spelling.md](./contracts/gate-80-fallback-spelling.md):
the exact fallback spelling passes; a mismatched-job-name variant, the bare
`wing-commander-` constant, and two near-miss literals all still fail.

## 2. Prove Gate 80 passes over the repository with the waiver removed

```bash
python3 .github/scripts/verify-spec-branch-push-concurrency.py
```

Expected (per SC-001): `pr-conversation.yml`'s `stalled` job is listed among
the jobs checked, is **not** in the waivers file any more, and reports no
failure — its declared group matches the new accepted spelling.

## 3. Verify the survivor job's admission condition case by case (SC-003)

Read `stalled`'s shipped `if:` against data-model.md's condition table and
confirm, for each of the three `resolve-identity` outcomes crossed with each
`classify-and-announce` outcome:

| `resolve-identity` | `classify-and-announce` | `stalled` admitted? |
|---|---|---|
| success | success | No |
| success | failure | Yes |
| success | skipped | Yes |
| failure | skipped | Yes |
| skipped | skipped | Yes |

This is the same table data-model.md ships; re-derive it from the literal
`if:` string in the merged workflow file (not from this document) as the
actual verification step, the way spec 041's Gate 28 verifies its own six
conditions by evaluation rather than by inspection.

## 4. Confirm the comment gates still pass (SC-006)

```bash
python .github/scripts/run-local-gates.py
```

Expected: full green, including whichever gate(s) byte-compare the
concurrency-block and identity-derivation comments this feature rewrites
(research.md D7) — a stale comment asserting "spec-dir isn't knowable until
... this job" is exactly the kind of drift those gates exist to catch.

## 5. Post-merge: re-drive one real stalled run (SC-007)

Not automatable from this repository's own test suite — the same category
of confirmation this repository already defers to a live drill for
Actions-only behaviour (CLAUDE.md: "A fix to behaviour that only runs in
Actions is proven after merge by re-driving one run").

1. Open (or reuse) a PR whose head ref is `spec/<slug>` for a specification
   currently mid-cycle (an implement or rebase run holding
   `wing-commander-specs/<slug>`).
2. Trigger `pr-conversation` on that PR under a condition that stalls it
   before `classify-and-announce` completes (e.g. a deliberately invalid
   `container-image` input on a scratch dispatch, mirroring spec 041's own
   drill pattern).
3. Confirm: the run does not attempt its `git push` until the holder's cycle
   releases `wing-commander-specs/<slug>` (visible as the `stalled` job
   queuing, not running, in the Actions UI while the holder is active); the
   mark lands cleanly once the slot is free; the stall notice still posts.
4. Separately, dispatch `pr-conversation` for a PR whose head ref does not
   parse as `spec/NNN-slug` (a `fix/` branch) and confirm zero comments and
   zero failed jobs (SC-004, unchanged from today).

Record the run URL as the evidence this drill requires, on the PR or the
lifecycle issue.
