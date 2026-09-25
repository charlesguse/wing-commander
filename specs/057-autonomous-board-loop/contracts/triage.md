# Contract: Triage

## `.github/scripts/board_triage.py`

```python
def check_rate_limit(run_transcript_path: str) -> dict | None:
    """Returns evidence only when the cited run's transcript carries
    rate-limit evidence (a `rate_limit_event`, or a terminal `api_error`
    with `api_error_status: 429`) AND its terminal result is a failure
    (`is_error: true` or `subtype` != "success") AND records one turn
    (finite `num_turns`, 0 <= n <= 1) AND zero cost (finite
    `total_cost_usd` == 0); else None. Missing, non-numeric or non-finite
    turns/cost → None. A `rate_limit_event` alone is not enough: ordinary
    long runs emit informational ones (#402). The evidence quotes the
    transcript's own fields, never constants:
    {rate_limit_event: bool, rate_limit_status: str|None,
     terminal_reason: str|None, api_error_status: str|None,
     num_turns, cost_usd}."""

def check_action_bump(run_commit_sha: str, workflow_files: list[str],
                      cited_workflow_path: str | None) -> dict | None:
    """NEW (research.md D4). For the cited run's own workflow file
    (cited_workflow_path, the run API's `path` field) and each local
    reusable workflow it calls -- never any other workflow (#505) --
    diffs its `uses: owner/action@ref` lines as pinned at run_commit_sha
    against the same file's lines on current main. workflow_files (main's
    tracked workflows) bounds that scope. Returns {workflow_file,
    action_ref, run_pin, main_pin} for the first divergent pin where
    main's is newer, or None if every in-scope pin matches, the run's pin
    is not older, or the cited workflow is unknown or untracked on main."""

def triage(issue: dict, cited_run: str | None) -> TriageVerdict:
    """Read-only until the return value (FR-011). Never closes on evidence
    it did not itself read. See data-model.md "Triage Verdict"."""
```

## Close grounds (FR-012) — exactly two

1. **Rate limit**: `check_rate_limit()` returns non-None →
   `outcome: closed, ground: rate_limit`. Comment quotes the record's own
   fields verbatim (FR-013).
2. **Action bump**: `check_action_bump()` returns non-None →
   `outcome: closed, ground: action_bump`. Comment names both pins
   compared (FR-013).

Any other agent-proposed close reason (including "already fixed on
`main`") is **not** a close ground: the loop records the proposal and
named commit, applies `board:stalled`, and ends the run for that item
(`outcome: handover`) — FR-012's explicit deferral.

## Order (#578)

The two close grounds are tried first, and only when a cited run with a
readable transcript exists: rate limit, then action bump. Every path that
does not close — no cited run, unavailable evidence, or no close ground
found — then goes through one exit: an `already_fixed_proposal` is handed
over (above); any other close the agent proposed is recorded verbatim and
the verdict is `proceed`. So a cited run's own 429 or action-bump
evidence still outranks an "already fixed" proposal, and an issue citing
no run (most human-filed ones) is handed over rather than routed. The
handover comment posts its evidence, which includes the agent's own
reasoning (FR-056), inside a fence built by `fenced_section()` (#562).

## Unavailable evidence (FR-014)

When the cited run's transcript cannot be fetched (expired artifact,
missing run, `gh`/API error), `triage()` returns
`outcome: proceed, ground: evidence_unavailable` and records why — never a
close.

## No cited run (edge case)

A maintainer-filed issue citing no run: neither ground can apply;
`outcome: proceed`, and the loop continues to the route step — unless the
agent proposed "already fixed on `main`", which is handed over (#578).

## Cited run source (#505)

The cited run is the first run URL in the issue's own title/body or in a
comment that passed `wing-commander-issue-context`'s trust filter
(OWNER/MEMBER/COLLABORATOR or the issue's own author, never a bot) --
scanned from that composite's `context-file`, never from a comments fetch
of the triage job's own, by `board_triage.find_cited_run()`: `>`-quoted
lines and fenced code blocks are skipped (quoting a stranger's link is not
citing it), and a watchdog issue's own `_First seen: [this run](URL)_`
marker wins over any other link. Both close grounds read only that run.

An eligible issue's external author can choose their own issue's cited
run; that can only close their own issue, which they can already do, so it
grants nothing new.

## Gate: `verify-board-triage.py`

Fixtures (FR-064 bullet 1), each a checked-in transcript/workflow-pin pair:
1. 429 present (`rate_limit_event`, `api_error_status: 429`, one turn,
   zero cost) → `closed, rate_limit`.
2. 429 absent, run genuinely failed → `proceed`.
3. Cited run's artifact expired/missing → `proceed, evidence_unavailable`.
4. `main` ahead of the run's action pin → `closed, action_bump`.
5. Pins equal (`main` not ahead) → `proceed`.
6. Agent proposes "already fixed on `main`", naming a real commit → NOT
   closed; `handover`, `board:stalled` applied, proposal+commit recorded.
7. `check_action_bump()` scoping, against a throwaway repository: a bump
   in a workflow the cited run did not run → no bump; in the cited
   workflow or a local reusable workflow it calls → bump; an unknown or
   untracked cited workflow → no bump. Widening the scope must fail these.
8. board-loop.yml's `cite` step reads only the trust-filtered
   `context-file`, and no triage-job step reads comments unfiltered;
   each proven by mutating the real workflow.
9. `find_cited_run()`: a quoted or fenced link is ignored, a watchdog
   "First seen" run is preferred, a plain body link still works.
10. Rate-limit evidence without a failed run, one turn and zero cost →
    NOT closed (#402): a many-turn, nonzero-cost run carrying a
    `rate_limit_event`, a many-turn $0 429, a negative-turns 429, a
    one-turn nonzero-cost 429, a 429 with no cost recorded, and a
    successful one-turn $0 run all `proceed`. Closed cases pin the quoted
    evidence exactly. Removing any one guard, or hard-coding the evidence,
    must fail these.
11. Order (#578): "already fixed" with no cited run → `handover`; with a
    cited run whose transcript file is missing, or whose transcript path
    is empty (an expired artifact) → `handover`; with a cited run
    carrying 429 evidence → `closed, rate_limit`; an unsupported close
    with no cited run → `proceed` with the proposal recorded. Restoring
    the pre-#578 order, or moving the handover ahead of the close
    grounds, or reverting only the empty-transcript-path exit, must fail
    these; so must posting the handover evidence raw instead of through
    `fenced_section()`, whether by replacing the fenced line, inlining a
    `.evidence` read into the comment's printf, or reading it again.
