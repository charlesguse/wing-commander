---
name: "review-step-gating"
description: "Review a GitHub Actions change for step-gating defects: guards that hard-fail on a failure something above them declared survivable and strand the teardown or degradation path below, always() used where !cancelled() was meant, and outputs an always()-gated reporter can never read. Use when reviewing or writing any .github/workflows change that touches an `if:`, a `continue-on-error:`, or a step that exits non-zero."
compatibility: "Reads .github/workflows/*.yml; needs python3 with PyYAML"
user-invocable: true
disable-model-invocation: false
---

# Reviewing step gating in GitHub Actions workflows

## The defect this exists to catch

`continue-on-error: true` on a step is a statement with a consequence:
*this step failing must not kill the job, because something below it handles
the failure.* A later step that hard-exits on that same failure silently
revokes the statement. The job status flips to failure, and **every**
subsequent step whose `if:` lacks `always()` / `!cancelled()` / `failure()`
is skipped — including steps with no `if:` at all, which carry an implicit
`success()`.

The handler that the `continue-on-error` was added for is exactly such a
step. It becomes unreachable dead code. Nothing in the file looks wrong: the
degradation path is right there, correctly written, sitting below a guard
that guarantees it never runs.

Five sites shipped this way in PR #221, all in one pattern — a new
`Fail loud on non-healthy agent verdict` step inserted between an agent step
that was *already* `continue-on-error: true` and the deterministic fallback
that tolerance existed for:

| Site | What the guard took away |
|---|---|
| `cleanup.yml` teardown-done | the fallback summary text, closing the lifecycle issue, `stage:done`, deleting five pipeline branches |
| `finalize.yml` finalize | `Verify agent output`, so `failed` was never set and the `always()`-gated failure callout skipped anyway |
| `auto-update-spec-kit.yml` evaluate-path | `Read back decision` → the needs-migration human routing |
| `auto-update-spec-kit.yml` e2e-stage | `Read back stage result` → all pass/fail reporting for the candidate |
| `auto-update-spec-kit.yml` comment-reply | `Read back interpretation` → the "ask for a clearer reply" prompt |

Gate 23 does not catch this: it checks that each agent call site *has* a
fail-loud step, never where that step sits. **Gate 24**
(`.github/scripts/verify-gate-24.py`) now covers the deterministic core of
the placement question — a guard that tests a tolerated signal *negatively*
and strands a later unprotected step that reads that same signal. It fires
on all five defects above and on nothing in the current fleet.

What Gate 24 deliberately cannot decide is everything else on this page: a
stranded *teardown* that never mentions the verdict, an `always()` that
admits more than it was meant to, two files comparing one value with
different operators. That judgement is what this skill is for. Run the gate
first; it is cheap and exact. Then read on for the part it can't do.

## The mechanics to hold in your head

- **No `if:` means `success()`.** A bare step is conditional. Reviewers read
  bare steps as unconditional; they are not.
- **`always()` also defeats the implicit `success()`.** Adding it to fix
  "this should run after a tolerated failure" also makes the step run on
  cancelled runs, and on runs where an unrelated earlier step failed. Reach
  for `!cancelled()` unless cancellation genuinely needs handling.
- **`continue-on-error: true` keeps the job green.** The step renders as
  failed, its `outcome` is `failure`, its `conclusion` is `success`, and
  nothing downstream is skipped on its account.
- **`steps.<id>.outcome` is the honest one.** `conclusion` launders a
  tolerated failure into `success`.
- **A skipped step's outputs are the empty string, not unset.** So
  `x != 'true'` is TRUE for a step that never ran — the reason a
  `valid != 'true'` guard fires on runs it has nothing to say about.
