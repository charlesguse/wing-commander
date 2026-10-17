# Agent start-up classifier fixtures

Each case is a pair:

- `<branch>.log` -- raw job log text fed to `classify-agent-startup.py`.
- `<branch>.expect.json` -- `{"verdict", "step", "error_contains"}`; `step`
  and `error_contains` may be `null`. An optional `"note"` records provenance
  (`synthetic`: hand-written, not captured from a live run).

`verify-agent-startup-classifier.py` runs every pair and fails when a verdict
branch has no fixture or a fixture lacks its expect file.
