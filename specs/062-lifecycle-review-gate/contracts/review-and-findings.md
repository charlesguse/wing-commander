# Contract: Review and Findings

## Reviewer step

- **Model**: `vars.WING_COMMANDER_LIFECYCLE_REVIEW_GATE_MODEL`, default
  `claude-sonnet-5` (constitution II — implementation-weight; the review
  elaborates an already-implemented PR, the same weight class planning
  and task generation occupy, not the specification premium tier).
- **Turn budget**: `wing-commander-turn-ceiling`, `intended-turns: 30`
  (matching `board-loop.yml`'s reviewer — no reason for a different
  ceiling; FR-009).
- **Tool allowlist**: `Skill,Read,Grep,Glob,Bash(python3 -I
  <pristine>/scripts/git_read.py:*),Bash(cat:*)`;
  disallowed: `WebSearch,WebFetch,Write,Edit,Bash(git:*),Bash(cd:*),
  Bash(git push:*),Bash(git commit:*)` — the same read-only shape
  `board-loop.yml`'s reviewer already uses, plus `Skill` (D3) to reach
  Claude Code's packaged `code-review` capability, which
  `board-loop.yml`'s reviewer does not grant because it never invokes a
  packaged skill.
- **Independence**: a separate job, separate agent invocation, no shared
  transcript/memory with whatever implemented or finalized the PR
  (FR-008) — structurally true, the same way `board-loop.yml`'s reviewer
  job has no access to its fixer job's transcript.
- **Context handed to the agent**: the PR's diff, title, body, and commit
  subjects staged as files (no `gh` grant, matching `board-loop.yml`'s
  reviewer — FR-011: "framed as untrusted data, never as instructions").
  The reviewer is instructed to invoke the `code-review` skill against
  the staged diff at an explicit effort level (a fixed default, e.g.
  `medium` — the exact level is an implementation-time tuning choice) and
  to end its final message with the fenced
  ` ```wing-commander-review-findings ` block, restating whatever the
  skill's own review surfaced in that shape.

## Finding shape (reused, not new)

Validated against `.github/schemas/board-review-finding.schema.json`
unmodified — see data-model.md §3. The existing validator
(`verify-board-review-finding-schema.py`) is extended to also validate
this gate's own fenced-block output against the same schema file (one
schema, two producers), never a second, near-identical schema (FR-010,
FR-035).

## Posting the review

`wing-commander-post-review-comment` (D10; data-model.md, new composite):
`gh api -X POST repos/<repo>/pulls/<pr>/reviews -f event=COMMENT -F
body=@<file>`. The body states plainly why the review is `COMMENT` rather
than `APPROVE`/`REQUEST_CHANGES` — the same explanation
`board-loop.yml`'s reviewer already gives verbatim ("GitHub rejects
APPROVE and REQUEST_CHANGES from the PR's own author identity, and this
gate's PR and its review share the wing-commander-bot App identity") —
plus the round number and head SHA.

## Clean vs. not-clean outcome

- **Zero open in-scope findings** → `outcome: clean` (data-model.md §2);
  the gate reports a passing status on the head SHA suitable for use as a
  required check (FR-013) — a `gh api` commit-status write
  (`state=success`, matching the granularity `lint-workflows.yml`'s own
  status already uses) or a `check_run`, whichever this repository's
  existing status-reporting convention for a non-required-workflow check
  uses (an implementation-time lookup against how `lint-workflows.yml`
  itself surfaces as a required check, so this gate's pass reads the same
  way to a branch-protection rule).
- **Any open in-scope finding, budget exhaustion, or the reviewer step
  itself failing/timing out/being rate-limited** → a non-passing,
  distinguishable status (FR-014): the failure is never reported as
  silence — a `state=failure`/`state=error` distinct from "no status
  posted yet," and the lifecycle issue names which of the four this round
  hit (FR-015, SC-008). A rate-limited round (the existing
  `wing-commander-agent-verdict` rate-limit signal, spec 047's precedent)
  is retryable — it does not increment `review_gate.round` or write
  `folded_fingerprints`/`filed_fingerprints`, so the next run tries the
  same head SHA fresh rather than counting it as a spent, non-converging
  round.

## Out-of-scope findings (files touched outside the PR's own diff)

Filed exactly as `board-loop.yml`'s reviewer already files its own
out-of-scope findings: `wing-commander-durable-failure-issue`, deduped by
the fingerprint scheme in data-model.md §1, body-prefixed `Found by the
code review of #<N>.` (FR-019). Never held against this PR's readiness or
gate status (FR-020) — `disposition`'s partition step (contracts/
lifecycle-review-gate-workflow.md job 5) only ever counts `in_scope: true`
findings toward `review_gate.findings_open`.
