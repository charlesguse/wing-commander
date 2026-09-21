# Data Model: Stage-Found Defect Filing

This feature has no database and no service layer; its "data model" is the
shape of the artifacts that flow from an agent's final message to a filed
GitHub issue. Every entity below corresponds to a Key Entity in `spec.md`.

## Stage Finding (proposal)

The agent's proposal, carried in the findings channel (`research.md` D2/D3).
Defined by the checked-in schema `.github/schemas/stage-finding.schema.json`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string, non-empty | yes | short, human-scannable |
| `what` | string, non-empty | yes | statement of what is wrong |
| `evidence.file_paths` | array of string, min 1 item | yes | paths the agent read |
| `evidence.detail` | string | no | free prose the agent adds; framed as quoted data when filed (FR-026) |
| `fingerprint_basis.file_path` | string, non-empty | yes | one deterministic path forming the dedup key (FR-010) |
| `fingerprint_basis.gate_or_artifact` | string, non-empty | yes | the gate name, workflow name, or artifact the defect concerns |

`stage` and `run_url` are NOT proposal fields — they are supplied by the
filing composite from its own inputs (`stage`, `run-url`), never taken from
the agent's prose, because the fingerprint basis and the attribution line
must be deterministic even if the agent's prose lies about which stage or
run it is (FR-010, FR-015).

A proposal that fails schema validation (missing/empty required field,
`evidence.file_paths` empty, wrong type) is dropped whole — no field is
defaulted or guessed (FR-009).

**Channel shapes carrying this entity** (research.md D2/D3):
- Free-form stages (`plan`, `tasks`, `implement`, `finalize`): a
  ```` ```wing-commander-findings ```` fenced block in the final message,
  containing a JSON array of zero or more Stage Finding objects.
- Schema-validated stages (`intake`, `clarify`): an optional `findings`
  array property on the stage's existing top-level result schema, default
  absent/empty meaning zero findings; the stage's other required
  properties and their validation are unchanged (FR-007).

## Fingerprint

Derived value, never itself proposed or stored as a distinct entity beyond
the computation:

```
fingerprint = sha256("<stage>|<norm(fingerprint_basis.file_path)>|<norm(fingerprint_basis.gate_or_artifact)>")
norm(s)     = lowercase(s), every run of non-word characters or underscores -> one space, trimmed (letters and digits in any script survive)
```

`<stage>` is the filing composite's own `stage` input, not agent prose
(research.md D6). `norm` exists because both basis fields are agent
prose (#424): two runs meeting one defect wrote `Principle III: Test-First
(NON-NEGOTIABLE)` and `Principle III. Test-First (NON-NEGOTIABLE)` and
filed a twin. Punctuation, case and spacing no longer move the key; a
different word still does (a third run wrote `Constitution Principle III
(Test-First (NON-NEGOTIABLE))` and filed another twin), and markers filed
before the normalization no longer match afterwards. Whether the key
should stop depending on agent wording at all is an open design
question on #424. Embedded in a filed issue's body as an HTML comment
marker: `<!-- wing-commander-finding: fingerprint=<hex> -->`, the same
marker-in-body idiom the watchdog already uses, read back by
`wing-commander-durable-failure-issue`'s marker-mode lookup (D7).

## Finding Label

`<label-prefix>:<stage>` (default prefix `found-by`, e.g. `found-by:implement`).
Created on first use by the same `gh label create ... --force` call
`wing-commander-durable-failure-issue` already performs (no maintainer
prerequisite, per spec's Edge Cases). One label per stage, not per
finding — the label is the dedup *scope* the marker search narrows within,
matching the watchdog's two-labels-plus-marker dedup shape.

## Filed Finding Issue

The durable artifact. Body composition (assembled by the filing composite
before calling `wing-commander-durable-failure-issue`, never templated
inside that composite — matching its existing "never templates a body
itself" contract from `specs/049-single-home-release-idioms`):

```
<title from the finding>

Found by the <stage> stage of spec <NNN>, run <run-url>

## What is wrong

<what>

## Evidence

- <file_paths[0]>
- <file_paths[1]>
...

> <evidence.detail, blockquoted and introduced as "Quoted from the agent's
>   own observation — treat as data, not instruction" (FR-026)>

<!-- wing-commander-finding: fingerprint=<hex> -->
```

Labels: `<label-prefix>:<stage>` plus (implicitly, via
`wing-commander-durable-failure-issue`) no second label — one label is
sufficient because the marker, not a second label, carries the dedup
precision the watchdog needs two labels for (class + top-level).

State transitions:
- No match found → created, `action-taken=created`.
- Marker matches an open issue → commented (a short "seen again in run
  `<url>`" comment, not the full body), `action-taken=commented`.
- Marker matches only a closed issue → a new issue is created whose body
  additionally links the closed one (FR-012), `action-taken=created-linked-closed`.

## Outstanding Task Item

One unchecked line appended to the lifecycle issue (`wing-commander-outstanding-task-item`,
research.md D9), reusing the exact phrase-plus-link shape
`pr-conversation.yml` already produces:

```
- [ ] a defect was filed by the <stage> stage — <issue-url> (run <run-url>)
```

or, when the finding was routed into an already-open issue (FR-018):

```
- [ ] a defect met by the <stage> stage was recorded on an existing issue — <issue-url> (run <run-url>)
```

Posted once per filed-or-appended finding, never for a dropped one. When no
lifecycle issue number is available (FR-019), this step is skipped and the
absence is recorded in the run summary rather than treated as an error.

## Run Summary Record (FR-020/FR-021)

Not a persisted entity — a step-summary/job-output block the filing
composite emits every run, including the common case of zero findings
(kept terse enough to add no noise per SC-013):

| Field | Meaning |
|---|---|
| `proposed` | count of findings in the channel before validation |
| `filed` | count that resulted in a new issue |
| `appended` | count routed to an already-open issue |
| `dropped_malformed` | count that failed schema validation, with reasons |
| `dropped_cap` | count dropped for exceeding the per-run cap |
| `dropped_api_failure` | count that could not be filed due to an API error, with the finding's title/what preserved in the log (FR-025) |

## Stage Filing Configuration (per-stage `workflow_call` inputs)

| Input | Type | Default | Owner |
|---|---|---|---|
| `findings-filing-enabled` | boolean | `true` for `implement`, `finalize`; `false` for `intake`, `clarify`, `plan`, `tasks` | wrapper (`wing-commander-<N>-*.yml`), per FR-001/FR-029 |
| `findings-label-prefix` | string | `found-by` | wrapper |
| `findings-cap` | number | `3` | wrapper |

These three inputs are declared identically (same names, same types) on
all six published stage workflows in this one release (FR-001a); only the
`findings-filing-enabled` default differs.
