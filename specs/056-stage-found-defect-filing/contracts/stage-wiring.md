# Contract: FR-001, FR-001a, FR-003, FR-006, FR-023, FR-029 — per-stage wiring

For each of the six stage workflows, the exact points this feature adds
to. "Read-back step" is the step `wing-commander-stage-findings` (see
`wing-commander-stage-findings.md`) must run after (FR-023); "channel
mode" is per `research.md` D2/D3.

| Stage (`.github/workflows/`) | Findings-filing-enabled default | Channel mode | Runs after (read-back step) | Agent step(s) gaining the FR-003 paragraph |
|---|---|---|---|---|
| `intake.yml` | `false` | `structured-array` (add `findings` to the existing `--json-schema`) | "Resolve created spec" (`id: created`) | "Create spec from issue" (`id: agent`) |
| `clarify.yml` | `false` | `structured-array` (add `findings` to the existing `--json-schema`) | "Determine clarification follow-up outcome" (`id: clarification`) | the clarify agent step |
| `plan.yml` | `false` | `fenced-block` | "Verify plan committed (auto)" / "Verify plan PR and flip stage label" (whichever the run's mode took) | both agent steps (`agent-auto`, `agent-pr`) |
| `tasks.yml` | `false` | `fenced-block` | "Verify tasks committed (auto)" / "Verify tasks PR (pr)" | both agent steps |
| `implement.yml` | `true` | `fenced-block` | "Consolidate final outcome" (`id: final`) — the single point that exists regardless of whether the cycle or the retry-at-escalation-model path ran (research.md D1: one attribution surface for the combined implement⟲converge turn) | "Implement and converge (cycle)" and "Implement and converge (retry at escalation model)" |
| `finalize.yml` | `true` | `fenced-block` | "Verify agent output" (`id: verify-agent-output`) | "Summarize changes and remaining work" (`id: summarize`) |

Each of these six workflows' `workflow_call.inputs` block gains the three
inputs `data-model.md`'s "Stage Filing Configuration" table names, and each
of the corresponding wrapper workflows
(`wing-commander-1-intake.yml` … `wing-commander-6-finalize.yml`) passes
them through as declared, typed inputs at its own `workflow_call` site to
the stage — never reading `vars.*`/`github.event.*` directly inside the
published stage (Principle VII).

## The FR-003 prompt paragraph

One paragraph, worded once and reused verbatim (a comment-pointer, per
CLAUDE.md's "repeated comment prose gets ONE canonical comment" rule,
resolved by copying the same literal text — not by a cross-file `-- see`
reference, since this text lives inside each stage's own prompt
composition and prompts are not one of the comment-pointer gate's checked
surfaces) across all six stages' prompt-composition steps, parameterized
only by that stage's own channel-mode instructions:

> If, while doing your own task, you notice a defect that is not your own
> task to fix — a gate that cannot fail its subject, a contract that
> contradicts the workflow it describes, a stale count, or similar — do
> not fix it and do not attempt to file it yourself. `<channel-specific
> instruction>` Then continue your own task unchanged.

The channel-specific instruction shows the agent the finding's exact
shape (#420 — the first live run with filing enabled lost a real finding
because the paragraph as first shipped described the object in prose and
the agent wrote YAML with invented keys). For the fenced-block stages it
says the block MUST be JSON, not YAML, an array with one object per
finding, and spells out a one-element example carrying every key of
`.github/schemas/stage-finding.schema.json` with `detail` marked optional;
for the structured-array stages it names the same keys in prose and the
stage's `--json-schema` declares them, closed, under `findings.items`.
Both tell the agent that `gate_or_artifact` is half of the dedup key and
must be a stable name, never a sentence, and that an empty array means
nothing to report.

`verify-stage-findings-wiring.py` checks for this paragraph's presence by
a stable substring (e.g. `"do not attempt to file it yourself"`), not by
byte-identity, so the channel-specific clause can legitimately differ
between the two channel modes without the gate treating that as drift.
It also requires every prompt carrying the paragraph to name each
required key of the schema file, quoted, and the two structured stages'
`findings.items` to require the same keys with `additionalProperties`
closed — the schema file stays the single home for the shape.

## Read-only stages and the write-tool question (FR-004)

None of the six stages' tool allowlists gain a `gh issue create` (or any
new write) grant for this feature — confirmed for all six today (none
currently grants it; `implement.yml` was directly grepped and confirmed
empty). The findings channel itself needs no new tool grant because it is
carried in output every stage already produces (its final message, or its
existing structured result) — this is exactly why FR-006 rules out a
`findings/*.json` file as the channel: writing one would need a `Write`
grant `intake`/`clarify`'s (and future discovery stages') read-only
posture does not otherwise require.
