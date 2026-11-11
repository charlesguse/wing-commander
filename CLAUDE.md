# Working on wing-commander

Orientation, for local and cloud sessions (stage agents can skip it):
[README.md](README.md) says who acts in this repository and how the owner
drives it; [docs/reference.md](docs/reference.md) lists every loop, default,
limit and switch, and says which changes must update it.

## Before pushing

This section addresses the implement stage agent and human/local sessions
only — the intake, clarify, plan, and tasks stage agents are not addressed
by it.

Run the full PR-time gate suite locally — it is derived from what
lint-workflows.yml actually invokes, so it is the same set CI runs:

    python .github/scripts/run-local-gates.py

A change that touches any `if:`, `continue-on-error:`, or failing step in a
workflow should also get a pass from the `review-step-gating` skill.

A change that adds a `container:` block to a job, or a `run:` step inside
one, should also get a pass from the `container-shell-safety` skill.

## Shared logic has exactly one home

Before pasting a `run:` block, jq program, or shell helper into a second
workflow, move it instead:

- Cross-workflow shell/jq belongs in a composite action under
  `.github/actions/` (scripts shared between composites go in
  `.github/actions/_shared/`), with the workflows consuming its outputs.
  Each call site keeps at most a one-line fallback for the case where the
  composite never ran.
- Repeated comment prose gets ONE canonical comment; every other site
  points at it (`-- see clarify.yml`). Gate 47
  (verify-comment-canonical-pointers.py) enforces the pointers.

Why this is worth the detour: a pasted copy is invisible until the first
divergent fix. The per-run cost line was once pasted into 12 run-blocks
across 9 stage workflows, where a rounding fix would have had to land 12
times with nothing failing on a drifted copy; it now lives solely in
`wing-commander-metrics-summary`'s `cost-line` output, and
`verify-metrics-summary-record-emission.py` fails if a copy of the
formatter reappears in a workflow. When you consolidate something like
this, add the "single home" check to the nearest existing gate the same
way — a rule with no gate behind it lasts until the next session.

## Deciding without the owner

This section addresses the owner's own sessions, local and cloud: the ones
the owner starts and talks to. Stage agents and the board loop's agents are
not addressed by it; they keep the rules their own stage gives them.

The owner guides this repository and does not gate it (owner decision,
2026-11-10). Sort every choice by whether it is reversible, not by whether
it involves a trade-off:

- **Decide and record** a reversible choice: one revert or one switch
  undoes it, it stays inside the constitution and the published contract,
  and it needs no new credential, permission, repository setting or model
  tier. Take the option the evidence favours, write a decision record, and
  carry on.
- **Build and compare** when two or three options are each about an hour
  of agent work or less: one branch each, the same checks on all. Decide
  when one clearly wins. When none does, bring the owner the comparison.
- **Ask first** on new ground: no earlier decision of the same shape
  (`answer-from-precedent` skill), a break in the published contract, a
  security boundary, a constitution amendment, spend or model tier,
  deleted history, a reversal of a decision the owner made, or a change to
  this section or to a list of what is the owner's. Ask with the options,
  the evidence and a recommendation.

A question blocks only the work that depends on its answer. Keep going on
the rest.

The owner's word stops any of this: an instruction in the session, a
changes-requested review, the hold label, or a line under "Owner
decisions" on the Roadmap issue. Read that list before you merge a spec PR
or promote a proposal.

A **decision record** is a comment that starts
`**Session decision (YYYY-MM-DD):**` on the pull request or issue the
decision governs. It gives what was chosen, the options considered, the
evidence, and the undo (the revert or the switch).
`gh search issues "Session decision"` is the log the owner reads
afterwards. Two places start a pipeline run when commented on: a
lifecycle issue while its spec is in clarify, and a final PR. A record
about either goes on the Roadmap issue and names it.

### Merging on evidence

Each condition is a lookup, not a judgment of the work. Read it from
GitHub at the moment of the merge, post what you read in a decision
record, then squash-merge pinned to that head.

- **A fix PR that one of the owner's sessions opened** merges without
  asking when every check run on the exact head SHA has completed
  successfully (a head with no checks is not green), the latest
  `review-until-clean` pass reviewed that head and is CLEAN, and the
  merging session did not review it. When the loop's thrash check stops
  it, choose one targeted pass with a different method or a smaller scope
  yourself, and record why. A second stop, or a merge with a finding
  still open, goes to the owner.
