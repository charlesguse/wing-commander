#!/usr/bin/env python3
"""Gate 181 - an agent step with a read-only GitHub token does not inherit
the job's App token, and every agent step is denied reads of /proc.

WHY THIS EXISTS
---------------
#1310: `wing-commander-context` mints the App installation token and writes
it to `$GITHUB_ENV` as `WC_BOT_TOKEN`, so every later step in the job has it
in its environment. `anthropics/claude-code-action` hands its whole
environment to Claude. Three agent steps are deliberately given the job's
read-only `github.token` instead of the App token (lifecycle-review-gate's
Reviewer, spec-pr-review's Reviewer, watchdog's Diagnose shadow), yet they
still carried the write-capable `WC_BOT_TOKEN`, and their grants (a bare
`Read`, `Bash(cat:*)`) reach `/proc/self/environ`. Each such step now sets
`WC_BOT_TOKEN: ''` in its own `env:`, which hides the job's value from that
step alone; the post-agent re-mint and every later step (Gate 68) still see
it. The tool-args composite denies every agent `Read(//proc/**)` and
`Bash(*proc/*)`, which also covers the model credential and a GH_TOKEN the
step is meant to hold.

WHAT IT CHECKS
--------------
Every `anthropics/claude-code-action` step under `.github/workflows/`:

  1. Token scrub. In a job that runs `wing-commander-context`, a step whose
     `github_token` is not the App token (it is `github.token`, another
     read-only token, or unset) sets `WC_BOT_TOKEN` to the empty string in
     its own `env:`. In any job, such a step names the App token in no
     other `env:` value. The App token is `env.WC_BOT_TOKEN` or a
     `steps.<id>.outputs.token`.
  2. /proc deny. A step that passes a model credential (an OAuth token, an
     API key, or a Bedrock, Vertex or Foundry switch) takes its
     `--disallowedTools` from `steps.<id>.outputs.disallowed-tools`, every
     such `<id>` being a `wing-commander-tool-args` step in the same job,
     or lists both denies literally. A step in EXEMPT_PROC_DENY is held to
     its entry instead, and fails as stale once it no longer needs it.
  3. The composite. The shipped `Compose tool args` step is run three ways
     (defaults; a disallowed override of nothing plus both denies in
     extra-allowed-tools; a subfolder project) and must emit both denies
     every time, and name neither in its tooling statement.

A step with no model credential (agent-startup-check.yml's setup-only run)
reaches no model, so check 2 does not apply to it.

`--self-test` mutates the real files: it removes each override, sets one to
the App token, gives one a GH_TOKEN of the App token, drops the
github_token of one read-only step, points a step at a non-tool-args step,
gives a step a literal list without the denies, removes each deny from the
composite and its append line, and renames an exempt step. Each must
fail; the real files must pass.

Usage:
    python3 .github/scripts/verify-agent-credential-scrub.py
    python3 .github/scripts/verify-agent-credential-scrub.py --self-test
"""
import collections
import copy
import glob
import os
import re
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    production_shell, resolve_bash, run_step, use_utf8_stdout)

AGENT_PREFIX = "anthropics/claude-code-action@"
CONTEXT_RE = re.compile(r"(?:^|/)\.github/actions/wing-commander-context(?:@\S*)?$")
TOOL_ARGS_RE = re.compile(r"(?:^|/)\.github/actions/wing-commander-tool-args(?:@\S*)?$")
APP_TOKEN_RE = re.compile(r"env\.WC_BOT_TOKEN\b|steps\.[\w-]+\.outputs\.token\b")
DISALLOWED_REF_RE = re.compile(r"steps\.([\w-]+)\.outputs\.disallowed-tools\b")
DISALLOWED_ARG_RE = re.compile(r"--disallowedTools\s+(\"[^\"]*\"|'[^']*'|\S+)")
CREDENTIAL_INPUTS = ("claude_code_oauth_token", "anthropic_api_key",
                     "use_bedrock", "use_vertex", "use_foundry")
PROC_DENIES = ("Read(//proc/**)", "Bash(*proc/*)")

ACTION = os.path.join(".github", "actions", "wing-commander-tool-args", "action.yml")
COMPOSE_STEP = "Compose tool args"

Exemption = collections.namedtuple(
    "Exemption", "reason issue decided_by", defaults=((),))

_UPDATER_REASON = (
    "its tool lists are literals in a file left alone while the owner's "
    "updater work was open; the /proc denies are added there next")
