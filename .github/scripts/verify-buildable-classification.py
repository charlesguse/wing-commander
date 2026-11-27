#!/usr/bin/env python3
"""Gate 166 -- the buildable classification of tasks.md lines (specs/123).

Runs `.github/actions/_shared/count-tasks-checkboxes.sh` over every fixture
under `.github/scripts/fixtures/123-implement-task-completion/classification/`
(a `<name>.tasks.md` plus a `<name>.expected` of `key=value` lines, and an
optional `env:KEY=value` line) and fails on any mismatch. Also holds the
"single home" rule (FR-017): the write-boundary class of the counter must
come from classify-out-of-boundary-tasks.sh, never a second pattern list.
"""
import os
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COUNTER = os.path.join(ROOT, ".github", "actions", "_shared", "count-tasks-checkboxes.sh")
FIXTURES = os.path.join(
    ROOT, ".github", "scripts", "fixtures", "123-implement-task-completion"
)


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.email=g@example.invalid", "-c", "user.name=gate", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    )


def parse_outputs(text):
    """key=value lines; heredoc blocks collapse to their joined body."""
    out, lines, i = {}, text.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([a-z-]+)<<(\S+)$", line)
        if m:
            body = []
            i += 1
            while i < len(lines) and lines[i] != m.group(2):
                body.append(lines[i])
                i += 1
            out[m.group(1)] = "\n".join(body)
        elif "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
        i += 1
    return out


