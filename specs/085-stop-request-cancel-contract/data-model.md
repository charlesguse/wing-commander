# Phase 1 Data Model: The Stop Decision Answers Both Questions

This feature has no persisted storage and no database-style entities; its
"data model" is the shape of the values that cross the two interfaces this
plan touches — the Python function/CLI boundary and the composite's shell
boundary. Each entity below names its fields, invariants, and where it is
produced/consumed. Entities carried over unchanged from `board_stop_check.py`
(Run announcement, Stop request) are included for completeness, per
spec.md's own "Key Entities" section, and are not modified by this feature.

## StopDecision (new)

The answer `find_stop_request()` produces for one job at one moment. Replaces
the single "run id, which may be your own" return value.

| Field | Type | Invariant |
|---|---|---|
| `stand_down` | `bool` | `True` whenever an authorized, unactioned stop request exists in the comment thread at or after the current baseline (FR-002), regardless of whether a cancel target exists. `False` otherwise. |
| `cancel_run_id` | `str \| None` | `None` whenever the only run announcement found is the run performing the check, or when `stand_down` is `False`, or when no earlier run announced itself at all (FR-003). Otherwise the earlier run's id, as a decimal string matching `MARKER_RUN_RE`'s captured group. **MUST NOT equal the current run's own id under any input** — this is the one invariant Gate 87 mutation-proves (research.md D9). |

**Representation**:
- In Python: a `collections.namedtuple("StopDecision", ["stand_down",
  "cancel_run_id"])` (research.md D1), returned by `find_stop_request()` and
  compared directly (`==`) against fixture-declared expectations in Gate 87.
- On the wire (stdout of `board_stop_check.py`'s `main()`): one line of JSON,
  `{"stand_down": <bool>, "cancel_run_id": <string> | null}`, printed exactly
  once per invocation, only on success (contracts/decision-function.md).
- In the composite's shell: two variables parsed from that JSON via `jq`
  (contracts/composite-invocation.md) — a `stand_down` truth value folding
  into the existing `paused` output, and a `cancel_run_id` string (possibly
  empty) gating the existing `gh run cancel` branch.

**Relationships**: Produced by `find_stop_request()` from an ordered list of
Run announcements and Stop requests (below); consumed by
`wing-commander-board-stop-check`'s `check` step to compute `paused` and,
when `cancel_run_id` is present, to drive the existing cancel-guard sequence
(unreadable-run check, workflow-path check, repository check, completed-
status check — all unchanged, FR-008).

## Run announcement (unchanged)

A `**Run:**` line at the start of a line, in a comment the loop's own App
posted (`is_loop_marker_author()`), matched by `MARKER_RUN_RE`. The *last*
such line in a given comment is the one that counts (`last_run_match()`,
issue #580). Sets the baseline for what a "stop" must be posted after, and
names the candidate cancel targets `find_stop_request()` considers. Not
modified by this feature — carried here only because `StopDecision` is
computed from a sequence of these.

## Stop request (unchanged)

A first-line `stop` command (`is_stop_command()`, `STOP_COMMAND_RE`), posted
by an author whose `author_association` is in `MAINTAINER_ASSOCIATIONS`
(`OWNER`, `MEMBER`, `COLLABORATOR`), at or after the baseline. Not modified by
this feature; `StopDecision.stand_down` is `True` exactly when at least one
such request exists in the ordered comment list.

## Stop-check composite (surface unchanged, internals reworked)

`.github/actions/wing-commander-board-stop-check/action.yml` — the one home
of the surrounding orchestration: the issue-state read, the paginated
comment read, the decision call, the guarded cancel, and the `paused` output.
FR-008 fixes its published surface:

| Surface element | Before | After |
|---|---|---|
| Inputs | `token`, `cancel-token`, `issue-number`, `bot-login`, `initial-paused`, `check-issue-closed` | unchanged (same names, same defaults) |
| Output | `paused` (boolean-as-string) | unchanged (same name, same meaning) |
| Decision source | inline `python3 -c` block, `sys.path` bootstrap, `from board_stop_check import find_stop_request` | `python3 .github/scripts/board_stop_check.py` invoked as a subprocess, fed the same stdin JSON shape `main()` already documents |
| Self-cancel guard | `if [ "$stop_run_id" != "$GITHUB_RUN_ID" ]` around the whole cancel sequence | same shape, reading `cancel_run_id` (already `None`/empty whenever it would equal `$GITHUB_RUN_ID`, per the StopDecision invariant above), re-commented as deliberately redundant defence in depth (FR-004) |
| Unreadable-run / workflow-path / repository / completed-status guards | present, in this order, inside the self-cancel branch | unchanged (FR-008) |

## Single-home check (Gate 60's `board-stop-check` entry, reworked)

`verify-single-home-idioms.py`'s `DECLARED_HOMES["board-stop-check"]` names
the composite above as the idiom's one home and fails a second site. Its
detection strategy changes from three literal, file-wide fragments to a
structural, per-step-list scan (research.md D7):

| Field | Before | After |
|---|---|---|
| Scope | whole file, any two lines apart | one job's (or one composite's own) resolved step list |
| Trigger 1 ("obtains a decision") | literal `"from board_stop_check import find_stop_request"` | regex matching either `board_stop_check\.py` (CLI) or `from board_stop_check import find_stop_request` (import) |
| Trigger 2 ("performs a cancellation") | literal `"gh run cancel"` | unchanged: `"gh run cancel"` |
| Trigger 3 (dropped) | literal `"board-stop-check-comments.json"` | removed — an implementation-detail filename, not part of the idiom's essential shape, and not required once triggers 1+2 already co-occur structurally |
| A finding requires | all three triggers present anywhere in the file | both remaining triggers present somewhere within the same step list |
