# Contract: Emission (published, always on)

**Layer**: published contract — `.github/actions/wing-commander-metrics-summary`
(extended, not replaced) plus the ~14 existing published stage workflows
that call it.

## `wing-commander-metrics-summary` — new/changed surface

All existing inputs/outputs (`transcript-path`, `model`, `max-turns`,
`ceiling`, `warn-fraction`, `run-label`, `verdict`, `verdict-reason`)
are unchanged (FR-036: no removal or rename; FR-011: the rendered
step-summary table does not change). Additions:

| Name | Kind | Required | Default | Description |
|---|---|---|---|---|
| `record-path` | input | No | `${{ runner.temp }}/wing-commander-metrics-record.json` | Where the normalized JSON record (contracts/metrics-record-schema.md) is written. Always written, regardless of transcript health — a missing/unparseable transcript produces the degraded-record shape, never a missing file. |
| `stage` | input | No | `""` (→ `stage_available: false`) | Literal stage name for the record's `stage` field. Never inferred from the transcript or ambient state (constitution VII: stage workflows read no ambient state — this is a declared input, supplied by the caller). |
| `spec-dir` / `spec-issue` | input | No | `""` / `""` | Literal spec identity, when the caller already has it (most call sites do — same context resolution every stage already performs for its own status comment). Absent → `spec.identity_available: false`. |
| `record-json` | output | — | — | The same JSON as `record-path`'s contents, as a string, for callers that want it without a file read. |
| `record-key` | output | — | — | The `run.record_key` value, for callers wiring the per-run rollup line (contracts/persist-workflow.md). |

**Guarantees** (unchanged behavior class from the existing action):
never fails the step or the job; a missing/empty/unparseable transcript
degrades every transcript-derived field to unavailable rather than
guessing, defaulting, or omitting (FR-007, FR-009); no network access;
no agent invocation (FR-040a); reads only the file at `transcript-path`
plus its own declared inputs — no `github.event.*`, no `vars.*`.

## Call-site contract

Every one of the ~14 existing call sites (`intake.yml`, `clarify.yml`,
`plan.yml` ×2, `tasks.yml` ×2, `implement.yml` ×3, `finalize.yml`,
`cleanup.yml`, `rebase.yml`, `watchdog.yml` (diagnose),
`pr-conversation.yml` ×2 — data-model.md) gains, immediately after its
existing "Upload execution transcript" step:

```yaml
- name: Upload metrics record
  if: always() && steps.<agent-id>.outcome != 'skipped'
  uses: actions/upload-artifact@v6
  with:
    name: metrics-record<-same suffix the transcript upload at this site already uses>
    path: ${{ runner.temp }}/wing-commander-metrics-record.json
    if-no-files-found: ignore
    retention-days: 90
```

placed after the metrics-summary step runs (so the file exists) and
before any later agent step in the same job overwrites the shared
`runner.temp` path — the same ordering constraint the transcript upload
already observes at multi-step jobs (`implement.yml`).

Each of the ~14 sites that already posts a status comment to a spec's
lifecycle issue (all except `watchdog.yml`'s diagnose site, which posts
to a findings issue, not a spec lifecycle issue) additionally appends
the per-run cost line (data-model.md "Rollup — per-run cost line") built
from `wing-commander-metrics-summary`'s outputs, to the body of the
comment it already sends. No new comment is added (FR-031c); the
existing `gh issue comment` / `wing-commander-callout` call for that
step gains one more line in its body.

## Non-goals reasserted (FR-002, FR-003, FR-011)

This action still writes nothing to any branch, issue, or other durable
location. It still requires no configuration to run — a caller that
passes none of the new optional inputs still gets a valid degraded-in-those-fields
record. The rendered `$GITHUB_STEP_SUMMARY` table is byte-for-byte the
same shape it was before this feature.
