# Data Model: A never-unblocking merge gate is named

Like spec 055's own data model, this feature has no application database —
every entity below is either state read live from the test repository (PR
data) or in-memory bash state scoped to one `poll` step invocation. This
document extends spec 055's data model
(`specs/055-unattended-e2e-gates/data-model.md`) rather than replacing it:
every entity spec 055 already defined keeps its shape; this feature adds one
new per-gate entity (Gate waiting state, already named in spec.md's Key
Entities) and one new reason within the existing verdict shape.

## Merge gate (unchanged from spec 055)

Reuses spec 055's Lifecycle gate table exactly — the three PR-merge gates
(spec-draft, plan, finalize), each with the name already used in verdict
evidence, an expected head branch (`<prefix><slug>`), and an expected base
branch (`gate_expected_base`, `auto-release.yml:979`). This feature adds no
new gate and renames none.

## Gate waiting state (NEW — per merge gate, per attempt)

| Field | Type | Source | Lifetime |
|---|---|---|---|
| `blocked_since` | integer seconds (as `$SECONDS`), or empty string | Set by the `poll` step from the allowance-decision script's `start` answer (research.md D2/D3); cleared by its `clear` answer | One attempt; discarded when the attempt ends, exactly like `gate_failures`/`gate_last_failure` |
| last evidence observed | the PR number and merge-decision token from the most recent successful read for this gate | Already exists implicitly via `$pr_number`/`$merge_decision` at each loop iteration; not separately persisted, since the verdict write happens in the same iteration that decides `stall` | One loop iteration |

Represented in `auto-release.yml` as `declare -A gate_blocked_since=([spec-draft/]="" [plan/]="" [spec/]="")`, parallel to the existing `gate_merged`/`gate_name`/`gate_failures`/`gate_last_failure` arrays (`auto-release.yml:866-869`).

**State transitions** (driven once per gate per loop iteration, only after a successful PR-list read and merge-decision call — a failed read never reaches this logic, satisfying FR-006):

```
                merge-decision token this iteration
                            |
        +-------------------+-------------------+
        |                                        |
  == "blocked-pending"                    != "blocked-pending"
        |                                        |
        v                                        v
  blocked_since empty?                    allowance script -> "clear"
   /            \                          blocked_since := ""
 yes            no
  |              |
  v              v
start          elapsed = SECONDS - blocked_since
blocked_since       |
:= SECONDS      elapsed >= allowance?
  |              /          \
  v            yes           no
(keep waiting)  |             |
                v             v
             stall          wait
    (write fail-gate-stall) (keep waiting,
                              blocked_since unchanged)
```

This transition table is exactly what
`auto-release-e2e-gate-allowance-decision.sh` (contracts/gate-allowance-decision.md) computes, given `(merge_decision, blocked_since, now, allowance)`.

**Invariants** (from spec.md's Edge Cases and Functional Requirements):
- A gate that alternates between "nothing resolved" and "something still
  running" across observations never resets `blocked_since`, because both
  shapes are already collapsed into the single `blocked-pending` token by
  the merge-decision script (D1) before the allowance script ever sees
  them — the allowance script has no visibility into rollup *shape* at all,
  only the token and the clock (FR-005).
- Only one gate's stall can be reported per attempt: the `poll` step's
  existing `for prefix in "spec-draft/" "plan/" "spec/"` loop
  (`auto-release.yml:980`) processes gates in a fixed order and `exit 0`s
  immediately on the first `stall`, exactly as it already does for
  `conflicting`/`blocked`/`wrong-attempt`/`wrong-base` — no change to that
  control flow is needed for this invariant to hold.
- The 20-minute allowance is bounded by, and much smaller than, the
  135-minute poll budget (FR-004): 1200s vs 8100s, leaving ~6900s (115
  minutes) even for a gate blocked-pending from the attempt's very first
  observation.

## Merge-decision script output vocabulary (AMENDED)

`auto-release-e2e-merge-decision.sh` prints one of: `none` / `wrong-attempt`
/ `wrong-base` / `wait` / `conflicting` / `blocked` / **`blocked-pending`
(NEW)** / `merge\n<number>`. Every value except `blocked-pending` is
unchanged in meaning from spec 055 (`contracts/gate-decision-scripts.md`
step-by-step logic, quoted in this feature's own
`contracts/gate-allowance-decision.md`). `blocked-pending` replaces exactly
the sub-case of `wait` that spec 055's own comments already call out as "a
freshly opened PR under required checks... indistinguishable, from this
data alone, from a genuinely misconfigured required check that will never
report" (`auto-release-e2e-merge-decision.sh:96-104`) — this feature is
what makes that distinction observable over time, via the new allowance
script, rather than at the level of a single snapshot.

## Allowance-decision script I/O (NEW)

**Input** (`contracts/gate-allowance-decision.md` has the full contract):
`merge_decision` (the token the merge-decision script just printed),
`blocked_since` (empty or a `$SECONDS` integer), `now` (`$SECONDS`),
`allowance_seconds` (1200, from the new `GATE_BLOCKED_ALLOWANCE_SECONDS` env
constant).

**Output**: one of `clear` / `start` / `wait` / `stall`.

## End-to-end verdict (extends spec 055's shape — same six fields, no new `outcome` value, one new reason)

```jsonc
{
  "outcome": "pass" | "fail-infra" | "fail-timeout" | "fail-incomplete"
           | "fail-wrong-output" | "fail-gate-stall",
  "verified_head": "<head_sha>",
  "failing_check": "<string, e.g. 'spec-draft PR merge'>",
  "expected": "<string, null on pass>",
  "observed": "<string, null on pass>",
  "evidence_url": "<link to the test repository's lifecycle issue>"
}
```

- `outcome` gains no new value — `fail-gate-stall` already exists (spec
  055). This feature adds a fifth trigger for it (research.md D4):

| Trigger | `outcome` | `failing_check` | `expected` | `observed` |
|---|---|---|---|---|
| Merge decision = `blocked-pending` for `GATE_BLOCKED_ALLOWANCE_SECONDS` (1200s) continuously | `fail-gate-stall` | `"<gate name>"` | `"gh pr merge succeeds"` | `"PR #<n>: required checks never reported a result"` |

  This row sits directly beside spec 055's existing five rows in
  `specs/055-unattended-e2e-gates/contracts/verdict-extension.md`'s table
  (unedited by this feature, since edits to spec 055's directory are out of
  scope here) — `contracts/gate-allowance-decision.md` in this feature's
  own directory is the authoritative statement of this new row.
- `pass` and every existing `fail-*` trigger are unchanged (FR-007, SC-003).

## Failure report classification (unchanged — spec 055's three-way split already covers this)

| `outcome` | Classification shown in the durable `auto-release:failed` issue |
|---|---|
| `fail-infra` | "infrastructure" (unchanged) |
| `fail-gate-stall` | "gate stall" (unchanged mapping; this feature's new reason is one more `fail-gate-stall` trigger, not a new classification) |
| every other `fail-*` | "pipeline defect" (unchanged) |

No code change is needed at the classification `case` (`auto-release.yml:1790-1794`) — it already maps every `fail-gate-stall` outcome to "gate stall" regardless of reason, which is exactly what FR-008 requires.
