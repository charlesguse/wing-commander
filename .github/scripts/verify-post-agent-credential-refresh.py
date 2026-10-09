#!/usr/bin/env python3
"""Gate 68 - a bot-acting step after an agent step always holds a fresh
credential, and a tolerated observability callout is actually tolerated.

WHY THIS EXISTS
---------------
spec 052: the minted App installation token has a one-hour lifetime,
shorter than some agent steps run. Every agent-bearing job now relays its
mint into a job-scoped env.WC_BOT_TOKEN / env.WC_SCRATCH_TOKEN variable and
re-mints it immediately after each agent step (contracts/
wing-commander-context-relay.md). Nothing stops a future edit from adding a
new post-agent step that reads the stale `steps.<id>.outputs.token` form
directly, or a second agent step in the same job with no refresh between it
and the one before it, or a new "Report over-budget agent run" copy with no
`continue-on-error: true` -- each of those quietly reintroduces the defect
this feature fixed. This gate catches all three, structurally, on every PR
that touches a workflow file.

WHAT THIS CHECKS
----------------
The subject set is DERIVED (spec 072/073, #410 item 1, #558): every job in
every `.github/workflows/*.yml` file that contains at least one agent step
(`uses: anthropics/claude-code-action@*`) is a subject. Each derived subject
resolves to exactly one disposition:

- `full_subject` (the default): checks 1, 2 and 6/7 below all apply.
- `exempt`: an EXEMPT_JOBS entry names a mechanically-asserted condition
  (a wall-clock bound) in place of checks 1/2/6/7; the condition is
  evaluated every run and the gate fails, naming the entry, when it no
  longer holds.
- `agentless_in_scope`: the pre-existing AGENTLESS_JOBS set (today just
  `tasks-approved`, which never runs an agent step by design and therefore
  never actually reaches this branch via derivation -- kept for the jobs
  checks 3/5 below still cover regardless of agent-step presence).

A SUBJECT_FLOOR of checked-in (path, job_name) pairs is asserted to be a
subset of the derived set on every run: derivation alone cannot notice a
job that used to have an agent step and no longer does (there is nothing
left to match once the step is gone), so the floor exists purely for
drop-detection.

1. No step positioned after a `full_subject` job's first agent step
   references `steps.<any-id>.outputs.*token*` directly (dot or bracket
   notation, or through `fromJSON(...)`) -- it must resolve its credential
   through `env.WC_BOT_TOKEN` / `env.WC_SCRATCH_TOKEN` instead. The one
   exemption is the relay step itself (`name` starting with "Relay" and
   containing "token to the job environment") -- that step's entire job is
   to read the fresh mint's raw output and put it in the job environment,
   so it necessarily reads the raw form (FR-020 care point 1).
2. Every agent step in a `full_subject` job is followed, before the next
   agent step or the job's own end (whichever comes first), by a
   `wing-commander-context` (or, for auto-update-spec-kit.yml's e2e-stage
   job, `scoped-app-token`) invocation -- checking only "between two agent
   steps" missed both a job's single agent step (clarify.yml) and the
   refresh after a job's LAST agent step entirely (FR-020 care point 2,
   maintainer review of PR #407 hole (a)).
3. Every step whose name matches "Report over-budget agent run", including
   its "(cycle)"/"(retry)"/"(progress comment)"/"(auto)"/"(pr)" per-agent-step
   variants (data-model.md's 12-row table), carries `continue-on-error: true`
   (FR-021), in EVERY job in every loaded workflow file -- not gated on
   disposition, since the tolerance is a property of the step itself,
   regardless of whether its job is a subject at all (research.md D9;
   maintainer review of PR #407 hole (b): an earlier version of this check
   matched only the bare name).
4. A workflow file that fails to parse fails the gate, naming the file,
   rather than silently contributing zero subjects; a derived subject set
   of size zero fails the gate as misconfigured; a SUBJECT_FLOOR member
   missing from the derived set fails the gate, naming the pair (FR-022,
   Constitution Principle VIII; spec 072 FR-004).
5. Every "Record agent-ran signal", "Refresh authenticated [spec-branch]
   remote (post-agent...)", and "Determine failed post-agent step" step,
   in EVERY job in every loaded workflow file, resolves through its one
   shared composite home (`.github/actions/wing-commander-agent-ran-signal`,
   `.github/actions/wing-commander-refresh-remote`,
   `.github/actions/wing-commander-failed-post-agent-step`) rather than a
   re-pasted inline `run:` block (CLAUDE.md's single-home rule; maintainer
   review of PR #407: this repository's own docs claimed byte-identity was
   already enforced here, and it was not) -- job-agnostic, like check 3
   (research.md D9).
6. Each of the six stages' separate 'stalled' survivor job (STALL_REASON_JOBS)
   has a "Determine which dependency did not start" step that resolves
   through `.github/actions/wing-commander-stall-reason` (second maintainer
   review of PR #407, CLAUDE.md single-home rule), and passes the entry
   job's agent-started output -- published from
   wing-commander-agent-ran-signal's `started` -- to that composite and to
   every chain-stop-notice call beside it that passes agent-ran (#889/#972:
   an agent action that failed in its own setup is not "the agent ran"),
   with the agent-started guard on the very restart-command arm that says
   "its pushed commits are on the branch", and implement's agent-started
   never read from its non-pushing progress composer
   (AGENT_STARTED_EXCLUDED_SIGNALS).
7. Every agent step in a `full_subject` job has its own refresh/agent-ran/
   credential-status composite call, matched by `uses:` rather than any one
   step's `name:` (REQUIRED_PER_AGENT_STEP_COMPOSITES, exempting
   NO_REMOTE_REFRESH_JOBS from the refresh-remote leg where no git remote is
   ever persisted in that job) -- second maintainer review of PR #407,
   FR-020/FR-021 hole (a): deleting one of these steps, or renaming it away
   from anything checks 2/5 recognized by name, used to still pass Gates
   68/69. Checked BY POSITION -- each agent step's own window, up to the
   next agent step or the job's end -- not by a job-wide total (third
   maintainer review of PR #407 hole (c)): a total alone cannot tell "each
   agent step has its own call" from "one has two and another has none,"
   e.g. duplicating an earlier agent step's credential-status call while
   dropping a later one's leaves the total unchanged. The "Determine failed
   post-agent step" composite call itself must also exist in each of the
   six entry jobs whose FAILED_STEP context a stall job reads
   (FAILED_STEP_REQUIRED_JOBS) -- third maintainer review of PR #407, Gate
   68 hole (a).
8. A pre-agent step (before a subject's first agent step, whether the
   subject is `full_subject` or `exempt`) MUST NOT relay a credential-shaped
   value into `$GITHUB_ENV` under a name other than WC_BOT_TOKEN /
   WC_SCRATCH_TOKEN (third maintainer review of PR #407, FR-020) --
   job-agnostic within any job that has an agent step at all, like checks 3
   and 5 (research.md D9): a later step reading that shadow variable --
   before OR after the agent step -- would hold a token minted before the
   agent ran, without ever matching check 1's direct `steps.<id>.outputs.token`
   reference pattern.
9. Every `exempt` entry's own condition -- a wall-clock bound present and at
   or under 10 minutes -- is asserted true on every run; the gate fails,
   naming the entry, its reason and its deciding issue, when it is not
   (FR-007, spec 073; Constitution Principle IX).
10. Every EXEMPT_JOBS key names a (workflow, job) pair that actually
    resolves -- checked directly against EXEMPT_JOBS's own keys, not just
    the derived set, since a renamed or deleted job drops out of derivation
    and would otherwise leave the exemption in place with nothing left to
    check it (#735; the stale-waiver check Gate 105 already does for
    labels).
11. Each agent step's credential-status call (the one check 6 finds by its
    mint-outcome) passes a `refresh-outcome` reading the `.outcome` of
    that agent step's OWN refresh-remote step, in its own window (code
    review of #947; `.conclusion` is always 'success' under the refresh
    step's continue-on-error, code review of #951): the
    input defaults to 'success', so a dropped or cross-wired input leaves
    a failed refresh unattributed while check 6 still passes. A
    NO_REMOTE_REFRESH_JOBS job may omit it; if it passes one, every step
    it names must sit in that agent step's window. Step references in
    checks 6 and 11 match case-insensitively, as GitHub resolves them.

Static structure only (`yaml.safe_load`) -- this gate's subject is step
*ordering and reference shape*, not step *behaviour*, so no
`wc_shell_harness.py` execution pass is needed (research.md D6).

Self-test (--self-test): loads the real shipped trees, then reintroduces
each way this could regress -- a post-agent step's credential reference
reverted to the stale form or spelled with bracket notation, fromJSON(...)
with or without nested parens/bracket key, a bare toJSON(...) outputs
dump, a whole-step or whole-steps-context toJSON(...) dump (#410 item 2),
or full bracket notation on every segment; the refresh step between
implement.yml's retry and progress agent steps deleted;
`continue-on-error: true` stripped from clarify.yml's canonical
over-budget step (and from a suffixed variant); clarify.yml's only
post-agent refresh deleted; a subject job's agent step replaced with a
non-agent step, or spelled so the derivation rule no longer recognizes it;
a single-home composite call reverted to a non-composite step (for each of
the four single-homed step kinds); the refresh-remote step deleted
entirely; the credential-status step renamed away from its recognized name
with its `uses:` reverted; the "Determine failed post-agent step" step
deleted outright (hole (a)); implement.yml's progress-agent-step
credential-status call deleted while cycle's is duplicated, leaving the
job-wide total unchanged (hole (c)); rebase.yml's publish arm reverted to
the pre-agent credential, its post-agent context re-mint deleted, and its
refresh-remote call deleted; each exempt entry's condition broken in the
direction that should fail it (each of the four bounded jobs' bound
removed, and raised past the credential's lifetime -- spec 073 FR-012); board-loop.yml's
promoted jobs (#733/#848) losing triage's post-agent context call, the
Reviewer's agent-ran signal, and the Reviewer's own credential-status call
(whose mint id prefixes review-fixup's); a derived subject with no floor
membership and no exemption; the derived set emptied; a SUBJECT_FLOOR
member this feature itself adds losing its agent step; and an EXEMPT_JOBS
entry's named job renamed away, leaving the entry stale (#735); a
credential-status call's refresh-outcome dropped, pointed at another
agent step's refresh, or (e2e-stage) at a pre-agent step; and board-loop's
fixer refresh step reverted to an inline block -- and asserts each one
fails. Negative control: step references spelled in upper case pass.

Usage: python3 .github/scripts/verify-post-agent-credential-refresh.py [--self-test]
"""
import copy
import glob
import io
import os
import re
import sys
from collections import namedtuple

import yaml

