# Contract: `.github/scripts/verify-skill-scripts.py`

This is a live contract read by gates; fix it like code.

## Invocation

| Command | Meaning | Exit |
|---|---|---|
| `python3 .github/scripts/verify-skill-scripts.py` | check cross-tree names of every `.claude/skills/*/scripts/*.py`, then run every discovered `--self-test` | 0 clean, 1 any finding |
| `python3 .github/scripts/verify-skill-scripts.py --self-test` | seed defects in scratch copies; each must be caught | 0 all caught, 1 any seeded defect passed |

Both are invoked by lint-workflows' `lint` job, one step each, each
`if: "!cancelled()"`, step names unique among PR-time steps.

## Output

One line per finding to stdout, then a summary line:

    skill-script: <path>: <module>.<name>: <reason>
    verify-skill-scripts: N finding(s)

`<reason>` is one of `missing-name`, `missing-module`, `self-test-failed`,
`unrecognised-loader`. A clean run prints
`verify-skill-scripts: OK (<S> scripts, <R> reaches, <T> self-tests)`.

## Guarantees

- Never imports or executes a skill script except as `<script> --self-test`
  in a subprocess with `GH_TOKEN`/`GITHUB_TOKEN` unset and a 60s timeout.
- Discovery is from the tree; no list of script names appears in the gate.
- Zero discovered scripts exits 1.
- A missing third-party module is not reported as a repository name.

## `--self-test` cases (each a checked-in fixture under
`.github/scripts/verify-skill-scripts-fixtures/`)

1. removed name (`from M import n`, `n` absent) -> `missing-name`
2. removed attribute (`import M as m; m.n`) -> `missing-name`
3. removed module -> `missing-module`
4. failing skill self-test -> `self-test-failed`
5. new skill script with imports, no gate edit -> checked (discovery)
6. script importing only stdlib/third-party -> passes
7. empty skill tree -> fails loudly
