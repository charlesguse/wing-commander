#!/usr/bin/env python3
"""Gate: the `model:haiku` implement opt-in stays confined (spec 110, FR-014..016).

1. wing-commander-5-implement.yml's `resolve-model` job resolves the tier
   as FR-014 says, checked by RUNNING its `tier` step under bash -- the
   shell GitHub runs it with -- against a stub `gh` serving each label set,
   never by parsing the script (review gate round 9: a token heuristic over
   if/elif/fi can miscount heredocs, case/esac, $(if ...) and multi-line
   strings, and pass or fail for reasons the shell does not share):
   * no opt-in label: the default tier and escalation variables, and a
     max-turns equal to implement.yml's `max-turns` input default, so a
     non-Haiku cycle keeps the budget it has today;
   * `model:haiku`: claude-haiku-5-5, escalating to claude-sonnet-5-5
     whatever the escalation variable says, with the Haiku budget variable
     (a non-numeric or zero one falling back to that same default);
   * `model:haiku` and `model:opus`: claude-opus-5-5 (model:opus wins);
   * labels that cannot be read: the default tier, with a warning.
   The job's outputs carry the step's tier, escalation and max-turns.
2. Only that wrapper reads the label: pr-conversation and the board loop
   never mention `model:haiku`.

Usage: verify-implement-haiku-optin.py [--root DIR]
       verify-implement-haiku-optin.py --self-test
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wc_shell_pin import effective_shell, pins_bash  # noqa: E402

WRAPPER = ".github/workflows/wing-commander-5-implement.yml"
STAGE = ".github/workflows/implement.yml"
OTHERS = (".github/workflows/wing-commander-9-pr-conversation.yml",
          ".github/workflows/board-loop.yml",
          ".github/workflows/pr-conversation.yml")

HAIKU, SONNET, OPUS = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"
JOB_OUTPUTS = {"model": "${{ steps.tier.outputs.tier }}",
               "escalation-model": "${{ steps.tier.outputs.escalation }}",
               "max-turns": "${{ steps.tier.outputs.max-turns }}"}
# A stand-in for `gh issue view ... --jq '.labels[].name'`: prints the
# case's labels, or fails as an API error would.
STUB_GH = """#!/bin/sh
[ "${STUB_GH_FAIL:-}" = "1" ] && { echo "gh: HTTP 502" >&2; exit 1; }
printf '%s' "$STUB_LABELS"
"""


def stage_default(stage_text):
    try:
        doc = yaml.safe_load(stage_text) or {}
        on = doc.get("on", doc.get(True)) or {}
        return int(on["workflow_call"]["inputs"]["max-turns"]["default"])
    except (yaml.YAMLError, AttributeError, KeyError, TypeError, ValueError):
        return None


def tier_job(wrapper_text):
    """(workflow, resolve-model job, its `tier` step), or Nones."""
    try:
        doc = yaml.safe_load(wrapper_text) or {}
        job = doc["jobs"]["resolve-model"]
        step = next(s for s in job["steps"] if s.get("id") == "tier")
    except (yaml.YAMLError, AttributeError, KeyError, TypeError, StopIteration):
        return None, None, None
    return doc, job, step


def run_shell(doc, job, step):
    """The shell the runner uses for this step, resolved by
    wc_shell_pin.effective_shell (step > job > workflow `defaults.run.
    shell`, the one home of that rule), as a template with {0}; with no
    shell set anywhere, `bash -e {0}` on a runner but sh inside a
    `container:` job. None for anything this gate does not run (it runs
    bash only) or cannot read."""
    try:
        shell = effective_shell(step, job, doc)
    except AttributeError:
        return None
    if not shell:
        return None if job.get("container") else "bash -e {0}"
    if shell == "bash":
        return "bash --noprofile --norc -eo pipefail {0}"
    if pins_bash(shell) and "{0}" in str(shell):
        return str(shell)
    return None


def run_tier(template, step, bindir, labels, env_vars, gh_fails=False):
    """Run the step's script under `template` with the stub gh in `bindir`
    and return (outputs dict, stdout+stderr, exit code)."""
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "step.sh"
        script.write_text(step.get("run") or "", encoding="utf-8")
        out, summary = Path(tmp) / "output", Path(tmp) / "summary"
        out.write_text("", encoding="utf-8")
        env = {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
               "HOME": tmp, "GITHUB_OUTPUT": str(out),
               "GITHUB_STEP_SUMMARY": str(summary),
               "GITHUB_REPOSITORY": "owner/repo", "STUB_LABELS": labels,
               "STUB_GH_FAIL": "1" if gh_fails else ""}
        # The step's own env: block, with its ${{ }} expressions replaced by
        # the case's values (unset variables are empty, as in Actions).
        for key in (step.get("env") or {}):
            env[key] = ""
        env.update({"ISSUE": "1", "GH_TOKEN": "x"})
        env.update(env_vars)
        argv = template.replace("{0}", str(script)).split()
        proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                              check=False, timeout=30)
        outputs = {}
        for line in out.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                outputs[key] = value
    return outputs, proc.stdout + proc.stderr, proc.returncode


def behaviour_failures(wrapper_text, budget):
    doc, job, step = tier_job(wrapper_text)
    if step is None:
        return [f"{WRAPPER}: no resolve-model job with a `tier` step"]
    template = run_shell(doc, job, step)
    if template is None:
        return [f"{WRAPPER}: the tier step's shell is not bash (or cannot "
                "be read); this gate runs it under bash only"]
    with tempfile.TemporaryDirectory() as bindir:
        gh = Path(bindir) / "gh"
        gh.write_text(STUB_GH, encoding="utf-8")
        gh.chmod(0o755)
        return run_cases(template, job, step, bindir, budget)


def run_cases(template, job, step, bindir, budget):
    failures = []
    outputs = job.get("outputs") or {}
    for name, want in JOB_OUTPUTS.items():
        if str(outputs.get(name, "")).strip() != want:
            failures.append(f"{WRAPPER}: resolve-model output {name} must be "
                            f"{want!r}, got {outputs.get(name)!r}")
    defaults = {"MODEL_VAR": "", "ESCALATION_VAR": "", "HAIKU_MAX_TURNS": ""}
    cases = [
        # (name, labels, env, gh fails, expected tier/escalation/max-turns,
        #  text the run must print)
        ("no label", "", defaults, False, (SONNET, OPUS, budget), None),
        ("other labels", "spec-request\nmodel:haikus", defaults, False,
         (SONNET, OPUS, budget), None),
        ("model:haiku", "spec-request\nmodel:haiku", defaults, False,
         (HAIKU, SONNET, budget), None),
        ("model:haiku, budget and escalation variables set", "model:haiku",
         dict(defaults, MODEL_VAR="claude-x", ESCALATION_VAR="claude-y",
              HAIKU_MAX_TURNS="60"), False, (HAIKU, SONNET, 60), None),
        ("model:haiku, non-numeric budget", "model:haiku",
         dict(defaults, HAIKU_MAX_TURNS="lots"), False,
         (HAIKU, SONNET, budget), None),
        ("model:haiku, zero budget", "model:haiku",
         dict(defaults, HAIKU_MAX_TURNS="0"), False, (HAIKU, SONNET, budget),
         None),
        ("model:opus", "model:opus", defaults, False, (OPUS, OPUS, budget),
         None),
        ("model:haiku and model:opus", "model:haiku\nmodel:opus", defaults,
         False, (OPUS, OPUS, budget), None),
        ("model:opus and model:haiku, variables set", "model:opus\nmodel:haiku",
         dict(defaults, ESCALATION_VAR="claude-y", HAIKU_MAX_TURNS="60"),
         False, (OPUS, "claude-y", budget), None),
        ("labels unreadable", "model:haiku", defaults, True,
         (SONNET, OPUS, budget), "::warning::"),
    ]
    for name, labels, env, gh_fails, want, prints in cases:
        try:
            got, log, rc = run_tier(template, step, bindir, labels, env,
                                    gh_fails)
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{name}: the tier step could not run: {exc}")
            continue
        seen = (got.get("tier"), got.get("escalation"), got.get("max-turns"))
        expect = (want[0], want[1], str(want[2]))
        if rc != 0 or seen != expect:
            failures.append(f"{WRAPPER} tier step, {name}: expected tier/"
                            f"escalation/max-turns {expect}, got {seen} "
                            f"(rc={rc}) {log.strip()[-200:]}")
        elif prints and prints not in log:
            failures.append(f"{WRAPPER} tier step, {name}: must print "
                            f"{prints!r}")
    return failures


def check(texts):
    """texts maps repo-relative path -> file text; returns failure strings."""
    wrapper, stage = texts.get(WRAPPER), texts.get(STAGE)
    if wrapper is None or stage is None:
        return [f"{WRAPPER} or {STAGE} missing"]
    failures = []
    budget = stage_default(stage)
    if budget is None:
        failures.append(f"cannot read {STAGE}'s max-turns input default")
    else:
        failures += behaviour_failures(wrapper, budget)
    for rel in OTHERS:
        if rel not in texts:
            failures.append(f"{rel} missing; the confinement check cannot run")
        elif "model:haiku" in texts[rel]:
            failures.append(f"{rel} must not read the model:haiku label")
    return failures


GOOD_RUN = """tier="${MODEL_VAR:-claude-sonnet-5-5}"
escalation="${ESCALATION_VAR:-claude-opus-5-5}"
max_turns=180
labels="$(gh issue view "$ISSUE" --json labels)" || {
  echo "::warning::could not read labels"
  labels=''
}
if grep -qx 'model:opus' <<< "$labels"; then
  tier="claude-opus-5-5"