AGENT_ACTION_RE = re.compile(r"^anthropics/claude-code-action@")
# Matches steps.<id>.outputs.<...token...> in every mix of dot and bracket
# notation for EACH segment (steps['ctx']['outputs']['token'],
# steps.ctx['outputs'].token, ...), fromJSON(...).<...token...> and
# fromJSON(...)['token'] (a raw mint's output re-wrapped through fromJSON
# instead of read directly, one level of nested parens tolerated so
# fromJSON(toJSON(steps.ctx.outputs)).token is still caught), and a bare
# toJSON(steps.<id>.outputs) dump of a step's whole outputs object (no
# literal "token" substring to match on its own, but equivalent to reading
# the token since the dumped object carries it) -- second maintainer
# review of PR #407, FR-020 care point 1 hole (b): an earlier version of
# this regex missed all of these spellings. Since #410 (item 2) also a
# bare toJSON(steps.<id>) / toJSON(steps) dump of a whole step or of the
# whole steps context: `fromJSON(toJSON(steps.ctx)).outputs.token` read
# the token from a whole-step dump and passed check 1, because the only
# toJSON form it knew was the `.outputs` one.
_STEP_REF = r"steps(?:\.[\w-]+|\[[\'\"][\w-]+[\'\"]\])"
_OUTPUTS_REF = r"(?:\.outputs|\[[\'\"]outputs[\'\"]\])"
_TOKEN_KEY = r"(?:\.[\w-]*token[\w-]*|\[[\'\"][\w-]*token[\w-]*[\'\"]\])"
TOKEN_REF_RE = re.compile(
    rf"{_STEP_REF}{_OUTPUTS_REF}{_TOKEN_KEY}"
    rf"|fromJSON\((?:[^()]|\([^()]*\))*\){_TOKEN_KEY}"
    rf"|toJSON\({_STEP_REF}{_OUTPUTS_REF}\)"
    rf"|toJSON\({_STEP_REF}\)"
    r"|toJSON\(steps\)",
    re.IGNORECASE)
RELAY_STEP_NAME_RE = re.compile(r"^Relay\b.*token to the job environment", re.IGNORECASE)

# Third maintainer review of PR #407 (FR-020): the hole check 1 does not
# cover -- a step BEFORE the agent step relays a pre-agent-minted
# credential-shaped value into $GITHUB_ENV under some name OTHER than the
# two this feature's own relay uses (WC_BOT_TOKEN, WC_SCRATCH_TOKEN). Any
# later step (before OR after the agent step) that reads that shadow
# variable holds a token minted before the agent ran, evading the refresh
# entirely without ever matching check 1's `steps.<id>.outputs.token`
# pattern. ALLOWED_RELAY_VARS are the two names this feature's own design
# legitimately relays through; GITHUB_ENV_ASSIGN_RE finds a `NAME=...`
# write immediately feeding a `$GITHUB_ENV` append; SHADOW_TOKEN_SOURCE_RE
# extends TOKEN_REF_RE with env.WC_BOT_TOKEN/env.WC_SCRATCH_TOKEN
# (re-relaying an already-relayed token under a second name is just as
# much a shadow copy). The bare toJSON(steps.<id>) / toJSON(steps) dump
# it used to add on its own is in TOKEN_REF_RE since #410, so check 1
# and check 8 (below) see the same set of token-carrying spellings.
ALLOWED_RELAY_VARS = {"WC_BOT_TOKEN", "WC_SCRATCH_TOKEN"}
GITHUB_ENV_ASSIGN_RE = re.compile(
    r'([A-Za-z_][A-Za-z0-9_]*)\s*=.*>>\s*"?\$GITHUB_ENV"?')
_ENV_TOKEN_VAR_RE = (
    r"env(?:\.(?:WC_BOT_TOKEN|WC_SCRATCH_TOKEN)\b"
    r"|\[[\'\"](?:WC_BOT_TOKEN|WC_SCRATCH_TOKEN)[\'\"]\])")
SHADOW_TOKEN_SOURCE_RE = re.compile(
    TOKEN_REF_RE.pattern
    + rf"|{_ENV_TOKEN_VAR_RE}",
    re.IGNORECASE)
MINT_USES_MARKERS = ("wing-commander-context", "scoped-app-token")
# Matches the base name and every "(cycle)"/"(retry)"/"(progress comment)"/
# "(auto)"/"(pr)" per-agent-step variant (data-model.md's 12-row table) --
# an earlier version of this gate matched only the bare name and silently
# never checked the 9 suffixed sites (maintainer review of PR #407).
OVER_BUDGET_NAME = "Report over-budget agent run"
OVER_BUDGET_NAME_RE = re.compile(
    r"^Report over-budget agent run(\s*\([^)]+\))?$")

# Single-home composites (spec 052, maintainer review of PR #407, CLAUDE.md's
# "shared logic has exactly one home" rule): a step matching the name regex
# must resolve through the named composite, never a re-pasted inline `run:`
# block -- verify-credential-relay-shell.py's docstring claimed this was
# already true; it was not enforced anywhere until this check existed.
SINGLE_HOME_STEPS = [
    (re.compile(r"^Record agent-ran signal\b"),
     "wing-commander-agent-ran-signal"),
    # board-loop's fix and review jobs name theirs "Refresh authenticated
    # remote (post-agent, <agent>)" -- no spec branch there (code review
    # of #947).
    (re.compile(r"^Refresh authenticated (?:spec-branch )?remote \(post-agent"),
     "wing-commander-refresh-remote"),
    (re.compile(r"^Determine failed post-agent step$"),
     "wing-commander-failed-post-agent-step"),
]

# The "Determine which dependency did not start" reason step lives in each
# stage's separate survivor/stalled job (spec 041), not the entry job the
# derived-subject engine scans -- a second, small map and check covers it
# (second maintainer review of PR #407, CLAUDE.md single-home rule).
# auto-update-spec-kit.yml's e2e-stage and plan.yml are excluded: neither
# has a wing-commander-chain-stop-notice-based survivor job (contracts/
# agent-ran-signal.md's "Not in scope for consumption"); rebase.yml has no
# separate survivor job at all (spec.md Edge Cases) and is excluded for the
# same reason.
STALL_REASON_JOBS = {
    ".github/workflows/clarify.yml": "stalled",
    ".github/workflows/finalize.yml": "stalled",
    ".github/workflows/implement.yml": "stalled",
    ".github/workflows/intake.yml": "stalled",
    ".github/workflows/pr-conversation.yml": "stalled",
    ".github/workflows/tasks.yml": "stalled",
}
REASON_STEP_NAME = "Determine which dependency did not start"
REASON_COMPOSITE = "wing-commander-stall-reason"

# Jobs that never run an agent step, by design -- tasks-approved is a
# PR-merge acceptance handler with no agent involvement at all. Such a job
# can never actually appear in the DERIVED subject set (derivation requires
# >= 1 agent step), so this disposition is unreachable through that set
# today; it is kept, unchanged, because checks 3/5/8 below still cover a job
# named here regardless of agent-step presence, and because a future
# AGENTLESS_JOBS entry might legitimately gain, then lose, an agent step
# without ever being expected to carry the post-agent mechanism (research.md
# D3; spec 072/073 disposition model, contract Section on the Derived
# Subject).
AGENTLESS_JOBS = {"tasks-approved"}

# Second maintainer review of PR #407, FR-020/FR-021 hole (a): today,
# deleting the refresh/agent-ran/credential-status step for one agent step,
# or renaming it away from anything checks 2/5 recognize by `name:`, still
# passes Gates 60/68/69. Counting `uses:` references to each composite --
# which survives a rename, and which a re-pasted inline block (no `uses:`
# at all) can never satisfy -- closes that hole. Keyed by (path, job_name)
# rather than a blanket rule: e2e-stage never persists env.WC_BOT_TOKEN in
# a git remote (contracts/wing-commander-context-relay.md's e2e-stage
# section; the scratch-token relay is a distinct, second credential with no
# remote of its own either), so it has no refresh-remote call to require.
REQUIRED_PER_AGENT_STEP_COMPOSITES = [
    ("wing-commander-refresh-remote", "refresh"),
    ("wing-commander-agent-ran-signal", "agent-ran signal"),
    ("wing-commander-post-agent-credential-status", "credential-status"),
]
NO_REMOTE_REFRESH_JOBS = {
    (".github/workflows/auto-update-spec-kit.yml", "e2e-stage"),
    # board-loop's triage and route check out with persist-credentials:
    # false and never push -- their writes are comments, labels and filed
    # issues through env.WC_BOT_TOKEN directly. claude-code-action does
    # rewrite origin with its own token when each agent step starts, so
    # .git/config holds a token that goes stale; refreshing it is moot
    # because no step after the agent uses origin's persisted credential.
    # That is what every entry here shares: e2e-stage and
    # classify-and-announce reach a remote only through explicit
    # token-bearing URLs. Promoted from EXEMPT_JOBS to full subjects with
    # fix and review (#733/#848, tracked on #889).
    (".github/workflows/board-loop.yml", "triage"),
    (".github/workflows/board-loop.yml", "route"),
    # T009 (spec 052's own tasks.md): classify-and-announce resolves
    # spec-meta.json via the contents API rather than a "Checkout spec
    # branch" step, so there is no persisted git remote credential to
    # refresh in this job either.
    (".github/workflows/pr-conversation.yml", "classify-and-announce"),
    # specs/062-lifecycle-review-gate T020: the review job checks out the
    # lifecycle PR's head ref with persist-credentials: false and never
    # pushes -- its only write is the `gh api` review post (through
    # env.WC_BOT_TOKEN directly), so no step after its agent uses origin's
    # persisted credential either.
    (".github/workflows/lifecycle-review-gate.yml", "review"),
}

# Third maintainer review of PR #407, Gate 68 hole (a): nothing previously
# required the "Determine failed post-agent step" step to exist at all --
# check 5 (SINGLE_HOME_STEPS) only fires when a step matching that NAME is
# present, so deleting the step entirely, or pasting the old inline jq
# back under a different step name, passed every gate. This is the entry
# job (not the survivor/stalled job) whose FAILED_STEP output the stall
# path reads -- the same six jobs STALL_REASON_JOBS names, with
# pr-conversation's and tasks.yml's survivor job translated to its own
# entry job. 'act' (pr-conversation), 'tasks-approved', and rebase.yml's
# 'rebase' are excluded: 'act' and 'tasks-approved' have no survivor job
# wrapping them (tasks-approved is also agentless), and rebase.yml's
# 'Abandon and escalate' arm is job-local -- it consumes the composite's
# output directly rather than through a job output a separate job reads
# (spec.md Edge Cases "rebase.yml has no separate survivor job").
FAILED_STEP_REQUIRED_JOBS = {
    ".github/workflows/clarify.yml": "clarify",
    ".github/workflows/finalize.yml": "finalize",
    ".github/workflows/implement.yml": "implement",
    ".github/workflows/intake.yml": "intake",
    ".github/workflows/pr-conversation.yml": "classify-and-announce",
    ".github/workflows/tasks.yml": "tasks",
}


def _is_agent_step(step):
    return bool(AGENT_ACTION_RE.match(str((step or {}).get("uses", ""))))


def _is_mint_step(step):
    uses = str((step or {}).get("uses", ""))
    return any(marker in uses for marker in MINT_USES_MARKERS)


# Extracts the <id> out of a matched `steps.<id>` / `steps['<id>']`
# fragment, so a `toJSON(steps.<id>)` / `toJSON(steps.<id>.outputs)` match
# can be checked against the job's own mint step ids rather than assumed
# to be the mint on sight (#439 review): `toJSON({_STEP_REF}...)` matches
# ANY step id, so an unrelated step dumped for logging/diagnostics -- not
# the credential mint -- would otherwise be reported as a stale
# credential reference.
_STEP_ID_RE = re.compile(
    r"steps(?:\.([\w-]+)|\[[\'\"]([\w-]+)[\'\"]\])", re.IGNORECASE)


# A step reference plus the property read from it (group 3/4), e.g.
# `steps.refresh-remote.outcome` / `steps['refresh-remote']['conclusion']`.
# Used by check 11 to require .outcome of a continue-on-error refresh step.
_STEP_PROP_RE = re.compile(
    r"steps(?:\.([\w-]+)|\[[\'\"]([\w-]+)[\'\"]\])"
    r"(?:\s*\.\s*([\w-]+)|\s*\[\s*[\'\"]([\w-]+)[\'\"]\s*\])?",
    re.IGNORECASE)