# (workflow basename, step name) -> why the step lists its denies by hand
# without them (Gate 124 reads `issue=`).
EXEMPT_PROC_DENY = {
    ("auto-update-spec-kit.yml", "Decide upgrade path"): Exemption(
        reason=_UPDATER_REASON, issue=(889,), decided_by=(1310,)),
    ("auto-update-spec-kit.yml", "Run e2e agent-driven stage"): Exemption(
        reason=_UPDATER_REASON, issue=(889,), decided_by=(1310,)),
    ("auto-update-spec-kit.yml", "Interpret the maintainer's reply"): Exemption(
        reason=_UPDATER_REASON, issue=(889,), decided_by=(1310,)),
}

# The read-only agent steps this gate was written for: the self-test
# removes each one's override and expects a failure naming it.
READ_ONLY_STEPS = (
    ("lifecycle-review-gate.yml", "review", "Reviewer"),
    ("spec-pr-review.yml", "review", "Reviewer"),
    ("watchdog.yml", "diagnose", "Diagnose shadow"),
)


def _uses(step):
    return str((step or {}).get("uses") or "").strip()


def _is_agent(step):
    return isinstance(step, dict) and _uses(step).startswith(AGENT_PREFIX)


def _name(step):
    return step.get("name") or step.get("id") or "(unnamed step)"


def _items(csv):
    return [i.strip() for i in csv.split(",") if i.strip()]


def check_doc(base, doc):
    """Problems for one parsed workflow, `base` being its file name."""
    problems = []
    seen_exempt = set()
    jobs = (doc or {}).get("jobs") if isinstance(doc, dict) else None
    for job_id, job in (jobs or {}).items():
        if not isinstance(job, dict):
            continue
        steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
        has_context = any(CONTEXT_RE.search(_uses(s)) for s in steps)
        tool_args_ids = {s.get("id") for s in steps
                         if TOOL_ARGS_RE.search(_uses(s)) and s.get("id")}
        for step in steps:
            if not _is_agent(step):
                continue
            name = _name(step)
            where = f"{base}: job {job_id!r} step {name!r}"
            with_block = step.get("with") or {}
            env = step.get("env") or {}

            # 1. Token scrub.
            token = str(with_block.get("github_token") or "")
            read_only = not APP_TOKEN_RE.search(token)
            if read_only and isinstance(env, dict):
                # The step's own env: must not hand the App token back
                # under another name (the `GH_TOKEN: ${{ env.WC_BOT_TOKEN }}`
                # every App-token agent step carries).
                for k in sorted(env, key=str):
                    if k != "WC_BOT_TOKEN" and APP_TOKEN_RE.search(str(env[k])):
                        problems.append(
                            f"{where} runs with a read-only github_token "
                            f"({token or 'none'}) but its env: {k} is "
                            f"{env[k]!r}, which hands it the App token "
                            f"(#1310).")
            if has_context and read_only:
                value = env.get("WC_BOT_TOKEN", None) if isinstance(env, dict) else None
                if value != "":
                    shown = "unset" if value is None else repr(value)
                    problems.append(
                        f"{where} runs with a read-only github_token "
                        f"({token or 'none'}) in a job that runs "
                        f"wing-commander-context, but its env: WC_BOT_TOKEN "
                        f"is {shown}, so it inherits the job's App token. "
                        f"Set `WC_BOT_TOKEN: ''` in the step's own env: "
                        f"(#1310).")

            # 2. /proc deny.
            if not any(k in with_block for k in CREDENTIAL_INPUTS):
                continue
            key = (base, name)
            if key in EXEMPT_PROC_DENY:
                seen_exempt.add(key)
            args = str(with_block.get("claude_args") or "")
            m = DISALLOWED_ARG_RE.search(args)
            value = m.group(1).strip("\"'") if m else ""
            refs = DISALLOWED_REF_RE.findall(value)
            if refs:
                bad = sorted(set(r for r in refs if r not in tool_args_ids))
                if bad:
                    problems.append(
                        f"{where} takes --disallowedTools from "
                        f"{', '.join(bad)}, which is not a "
                        f"wing-commander-tool-args step in this job, so "
                        f"nothing guarantees its /proc denies (#1310).")
                elif key in EXEMPT_PROC_DENY:
                    problems.append(
                        f"{where} is in EXEMPT_PROC_DENY but now takes its "
                        f"denies from the tool-args composite: remove the "
                        f"stale entry.")
                continue
            missing = [d for d in PROC_DENIES if d not in _items(value)]
            if missing and key not in EXEMPT_PROC_DENY:
                problems.append(
                    f"{where} passes a model credential but its "
                    f"--disallowedTools ({value or 'absent'}) lacks "
                    f"{', '.join(missing)}. Compose it with "
                    f"wing-commander-tool-args, which adds both (#1310).")
            elif not missing and key in EXEMPT_PROC_DENY:
                problems.append(
                    f"{where} is in EXEMPT_PROC_DENY but already lists both "
                    f"/proc denies: remove the stale entry.")
    return problems, seen_exempt


