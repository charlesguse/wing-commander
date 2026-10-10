# Working on wing-commander

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

## Working the issue board

The board has three lanes, and only the first one waits on the owner:

- **Roadmap** — specs the owner chose. The open `disposition:tracking`
  issue titled "Roadmap" (#890 at the 2026-10-01 board reset) lists what
  is in flight, queued and parked. Only the owner applies `spec-request`.
- **Maintenance** — small defects from stages, reviews and the watchdog.
  They are fixed directly, never turned into specs. Collect them as
  checklist lines on the open `disposition:tracking` issue titled
  "Maintenance backlog" (#889 at the reset), not as one issue each.
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
  `verify-*.py`, a plumbing fix, a comment correction) and carries no
  design trade-off is a local fix PR, even when it edits a workflow. A
  change that needs the owner to decide a trade-off, spans several
  stages, or would benefit from the clarify stage's questions is filed
  with the `spec-proposal` label and added to the Roadmap issue's
  "Proposed" list. Never apply `spec-request` yourself: the owner's label
  event is what starts intake, and every intake ends in questions only the
  owner can answer. When the owner asks you to answer them, answer only
  the ones a precedent already settles and raise the rest
  (`answer-from-precedent` skill).
- Every fix PR gets a code review before merge. Fix the findings in the
  same PR. The `review-until-clean` skill is the procedure: a fresh
  reviewer per pass, a test that fails without each fix, and a thrash
  check after every pass. A bug the review surfaces outside the PR's
  scope becomes a new checklist line on the Maintenance backlog issue
  carrying `found by the code review of #N`, never a new issue and never
  an extra commit that widens the PR.
- Spec documents are not defects. An error in a spec's own spec.md,
  plan.md, tasks.md or research.md is corrected in that spec's open PR,
  or not at all once it has merged (see "Other repo-specific rules").
  The stage-findings composite drops findings that cite only those files
  for the same reason. Contracts under `specs/*/contracts/` are the
  exception: they are live and fixed like code.
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
  Keep concurrent local agents to two (one review pass is one agent), and
  treat any agent that has run longer than ten minutes as having spent
  most of the window. Note any lifecycle issue in `stage:implement`
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