def _step_ref_re(step_id):
    """A `steps.<step_id>` / `steps['<step_id>']` reference to exactly this
    id. (?![\w-]), not \b: a hyphen is a word boundary, so
    `reestablish-review\b` also matched review-fixup's
    `steps.reestablish-review-fixup.outcome` and hid a deleted Reviewer
    credential-status call (code review of #733/#848). Case-insensitive:
    GitHub expressions resolve context and property names in any case, so
    `STEPS.reestablish.outcome` is the same reference (code review of
    #947)."""
    return re.compile(
        rf"steps(?:\.{re.escape(step_id)}(?![\w-])"
        rf"|\[[\'\"]{re.escape(step_id)}[\'\"]\])",
        re.IGNORECASE)


def _toJSON_dump_is_mint(matched_text, mint_ids):
    """A `toJSON(steps.<id>...)` match only implicates a credential when
    <id> names a mint step in this job. `toJSON(steps)` (the whole
    context, no id to extract) always implicates one when the job has a
    mint step at all, since the dumped context necessarily carries it.
    Compared case-insensitively, as GitHub resolves the expression."""
    if matched_text.lower() == "tojson(steps)":
        return bool(mint_ids)
    m = _STEP_ID_RE.search(matched_text)
    ref_id = (m.group(1) or m.group(2)) if m else None
    return ref_id is not None and ref_id.lower() in {str(i).lower() for i in mint_ids}


def _is_relay_step(step):
    return bool(RELAY_STEP_NAME_RE.match(str((step or {}).get("name", ""))))


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _step_text(step):
    return "\n".join(_walk_strings(step))


# --------------------------------------------------------------------------
# Exemption record (research.md D4; contracts/gate-68-derived-subjects.md
# Section 3): a derived subject whose disposition is `exempt` skips checks
# 1/2/7 in favour of a DIFFERENT, per-entry `condition` that must hold on
# every run -- an entry with no condition, or one that is always True, is
# not a valid entry (Constitution IX; FR-007 of spec 073).
# --------------------------------------------------------------------------
# `decided_by` is the provenance FR-007 requires: the issue(s) that
# DECIDED the exemption, kept even after they close. `issue` is the open
# TRACKER for retiring it: a tuple of OPEN issues, or () with
# `permanent=True` and a one-line `permanent_reason`. verify-waiver-
# citations.py (Gate 124) holds every entry to exactly one of the two and
# checks only `issue` for openness, never `decided_by`.
ExemptionEntry = namedtuple(
    "ExemptionEntry",
    ["reason", "issue", "condition", "permanent", "permanent_reason",
     "decided_by"],
    defaults=(False, None, ()))


def _wall_clock_bound_ok(job, max_minutes=10):
    """Every agent step in the job carries its own `timeout-minutes`, or
    falls back to the job-level `timeout-minutes` when the step has none,
    and that value is present and <= max_minutes (contract Section 3, "Wall-
    clock bound"; FR-006)."""
    steps = list((job or {}).get("steps") or [])
    job_timeout = (job or {}).get("timeout-minutes")
    agent_steps = [s for s in steps if _is_agent_step(s)]
    if not agent_steps:
        return False
    for step in agent_steps:
        timeout = (step or {}).get("timeout-minutes", job_timeout)
        if timeout is None:
            return False
        try:
            if float(timeout) > max_minutes:
                return False
        except (TypeError, ValueError):
            return False
    return True


# path -> set of job names -- the checked-in floor a derived subject's
# disappearance is compared against (research.md D3; contract Section 2).
# Nine pre-existing entries (spec 052's FR-007 stages) plus seven this
# feature adds (rebase.yml/rebase, cleanup.yml/teardown-done, watchdog.yml/
# diagnose, board-loop.yml's four jobs) -- sixteen total. auto-update-
# spec-kit.yml's evaluate-path/comment-reply are EXEMPT_JOBS entries, not
# floor members (their exclusion was already prose-only and unreachable
# through the old hand-typed SUBJECTS list; this feature mechanizes the
# condition without also newly floor-tracking them).
SUBJECT_FLOOR = {
    ".github/workflows/intake.yml": {"intake"},
    ".github/workflows/clarify.yml": {"clarify"},
    ".github/workflows/plan.yml": {"plan"},
    ".github/workflows/tasks.yml": {"tasks"},
    ".github/workflows/implement.yml": {"implement"},
    ".github/workflows/finalize.yml": {"finalize"},
    ".github/workflows/pr-conversation.yml": {"classify-and-announce", "act"},
    ".github/workflows/auto-update-spec-kit.yml": {"e2e-stage"},
    ".github/workflows/rebase.yml": {"rebase"},
    ".github/workflows/cleanup.yml": {"teardown-done"},
    ".github/workflows/watchdog.yml": {"diagnose"},
    ".github/workflows/board-loop.yml": {"triage", "route", "fix", "review"},
}

# (workflow_path, job_name) -> ExemptionEntry -- every entry a derived
# subject resolves to instead of full_subject, each with a mechanically
# asserted condition (FR-007; contract "Entries this feature adds").
EXEMPT_JOBS = {
    (".github/workflows/cleanup.yml", "teardown-done"): ExemptionEntry(
        reason=(
            "wall-clock bound (timeout-minutes: 10) instead of the full "
            "post-agent mechanism -- the agent measured ~1 minute on all "
            "40 sampled runs (FR-005)"),
        issue=(),
        permanent=True,
        permanent_reason=(
            "An agent step bounded by its own 10-minute timeout is the "
            "design for a short job, not debt awaiting a fix."),
        decided_by=(558,),
        condition=_wall_clock_bound_ok,
    ),
    (".github/workflows/watchdog.yml", "diagnose"): ExemptionEntry(
        reason=(
            "agent step already carries timeout-minutes: 10, the same "
            "bound cleanup.yml adopts (research.md D6)"),
        issue=(),
        permanent=True,
        permanent_reason=(
            "An agent step bounded by its own 10-minute timeout is the "
            "design for a short job, not debt awaiting a fix."),
        decided_by=(558,),
        condition=_wall_clock_bound_ok,
    ),
    (".github/workflows/auto-update-spec-kit.yml", "evaluate-path"): ExemptionEntry(
        reason=(
            "mechanizes spec 052's existing prose-only exclusion -- agent "
            "step already carries timeout-minutes: 10"),
        issue=(),
        permanent=True,
        permanent_reason=(
            "An agent step bounded by its own 10-minute timeout is the "
            "design for a short job, not debt awaiting a fix."),
        decided_by=(558,),
        condition=_wall_clock_bound_ok,
    ),
    (".github/workflows/auto-update-spec-kit.yml", "comment-reply"): ExemptionEntry(
        reason=(
            "mechanizes spec 052's existing prose-only exclusion -- agent "
            "step already carries timeout-minutes: 10"),
        issue=(),
        permanent=True,
        permanent_reason=(
            "An agent step bounded by its own 10-minute timeout is the "
            "design for a short job, not debt awaiting a fix."),
        decided_by=(558,),
        condition=_wall_clock_bound_ok,
    ),
}


def _disposition(path, job_name):
    """-> 'exempt' | 'agentless_in_scope' | 'full_subject'. Every derived
    subject resolves to exactly one (contract Section 3; FR-009 spec 072).
    `full_subject` is the default -- a job that qualifies as neither exempt
    nor agentless is expected to comply with the full mechanism, and
    check_job_full_subject below fails it if it does not."""
    if (path, job_name) in EXEMPT_JOBS:
        return "exempt"
    if job_name in AGENTLESS_JOBS:
        return "agentless_in_scope"
    return "full_subject"


def load_all(root="."):
    """-> {path: parsed_yaml_or_None} for every `.github/workflows/*.yml`
    file (research.md D2) -- widened from the old hand-typed SUBJECTS keys.
    A file that fails to parse is recorded as None; the caller reports it
    by name rather than silently deriving zero subjects from it (contract
    Section 1)."""
    out = {}
    pattern = os.path.join(root, ".github", "workflows", "*.yml")
    for full in sorted(glob.glob(pattern)):
        path = os.path.relpath(full, root).replace(os.sep, "/")
        try:
            with io.open(full, encoding="utf-8") as f:
                out[path] = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            out[path] = None
    return out


def derive_subjects(loaded):
    """-> set of (path, job_name) for every job, in every loaded workflow
    file, containing at least one agent step -- the derivation rule
    (research.md D2; contract Section 1). No further reading of the job
    narrows this set; disposition (exempt/agentless/full_subject) is a
    separate question, answered by `_disposition`."""
    derived = set()
    for path, wf in loaded.items():
        if not wf:
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            if any(_is_agent_step(s) for s in (job or {}).get("steps") or []):
                derived.add((path, job_name))
    return derived


def check_job_universal(path, job_name, job):
    """Checks 3 and 5 -- job-agnostic (research.md D9): run for every job in
    every loaded workflow file, regardless of agent-step presence or
    disposition, since both are properties of a step's own name/uses, not
    of the job's subject status."""
    failures = []
    steps = list((job or {}).get("steps") or [])

    # check 3 -- tolerance, independent of whether the job has an agent step.
    # Matches every per-agent-step suffix variant, not only the bare name
    # (maintainer review of PR #407 hole (b)).
    for step in steps:
        name = str((step or {}).get("name", ""))
        if OVER_BUDGET_NAME_RE.match(name) and not (step or {}).get("continue-on-error"):
            failures.append(
                f"{path} [{job_name}]: {name!r} does not carry "
                f"continue-on-error: true -- its own failure can strand the "
                f"deterministic read-back and every step below it (FR-021)")

    # check 5 -- shared post-agent logic resolves through its one composite
    # home, never a re-pasted inline block (CLAUDE.md's single-home rule,
    # maintainer review of PR #407).
    for step in steps:
        name = str((step or {}).get("name", ""))
        uses = str((step or {}).get("uses", ""))
        for name_re, composite in SINGLE_HOME_STEPS:
            if name_re.match(name) and composite not in uses:
                failures.append(
                    f"{path} [{job_name}] step {name!r} does not call the "
                    f"{composite} composite (CLAUDE.md single-home rule) -- "
                    f"got uses: {uses!r}")

    return failures


def check_job_shadow_relay(path, job_name, job):
    """Check 8 -- job-agnostic within any job that has an agent step at all
    (research.md D9), regardless of full_subject/exempt disposition: a step
    BEFORE the job's first agent step relaying a pre-agent-minted
    credential-shaped value into $GITHUB_ENV under a name other than
    WC_BOT_TOKEN/WC_SCRATCH_TOKEN (third maintainer review of PR #407,
    FR-020) -- a later step reading that shadow variable, before or after
    the agent step, would hold a token minted before the agent ran."""
    failures = []
    steps = list((job or {}).get("steps") or [])
    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]
    if not agent_idxs:
        return failures
    first = agent_idxs[0]
    for step in steps[:first]:
        if _is_relay_step(step):
            continue
        text = _step_text(step)
        if not SHADOW_TOKEN_SOURCE_RE.search(text):
            continue
        for m in GITHUB_ENV_ASSIGN_RE.finditer(text):
            varname = m.group(1)
            if varname in ALLOWED_RELAY_VARS:
                continue
            name = (step or {}).get("name", "<unnamed step>")
            failures.append(
                f"{path} [{job_name}] pre-agent step {name!r} relays a "
                f"credential-shaped value into env.{varname} via "
                f"$GITHUB_ENV -- a later step reading env.{varname} would "
                f"hold a token minted before the agent ran, evading the "
                f"WC_BOT_TOKEN/WC_SCRATCH_TOKEN relay this feature "
                f"requires (FR-020, third maintainer review of PR #407)")
    return failures