def run_counter(tasks_text, env_extra=None, rel="specs/999-x/tasks.md", spec_meta=None):
    """spec_meta, when given, is committed as spec-meta.json beside tasks.md:
    the counter reads its recorded gate_suite_ready when no env is passed."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as fh:
            fh.write(tasks_text)
        if spec_meta is not None:
            with open(os.path.join(os.path.dirname(path), "spec-meta.json"), "w") as fh:
                fh.write(spec_meta)
        git(tmp, "init", "-q")
        git(tmp, "add", "-A")
        git(tmp, "commit", "-q", "-m", "x")
        env = dict(os.environ)
        env.pop("GATE_SUITE_READY", None)
        env.update(env_extra or {})
        proc = subprocess.run(
            ["bash", COUNTER, "HEAD", rel], cwd=tmp, env=env,
            capture_output=True, text=True,
        )
    return proc


def check_classification(failures):
    d = os.path.join(FIXTURES, "classification")
    cases = sorted(f[: -len(".tasks.md")] for f in os.listdir(d) if f.endswith(".tasks.md"))
    if not cases:
        failures.append("no classification fixtures found")
    for name in cases:
        exp_path = os.path.join(d, name + ".expected")
        if not os.path.exists(exp_path):
            failures.append(f"{name}: missing .expected file")
            continue
        env, expected = {}, {}
        for line in open(exp_path).read().splitlines():
            if not line.strip():
                continue
            if line.startswith("env:"):
                k, v = line[4:].split("=", 1)
                env[k] = v
            else:
                k, v = line.split("=", 1)
                expected[k] = v
        meta = os.path.join(d, name + ".spec-meta.json")
        proc = run_counter(open(os.path.join(d, name + ".tasks.md")).read(), env,
                           spec_meta=open(meta).read() if os.path.exists(meta) else None)
        if proc.returncode != 0:
            failures.append(f"{name}: counter exited {proc.returncode}: {proc.stderr.strip()}")
            continue
        got = parse_outputs(proc.stdout)
        for k, v in expected.items():
            if got.get(k) != v:
                failures.append(f"{name}: {k} expected {v!r}, got {got.get(k)!r}")


DECIDE = os.path.join(ROOT, ".github", "actions", "_shared", "decide-implement-outcome.sh")


def check_cap_outcome(failures):
    """Each `<name>.env` is the stop rule's input; `<name>.expected` pins
    output keys (FR-006, FR-014, FR-015, FR-015a)."""
    d = os.path.join(FIXTURES, "cap-outcome")
    names = sorted(f[: -len(".env")] for f in os.listdir(d) if f.endswith(".env"))
    if not names:
        failures.append("no cap-outcome fixtures found")
    for name in names:
        exp = os.path.join(d, name + ".expected")
        if not os.path.exists(exp):
            failures.append(f"cap-outcome/{name}: missing .expected file")
            continue
        env = {"PATH": os.environ.get("PATH", "")}
        for line in open(os.path.join(d, name + ".env")).read().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
        proc = subprocess.run(["bash", DECIDE], env=env, capture_output=True, text=True)
        got = parse_outputs(proc.stdout)
        for line in open(exp).read().splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            if got.get(k) != v:
                failures.append(f"cap-outcome/{name}: {k} expected {v!r}, got {got.get(k)!r}")


def check_prompt(failures):
    """FR-001/FR-002: both implement prompts say a checkpoint is not a
    stopping point and keep the push-per-phase rule."""
    text = open(os.path.join(ROOT, ".github", "workflows", "implement.yml")).read()
    flat = re.sub(r"\s+", " ", text)
    for needle in ("a phase checkpoint is a place to push, not a stopping point",
                   "push after every phase"):
        if flat.count(needle) < 2:
            failures.append(f"implement.yml: both prompts must carry {needle!r}")


def decide_arm_failures(text, fixture="cycle-outcome-line"):
    """#889 (found by the code review of #1119): runs implement.yml's own
    inline decide command, in each read-back arm, against a cap-outcome
    fixture, and checks the line it picks back. Counting literals in the
    workflow passed any edit that kept them (a renamed shell variable, a
    dropped env assignment); running the shipped text does not."""
    d = os.path.join(FIXTURES, "cap-outcome")
    fx = {}
    for line in open(os.path.join(d, fixture + ".env")).read().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fx[k] = v
    exp = dict(l.split("=", 1) for l in open(os.path.join(d, fixture + ".expected")).read().splitlines() if "=" in l)
    lines = text.splitlines()
    arms = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith('decision="$(') and 'bash "$DECIDE_SCRIPT"' in line:
            # Start at the arm's own turns_used assignment just above, so the
            # step-env source of TURNS_USED is run too, not injected.
            start = i
            for k in range(i - 1, max(i - 4, -1), -1):
                if lines[k].lstrip().startswith("turns_used="):
                    start = k
                    break
            for j in range(i, min(i + 40, len(lines))):
                if lines[j].strip() == 'cycle_outcome="$(pick cycle-outcome)"':
                    arms.append("\n".join(l.strip() for l in lines[start:j + 1]))
                    break
    failures = []
    if len(arms) != 2:
        return [f"implement.yml: expected 2 read-back arms whose inline decide command is followed by "
                f"cycle_outcome=\"$(pick cycle-outcome)\", found {len(arms)}"]
    shell_vars = {"ok": fx.get("OK", ""), "truncated": fx.get("TRUNCATED", ""),
                  "converge_sha": fx.get("CONVERGE_SHA", "")}
    env = {"PATH": os.environ.get("PATH", ""), "DECIDE_SCRIPT": DECIDE,
           "INTENDED_TURNS": fx.get("TURN_BUDGET", ""), "TURNS_REPORTED": fx.get("TURNS_USED", "")}
    for k, v in fx.items():
        if k not in ("OK", "TRUNCATED", "TURNS_USED", "CONVERGE_SHA", "TURN_BUDGET"):
            env[k] = v
    for n, arm in enumerate(arms, 1):
        prelude = "".join(f"{k}={shlex.quote(v)}\n" for k, v in shell_vars.items())
        script = ("set -uo pipefail\n" + prelude + arm +
                  '\nprintf "cycle-outcome=%s\\nprogressed=%s\\nhandoff=%s\\n" '
                  '"$cycle_outcome" "$progressed" "$handoff"\n')
        proc = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
        got = parse_outputs(proc.stdout)
        for key in ("cycle-outcome", "progressed", "handoff"):
            if key in exp and got.get(key) != exp[key]:
                failures.append(f"implement.yml read-back arm {n}: the inline decide command gave "
                                f"{key}={got.get(key)!r}, expected {exp[key]!r} (cap-outcome/{fixture}) "
                                f"{proc.stderr.strip()[:200]}")
    return failures


def check_cycle_outcome_wiring(failures):
    """FR-003 / single home: implement.yml picks the cycle-outcome line from
    decide-implement-outcome.sh in both arms and never formats it itself."""
    text = open(os.path.join(ROOT, ".github", "workflows", "implement.yml")).read()
    failures.extend(decide_arm_failures(text))
    # The run must catch what the old literal counts caught and what they
    # missed: an env assignment glued to the next one, and a renamed shell
    # variable.
    for old, new, what in (
        ('TURN_BUDGET="${INTENDED_TURNS:-}" IMPL_CHECKED_BASE=',
         'TURN_BUDGET="${INTENDED_TURNS:-}"IMPL_CHECKED_BASE=', "a glued env assignment"),
        ('TURNS_USED="$turns_used"', 'TURNS_USED="$turns"', "a renamed turns variable"),
        ('turns_used="${TURNS_REPORTED:-}"', 'turns_used="${TURN_REPORTED:-}"',
         "a misspelt TURNS_REPORTED source"),
    ):
        if old not in text or not decide_arm_failures(text.replace(old, new)):
            failures.append(f"cycle-outcome wiring check does not catch {what}")
    if "CYCLE_OUTCOME" not in text:
        failures.append("implement.yml: the progress comment must carry CYCLE_OUTCOME")
    if re.search(r"buildable task\(s\)", text):
        failures.append("implement.yml: a copy of the cycle-outcome formatter "
                        "must live only in decide-implement-outcome.sh")
    src = open(DECIDE).read()
    if "buildable task(s)" not in src:
        failures.append("decide-implement-outcome.sh lost the cycle-outcome formatter")


def check_unreadable(failures):
    with tempfile.TemporaryDirectory() as tmp:
        git(tmp, "init", "-q")
        proc = subprocess.run(
            ["bash", COUNTER, "HEAD", "nope/tasks.md"], cwd=tmp,
            capture_output=True, text=True,
        )
    if proc.returncode == 0 or proc.stdout.strip():
        failures.append("unreadable ref:path must exit non-zero with empty stdout")


def check_single_home(failures):
    src = open(COUNTER).read()
    if "classify-out-of-boundary-tasks.sh" not in src:
        failures.append("counter does not call classify-out-of-boundary-tasks.sh")
    # No second pattern list for the write-boundary class: the only path
    # literals allowed are the NO_WRITE_PATHS default.
    stripped = re.sub(r'NO_WRITE_PATHS="\$\{NO_WRITE_PATHS:-[^}]*\}"', "", src)
    code = "\n".join(l for l in stripped.splitlines() if not l.lstrip().startswith("#"))
    if re.search(r"\.claude/|\.git/", code):
        failures.append("counter holds a second write-boundary pattern list")


def check_gate_ready_plumbing(failures):
    """FR-010 consistency: implement records its cycle's readiness in
    spec-meta, and no other caller overrides the counter's read of it."""
    wf = os.path.join(ROOT, ".github", "workflows")
    imp = open(os.path.join(wf, "implement.yml")).read()
    m = re.search(r"id: record-truncation-commit\n.*?(?=\n      - name:)", imp, re.S)
    step = m.group(0) if m else ""
    if "GATE_READY_NOW: ${{ needs.gate-suite-implement-cycle.outputs.ready" not in step \
            or '.gate_suite_ready = ($ready == "true")' not in step:
        failures.append("implement.yml record-truncation-commit must record the cycle's gate-suite readiness as gate_suite_ready")
    comp = open(os.path.join(ROOT, ".github", "actions", "wing-commander-tasks-checkbox-count", "action.yml")).read()
    m2 = re.search(r"  gate-suite-ready:\n(?:    .*\n)*?    default: (\S+)", comp)
    if not m2 or m2.group(1) != '""':
        failures.append("wing-commander-tasks-checkbox-count gate-suite-ready must default to \"\" "
                        "(a literal default would override the recorded readiness)")
    for name in ("finalize.yml", "lifecycle-review-gate.yml", "migrate-stranded-review-lifecycles.yml"):
        text = open(os.path.join(wf, name)).read()
        if re.search(r"gate-suite-ready:|GATE_SUITE_READY", text):
            failures.append(f"{name} must not pass gate-suite readiness: the counter reads the cycle's recorded value")
    src = open(COUNTER).read()
    if "gate_suite_ready" not in src:
        failures.append("count-tasks-checkboxes.sh must read the recorded gate_suite_ready when none is passed")


