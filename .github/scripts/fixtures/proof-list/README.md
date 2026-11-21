# Proof list fixtures

Fixtures for specs/124-merge-proof-list. Every fixture fails without the code it tests.

| Fixture | Read by |
|---|---|
| `*.json` (states, qualification, set-apart, report, failed reads) | `.github/scripts/verify-proof-list.py` |
| reach copies and stale-exemption cases | `.github/scripts/verify-board-prove.py` (Gate 89), built in code |
| section statuses (built, paused, failed, never, unreadable, stale) | `.github/scripts/verify-board-status.py` |
| `sc001/corpus.json`, `sc001/expected.json` | the SC-001 replay in `verify-proof-list.py`; captured by the maintainer, never written by the implement stage |
