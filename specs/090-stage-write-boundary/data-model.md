# Phase 1 Data Model: The Implement Stage's Write Boundary

This feature has no database or application data model. Its "entities" are
values declared as `workflow_call`/composite inputs, or computed by
deterministic shell/Python inside GitHub Actions steps and carried as
step/job outputs — the workflow-native equivalent of a data model for this
project type (a CI/CD pipeline), following spec 059's own data-model.md
shape.

## Entities

### Write boundary (`no-write-paths`)

- **Shape**: comma-separated string of path prefixes (e.g. `.claude/`); may
  be empty.
- **Declared by**: `implement.yml`'s `workflow_call` input `no-write-paths`,
  default `.claude/` (FR-019, FR-021). This is the *one* definition FR-003
  requires; every other entity below reads it, never restates it.
- **Consumed by**: the write-paths statement (below), the per-task
  classification (below), transitively the routing label only in that it
  shares the same `implement.yml` scope.
- **Validation rule**: FR-005 — the statement built from this value must
  never claim a path is forbidden that the run's actual tool grants would
  in fact permit; since `Write`/`Edit` carry no path-scoping syntax on this
  contract at all (D0), this holds trivially today — the value is prose the
  agent is asked to honor, not a second enforcement layer, and D0's finding
  that no known drift-inducing counter-mechanism exists in-repo is what
  makes that acceptable per Assumptions.

### Write-paths statement (`write-paths-statement`)

- **Shape**: one rendered sentence.
- **Computed by**: `wing-commander-tool-args`, the same composite step that
  renders `shell-commands`, using the identical four-shape template
  (D2): empty input → "may write any path"; non-empty → "may not write:
  \<list\>."
- **Read at**: prompt-composition time, before the agent's first tool call
  (FR-004) — rendered into both the cycle and retry Tooling paragraphs.
- **Relates to**: derived 1:1 from Write boundary; cannot diverge from it
  because there is no second literal (FR-003, FR-005).

### Unchecked task text (`unchecked-items`, pre-existing, spec 059)

- **Shape**: newline-delimited literal text of each `- [ ]` line outside a
  fenced block, at a given ref.
- **Computed by**: `wing-commander-tasks-checkbox-count` (unchanged by this
  feature — Dependencies section of spec.md).
- **Consumed by**: the per-task classification below, as its sole source of
  task text — no second read of `tasks.md`.

### Per-task classification (`findings-json`, `out-of-boundary-count`)

- **Shape**: `findings-json` is a JSON array, each element shaped to
  `.github/schemas/stage-finding.schema.json`; `out-of-boundary-count` is a
  non-negative integer (`len(findings-json)`).
- **Computed by**: `wing-commander-write-boundary` (new), one call per
  arm/ref, over `unchecked-items` at the tip, given `no-write-paths` (D3).
- **Classification rule**, per unchecked line:

  | Path-like tokens found | All within a `no-write-paths` prefix | Verdict |
  |---|---|---|
  | none | — | falls through — ordinary unfinished work (FR-015) |
  | ≥1 | no (at least one in-reach) | falls through — ordinary unfinished work (FR-015, "several paths, only one out of reach") |
  | ≥1 | yes | out-of-boundary — one `findings-json` entry (FR-006, FR-007) |

