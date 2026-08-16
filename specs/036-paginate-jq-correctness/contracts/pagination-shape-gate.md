# Contract: The Pagination-Shape Gate (Gate 18)

This is a repository-internal check, not a `workflow_call` interface — it
has no adopter-visible surface. This contract documents its input/output
behavior so Gate 18's implementation and its self-test
(`verify-gate-18.py`) can be built and verified against the same stated
rules, and so `tasks.md` can turn each rule into an independently
verifiable task.

## Scope (FR-006)

Scans, in the repository as checked out (never the transient
`.wing-commander-pipeline/` checkout — Assumptions):

- Every `run:` block in every `.github/workflows/*.yml` / `*.yaml` file.
- Every `run:` block in every `.github/actions/**/action.yml` composite
  action.
- The text of every checked-in shell/Python script the repository ships
  (today: none outside `.github/scripts/` contain `gh api --paginate`;
  the scope is defined by where shell can live, not a named subset —
  spec.md's "The defect class appearing outside workflow files" Edge
  Case — so a future script anywhere in the tracked tree is in scope).

Excluded: anything not checked into the repository (build output,
`.wing-commander-pipeline/`, `node_modules`-equivalent — there are none
today, but the rule is "tracked files," not "everything on disk").

## Detection rule

For every shell invocation matching `gh api ... --paginate` (in any of the
scanned sources above):

1. If a `--jq '<expr>'` argument is present on the same invocation:
   - Strip leading/trailing whitespace from `<expr>`. If the first
     non-whitespace character is `[`, the filter collects results into an
     array — **FAIL** (`array-collecting`, the T067 defect shape).
   - Otherwise — **PASS** (`streaming-json` or `non-json-lines`; FR-008
     does not distinguish them for gating purposes, since neither is ever
     wrong). This covers both a JSON-per-line filter consumed via `jq -s`
     and a non-JSON-per-line filter like `@tsv`.
2. If no `--jq` argument is present at all on the invocation — **FAIL**
   (`no-filter`), regardless of what the consumer downstream of the `gh
   api` call does with the result (FR-011: "whether or not its consumer
   happens to tolerate one value per page").
3. A site matching rule 1 or 2's FAIL condition is **exempted** (verdict
   flips to PASS) only if a comment containing the literal token
   `wc-pagination-exempt:` followed by non-whitespace text appears on the
   same line as the `gh api` invocation or the line immediately preceding
   it (research.md D3). A bare `wc-pagination-exempt` with no reason text
   does not exempt the site.

## Output

- Exit 0, no output beyond a one-line summary, when every scanned site
  passes.
- Exit 1 when any site fails. For each failing site, one
  `::error file=<path>,line=<N>::` line naming: the file and line
  (FR-007), which rule fired (`array-collecting` vs `no-filter`), and the
  required correct form — `gh api "<path>" --paginate --jq '.[] |
  <per-item filter>' | jq -s '.'` — so SC-006 ("a maintainer given only
  the check's failure output can rewrite the offending call... without
  consulting anything else") holds without the maintainer reading this
  contract or `research.md`.

## Wiring (FR-009)

A step named `Gate 18 — <short description>` in `lint-workflows.yml`'s
existing `lint` job, in the same numbered sequence as Gates 6-8 and
15-17, immediately followed by a `Gate 18 self-test — the detector
actually detects` step running `python3 .github/scripts/verify-gate-18.py`.
`verify-gate-18.py` extracts Gate 18's own source from the shipped
`lint-workflows.yml` at run time (no second copy) and runs it against a
fixture table covering, at minimum:

| Case | Expect |
|---|---|
| `--jq '[.[] \| select(...)]'` (T067's exact shape) | FAIL, mentions `array-collecting` and the correct form |
| No `--jq` at all, on an array endpoint | FAIL, mentions `no-filter` |
| No `--jq` at all, on an object endpoint (`{"jobs":[...]}` shape) | FAIL — this is the watchdog `:665`/`:740` shape; flagged regardless of the consumer's own tolerance (FR-011) |
| `--jq '.[] \| {...}'` piped to `jq -s '.'` downstream | PASS |
| `--jq '.[] \| [.a,.b] \| @tsv'` (non-JSON lines) | PASS |
| `--jq '.[] \| select(.x == ["a"])'` (a literal `[` inside the filter, not at the top level) | PASS — the rule anchors on the filter's *outermost* result shape, not "contains `[` anywhere" |
| A FAIL-shaped call carrying a same-line `# wc-pagination-exempt: <reason>` | PASS |
| A FAIL-shaped call carrying a bare `# wc-pagination-exempt` with no reason | still FAIL |
| The same FAIL shape inside a composite action's `action.yml` | FAIL — proves reach beyond `.github/workflows/` |
| The same FAIL shape inside a checked-in `.sh` file | FAIL — proves reach beyond workflow/action YAML |
| The five sites' shipped fix (research.md D1's streaming form), as they read after this feature lands | PASS — the regression case: reverting any one of the fixes must make this fixture FAIL again |

Per Acceptance Scenario 6/SC-005, Gate 10 (`verify-gate-wiring.py`) already
guarantees that if the `Gate 18` step or its self-test step is removed,
renamed without updating `verify-gate-18.py`, or the self-test step is
dropped, that itself fails a check — no separate mechanism is needed for
"the gate is itself gated."
