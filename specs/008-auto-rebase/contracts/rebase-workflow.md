# Contract: `speckit-rebase.yml`

This project has no library/API surface; its "interfaces" are the GitHub
Actions trigger contract and the deterministic checks/writes that must
run in order. This document is the contract the implementation (tasks
phase, next stage) must satisfy.

## Trigger contract

```yaml
on:
  push:
    branches: [main]
  schedule:
    - cron: "17 4 * * *"
```

Unchanged from the stub (`docs/architecture.md` §Auto-rebase,
research.md D7).

## `discover` job gate (coarse — job-level `if:`, payload-only)

```
discover:
  !endsWith(github.actor, '[bot]')
```

Unchanged from the stub. On `schedule` events this is always true
(FR-001); on `push` events it is false exactly when the push was made by
the pipeline's own App-token identity (FR-009).

## `discover` job contract (FR-002, FR-012, FR-013)

Runs once per trigger, checkout of `main` only (bootstrap — reused for
`speckit-context`'s token mint, not for reading `spec-meta.json`, per
research.md D1).

1. `git ls-remote --heads origin 'spec/*'` → candidate slugs.
2. For each candidate, `git show spec/<slug>:specs/<slug>/spec-meta.json`:
   - Missing, unparseable, or `.spec_dir != specs/<slug>` → excluded;
     `::warning::` + `$GITHUB_STEP_SUMMARY` line naming the branch and
     the reason (spec.md edge case — never acted on blindly).
   - `.stage == "stalled"` → excluded silently (FR-002; this is routine,
     not a warning condition).
   - Otherwise: candidate carries forward `slug`, `spec_dir`, `.issue`.
3. For each surviving candidate, check the lifecycle issue (`.issue`)
   for label `rebase:blocked`:
   - Absent → keep.
   - Present → `gh issue view <issue> --json comments` and find the most
     recent comment matching `<!-- speckit-rebase: blocked branch-sha=([0-9a-f]+) main-sha=([0-9a-f]+) -->`.
     Compare `branch-sha` against the branch's current
     `git ls-remote origin spec/<slug>` tip and `main-sha` against
     `git rev-parse origin/main`. Both equal → exclude (FR-012 dedup,
     research.md D6). Either differs → keep.