def workflow_files(root="."):
    return sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.yml")))


def load(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def check_docs(docs):
    """docs: {basename: parsed doc}. Returns the problems, stale exemptions
    included."""
    problems = []
    seen = set()
    for base in sorted(docs):
        p, s = check_doc(base, docs[base])
        problems.extend(p)
        seen |= s
    for key in sorted(set(EXEMPT_PROC_DENY) - seen):
        problems.append(
            f"{key[0]}: EXEMPT_PROC_DENY names step {key[1]!r}, which is no "
            f"longer an agent step with a model credential: remove the "
            f"stale entry.")
    return problems


def agent_step_count(docs):
    return sum(1 for d in docs.values()
               for j in ((d or {}).get("jobs") or {}).values()
               if isinstance(j, dict)
               for s in (j.get("steps") or []) if _is_agent(s))


# --- check 3: the composite itself --------------------------------------
def compose_script(action_text):
    doc = yaml.safe_load(action_text) or {}
    for step in ((doc.get("runs") or {}).get("steps") or []):
        if (step or {}).get("name") == COMPOSE_STEP:
            return step.get("run") or "", step.get("env") or {}, step
    return None, None, None


COMPOSE_CASES = (
    ("defaults", {}),
    ("a disallowed override of nothing, both denies re-allowed",
     {"DISALLOWED_OVERRIDE": "", "EXTRA_ALLOWED": ",".join(PROC_DENIES)}),
    ("a subfolder project", {"PROJECT": "apps/web"}),
)


def check_composite(action_text, bash):
    script, step_env, step = compose_script(action_text)
    if script is None:
        return [f"{ACTION}: no step named {COMPOSE_STEP!r}; update this gate "
                f"and the action together."]
    constants = {k: str(v) for k, v in step_env.items() if "${{" not in str(v)}
    base_env = {
        **constants,
        "STEP_LABEL": "gate-181", "DEFAULT_ALLOWED": "Read,Grep,Bash(cat:*)",
        "DEFAULT_DISALLOWED": "WebFetch", "EXTRA_ALLOWED": "",
        "EXTRA_DISALLOWED": "", "ALLOWED_OVERRIDE": "__unset__",
        "DISALLOWED_OVERRIDE": "__unset__", "NO_WRITE_PATHS": "",
        "PROJECT": "", "PROJECT_DENY": "",
    }
    problems = []
    for label, overrides in COMPOSE_CASES:
        tmp = tempfile.mkdtemp(prefix="wc-gate-181-")
        try:
            os.makedirs(os.path.join(tmp, "ws"))
            env = {**base_env, **overrides,
                   "GITHUB_ACTION_PATH": os.path.abspath(os.path.dirname(ACTION)),
                   "GITHUB_WORKSPACE": os.path.join(tmp, "ws")}
            rc, output, outputs, _ = run_step(
                bash, script, tmp, env, tmp, shell=production_shell(step))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if rc != 0:
            problems.append(f"{ACTION} ({label}): the compose step exited "
                            f"{rc}: {output.strip()[:300]}")
            continue
        denied = _items(outputs.get("disallowed-tools") or "")
        missing = [d for d in PROC_DENIES if d not in denied]
        if missing:
            problems.append(
                f"{ACTION} ({label}): disallowed-tools lacks "
                f"{', '.join(missing)}: {outputs.get('disallowed-tools')!r} "
                f"(#1310).")
        # The statement names what the caller allowed, so it is read only
        # where nothing re-allows a deny.
        statement = outputs.get("shell-commands") or ""
        if "EXTRA_ALLOWED" not in overrides and "proc" in statement:
            problems.append(f"{ACTION} ({label}): the tooling statement names "
                            f"a /proc deny: {statement!r}")
    return problems


def run_real(bash):
    docs = {os.path.basename(p): load(p) for p in workflow_files()}
    action_text = open(ACTION, encoding="utf-8").read()
    return docs, action_text, check_docs(docs) + check_composite(action_text, bash)


# --- self-test ------------------------------------------------------------
def _find(docs, base, job, name):
    for step in docs[base]["jobs"][job]["steps"]:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise KeyError(f"{base} {job} {name}")


def _first_tool_args_agent(docs):
    for base in sorted(docs):
        for job_id, job in (docs[base].get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                if _is_agent(step) and DISALLOWED_REF_RE.search(
                        str((step.get("with") or {}).get("claude_args") or "")):
                    return base, job_id, step
    raise KeyError("no agent step takes its denies from tool-args")


def self_test(docs, action_text, bash):
    failures = []

    def expect(label, problems, needle):
        if not any(needle in p for p in problems):
            failures.append(f"{label}: not caught (wanted {needle!r}); "
                            f"got {problems!r}")
        else:
            print(f"note: (expected) {label}: caught")

    for base, job, name in READ_ONLY_STEPS:
        d = copy.deepcopy(docs)
        del _find(d, base, job, name)["env"]["WC_BOT_TOKEN"]
        expect(f"{base} {name!r} without its override", check_docs(d),
               f"{base}: job {job!r} step {name!r} runs with a read-only")

    d = copy.deepcopy(docs)
    _find(d, *READ_ONLY_STEPS[0])["env"]["WC_BOT_TOKEN"] = "${{ env.WC_BOT_TOKEN }}"
    expect("an override set back to the App token", check_docs(d),
           "inherits the job's App token")

    d = copy.deepcopy(docs)
    _find(d, *READ_ONLY_STEPS[1])["env"]["GH_TOKEN"] = "${{ env.WC_BOT_TOKEN }}"
    expect("an App token under another env: name", check_docs(d),
           "env: GH_TOKEN is '${{ env.WC_BOT_TOKEN }}', which hands it")

    d = copy.deepcopy(docs)
    step = _find(d, *READ_ONLY_STEPS[1])
    del step["with"]["github_token"]
    del step["env"]["WC_BOT_TOKEN"]
    expect("a step with no github_token and no override", check_docs(d),
           "read-only github_token (none)")

    d = copy.deepcopy(docs)
    base, job_id, step = _first_tool_args_agent(d)
    step["with"]["claude_args"] = DISALLOWED_REF_RE.sub(
        "steps.not-tool-args.outputs.disallowed-tools", step["with"]["claude_args"])
    expect("a step reading its denies from a non-tool-args step",
           check_docs(d), "not-tool-args, which is not a wing-commander-tool-args")

    d = copy.deepcopy(docs)
    base, job_id, step = _first_tool_args_agent(d)
    step["with"]["claude_args"] = re.sub(
        DISALLOWED_ARG_RE, '--disallowedTools "WebFetch,Write"',
        step["with"]["claude_args"], count=1)
    expect("a step listing its denies by hand without /proc", check_docs(d),
           "lacks Read(//proc/**), Bash(*proc/*)")

    d = copy.deepcopy(docs)
    (ex_base, ex_name) = sorted(EXEMPT_PROC_DENY)[0]
    for job in d[ex_base]["jobs"].values():
        for s in (job or {}).get("steps") or []:
            if isinstance(s, dict) and s.get("name") == ex_name:
                s["name"] = ex_name + " (renamed)"
    expect("an exemption whose step was renamed", check_docs(d),
           f"names step {ex_name!r}, which is no")

    for deny in PROC_DENIES:
        mutated = action_text.replace(deny, "", 1)
        expect(f"the composite without {deny}",
               check_composite(mutated, bash), f"disallowed-tools lacks {deny}")
    line = ('        effective_disallowed="${effective_disallowed:+'
            '$effective_disallowed,}$AGENT_PROC_DENIES"\n')
    if line not in action_text:
        failures.append("the composite's append line was not found; the "
                        "self-test's mutation point has drifted.")
    else:
        expect("the composite without its append line",
               check_composite(action_text.replace(line, "", 1), bash),
               "disallowed-tools lacks Read(//proc/**)")
    return failures


def main():
    use_utf8_stdout()
    if not os.path.isdir(".github"):
        sys.exit("::error::run this from the repository root.")
    bash = resolve_bash()
    docs, action_text, problems = run_real(bash)
    if agent_step_count(docs) == 0:
        print("::error::Gate 181: found no claude-code-action step; the "
              "walk regressed.")
        return 1
    for p in problems:
        print(f"::error::Gate 181: {p}")
    if problems:
        return 1
    print(f"Gate 181: {agent_step_count(docs)} agent step(s): each read-only "
          f"one sets WC_BOT_TOKEN empty, and each is denied /proc.")
    if "--self-test" in sys.argv[1:]:
        failures = self_test(docs, action_text, bash)
        for f in failures:
            print(f"::error::Gate 181 self-test: {f}")
        if failures:
            return 1
        print("Gate 181 self-test: every mutation was caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
