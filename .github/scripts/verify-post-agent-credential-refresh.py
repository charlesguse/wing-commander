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
For each of the 8 sweep-stage jobs (FR-007's list), except the jobs in
AGENTLESS_JOBS (tasks-approved: a PR-merge acceptance handler that never
runs an agent step by design):

1. No step positioned after the job's first agent step references
   `steps.<any-id>.outputs.*token*` directly (dot or bracket notation, or
   through `fromJSON(...)`) -- it must resolve its credential through
   `env.WC_BOT_TOKEN` / `env.WC_SCRATCH_TOKEN` instead. The one exemption is
   the relay step itself (`name` starting with "Relay" and containing
   "token to the job environment") -- that step's entire job is to read the
   fresh mint's raw output and put it in the job environment, so it
   necessarily reads the raw form (FR-020 care point 1).
2. Every agent step in a job is followed, before the next agent step or the
   job's own end (whichever comes first), by a `wing-commander-context` (or,
   for auto-update-spec-kit.yml's e2e-stage job, `scoped-app-token`)
   invocation -- checking only "between two agent steps" missed both a
   job's single agent step (clarify.yml) and the refresh after a job's LAST
   agent step entirely (FR-020 care point 2, maintainer review of PR #407
   hole (a)).
3. Every step whose name matches "Report over-budget agent run", including
   its "(cycle)"/"(retry)"/"(progress comment)"/"(auto)"/"(pr)" per-agent-step
   variants (data-model.md's 12-row table), carries `continue-on-error: true`
   (FR-021), in every job scanned -- not just jobs with an agent step, since
   the tolerance is a property of the step itself (maintainer review of PR
   #407 hole (b): an earlier version of this check matched only the bare
   name).
4. If any of the 8 named files is missing, a named job cannot be located, a
   subject job outside AGENTLESS_JOBS contains zero agent steps, or zero
   agent steps are found across the whole named subject, the gate fails
   loudly rather than passing vacuously over an empty result set (FR-022,
   Constitution Principle VIII; maintainer review of PR #407 hole (c): a
   job silently losing its agent step used to pass this gate).
5. Every "Record agent-ran signal", "Refresh authenticated spec-branch
   remote (post-agent...)", and "Determine failed post-agent step" step
   resolves through its one shared composite home
   (`.github/actions/wing-commander-agent-ran-signal`,
   `.github/actions/wing-commander-refresh-remote`,
   `.github/actions/wing-commander-failed-post-agent-step`) rather than a
   re-pasted inline `run:` block (CLAUDE.md's single-home rule; maintainer
   review of PR #407: this repository's own docs claimed byte-identity was
   already enforced here, and it was not).
6. Each of the six stages' separate 'stalled' survivor job (STALL_REASON_JOBS)
   has a "Determine which dependency did not start" step that resolves
   through `.github/actions/wing-commander-stall-reason` (second maintainer
   review of PR #407, CLAUDE.md single-home rule).
7. Every agent step has its own refresh/agent-ran/credential-status
   composite call, matched by `uses:` rather than any one step's `name:`
   (REQUIRED_PER_AGENT_STEP_COMPOSITES, exempting NO_REMOTE_REFRESH_JOBS
   from the refresh-remote leg where no git remote is ever persisted in
   that job) -- second maintainer review of PR #407, FR-020/FR-021 hole
   (a): deleting one of these steps, or renaming it away from anything
   checks 2/5 recognized by name, used to still pass Gates 68/69. Checked
   BY POSITION -- each agent step's own window, up to the next agent step
   or the job's end -- not by a job-wide total (third maintainer review of
   PR #407 hole (c)): a total alone cannot tell "each agent step has its
   own call" from "one has two and another has none," e.g. duplicating an
   earlier agent step's credential-status call while dropping a later
   one's leaves the total unchanged.
8. The "Determine failed post-agent step" composite call itself must exist
   in each of the six entry jobs whose FAILED_STEP context a stall job
   reads (FAILED_STEP_REQUIRED_JOBS) -- third maintainer review of PR #407,
   Gate 68 hole (a): check 5 above only fires when a step named "Determine
   failed post-agent step" is present, so deleting the step entirely, or
   pasting its old inline jq back under an unrecognized step name, passed
   every gate; this check requires the composite CALL to exist regardless
   of what any step is named.
9. No step BEFORE the job's first agent step relays a credential-shaped
   value into `$GITHUB_ENV` under a name other than WC_BOT_TOKEN /
   WC_SCRATCH_TOKEN (third maintainer review of PR #407, FR-020): a later
   step reading that shadow variable -- before OR after the agent step --
   would hold a token minted before the agent ran, without ever matching
   check 1's direct `steps.<id>.outputs.token` reference pattern. Also
   matches `env.WC_BOT_TOKEN`/`env.WC_SCRATCH_TOKEN` re-relayed under a
   second name, and a bare `toJSON(steps.<id>)` / `toJSON(steps)` dump
   (the whole step result, not just its outputs, still carries the token
   when the step IS the mint; since #410 check 1 catches that dump too,
   so `fromJSON(toJSON(steps.ctx)).outputs.token` in a post-agent step
   no longer passes).

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
non-agent step; a single-home composite call reverted to a non-composite
step (for each of the four single-homed step kinds); the refresh-remote
step deleted entirely; the credential-status step renamed away from its
recognized name with its `uses:` reverted; the "Determine failed
post-agent step" step deleted outright (hole (a)); implement.yml's
progress-agent-step credential-status call deleted while cycle's is
duplicated, leaving the job-wide total unchanged (hole (c)); the subject
list pointed at a 9th nonexistent file; and the subject list emptied --
and asserts each one fails.

Usage: python3 .github/scripts/verify-post-agent-credential-refresh.py [--self-test]
"""
import copy
import io
import os
import re
import sys

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
# and check 9 see the same set of token-carrying spellings.
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
    (re.compile(r"^Refresh authenticated spec-branch remote \(post-agent"),
     "wing-commander-refresh-remote"),
    (re.compile(r"^Determine failed post-agent step$"),
     "wing-commander-failed-post-agent-step"),
]

# The "Determine which dependency did not start" reason step lives in each
# stage's separate survivor/stalled job (spec 041), not the entry job
# SUBJECTS scans -- a second, small map and check covers it (second
# maintainer review of PR #407, CLAUDE.md single-home rule). auto-update-
# spec-kit.yml's e2e-stage and plan.yml are excluded: neither has a
# wing-commander-chain-stop-notice-based survivor job (contracts/
# agent-ran-signal.md's "Not in scope for consumption").
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

# path -> job names in scope, per FR-007's eight named stages.
SUBJECTS = {
    ".github/workflows/intake.yml": ["intake"],
    ".github/workflows/clarify.yml": ["clarify"],
    ".github/workflows/plan.yml": ["plan"],
    ".github/workflows/tasks.yml": ["tasks", "tasks-approved"],
    ".github/workflows/implement.yml": ["implement"],
    ".github/workflows/finalize.yml": ["finalize"],
    ".github/workflows/pr-conversation.yml": ["classify-and-announce", "act"],
    ".github/workflows/auto-update-spec-kit.yml": ["e2e-stage"],
}

# Jobs in SUBJECTS that never run an agent step, by design -- tasks-approved
# is a PR-merge acceptance handler with no agent involvement at all (unlike
# every other SUBJECTS job, whose absence of an agent step would mean the
# sweep regressed). Exempted from the "must contain an agent step" check
# (FR-020 care point 4/maintainer review of PR #407 hole (c)); still scanned
# for checks 3 and 5, which apply regardless of agent-step presence (checks
# 1 and 2 are inherently agent-step-relative and never run for such a job).
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
    # T009 (this feature's own tasks.md): classify-and-announce resolves
    # spec-meta.json via the contents API rather than a "Checkout spec
    # branch" step, so there is no persisted git remote credential to
    # refresh in this job either.
    (".github/workflows/pr-conversation.yml", "classify-and-announce"),
}

# Third maintainer review of PR #407, Gate 68 hole (a): nothing previously
# required the "Determine failed post-agent step" step to exist at all --
# check 5 (SINGLE_HOME_STEPS) only fires when a step matching that NAME is
# present, so deleting the step entirely, or pasting the old inline jq
# back under a different step name, passed every gate. This is the entry
# job (not the survivor/stalled job) whose FAILED_STEP output the stall
# path reads -- the same six jobs STALL_REASON_JOBS names, with
# pr-conversation's and tasks.yml's survivor job translated to its own
# entry job. 'act' (pr-conversation) and 'tasks-approved' are excluded:
# neither has a survivor job wrapping it (tasks-approved is also agentless
# -- AGENTLESS_JOBS -- so it has nothing to report as a failed post-agent
# step in the first place).
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
_STEP_ID_RE = re.compile(r"steps(?:\.([\w-]+)|\[[\'\"]([\w-]+)[\'\"]\])")


def _toJSON_dump_is_mint(matched_text, mint_ids):
    """A `toJSON(steps.<id>...)` match only implicates a credential when
    <id> names a mint step in this job. `toJSON(steps)` (the whole
    context, no id to extract) always implicates one when the job has a
    mint step at all, since the dumped context necessarily carries it."""
    if matched_text == "toJSON(steps)":
        return bool(mint_ids)
    m = _STEP_ID_RE.search(matched_text)
    ref_id = (m.group(1) or m.group(2)) if m else None
    return ref_id in mint_ids


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


def load_all(root="."):
    """-> {path: parsed_yaml_or_None} for every subject file."""
    out = {}
    for path in SUBJECTS:
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            out[path] = None
            continue
        with io.open(full, encoding="utf-8") as f:
            out[path] = yaml.safe_load(f) or {}
    return out


def check_job(path, job_name, job):
    """-> (failures: list[str], agent_step_count: int)."""
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

    agent_idxs = [i for i, s in enumerate(steps) if _is_agent_step(s)]
    if not agent_idxs:
        if job_name not in AGENTLESS_JOBS:
            failures.append(
                f"{path} [{job_name}]: expected at least one agent step "
                f"(uses: anthropics/claude-code-action@*) in this job and "
                f"found none -- either the sweep regressed or this job "
                f"belongs in AGENTLESS_JOBS (FR-020 care point 4/maintainer "
                f"review of PR #407 hole (c))")
        return failures, 0

    first = agent_idxs[0]

    # check 1 -- no stale credential reference after the first agent step.
    mint_ids = {(s or {}).get("id") for s in steps if _is_mint_step(s) and (s or {}).get("id")}
    for step in steps[first + 1:]:
        if _is_relay_step(step):
            continue
        name = (step or {}).get("name", "<unnamed step>")
        m = TOKEN_REF_RE.search(_step_text(step))
        if m and m.group(0).startswith("toJSON(") and not _toJSON_dump_is_mint(m.group(0), mint_ids):
            continue
        if m:
            failures.append(
                f"{path} [{job_name}] step {name!r} references "
                f"{m.group(0)} after the job's first agent step -- it must "
                f"resolve its credential through env.WC_BOT_TOKEN / "
                f"env.WC_SCRATCH_TOKEN instead (FR-020 care point 1)")

    # check 9 -- a step BEFORE the agent step relaying a pre-agent-minted
    # credential-shaped value into $GITHUB_ENV under a name other than
    # WC_BOT_TOKEN/WC_SCRATCH_TOKEN -- third maintainer review of PR #407,
    # FR-020: any later step reading that shadow variable (before or after
    # the agent step) holds a token minted before the agent ran, without
    # ever matching check 1's direct steps.<id>.outputs.token pattern.
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
    # 052's own T042/data-model.md), so in a multi-agent-step job all of a
    # job's credential-status calls cluster at the END, never inside any
    # individual agent step's window. Its "position" is therefore checked
    # by REFERENCE, not by sequential order: each agent step's own mint
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
        mint_ref_re = re.compile(
            rf"steps(?:\.{re.escape(mint_id)}\b"
            rf"|\[[\'\"]{re.escape(mint_id)}[\'\"]\])")
        referenced = any(
            "wing-commander-post-agent-credential-status" in str((s or {}).get("uses", ""))
            and mint_ref_re.search(_step_text(s))
            for s in steps)
        if not referenced:
            failures.append(
                f"{path} [{job_name}]: agent step {agent_name!r}'s mint "
                f"step (id: {mint_id!r}) is never referenced by any "
                f"wing-commander-post-agent-credential-status call's "
                f"mint-outcome anywhere in the job -- this agent step has "
                f"no credential-status call of its OWN, even though the "
                f"job-wide total may look sufficient (FR-020, FR-021, "
                f"third maintainer review of PR #407 hole (c))")

    # check 7 -- the "Determine failed post-agent step" composite call must
    # actually exist in this job, not merely be well-formed when present --
    # third maintainer review of PR #407, Gate 68 hole (a).
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

    return failures, len(agent_idxs)


def check_stall_reason_job(path, job):
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
    return []


def scan(loaded, subjects=None, stall_reason_jobs=None):
    subjects = SUBJECTS if subjects is None else subjects
    stall_reason_jobs = (STALL_REASON_JOBS if stall_reason_jobs is None
                         else stall_reason_jobs)
    failures = []
    total_agent_steps = 0
    for path, job_name in stall_reason_jobs.items():
        wf = loaded.get(path)
        if wf is None:
            # Already reported (or not, per subjects) by the main SUBJECTS
            # loop below when path is also a SUBJECTS key; otherwise still
            # worth naming here so a missing file is never silently unchecked.
            failures.append(
                f"{path}: file not found -- cannot check its stall-reason "
                f"composite call (FR-022)")
            continue
        job = (wf.get("jobs") or {}).get(job_name)
        if job is None:
            failures.append(
                f"{path}: job {job_name!r} not found -- cannot check its "
                f"stall-reason composite call (FR-022)")
            continue
        failures += check_stall_reason_job(path, job)

    for path, job_names in subjects.items():
        wf = loaded.get(path)
        if wf is None:
            failures.append(
                f"{path}: file not found -- cannot check its credential "
                f"handling (FR-022)")
            continue
        jobs = wf.get("jobs") or {}
        for job_name in job_names:
            job = jobs.get(job_name)
            if job is None:
                failures.append(
                    f"{path}: job {job_name!r} not found -- cannot check "
                    f"its credential handling (FR-022)")
                continue
            job_failures, n_agent = check_job(path, job_name, job)
            failures += job_failures
            total_agent_steps += n_agent

    if total_agent_steps == 0:
        failures.append(
            "zero agent steps were found across the named workflow "
            "files/jobs -- the subject list is misconfigured or "
            "unreachable, never a silent pass over an empty result set "
            "(FR-022)")

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
    """Hole (c): a subject job that stops having an agent step must fail
    loudly, not silently skip all of its checks."""
    job = loaded[".github/workflows/clarify.yml"]["jobs"]["clarify"]
    step = _find_step(job, "Fold answers into the draft spec")
    assert step is not None, "fixture assumption broken: step renamed"
    assert "claude-code-action" in str(step.get("uses", "")), \
        "fixture assumption broken: no longer the agent step"
    step["uses"] = "actions/checkout@v5"


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


def mut_nonexistent_ninth_file(loaded_and_subjects):
    loaded, subjects = loaded_and_subjects
    subjects["nonexistent-ninth-workflow.yml"] = ["some-job"]


def mut_zero_files(loaded_and_subjects):
    loaded, subjects = loaded_and_subjects
    subjects.clear()


def mut_nonexistent_job_in_existing_file(loaded_and_subjects):
    """should-fix (PR #407 review): a job that cannot be located inside an
    existing, reachable file is its own failure mode from a missing file."""
    loaded, subjects = loaded_and_subjects
    subjects[".github/workflows/clarify.yml"] = ["nonexistent-job"]


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
    ("a single-home composite call reverted to a non-composite step",
     mut_single_home_reverted),
    ("the 'Determine failed post-agent step' composite call reverted to a "
     "non-composite step", mut_failed_step_single_home_reverted),
    ("the 'Determine which dependency did not start' composite call (in "
     "the stalled job) reverted to a non-composite step",
     mut_stall_reason_single_home_reverted),
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
]

SUBJECT_MUTATIONS = [
    ("the subject list pointed at a 9th, nonexistent workflow file",
     mut_nonexistent_ninth_file),
    ("the subject list pointed at zero workflow files", mut_zero_files),
    ("the subject list pointed at a nonexistent job inside an existing "
     "file", mut_nonexistent_job_in_existing_file),
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

    for label, apply_mutation in SUBJECT_MUTATIONS:
        mutated_loaded = copy.deepcopy(base)
        mutated_subjects = copy.deepcopy(SUBJECTS)
        apply_mutation((mutated_loaded, mutated_subjects))
        broke = scan(mutated_loaded, mutated_subjects)
        if not broke:
            problems.append(f"MUTATION SURVIVED -- reintroducing {label!r} "
                            f"broke nothing in this gate.")
        else:
            print(f"Mutation OK -- {label}: {len(broke)} assertion(s) fail.")

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