def check_job_full_subject(path, job_name, job):
    """Checks 1, 2 and 6/7 -- ONLY for a derived subject whose disposition
    is `full_subject` (research.md D9, T008). The caller guarantees at
    least one agent step (derivation's own definition), so `agent_idxs` is
    never empty here."""
    failures = []
    steps = list((job or {}).get("steps") or [])
    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]
    first = agent_idxs[0]

    # check 1 -- no stale credential reference after the first agent step.
    mint_ids = {(s or {}).get("id") for s in steps if _is_mint_step(s) and (s or {}).get("id")}
    for step in steps[first + 1:]:
        if _is_relay_step(step):
            continue
        name = (step or {}).get("name", "<unnamed step>")
        m = TOKEN_REF_RE.search(_step_text(step))
        if m and m.group(0).lower().startswith("tojson(") and not _toJSON_dump_is_mint(m.group(0), mint_ids):
            continue
        if m:
            failures.append(
                f"{path} [{job_name}] step {name!r} references "
                f"{m.group(0)} after the job's first agent step -- it must "
                f"resolve its credential through env.WC_BOT_TOKEN / "
                f"env.WC_SCRATCH_TOKEN instead (FR-020 care point 1)")

    # check 2 -- every agent step is followed, before the NEXT agent step or
    # the end of the job (whichever comes first), by a fresh mint. Checking
    # only "between consecutive agent steps" (agent_idxs[1:]) missed the
    # single-agent-step case entirely (clarify.yml) and the refresh after
    # the LAST agent step in every job (maintainer review of PR #407 hole
    # (a)) -- a sentinel boundary at len(steps) covers both.
    boundaries = agent_idxs[1:] + [len(steps)]
    for idx, boundary in zip(agent_idxs, boundaries):
        between = steps[idx + 1:boundary]
        if not any(_is_mint_step(s) for s in between):
            name = (steps[idx] or {}).get("name", "<unnamed step>")
            failures.append(
                f"{path} [{job_name}]: agent step {name!r} has no "
                f"wing-commander-context (or scoped-app-token) re-mint "
                f"after it, before the next agent step or the job's end -- "
                f"every step below it runs on a stale credential (FR-020 "
                f"care point 2)")

    # check 6 -- each agent step has its own refresh/agent-ran/credential-
    # status composite call, matched by `uses:` (never by step `name:`, so a
    # rename can't hide a deletion) -- second maintainer review of PR #407,
    # FR-020/FR-021 hole (a). Checked by POSITION, not merely by a job-wide
    # total (third maintainer review of PR #407 hole (c)): a job-wide count
    # cannot tell "each agent step has its own call" from "one agent step
    # has two and another has none" -- e.g. removing the LAST agent step's
    # credential-status call while duplicating an EARLIER one's leaves the
    # total unchanged. refresh-remote and agent-ran-signal each run
    # immediately after their own agent step (contracts/
    # wing-commander-context-relay.md's call-site convention), so their
    # position check is "at least one call inside this agent step's own
    # window" (same boundaries as check 2). credential-status is different
    # BY DESIGN: it is deferred to the job's own last steps, after every
    # business-logic/report step (review-step-gating self-review, spec
    # 052's own T042/data-model.md), except in rebase.yml, where it runs
    # just before "Publish rebased branch", which reads it (#661). Either
    # way it sits outside the agent step's window: in a multi-agent-step
    # job, all of a job's credential-status calls cluster at the END, never
    # inside any individual agent step's window. Its "position" is
    # therefore checked by REFERENCE, not by sequential order: each agent
    # step's own mint
    # step (found inside its window) must have some credential-status call,
    # anywhere in the job, whose `mint-outcome` names that exact mint
    # step's id -- the same reference a duplicated call cannot satisfy for
    # more than one agent step, since ids are unique per agent step.
    mint_id_re = re.compile(r"^[\w-]+$")
    for idx, boundary in zip(agent_idxs, boundaries):
        between = steps[idx + 1:boundary]
        agent_name = (steps[idx] or {}).get("name", "<unnamed step>")
        for marker, label in REQUIRED_PER_AGENT_STEP_COMPOSITES:
            if marker == "wing-commander-post-agent-credential-status":
                continue
            if marker == "wing-commander-refresh-remote" and (path, job_name) in NO_REMOTE_REFRESH_JOBS:
                continue
            n_calls = sum(1 for s in between if marker in str((s or {}).get("uses", "")))
            if n_calls < 1:
                failures.append(
                    f"{path} [{job_name}]: agent step {agent_name!r} has no "
                    f"{marker} call between it and the next agent step or "
                    f"the job's end -- each agent step needs its OWN {label} "
                    f"composite call at that position, not merely a call "
                    f"somewhere else in the job (FR-020, FR-021, third "
                    f"maintainer review of PR #407 hole (c))")

        mint_id = next(
            ((s or {}).get("id") for s in between if _is_mint_step(s)), None)
        if mint_id is None or not mint_id_re.match(str(mint_id)):
            continue  # no mint id to cross-reference; check 2 already flags a missing mint.
        mint_ref_re = _step_ref_re(mint_id)
        status_calls = [
            s for s in steps
            if "wing-commander-post-agent-credential-status" in str((s or {}).get("uses", ""))
            and mint_ref_re.search(_step_text(s))]
        if not status_calls:
            failures.append(
                f"{path} [{job_name}]: agent step {agent_name!r}'s mint "
                f"step (id: {mint_id!r}) is never referenced by any "
                f"wing-commander-post-agent-credential-status call's "
                f"mint-outcome anywhere in the job -- this agent step has "
                f"no credential-status call of its OWN, even though the "
                f"job-wide total may look sufficient (FR-020, FR-021, "
                f"third maintainer review of PR #407 hole (c))")
            continue

        # check 11 -- the same call's refresh-outcome names THIS window's
        # refresh step (code review of #947). The input defaults to
        # 'success', so dropping it, or pointing it at another agent step's
        # refresh, still passes check 6 while a failed refresh in this
        # window is never attributed to the credential. A job that never
        # refreshes a remote (NO_REMOTE_REFRESH_JOBS) may omit the input;
        # when it passes one (e2e-stage's scratch-token re-mint), every
        # step it names must sit in this window, and a value naming no step
        # (a literal 'skipped') passes as omitting it would (code review
        # of #951).
        window_ids = {str((s or {}).get("id")) for s in between if (s or {}).get("id")}
        if (path, job_name) in NO_REMOTE_REFRESH_JOBS:
            refresh_ids, required = window_ids, False
        else:
            refresh_steps = [s for s in between
                             if "wing-commander-refresh-remote" in str((s or {}).get("uses", ""))]
            refresh_ids = {str(s["id"]) for s in refresh_steps
                           if (s or {}).get("id") and mint_id_re.match(str(s["id"]))}
            required = True
            if refresh_steps and not refresh_ids:
                failures.append(
                    f"{path} [{job_name}]: agent step {agent_name!r}'s "
                    f"wing-commander-refresh-remote call has no id, so no "
                    f"credential-status call can name its outcome (check 11)")
                continue
            if not refresh_steps:
                continue  # the missing refresh call is check 6's failure.
        for call in status_calls:
            call_name = (call or {}).get("name", "<unnamed step>")
            refresh_input = str(((call or {}).get("with") or {}).get("refresh-outcome", ""))
            named = {(m.group(1) or m.group(2)).lower()
                     for m in _STEP_ID_RE.finditer(refresh_input)}
            allowed = {i.lower() for i in refresh_ids}
            # The refresh step is continue-on-error: true, so only its
            # .outcome records a failure -- .conclusion is always 'success'
            # and .outputs.* carries no failure at all. A required job must
            # read .outcome of every refresh step it names (code review of
            # #951).
            if required:
                bad_props = sorted({
                    (m.group(0)) for m in _STEP_PROP_RE.finditer(refresh_input)
                    if (m.group(1) or m.group(2)).lower() in allowed
                    and (m.group(3) or m.group(4) or "").lower() != "outcome"})
                if bad_props:
                    failures.append(
                        f"{path} [{job_name}]: credential-status call "
                        f"{call_name!r} for agent step {agent_name!r} reads "
                        f"{', '.join(bad_props)} in refresh-outcome -- the "
                        f"refresh step is continue-on-error: true, so only "
                        f"its .outcome records a failed refresh (FR-004; "
                        f"check 11)")
            if not refresh_input.strip():
                if required:
                    failures.append(
                        f"{path} [{job_name}]: credential-status call "
                        f"{call_name!r} for agent step {agent_name!r} has no "
                        f"refresh-outcome -- it defaults to 'success', so a "
                        f"failed refresh of this agent step's remote is "
                        f"never attributed to the credential (FR-004; "
                        f"check 11)")
            elif not named <= allowed or (required and not named & allowed):
                failures.append(
                    f"{path} [{job_name}]: credential-status call "
                    f"{call_name!r} for agent step {agent_name!r} passes "
                    f"refresh-outcome {refresh_input!r}, which does not "
                    f"name this agent step's own "
                    f"{'refresh-remote step' if required else 'post-agent steps'}"
                    f" ({', '.join(sorted(refresh_ids)) or 'none'}) -- a "
                    f"failed refresh here would be attributed to another "
                    f"window, or to nothing (FR-004; check 11)")

    # check 7 (the failed-post-agent-step composite CALL must exist, not
    # merely be well-formed when present under a recognized name) -- third
    # maintainer review of PR #407, Gate 68 hole (a).
    required_job = FAILED_STEP_REQUIRED_JOBS.get(path)
    if required_job == job_name:
        marker = "wing-commander-failed-post-agent-step"
        if not any(marker in str((s or {}).get("uses", "")) for s in steps):
            failures.append(
                f"{path} [{job_name}]: no step calls the {marker} "
                f"composite -- the stall path's FAILED_STEP context is "
                f"unreachable if this step is deleted or pasted back "
                f"under a different, uncalled shape (FR-020, FR-021, "
                f"third maintainer review of PR #407 hole (a))")

    return failures


NOTICE_COMPOSITE = "wing-commander-chain-stop-notice"
_AGENT_RAN_NEEDS_RE = re.compile(
    r"^\$\{\{\s*needs\.([A-Za-z0-9_-]+)\.outputs\.agent-ran\s*\}\}$")

# Agent-ran signal step ids whose `started` must never feed a job's
# agent-started output (code review of PR #978): implement's progress
# composer runs only after a cycle or retry succeeded and never pushes, so
# its own setup failure would tell the notice no agent work exists while
# that cycle's commits are on the branch (FR-015).
AGENT_STARTED_EXCLUDED_SIGNALS = {
    ".github/workflows/implement.yml": {"agent-ran-progress"},
}


