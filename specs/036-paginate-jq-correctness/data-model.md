# Phase 1 Data Model: Multi-Page `gh api` Reads Return What They Claim

This feature introduces no persisted storage and no new file format that
outlives a single workflow run. Every shape below is either a value carried
through an existing `signals.json`-style accumulate-and-merge file, a new
sibling of it with the same lifecycle, a static-analysis finding produced
and consumed within one gate run, or a fixture used only inside a test
harness.

## Paginated read (static-analysis subject — scanned, not stored)

The unit Gate 18 (research.md D2) evaluates. Not a runtime object; a
location in the repository's own source, matching spec.md's Key Entities
definition.

| Field | Type | Notes |
|---|---|---|
| `file` | string | Repo-relative path of the workflow, composite action (`action.yml`), or checked-in script containing the call. |
| `line` | int | 1-indexed line of the `gh api ... --paginate` invocation, for FR-007's "identify each offending location by file and line." |
| `jq_filter` | string \| null | The verbatim `--jq` argument, if present; `null` when no `--jq` is given at all. |
| `shape` | enum: `array-collecting` \| `no-filter` \| `streaming-json` \| `non-json-lines` | Derived from `jq_filter` (research.md D1/D2): `array-collecting` when the filter's outermost result wraps items in `[...]` (the T067 defect); `no-filter` when `jq_filter` is `null` on an endpoint whose body is an array or `{...}` object (the two accidentally-safe watchdog reads' shape); `streaming-json` when the filter emits one JSON value per line (`.[] \| ...`, no wrapping `[...]`); `non-json-lines` when the filter emits non-JSON text per line (e.g. `@tsv`), matching `lint-workflows.yml:1176`'s exempt-by-construction form. |
| `exempt` | `{reason: string} \| null` | Present when a `wc-pagination-exempt: <reason>` comment (research.md D3) is found within one line of the call; `null` otherwise. A present-but-empty reason does not count — `exempt` stays `null` and the site is still flagged. |
| `verdict` | enum: `pass` \| `fail` | `fail` iff `shape` is `array-collecting` or `no-filter` AND `exempt` is `null`. `array-collecting` or `no-filter` WITH a valid `exempt` is `pass` (FR-013). `streaming-json` and `non-json-lines` are always `pass` regardless of `exempt` (FR-008). |

Gate 18 emits one `::error file=<file>,line=<line>::...` per `fail` verdict,
naming both what is wrong (which `shape`) and the required form (FR-007),
and exits non-zero if any exist.

## Collector read outcome (ephemeral, produced by each `watchdog.yml` collector, consumed by `aggregate` and `diagnose`)

New entity (research.md D6), sibling to spec 015/023's existing `signals.json`
entries — same accumulate-in-`$RUNNER_TEMP`, fold-via-`jq`, discard-after-the-run
lifecycle, never written to a file this repository keeps.

| Field | Type | Notes |
|---|---|---|
| `collector` | string | One of the five collector step ids: `collect-execution-output`, `collect-branch-drift`, `collect-spec-meta`, `collect-step-summary`, `collect-annotations` — matching the names already used in `aggregate`'s existing `steps.<id>.outcome` list (`watchdog.yml:842-847`). |
| `outcome` | enum: `ok` \| `failed` | `failed` iff any `gh api` (or equivalent evidence-fetching) call inside that collector's script returned a non-zero exit this run, captured before the existing `\|\| echo '<empty>'` fallback swallows it. `ok` covers both "found signals" and "found nothing" — FR-010's required distinction is failed-vs-not-failed, not failed-vs-empty-vs-nonempty. |

Written by each collector to `$RUNNER_TEMP/collector-outcomes.json` (a
JSON array of the above), same file-per-run scope as `signals.json`.

## Untrusted-collectors output (new `collect` job output, consumed by `diagnose`)

| Field | Type | Notes |
|---|---|---|
| `untrusted-collectors` | JSON array of string | Every `collector` name from Collector read outcome entries with `outcome: "failed"`, deduplicated. `[]` when every collector's reads all succeeded (today's behavior — unchanged: FR-005/SC-007). Exposed as `steps.aggregate.outputs.untrusted-collectors`, then as the `collect` job's own `workflow_call` output (plan.md's Complexity Tracking — the one deliberate FR-015-authorized widening), alongside the existing, unchanged `signals` output. |

Materialized by the `diagnose` job into a second file
(`${{ runner.temp }}/watchdog-untrusted-collectors.json`) next to the
existing `watchdog-signals.json`, read the same way (Read tool, framed as
untrusted-data-adjacent metadata the agent is told to use only to qualify
its confidence — never to reason about the *content* of a collector's
evidence, which Out of Scope leaves untouched).

## Multi-page fixture (test-only, both harnesses — never shipped)

| Field | Type | Notes |
|---|---|---|
| `page_size` | int, fixed at 30 | Matches spec.md's Key Entities "Page boundary... thirty items by default." Used by both `gh_stub.py` (research.md D4) and Gate 19's stub (research.md D5) to decide how many items land on page 1 before a synthetic page 2 begins. |
| `items` | list of JSON objects | The full, un-paginated collection a scenario wants the fixture to represent (releases, or annotations). Chunked into `ceil(len(items) / page_size)` pages by the stub. |
| `emitted` | list of string | What actually reaches the collector/step's stdin/subshell: one JSON document (or, when a `--jq` filter is supplied, one filtered result) per chunk, concatenated with no added separator — the exact byte shape real `gh --paginate` produces, which is what makes a test built from this fixture able to fail against the pre-fix code and pass against the fix. |

No field of this entity is persisted; it exists only inside the process
memory / temp files of `verify-gate-19.py` and
`auto-update-spec-kit-tests/gh_stub.py` for the duration of one test run.

## Unaffected existing entities

- `signals.json` / the `Signal` entity (spec 015/023): unchanged shape.
  This feature fixes what reaches it (annotation entries no longer silently
  dropped) but adds no field to it — read outcomes live in the sibling file
  above precisely so this shape stays untouched (research.md D6's rejected
  alternative).
- Auto-update `Verification (smoke test) result` (spec 027/034,
  `specs/034-e2e-verification-tier/data-model.md`): untouched. This
  feature only fixes how `releases_json` is read inside `detect` and
  `evaluate-path`; neither step's output contract changes shape, only
  correctness past the page boundary (FR-003/FR-004).
