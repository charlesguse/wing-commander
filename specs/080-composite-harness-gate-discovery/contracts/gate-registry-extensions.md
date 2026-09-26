# Contract: `wc_gate_registry.py` extensions

`wc_gate_registry.py` is the shared module `run-local-gates.py` and
`verify-gate-wiring.py` both import "so they cannot disagree about what a
gate is" (its own module docstring). This feature adds three functions
and changes none of the existing ones' signatures or return shapes —
every current caller of `gate_scripts()`, `invocations()`,
`pr_time_gates()`, `pr_time_invocations()`, `referenced_script_paths()`,
`shared_modules()`, `workflow_files()`, `pr_time_inline_steps()` keeps
working unmodified (research.md D1/D2: `gate_scripts()` itself is not
widened).

## `unsupported_actions_scripts(root=".") -> list[str]`

**Purpose**: every path under `.github/actions/` that FR-012 forbids —
consumed only by `verify-actions-no-gate-scripts.py`. Never consumed by
`run-local-gates.py` or folded into `gate_scripts()` — that would make
the local runner try to execute a file this function exists to reject
(research.md D2).

**Contract**:
- Walks exactly `<root>/.github/actions` (`os.path.join(root, ACTIONS_DIR)`
  where `ACTIONS_DIR = ".github/actions"`), never a broader recursive scan
  from `<root>` — a sibling `.wing-commander-pipeline/.github/actions/**`
  tree (a different top-level directory) is unreachable from this walk by
  construction, not by an exclusion rule that could be forgotten.
- Matches, at any depth: a file named exactly `run-tests.sh`; a file
  matching `verify-*.py` or `verify-*.sh` with no other file in the same
  directory belonging to the same multi-file harness (i.e. a *standalone*
  script, matching FR-012's "standalone `verify-*.py` or `verify-*.sh`" —
  a `verify-*.py` imported as a helper by a sibling `run-tests.sh` in the
  same directory is part of that harness, not a second, independent
  violation).
- Excludes anything whose repo-relative path has `.github/actions/_shared/`
  as a prefix (FR-014: the carve-out is structural, not a manifest entry).
- Returns repo-relative, forward-slash paths (same normalisation as
  `_rel()`), sorted.
- Returns `[]` when `.github/actions/` holds nothing of this shape — the
  expected common case (spec.md Edge Case: "Most composites have none").

## `referenced_actions_script_paths(root=".") -> dict[str, list[str]]`

**Purpose**: the reverse-direction sibling of the existing
`referenced_script_paths()`, scoped to `.github/actions/` instead of
`.github/scripts/`. Consumed by `verify-gate-wiring.py`'s reverse check
(FR-004).

**Contract**:
- Identical shape and technique to `referenced_script_paths()`: scans
  every workflow's `run:` text (via the existing `_run_text()`, which
  already strips `#`-prefixed comment lines — a path named only in a
  comment is never counted, satisfying FR-004's second sentence for the
  `.github/actions/` case the same way it already does for
  `.github/scripts/`), extracting every substring matching
  `\.github/actions/[A-Za-z0-9_./-]+`.
- Returns `{path: sorted([workflow, ...])}`.
- Matches on the substring starting at `.github/actions/` regardless of
  what precedes it in the source line — so `./.github/actions/_shared/
  x.sh` and `./.wing-commander-pipeline/.github/actions/_shared/x.sh` both
  key to the identical string `.github/actions/_shared/x.sh` (FR-013 is
  satisfied by this matching behaviour, not by a separate normalisation
  step — research.md D4).
- Does not distinguish a file reference from a directory reference (an
  `os.path.exists()` check downstream treats both as "resolved"); this
  matches the existing `.github/scripts/` reverse check's behaviour and
  is correct here too, since a `run:` block can legitimately name either
  a composite's directory or one of its scripts.

## `gate_label(script, args, root=".") -> str`

**Purpose**: the one place a gate's display/cache/filter identity is
computed — replaces `run-local-gates.py`'s inline `label_of` (FR-007,
research.md D5).

**Contract**:
- `script` relative to `.github/scripts/` (e.g. given
  `.github/scripts/dispatch-and-wait-tests/run-tests.sh`, produces
  `dispatch-and-wait-tests/run-tests.sh` — never `os.path.basename`,
  which collapses every `.github/scripts/*/run-tests.sh` harness to the
  identical string `run-tests.sh`).
- For a script directly under `.github/scripts/` with no subdirectory
  (e.g. `.github/scripts/verify-gate-wiring.py`), the relative form and
  the basename coincide (`verify-gate-wiring.py`) — this function is a
  drop-in replacement for `label_of`'s output on every gate that was never
  colliding, not only the ones that were.
- Joined with `args` exactly as `label_of` did:
  `(relative_path + " " + " ".join(args)).strip()`.
- **Invariant**: for any two `(script, args)` pairs with different
  `script` values, `gate_label` MUST return different strings. True by
  construction, since two distinct files cannot share a repo-relative
  path — no uniqueness check is needed at call sites; it is a property of
  the function, asserted by `verify-gate-wiring.py`'s new self-test
  fixture (research.md D6) as regression coverage, not as run-time
  validation.

## Call-site changes (no new contract, listed for completeness)

- `run-local-gates.py`: every use of the removed `label_of` becomes a call
  to `wc_gate_registry.gate_label`. Output format, timing-cache file
  shape, and `--jobs 1`'s byte-identical-output contract are unchanged —
  only the *value* of the label changes for the five colliding harnesses,
  never the mechanism around it.
- `verify-gate-wiring.py`: gains calls to `unsupported_actions_scripts`
  (via the new `verify-actions-no-gate-scripts.py`, not directly — Gate 10
  itself does not enforce FR-012; see `contracts/enforcement-gate-cli.md`)
  and to `referenced_actions_script_paths` (directly, alongside its
  existing `referenced_script_paths` loop).