def check_agent_started_wiring(path, job, wf):
    """-> list[str]. #889/#972: the agent-started signal reaches the stall
    reason and the notice. The entry job is the one the reason step's own
    agent-ran input names; it must publish agent-started from
    wing-commander-agent-ran-signal's `started`, and every stall-reason or
    chain-stop-notice call in this job that passes agent-ran from it must
    pass the matching agent-started too -- a call that drops it falls back
    to "the agent ran ... its pushed commits are on the branch" for an
    agent whose action never got past its own setup."""
    failures = []
    reason = _find_step(job, REASON_STEP_NAME) or {}
    ran = str((reason.get("with") or {}).get("agent-ran", "")).strip()
    m = _AGENT_RAN_NEEDS_RE.match(ran)
    if not m:
        return [f"{path} [stalled] step {REASON_STEP_NAME!r}: agent-ran is "
                f"not a needs.<job>.outputs.agent-ran reference ({ran!r}) "
                f"-- cannot check its agent-started wiring (#889)"]
    entry = m.group(1)
    want = "${{ needs.%s.outputs.agent-started }}" % entry
    entry_job = ((wf or {}).get("jobs") or {}).get(entry) or {}
    published = str((entry_job.get("outputs") or {}).get("agent-started", ""))
    if "outputs.started" not in published:
        failures.append(
            f"{path} [{entry}]: no agent-started job output read from "
            f"wing-commander-agent-ran-signal's `started` (got "
            f"{published!r}) -- the stall path cannot tell an agent that "
            f"never started from one that ran (#889)")
    for sid in sorted(AGENT_STARTED_EXCLUDED_SIGNALS.get(path, ())):
        if f"steps.{sid}.outputs.started" in published:
            failures.append(
                f"{path} [{entry}]: agent-started reads steps.{sid}'s "
                f"`started` -- that agent step runs only after the work-"
                f"bearing one succeeded and never pushes, so its own setup "
                f"failure would report no agent work while that work is on "
                f"the branch (FR-015, code review of PR #978)")
    for step in job.get("steps") or []:
        uses = str((step or {}).get("uses", ""))
        if REASON_COMPOSITE not in uses and NOTICE_COMPOSITE not in uses:
            continue
        w = (step or {}).get("with") or {}
        if str(w.get("agent-ran", "")).strip() != ran:
            continue
        if str(w.get("agent-started", "")).strip() != want:
            failures.append(
                f"{path} [stalled] step {step.get('name')!r} passes "
                f"agent-ran but not agent-started: {want} (#889) -- got "
                f"{w.get('agent-started')!r}")
        restart = str(w.get("restart-command", ""))
        guard = "needs.%s.outputs.agent-started != 'false'" % entry
        # The guard must sit in the very `&&` arm that yields the "pushed
        # commits" string, not merely somewhere in the expression (code
        # review of PR #978): every quoted alternative carrying that phrase
        # is preceded directly by `<guard> && `.
        arms = re.findall(r"(?:(\S+)\s*!=\s*'false'\s*&&\s*)?'[^']*pushed "
                          r"commits are on the branch[^']*'", restart)
        want_ref = "needs.%s.outputs.agent-started" % entry
        if "pushed commits are on the branch" in restart and (
                not arms or any(a != want_ref for a in arms)):
            failures.append(
                f"{path} [stalled] step {step.get('name')!r}: its "
                f"restart-command offers \"its pushed commits are on the "
                f"branch\" without the {guard!r} guard, so an agent that "
                f"never started is told its commits exist (#889)")
    return failures


def check_stall_reason_job(path, job, wf=None):
    """-> list[str]. The reason step's own single-home composite call."""
    step = _find_step(job, REASON_STEP_NAME)
    if step is None:
        return [f"{path}: no {REASON_STEP_NAME!r} step found in the "
                f"'stalled' job -- cannot check its single-home composite "
                f"call (CLAUDE.md single-home rule)"]
    uses = str((step or {}).get("uses", ""))
    if REASON_COMPOSITE not in uses:
        return [f"{path} [stalled] step {REASON_STEP_NAME!r} does not call "
                f"the {REASON_COMPOSITE} composite (CLAUDE.md single-home "
                f"rule) -- got uses: {uses!r}"]
    return check_agent_started_wiring(path, job, wf)


def scan(loaded):
    failures = []

    for path, job_name in STALL_REASON_JOBS.items():
        wf = loaded.get(path)
        if wf is None:
            failures.append(
                f"{path}: file not found or failed to parse -- cannot "
                f"check its stall-reason composite call (FR-022)")
            continue
        job = (wf.get("jobs") or {}).get(job_name)
        if job is None:
            failures.append(
                f"{path}: job {job_name!r} not found -- cannot check its "
                f"stall-reason composite call (FR-022)")
            continue
        failures += check_stall_reason_job(path, job, wf)

    # Checks 3/5 -- job-agnostic, every job in every loaded file (D9).
    for path, wf in loaded.items():
        if wf is None:
            failures.append(
                f"{path}: file not found or failed to parse -- cannot "
                f"check its credential handling (FR-022)")
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            failures += check_job_universal(path, job_name, job)

    # Derivation (D2) plus the floor invariant (D3).
    derived = derive_subjects(loaded)
    if not derived:
        failures.append(
            "the derived agent-bearing subject set is empty -- "
            "misconfigured or unreachable, never a silent pass over an "
            "empty result set (FR-022)")

    for path, job_names in SUBJECT_FLOOR.items():
        for job_name in job_names:
            if (path, job_name) not in derived:
                failures.append(
                    f"{path} [{job_name}]: a SUBJECT_FLOOR member is "
                    f"missing from the derived agent-bearing subject set "
                    f"-- this subject's last agent step disappeared "
                    f"(FR-022, spec 072 FR-004)")

    # Check 10 -- every EXEMPT_JOBS key must itself resolve to a job that
    # exists. Checked directly against EXEMPT_JOBS's own keys, not merely
    # the derived set below: a renamed or deleted job drops out of
    # derivation entirely, so an exemption naming it would otherwise never
    # be looked at again by anything (#735).
    for path, job_name in EXEMPT_JOBS:
        wf = loaded.get(path)
        if wf is None or job_name not in (wf.get("jobs") or {}):
            failures.append(
                f"{path} [{job_name}]: EXEMPT_JOBS entry names a "
                f"workflow/job pair that does not exist -- the exemption "
                f"has outlived a renamed or deleted job (FR-007, #735)")

    # Disposition + checks 1/2/6/7 (full_subject only) and check 8 (any
    # derived subject, regardless of disposition).
    for path, job_name in sorted(derived):
        job = (loaded[path].get("jobs") or {}).get(job_name)
        disposition = _disposition(path, job_name)
        if disposition == "exempt":
            entry = EXEMPT_JOBS[(path, job_name)]
            if not entry.condition(job):
                failures.append(
                    f"{path} [{job_name}]: exempt entry's condition no "
                    f"longer holds -- {entry.reason} (decided by "
                    f"{'/'.join('#' + str(n) for n in entry.decided_by) or '?'}"
                    f") (FR-007)")
        elif disposition == "agentless_in_scope":
            pass
        elif disposition == "full_subject":
            failures += check_job_full_subject(path, job_name, job)
        else:
            failures.append(
                f"{path} [{job_name}]: neither full_subject, "
                f"agentless_in_scope, nor exempt (spec 072 FR-013)")

        failures += check_job_shadow_relay(path, job_name, job)

    return failures


# --------------------------------------------------------------------------
# Self-test -- mutations reintroducing each way this could regress.
# --------------------------------------------------------------------------
def _find_step(job, name):
    for step in (job or {}).get("steps") or []:
        if (step or {}).get("name") == name:
            return step
    return None


def mut_stale_credential_reference(loaded):
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ steps.ctx.outputs.token }}"


