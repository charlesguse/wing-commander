# Contract: The Run Stamp

This is the design source for FR-013's "documented once" requirement —
the canonical prose lives, at implementation time, in a
`(canonical copy, do not condense)`-marked comment inside
`.github/actions/wing-commander-metrics-summary/action.yml` next to the
`run-stamp` step this contract describes; every other reference (the 12
stage-workflow call sites, the watchdog collector, this repository's other
docs) points at that comment via `-- see wing-commander-metrics-summary/action.yml`,
checked by Gate 47 (`verify-comment-canonical-pointers.py`).

## Shape

```text
<!-- wing-commander-cost-stamp:<workflow_run_id>:<run_attempt>:<job_key-or-job_id>:<step_index> -->
```

An HTML comment. The four colon-delimited fields are exactly the widened
metrics record key (`data-model.md`'s "Metrics record key" entity) — the
stamp carries that key and nothing else. `workflow_run_id` and
`run_attempt` together are the **run-identity portion**: the first two
fields, always numeric, always present.

## Single home

Computed by exactly one step: `wing-commander-metrics-summary/action.yml`'s
`run-stamp` step (`id: run-stamp`), the first step the composite runs,
built from the same four ambient values (`github.run_id`,
`github.run_attempt`, `github.job`, the `step-index` input) `RECORD_KEY`
is built from. No other file constructs this string. Two things read the
resulting value without reformatting it:

1. The composite's own `cost-line` output appends it as the final
   concatenation term of the cost-line jq pipeline — every consumer of
   `cost-line` inherits the stamp with no call-site change (FR-003).
2. The composite additionally exposes it standalone as the `stamp`
   output, consumed by exactly one more line in each of the 12 stage
   call sites' degraded literal fallback (`[ -n "$line" ] || line="**Cost**:
   metrics unavailable $RUN_STAMP"`) — see `cost-attribution.md`'s sibling
   note and `research.md` R3.

**Enforcement**: `verify-metrics-summary-record-emission.py`'s
`case_run_stamp_has_exactly_one_home` (sibling to the existing
`case_cost_line_formatter_has_exactly_one_home`) scans every workflow file
and every `.github/actions/**` file outside the canonical action for a
*construction* of the marker prefix — a `wing-commander-cost-stamp:`
occurrence not immediately adjacent to a `steps.*.outputs.stamp` /
`$RUN_STAMP` reference. A literal reconstruction fails the gate; a
consumption of the already-computed output passes it.

## Invisibility

An HTML comment renders as nothing in GitHub's Markdown — issue comments,
PR comments, step summaries alike. This is the same rendering guarantee
the existing rollup marker
(`<!-- wing-commander-metrics-rollup:begin -->`,
`wing-commander-metrics-persist/action.yml`) already relies on. No
existing byte-comparing gate over a *rendered* comment's human-visible
text is affected; a gate that byte-compares the *raw* body of a
cost-bearing comment (if any exists) needs its fixture updated to include
the trailing stamp — flagged here as an implementation-time audit, not
resolved by this plan (Constraints).

## What it is not

- Not a token, not a credential, not a network-fetched value — pure
  string interpolation of already-ambient GitHub Actions context.
- Not extended to any comment without a cost line (Out of Scope).
- Not back-filled onto comments posted before this feature ships (Out of
  Scope) — a pre-stamp comment simply has no marker to parse, and is
  treated as unstamped (`cost-attribution.md`).
- Not trusted on its own — a comment's stamp is only believed when the
  comment was also authored by one of the pipeline's own identities
  (FR-007, unchanged); the stamp narrows the existing author filter, it
  does not replace it.
