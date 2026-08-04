# Contract: Excluded-Comments Notice Callout (FR-008)

A new callout point, additive to the table `specs/019-next-step-callouts/
contracts/callout-points.md` established for `intake.yml` (rows 1–2 there
cover the existing clarification-needed / spec-ready outcomes). This row is
independent of those two — it is about comment-trust legibility, not spec
completeness — and its condition is knowable before the agent step even
runs.

## Condition (deterministic — research.md D4)

```
notice_needed := (qualifying-count == 0) AND (excluded-human-count > 0)
```

Both values come from `contracts/comment-trust-gate.md`'s step outputs.
Evaluated in a plain `if:` on the callout step — never decided by the
agent.

| Scenario | `qualifying-count` | `excluded-human-count` | Notice? |
|---|---|---|---|
| No comments at all | 0 | 0 | No (FR-007 — silent, body-only) |
| Only bot comments | 0 | 0 | No (Edge Cases — silent, body-only; research.md D4) |
| Mixed: some qualify, some don't | >0 | any | No (qualifying comments were used; Edge Cases' "mixed authorship" case has no notice) |
| All comments present, human, none qualify | 0 | >0 | **Yes** |

## Placement

Posted by a new step immediately after the comment-trust-gate step
(`contracts/comment-trust-gate.md`), gated on
`steps.lifecycle-gate.outputs.is-open == 'true'` and the condition above —
**before** the agent step runs, since the condition needs nothing the
agent produces. This is deliberately earlier than intake's other two
callouts (posted after the agent completes and spec.md's clarification
state is known): a maintainer who applied the label to a well-discussed
issue should learn immediately that the discussion wasn't actually usable,
without waiting for the full spec-drafting run to finish.

## Invocation (via the existing `wing-commander-callout` composite action)

```yaml
kind: action
summary: "Confirm the issue body reflects the discussion before relying on this spec"
body: >
  <excluded-human-count> comment(s) on this issue did not qualify for
  the specification (not from a maintainer or the original reporter) and
  were not used. If the discussion actually settled something the body
  doesn't capture, update the body before this spec is finalized.
```

- `summary` states the action in plain language (matching
  `contracts/callout-points.md`'s existing clause: "a plain-language
  statement of the action, not a status label").
- No `pr-url` — this notice can fire before any spec PR exists (e.g. the
  request itself turns out undiscernible and intake stops early per its
  existing step 2); it is about the input to specification, not its output.
- `excluded-human-count` is safe to interpolate directly (an integer count,
  not comment content).

## Non-goals

This callout never names *which* comments or *who* authored them — doing so
would require surfacing the very content the trust gate exists to keep out
of the maintainer-approved surface, and isn't needed to convey the
actionable fact (some discussion existed and wasn't used).