- **A spec PR** merges without asking under constitution X's spec-merge
  rule. Read the rule and check every condition it lists. A review pass
  counts when a fresh session ran it, or it is a round of
  `spec-pr-review.yml`, and its report on the PR names the head it
  reviewed and says whether it is clean. The three-round limit below
  still holds: two clean passes in a row inside three, or the owner
  decides.
- **Every other merge waits for the owner's direction for that pull
  request:** a plan PR, a final PR, a PR the pipeline opened and left
  open, a PR from outside the owner's sessions, and any PR that touches
  `.specify/memory/constitution.md`.

### Promoting a proposal

A session applies `spec-request` to a `spec-proposal` under constitution
X's promotion rule. Read the rule and check every condition it lists.

- Count the lifecycles in flight first:
  `gh issue list --state open --limit 500 --json number,labels --jq '[.[] | select(any(.labels[].name; . == "spec-request" or startswith("spec:")))] | length'`.
  Promote only when the count is under three.
- Take proposals in the order the Roadmap issue lists them, "Queued"
  before "Proposed".
- Post the decision record on the proposal, with the count, **before**
  applying the label. Once intake has labelled the issue, a comment there
  starts a clarify run.
- Intake ends in clarification questions. Answer the ones a precedent
  settles and raise the rest (`answer-from-precedent` skill).

## Working the issue board

The board has three lanes, and only the first one can wait on the owner:

