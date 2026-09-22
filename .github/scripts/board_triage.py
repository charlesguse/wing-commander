#!/usr/bin/env python3
"""Board loop triage (specs/057-autonomous-board-loop, contracts/triage.md,
research.md D4, data-model.md "Triage Verdict").

WHY THIS EXISTS
---------------
Triage MUST close an issue only on evidence it re-derives itself, never on
an agent's unverified proposal (FR-011/FR-012, Principle IX). This module is
that gate: it takes an agent's proposal only as an input to check for
disagreement (edge case, spec.md) -- the two real close grounds are decided
here, in code, from the cited run's own transcript and current `main`.

Ground 1 (rate limit) mirrors wing-commander-agent-verdict's own
classification rules (spec 047) rather than re-parsing the transcript a
second, divergent way: a `rate_limit_event` record, or a terminal
`api_error_status == "429"`, in the cited run's own execution-output
transcript.

Ground 2 (action bump) has no prior art in this repository (research.md D4):
it diffs each workflow file's `uses: owner/action@ref` pins as they stood at
the cited run's own commit against the same file's pins on current `main`.
Because the cited run's commit is (by construction, verified here) an
ancestor of `main` on a fast-forward-only branch, ANY divergent pin between
that commit and `main` is, by definition, a pin `main` moved to later --
there is no older-pin case to distinguish once ancestry holds.
"already fixed on `main`" (FR-012's explicit third ground) is NOT
implemented here -- see the module docstring for `triage()` below.
"""
import json
import re
import subprocess
import sys

USES_RE = re.compile(r"^\s*uses:\s*(\S+)\s*$", re.MULTILINE)


def _last_of_type(records, type_name):
    matches = [r for r in records if isinstance(r, dict) and r.get("type") == type_name]
    return matches[-1] if matches else None


