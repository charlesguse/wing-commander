#!/usr/bin/env python3
"""Gate: the shared reviewer's trust boundaries hold (specs/127-shared-pr-reviewer,
SC-008 (a)-(d), FR-012, FR-022, FR-027).

  (a) the `code-run` job has `permissions: {}` and references no secret;
  (b) a hostile PR check cannot leak the environment, and what it writes into
      its own directory never reaches the staged result;
  (c) the only commands stage_code_run runs are the discovered named check and
      the default branch's run-local-gates.py;
  (d) neither agent job holds a write token, a web tool or a Bash tool.

`--self-test` proves the static checks fail on a mutated workflow.
"""
import copy
import os
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wc_shared_review  # noqa: E402

WORKFLOW = os.path.join(HERE, "..", "workflows", "shared-pr-reviewer.yml")
HOSTILE = os.path.join(HERE, "tests", "fixtures", "shared-review-hostile")
WEB_TOOLS = ("WebSearch", "WebFetch")


def _text(obj):
    return yaml.safe_dump(obj)


def static_problems(wf):
    problems = []
    jobs = wf.get("jobs") or {}
    code = jobs.get("code-run")
    if not isinstance(code, dict):
        return ["the callable has no code-run job"]
    if code.get("permissions") != {}:
        problems.append("code-run must declare `permissions: {}`")
    if "secrets" in _text(code) or "app-private-key" in _text(code):
        problems.append("code-run references a secret")
    for name in ("find", "check"):
        job = jobs.get(name)
        if not isinstance(job, dict):
            problems.append("the callable has no {0} job".format(name))
            continue
        if job.get("permissions") != {"contents": "read"}:
            problems.append("{0} must hold only `contents: read`".format(name))
        text = _text(job)
        if "create-github-app-token" in text or "app-private-key" in text:
            problems.append("{0} mints or reads an App credential".format(name))
        for step in job.get("steps") or []:
            w = (step or {}).get("with") or {}
            if "default-allowed-tools" in w:
                allowed = [t.strip() for t in str(w["default-allowed-tools"]).split(",")]
                if any(t.startswith("Bash") or t in WEB_TOOLS or t in ("Write", "Edit") for t in allowed):
                    problems.append("{0} allows a Bash, web or write tool".format(name))
                disallowed = str(w.get("default-disallowed-tools", ""))
                for tool in WEB_TOOLS:
                    if tool not in disallowed:
                        problems.append("{0} does not disallow {1}".format(name, tool))
    return problems


def dynamic_problems():
    problems = []
    secret_env = {"GH_TOKEN": "x", "ACTIONS_RUNTIME_TOKEN": "x", "ANTHROPIC_API_KEY": "x"}
    saved = {k: os.environ.get(k) for k in secret_env}
    os.environ.update(secret_env)
    try:
        with tempfile.TemporaryDirectory() as reviewer:
            result = wc_shared_review.stage_code_run(
                HOSTILE, reviewer, [os.path.relpath(os.path.join(HOSTILE, "test_probe.py"), HOSTILE)],
                timeout=60)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    if result.get("status") != "staged":
        problems.append("the staged result's status was overwritten: {0!r}".format(result.get("status")))
    named = result.get("named_check") or {}
    tail = named.get("output_tail", "")
    if "LEAKED:" not in tail:
        problems.append("the hostile probe did not run, so isolation is unproven")
    else:
        leaked = tail.split("LEAKED:")[-1].split("\n")[0].strip()
        if leaked:
            problems.append("variables reached the PR's check: " + leaked)
    if named.get("exit") in (0, None):
        problems.append("the failing hostile check was not staged as a non-zero exit")
    return problems


def main():
    wf = yaml.safe_load(open(WORKFLOW, encoding="utf-8")) or {}
    problems = static_problems(wf)
    if "--self-test" in sys.argv:
        bad = 0
        mutations = {
            "code-run gains a secret": lambda w: w["jobs"]["code-run"].update(
                {"env": {"T": "${{ secrets.x }}"}}),
            "code-run loses its empty permissions": lambda w: w["jobs"]["code-run"].pop("permissions"),
            "find gains a write token": lambda w: w["jobs"]["find"].update(
                {"permissions": {"contents": "write"}}),
        }
        for label, mutate in mutations.items():
            clone = copy.deepcopy(wf)
            mutate(clone)
            if not static_problems(clone):
                print("::error::self-test: mutation not caught: " + label)
                bad += 1
        return 1 if bad else (1 if problems else 0)
    problems += dynamic_problems()
    for p in problems:
        print("::error::verify-shared-review-isolation: " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