- **Roadmap** — specs the owner chose. The open `disposition:tracking`
  issue titled "Roadmap" (#890 at the 2026-10-01 board reset) lists what
  is in flight, queued and parked. `spec-request` is applied by the owner,
  or by a session under "Promoting a proposal" above.
- **Maintenance** — small defects from stages, reviews and the watchdog.
  They are fixed directly, never turned into specs. Collect them as
  checklist lines on the open `disposition:tracking` issue titled
  "Maintenance backlog" (#889 at the reset), not as one issue each.
  Edit that issue's body only through `python .github/scripts/board_backlog_edit.py`
  (fetch, apply, write, read back, retry); never a blind whole-body write, which
  loses a concurrent edit by the board loop or another session.
- **Signals** — watchdog classes that are recoveries or cosmetic, not
  defects (`denied-tool`, `narrative-drift`). The watchdog reports them
  on the lifecycle issue and files nothing (watchdog.yml's `Determine
  issue-filing eligibility`).

The open `disposition:tracking` issue titled "Board status" is rewritten
daily by `board-status.yml` from the board itself: what waits on the
owner, what the pipeline is working on, and main's CI. Read it before
the board. When the owner asks what's on them, the `whats-on-me` skill
renders that report live and adds what only the session knows.

Keep at most three lifecycles in implement at once; the rest wait in the
Roadmap issue's "Queued" list. A lifecycle that has to wait for the
owner's answers belongs in "Parked", closed with the `parked` label, not
open on the board.

Open issues are worked in this order: triage, route, fix, review, merge,
prove. Each step has a rule.

- Triage against current main before touching code. Read the commits
  since the issue was filed and the run it cites. A watchdog
  `pipeline-defect` whose execution-output artifact records an API 429
  (a `rate_limit_event`, `api_error_status: 429`, one turn, zero cost) or
  an upstream action bump is closed with that evidence quoted, not fixed.
- Before closing any issue, check that no waiver register cites it as its
  tracker: `grep -rnE '"#N"|issue *= *\([^)]*\bN\b' .github/scripts/`
  covers the `*-waivers.json` registers and the `EXEMPT_*` tables (a
  `decided_by` hit is provenance and can stay). Gate 124
  (`verify-waiver-citations.py --check-open`) runs on pushes to main and
  on the daily schedule, never on a pull request, so closing a cited
  issue turns main red while every PR stays green. Repoint the waiver at
  the issue that now tracks the work, usually the Maintenance backlog, in
  the same sitting.
- Route by shape. A change that is deterministic and gate-shaped (a new
  `verify-*.py`, a plumbing fix, a comment correction) is a local fix PR,
  even when it edits a workflow. A reversible design choice inside it does
  not change its shape: decide it, or build and compare, under "Deciding
  without the owner". A change that spans several stages, would benefit
  from the clarify stage's questions, or turns on new ground is filed
  with the `spec-proposal` label and added to the Roadmap issue's
  "Proposed" list. A proposal becomes a spec when `spec-request` is
  applied to it, which starts intake: by the owner, or by a session under
  "Promoting a proposal".
- Every fix PR gets a code review before merge. Fix the findings in the
  same PR. The `review-until-clean` skill is the procedure: every pass
  is a brand-new session that reviews with no findings cap and fixes,
  each fix carries a test that fails without it, and the loop checks for
  thrash after every pass. A bug the review surfaces outside the PR's
  scope becomes a new checklist line on the Maintenance backlog issue
  carrying `found by the code review of #N`, never a new issue and never
  an extra commit that widens the PR.
- Spec documents are not defects. An error in a spec's own spec.md,
  plan.md, tasks.md or research.md is corrected in that spec's open PR,
  or not at all once it has merged (see "Other repo-specific rules").
  The stage-findings composite drops findings that cite only those files
  for the same reason. Contracts under `specs/*/contracts/` are the
  exception: they are live and fixed like code.
- A spec PR gets at most three review rounds. Two clean rounds in a row
  inside those three let a session merge it ("Merging on evidence");
  otherwise the owner decides to merge it. A finding that only names a
  file, a literal, a regex or a step's shape is a plan-level finding. Record it on the lifecycle issue
  for the plan stage instead of spending another spec round on it; a
  round that raises only plan-level findings is clean. Prefer
  smaller specs: when a spec needs more rounds than that, it is usually
  carrying a plan, or two features, and should be split. Spec PR #1091
  took eight rounds, each finding a narrower build detail, and its
  feature still could not be built in five implement cycles.
- A review of a PR whose changed files a `specs/NNN-*/` spec references
  should also get a pass from the `spec-cross-reference` skill, which can
  elevate a finding into a named-requirement violation or refute one
  outright. A finding with no governing spec — a general bug, a tooling
  fix, an infra change — has nothing to check it against; don't force one.
- A fix to behaviour that only runs in Actions is proven after merge by
  re-driving one run (`gh workflow run` on the wrapper that can dispatch
  it) and recording the evidence on the PR or the issue. The
  `prove-after-merge` skill finds the runs that reach the change and
  checks the run actually took the changed path.
- Pipeline agent runs and local Claude sessions share one usage window.
  Keep concurrent local agents to two (one review pass is one session),
  and treat any agent that has run longer than ten minutes as having
  spent most of the window. Note any lifecycle issue in `stage:implement`
  before fanning out so a stall can be attributed to the burst rather
  than to the pipeline.
- `gh pr merge` on a PR that touches `.github/workflows/` needs a token
  with the `workflow` scope. When GitHub refuses for that reason, hand the
  merge to the maintainer (`gh auth refresh -h github.com -s workflow`);
  never push to main around the refusal.

## Other repo-specific rules

- Workflow comments are load-bearing: gates byte-compare and mutate them.
  Treat comment edits as code edits and re-run the suite.
- This repository is public. Never reference private downstream consumers
  (repo names, orgs, customers) in code, comments, commits, PRs, or
  issues.
- This repository's amendment history is the stack of Sync Impact Reports
  in `.specify/memory/constitution-history.md`, newest first. Keep them.
  `constitution.md` itself carries only a one-line pointer to that file, so
  every agent that reads the constitution doesn't pay for the history. A
  new amendment moves the report the `speckit-constitution` skill writes at
  the top of `constitution.md` to the top of the history file's list, in
  the same commit. The vendored skill (Spec Kit v1.0.5+) calls its report
  temporary scratch to be removed before commit; that instruction does not
  apply here -- the report is moved, not deleted.
- Once a feature's final PR has merged, its `specs/NNN-*/` spec.md,
  plan.md, research.md and tasks.md are historical records: don't file or
  fix errata against them. Correct the code or the live docs instead.
  Contracts a gate reads (`specs/*/contracts/`) remain live and are fixed
  like code.
