# Phase 1 Data Model: Auto-Rebase

This feature has no application data model — it manipulates GitHub
branches, an implicit `spec/*` branch set, `spec-meta.json` (read-only),
and lifecycle-issue comments/labels. The "entities" below are the ones
named in `spec.md`'s Key Entities section, expressed as their concrete
on-disk/on-GitHub representation, plus the escalation marker research.md
D6 introduces.

## Main-line advance (trigger, not persisted)

Read once per run from the triggering event; determines only *whether*
`discover` runs, never which branches it selects (that's D1, driven by
`spec-meta.json` state).

| Source | Field | Used for |
|---|---|---|
| `push` to `main` | `github.actor` | FR-009 loop guard — skip when it ends with `[bot]` |
| `schedule` (`17 4 * * *`) | — | FR-001's periodic run; the actor gate still evaluates but scheduled runs are never bot-actor, so it's a no-op filter here |

## In-flight specification working branch (`spec/NNN-slug`)

Discovered fresh each run (research.md D1) — never cached across runs.

| Field | Source | Used for |
|---|---|---|
| `slug` | Parsed from `spec/<slug>` via `git ls-remote --heads origin 'spec/*'` | Identity; must match `^[0-9]{3}-[a-z0-9][a-z0-9-]*$` |
| `spec-meta.json` (`.stage`) | `git show spec/<slug>:specs/<slug>/spec-meta.json` — **the branch tip, never `main`** | Exclude if `"stalled"` (FR-002); malformed/self-inconsistent (`.spec_dir != specs/<slug>`) also excludes, logged as "cannot identify" |
| `spec-meta.json` (`.issue`) | Same read | The lifecycle issue to escalate to on abandonment (FR-013) |
| Branch tip SHA | `git rev-parse` after checkout (= the lease value `--force-with-lease` protects, research.md D3) | FR-011's concurrent-update guard; also half of D6's dedup marker |

A branch failing the self-identity check is excluded from *all* action
this run — not rebased, not escalated (spec.md edge case: "must record
why rather than acting blindly on an unidentified specification"). This
is logged via `::warning::` and `$GITHUB_STEP_SUMMARY` only; there is no
pull request to comment on the way `speckit-7-cleanup.yml`'s refusal path
has, and the issue itself is exactly what couldn't be trusted.

## Rebase attempt (per matrix entry, ephemeral — not persisted beyond its own run)

| Field | Computed | Outcome it feeds |
|---|---|---|
| `before` (`git rev-parse HEAD`, pre-rebase) | Checkout step | No-op detection (`before == after` after a clean rebase ⇒ nothing to publish) |
| `origin/main` tip | `git fetch origin main:refs/remotes/origin/main` (scoped fetch — never touches the branch's own remote-tracking ref, research.md D3) | Rebase target |
| `after` (`git rev-parse HEAD`, post-rebase) | After `git rebase origin/main` exits 0 | Clean path: push iff `after != before` |
| Conflict state | `git status` mid-rebase (`rebase-merge`/`rebase-apply` present) | Routes to the AI-assisted path |
| `conflicted_files` (accumulated) | Agent's own `git diff --name-only --diff-filter=U` calls at each stop, appended to a temp manifest | Input to the post-step scope check (research.md D4) |
| `pre_tip` commit sequence | `git rev-list --reverse origin/main..HEAD` captured before the agent runs | Baseline for the pairwise per-commit scope check |
| `post_tip` commit sequence | Same command, re-run after the agent reports the rebase complete | Compared 1:1 against `pre_tip`'s sequence; length/order mismatch ⇒ scope-check failure ⇒ abandon |

**Outcome resolution**:

```
rebase clean, tip unchanged            → no-op (FR-004 acceptance #3 / edge case) — no push, no comment
rebase clean, tip changed              → push --force-with-lease (FR-004)
  lease rejected (concurrent update)   → skip silently, no comment (FR-011)
rebase conflicts, agent resolves,
  scope check passes                   → push --force-with-lease (FR-006), same lease behavior as above
rebase conflicts, agent fails/
  times out/self-aborts, OR
  scope check fails                    → git rebase --abort; branch untouched; escalate (D6) — FR-007/FR-008
rebase itself errors outright
  (not a conflict stop)                → git rebase --abort; branch untouched; escalate (D6) — FR-007/FR-008
branch excluded at discover time
  (stalled, unidentifiable, or
  known-blocked & unchanged, D6)       → not attempted at all this run
```

## Escalation marker (lifecycle issue comment + label, `rebase:blocked`)

Not a file — the closest thing this stage has to persisted cross-run
state, deliberately kept off `spec-meta.json` (FR-007 forbids writing to
the working branch on an abandoned attempt).

| Element | Written when | Read when |
|---|---|---|
| `rebase:blocked` label on the lifecycle issue | An attempt is abandoned (FR-008) | `discover`, to decide whether to even look for a marker comment (cheap short-circuit: absent label ⇒ never blocked, always attempt) |
| Comment body: human-readable ask for help + `<!-- speckit-rebase: blocked branch-sha=<sha> main-sha=<sha> -->` | Same | `discover`, on the most recent comment matching the marker prefix, to compare against the branch's *current* tip and `main`'s *current* tip (FR-012 dedup, research.md D6) |
| Label removal | A subsequent attempt on the same branch succeeds (clean or AI-resolved) | — (auto-recovery; nothing reads the absence explicitly, it's just no longer true) |

**Dedup decision** (`discover`, per candidate branch already past the
`stalled` filter):

```
label absent                                        → attempt (never blocked)
label present, marker SHAs == current branch+main    → exclude from this run's matrix (FR-012: ask once, then skip until it changes)
label present, marker SHAs != current branch or main → attempt again (something changed since the stall)
```

A repeat failure against a *new* `(branch-sha, main-sha)` pair posts a
fresh comment with a refreshed marker rather than reusing the old one, so
the maintainer always sees the current stall's SHAs and timestamp.

## Lifecycle issue (GitHub issue, unchanged shape from stages 1–7)

This stage's only writes, both gated on the abandon path (FR-008) — the
clean and AI-resolved paths never touch the issue at all (edge case:
"completes without changing that branch and without posting a comment"
when there's nothing to rebase; the same silence applies to every
successful/no-op rebase, not just the literal no-op case):

| Outcome | Comment | Labels |
|---|---|---|
| Abandoned, issue identified | Ask for human help + SHA marker (research.md D6) | `rebase:blocked` added |
| Abandoned, issue unidentifiable | None (nothing to comment on) | None — logged to step summary only |
| Subsequent success on a previously-blocked branch | None | `rebase:blocked` removed |
