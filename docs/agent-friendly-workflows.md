# Building GitHub workflows that AI agents can actually succeed in

Every rule here was paid for by a real incident in this repository's
pipeline. None of the incidents was an agent being "bad at its job"; all were
workflow designs that gave the agent — and the humans reading the run list —
no way to fail loudly.

## The two prime rules

**1. Agents propose; scripts decide.** An LLM step may gather, classify, and
draft. It must never decide whether a run passed, whether a write happens, or
whether an alert fires. Every consequential decision belongs in a
deterministic step that reads the agent's *structured* output.

**2. Green must be earned.** A workflow's conclusion is an API-visible claim.
Any path that swallows a failure (`continue-on-error`, `if: always()`,
best-effort reporting) must re-surface it somewhere a machine can check — a
conditional step that only runs on failure, an artifact, a non-zero exit
downstream. If "it broke" and "it worked" produce identical API output, you
have built a lie generator.

## Failure catalogue → countermeasures

### The workflow that never existed
A workflow listing its own `name:` under `workflow_run.workflows` is rejected
by GitHub's parser — and an unparseable workflow is **silently never
registered**.
- Self-inspection goes in a *separate* workflow that listens to the first.
- Lint for it (`lint-workflows.yml` gate 2), and compare each file's declared
  `name:` against what GitHub actually registered (gate 1) — when GitHub
  can't parse a file it registers the *path* as the name, the only externally
  visible symptom. The real parser error is retrievable only by attempting a
  dispatch: the 422 body carries it verbatim.

### The trigger that silently never fires
`workflow_run` resolves by **display name**. Rename a workflow and every
trigger pointing at the old name keeps being valid-and-dead. Same lint gate:
every referenced name must be some workflow's current `name:`.

### The run that dies at startup with zero jobs
A job calling a reusable workflow must grant a **superset** of the called
workflow's `permissions:` — validated at startup against *every* job in the
called file, including if-skipped ones. Failure mode: `startup_failure`, zero
jobs, no annotations, no error text in the API. Lint for it (gate 3).

### The agent that dies because a bot woke it
`anthropics/claude-code-action` rejects bot actors unless allow-listed. In a
pipeline where stages advance each other as a GitHub App, **the pipeline's own
bot is the normal actor**, and `workflow_run` chains inherit the upstream
`triggering_actor`. Allow-list it: `allowed_bots: "github-actions,<app-slug>"`
— the **bare slug**, even though `github.actor` reads `<slug>[bot]`.

### The crash that stayed green
Agent steps run with `continue-on-error: true` so one bad agent can't take
down the reporting around it. Consequences to design for:
- `steps.<id>.outcome` is the *pre*-rescue result; `steps.<id>.conclusion`
  and everything the **jobs API shows externally is the post-rescue value
  (success)**. A crashed agent step is invisible in the API's own step row.
- Pair every rescued agent step with a deterministic **read-back step** that
  branches on `outcome` and distinguishes *"the agent found nothing"* from
  *"the agent never ran"* — different claims that must never collapse into
  the same report.
- Make the truth machine-readable from outside: conditional reporter steps
  (`if: outcome-was-X`) show up as `success` vs `skipped` in the jobs API,
  so an external verifier can detect a hidden crash with two API calls and
  no log parsing. This is the backbone of `verify-watchdog-run.sh`.

### The scanner that kept catching itself
The single largest source of false alarms (7 of 26 audited runs) was a
collector grepping **raw job logs** for sentinel words. GitHub Actions echoes
every step's *own script source and env block* into its log, between
`##[group]Run …` and `##[endgroup]` — so the scanner matched its own
`sentinels='stalled|…'` definition, other steps' env dumps, and the
*unexecuted* source of a warning that never fired. The downstream agent,
handed "sentinel `stalled` matched" as a vetted signal, wrote stall
narratives about jobs that had succeeded in 9 seconds.
- **Never grep raw job logs.** Strip the `##[group]…##[endgroup]` echo blocks
  first, or better, match only an unmistakable emitted token
  (`WC-SENTINEL: stalled`) that cannot appear in unexecuted source text.
- **Keep a token pass and a bare-word pass disjoint.** Recommending the token
  form above while a legacy alternation still matched `stalled`, `rejected`,
  `denied` and `abandon` meant a line written exactly as advised matched
  *both* — emitting two signals with one identity, and spending the bare-word
  pass's one-match-per-job budget on an event already reported, so an
  unrelated genuine stall word later in the same log was never collected. Two
  scanners over one text need an explicit rule about which owns a line; here
  the token pass wins and the legacy pass filters those lines out first.