- **Each `findings-json` entry**: `title` names the task and path; `what`
  states it is outside the stage's write boundary and why; `evidence.
  file_paths` = `[<spec-dir>/tasks.md]`; `evidence.detail` = the literal
  task line plus the out-of-boundary path(s); `fingerprint_basis.file_path`
  = the same `<spec-dir>/tasks.md`; `fingerprint_basis.gate_or_artifact` =
  the literal unchecked line text (verbatim, so it anchors — D6). Using the
  spec's own `tasks.md` path and the exact line text as the fingerprint
  basis, rather than the out-of-boundary target path, is what keeps two
  specs meeting the same `.claude/` path from colliding onto one
  fingerprint (Edge Case: "the same out-of-boundary task in two specs at
  once").
- **Validation rules**: FR-014 — a *checked* task is never classified,
  never re-opened, never re-filed, whatever its path (the classifier only
  ever sees `unchecked-items`, so a checked task cannot reach it at all).
  FR-013 — the classification call itself is only made when the read-back
  is otherwise proceeding (`ok=true`, not yet known to be `truncated`); its
  result is only *acted on* (routing, reason branch) when `truncated=false`
  is later confirmed, mirroring spec 059's own scope note for `progressed`.

### All-unchecked-out-of-boundary (`all-unchecked-out-of-boundary`)

- **Shape**: boolean.
- **Computed by**: `wing-commander-write-boundary`, from the classification
  table above: `true` iff `unchecked-count(tip) > 0` and every unchecked
  line was classified out-of-boundary.
- **Relates to**: read by `Read back cycle outcome`/`Read back retry
  outcome` only inside the branch spec 059's existing hand-off condition
  already selects (D5) — it changes the `reason` narrative there, never the
  `converged`/`progressed`/`handoff` booleans themselves.

### Routed flag (`routed`, new step-local output)

- **Shape**: boolean, step-local (not a `workflow_call` output — mirrors
  spec 059's `progressed`/`handoff`).
- **Computed by**: `Read back cycle outcome`/`Read back retry outcome`:
  `routed = ok && !truncated && all-unchecked-out-of-boundary` (D5),
  deliberately NOT gated on spec 059's `handoff` (PR #836 review, item 2) —
  a cycle that ticks the last in-reach task, or whose `converge:` commit
  re-appends only out-of-boundary lines, still leaves 100% of the remaining
  unchecked work unreachable, and that must be filed the moment this cycle
  sees it rather than only on the one narrow path spec 059's own decision
  table was built to describe. Carried through "Consolidate final outcome"
  under the existing `RETRY_RAN` selection, alongside `findings-json`.
- **Relates to**: gates whether "Route out-of-boundary tasks" (below) runs
  at all this cycle.

### Non-convergence reason (`reason` narrative, extended)

- **Shape**: free text, assembled (not agent-authored), extending spec
  059's own cases.
- **New case**: when `routed=true`, the narrative names each out-of-
  boundary task id/path from `findings-json` and states plainly that the
  loop is ending here because the only remaining work is outside the
  stage's write boundary — satisfying FR-011's "neither converged nor
  stalled nor failed," distinguishable on sight from spec 059's existing
  generic hand-off narrative ("the cycle checked nothing new").
- **Unaffected case**: FR-012 — a cycle where `progressed=true` this cycle
  (other work also got done) uses spec 059's existing "outstanding with
  progress" narrative unchanged. Unlike the shipped `reason` branch, which
  checks `routed` before `handoff`/`progressed` precisely because `routed`
  no longer implies `handoff` (PR #836 review, item 2), `routed` CAN be
  `true` in the same cycle a `progressed=true` task also ticked — the
  narrative branch order, not the `routed` formula itself, is what keeps
  "outstanding with progress" from being displaced by the routed phrasing.

### Routed finding (filed GitHub issue)

- **Shape**: a GitHub issue, filed via `wing-commander-stage-findings` with
  `channel-mode: structured-array`, `finding-kind: routed-task`,
  `label-prefix: ${{ inputs.write-boundary-label-prefix }}` (default
  `route-out-of-boundary`), carrying label `route-out-of-boundary:
  implement` and the same `<!-- wing-commander-finding: fingerprint=... -->`
  marker convention `found-by:*` findings already use.
- **Computed/filed by**: "Route out-of-boundary tasks" (new step), guarded
  `ok == 'true' && truncated != 'true' && write-boundary-findings-json !=
  '[]' && (routed == 'true' || handoff == 'true' || iteration >= max)`
  (FR-013, FR-007; PR #836 review, item 12) — broadened past `routed` alone
  so a mixed unchecked set (some out-of-boundary, some ordinary) still gets
  its out-of-boundary tasks filed on a stalled or cap-reached cycle, not
  only on a clean routed hand-off.
- **Idempotency**: FR-008 — the fingerprint is the anchor form (D6), keyed
  on `(stage, tasks.md path, exact line text)`; the same out-of-boundary
  task on a later cycle, a retry of the same iteration, or a re-driven run
  recomputes the identical fingerprint and `wing-commander-durable-failure-
  issue` (downstream of the findings composite) recognizes the existing
  open issue rather than filing a second one.
- **Board-loop visibility**: labeled outside Principle X's three
  authorized-entry classes (maintainer label, `found-by:<stage>`,
  `spec-request`) by construction — the loop may read and triage-propose on
  it, never push a fix for it, until a human relabels it (D4).

### Routed-item lookup (`finalize.yml`, new)

- **Shape**: for each unchecked line at the tip when `finalize.yml` runs, a
  computed fingerprint (D6, shared formula) and, if a matching open/closed
  issue carrying that marker and the `route-out-of-boundary:implement`
  label exists, its URL.
- **Computed by**: "Look up routed write-boundary items" (new deterministic
  step), feeding the existing remaining-manual-work prompt (`finalize.
  yml:722-738`) a rendered mapping it must use verbatim for any line that
  matched, rather than composing prose for that line itself.
- **Validation rule**: SC-005 — every remaining-manual-work item that
  matched a routed item's fingerprint carries that item's URL, never bare
  prose; an unmatched unchecked line (ordinary unfinished work) is handled
  exactly as today.

## Relationships

```
no-write-paths (implement.yml input)
  ├─▶ write-paths-statement (wing-commander-tool-args)   [prompt, FR-004]
  └─▶ per-task classification (wing-commander-write-boundary)
        ├─▶ findings-json, out-of-boundary-count
        └─▶ all-unchecked-out-of-boundary

unchecked-items(tip) [unchanged, spec 059] ─▶ per-task classification

ok, truncated, all-unchecked-out-of-boundary ─▶ routed
                              (NOT gated on handoff -- PR #836 review, item 2)
routed, findings-json ─▶ reason narrative (extended)
ok, truncated, findings-json, (routed or handoff or iteration>=max)
                                       ─▶ "Route out-of-boundary tasks"
                                       ─▶ routed finding (GitHub issue)
                                       ─▶ lifecycle-issue recap comment
                                          (wing-commander-stage-findings'
                                           existing mechanism)

routed finding's fingerprint formula ──shared──▶ compute-finding-
                                                   fingerprint.sh
                                                        │
                    finalize.yml's "Look up routed      │
                    write-boundary items" recomputes ◀──┘
                    the same formula per unchecked line
                        │
                        ▼
                  remaining-manual-work prompt (extended)
```

## State: what does *not* change

- `implement.yml`'s existing `workflow_call` inputs/outputs other than the
  two additive inputs this feature adds (FR-021).
- Spec 059's `converged`/`progressed`/`handoff` decision table and
  formulas — this feature only adds a new `reason`-narrative branch and a
  new `routed` flag alongside them (D5, Out of Scope).
- `wing-commander-tasks-checkbox-count`'s own contract and behavior
  (Dependencies section — left unchanged).
- `tasks.md`'s own schema — no new checkbox marker, no new heading
  convention (FR-010, Out of Scope).
- `wing-commander-stage-findings`'s existing `defect`-kind behavior,
  outputs, and rendered text — the new `finding-kind` input's default
  reproduces today's output byte-for-byte (FR-021).
- Any vendored `.claude/skills/speckit-*` artifact, including
  `/speckit-converge`'s append-only contract (FR-016).
