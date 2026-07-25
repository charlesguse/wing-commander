# Building GitHub workflows that AI agents can actually succeed in

Every rule in this document was paid for by a real incident in this
repository's pipeline. The watchdog — the workflow whose only job is to catch
silent failures — sat dead for four days, then reported green while its own
agent had crashed in five seconds, then fabricated evidence by quoting its own
prompt. None of that was an agent being "bad at its job"; all of it was
workflow design that gave the agent (and the humans reading the run list) no
way to fail loudly. This is the design guide for not repeating it.

## The two prime rules

**1. Agents propose; scripts decide.** An LLM step may gather, classify, and
draft. It must never be the thing that decides whether a run passed, whether a
write happens, or whether an alert fires. Every consequential decision belongs
in a deterministic step that reads the agent's *structured* output — or
ignores it entirely.

**2. Green must be earned.** A workflow's conclusion is an API-visible claim.
Any path that swallows a failure (`continue-on-error`, `if: always()`,
best-effort reporting) must re-surface that failure somewhere a machine can
check — a conditional step that only runs on failure, an artifact, a non-zero
exit somewhere downstream. If "it broke" and "it worked" produce identical
API output, you have built a lie generator.

## Failure catalogue → countermeasures

### The workflow that never existed
A workflow listing its own `name:` under `workflow_run.workflows` is rejected
by GitHub's parser — and an unparseable workflow is **silently never
registered**. Valid YAML, valid bash, four days of nothing.
- Self-inspection goes in a *separate* workflow that listens to the first.
- Lint for it (`lint-workflows.yml` gate 2), and compare each file's declared
  `name:` against what GitHub actually registered (gate 1) — when GitHub
  can't parse a file it registers the *path* as the name, which is the only
  externally visible symptom. The real parser error is retrievable only by
  attempting a dispatch: the 422 body carries it verbatim.

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
down the reporting around it. Consequences you must design for:
- `steps.<id>.outcome` is the *pre*-rescue result; `steps.<id>.conclusion`
  and everything the **jobs API shows externally is the post-rescue value
  (success)**. A crashed agent step is invisible in the API's own step row.
- Therefore: pair every rescued agent step with a deterministic **read-back
  step** that branches on `outcome` and distinguishes *"the agent found
  nothing"* from *"the agent never ran"* — these are different claims and
  must never collapse into the same report.
- Make the truth machine-readable from outside: conditional reporter steps
  (`if: outcome-was-X`) show up as `success` vs `skipped` in the jobs API.
  An external verifier can then detect a hidden crash with two API calls and
  no log parsing. This is the backbone of `verify-watchdog-run.sh`.

### The scanner that kept catching itself
The single largest source of false alarms — 7 of 26 audited runs, one real
issue filed on a fabricated premise — was not the agent at all. A collector
grepped **raw job logs** for sentinel words (`stalled`, `turn budget
warning`, …). But GitHub Actions echoes every step's *own script source and
env block* into its log, between `##[group]Run …` and `##[endgroup]`. So the
scanner matched its own `sentinels='stalled|…'` definition, other steps'
`STALLED_LABEL: false` env dumps, and the *unexecuted* `printf '⚠️ Turn
budget warning…'` template of a warning that never fired — on essentially
every run. The downstream agent, handed "sentinel `stalled` matched in job
X" as a vetted signal, dutifully wrote stall narratives about jobs that had
succeeded in 9 seconds.
- **Never grep raw job logs.** Strip the `##[group]…##[endgroup]` echo
  blocks (script source, env, with) first, or better, match only an
  unmistakable emitted token (`WC-SENTINEL: stalled`) that cannot appear in
  unexecuted source text.
- **Give the judge the contradicting fact.** A signal that says "job X
  stalled" must carry job X's own conclusion and duration, and the quotable
  matched line — and the agent must be told a stall claim about a
  9-second-success job dies unless the line itself says otherwise.
- **Recompute claims before filing.** "Budget exceeded" is checkable against
  `num_turns` / `--max-turns`; "job stalled" against the job's conclusion.
  One API call kills the false positive at the gate that creates issues.
- The same echo also burned the *audit*: the prompt's illustrative example
  string appears verbatim in every job log (the prompt is echoed too), which
  looks exactly like the agent quoting its prompt in its output. Scope
  fabrication checks to the agent's **output artifact**, never the log —
  and don't put concrete, copyable examples of feared output in prompts in
  the first place; describe the shape, don't instantiate it.
- Require grounding: evidence must quote text that exists in the input the
  agent was given, and the prompt must say to drop findings that can't be
  grounded.

### The pass that was an empty file
A step can be green while its output is garbage: the agent SDK exited 0 with
an execution log of literally `[]` — no result record at all — and the
read-back treated "nothing parsed" as "zero findings", posting a clean bill
of health. "The agent found nothing" and "the agent produced nothing" are
different claims. Require the terminal result record to exist with
`is_error == false` and `subtype == "success"` before believing an empty
findings array; route everything else to the failure path.

### The stall that ran 44 minutes (and would have run six hours)
An agent step hung; the file had no `timeout-minutes` anywhere; GitHub's
default is six hours. Someone happened to cancel it.
- **Step-level** `timeout-minutes` on every agent step, sized generously
  above normal (a 1-minute agent gets 10). With `continue-on-error`, a
  timeout fails the *step* and flows into your read-back's "agent never
  finished" path — graceful degradation instead of a `cancelled` run.
- **Job-level** `timeout-minutes` on every job as the backstop.

### The verifier nobody verified
Watching the watchdog with another agent compounds error rates — that is how
the fabricated-evidence incident happened. The outer layer must be **cheaper
and dumber** than the layer it checks:
- run conclusion is honest;
- runtime sits in a band derived from the workflow's own successful history
  (catches both instant deaths and stalls; use a median with wide margins —
  this gates alerting, so false positives are expensive);
- the conditional truth-encoding steps all read `skipped`;
- the agent's terminal output record parses, `is_error` is false, and known
  fabrication markers are absent.
All of that is a shell script over the Actions API. On failure it exits
non-zero **and files a deduplicated issue** — a broken watchdog must page
someone, not journal quietly.

### The success you could never rehearse
If the only way to see a workflow run is to wait for organic traffic, its
failure modes are discovered in production. Keep a manually dispatched test
workflow that exercises the real chain end to end — and give it a
**failure-injection input** whose whole purpose is to prove red still shows
up as red. A monitoring path you have never seen fail is not monitoring.

## Mechanics that bite agents specifically

- **Structured output**: force a JSON schema (`--json-schema` inline — the
  CLI `JSON.parse`s the argument; a file path fails). Parse the terminal
  `result` record of the execution log; never trust agent narration about
  its own success.
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
- **`gh api --paginate` breaks on `/jobs`**: it concatenates JSON documents
  and jq chokes downstream. Use `?per_page=100`.
- **Job display names are not job ids**: reusable workflows prefix
  (`watchdog / collect`), matrix jobs suffix (`triage (step-stalled, ...)`),
  and a matrix parameter can itself contain `/ `. Normalize suffix first,
  then prefix.
- **Re-runs execute the workflow at the original SHA.** You cannot test a
  workflow fix by re-running an old failure; trigger a fresh run.

## Checklist for a new agent-bearing workflow

- [ ] Agent steps: `continue-on-error: true` + deterministic read-back that
      separates "found nothing" from "never ran"
- [ ] Agent steps: step-level `timeout-minutes`; every job: job-level backstop
- [ ] Agent output: JSON schema forced; terminal result record parsed; log
      uploaded as artifact `if: always()`
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
