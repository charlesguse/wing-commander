---
name: "container-shell-safety"
description: "Review a GitHub Actions change for container-shell-resolution defects: a run: step inside a caller-supplied-container job with no effective shell: bash, exposed to a non-bash default shell on an adopter's image. Use when reviewing or writing any workflow change that adds a container: block to a job, or adds/edits a run: step inside a job that already has one."
compatibility: "Reads .github/workflows/*.yml; needs python3 with PyYAML"
user-invocable: true
disable-model-invocation: false
---

# Reviewing container shell safety in GitHub Actions workflows

## The defect this exists to catch

A job's `container: image: ${{ inputs.container-image }}` is a caller's
own image, never one this repo controls. A `run:` step inside that job
with no effective `shell:` — its own, or a job- or workflow-level
`defaults: run: shell:` — has its shell resolved by Actions from whatever
that image offers. On an image without bash reachable the way Actions
expects, that resolves to `sh`, and a step whose body uses a bash-only
construct fails outright: `set -o pipefail` → `Illegal option -o pipefail`,
an array assignment → a syntax error, `[[ ... ]]` → the same. Not on some
runs against that image — on every one.

PR #293 shipped the fix for the one construct its own gate could prove:
`set ... pipefail`. It took two review passes to find all 38 sites (the
first pass covered 12), and a third finding caught a precedence bug in the
gate's own "is this covered" logic (step and job shell were OR'd together
instead of layered, which Actions itself never does). `pipefail` is one
bash-only construct out of several; a step using arrays, `[[ ]]`, `local`,
process substitution, or `read -d` is exactly as exposed, and none of
those trip a pipefail-shaped check.

## Gate 43 does not (and should not) catch all of this

`case_container_pipefail_steps_pin_shell_bash`
(`.github/scripts/verify-metrics-summary-record-emission.py`) is the
exact, auto-failing subset: it flags a step only when its body matches
`set ... pipefail`. Widening that gate to auto-fail on every
possibly-bash-only construct would false-positive constantly — `local`,
`[[`, and array-assignment-shaped text show up in strings, comments, and
genuinely POSIX-safe code far more often than they show up in a real
defect. A gate that fails loudly and often on things that are fine trains
reviewers to stop reading its output, which is worse than not having the
gate. This is the same reasoning `review-step-gating`'s Gate 24 /
`stranded-steps.py` split rests on: machine-check what can be proven
mechanically, hand a human the rest as an enumerated, judged list.

## Procedure

**0. Run the gate. It is exact, and it takes a second.**

```
python3 .github/scripts/verify-metrics-summary-record-emission.py
```

Anything it reports is a defect: a `set ... pipefail` step with no
covering `shell: bash`. Fix those before reading further.

**1. Then enumerate every remaining candidate. Do not do this by eye.**

```
python3 .claude/skills/container-shell-safety/scripts/unpinned-container-steps.py
python3 .claude/skills/container-shell-safety/scripts/unpinned-container-steps.py .github/workflows/rebase.yml
```

It reports every `run:` step in a caller-supplied-container job with no
effective `shell:`, regardless of whether it currently contains
`pipefail` — so it also catches "no bash-only construct yet, but nothing
stops the next edit from adding one." Findings where the step's body
matches a known bash-only construct (array assignment, `[[ ]]`, `local`,
process substitution, `read -d`, or a split-flag `pipefail` the gate's own
regex would miss) sort first and name which construct matched. It never
decides whether a finding is a real defect; that part is yours.

**2. For each finding, ask which of these it is.**

- *A near-certain defect* — a known bash-only construct matched, and
  nothing about the step's context makes that construct provably inert
  (e.g. it appears only inside a string literal being echoed, not
  executed).
- *Currently safe, likely to stay that way* — no construct matched, the
  step does something simple and unlikely to grow one (a single `gh`/`jq`
  call, a straight-line series of commands).
- *Currently safe, likely NOT to stay that way* — no construct matched
  today, but the step's purpose (looping over a matrix's worth of files,
  anything copy-pasted from a bash-pinned sibling step, accumulating
  results into a list) makes a future edit reaching for an array or
  `pipefail` plausible.

The first two need no urgent change (though pinning `shell: bash`
regardless costs one line and closes the door permanently). The third is
worth pinning now, before the construct that would have tripped Gate 43
lands and the step crashes on an adopter's image before anyone notices
the gap.

**3. The fix, when one is warranted, is always the same shape.**

Add `shell: bash` to the step (this repo's placement convention: right
after `id:` if present, otherwise right after `name:`, before `if:`/
`env:`). Prefer a job- or workflow-level `defaults: run: shell: bash`
over repeating the per-step key across many steps in the same
container-bound job — `wc_shell_pin.effective_shell` (shared by Gate 43
and this skill's script) already treats either form as covering a step,
so the gate will not fail a job that uses the shorter form.

## Reporting

State, per finding: the step (`file:line`, job name), which construct
matched (or that none did, and why you judged it safe or risky anyway),
and the fix applied or the reason none was needed. If a step's `run:`
mentions a bash-only word only inside a quoted string or a `#` comment —
not executed — say so explicitly; a false match that reads as a real
finding is the part that fools the next reviewer, the same failure mode
`review-step-gating`'s own reporting guidance warns about.