elif grep -qx 'model:haiku' <<< "$labels"; then
  tier="claude-haiku-5-5"
  escalation="claude-sonnet-5-5"
  max_turns="${HAIKU_MAX_TURNS:-180}"
  case "$max_turns" in
    ''|*[!0-9]*|0|0[0-9]*) max_turns=180 ;;
  esac
fi
{
  echo "tier=$tier"
  echo "escalation=$escalation"
  echo "max-turns=$max_turns"
} >> "$GITHUB_OUTPUT"
"""
GOOD_STAGE = ("on:\n  workflow_call:\n    inputs:\n      max-turns:\n"
              "        type: number\n        default: 180\n")


def wrapper_doc(run):
    return yaml.safe_dump({"jobs": {"resolve-model": {
        "outputs": dict(JOB_OUTPUTS),
        "steps": [{"name": "Resolve model tier", "id": "tier",
                   "env": {"MODEL_VAR": "x", "ESCALATION_VAR": "x",
                           "HAIKU_MAX_TURNS": "x", "ISSUE": "x"},
                   "run": run}]}}}, sort_keys=False)


def self_test():
    base = {WRAPPER: wrapper_doc(GOOD_RUN), STAGE: GOOD_STAGE,
            OTHERS[0]: "model:opus\n", OTHERS[1]: "model:opus\n",
            OTHERS[2]: "model:opus\n"}
    ok = True
    if check(base):
        print(f"self-test: the good layout must pass: {check(base)}",
              file=sys.stderr)
        ok = False
    escalation = '  escalation="claude-sonnet-5-5"\n'
    good = {
        # Shapes the old token heuristic misread; the shell does not.
        "heredoc quoting fi": GOOD_RUN.replace(
            escalation, escalation + "  cat >/dev/null <<'EOF'\nfi\nelse\nEOF\n"),
        "case/esac inside the branch": GOOD_RUN.replace(
            escalation, escalation + '  case "$x" in a) : ;; esac\n'),
        "$(if ...) substitution": GOOD_RUN.replace(
            escalation, escalation + '  y="$(if true; then echo fi; fi)"\n'),
        "multi-line string": GOOD_RUN.replace(
            escalation, escalation + '  note="first line\nfi\nelse"\n'),
        "nested if": GOOD_RUN.replace(
            escalation, '  if [ -n "${x:-}" ]; then\n    :\n  fi\n' + escalation),
        "comment quoting the tests": "# if grep -qx 'model:haiku' runs first\n"
                                     + GOOD_RUN,
    }
    for name, run in good.items():
        got = check(dict(base, **{WRAPPER: wrapper_doc(run)}))
        if got:
            print(f"self-test: {name} must pass: {got}", file=sys.stderr)
            ok = False
    # A workflow-level `defaults.run.shell: bash` (pipefail) is honoured.
    got = check(dict(base, **{WRAPPER: "defaults:\n  run:\n    shell: bash\n"
                                       + wrapper_doc(GOOD_RUN)}))
    if got:
        print(f"self-test: a bash defaults.run.shell must pass: {got}",
              file=sys.stderr)
        ok = False
    swapped = GOOD_RUN.replace("'model:opus'", "'model:TMP'") \
        .replace("'model:haiku'", "'model:opus'") \
        .replace("'model:TMP'", "'model:haiku'") \
        .replace('  tier="claude-opus-5-5"\n', "  TIER_OPUS\n") \
        .replace('  tier="claude-haiku-5-5"\n', '  tier="claude-opus-5-5"\n') \
        .replace("  TIER_OPUS\n", '  tier="claude-haiku-5-5"\n')
    bad = {
        "drifted stage default": dict(base, **{STAGE: GOOD_STAGE.replace(
            "180", "100")}),
        "no opt-in at all": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace("model:haiku", "model:zzz"))}),
        # The escalation spelled only as data -- the old token heuristic
        # read both as the Haiku branch setting it (review gate round 9).
        "escalation only inside a heredoc": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace(escalation, "  cat >/dev/null <<'EOF'\n"
                             + escalation + "EOF\n"))}),
        "escalation only inside a multi-line string": dict(base, **{
            WRAPPER: wrapper_doc(GOOD_RUN.replace(
                escalation, '  note="\n' + escalation + '"\n'))}),
        "branches swapped": dict(base, **{WRAPPER: wrapper_doc(swapped)}),
        "Haiku escalates to Opus": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace(escalation, '  escalation="claude-opus-5-5"\n'))}),
        "escalation only in a nested if never taken": dict(base, **{
            WRAPPER: wrapper_doc(GOOD_RUN.replace(
                escalation, '  if [ -n "${x:-}" ]; then\n' + "  " + escalation
                + "  fi\n"))}),
        "escalation applied to every tier": dict(base, **{
            WRAPPER: wrapper_doc(GOOD_RUN.replace(escalation, "").replace(
                "{\n  echo \"tier", 'escalation="claude-sonnet-5-5"\n{\n  echo "tier'))}),
        "non-Haiku budget drifted": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace("max_turns=180\nlabels", "max_turns=100\nlabels"))}),
        "bad Haiku budget not caught": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace("''|*[!0-9]*|0|0[0-9]*)", "''|0)"))}),
        "label failure aborts the step": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace(' || {\n  echo "::warning::could not read labels"\n'
                             "  labels=''\n}", ""))}),
        "label failure is silent": dict(base, **{WRAPPER: wrapper_doc(
            GOOD_RUN.replace('  echo "::warning::could not read labels"\n', ""))}),
        "job output unmapped": dict(base, **{WRAPPER: wrapper_doc(GOOD_RUN)
                                    .replace("steps.tier.outputs.escalation",
                                             "steps.tier.outputs.tier")}),
        "tier step under sh": dict(base, **{WRAPPER: wrapper_doc(GOOD_RUN)
                                    .replace("id: tier", "id: tier\n      shell: sh")}),
        "tier step in a container job with no shell": dict(base, **{
            WRAPPER: wrapper_doc(GOOD_RUN).replace(
                "  resolve-model:\n", "  resolve-model:\n    container: alpine\n")}),
        "malformed defaults": dict(base, **{WRAPPER: "defaults: bash\n"
                                            + wrapper_doc(GOOD_RUN)}),
        "stray reader": dict(base, **{OTHERS[1]: "model:opus model:haiku\n"}),
        "stray reader in pr-conversation": dict(base, **{OTHERS[2]: "model:haiku\n"}),
        "reader file missing": {k: v for k, v in base.items() if k != OTHERS[1]},
    }
    for name, texts in bad.items():
        if not check(texts):
            print(f"self-test: bad case {name!r} passed", file=sys.stderr)
            ok = False
    if not ok:
        return 1
    print(f"self-test ok ({len(good)} good shapes, {len(bad)} bad cases)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    root = Path(args.root)
    texts = {rel: (root / rel).read_text(encoding="utf-8")
             for rel in (WRAPPER, STAGE) + OTHERS if (root / rel).is_file()}
    failures = check(texts)
    for f in failures:
        print(f, file=sys.stderr)
    if failures:
        return 1
    print("model:haiku opt-in resolves as FR-014 says and is confined to the "
          "implement wrapper")
    return 0


if __name__ == "__main__":
    sys.exit(main())
