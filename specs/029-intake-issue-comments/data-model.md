# Data Model: Include Follow-Up Comments in Intake Specification

**Feature**: 029-intake-issue-comments

This feature has no application data store — its "entities" are the values
that flow through one `intake.yml` job run at run time (GitHub API reads →
a new deterministic filter step → staged file → agent-assembled feature
description). Documented here as data shapes/validation rules, mirroring
the spec's own Key Entities section and `research.md`'s decisions.

## Entities

### LifecycleIssue (read, not modified by this feature's new logic)

| Field | Type | Source | Notes |
|---|---|---|---|
| `number` | integer | `inputs.issue-number` | Already an existing intake input. |
| `title` | string | `gh issue view --json title` (agent step, existing) | Untrusted; unchanged by this feature. |
| `body` | string | `gh issue view --json body` (agent step, existing) | Untrusted; unchanged by this feature. |
| `author.login` | string | `gh issue view --json author` (agent step, existing) | Untrusted display value. |
| `author.id` | integer | **NEW**: `gh api repos/{owner}/{repo}/issues/{number} --jq .user.id` (deterministic step) | Needed to evaluate the author-inclusive clause of the trust gate (FR-002) *before* the agent runs; the agent's own `--json author` fetch has no numeric id field, so this is a separate, deterministic read. |

### Comment (read, all — before filtering)

Per the spec's Key Entities section: "a single follow-up on the issue;
carries its author, the author's association to the repository, whether the
author is a bot, a creation time (for ordering/precedence), and a body of
untrusted text."

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | integer | `GET .../issues/{number}/comments` (`gh api`) | Comment identity, not otherwise used downstream. |
| `user.login` | string | same | Display only — the qualification decision uses `user.id`, not login (research.md D2). |
| `user.id` | integer | same | Compared against `LifecycleIssue.author.id` for the author-inclusive clause. |
| `user.type` | enum `User` \| `Bot` \| `Organization` | same | `"Bot"` → excluded unconditionally (FR-003), regardless of `author_association`. |
| `author_association` | enum (`OWNER`, `MEMBER`, `COLLABORATOR`, `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, `FIRST_TIMER`, `MANNEQUIN`, `NONE`) | same | Qualifies only when `OWNER`, `MEMBER`, or `COLLABORATOR` (FR-002). |
| `created_at` | ISO-8601 timestamp | same | Ordering key (Assumptions: "later" = later creation time); also the staged file's per-section heading. |
| `body` | string (untrusted) | same | Never shell-interpolated, never pasted into the agent prompt string (FR-004) — reaches the agent only via a staged file (D3) and only if qualifying (below). |

This entity exists only transiently inside the new deterministic step's
process memory / pipe — it is never itself persisted to disk. Only the
derived `QualifyingComment` (below) is written to disk.

### QualifyingComment (derived — the only comment shape that reaches disk/agent)

A `Comment` that passed the trust gate (research.md D2):

```
qualifies(c, issue_author_id) :=
  c.user.type != "Bot"
  AND ( c.author_association ∈ {OWNER, MEMBER, COLLABORATOR}
        OR c.user.id == issue_author_id )
```

Written, in `created_at` order, to a single staged file (default path
`/tmp/wing-commander/intake-comments.md`) with one section per qualifying
comment:

```
## Comment by @<user.login> (<created_at>)

<body, verbatim>
```

Non-qualifying and bot comments are **not** written anywhere (research.md
D3 — defense in depth: excluded content is never reachable through this
file, not merely instructed-against).

### CommentCounts (derived — the only cross-comment signal exposed outside the file)

Computed once, in the same deterministic step, as GitHub Actions step
outputs (numbers only — never comment content):

| Output | Definition |
|---|---|
| `total-count` | Count of all comments on the issue (qualifying + non-qualifying + bot). |
| `qualifying-count` | Count of `QualifyingComment`s (also: number of sections in the staged file). |
| `excluded-human-count` | Count of comments where `user.type != "Bot"` and `qualifies() == false` — i.e., excluded specifically by the association/author-id check, not by being a bot. |

### NoticeCondition (derived, deterministic — FR-008)

```
notice_needed := (qualifying-count == 0) AND (excluded-human-count > 0)
```

See research.md D4 for the full rationale, including why bot-only exclusion
(`excluded-human-count == 0`) does **not** trigger the notice. When true, a
`kind: action` callout (via the existing `wing-commander-callout` composite
action, same as every other intake callout point) is posted stating that
non-qualifying comments exist and were not used, and that the issue body may
need updating first — independent of, and prior to, the agent step, since
the condition is fully known before the agent runs.

### FeatureDescription (assembled by the agent, not persisted as a separate artifact)

The composite text handed to `/speckit-specify` (FR-005): `LifecycleIssue.
title` + `LifecycleIssue.body` + the ordered `QualifyingComment` sections
read from the staged file, when `qualifying-count > 0`; identical to today's
"title + body" when `qualifying-count == 0` (FR-007 — byte-for-byte
equivalent behavior, since nothing new is appended). This is not a new file
or schema — it is the same in-context feature description `/speckit-specify`
already consumes today, just assembled from one additional source.

## Relationships

```
LifecycleIssue.author.id ─┐
                           ├─▶ qualifies(Comment) ─▶ QualifyingComment[] ─▶ staged file ─┐
Comment[] (all, via API) ─┘                       └─▶ CommentCounts ─▶ NoticeCondition   │
                                                                                           ▼
                                              FeatureDescription = title + body + staged file (if any)
                                                                                           │
                                                                                           ▼
                                                                            /speckit-specify (unchanged)
```

## State / lifecycle

No persistent state or state machine, and nothing written back to
`spec-meta.json` beyond what intake already writes today. This is a
stateless, per-run computation: fetch → filter → stage → (agent) assemble →
specify, entirely within one `intake.yml` job invocation. The staged file
lives under `/tmp/wing-commander/` (runner-local, matching `clarify.yml`'s
existing staging convention) and is discarded with the runner at job end.