- **Job-level skip propagation is transitive.** A job whose `needs:`
  ancestor was skipped is itself skipped unless it carries `always()` /
  `!cancelled()`, however many hops away that ancestor is. (This repo lost
  its whole adopt chain to that in 2026-08; see PR #189.)

## Procedure

**0. Run the gate. It is exact, and it takes a second.**

```
python3 .github/scripts/verify-gate-24.py
```

Anything it reports is a defect, already named down to the guard and the
step it strands. Fix those before reading further.

**1. Then enumerate the rest mechanically. Do not do this by eye.**

```
python3 .claude/skills/review-step-gating/scripts/stranded-steps.py
python3 .claude/skills/review-step-gating/scripts/stranded-steps.py .github/workflows/cleanup.yml
```

It reports every step that (a) derives from a `continue-on-error` step,
(b) can exit non-zero, (c) is not itself `continue-on-error`, and (d) has
unprotected steps below it — listing exactly which ones are lost. It filters
out steps that could not have run on that path anyway (a guard gated
`verdict != 'healthy'` does not really strand a step gated
`verdict == 'healthy'`), and sorts first the findings where a stranded step
reads the very signal the guard fires on — the degradation-path shape. It
never decides whether a finding is a defect; that part is yours.

To see the pre-fix state of a file, or to review a workflow as it exists on
another ref, dump it first and pass the path:

```
git show HEAD:.github/workflows/cleanup.yml > /tmp/cleanup.yml
python3 .claude/skills/review-step-gating/scripts/stranded-steps.py /tmp/cleanup.yml
```

**2. For each stranded step, ask which of four things it is.**

- *A teardown that must complete* — closing an issue, deleting branches,
  releasing a lock, flipping a label the rest of the system reads.
- *The degradation path this tolerance exists for* — the fallback text, the
  read-back that turns a failed agent into a routed-to-a-human outcome.
- *A maintainer-facing report* — a callout or comment that is the only way a
  human learns the run went wrong.
- *Work that genuinely should not happen* — do not open a PR, do not flip
  the stage label, do not dispatch the next stage. **This is the common
  case, and it needs no change.**

The first three are defects. The fourth is the design.

**3. Apply the resolution that fits. There are four, all in use here.**

- **Hard exit in place** — nothing below needs to run. `clarify`, `plan`
  (auto/pr), `tasks` (auto/pr), `pr-conversation` (classify/act): 7 of the
  19 agent sites.
- **Hard exit in place, with `!cancelled()` on what must survive it** —
  `rebase.yml`, whose abandon/escalate arm and `Publish rebased branch` both
  carry it.
- **Defer the guard to the job's last steps** — `intake.yml`, so spec
  resolution, PR labelling, transcript upload and metrics all complete
  first, and the run still ends red.
- **`continue-on-error: true` on the guard itself** — the annotation is
  emitted where it belongs in the log, and the degradation path below owns
  the run's outcome. 10 of the 19 sites, including all five fixed in PR
  #221.

The rule that decides between the last two: **if the job has housekeeping
left that must finish and the run should still end red, defer the guard; if
the job has a deterministic fallback that handles the failure, tolerate the
guard and let the fallback own the outcome.** Never leave a hard exit
upstream of either.

**4. Check the three neighbouring mistakes while you are in there.**

- **An `always()`-gated reporter reading an output that a hard exit
  prevents.** `finalize.yml`'s failure callout was `always()`-gated and
  still skipped, because the step that sets `failed` never ran. `always()`
  on the reporter is worthless if the producer is stranded.
- **`always()` where the intent was "survive a tolerated failure".** Check
  what else it now admits: a legitimately *skipped* producer (empty-string
  outputs pass a `!= 'true'` test), a cancelled run, and double-reporting
  when a guard above already failed the job with a more accurate message.
  `intake.yml`'s `Fail on invalid agent result` had all three.
- **Two places computing the same signal with different boundaries.**
  `wing-commander-agent-verdict` used `counted >= intended` while
  `wing-commander-metrics-summary` used `ratio > 1`, so at exactly 100% of
  the budget the issue callout and the run summary described the same run
  differently. When a value is compared in two files, compare the operators.

## Reporting

State, per finding: the guard (`file:line`), the concrete scenario that
fires it, the named steps it strands, and what the user-visible damage is —
"the lifecycle issue is never closed and five branches survive", not "a step
may be skipped". If the newly-written `!= 'healthy'` branch below is
unreachable, say so explicitly; dead code that reads as a safety net is the
part that fools the next reviewer.
