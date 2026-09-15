# Contract: FR-017, FR-018, FR-019, FR-020 — the records describe the tree that shipped

`research.md` D11/D12 explain why these are three different kinds of edit
(a new doc section, a tasks.md correction, and a PR-body metadata edit)
landing through three different mechanisms, and what FR-019's correction
says without re-deriving root cause.

## FR-017 — `docs/architecture.md` gains an Auto-Release section

**New `## Auto-Release` H2**, inserted after the existing
`## Private-image dogfood` section (today ending line 1103) and before
`## Reusability` (today starting line 1105) — i.e. it joins
`## Auto-Update Spec Kit` and `## Private-image dogfood` as the third
free-standing, unnumbered pipeline workflow documented before the
Reusability section, in the position a reader scanning that list would
expect it (chronological/thematic neighbor to the other two
schedule-or-dispatch-triggered, non-`intake→cleanup`-chain workflows).

**Depth**: matches `## Private-image dogfood`'s shape (Trigger paragraph +
one prose block covering purpose, key steps, wrapper/stage division), per
the spec's own Assumption — not the deeper bulleted-subsection shape of
`## Auto-Update Spec Kit`, and not a published-stage-depth section (this
workflow is not a published stage; it has no `workflow_call` contract to
document as an interface).

**Content** (drawn from the workflow as consolidated by this same
feature, so it describes the *post*-consolidation tree, not the
pre-consolidation one): trigger (`schedule`, `workflow_dispatch`,
`WING_COMMANDER_AUTO_RELEASE_PAUSED` kill switch, per docs/setup.md — those
repository variables already exist per spec 045); purpose (verify the
latest merged features against a maintainer-onboarded end-to-end test
repository before cutting a release); and a pointer to the three shared
composites this section's own workflow now consumes
(`_shared/scoped-app-token`, `_shared/orphan-branch-reset`,
`_shared/durable-failure-issue`) rather than re-describing their mechanics
inline — the section documents auto-release.yml's shape, not the idioms,
which already have their own canonical description at their
`action.yml`'s own header comment (the same "one canonical comment, others
point at it" convention this repository already uses, per Gate 47).

## FR-018 — `specs/045-auto-release-verified-head/tasks.md` T023

Today's text (line 199) directs adding `auto-release.yml` to the
`shell_exempt` array and implies that happened. Corrected text records,
as a completed *finding* rather than a completed *action*: that
`auto-release.yml` triggers on `schedule`/`workflow_dispatch`, not
`workflow_call`, so `wc_published_stages.py` never derives it as a
published stage; that Gate 48's closure check therefore never forces it
into either `SHELL_LINTED` or `SHELL_EXEMPT`; and that no entry for it
exists in `verify-stage-shell-lint.py`'s `SHELL_EXEMPT` dict or in
`release.yml` today, confirmed against `origin/main`, and none is
required. The task stays checked off (`[X]`) — the task was "record the
deliberate choice," and recording it correctly is what this feature
finishes; it was not "add the registration," which was never the
requirement Gate 48's own design imposes.

## FR-019 — PR #317's finalize narrative

Not a repository file: the `<!-- wing-commander-finalize:narrative:begin
--> ... <!-- wing-commander-finalize:narrative:end -->` block inside
merged PR #317's own description (`gh pr view 317`, state `MERGED`,
merged 2026-09-14T03:03:22Z). Corrected via `gh pr edit 317 --body ...` in
an implementation task — a metadata edit to a merged PR's description,
not a new commit, matching the spec's own Assumption that this "does not
touch the merged commit history of #317."

**Corrected content**: replace "all gate suite checks passing" with an
accurate statement that CI on #317 failed Gate 12, then failed Gate 15,
before eventually passing; replace the claim that `auto-release.yml` "was
registered as shell_exempt in release.yml's Gate 1a" with the same
finding FR-018 records (no registration exists or is required). No
investigation into *why* Gate 12/Gate 15 failed on that run is in scope —
FR-019 requires the outcome be checkable against what CI did, not a root
cause.

## FR-020 — no private downstream consumer named anywhere

Every artifact this feature adds or edits (the four `_shared/` files,
Gate 60, its waiver file, the `docs/architecture.md` section, the tasks.md
correction, the PR #317 body edit) stays generic to any adopting
repository — no repository name, org, or customer beyond this public
repository's own. This is a constraint checked by review, not a
machine-checkable gate this feature adds (no FR asks for one); the code
review pass this PR gets before merge (per CLAUDE.md's "every fix PR gets
a code review before merge") is where this is verified, the same as for
every other PR in this repository.
