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

Ground 1 (rate limit) requires ALL of the following in the cited run's own
execution-output transcript (spec.md's rate-limit story and edge cases,
contracts/triage.md fixture 1):
  - rate-limit evidence: a `rate_limit_event` record, or a terminal result
    with `terminal_reason == "api_error"` and `api_error_status == "429"`;
  - one turn: the terminal result's `num_turns` is a number <= 1;
  - zero cost: the terminal result's `total_cost_usd` is a number == 0.
Rate-limit evidence alone is NOT enough: Claude Code emits informational
`rate_limit_event` records in ordinary long runs, and #402 was wrongly
closed on a 451-turn, $43 run that carried one. Missing or non-numeric
turns/cost never close.

Ground 2 (action bump) has no prior art in this repository (research.md D4):
it diffs the cited run's own workflow file's `uses: owner/action@ref` pins
(plus those of the local reusable workflows it calls -- never any other
workflow, #505) as they stood at the cited run's own commit against the
same file's pins on current `main`.
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


def _number(value):
    """value as a float when it is a real number (not a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def check_rate_limit(run_transcript_path):
    """Reads the cited run's own execution-output transcript and returns
    {"rate_limit_event": True, "api_error_status": "429",
     "num_turns": <int>, "cost_usd": <float>} only when ALL of these hold:
      1. rate-limit evidence -- a `rate_limit_event` record, or a terminal
         result with `terminal_reason == "api_error"` and
         `api_error_status == "429"`;
      2. one turn -- the terminal result's `num_turns` is present, numeric,
         and <= 1;
      3. zero cost -- the terminal result's `total_cost_usd` is present,
         numeric, and == 0.
    Else None. Evidence alone is not a rate-limited run: ordinary long runs
    carry informational `rate_limit_event` records (#402). Missing or
    non-numeric turns/cost return None -- never close on absent evidence.
    Never raises on a missing/unparsable transcript -- the caller
    (triage()) treats that as evidence_unavailable, not as "no rate
    limit"."""
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

    num_turns = _number(result.get("num_turns"))
    cost_usd = _number(result.get("total_cost_usd"))
    if num_turns is None or num_turns > 1:
        return None
    if cost_usd is None or cost_usd != 0:
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


# A `uses: ./.github/workflows/<name>.yml` line -- a local reusable
# workflow the cited workflow calls, and so part of what the cited run
# executed. A local ref carries no `@ref`, so _uses_pins() never reads it
# as a pin; this pattern only widens the scope to the callee's own file.
LOCAL_REUSABLE_RE = re.compile(
    r"^\s*(?:-\s+)?uses:\s*[\"']?\./(\.github/workflows/[^\s\"'@#]+\.ya?ml)",
    re.MULTILINE)


def _normalize_workflow_path(path):
    """The run API's `path` field (".github/workflows/x.yml"), with any
    trailing "@ref" stripped. None for a missing or blank value."""
    if not path:
        return None
    return str(path).strip().split("@", 1)[0] or None


def _scoped_workflow_files(cited_workflow_path, workflow_files, read_at_run):
    """#505: the only files check_action_bump() may compare -- the cited
    run's own workflow plus every local reusable workflow it calls
    (transitively, each as it stood at the run's commit). A bump in an
    unrelated workflow says nothing about why THIS run failed, so it must
    never become close evidence for the issue that cites the run.

    `workflow_files` is main's own tracked workflow list and only bounds
    the scope: a cited path not in it (a dynamic workflow such as
    "dynamic/pages/...", or one since deleted or renamed) yields [] --
    there is no main-side file to compare against, so no bump can be
    shown. `read_at_run(path)` returns the file's text at the run's
    commit, or None; it is injected so this stays fixturable without a git
    history. Order: the cited workflow first, then callees as found."""
    cited = _normalize_workflow_path(cited_workflow_path)
    tracked = set(workflow_files or [])
    if cited is None or cited not in tracked:
        return []
    scoped = []
    queue = [cited]
    while queue:
        path = queue.pop(0)
        if path in scoped or path not in tracked:
            continue
        scoped.append(path)
        queue.extend(LOCAL_REUSABLE_RE.findall(read_at_run(path) or ""))
    return scoped


def check_action_bump(run_commit_sha, workflow_files, cited_workflow_path):
    """NEW (research.md D4). Runtime wrapper: reads the `uses:` pins of the
    cited run's own workflow file(s) -- cited_workflow_path (the run API's
    `path` field) plus the local reusable workflows it calls, see
    _scoped_workflow_files() -- as they stood at run_commit_sha (via
    `git show`) and on current main (HEAD of this checkout, i.e. the
    working tree), and returns the first divergence via
    _first_divergent_pin(). workflow_files (main's tracked workflows)
    bounds that scope and never widens it (#505). Because run_commit_sha
    is verified here to be an ancestor of main on a fast-forward-only
    branch, any divergence found IS main's pin being the newer one --
    there is no older-pin case once ancestry holds. Returns None when
    every in-scope pin matches, the cited workflow is unknown or not
    tracked on main, the commit cannot be confirmed as an ancestor of
    main, or a workflow file's content cannot be read at that commit."""
    if _normalize_workflow_path(cited_workflow_path) is None:
        return None
    if not _is_ancestor(run_commit_sha):
        return None

    run_texts = {}

    def read_at_run(path):
        if path not in run_texts:
            run_texts[path] = _git_show(run_commit_sha, path)
        return run_texts[path]

    for workflow_file in _scoped_workflow_files(
            cited_workflow_path, workflow_files, read_at_run):
        run_text = read_at_run(workflow_file)
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
    "cited_run_workflow_path": str|None, "workflow_files": [str], "agent_proposal": {"close": bool, "ground":
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
        bump_evidence = check_action_bump(
            commit_sha, workflow_files, issue.get("cited_run_workflow_path"))
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


FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _unquoted_unfenced(text):
    """`text` with every `>`-quoted line and every fenced code block
    removed. #505 review: a trusted author quote-replying to a stranger's
    comment (or pasting it in a code block) carries the stranger's run link
    into trusted text; neither is the trusted author citing that run. An
    unclosed fence runs to the end of the text, as it renders -- that can
    only drop a cite, never add one."""
    kept = []
    fence = None
    for line in (text or "").split("\n"):
        if fence is not None:
            stripped = line.lstrip(" ")
            if (len(line) - len(stripped) <= 3 and stripped.startswith(fence)
                    and not stripped.rstrip().lstrip(fence[0])):
                fence = None
            continue
        match = FENCE_OPEN_RE.match(line)
        if match:
            fence = match.group(1)
            continue
        if line.lstrip().startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept)


def find_cited_run(text, repository):
    """#505: the run an issue cites, from text that already passed
    wing-commander-issue-context's trust filter (its context-file: title,
    body, then qualifying comments oldest first). Quoted lines and fenced
    code blocks are ignored (see _unquoted_unfenced). A watchdog issue's own
    `_First seen: [this run](URL)_` marker (watchdog.yml) wins over any
    other run link; otherwise the first run link of `repository` wins.
    Returns the run URL (https://github.com/OWNER/REPO/actions/runs/ID) or
    None."""
    run_url = r"https://github\.com/{0}/actions/runs/[0-9]+".format(
        re.escape(repository))
    scanned = _unquoted_unfenced(text)
    first_seen = re.search(
        r"_First seen: \[this run\]\((" + run_url + r")[^)\s]*\)_", scanned)
    if first_seen:
        return first_seen.group(1)
    match = re.search(run_url + r"(?![0-9])", scanned)
    return match.group(0) if match else None


def main():
    """Runtime entry point: reads the same shape triage() expects from
    stdin as JSON `{"issue": {...}, "cited_run": str|None}`, prints the
    TriageVerdict as JSON to stdout.

    `find-cited-run --repository OWNER/REPO FILE` instead prints
    find_cited_run() of FILE (nothing when no run is cited) -- the single
    home board-loop.yml's triage `cite` step calls."""
    if len(sys.argv) > 1 and sys.argv[1] == "find-cited-run":
        import argparse
        parser = argparse.ArgumentParser(prog="board_triage.py find-cited-run")
        parser.add_argument("--repository", required=True)
        parser.add_argument("context_file")
        args = parser.parse_args(sys.argv[2:])
        with open(args.context_file, encoding="utf-8") as fh:
            print(find_cited_run(fh.read(), args.repository) or "")
        return
    payload = json.load(sys.stdin)
    verdict = triage(payload.get("issue") or {}, payload.get("cited_run"))
    print(json.dumps(verdict))


if __name__ == "__main__":
    main()
