# Fixtures for verify-implement-stall-handoff.py (Gate 165)

Each fixture exercises one branch of a shared script under
`.github/actions/_shared/`. Naming: `<script>-<branch>.{md,json,env}` for the
input, with the expected output beside it as `<script>-<branch>.expected`.

- `count-tasks-checkboxes-*.md` -- tasks.md inputs; `.expected` holds the
  script's `key=value` output lines (heredocs included).
- `render-remaining-work-*.maintainer` / `.impl` -- the two item lists;
  `.expected` is the rendered markdown.
- `validate-implement-blocker-*.json` -- blocker records; `.tasks.md` is the
  tasks.md they are checked against; `.expected` the script's stdout.
- `decide-implement-outcome-*.env` -- cycle inputs as `KEY=value` lines;
  `.expected` the decision lines.