def mut_bracket_notation_credential_reference(loaded):
    """should-fix (PR #407 review): a stale reference spelled with bracket
    notation (steps['ctx'].outputs['token']) must be caught too, not only
    the plain dot-notation form."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ steps['ctx'].outputs['token'] }}"


def mut_fromjson_bracket_credential_reference(loaded):
    """should-fix (second review of PR #407): fromJSON(...)['token'] --
    bracket notation on the fromJSON(...) result -- must be caught too."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ fromJSON(toJSON(steps.ctx.outputs))['token'] }}"


def mut_nested_fromjson_credential_reference(loaded):
    """should-fix (second review of PR #407):
    fromJSON(toJSON(steps.ctx.outputs)).token -- a raw mint re-wrapped
    through a nested fromJSON(toJSON(...)) round-trip instead of read
    directly -- must be caught despite the inner call's own parens."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ fromJSON(toJSON(steps.ctx.outputs)).token }}"


def mut_bare_tojson_outputs_dump(loaded):
    """should-fix (second review of PR #407): toJSON(steps.ctx.outputs) has
    no literal "token" substring of its own but dumps the whole outputs
    object -- equivalent to reading the token -- must be caught."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ toJSON(steps.ctx.outputs) }}"


def mut_whole_step_dump_credential_reference(loaded):
    """#410 item 2: fromJSON(toJSON(steps.ctx)).outputs.token -- the token
    read out of a WHOLE-STEP dump, which carries `.outputs.token` with it.
    Reproduced on ff45ce7 against 'Announce remaining clarification
    questions' in clarify.yml: the gate reported 0 failures."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce remaining clarification questions")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ fromJSON(toJSON(steps.ctx)).outputs.token }}"


def mut_whole_steps_context_dump(loaded):
    """#410 item 2, the wider form: toJSON(steps) dumps every step's
    result, the mint's outputs included."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ fromJSON(toJSON(steps)).ctx.outputs.token }}"


def mut_unrelated_step_tojson_dump(loaded):
    """NEGATIVE control (#439 review): toJSON(steps.<id>) matches any step
    id, not only the mint's. Dumping 'agent-verdict' (a real, non-mint
    post-agent step in this same job) for logging/diagnostics must NOT be
    reported -- it never carries the credential."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert _find_step(job, "Compute agent run verdict") is not None, \
        "fixture assumption broken: step renamed"
    step["with"]["token"] = "${{ env.WC_BOT_TOKEN }} ${{ toJSON(steps.agent-verdict) }}"


def mut_full_bracket_credential_reference(loaded):
    """should-fix (second review of PR #407):
    steps['ctx']['outputs']['token'] -- bracket notation on every segment,
    including "outputs" itself, which the dot-only middle segment in an
    earlier version of this regex missed."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Announce spec PR ready for review")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["token"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["with"]["token"] = "${{ steps['ctx']['outputs']['token'] }}"


def mut_shadow_env_relay(loaded):
    """Third maintainer review of PR #407 (FR-020): a pre-agent step
    relaying the pre-agent-minted token into a $GITHUB_ENV variable other
    than WC_BOT_TOKEN/WC_SCRATCH_TOKEN must be caught -- a later step
    reading it would hold a stale credential without ever matching check
    1's direct steps.<id>.outputs.token pattern."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    steps = job["steps"]
    ctx_idx = next((i for i, s in enumerate(steps) if (s or {}).get("id") == "ctx"), None)
    assert ctx_idx is not None, "fixture assumption broken: ctx step renamed/moved"
    shadow_step = {
        "name": "Stash a spare copy of the token",
        "shell": "bash",
        "env": {"OLD_TOKEN": "${{ steps.ctx.outputs.token }}"},
        "run": 'echo "STASHED_TOKEN=$OLD_TOKEN" >> "$GITHUB_ENV"\n',
    }
    steps.insert(ctx_idx + 1, shadow_step)


def mut_drop_retry_progress_refresh(loaded):
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    steps = job["steps"]
    name = "Re-establish Wing Commander context (post-agent, retry)"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_drop_tolerance(loaded):
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, OVER_BUDGET_NAME)
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("continue-on-error") is True, \
        "fixture assumption broken: tolerance already missing"
    del step["continue-on-error"]


def mut_drop_clarify_only_refresh(loaded):
    """Hole (a): clarify has exactly one agent step, so the refresh check
    only fires post-052-review when a job's LAST (not just "between two")
    agent step is checked."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    steps = job["steps"]
    name = "Re-establish Wing Commander context (post-agent)"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_drop_suffixed_tolerance(loaded):
    """Hole (b): the over-budget check must match suffixed variants like
    "(cycle)", not only the bare name."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    step = _find_step(job, "Report over-budget agent run (cycle)")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("continue-on-error") is True, \
        "fixture assumption broken: tolerance already missing"
    del step["continue-on-error"]


def mut_job_loses_agent_step(loaded):
    """Hole (c), generalized to the floor invariant (spec 072 FR-004): a
    subject job that stops having an agent step must fail loudly, not
    silently skip all of its checks."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Fold answers into the draft spec")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "claude-code-action" in str(step.get("uses", "")), \
        "fixture assumption broken: no longer the agent step"
    step["uses"] = "actions/checkout@v5"


def mut_new_floor_member_loses_agent_step(loaded):
    """Spec 072 FR-004/US2, generalized: a SUBJECT_FLOOR member THIS
    FEATURE adds (board-loop.yml's review job) losing its agent step must
    fail loudly the same way an original floor member does."""
    job = loaded[".github/workflows/board-loop.yml"]["jobs"]["review"]
    steps = job["steps"]
    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]
    assert len(agent_idxs) == 2, "fixture assumption broken: agent step count changed"
    for idx in agent_idxs:
        steps[idx]["uses"] = "actions/checkout@v5"


def mut_agent_step_unrecognized_spelling(loaded):
    """Recognition regression (contract Section 1): an agent step whose
    `uses:` no longer matches AGENT_ACTION_RE's exact, case-sensitive
    prefix must drop its job out of the derived set (caught by the floor
    invariant), not be silently treated as still recognized."""
    job = loaded[".github/workflows/finalize.yml"]["jobs"]["finalize"]
    step = _find_step(job, "Summarize change and extract remaining manual work")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["uses"] == "anthropics/claude-code-action@v1", \
        "fixture assumption broken: uses form changed"
    step["uses"] = "Anthropics/Claude-Code-Action@v1"


def mut_zero_derived_subjects(loaded):
    """Contract Section 1's misconfiguration case, generalized to the
    derived model: every agent step in every loaded file replaced, leaving
    a derived set of size zero -- must fail loudly, never pass vacuously."""
    for wf in loaded.values():
        if not wf:
            continue
        for job in (wf.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                if _is_agent_step(step):
                    step["uses"] = "actions/checkout@v5"


def mut_synthetic_uncovered_agent_job(loaded):
    """Spec 072 FR-013, restated for the exemption model: a derived subject
    with no SUBJECT_FLOOR membership and no EXEMPT_JOBS entry defaults to
    full_subject and must fail full_subject compliance (no mint, no
    composites) rather than pass unnoticed."""
    wf = loaded[".github/workflows/watchdog.yml"]
    wf["jobs"]["synthetic-uncovered-agent-job"] = {
        "runs-on": "ubuntu-latest",
        "steps": [
            {"name": "Do agent things", "id": "agent",
             "uses": "anthropics/claude-code-action@v1", "with": {}},
        ],
    }


def mut_single_home_reverted(loaded):
    """CLAUDE.md single-home rule: a call site reverting to a re-pasted
    inline block instead of the shared composite must be caught."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Record agent-ran signal")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "wing-commander-agent-ran-signal" in str(step.get("uses", "")), \
        "fixture assumption broken: composite already not called"
    step["uses"] = "actions/checkout@v5"


def mut_failed_step_single_home_reverted(loaded):
    """Second maintainer review of PR #407: the 'Determine failed
    post-agent step' composite call reverted to a re-pasted inline block."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Determine failed post-agent step")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "wing-commander-failed-post-agent-step" in str(step.get("uses", "")), \
        "fixture assumption broken: composite already not called"
    step["uses"] = "actions/checkout@v5"


def mut_failed_step_deleted_entirely(loaded):
    """Hole (a): deleting the 'Determine failed post-agent step' step
    outright (not merely reverting its `uses:`) must fail -- check 5 alone
    only inspects a step that still exists under the recognized name."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    steps = job["steps"]
    name = "Determine failed post-agent step"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_failed_step_pasted_under_new_name(loaded):
    """Hole (a): the old inline jq pasted back under an unrecognized step
    name (no `uses:` at all) must still fail -- check 7 requires the
    composite CALL to exist, regardless of what any step is named."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Determine failed post-agent step")
    assert step is not None, "fixture assumption broken: step renamed"
    step["name"] = "Compute the step that failed"
    step.pop("uses", None)
    step.pop("with", None)
    step["run"] = "echo step=$(echo)>> \"$GITHUB_OUTPUT\""


def mut_credential_status_position_swap(loaded):
    """Hole (c): implement.yml's progress-agent-step credential-status call
    deleted while cycle's is duplicated -- the job-wide TOTAL stays the
    same (3 calls either way), so only a position-aware check catches
    that the progress agent step's own window now has zero."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    steps = job["steps"]
    progress_idx = next((i for i, s in enumerate(steps)
                         if (s or {}).get("name") == "Determine post-agent credential status (progress)"), None)
    cycle_idx = next((i for i, s in enumerate(steps)
                      if (s or {}).get("name") == "Determine post-agent credential status (cycle)"), None)
    assert progress_idx is not None, "fixture assumption broken: step renamed"
    assert cycle_idx is not None, "fixture assumption broken: step renamed"
    dup = copy.deepcopy(steps[cycle_idx])
    dup["id"] = "credential-status-cycle-dup"
    del steps[progress_idx]
    steps.insert(cycle_idx + 1, dup)


def mut_stall_reason_single_home_reverted(loaded):
    """Second maintainer review of PR #407: the 'Determine which dependency
    did not start' composite call, in the separate 'stalled' job, reverted
    to a re-pasted inline block."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["stalled"]
    step = _find_step(job, REASON_STEP_NAME)
    assert step is not None, "fixture assumption broken: step renamed"
    assert REASON_COMPOSITE in str(step.get("uses", "")), \
        "fixture assumption broken: composite already not called"
    step["uses"] = "actions/checkout@v5"


def mut_stall_reason_drops_agent_started(loaded):
    """#889/#972: intake's stall reason stops passing agent-started, so a
    run whose agent action died in its own setup is reported as "the agent
    step ran ... its pushed commits are on the branch" again."""
    job = loaded[".github/workflows/intake.yml"]["jobs"]["stalled"]
    step = _find_step(job, REASON_STEP_NAME)
    assert step is not None, "fixture assumption broken: step renamed"
    assert "agent-started" in (step.get("with") or {}), \
        "fixture assumption broken: agent-started already absent"
    del step["with"]["agent-started"]


def mut_notice_drops_agent_started(loaded):
    """#889/#972: implement's stall notice stops passing agent-started."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["stalled"]
    step = _find_step(job, "Report the stage did not start")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "agent-started" in (step.get("with") or {}), \
        "fixture assumption broken: agent-started already absent"
    del step["with"]["agent-started"]


def mut_restart_command_drops_agent_started_guard(loaded):
    """#889/#972: clarify's restart-command offers "its pushed commits are
    on the branch" to an agent that never started again."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["stalled"]
    step = _find_step(job, "Report the stage did not start")
    assert step is not None, "fixture assumption broken: step renamed"
    guard = " && needs.clarify.outputs.agent-started != 'false'"
    restart = step["with"]["restart-command"]
    assert guard in restart, "fixture assumption broken: guard absent"
    step["with"]["restart-command"] = restart.replace(guard, "")


def mut_restart_command_guard_on_wrong_arm(loaded):
    """Code review of PR #978: intake's agent-started guard moved onto the
    success arm, leaving the "pushed commits" arm unguarded while the guard
    text still appears in the expression."""
    job = loaded[".github/workflows/intake.yml"]["jobs"]["stalled"]
    step = _find_step(job, "Report the stage did not start")
    assert step is not None, "fixture assumption broken: step renamed"
    guard = " && needs.intake.outputs.agent-started != 'false'"
    restart = step["with"]["restart-command"]
    assert guard in restart, "fixture assumption broken: guard absent"
    restart = restart.replace(guard, "")
    success = "needs.intake.outputs.agent-conclusion == 'success'"
    assert success in restart, "fixture assumption broken: success arm"
    step["with"]["restart-command"] = restart.replace(
        success, success + guard, 1)


def mut_implement_agent_started_reads_progress(loaded):
    """Code review of PR #978: implement's agent-started output reads the
    non-pushing progress composer's `started` again."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    out = job["outputs"]["agent-started"]
    assert "agent-ran-progress" not in out, \
        "fixture assumption broken: progress already read"
    job["outputs"]["agent-started"] = out.replace(
        "${{ ", "${{ steps.agent-ran-progress.outputs.started || ", 1)


def mut_entry_job_drops_agent_started_output(loaded):
    """#889/#972: tasks' entry job stops publishing agent-started, so the
    stalled job's needs.tasks.outputs.agent-started reads empty."""
    job = loaded[".github/workflows/tasks.yml"]["jobs"]["tasks"]
    assert "agent-started" in (job.get("outputs") or {}), \
        "fixture assumption broken: agent-started output already absent"
    del job["outputs"]["agent-started"]


def mut_refresh_remote_step_deleted(loaded):
    """Hole (a): deleting the refresh-remote step entirely (not merely
    reverting its `uses:`) must fail -- check 5 alone only inspects a step
    that still exists under the recognized name."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    steps = job["steps"]
    name = "Refresh authenticated spec-branch remote (post-agent)"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_credential_status_renamed_and_reverted(loaded):
    """Hole (a): today, renaming a step away from anything a name-keyed
    check recognizes lets its `uses:` be reverted to a non-composite step
    undetected (no check still watching it by its old name). Check 6 keys
    on `uses:` counted across the whole job, not on any one step's name, so
    it still catches the missing composite call after the rename."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Determine post-agent credential status")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "wing-commander-post-agent-credential-status" in str(step.get("uses", "")), \
        "fixture assumption broken: composite already not called"
    step["name"] = "Check the token is still good"
    step["uses"] = "actions/checkout@v5"


def mut_rebase_publish_reverted(loaded):
    """rebase.yml's own check-1 regression: the publish arm's GH_TOKEN
    reverted to the pre-agent mint (spec.md FR-001, FR-012)."""
    job = loaded[".github/workflows/rebase.yml"]["jobs"]["rebase"]
    step = _find_step(job, "Publish rebased branch")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["env"]["GH_TOKEN"] == "${{ env.WC_BOT_TOKEN }}", \
        "fixture assumption broken: token form changed"
    step["env"]["GH_TOKEN"] = "${{ steps.ctx.outputs.token }}"


def mut_rebase_reestablish_deleted(loaded):
    """rebase.yml's own check-2 regression: the post-agent context re-mint
    deleted entirely (spec.md FR-001, FR-012)."""
    job = loaded[".github/workflows/rebase.yml"]["jobs"]["rebase"]
    steps = job["steps"]
    name = "Re-establish Wing Commander context (post-agent)"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_rebase_refresh_remote_deleted(loaded):
    """rebase.yml's own check-6/7 regression: the refresh-remote call
    deleted, since rebase.yml is not in NO_REMOTE_REFRESH_JOBS (spec.md
    FR-002, FR-012)."""
    job = loaded[".github/workflows/rebase.yml"]["jobs"]["rebase"]
    steps = job["steps"]
    name = "Refresh authenticated spec-branch remote (post-agent)"
    idx = next((i for i, s in enumerate(steps) if (s or {}).get("name") == name), None)
    assert idx is not None, "fixture assumption broken: step renamed"
    del steps[idx]


