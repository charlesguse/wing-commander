# Research: Gate 12 — gh call-site authoring rule and shared locator

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below
resolve the open design choices the spec leaves to planning.

## R1 — Locator technique (pure Python, single pass)

- **Decision**: A single left-to-right character scanner in
  `.github/scripts/wc_gh_callsites.py` with an explicit state stack (normal,
  single-quote, double-quote, `$( )` depth, backtick, comment, heredoc body).
  It emits one `Token(kind, line, col, text)` per command-position `gh`
  word and classifies each as `statement`, `subst_first`, `disallowed` or
  `mention`. Heredoc bodies are skipped by recording the delimiter at the
  `<<` and consuming lines until the terminator in the same pass (no
  re-slicing, which removes the quadratic behaviour, FR-008).
- **Rationale**: FR-004 lets only three things be mentions, so the scanner
  only needs to track quote, comment and heredoc state precisely. Everything
  else defaults to "call" (FR-006), so the scanner never has to model
  `case`, ANSI-C strings, `${…}` nesting or escaped backticks: it only has
  to notice them and fail closed. That is where the ~690 lines shrink to
  ~250 (SC-003).
- **Alternatives**: `shfmt` or `bashlex` (rejected, FR-019: no new
  dependency); regex-only (rejected: cannot track quote state); keep the
  inline parser and patch gaps (rejected: PR #969 shows it does not converge).

## R2 — Allowed-form acceptance

- **Decision**: A `gh` token is a call at command position when the
  preceding tokens on its simple command are only: nothing (statement
  start after newline, `;`, `&&`, `||`, `|`, `{`, `(`, `then`, `do`,
  `else`), optional `GH_TOKEN=<word>`, optional `timeout <N>`. It is allowed
  when at statement level, or first command of a one-level `$(…)` (no
  nested `$(`/backtick between). Anything else at command position, or any
  `gh` reached through a quote that contains `$(`/backtick, an unquoted
  heredoc body, `$'…'`, or a `case` arm inside `$( )`, is `disallowed`.
- **Rationale**: Matches the census (294 + 183 + 1 timeout). The subcommand
  and `gh api` method flag must be literal words; a word starting with `$`,
  quote-with-expansion, or backtick in those slots is `disallowed`.
- **Alternatives**: accept `env`/`command`/`exec` prefixes (rejected:
  not in the census; add on evidence).

## R3 — Gate placement and naming

- **Decision**: New `verify-gate-12-token-permissions.py` holds the gate
  body moved out of `lint-workflows.yml` (permission table, token
  resolution, docs/setup.md parse, composite call-site walk — logic kept
  as-is, FR-007). Existing `verify-gate-12.py` stays the self-test but
  imports the gate script instead of extracting source from the workflow
  YAML. The `lint-workflows.yml` step becomes
  `python3 .github/scripts/verify-gate-12-token-permissions.py`, step name
  unchanged. Registry and `run-local-gates.py` pick it up via
  `wc_gate_registry.py`; path triggers add the scripts, `wc_gh_callsites.py`,
  `docs/setup.md`, workflows and actions.
- **Rationale**: Principle VIII (same subject and arguments locally and in
  CI); keeps "Gate 12" numbering (spec assumption).
- **Alternatives**: rename the self-test (rejected: churns
  `verify-gate-wiring.py`'s references).

## R4 — Gate 28 migration

- **Decision**: `verify-gh-api-explicit-method.py` calls
  `wc_gh_callsites.locate()` and reads `-X/--method` from the located call's
  literal argument words; glued forms (`-XPOST`, `--method=POST`) are parsed
  there. Its own tokeniser is deleted.
- **Rationale**: FR-012; closes the "glued method flags" gap.

## R5 — Single-home check

- **Decision**: Extend `verify-single-home-idioms.py` (nearest existing
  gate, with `single-home-waivers.json`) with an idiom that fails when a
  script outside `wc_gh_callsites.py` tokenises shell for `gh` (heuristics:
  regex `\bgh\b` combined with quote/heredoc-state scanning, or a
  `shlex`-based `gh` search in `.github/scripts/*.py`). The only waiver is
  `verify-stop-point-recording.py` (#954's reader), citing the new #889
  checklist line (Gate 124 compatible).
- **Alternatives**: a new gate (rejected: CLAUDE.md says extend nearest).

## R6 — Acceptance corpus and differential oracle

- **Decision**: Copy the 183 scenarios from
  `archive/pr-969-gate-12-corpus:.github/scripts/verify-gate-12.py` into a
  data file `.github/scripts/gate-12-corpus.json` (id, snippet, token
  setup, expected verdict `pass | permission | disallowed`, optional
  `changed_from_969: true` note). Copy the generator and runner from
  `archive/gate-12-fuzz/` into `.github/scripts/gate-12-fuzz/`, with
  `wc_shell_harness.py` providing the stub `gh` (extended if it lacks an
  argv-recording stub). The self-test runs a seeded, bounded fuzz batch
  (deterministic seed, fixed count so CI time is bounded).
- **Mutation (FR-016)**: self-test imports the locator, monkeypatches the
  classifier to return `mention` for a known call, and asserts the corpus
  run goes red.
- **Rationale**: Principle VIII.

## R7 — Census re-verification and mention sites

- **Decision**: Implementation's first task is to run the new locator in
  report mode over the tree and record counts of (executable calls,
  disallowed forms, mentions in unquoted heredocs / `$(`-bearing double
  quotes). Expected: 478 calls, ~1–2 migrations (`timeout` site is accepted
  by the `timeout N` prefix, so likely zero), ~80 mentions of which those in
  unquoted heredocs are fixed by quoting the delimiter (only where the body
  has no intended expansion) or rewording. Result recorded in tasks and on
  the PR.
- **Rationale**: Spec assumption requires planning/implementation to count
  these; the count needs the locator, which does not exist yet, so it is
  sequenced first in implementation rather than guessed here.

## R8 — Authoring rule home

- **Decision**: One section "Authoring rule for `gh` call sites" in
  `CONTRIBUTING.md` if present, else `docs/` contributor doc chosen at
  implementation (a `Grep` for the existing contributor doc decides); gate
  failure messages end with a pointer to that heading. Other prose points
  at it, not restates it.
- **Rationale**: FR-002; CLAUDE.md "one canonical comment".

## R9 — #889 bookkeeping

- **Decision**: Implementation adds one checklist line to #889 for #954's
  reader migration and ticks the six gap lines when fixtures land. Done
  with `gh issue` at implement time, not by this plan stage.
