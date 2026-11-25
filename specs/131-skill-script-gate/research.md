# Research: Gate the skill scripts' self-tests and cross-tree imports

No `[NEEDS CLARIFICATION]` markers remained in spec.md. The decisions below
settle what the spec leaves to the plan.

## D1. Check imports statically, with `ast`

- **Decision**: parse each skill script with `ast`; never import or run it.
- **Rationale**: FR-005 and the edge case on import-time side effects rule out
  executing the script. Static analysis cannot touch the network and needs no
  stubs. The target module is also parsed with `ast`, and its top-level names
  (def, class, assignment, import-as, `__all__`) are the set a reach must hit.
- **Alternatives**: `importlib` with stubbed `subprocess`/`urllib` is rejected
  because it runs module top-level code and the stubs drift. A regex scan is
  rejected because it misses `import x as m` attribute use.

## D2. What counts as a cross-tree reach

- `from M import n` where `M.py` exists in `.github/scripts/`: `n` must be a
  top-level name of `M` (or a submodule or package member).
- `import M` / `import M as m` followed by `m.attr` loads: each `attr` must be
  a top-level name of `M`.
- `M` counts as cross-tree when `.github/scripts/M.py` exists, or `M` is
  reached through the script's own `sys.path` insertion of `.github/scripts`.
  A module that resolves to neither the stdlib nor a third-party package
  nor `.github/scripts` fails as "module not found". The stdlib is taken from
  `sys.stdlib_module_names`. Third-party names (`yaml`) are an allowlist read
  from imports that are not in the repo tree, so a missing PyYAML is never
  reported as a renamed repo name (spec edge case).
- Dynamic loading (`importlib.util.spec_from_file_location` on a path under
  `.github/scripts`) is also recognised: the gate treats the loaded file
  name as the module, and attribute use on the bound variable is checked the
  same way. If a script's loader pattern is not recognised the gate fails
  loudly rather than skipping (Principle VIII). Task 1 inventories how each
  of the six scripts actually reaches the tree and sets the exact patterns.

## D3. Discover skill scripts and self-tests from the tree

- **Decision**: glob `.claude/skills/*/scripts/*.py`. A script "offers a
  self-test" when its AST contains the string constant `"--self-test"` in an
  `add_argument` call or a `sys.argv`/`in argv` comparison.
- **Rationale**: FR-003/FR-004 forbid a hand list. Detecting the flag by AST
  keeps `redrive_candidates.py` and the others out unless they declare it.
- **Alternatives**: running every script with `--help` is rejected because
  it executes unknown code paths.

## D4. One new gate, two modes in one script

- **Decision**: one new script `.github/scripts/verify-skill-scripts.py`.
  Default mode checks imports and then runs every discovered self-test as a
  subprocess (`python -I`-free, cwd repo root, `timeout` 60s each, network
  env vars unset). `--self-test` builds mutated scratch copies of the tree
  and shows the three seeded defects fail (FR-006).
- **Rationale**: One home (CLAUDE.md "single home"). Not folded into
  `verify-convergence-single-home.py`, which is about arithmetic copies and
  already owns the `paths:` check (FR-008); folding would blur both.
- **Alternatives**: two scripts (imports, self-tests) double the CI wiring and
  the fixtures for no gain. Rejected.

## D5. Wiring and local parity

- lint-workflows' `lint` job gets two steps, each `if: "!cancelled()"`, with
  names unique among PR-time steps:
  `Gate NNN — skill scripts' cross-tree names resolve and their self-tests pass`
  and `Gate NNN fixtures — verify-skill-scripts self-test`. `NNN` is the next
  free number at implement time. `wc_gate_registry.pr_time_invocations`
  derives both into `run-local-gates.py` (FR-007), so no list edit.
- If spec 129's sharded layout is on main when implementing, the two steps go
  in the one shard that owns the skill/scripts gates and nowhere else
  (FR-011). Task 1 checks which layout is live.
- The `paths:` entry `.claude/skills/*/scripts/**` already exists. Nothing is
  added; `verify-convergence-single-home.py` stays its only enforcer (FR-008).
  The new gate's own file lives under `.github/scripts/`, already in `paths:`.
- `docs/reference.md` is edited only if a category in its "Keeping this
  current" section changes. A new gate script is expected not to change one;
  task 1 confirms by reading that section.

## D6. Size and PR split (FR-010)

- **Decision**: a single PR is expected to be well within the board's
  backstop only if the script plus fixtures stay lean; PR #1205 already hit
  files=2/lines=123 over the limit with a partial version. Split in two PRs:
  PR A: gate script + `--self-test` fixtures + wiring (this is the fix).
  PR B: only if needed, the housekeeping (close #1205, tick `bl-ddabf5f6`).
  FR-009 housekeeping is not code and needs no PR: close #1205 with a pointer
  and tick the backlog line through `board_backlog_edit.py` on merge.
- **Alternatives**: three PRs (imports, self-test run, fixtures) leave a
  window where a half-gate is on main. Rejected.

## D7. Self-test runtime and offline rule

- The skill self-test subprocess runs with `GH_TOKEN`/`GITHUB_TOKEN` unset and
  a 60s timeout, which makes a network-needing self-test fail loudly as the
  spec requires (FR-004). `thrash_signals.py --self-test` needs only git,
  present in the CI job.
- Budget (SC-004): static parse of six files plus one self-test is expected
  in a few seconds; the gate's own `--self-test` runs mutated copies of a
  handful of small files, not the full tree.