def mut_cleanup_bound_removed(loaded):
    """cleanup.yml's exemption-condition regression: timeout-minutes: 10
    removed from Completion summary (spec.md FR-006, SC-004)."""
    job = loaded[".github/workflows/cleanup.yml"]["jobs"]["teardown-done"]
    step = _find_step(job, "Completion summary")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("timeout-minutes") == 10, \
        "fixture assumption broken: bound already missing"
    del step["timeout-minutes"]


def mut_cleanup_bound_raised(loaded):
    """cleanup.yml's exemption-condition regression, upper-bound direction:
    timeout-minutes raised past the credential's lifetime (spec.md FR-006,
    SC-004)."""
    job = loaded[".github/workflows/cleanup.yml"]["jobs"]["teardown-done"]
    step = _find_step(job, "Completion summary")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("timeout-minutes") == 10, \
        "fixture assumption broken: bound already changed"
    step["timeout-minutes"] = 90


def mut_watchdog_bound_removed(loaded):
    """watchdog.yml's exemption-condition regression -- proves the wall-
    clock condition function is not hardcoded to cleanup.yml alone
    (spec.md FR-006, research.md D6)."""
    job = loaded[".github/workflows/watchdog.yml"]["jobs"]["diagnose"]
    step = _find_step(job, "Diagnose")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("timeout-minutes") == 10, \
        "fixture assumption broken: bound already missing"
    del step["timeout-minutes"]


def _mut_bound(loaded, path, job_name, step_name, raise_to=None):
    """Remove the agent step's timeout-minutes, or raise it past the
    credential's lifetime when `raise_to` is given."""
    job = loaded[path]["jobs"][job_name]
    step = _find_step(job, step_name)
    assert step is not None, "fixture assumption broken: step renamed"
    assert step.get("timeout-minutes") == 10, \
        "fixture assumption broken: bound already changed"
    if raise_to is None:
        del step["timeout-minutes"]
    else:
        step["timeout-minutes"] = raise_to


def _mut_auto_update_bound_removed(loaded, job_name, step_name):
    _mut_bound(loaded, ".github/workflows/auto-update-spec-kit.yml",
               job_name, step_name)


def mut_watchdog_bound_raised(loaded):
    """watchdog.yml's exemption-condition regression, upper-bound
    direction. Spec 073 FR-012 asks for "a removed and an over-long
    wall-clock bound" for each bounded job; cleanup.yml had both and
    watchdog.yml only the first (code review of #947)."""
    _mut_bound(loaded, ".github/workflows/watchdog.yml", "diagnose",
               "Diagnose", raise_to=90)


def mut_evaluate_path_bound_raised(loaded):
    """auto-update-spec-kit.yml's evaluate-path, upper-bound direction."""
    _mut_bound(loaded, ".github/workflows/auto-update-spec-kit.yml",
               "evaluate-path", "Decide upgrade path", raise_to=90)


def mut_comment_reply_bound_raised(loaded):
    """auto-update-spec-kit.yml's comment-reply, upper-bound direction."""
    _mut_bound(loaded, ".github/workflows/auto-update-spec-kit.yml",
               "comment-reply", "Interpret the maintainer's reply", raise_to=90)


def mut_evaluate_path_bound_removed(loaded):
    """auto-update-spec-kit.yml's evaluate-path exemption-condition
    regression: the agent step's timeout-minutes: 10 removed, so the
    contract's one condition-broken mutation per EXEMPT_JOBS entry holds
    for all four (code review of #733/#848)."""
    _mut_auto_update_bound_removed(loaded, "evaluate-path", "Decide upgrade path")


def mut_comment_reply_bound_removed(loaded):
    """auto-update-spec-kit.yml's comment-reply exemption-condition
    regression, as above."""
    _mut_auto_update_bound_removed(
        loaded, "comment-reply", "Interpret the maintainer's reply")


def mut_board_loop_triage_context_deleted(loaded):
    """board-loop.yml's triage, a full subject since #733/#848 (it was a
    composite-adoption exemption until then): its post-agent
    wing-commander-context call deleted -- must fail naming the job (check
    2), not pass as the exemption it no longer is."""
    job = loaded[".github/workflows/board-loop.yml"]["jobs"]["triage"]
    steps = job["steps"]
    agent_idx = next((i for i, s in enumerate(steps) if _is_agent_step(s)), None)
    assert agent_idx is not None, "fixture assumption broken: agent step moved"
    ctx_idx = next(
        (i for i in range(agent_idx + 1, len(steps))
         if "wing-commander-context" in str((steps[i] or {}).get("uses", ""))),
        None)
    assert ctx_idx is not None, "fixture assumption broken: composite call moved"
    del steps[ctx_idx]


def _delete_step_by_id(job, step_id):
    steps = job["steps"]
    idx = next((i for i, s in enumerate(steps)
                if (s or {}).get("id") == step_id), None)
    assert idx is not None, f"fixture assumption broken: no step id {step_id!r}"
    del steps[idx]


def mut_board_loop_reviewer_agent_ran_deleted(loaded):
    """board-loop.yml's review job, a full subject since #733/#848: the
    Reviewer's agent-ran-signal call deleted. The composite-adoption
    exemption it replaced never required this call, so only the promotion
    makes it fail (check 6)."""
    job = loaded[".github/workflows/board-loop.yml"]["jobs"]["review"]
    _delete_step_by_id(job, "agent-ran-review")


def mut_board_loop_reviewer_status_deleted(loaded):
    """board-loop.yml's review job: the Reviewer's own credential-status
    call deleted. Its mint id `reestablish-review` is a prefix of
    review-fixup's `reestablish-review-fixup`, so check 6's mint
    cross-reference must not accept review-fixup's call as the Reviewer's
    (code review of #733/#848)."""
    job = loaded[".github/workflows/board-loop.yml"]["jobs"]["review"]
    _delete_step_by_id(job, "credential-status-review")


def mut_clarify_refresh_outcome_dropped(loaded):
    """Check 11 (code review of #947): the refresh-outcome input dropped,
    so it defaults to 'success' and a failed refresh is unattributed."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Determine post-agent credential status")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "refresh-outcome" in step["with"], \
        "fixture assumption broken: refresh-outcome already missing"
    del step["with"]["refresh-outcome"]


def mut_implement_refresh_outcome_cross_wired(loaded):
    """Check 11: the progress agent step's credential-status call reads the
    cycle agent step's refresh outcome -- check 6 still sees its own
    mint-outcome, so only check 11 catches it."""
    job = loaded[".github/workflows/implement.yml"]["jobs"]["implement"]
    step = _find_step(job, "Determine post-agent credential status (progress)")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["refresh-outcome"] == "${{ steps.refresh-remote-progress.outcome }}", \
        "fixture assumption broken: refresh-outcome changed"
    step["with"]["refresh-outcome"] = "${{ steps.refresh-remote-cycle.outcome }}"


def mut_clarify_refresh_outcome_conclusion(loaded):
    """Check 11 (code review of #951): refresh-outcome reads the window's
    own refresh step's .conclusion, which is always 'success' under
    continue-on-error: true, so a failed refresh is unattributed."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Determine post-agent credential status")
    assert step is not None, "fixture assumption broken: step renamed"
    assert step["with"]["refresh-outcome"] == "${{ steps.refresh-remote.outcome }}", \
        "fixture assumption broken: refresh-outcome changed"
    step["with"]["refresh-outcome"] = "${{ steps.refresh-remote.conclusion }}"


def mut_e2e_refresh_outcome_pre_agent(loaded):
    """Check 11, NO_REMOTE_REFRESH_JOBS arm: e2e-stage's refresh-outcome
    pointed at the PRE-agent scratch-token mint instead of its post-agent
    re-mint."""
    job = loaded[".github/workflows/auto-update-spec-kit.yml"]["jobs"]["e2e-stage"]
    step = _find_step(job, "Determine post-agent credential status")
    assert step is not None, "fixture assumption broken: step renamed"
    value = step["with"]["refresh-outcome"]
    assert "steps.scratch-token-post-agent." in value, \
        "fixture assumption broken: refresh-outcome changed"
    step["with"]["refresh-outcome"] = value.replace(
        "steps.scratch-token-post-agent.", "steps.scratch-token.")


def mut_board_loop_fixer_refresh_inlined(loaded):
    """Check 5 (code review of #947): board-loop names its refresh steps
    "Refresh authenticated remote (post-agent, <agent>)", which the
    single-home pattern used to miss. Reverted to an inline block."""
    job = loaded[".github/workflows/board-loop.yml"]["jobs"]["fix"]
    step = _find_step(job, "Refresh authenticated remote (post-agent, fixer)")
    assert step is not None, "fixture assumption broken: step renamed"
    step.pop("uses", None)
    step.pop("with", None)
    step["run"] = 'git remote set-url origin "https://x-access-token:${WC_BOT_TOKEN}@github.com/o/r"'


