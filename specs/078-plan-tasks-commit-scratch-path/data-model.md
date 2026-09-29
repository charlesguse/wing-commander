# Phase 1 Data Model: A Plan or Tasks Agent Can Write a Multi-Line Commit Message

This feature has no application data model — no database, no request/response
schema. What plays the equivalent role is the set of **agent prompt sites**
this change touches, the **canonical guidance source** that renders into
them, and the **gate's** view of both. This document is that structure,
concrete enough for `/speckit-tasks` to enumerate one task per site.

## Entity: Agent prompt site

One `prompt:` body handed to one agent invocation (`anthropics/claude-code-
action@v1`) in one job, in one workflow. Spec.md's Key Entities section
defines the concept; the table below is every instance, with the fields the
implementation needs.

| # | Workflow | Job | Step (`name`) | Step `id` | Scratch filename | Guidance today |
|---|---|---|---|---|---|---|
| 1 | `plan.yml` | `plan` | Generate implementation plan (direct commit) | `agent-auto` | `plan-commit-message-direct.txt` | none |
| 2 | `plan.yml` | `plan` | Generate implementation plan | `agent-pr` | `plan-commit-message-pr.txt` | none |
| 3 | `tasks.yml` | `tasks` | Generate task list (direct commit) | (matches `agent-auto`-equivalent id in tasks.yml) | `tasks-commit-message-direct.txt` | none |
| 4 | `tasks.yml` | `tasks` | Generate task list (review PR) | (matches `agent-pr`-equivalent id in tasks.yml) | `tasks-commit-message-pr.txt` | none |
| 5 | `board-loop.yml` | `fix` | Fixer | `fixer` | `board-loop-commit-message-fixer.txt` | none |
| 6 | `board-loop.yml` | `review` | Review-fixup | `review-fixup` | `board-loop-commit-message-review-fixup.txt` | none |
| 7 | `pr-conversation.yml` | `act` | Act on this classification | `agent` | `pr-conversation-commit-message-fold.txt` | none |
| 8 | `implement.yml` | `implement` | Implement and converge (cycle) | `cycle` | `implement-commit-message-cycle.txt` (unchanged, #440) | hand-written paragraph → converted to render |
| 9 | `implement.yml` | `implement` | Implement and converge (retry at escalation model) | `retry` | `implement-commit-message-retry.txt` (unchanged, #440) | hand-written paragraph → converted to render, keeps its addendum sentence (D4) |

Exact step ids for rows 3–4 are confirmed against the live `tasks.yml`
during task execution — this table names them by their `plan.yml` analogues
because `tasks.yml` mirrors `plan.yml`'s two-mode structure exactly (auto /
PR), but the literal `id:` strings are read from the file, not guessed, per
the constitution's "run the same subject" gate discipline.

**Attributes each row must satisfy after this change** (FR-001–FR-006,
FR-009):
- The step (or a step immediately preceding it in the same job) invokes
  `wing-commander-commit-message-guidance` with `scratch-filename` set to
  that row's filename, under a step id unique within the job.
- The `prompt:` string interpolates that step's `guidance` output at the
  point the existing commit instruction lives (appended to the existing
  numbered step for rows 1–4, appended to the existing commit sentence for
  rows 5–7, replacing the hand-written paragraph in place for rows 8–9).
- No two rows in the same job share a scratch filename (trivially true here
  since every row's filename is already unique — see research.md D2).

## Entity: Commit-message scratch file

A run-scoped file outside the checkout, named by an agent-prompt-site row
above, written by the `Write` tool, read once by `git commit -F`, never
`git add`ed.

| Field | Value |
|---|---|
| Path | `${{ runner.temp }}/<scratch-filename>` (row's filename above) |
| Written by | The agent, via the `Write` tool — never a shell heredoc/`$(cat ...)` (FR-004) |
| Read by | `git commit -F <path>`, issued by the same agent in the same turn or a later one in the same job |
| Lifecycle | Job-scoped; not required to survive the job; overwritten (not appended to) on a repeated commit at the same site (spec.md Edge Cases: "Repeated commits at one site") |
| Must never appear in | The commit's file list, `git status --porcelain` output, or any path under the repository working tree or `.git/` (FR-003, User Story 2) |

## Entity: Canonical guidance source

Implemented as `.github/actions/wing-commander-commit-message-guidance/action.yml`
(research.md D1).

**Inputs**:
| Name | Required | Description |
|---|---|---|
| `scratch-filename` | yes | The literal filename (no path) this site's scratch file uses, e.g. `plan-commit-message-direct.txt`. The action prefixes `${{ runner.temp }}/` itself so no call site hand-assembles the path. |
| `extra-note` | no (default `""`) | An optional site-specific sentence appended after the canonical paragraph verbatim. Only `implement.yml`'s retry site sets this (D4). |

**Output**:
| Name | Description |
|---|---|
| `guidance` | The complete rendered paragraph: what to do (Write to the named path, `git commit -F` from it), what is refused and why (heredoc, `$(cat ...)`, any path under the repository — FR-004), and the condition under which this applies (message longer than one line — FR-005), followed by `extra-note` if non-empty. |

**Invariants** (checked by the new gate, see below):
- The rendered text is byte-identical across every call site except for the
  substituted filename (and, at the one site that sets it, the trailing
  `extra-note`) — FR-009's "same meaning, same named forms."
- The action's own `run:` step is the only place this prose is written;
  no call site carries a hand-typed copy after this change (FR-011, SC-009).

## Entity: Exemption list

A Python literal (`EXEMPT_SITES`) inside `.github/scripts/verify-commit-
message-scratch-path.py`, matching `verify-rate-limited-exemption.py`'s
existing `EXEMPT_SITES` pattern: a set of `(workflow file basename, step
name)` tuples, each preceded by a comment stating why that site's commits
are always deterministic one-liners.

Ships **empty** at the end of this feature (research.md D6) — every
discovered site is a covered site. The structure exists so a future
genuinely-one-liner-only site has a recorded home (SC-008) rather than
forcing a false render or silently escaping the gate's discovery.
