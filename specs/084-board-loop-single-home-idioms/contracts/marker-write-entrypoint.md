# Contract: FR-001 through FR-005a — the marker-write CLI entrypoint

research.md D2/D3 explain why a command-line entrypoint (never a
composite) and how the two `board_eligibility` constants are resolved
without a second literal copy.

## `.github/scripts/board_item_marker.py` (gains a CLI; `write_marker`
unchanged)

**What's new**: a `main()` function and an `if __name__ == "__main__":`
guard. `write_marker(step, round, pr, branch, base_sha)` (line 110) is not
modified — FR-005 forbids changing rendered output, and the CLI is a thin
wrapper.

**CLI shape**:

```
python3 [-I] <scripts-dir>/board_item_marker.py \
  --step STEP [--round N] [--pr NUM] [--branch REF] [--base-sha SHA]
```

- `--step` (required): a literal step string (`stalled`, `review`,
  `readiness`, `proven`, `prove`, ...), or one of the two symbolic tokens
  `BREACH_STEP` / `AWAITING_MERGE_STEP`. A token is resolved by importing
  `board_eligibility.BREACH_STEP` / `.AWAITING_MERGE_STEP` inside the
  entrypoint — never by hardcoding the literal `"breach"` /
  `"awaiting-merge"` string in the caller's YAML (research.md D3).
- `--round` (optional, `type=int`, default `0`).
- `--pr` (optional, parsed with `int()` when present; omitted → `None`).
- `--branch`, `--base-sha` (optional strings; omitted → `None`).
- Absent-vs-empty (FR-004): an omitted flag is `None` (renders JSON
  `null`); an explicitly empty value (`--branch ""`) is `""`. `argparse`'s
  own default mechanism provides this distinction with no extra sentinel
  logic.
- Output: `print(write_marker(_resolve_step(step), round, pr, branch,
  base_sha))` to stdout — byte-identical to every current inline
  `python3 -c "...; print(write_marker(...))"` call (FR-003). Callers
  keep capturing it with `marker="$(python3 ... --step ...)"`, unchanged.

**Call-site spellings** (both already permitted by Gate 98's
`ALLOWED_PYTHON_ARGS_RE`, verified against the regex, no Gate 98 source
change required):

- Working tree (triage, route, prove — 6 sites):
  `python3 .github/scripts/board_item_marker.py --step ... [--round ...] [--pr ...] [--branch ...] [--base-sha ...]`
- Pristine snapshot (fix, review, readiness — 11 sites):
  `python3 -I "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py" --step ... [--round ...] [--pr ...] [--branch ...] [--base-sha ...]`

Every argument value that today comes from a shell variable
(`$PR_NUMBER`, `$BRANCH`, `$BASE_SHA`, `$NEXT_ROUND`) is passed the same
way, quoted, as a CLI flag value — no new environment variable is
introduced.

**Byte-identity obligation (FR-003)**: for each of the 17 existing call
sites (research.md's precedent report enumerates job, step, and exact
arguments for all 17), the new CLI invocation with equivalent flags MUST
produce output identical to the inline call it replaces. This is a
per-site regression check the implementation phase runs against the 17
argument combinations, not a new automated gate — `write_marker`'s body is
unchanged, so identity follows from correct argument translation.

**Not covered by this entrypoint**: `board-loop.yml`'s `select` job
resume step (`:432-444`) reads a marker via `read_marker`, in its own
`python3 - <<'PYEOF'` heredoc spelling — a distinct idiom (read, not
write) that this feature does not touch.

## Wiring

No workflow-registration change: the entrypoint is a script under
`.github/scripts/`, invoked directly from `run:` blocks in
`board-loop.yml`; it is not itself a `verify-*` gate and carries no
separate CI step. `board_eligibility.py` remains the one home for
`BREACH_STEP`/`AWAITING_MERGE_STEP`'s values (research.md D3).