def mut_upper_case_step_references(loaded):
    """NEGATIVE control (code review of #947): GitHub resolves `STEPS.x`
    and `Steps.X` like `steps.x`, so upper-case references to the window's
    own mint and refresh steps must still pass checks 6 and 11."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Determine post-agent credential status")
    assert step is not None, "fixture assumption broken: step renamed"
    step["with"]["mint-outcome"] = "${{ STEPS.reestablish.outcome }}"
    step["with"]["refresh-outcome"] = "${{ Steps['Refresh-Remote'].outcome }}"


def mut_e2e_refresh_outcome_literal(loaded):
    """NEGATIVE control (code review of #951): a NO_REMOTE_REFRESH_JOBS job
    may omit refresh-outcome, so a value naming no step at all (a literal
    'skipped') must pass check 11 just as omitting it does."""
    job = loaded[".github/workflows/auto-update-spec-kit.yml"]["jobs"]["e2e-stage"]
    step = _find_step(job, "Determine post-agent credential status")
    assert step is not None, "fixture assumption broken: step renamed"
    step["with"]["refresh-outcome"] = "skipped"


def mut_exempt_job_deleted(loaded):
    """#735: an EXEMPT_JOBS entry naming a job that no longer exists must
    fail. Deleting auto-update-spec-kit.yml's evaluate-path job (not a
    SUBJECT_FLOOR member) leaves the exemption as the only thing that
    mentions it, so check 10 is the sole failure. A rename would not do:
    the renamed job keeps its agent step and comes back as a fresh derived
    subject that fails unrelated checks, so the mutation would survive
    check 10's removal. self_test() also requires check 10's own message."""
    wf = loaded[".github/workflows/auto-update-spec-kit.yml"]
    jobs = wf["jobs"]
    assert "evaluate-path" in jobs, "fixture assumption broken: job renamed"
    del jobs["evaluate-path"]


SIMPLE_MUTATIONS = [
    ("a post-agent step's credential reference reverted to the stale "
     "steps.ctx.outputs.token form", mut_stale_credential_reference),
    ("a post-agent step's credential reference spelled with bracket "
     "notation instead of dot notation", mut_bracket_notation_credential_reference),
    ("a post-agent step's credential reference spelled fromJSON(...)['token']",
     mut_fromjson_bracket_credential_reference),
    ("a post-agent step's credential reference spelled "
     "fromJSON(toJSON(steps.ctx.outputs)).token", mut_nested_fromjson_credential_reference),
    ("a post-agent step's credential reference spelled bare "
     "toJSON(steps.ctx.outputs)", mut_bare_tojson_outputs_dump),
    ("a post-agent step's credential reference spelled "
     "steps['ctx']['outputs']['token']", mut_full_bracket_credential_reference),
    ("a post-agent step's credential reference spelled "
     "fromJSON(toJSON(steps.ctx)).outputs.token -- a whole-step dump (#410)",
     mut_whole_step_dump_credential_reference),
    ("a post-agent step's credential reference spelled "
     "fromJSON(toJSON(steps)).ctx.outputs.token -- the whole steps context (#410)",
     mut_whole_steps_context_dump),
    ("the refresh step between implement.yml's retry and progress agent "
     "steps deleted", mut_drop_retry_progress_refresh),
    ("continue-on-error: true stripped from clarify.yml's canonical "
     "over-budget step", mut_drop_tolerance),
    ("clarify.yml's only post-agent refresh (after its only agent step) "
     "deleted", mut_drop_clarify_only_refresh),
    ("continue-on-error: true stripped from a SUFFIXED over-budget step "
     "(implement.yml's \"(cycle)\" variant)", mut_drop_suffixed_tolerance),
    ("a subject job's agent step replaced with a non-agent step",
     mut_job_loses_agent_step),
    ("a SUBJECT_FLOOR member added by THIS feature (board-loop.yml's "
     "review job) loses both of its agent steps", mut_new_floor_member_loses_agent_step),
    ("an agent step spelled so the derivation rule's case-sensitive match "
     "no longer recognizes it", mut_agent_step_unrecognized_spelling),
    ("the derived agent-bearing subject set emptied", mut_zero_derived_subjects),
    ("a synthetic agent-bearing job with no floor membership and no "
     "exemption entry", mut_synthetic_uncovered_agent_job),
    ("a single-home composite call reverted to a non-composite step",
     mut_single_home_reverted),
    ("the 'Determine failed post-agent step' composite call reverted to a "
     "non-composite step", mut_failed_step_single_home_reverted),
    ("the 'Determine which dependency did not start' composite call (in "
     "the stalled job) reverted to a non-composite step",
     mut_stall_reason_single_home_reverted),
    ("intake's stall reason stops passing agent-started (#889)",
     mut_stall_reason_drops_agent_started),
    ("implement's stall notice stops passing agent-started (#889)",
     mut_notice_drops_agent_started),
    ("clarify's restart-command loses its agent-started guard (#889)",
     mut_restart_command_drops_agent_started_guard),
    ("tasks' entry job stops publishing the agent-started output (#889)",
     mut_entry_job_drops_agent_started_output),
    ("intake's agent-started guard moved onto the restart-command's "
     "success arm (code review of PR #978)",
     mut_restart_command_guard_on_wrong_arm),
    ("implement's agent-started reads the progress composer's signal "
     "(code review of PR #978)",
     mut_implement_agent_started_reads_progress),
    ("the refresh-remote step deleted entirely, not merely reverted",
     mut_refresh_remote_step_deleted),
    ("the credential-status step renamed away from its recognized name "
     "and its uses: reverted to a non-composite step",
     mut_credential_status_renamed_and_reverted),
    ("the 'Determine failed post-agent step' step deleted outright",
     mut_failed_step_deleted_entirely),
    ("the old inline jq pasted back under an unrecognized step name with "
     "no uses: at all", mut_failed_step_pasted_under_new_name),
    ("implement.yml's progress-agent-step credential-status call deleted "
     "while cycle's is duplicated (job-wide total unchanged)",
     mut_credential_status_position_swap),
    ("a pre-agent step relaying the pre-agent token into a $GITHUB_ENV "
     "variable other than WC_BOT_TOKEN/WC_SCRATCH_TOKEN", mut_shadow_env_relay),
    ("rebase.yml's publish arm's GH_TOKEN reverted to the pre-agent mint",
     mut_rebase_publish_reverted),
    ("rebase.yml's post-agent wing-commander-context re-mint deleted",
     mut_rebase_reestablish_deleted),
    ("rebase.yml's post-agent wing-commander-refresh-remote call deleted",
     mut_rebase_refresh_remote_deleted),
    ("cleanup.yml's teardown-done exemption bound removed", mut_cleanup_bound_removed),
    ("cleanup.yml's teardown-done exemption bound raised past the "
     "credential's lifetime", mut_cleanup_bound_raised),
    ("watchdog.yml's diagnose exemption bound removed", mut_watchdog_bound_removed),
    ("watchdog.yml's diagnose exemption bound raised past the credential's "
     "lifetime", mut_watchdog_bound_raised),
    ("auto-update-spec-kit.yml's evaluate-path exemption bound removed",
     mut_evaluate_path_bound_removed),
    ("auto-update-spec-kit.yml's evaluate-path exemption bound raised",
     mut_evaluate_path_bound_raised),
    ("auto-update-spec-kit.yml's comment-reply exemption bound removed",
     mut_comment_reply_bound_removed),
    ("auto-update-spec-kit.yml's comment-reply exemption bound raised",
     mut_comment_reply_bound_raised),
    ("board-loop.yml's triage (a full subject) post-agent context call deleted",
     mut_board_loop_triage_context_deleted),
    ("board-loop.yml's review: the Reviewer's agent-ran signal deleted",
     mut_board_loop_reviewer_agent_ran_deleted),
    ("board-loop.yml's review: the Reviewer's own credential-status call "
     "deleted", mut_board_loop_reviewer_status_deleted),
    ("an EXEMPT_JOBS entry's named job deleted, leaving the entry "
     "stale (#735)", mut_exempt_job_deleted),
    ("clarify.yml's credential-status refresh-outcome dropped",
     mut_clarify_refresh_outcome_dropped),
    ("implement.yml's progress credential-status refresh-outcome pointed at "
     "the cycle agent step's refresh", mut_implement_refresh_outcome_cross_wired),
    ("clarify.yml's credential-status refresh-outcome reads the refresh "
     "step's .conclusion", mut_clarify_refresh_outcome_conclusion),
    ("e2e-stage's credential-status refresh-outcome pointed at the "
     "pre-agent scratch-token mint", mut_e2e_refresh_outcome_pre_agent),
    ("board-loop.yml's fixer remote refresh reverted to an inline block",
     mut_board_loop_fixer_refresh_inlined),
]


def self_test():
    base = load_all()
    problems = []

    clean = scan(copy.deepcopy(base))
    if clean:
        problems.append("clean copy of the real tree FAILED: " + "; ".join(clean))

    for label, apply_mutation in SIMPLE_MUTATIONS:
        mutated = copy.deepcopy(base)
        apply_mutation(mutated)
        if mutated == base:
            problems.append(f"mutation {label!r} changed nothing -- the "
                            f"code it edits was rewritten; update the "
                            f"mutation.")
            continue
        broke = scan(mutated)
        if not broke:
            problems.append(f"MUTATION SURVIVED -- reintroducing {label!r} "
                            f"broke nothing in this gate.")
        else:
            print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")

    # Check 10 must be the check that catches a stale exemption, not some
    # other assertion the mutation happens to trip.
    mutated = copy.deepcopy(base)
    mut_exempt_job_deleted(mutated)
    broke = scan(mutated)
    if not (len(broke) == 1 and "EXEMPT_JOBS entry names" in broke[0]):
        problems.append("a stale EXEMPT_JOBS entry was not caught by check "
                        f"10 alone (#735): {broke!r}")

    # The promoted review job's two mutations must fail on the check that
    # owns them, not on something they happen to trip (#733/#848).
    review_job = ".github/workflows/board-loop.yml [review]: agent step 'Reviewer'"
    for mutate, want in (
            (mut_board_loop_reviewer_agent_ran_deleted,
             review_job + " has no wing-commander-agent-ran-signal call"),
            (mut_board_loop_reviewer_status_deleted,
             review_job + "'s mint step (id: 'reestablish-review') is never "
             "referenced")):
        mutated = copy.deepcopy(base)
        mutate(mutated)
        broke = scan(mutated)
        if not (len(broke) == 1 and broke[0].startswith(want)):
            problems.append(f"{mutate.__name__} did not fail with {want!r}: "
                            f"{broke!r}")

    # Check 11's and check 5's mutations must fail on the check that owns
    # them (code review of #947).
    for mutate, want in (
            (mut_clarify_refresh_outcome_dropped,
             ".github/workflows/clarify.yml [clarify]: credential-status "
             "call 'Determine post-agent credential status' for agent step "
             "'Fold answers into the draft spec' has no refresh-outcome"),
            (mut_implement_refresh_outcome_cross_wired,
             ".github/workflows/implement.yml [implement]: credential-status "
             "call 'Determine post-agent credential status (progress)'"),
            (mut_clarify_refresh_outcome_conclusion,
             ".github/workflows/clarify.yml [clarify]: credential-status "
             "call 'Determine post-agent credential status' for agent step "
             "'Fold answers into the draft spec' reads "
             "steps.refresh-remote.conclusion"),
            (mut_e2e_refresh_outcome_pre_agent,
             ".github/workflows/auto-update-spec-kit.yml [e2e-stage]: "
             "credential-status call"),
            (mut_board_loop_fixer_refresh_inlined,
             ".github/workflows/board-loop.yml [fix] step 'Refresh "
             "authenticated remote (post-agent, fixer)' does not call the "
             "wing-commander-refresh-remote composite")):
        mutated = copy.deepcopy(base)
        mutate(mutated)
        broke = scan(mutated)
        if not any(b.startswith(want) for b in broke):
            problems.append(f"{mutate.__name__} did not fail with {want!r}: "
                            f"{broke!r}")

    mutated = copy.deepcopy(base)
    mut_upper_case_step_references(mutated)
    broke = scan(mutated)
    if broke:
        problems.append(
            "upper-case step references (STEPS.reestablish, "
            "Steps['Refresh-Remote']) were not recognised: "
            f"{'; '.join(broke)}")
    else:
        print("Mutation OK (negative control) -- upper-case step references "
              "are recognised: 0 assertion(s) fail.")

    mutated = copy.deepcopy(base)
    mut_e2e_refresh_outcome_literal(mutated)
    broke = scan(mutated)
    if broke:
        problems.append(
            "a NO_REMOTE_REFRESH_JOBS refresh-outcome naming no step "
            "('skipped') was flagged -- expected 0 assertions, got: "
            f"{'; '.join(broke)}")
    else:
        print("Mutation OK (negative control) -- a literal refresh-outcome "
              "in a NO_REMOTE_REFRESH_JOBS job passes: 0 assertion(s) fail.")

    # Negative control: unlike SIMPLE_MUTATIONS, this mutation must NOT
    # break the gate (#439 review) -- it proves the toJSON(steps.<id>)
    # scoping fix actually discriminates the mint step from an unrelated
    # one, not just that a plausible-looking pattern happens to be absent
    # from the shipped tree today.
    mutated = copy.deepcopy(base)
    mut_unrelated_step_tojson_dump(mutated)
    broke = scan(mutated)
    if broke:
        problems.append(
            "a toJSON() dump of an unrelated, non-mint step was reported "
            "as a stale credential reference -- expected 0 assertions, "
            f"got: {'; '.join(broke)}")
    else:
        print("Mutation OK (negative control) -- toJSON() dump of an "
              "unrelated, non-mint step is not flagged: 0 assertion(s) fail.")

    for p in problems:
        print(f"::error::Gate 68 self-test: {p}")
    if problems:
        return 1
    print("Gate 68 self-test: clean tree passes; each mutation fails.")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()

    failures = scan(load_all())
    for f in failures:
        print(f"::error::Gate 68: {f}")
    print(f"Gate 68: post-agent credential refresh; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
