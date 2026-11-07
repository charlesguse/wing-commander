# Fixtures for spec 123 (implement finishes its tasks)

Checked-in inputs for the failure branches of the buildable classification
(FR-017). Each family is driven by a gate under `.github/scripts/`.

| Family | Directory | Driven by |
|---|---|---|
| classification | `classification/` | `verify-buildable-classification.py` |
| cap-outcome | `cap-outcome/` | `verify-buildable-classification.py` |
| finalize-wait | `finalize-wait/` | `verify-finalize-buildable-wait.py` |
| review-gate-skip | `review-gate-skip/` | `verify-finalize-buildable-wait.py` |
| cycle-outcome | `cycle-outcome/` | `verify-buildable-classification.py` |
| migration | `migration/` | `verify-migrate-stranded-review-lifecycles.py` |
| watchdog-handoff | `watchdog-handoff/` | `verify-finalize-buildable-wait.py` |

A classification case is `<name>.tasks.md` plus `<name>.expected`: one
`key=value` per line, naming the `count-tasks-checkboxes.sh` outputs the case
pins, and an optional `env:KEY=value` line (for example
`env:GATE_SUITE_READY=false`).