def check_fixture_readme(failures):
    """Every family the fixture README lists is a real, non-empty directory
    that the gate it names reads -- a row for fixtures nobody wrote reads as
    coverage that does not exist."""
    readme = open(os.path.join(FIXTURES, "README.md")).read()
    rows = re.findall(r"^\|[^|\n]*\|\s*`([^`/]+)/`\s*\|\s*`([^`]+\.py)`\s*\|\s*$", readme, re.M)
    if not rows:
        failures.append("fixture README lists no families")
    for dirname, gate in rows:
        d = os.path.join(FIXTURES, dirname)
        if not os.path.isdir(d) or not os.listdir(d):
            failures.append(f"fixture README lists {dirname}/ but no such fixture directory exists")
            continue
        gp = os.path.join(ROOT, ".github", "scripts", gate)
        if not os.path.exists(gp):
            failures.append(f"fixture README names {gate} for {dirname}/, which does not exist")
        elif f'"{dirname}"' not in open(gp).read():
            failures.append(f"fixture README says {gate} drives {dirname}/, but {gate} never reads it")
    for entry in sorted(os.listdir(FIXTURES)):
        if os.path.isdir(os.path.join(FIXTURES, entry)) and entry not in {r[0] for r in rows}:
            failures.append(f"fixture directory {entry}/ is missing from the fixture README")


def main():
    failures = []
    check_fixture_readme(failures)
    check_gate_ready_plumbing(failures)
    check_classification(failures)
    check_cap_outcome(failures)
    check_prompt(failures)
    check_cycle_outcome_wiring(failures)
    check_unreadable(failures)
    check_single_home(failures)
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("buildable classification: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