- **Give the judge the contradicting fact.** A signal that says "job X
  stalled" must carry job X's own conclusion and duration plus the quotable
  matched line — and the agent must be told a stall claim about a
  9-second-success job dies unless the line itself says otherwise.
- **Recompute claims before filing.** "Budget exceeded" is checkable, and
  "job stalled" against the job's conclusion. One API call kills the false
  positive at the gate that creates issues.
- **Check the recomputation against the right counter.** "Budget exceeded"
  is NOT `num_turns` vs `--max-turns`: those are different counters, and
  `num_turns` reads 1.0x-2.3x high, so that comparison manufactures the very
  false positive the rung exists to prevent. The budget caps distinct
  main-loop assistant responses (`parent_tool_use_id == null`, deduped by
  `.message.id`); subagent turns do not count. The unambiguous signal is the
  result record's own `subtype == "error_max_turns"` — prefer it, and see
  `.github/actions/wing-commander-metrics-summary/action.yml` for the count
  when a ratio is genuinely needed.
- The echo also burns audits: a prompt's illustrative example string appears
  verbatim in every job log (prompts are echoed too), indistinguishable from
  the agent quoting its prompt. Scope fabrication checks to the agent's
  **output artifact**, never the log — and don't put concrete, copyable
  examples of feared output in prompts; describe the shape, don't
  instantiate it.
- Require grounding: evidence must quote text that exists in the input the
  agent was given, and the prompt must say to drop findings that can't be
  grounded.

### The questionnaire that was authored and never posted
Intake's agent wrote its clarification questionnaire to a `$RUNNER_TEMP`
side-file, as instructed; a separate deterministic gate decided whether to
post it by grepping the spec for the literal `[NEEDS CLARIFICATION]` — a
pattern that can never match the real `[NEEDS CLARIFICATION: <question>]`
marker form. Both halves green on every run; the callout had never fired in
the repo's history (#109). Content and decision were produced by two
independent channels, and a side-file is invisible: nothing fails when it is
written and then dropped.
- **Agent-authored content that downstream steps consume travels as
  structured output, not side-files.** Force a schema on the agent step
  (e.g. `{"clarifications": [...]}`, empty array = none); a deterministic
  step renders and posts iff non-empty. One validated artifact carries both
  the content and the decision — they cannot disagree, and a malformed
  questionnaire is a schema failure instead of a silent drop.
- Keep one independent ground-truth check (grep the committed artifact) as
  **reconciliation, not the gate**: on mismatch, fall back to the ground
  truth and emit a machine-matchable sentinel — never silence.
