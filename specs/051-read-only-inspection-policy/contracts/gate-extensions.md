# Contract: Gate 27 and Gate 21 extensions

FR-014/FR-015/SC-003 require the policy to be enforced, not just written
down, and require the enforcement to land in the nearest existing gate. This
contract fixes the shape of both extensions so tasks.md implements against a
decided interface rather than reopening the design.

## Gate 27 (`verify-stage-tool-lists.py`) — two new checks

Both checks run inside the existing `run(root)` function, after the current
`compare(sites, table, relative)` call, appending to the same failures list
the script already returns. Both follow the file's existing style: a
hand-authored constant near the top of the module (next to `TABLE_DOC`,
`WORKFLOW_DIR`, `COMPOSITE`), a pure function taking the already-parsed
`sites`/`table` dicts, and a self-test mutation for each new failure mode.

### Check A — inspection-set completeness

```python
INSPECTION_SET = {
    "Bash(grep:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(sort:*)",
    "Bash(uniq:*)", "Bash(wc:*)", "Bash(cut:*)",
}

READ_CAPABLE_LABELS = {
    "intake", "clarify",
    "plan.direct-commit", "plan.pr",
    "tasks.direct-commit", "tasks.pr",
    "implement.cycle", "implement.retry",
}
```

`check_inspection_set(table)` iterates `READ_CAPABLE_LABELS`, and for each
label present in `table`, computes `INSPECTION_SET - set(table[label][0])`
(the allowed-tools cell already resolved by `parse_table`). A non-empty
difference is a failure naming the label and the missing primitive(s) —
"`<label>`'s default allowed list omits `<primitive>` from the read-only
inspection set (specs/010-reusable-pipeline/contracts/stage-interfaces.md's
policy section) and records no exception." A `READ_CAPABLE_LABELS` entry
absent from `table` is not a Check-A failure — the existing comparison
already reports a missing row as its own failure, so Check A only evaluates
labels the base comparison already confirmed exist.

**Exception path**: none exists in this feature — every read-capable row
gains the full set (data-model.md item 2's row list). The check is written
to support a future exception (a documented row-level note the check treats
as satisfying the requirement) without failing today, per FR-003's "or
record in its table row why it does not," but this feature's own tasks.md
work does not need to exercise that path since it leaves no row short.

**Self-test mutations** (added to `_mutations()`):
- Drop one primitive from a read-capable row (`plan.direct-commit` loses
  `Bash(cut:*)`) → expect the "omits `Bash(cut:*)`" failure.
- Drop one primitive from a non-read-capable row (`finalize` loses nothing
  relevant — `finalize` is never in `READ_CAPABLE_LABELS`, so no primitive
  removal there should ever trigger Check A) → the mutation instead proves
  the negative: no failure is raised for a deliberately-minimal row missing
  the whole set, confirming Check A does not apply the set universally.

### Check B — repository-guidance reconciliation

```python
MANDATED_COMMANDS = {
    "Bash(python .github/scripts/run-local-gates.py:*)": {
        "implement.cycle", "implement.retry",
    },
}
```

`check_mandated_commands(table)` iterates `MANDATED_COMMANDS.items()`, and
for each `(command, required_labels)`, checks that every label in
`required_labels` present in `table` has `command` in its allowed-tools
cell. A missing grant is a failure naming the label and the command —
"`<label>` is told by CLAUDE.md/its own prompt to run `<command>` but its
default allowed list does not permit it (FR-010)." This is the FR-010
reconciliation made mechanical: `MANDATED_COMMANDS` is this gate's
authoritative record of "what repository guidance mandates," maintained by
hand alongside `CLAUDE.md` edits (the same way `TABLE_DOC`'s path is a hand-
maintained constant), per research.md D7's reasoning that this judgment
belongs in reviewable code, not a prose-parser.

**Self-test mutation** (added to `_mutations()`): remove the gate-suite
command from `implement.cycle`'s table row → expect the "is told by
CLAUDE.md... but its default allowed list does not permit it" failure.

### `--self-test` wiring

Both checks' failure functions are called from `self_test()` the same way
`compare()` already is: once against the real, unmutated table (must be
clean), then once per mutation (must fail for the expected reason). No
change to the script's CLI surface (`--self-test`, `--root`) or its exit-code
contract (0 clean, 1 with failures).

## Gate 21 (`verify-tooling-statement.py`) — one new case, one new mutation

The action's shipped `Compose tool args` step gains D3's appended sentence
(a literal string constant in the `run:` block, appended to `shell_commands`
right before the `echo "shell-commands=$shell_commands"` emission — after
every existing branch of the if/else that sets `shell_commands`, so it
applies uniformly to all of them, including the "no shell command" case).

```python
STATIC_SUFFIX = (
    " Each command in a pipeline or `;`/`&&` chain is checked separately, "
    "and a `>`/`>>` redirect or a `cd … &&` prefix is denied regardless of "
    "this list — use the Read/Grep/Glob tools, or a single command, for "
    "anything multi-step."
)
```

Every existing `expect(...)` call in `CASES` gets `STATIC_SUFFIX` appended
to its `want_shell_commands` argument (twelve call-site edits, mechanical).
One new mutation is added to `MUTATIONS`:

```python
("reverts the appended compound-command guidance (D3)",
 lambda s: s.replace(STATIC_SUFFIX_LITERAL_IN_SCRIPT, "")),
```

removing the suffix from the shipped script, asserted (by the existing
mutation-loop machinery) to turn every one of the twelve cases red — this
is a stronger assertion than the file's other three mutations, each of which
only needs to turn *some* case red, but is achievable here because the
suffix is unconditional and every case's expected string ends with it.

No change to `verify-tooling-statement.py`'s `expect()` helper, `run_suite()`,
or `main()` — only `CASES`' expected strings and one `MUTATIONS` entry.
