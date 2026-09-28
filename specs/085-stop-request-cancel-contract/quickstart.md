# Quickstart: Validating the Stop Decision Contract

This is a validation guide, not an implementation guide — it names the
checks a reviewer or the implement/converge stages run to confirm the design
in `plan.md`/`contracts/` actually landed. Full detail on what each command
covers is in the linked contract; this file does not restate it.

## Prerequisites

- A checkout of this repository on `spec/085-stop-request-cancel-contract`
  (or a branch built from it) with the implementation landed.
- Python 3, `bash`, and `jq` on `PATH` (already required by the existing gate
  suite — no new dependency).

## 1. The decision function's two-fact contract (contracts/decision-function.md)

```bash
python3 -c "
import sys
sys.path.insert(0, '.github/scripts')
from board_stop_check import find_stop_request
print(find_stop_request(
    [{'body': '**Run:** https://github.com/example/example/actions/runs/999\n\n<!-- wing-commander-board-item: {} -->',
      'author_association': 'NONE', 'created_at': '2026-01-01T00:00:00Z',
      'user': {'login': 'wing-commander-bot[bot]', 'type': 'Bot'}},
     {'body': 'stop', 'author_association': 'OWNER',
      'created_at': '2026-01-01T00:05:00Z',
      'user': {'login': 'maintainer', 'type': 'User'}}],
    '999', 'wing-commander-bot[bot]'))
"
```

**Expected**: `StopDecision(stand_down=True, cancel_run_id=None)` — a stop on
a first pass through the current run stands the job down and names nothing
to cancel (User Story 1, Acceptance Scenario 1; FR-003).

## 2. `main()`'s CLI contract (contracts/decision-function.md)

```bash
echo '{"comments": [
  {"body": "**Run:** https://github.com/example/example/actions/runs/222\n\n<!-- wing-commander-board-item: {} -->",
   "author_association": "NONE", "created_at": "2026-01-01T00:00:00Z",
   "user": {"login": "wing-commander-bot[bot]", "type": "Bot"}},
  {"body": "**Run:** https://github.com/example/example/actions/runs/999\n\n<!-- wing-commander-board-item: {} -->",
   "author_association": "NONE", "created_at": "2026-01-01T00:10:00Z",
   "user": {"login": "wing-commander-bot[bot]", "type": "Bot"}},
  {"body": "stop", "author_association": "MEMBER",
   "created_at": "2026-01-01T00:15:00Z",
   "user": {"login": "maintainer", "type": "User"}}
], "current_run_id": "999", "bot_login": "wing-commander-bot[bot]"}' \
  | python3 .github/scripts/board_stop_check.py
```

**Expected**: one line, `{"stand_down": true, "cancel_run_id": "222"}` — an
earlier run's own announcement is named as the cancel target (User Story 1,
Acceptance Scenario 2).

```bash
echo 'not json' | python3 .github/scripts/board_stop_check.py; echo "exit: $?"
```

**Expected**: no stdout, a traceback on stderr, non-zero exit (FR-007).

## 3. The composite has no inline reimplementation (contracts/composite-invocation.md)

```bash
grep -n "sys.path" .github/actions/wing-commander-board-stop-check/action.yml
grep -n "from board_stop_check import" .github/actions/wing-commander-board-stop-check/action.yml
```

**Expected**: both commands find nothing (User Story 2, Acceptance
Scenario 1; SC-002).

## 4. Gate 87 — the decision function and the composite shell (contracts/gate-87-coverage.md)

```bash
python3 .github/scripts/verify-board-stop-check.py
```

**Expected**: every fixture, command case, mutation, and composite-shell case
reports `[ok]`; the two mutation notes (`bare \bstop\b word match...`,
`marker author check dropped...`, `MARKER_RUN_RE un-anchored...`,
`first \`**Run:**\` line...`, and the new self-cancel mutation from
research.md D9) each report `mutation caught`; total `0 failure(s)`.

## 5. Gate 60 — the structural single-home check (contracts/gate-60-structural-check.md)

```bash
python3 .github/scripts/verify-single-home-idioms.py
python3 .github/scripts/verify-single-home-idioms.py --self-test
```

**Expected**: the first command reports `0 failure(s)` against the real tree
(no second site of the idiom exists). The second reports `0 failure(s)`
across every synthetic case, including the new "references the module
without orchestrating a cancel" case passing silently and the post-change-
style third paste being caught (User Story 3, all four Acceptance Scenarios).

## 6. The full local gate suite (SC-006)

```bash
python .github/scripts/run-local-gates.py
```

**Expected**: every gate passes, including Gate 60 and Gate 87 above; no
gate is skipped or waived to reach green.

## 7. `board-loop.yml`'s six call sites are untouched (FR-008)

```bash
git diff main -- .github/workflows/board-loop.yml
```

**Expected**: no output — this file is a consumer of the composite's
`paused` output and is not part of this feature's diff.