def check_rate_limit(run_transcript_path):
    """Delegates to wing-commander-agent-verdict's existing rate-limited
    classifier (spec 047, research.md D4): reads the cited run's own
    execution-output transcript and returns
    {"rate_limit_event": True, "api_error_status": "429",
     "num_turns": <int>, "cost_usd": <float>} when that transcript carries
    rate-limit evidence, else None. Never raises on a missing/unparsable
    transcript -- the caller (triage()) treats that as evidence_unavailable,
    not as "no rate limit"."""
    try:
        with open(run_transcript_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None

    records = data if isinstance(data, list) else [data]
    result = _last_of_type(records, "result")
    if not result:
        return None

    rate_limit_event = _last_of_type(records, "rate_limit_event")
    terminal_reason = result.get("terminal_reason")
    api_error_status = str(result.get("api_error_status") or "")

    rate_limited = bool(rate_limit_event) or (
        terminal_reason == "api_error" and api_error_status == "429")
    if not rate_limited:
        return None

    return {
        "rate_limit_event": True,
        "api_error_status": "429",
        "num_turns": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"),
    }


def _uses_pins(text):
    """{owner/action: ref} for every `uses: owner/action@ref` line."""
    pins = {}
    for match in USES_RE.finditer(text or ""):
        value = match.group(1)
        if "@" not in value:
            continue
        name, ref = value.rsplit("@", 1)
        pins[name] = ref
    return pins


def _git_show(ref, path):
    proc = subprocess.run(
        ["git", "show", "{0}:{1}".format(ref, path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def _is_ancestor(commit_sha, of_ref="HEAD"):
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit_sha, of_ref],
        capture_output=True, text=True)
    return proc.returncode == 0


def _first_divergent_pin(workflow_file, run_pins, main_pins):
    """Pure comparison, fixturable without a real git history (contracts/
    triage.md: "each a checked-in transcript/workflow-pin pair"). Returns
    {workflow_file, action_ref, run_pin, main_pin} for the first (sorted by
    action_ref) pin present in both maps but with a different ref, else
    None."""
    for action_ref, run_pin in sorted(run_pins.items()):
        main_pin = main_pins.get(action_ref)
        if main_pin is not None and main_pin != run_pin:
            return {
                "workflow_file": workflow_file,
                "action_ref": action_ref,
                "run_pin": run_pin,
                "main_pin": main_pin,
            }
    return None


def check_action_bump(run_commit_sha, workflow_files):
    """NEW (research.md D4). Runtime wrapper: reads each workflow file's
    `uses:` pins as they stood at run_commit_sha (via `git show`) and on
    current main (HEAD of this checkout, i.e. the working tree), and
    returns the first divergence via _first_divergent_pin(). Because
    run_commit_sha is verified here to be an ancestor of main on a
    fast-forward-only branch, any divergence found IS main's pin being the
    newer one -- there is no older-pin case once ancestry holds. Returns
    None when every pin matches, the commit cannot be confirmed as an
    ancestor of main, or a workflow file's content cannot be read at that
    commit."""
    if not _is_ancestor(run_commit_sha):
        return None

    for workflow_file in workflow_files:
        run_text = _git_show(run_commit_sha, workflow_file)
        if run_text is None:
            continue
        try:
            with open(workflow_file, encoding="utf-8") as fh:
                main_text = fh.read()
        except OSError:
            continue

        divergence = _first_divergent_pin(
            workflow_file, _uses_pins(run_text), _uses_pins(main_text))
        if divergence is not None:
            return divergence
    return None


def triage(issue, cited_run):
    """Read-only until this return value (FR-011). See data-model.md
    "Triage Verdict". `issue` carries at least {"cited_run_url": str|None,
    "cited_run_commit_sha": str|None, "cited_run_transcript_path": str|None,
    "workflow_files": [str], "agent_proposal": {"close": bool, "ground":
    str|None, "proposed_commit_sha": str|None, "reasoning": str|None}}.

    "already fixed on `main`" (FR-012's explicit deferral) has no ground
    function -- when agent_proposal names it, this returns outcome:
    handover, never a close, per FR-012."""
    proposal = issue.get("agent_proposal") or {}

    if cited_run is None:
        outcome = {"outcome": "proceed", "ground": None, "evidence": {},
                   "agent_proposal": None}
        return _record_disagreement(outcome, proposal)

    transcript_path = issue.get("cited_run_transcript_path")
    if not transcript_path:
        outcome = {"outcome": "proceed", "ground": "evidence_unavailable",
                   "evidence": {"reason": "missing"}, "agent_proposal": None}
        return _record_disagreement(outcome, proposal)

    rate_limit_evidence = check_rate_limit(transcript_path)
    if rate_limit_evidence is not None:
        evidence = dict(rate_limit_evidence)
        evidence["run_url"] = cited_run
        return {"outcome": "closed", "ground": "rate_limit",
                "evidence": evidence, "agent_proposal": None}

    import os
    if not os.path.isfile(transcript_path):
        outcome = {"outcome": "proceed", "ground": "evidence_unavailable",
                   "evidence": {"reason": "missing"}, "agent_proposal": None}
        return _record_disagreement(outcome, proposal)

    commit_sha = issue.get("cited_run_commit_sha")
    workflow_files = issue.get("workflow_files") or []
    if commit_sha:
        bump_evidence = check_action_bump(commit_sha, workflow_files)
        if bump_evidence is not None:
            return {"outcome": "closed", "ground": "action_bump",
                    "evidence": bump_evidence, "agent_proposal": None}

    if proposal.get("ground") == "already_fixed_proposal":
        return {
            "outcome": "handover",
            "ground": "already_fixed_proposal",
            "evidence": {
                "proposed_commit_sha": proposal.get("proposed_commit_sha"),
                "agent_reasoning": proposal.get("reasoning"),
            },
            "agent_proposal": proposal.get("reasoning"),
        }

    outcome = {"outcome": "proceed", "ground": None, "evidence": {},
               "agent_proposal": None}
    return _record_disagreement(outcome, proposal)


def _record_disagreement(outcome, proposal):
    """Edge case (spec.md): when the agent proposed a close the gate does
    not support, the verdict still isn't closed -- the proposal is recorded
    verbatim for the caller to post on the issue, never silently dropped."""
    if proposal.get("close") and outcome["outcome"] != "closed":
        outcome["agent_proposal"] = proposal.get("reasoning") or json.dumps(proposal)
    return outcome


def main():
    """Runtime entry point: reads the same shape triage() expects from
    stdin as JSON `{"issue": {...}, "cited_run": str|None}`, prints the
    TriageVerdict as JSON to stdout."""
    payload = json.load(sys.stdin)
    verdict = triage(payload.get("issue") or {}, payload.get("cited_run"))
    print(json.dumps(verdict))


if __name__ == "__main__":
    main()