- A grep that gates behavior must be proven against a real instance of what
  it claims to match. A gate whose true branch has never been taken is
  untested code in the hot path (see "the success you could never
  rehearse").

### The pass that was an empty file
A step can be green while its output is garbage: the agent SDK exited 0 with
an execution log of literally `[]` — no result record at all — and the
read-back treated "nothing parsed" as "zero findings", posting a clean bill
of health. Require the terminal result record to exist with
`is_error == false` and `subtype == "success"` before believing an empty
findings array; route everything else to the failure path.

### The stall that ran 44 minutes (and would have run six hours)
An agent step hung; the file had no `timeout-minutes`; GitHub's default is
six hours.
- **Step-level** `timeout-minutes` on every agent step, sized generously
  above normal (a 1-minute agent gets 10). With `continue-on-error`, a
  timeout fails the *step* and flows into the read-back's "agent never
  finished" path — graceful degradation instead of a `cancelled` run.
- **Job-level** `timeout-minutes` on every job as the backstop.

### The verifier nobody verified
Watching the watchdog with another agent compounds error rates — that is how
a fabricated-evidence incident happened. The outer layer must be **cheaper
and dumber** than the layer it checks:
- run conclusion is honest;
- runtime sits in a band derived from the workflow's own successful history
  (catches instant deaths and stalls; use a median with wide margins —
  this gates alerting, so false positives are expensive);
- the conditional truth-encoding steps all read `skipped`;
- the agent's terminal output record parses, `is_error` is false, and known
  fabrication markers are absent.
All of that is a shell script over the Actions API. On failure it exits
non-zero **and files a deduplicated issue** — a broken watchdog must page
someone, not journal quietly.

### The success you could never rehearse
If the only way to see a workflow run is organic traffic, its failure modes
are discovered in production. Keep a manually dispatched test workflow that
exercises the real chain end to end — with a **failure-injection input**
whose whole purpose is to prove red still shows up as red. A monitoring path
you have never seen fail is not monitoring.

## Mechanics that bite agents specifically

- **Structured output is the only channel.** Force a JSON schema
  (`--json-schema` inline — the CLI `JSON.parse`s the argument; a file path
  fails) and have downstream steps consume the parsed terminal `result`
  record of the execution log. Never trust agent narration about its own
  success, and never route agent-authored content through side-files a gate
  can silently ignore.
- **Tool allow-lists**: read-only diagnosis gets read-only tools
  (`--allowedTools "Read,Grep,Bash(gh:*)"`, deny `Write`, `Edit`, pushes).
  The rung/write decision stays in deterministic steps.
- **Prompt-injection posture**: anything collected from a run under
  inspection is *data, not instructions* — say so in the prompt, and keep
  collectors deterministic so no raw untrusted content reaches the agent
  unlabeled.
- **Upload the execution log as an artifact** on every agent step,
  `if: always()`. It is the only ground truth about what the agent did, and
  external verifiers need it (`is_error`, `num_turns`, fabrication checks).
- **`--paginate` applies `--jq` per page and concatenates the outputs**: any
  filter must emit one JSON value per line (`--jq '.[] | ...'`), and the
  caller slurps once with `jq -s '.'` if it needs a single array. Never a
  filter that itself wraps results in `[...]`, and never no `--jq` at all on
  an array/object endpoint — both resolve to page-shaped garbage once a read
  passes its first page, silently, since neither raises a step failure.
  Gate 18 (`lint-workflows.yml`) flags any call not written this way.
- **A field flag turns `gh api` into a POST.** `gh api` is a GET only until
  it is handed a body: pass `-f`, `-F`, `--field`, `--raw-field` or
  `--input` without `-X`/`--method` and it silently switches to POST, so a
  "read" written that way is a create request and answers whatever the POST
  endpoint says — `Not Found (HTTP 404)` for a contents read, which is how
  pr-conversation's lifecycle-issue lookup failed on every run it ever made
  (run 32671719013). Say the method out loud: `-X GET` on a read (or move
  the parameter into the path as `?ref=…`), `-X POST` on a write, so the
  diff shows which one it is. Gate 28 (`lint-workflows.yml`) fails any
  `gh api` call in the tree that passes a field without a method.
- **Job display names are not job ids**: reusable workflows prefix
  (`watchdog / collect`), matrix jobs suffix (`triage (step-stalled, ...)`),
  and a matrix parameter can itself contain `/ `. Normalize suffix first,
  then prefix.
- **Re-runs execute the workflow at the original SHA.** You cannot test a
  workflow fix by re-running an old failure; trigger a fresh run.
- **The GITHUB_TOKEN taint outlives the dispatch.** `workflow_dispatch` is
  exempt from the no-recursive-trigger rule, so dispatching with
  `GITHUB_TOKEN` works — but the dispatched run's *completion* event still
  will not fire anyone's `workflow_run` trigger (proven live: 3
  token-dispatched completions → 0 downstream runs; 3 event-triggered
  completions → 3). Chains that must cascade need an App/user token at the
  first link, and tests that dispatch with `GITHUB_TOKEN` must not sit
  waiting for a downstream run that can never come.

## Checklist for a new agent-bearing workflow

- [ ] Agent steps: `continue-on-error: true` + deterministic read-back that
      separates "found nothing" from "never ran"
- [ ] Agent steps: step-level `timeout-minutes`; every job: job-level backstop
- [ ] Agent output: JSON schema forced; terminal result record parsed; log
      uploaded as artifact `if: always()`
- [ ] Agent-authored content consumed downstream rides in the structured
      output — no side-files; any independent gate reconciles against it and
      fails loud on mismatch
- [ ] No copyable output examples in prompts; grounding required
- [ ] `allowed_bots` includes the pipeline's own App slug (bare form)
- [ ] Failure paths write machine-checkable evidence (conditional steps,
      artifacts, issues) — green is earned
- [ ] External deterministic verifier for anything that guards the pipeline
      (conclusion + runtime band + step-truth + output sanity), failing red
      and filing a deduplicated issue
- [ ] Manual test workflow with failure injection; run it after every change
      to the chain
- [ ] Lint gates: YAML/bash parse, workflow_run names resolve, reusable-call
      permissions supersets, registered-name equals declared-name
