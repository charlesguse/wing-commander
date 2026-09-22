---
name: "spec-cross-reference"
description: "Cross-reference code review findings against the governing spec's FR-*/SC-* requirements before finalizing severity. Use when reviewing a PR whose changed files live under a directory a specs/NNN-*/ spec references (e.g. via its tasks.md or plan.md) -- never force this on a PR with no governing spec (a general bug fix, a tooling change, an infra tweak)."
compatibility: "Reads specs/*/{spec,plan,tasks}.md and specs/*/contracts/*.md; needs python3"
user-invocable: true
disable-model-invocation: false
---

# Cross-referencing a review against its governing spec

## The defect this exists to catch

A finding rated by code-shape alone drifts from what the feature actually
promises. Two failure directions, both seen in the same review (PR #451,
spec 057):

- **Under-rated.** A bug looked like an ordinary staleness check gone wrong
  until cross-referencing found FR-036 names the *exact* scenario ("right
  after a push the PR's check summary still shows the previous head's run")
  the code was supposed to handle and doesn't. That is a named-requirement
  violation, not a plausible edge case — it should outrank findings that
  have no such backing.
- **Over-rated.** A hypothesized race (two board-loop cycles landing two
  PRs for the same issue) looked plausible in isolation. FR-048's own
  concurrency group (`group: wing-commander-board-loop`, one item in flight
  repository-wide, applied to every trigger in the file) rules the race out
  structurally. Without checking the spec, that finding would have shipped
  at full severity instead of being flagged as refuted.

A finding can also be *reframed* rather than moved: a missing input on a
redrive looked like a silent-failure bug until FR-043 turned out to already
anticipate "a failed or undispatchable proof run" — the real gap was that
the evidence recorded doesn't say *which* of the two happened (an FR-044
legibility problem), not that the run stays open.

None of this is available from the diff alone. It only shows up by reading
the spec the changed code is supposed to satisfy.

## The one thing this skill cannot do

There is no gate for "did the reviewer check the spec" the way Gate 24
checks step-gating — matching a finding to a requirement is a judgement
call, not a byte comparison. What *is* mechanical, and what the script
below does instead of leaving it to memory, is answering the yes/no
question that judgement call depends on: **does a governing spec exist for
this diff at all, and if so, what does it require?** Skipping that lookup
is the actual failure mode (forgetting the spec exists, not misjudging a
requirement once it's in front of you).

## Procedure

**0. Find the governing spec. Do not rely on remembering which one it is.**

Run this with the PR's branch checked out (the spec's own `tasks.md` won't
exist yet on `main` for an unmerged feature):

```
git diff --name-only main...HEAD | python3 .claude/skills/spec-cross-reference/scripts/find_governing_spec.py
```

It ranks every `specs/*/` directory by how many changed paths its own
`tasks.md`/`plan.md`/`contracts/*.md` reference literally, and prints the
top match's full FR-*/SC-* list so nothing has to be re-read from memory.

**If it reports no governing spec, stop here.** A general bug fix, a
tooling change, or an infra tweak has nothing to cross-reference against —
do not manufacture a requirement mapping for a spec-less change, and do not
let a finding's severity go unstated just because this step found nothing.

**1. For each finding, check it against the printed FR-*/SC-* list.**

Ask three questions, in order:

- Does an FR name this exact scenario (not just the general area)? If so,
  the finding is a named-requirement violation — elevate it, and quote the
  requirement's own wording in the report.
- Does an FR or a structural guarantee elsewhere in the spec (a
  concurrency group, an idempotency key, an allowlist) rule out the
  precondition the finding depends on? If so, the finding is weakened or
  refuted — say so explicitly rather than dropping it silently.
- Does the requirement anticipate the failure but describe a different
  consequence than the one the finding claims? Reframe the finding to
  match what the spec actually requires (see the FR-043/FR-044 example
  above), rather than keeping the original framing.

A finding with no matching FR/SC is not therefore wrong — most cleanup,
efficiency, and reuse findings will not map to anything. Say plainly that
no requirement bears on it, rather than searching for a strained fit.

**2. Re-verify structural claims the spec relies on before trusting them.**

A spec bullet asserting a guarantee ("the loop runs under a global
concurrency group") is a claim about the code, not proof of it. Read the
actual file (as with `board-loop.yml`'s `concurrency:` block above) before
letting it downgrade a finding — the spec can be aspirational in a way the
shipped code isn't.

## Reporting

State, per finding: which FR/SC (if any) it maps to, whether that
elevates, refutes, reframes, or leaves the finding's severity unchanged,
and the requirement's own quoted wording — not a paraphrase, so the report
can be checked against the spec directly. For a finding with no governing
spec, say so in one line instead of leaving the cross-reference step
implicit.
