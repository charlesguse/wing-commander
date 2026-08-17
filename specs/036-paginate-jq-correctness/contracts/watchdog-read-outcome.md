# Contract: `watchdog.yml`'s Per-Collector Read Outcome

`watchdog.yml` is a published `workflow_call` stage (constitution VII) —
this is the one adopter-visible surface this feature touches, and it is a
strict, additive widening: no existing input, secret, or output is
removed, renamed, or changes meaning (FR-015).

## What's new on the `collect` job

A new job output, alongside the existing `evidence-available`, `signals`,
`collectors-failed`, and the others already declared at `watchdog.yml:227-234`:

```yaml
outputs:
  # ...existing outputs, unchanged...
  untrusted-collectors: ${{ steps.aggregate.outputs.untrusted-collectors }}
```

**Shape**: a JSON array of strings, each one of the five collector step
ids (`collect-execution-output`, `collect-branch-drift`,
`collect-spec-meta`, `collect-step-summary`, `collect-annotations`).
`[]` when every collector's underlying reads all succeeded this run —
which is every run today, so this output is `[]` for every historical
run and FR-005/SC-007's "identical outcome below the page boundary" holds
trivially for it.

**Relationship to the existing `collectors-failed` output**: `collectors-failed`
(an integer, `watchdog.yml:853`) already counts collector *steps* whose
shell exited non-zero — a different, coarser signal that today almost
never fires for a `gh api` read failure specifically, because the
existing `2>/dev/null || echo '<empty>'` fallback makes the step's shell
exit 0 regardless of whether the underlying read succeeded. `untrusted-collectors`
does not replace `collectors-failed`; it adds the finer-grained,
read-level distinction FR-010 requires. A collector can appear in
`untrusted-collectors` while its step's own exit code is still 0 (that is
precisely the case this feature makes visible for the first time).

## What's new for the `diagnose` job

The `diagnose` job already materializes `needs.collect.outputs.signals`
into `${{ runner.temp }}/watchdog-signals.json` before the agent step runs
(`watchdog.yml:976-982`). This feature adds one sibling file, written the
same way from the new output:

```yaml
- name: Write untrusted-collectors file
  env:
    UNTRUSTED: ${{ needs.collect.outputs.untrusted-collectors }}
  run: printf '%s' "$UNTRUSTED" > "${{ runner.temp }}/watchdog-untrusted-collectors.json"
```

The diagnose agent's prompt (`watchdog.yml:~1122` onward) gains one
additional instruction: read this file (same untrusted-data framing
convention already applied to `watchdog-signals.json`, FR-023) and, when
it names one or more collectors, state in the verdict which kinds of
evidence could not be gathered this run — **not** to reweigh or discard
any signal that *did* arrive (Out of Scope: "any change to the watchdog's
diagnostic reasoning" is explicitly excluded from this feature; the only
new input is trustworthiness metadata, not a new reasoning rule).

## Non-goals this contract deliberately excludes

- No retry, backoff, or recovery from a failed read (Out of Scope).
- No change to `evidence-available`'s existing all-five-failed threshold
  (`watchdog.yml:854`) or the "could not inspect this run" comment path —
  that path is for total failure; `untrusted-collectors` covers the new
  partial-failure case where the run still reaches a verdict (User Story 5,
  Acceptance Scenario 3).
- No change to any *other* published stage's contract. Only `watchdog.yml`
  is touched.

## Backward compatibility

An adopter's wrapper workflow that calls `watchdog.yml` and does not read
`untrusted-collectors` is unaffected — GitHub Actions ignores job outputs a
caller doesn't reference. No existing output's type or meaning changes, so
no consumer of `signals`, `evidence-available`, or `collectors-failed`
needs to change.
