# Fixtures for spec 123 (implement finishes its tasks)

Checked-in inputs for the failure branches of the buildable classification
(FR-017). Each family is driven by a gate under `.github/scripts/`.

| Family | Directory | Driven by |
|---|---|---|
| classification | `classification/` | `verify-buildable-classification.py` |
| cap-outcome (incl. the cycle-outcome line) | `cap-outcome/` | `verify-buildable-classification.py` |
| finalize-wait | `finalize-wait/` | `verify-finalize-buildable-wait.py` |
| review-gate-skip | `review-gate-skip/` | `verify-finalize-buildable-wait.py` |
| migration | `migration/` | `verify-migrate-stranded-review-lifecycles.py` |
| watchdog-handoff | `watchdog-handoff/` | `verify-finalize-buildable-wait.py` |

A classification case is `<name>.tasks.md` plus `<name>.expected`: one
`key=value` per line, naming the `count-tasks-checkboxes.sh` outputs the case
pins, and an optional `env:KEY=value` line (for example
`env:GATE_SUITE_READY=false`).

A review-gate-skip case is `<name>.tasks.md` (absent for an unreadable
count) plus `<name>.expected` pinning `skip=true|false`; the gate runs
lifecycle-review-gate.yml's own skip block against it.

Every row above must name a directory that exists, holds fixtures, and is
read by the gate it names (Gate 166, `check_fixture_readme`).
