# Drafted report to anthropics/claude-code-action

**Status**: Drafted as part of `specs/037-agent-turn-budget-guard`
(this repository's issue #206), per that feature's FR-018/SC-010. Filing
this upstream is optional and at the maintainers' discretion — this
document's presence in the repository is what satisfies the feature,
independent of whether it is ever filed. If filed, it should be opened
against `anthropics/claude-code-action` referencing the change described
below.

---

## Title (suggested)

`num_turns` in the terminal result is not the counter `--max-turns`
enforces, and comparing them post-hoc fails healthy runs

## Summary

`base-action/src/run-claude-sdk.ts` throws when:

```
resultMessage.subtype == "success" && !resultMessage.is_error
  && sdkOptions.maxTurns !== undefined
  && resultMessage.num_turns > sdkOptions.maxTurns
```

This was added 2026-08-07 in #1607 ("fix: enforce max turns from claude
args"). The intent — stop a run that exceeded its configured turn budget
— is reasonable, but the comparison is between two different counters:

- `--max-turns` cuts a run off after N distinct **main-loop** assistant
  API responses (by `.message.id`, excluding any response whose
  `parent_tool_use_id` is set — i.e. excluding subagent/Task-tool
  activity). Every genuinely turn-exhausted run in our history stops at
  exactly the configured cap when counted this way.
- `resultMessage.num_turns` is a larger, differently-defined total. Against
  the same runs, it reads 1.0x-2.3x higher than the counter `--max-turns`
  actually enforces, always upward, never below it.

Because the post-hoc check compares `num_turns` (the inflated counter)
against `maxTurns` (the value that caps the other counter), a run that
never came close to its real turn budget can still throw — after every
side effect the agent already committed (file edits, commits, pushes, PR
updates), since the check runs on the terminal result message, post-hoc.
There is no opt-out short of omitting `--max-turns` entirely, which
removes the real safety cap along with the false positive.

## Evidence (two independent occurrences, 31 hours apart)

**Occurrence 1** — an internal automation cycle (this repository's own
CI, 2026-08-06) rendered "198 / 100 turns (198%)" and a spurious
turn-budget warning for a run that used 87 of its 100 real (counted)
turns. This was diagnosed and worked around locally by doubling the
`--max-turns` value passed to the action for that one call site
(15 → 30, an unrelated site in the same family), which made the false
positive stop recurring *for that site only*.

**Occurrence 2** — run 31918153816 (this repository's `clarify` stage,
lifecycle issue #204, step "Fold answers into the draft spec"), 31 hours
after occurrence 1's local fix. Terminal result: `subtype: "success"`,
`is_error: false`, valid structured output (`{"answered": true,
"clarifications": []}`), cost $1.98. Counted (main-loop, our own
measurement): 36 of a configured 40 (90%). Reported: `num_turns: 47`
(1.31x the counted total, and above the 40 cap). The action failed the
step with: `Claude reported a successful result after 47 turns,
exceeding the configured maximum of 40`. By the time this fired, the
agent had already committed and pushed its changes and rewritten the
target pull request's body — none of that was undone or affected; only
the calling workflow's own downstream steps (which gated on this step's
reported outcome) were skipped, including the one that would have
notified our lifecycle-tracking issue that the work was ready for
review.

## Divergence sample

| Case | Counted (main-loop, distinct `.message.id`, no subagent) | Reported (`num_turns`) | Ratio |
|---|---|---|---|
| 2026-08-06 internal cycle | 87 | 198 | 2.28x |
| Run 31918153816 (`clarify`, #204) | 36 | 47 | 1.31x |
| Every genuinely turn-exhausted run we've observed | = configured cap, exactly | cap or above | 1.0x-2.3x |

## Suggested fix(es)

Any of the following would resolve this from our side without requiring
us to maintain a local workaround:

1. Compare `--max-turns` against the same counter it enforces, not
   `num_turns` — i.e. count distinct main-loop assistant responses
   internally the same way the enforcement path already must (since it
   is what actually cuts a run off at the cap), and use that count for
   both enforcement and the post-hoc success-path comparison.
2. Alternatively, expose the counted total the enforcement path already
   computes as its own field on the result message (e.g.
   `main_loop_turns`), distinct from `num_turns`, and only compare
   `--max-turns` against that new field — leaving `num_turns` as a
   larger, documented-as-different total for callers who want it for
   other purposes.
3. At minimum, document that `num_turns` and `--max-turns` are different
   counters and are not meant to be compared, so a caller (like us)
   knows not to rely on the post-hoc check's pass/fail as a proxy for
   "did this run stay within the turn budget I configured."

## What we did locally, in the meantime

We built our own transcript-derived turn count (same rule as above:
distinct `.message.id` on `type: "assistant"` records with no
`parent_tool_use_id`) and a shared "agent run verdict" step that
distinguishes this post-hoc rejection (terminal result healthy, just an
inflated-counter throw) from a genuine failure, and continues our
pipeline in the former case rather than treating it as a real failure.
We also widened the literal `--max-turns` value we hand the action to
`2.5x` our actual intended budget, sized from the 1.0x-2.3x divergence
sample above, so the flag still functions as a real (if now-inflated)
runaway ceiling rather than being removed. Both are workarounds for the
comparison described above, not fixes to it — we'd rather not need
either.
