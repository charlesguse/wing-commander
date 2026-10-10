---
name: "whats-on-me"
description: "Answer 'what's on me?' or 'is this still the lay of the land?' with a short, fresh report of what waits on the owner, what is moving without them, and what needs nothing, built from a live render of the Board status report plus what only this session knows. Use when the owner asks what needs them, comes back after a gap, or before a long session hands off."
compatibility: "Needs gh authenticated for this repository, and python3"
user-invocable: true
disable-model-invocation: false
---

# What's on the owner right now

## Why this exists

The owner asks this after a gap ("coming back to this a few days later, is
this still the lay of the land?") or mid-session ("what's on me at this
point?"). The answer has to be:

- **fresh:** the board moves without you. Merges land, stages advance and
  the bot asks new questions, so an answer from session memory is a
  guess;
- **short:** it is read on a phone;
- **filtered:** a question the project already answered is not on the
  owner.

## Procedure

**1. Render the board now, not from memory.**

```
python3 .claude/skills/whats-on-me/scripts/board_now.py
```

This prints the Board status report from a fresh snapshot. It uses
`wc_board_status.py`'s own `snapshot()` and `render()`, the one home of
what that report reads, and publishes nothing. The report covers:

- main's CI, the last release, and the board loop and auto-merge switches;
- **Waiting on you;**
- **In the pipeline;**
- the Maintenance backlog's size;
- other open issues and open PRs.

If gh can't read the board, fall back to the "Board status" issue itself
(open, `disposition:tracking`) and say how old its "Updated" line is.

**2. Add what the board can't show.**

- **Roadmap (#890):** the Proposed list, "Owner decisions", and In
  flight / Queued against the three-in-implement limit.
- **Open PRs:** CI on each head, and whether each needs a human merge:
  - spec PRs, plan PRs and amendments always do (constitution V);
  - a PR touching `.github/workflows/` does when the token lacks the
    `workflow` scope.
- **This session's own state:**
  - questions asked in chat and not yet answered;
  - agents still running and PRs mid-review;
  - promised follow-ups ("I'll re-drive after merge");
  - scheduled check-ins and triggers (`list_triggers`).

**3. Take settled questions out.** Before an item goes under "Needs you",
run the `answer-from-precedent` skill on it. A question with a matching
precedent is answered (or offered as answerable), not listed as the
owner's.

**4. Sort and write it.** Most important first; one line per item, with a
link, the action it needs, a recommendation where there is a choice, and
its age.

- **Needs you to move.** Only the owner can do these:
  - merge a spec PR, a plan PR or an amendment;
  - apply `spec-request`;
  - answer an open question that has no precedent;
  - merge a workflow-touching PR GitHub refused for scope;
  - set a variable, secret or App permission;
  - make a decision.
- **Quick cleanups.** A minute of the owner's time, or say "want me to?"
  and do it on a yes.
- **Older decisions still waiting.** Oldest first, with how long each has
  waited.
- **Moving without you.** What the pipeline and this session are doing,
  and when the next check-in is.
- **Nothing needed.** One line, so the owner knows the rest was looked
  at.

Keep each bucket short enough to read on a phone. If "Needs you" is empty,
say so first.

## Reporting

The five buckets above, in that order, in chat. Offer to publish them as a
page only when the report is long or the owner will share it.
