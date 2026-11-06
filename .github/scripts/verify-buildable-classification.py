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


def run_counter(tasks_text, env_extra=None, rel="specs/999-x/tasks.md"):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as fh:
            fh.write(tasks_text)
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
        proc = run_counter(open(os.path.join(d, name + ".tasks.md")).read(), env)
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


def check_cycle_outcome_wiring(failures):
    """FR-003 / single home: implement.yml picks the cycle-outcome line from
    decide-implement-outcome.sh in both arms and never formats it itself."""
    text = open(os.path.join(ROOT, ".github", "workflows", "implement.yml")).read()
    if text.count('cycle_outcome="$(pick cycle-outcome)"') < 2:
        failures.append("implement.yml: both read-back arms must pick cycle-outcome")
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


def main():
    failures = []
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