4. Emit the surviving `{slug, spec_dir, issue}` triples as a JSON array
   via `echo "branches=$json" >> "$GITHUB_OUTPUT"`. An empty array is a
   valid, successful output (FR-010's "no in-flight branches" case).

## `rebase` job contract (FR-003–FR-011)

```yaml
rebase:
  needs: discover
  strategy:
    fail-fast: false
    matrix:
      include: ${{ fromJson(needs.discover.outputs.branches) }}
  concurrency:
    group: speckit-rebase-${{ matrix.slug }}
    cancel-in-progress: false
```

Zero matrix entries ⇒ zero job runs ⇒ workflow still succeeds (FR-010).
Steps, per matrix entry:

1. `speckit-context` for the App token (push identity — research.md D3's
   note on why this matters for D7's loop guard).
2. Checkout `spec/${{ matrix.slug }}`, `fetch-depth: 0` — this populates
   `refs/remotes/origin/spec/<slug>` at the branch's *current* tip, which
   becomes the `--force-with-lease` comparison value. **No later step may
   run a bare `git fetch origin` (no refspec) — only
   `git fetch origin main:refs/remotes/origin/main`** (research.md D3);
   violating this silently defeats FR-011.
3. `before=$(git rev-parse HEAD)`; `git rebase origin/main`.
4. **Exit 0** (clean):
   - `after=$(git rev-parse HEAD)`. `after == before` → done, no push,
     no comment (Acceptance Scenario 1.3).
   - `after != before` → `git push --force-with-lease origin
     HEAD:refs/heads/spec/${{ matrix.slug }}`.
     - Succeeds → done (FR-004). If the branch was previously
       `rebase:blocked`, remove the label (research.md D6 auto-recovery).
     - Rejected (remote moved since checkout) → log and exit 0, no
       comment (FR-011).
5. **Exit nonzero, mid-rebase conflict** (`git status` shows
   `rebase-merge`/`rebase-apply`):
   - Record `pre_tip` commit sequence: `git rev-list --reverse
     origin/main..HEAD` (captured **before** the agent step — this is the
     ordered list the agent is expected to finish replaying).
   - `anthropics/claude-code-action@v1`, `--model claude-sonnet-5`,
     `--max-turns <bounded>`,
     `--allowedTools "Read,Edit,Grep,Glob,Bash(git status:*),Bash(git diff:*),Bash(git add:*),Bash(git rebase --continue:*),Bash(git rebase --abort:*)"`,
     `--disallowedTools "WebSearch,WebFetch"`. Prompt instructs: resolve
     only the in-progress rebase's conflicts, one stop at a time, editing
     only conflict-marked files, appending each stop's
     `git diff --name-only --diff-filter=U` output to a manifest file
     before resolving it, `git rebase --continue` after each; never
     `git commit`, `git push`, or any `gh` command (not in the
     allowlist regardless); `git rebase --abort` and stop if genuinely
     stuck rather than leaving a half-resolved stop.
   - `continue-on-error: true` on this step — a hard failure here is
     handled by step 6 below, not by failing the job outright.
6. **Deterministic post-step** (always runs after step 5, `if: always()`
   guarded on "step 5 was attempted"):
   - Rebase not reported complete (`rebase-merge`/`rebase-apply` still
     present, or the agent step errored/timed out) → scope check
     skipped, treat as failure.
   - Otherwise, `post_tip` commit sequence: `git rev-list --reverse
     origin/main..HEAD`. Length/order must match `pre_tip`'s sequence
     (anything else ⇒ failure — the tool allowlist makes this only
     reachable via a disallowed operation, so treat as a hard failure,
     not a silent skip). Pairwise per commit: `git show --name-only`
     on the `post_tip` commit must be a subset of (the corresponding
     `pre_tip` commit's `git show --name-only` **∪** the manifest file
     from step 5). Any file outside that union ⇒ scope-check failure.
   - Pass → `git push --force-with-lease` exactly as step 4 (FR-006);
     same lease/no-comment-on-rejection behavior; same
     `rebase:blocked` label removal on success.
   - Fail (any of the above) → `git rebase --abort` if still mid-rebase;
     no push under any circumstance (FR-007).
7. **Escalation** (only on a step 6 failure, or an outright non-conflict
   rebase error in step 3/4):
   - Re-read `pre_tip`'s `specs/${{ matrix.slug }}/spec-meta.json` for
     `.issue` (research.md D6 — re-derived, not reused from `discover`,
     since a long agent turn can separate the two reads).
   - Issue resolves → `gh issue comment` with the human-readable ask +
     the `<!-- speckit-rebase: blocked branch-sha=<pre_tip> main-sha=<origin/main tip> -->`
     marker; `gh label create rebase:blocked --force`; `gh issue edit
     --add-label rebase:blocked` (FR-008).
   - Issue does not resolve (missing/inconsistent) → `::warning::` +
     `$GITHUB_STEP_SUMMARY` only; no comment, no label (spec.md edge
     case — matches `discover`'s own identical rule in step 2 above,
     since the same read can fail here even if it passed at discovery
     time, e.g. a main-line advance rewrote something in between).

## Non-goals (explicitly out of contract, per spec.md Assumptions)

- Rebasing `spec-draft/*` (short-lived intake PR heads) — out of scope;
  only `spec/NNN-slug` persistent working branches are considered
  (research.md D1).
- Any automated retry-with-a-different-model escalation ladder (unlike
  `speckit-5-implement.yml`'s haiku→opus retry) — a stuck rebase always
  escalates to a human, never auto-retries at a higher tier.
- Touching `main` itself, or merging/approving anything — this stage
  only ever updates `spec/NNN-slug` branches and lifecycle-issue
  comments/labels.
