#!/usr/bin/env python3
"""Gate 165 — implement stall hand-off and honest remaining-work reporting.

WHY THIS EXISTS
----------------
Spec 117 replaces "one zero-progress cycle ends implement" with a
deterministic stop rule, gives maintainer-only tasks a `[maintainer]` marker
every reader treats the same way, and has finalize render the remaining-work
report in code (Maintainer steps vs Unfinished implementation). Every rule
lives in a script under `.github/actions/_shared/`; this gate runs each
script against the checked-in fixtures under
`.github/scripts/fixtures/117-implement-stall-handoff/` -- one fixture per
branch -- and diffs the output against the `.expected` file beside it.

Usage: python3 .github/scripts/verify-implement-stall-handoff.py
Requires: bash, git, awk, jq.
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, ".github", "scripts", "fixtures",
                        "117-implement-stall-handoff")
SHARED = os.path.join(ROOT, ".github", "actions", "_shared")
COMPOSITE = os.path.join(ROOT, ".github", "actions",
                         "wing-commander-tasks-checkbox-count", "action.yml")

FAILURES = []
CASES = 0


def fail(msg):
    FAILURES.append(msg)
    print(f"::error::{msg}")


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def check_equal(name, actual, expected):
    global CASES
    CASES += 1
    if actual != expected:
        fail(f"{name}: output differs from expected\n--- expected\n{expected}"
             f"--- actual\n{actual}")


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8")


def git_repo_with(files):
    """A throwaway git repo committing {relpath: content}; returns its path."""
    repo = tempfile.mkdtemp(prefix="wc-117-")
    for args in (["init", "-q"], ["config", "user.email", "g@example.invalid"],
                 ["config", "user.name", "gate"]):
        run(["git"] + args, cwd=repo)
    for rel, content in files.items():
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
    run(["git", "add", "-A"], cwd=repo)
    proc = run(["git", "commit", "-q", "-m", "fixture"], cwd=repo)
    if proc.returncode != 0:
        sys.exit(f"::error::fixture commit failed: {proc.stderr}")
    return repo


def count_script(tasks_text):
    repo = git_repo_with({"tasks.md": tasks_text})
    proc = run(["bash", os.path.join(SHARED, "count-tasks-checkboxes.sh"),
                "HEAD", "tasks.md"], cwd=repo)
    return proc


def check_classification():
    for md in sorted(glob.glob(os.path.join(FIXTURES, "count-tasks-checkboxes-*.md"))):
        name = os.path.basename(md)
        proc = count_script(read(md))
        if proc.returncode != 0:
            fail(f"{name}: count-tasks-checkboxes.sh exited {proc.returncode}: {proc.stderr}")
            continue
        check_equal(name, proc.stdout, read(md[:-3] + ".expected"))
    # An unreadable ref:path still fails loudly with nothing on stdout.
    repo = git_repo_with({"tasks.md": "- [ ] T001 x\n"})
    proc = run(["bash", os.path.join(SHARED, "count-tasks-checkboxes.sh"),
                "HEAD", "missing.md"], cwd=repo)
    global CASES
    CASES += 1
    if proc.returncode == 0 or proc.stdout:
        fail("count-tasks-checkboxes.sh: unreadable path must exit non-zero with empty stdout")


def check_composite_outputs():
    text = read(COMPOSITE)
    for out in ("impl-checked-count", "impl-unchecked-count",
                "impl-unchecked-items", "maintainer-items", "standing-count"):
        global CASES
        CASES += 1
        if not re.search(rf"^  {re.escape(out)}:\n(?:    .*\n)*?    value: \$\{{\{{ steps\.read\.outputs\.{re.escape(out)} \}}\}}",
                         text, re.M):
            fail(f"wing-commander-tasks-checkbox-count does not expose output '{out}'")


def render(maint_text, impl_text, routed_text=None):
    tmp = tempfile.mkdtemp(prefix="wc-117-render-")
    paths = []
    for name, text in (("maint", maint_text), ("impl", impl_text),
                       ("routed", routed_text)):
        if text is None:
            continue
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        paths.append(path)
    return run(["bash", os.path.join(SHARED, "render-remaining-work.sh")] + paths)


def check_render():
    for exp in sorted(glob.glob(os.path.join(FIXTURES, "render-remaining-work-*.expected"))):
        base = exp[:-len(".expected")]
        routed = base + ".routed"
        proc = render(read(base + ".maintainer"), read(base + ".impl"),
                      read(routed) if os.path.exists(routed) else None)
        name = os.path.basename(base)
        if proc.returncode != 0:
            fail(f"{name}: render-remaining-work.sh exited {proc.returncode}: {proc.stderr}")
            continue
        check_equal(name, proc.stdout, read(exp))
    # Replays of the real-world shapes: tasks.md -> classify -> render.
    for exp in sorted(glob.glob(os.path.join(FIXTURES, "pipeline-*.expected"))):
        base = exp[:-len(".expected")]
        proc = count_script(read(base + ".md"))
        if proc.returncode != 0:
            fail(f"{os.path.basename(base)}: classification failed: {proc.stderr}")
            continue
        lists = {}
        for key, delim in (("maintainer-items", "WING_COMMANDER_MAINTAINER_ITEMS_EOF"),
                           ("impl-unchecked-items", "WING_COMMANDER_IMPL_ITEMS_EOF")):
            m = re.search(rf"^{key}<<{delim}\n(.*?)^{delim}\n", proc.stdout, re.M | re.S)
            lists[key] = m.group(1) if m else ""
        out = render(lists["maintainer-items"], lists["impl-unchecked-items"])
        check_equal(os.path.basename(base), out.stdout, read(exp))


def check_finalize_wiring():
    global CASES
    text = read(os.path.join(ROOT, ".github", "workflows", "finalize.yml"))
    CASES += 1
    if "wing-commander-remaining-work" not in text:
        fail("finalize.yml does not render the remaining work through wing-commander-remaining-work")
    CASES += 1
    if "every tasks.md item that is still unchecked" in text:
        fail("finalize.yml still instructs the agent to copy unchecked task lines")
    action = read(os.path.join(ROOT, ".github", "actions",
                               "wing-commander-remaining-work", "action.yml"))
    CASES += 1
    if "_shared/render-remaining-work.sh" not in action:
        fail("wing-commander-remaining-work does not call _shared/render-remaining-work.sh")


MAINTAINER_KINDS = (
    "real workflow dispatch or run re-drive",
    "reading or\n            changing repository variables or settings",
    "opening or merging a\n            separate human-merged PR",
    "post-merge proof",
    "constitution\n            amendment merge",
)


def check_prompts():
    global CASES
    tasks = read(os.path.join(ROOT, ".github", "workflows", "tasks.yml"))
    for needle in ("`[maintainer]`", '"Maintainer\n            follow-up" phase'):
        CASES += 1
        if tasks.count(needle) < 2:
            fail(f"tasks.yml: both prompts must carry {needle!r}")
    for kind in MAINTAINER_KINDS:
        CASES += 1
        if tasks.count(kind) < 2:
            fail(f"tasks.yml: both prompts must list the maintainer kind {kind!r}")
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    CASES += 1
    if impl.count("Tasks marked `[maintainer]` are for the repository owner: skip") < 2:
        fail("implement.yml: both prompts must carry the [maintainer] skip rule")
    # A tasks.md whose only unchecked lines are maintainer-tagged has nothing
    # left for the loop (SC-003, loop side).
    proc = count_script(read(os.path.join(FIXTURES,
                                          "count-tasks-checkboxes-maintainer-only.md")))
    CASES += 1
    if "impl-unchecked-count=0\n" not in proc.stdout:
        fail("maintainer-only tasks.md must yield impl-unchecked-count=0")


def parse_kv(text):
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def check_blocker():
    import json
    tasks = read(os.path.join(FIXTURES, "validate-implement-blocker.tasks.md"))
    cases = json.loads(read(os.path.join(FIXTURES, "validate-implement-blocker-cases.json")))
    repo = git_repo_with({"tasks.md": tasks})
    for case in cases:
        name = f"validate-implement-blocker/{case['name']}"
        path = os.path.join(repo, "..", f"blocker-{case['name']}.json")
        path = os.path.abspath(path)
        if os.path.exists(path):
            os.remove(path)
        if case["blocker"] is not None:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(case["blocker"].replace("@X301@", "x" * 301))
        proc = run(["bash", os.path.join(SHARED, "validate-implement-blocker.sh"),
                    path, "HEAD", "tasks.md"], cwd=repo)
        global CASES
        CASES += 1
        if proc.returncode != 0:
            fail(f"{name}: exited {proc.returncode}: {proc.stderr}")
            continue
        got = parse_kv(proc.stdout)
        if (got.get("blocker-valid") == "true") != case["valid"]:
            fail(f"{name}: blocker-valid={got.get('blocker-valid')}, expected {case['valid']}")
        elif case["valid"] and got.get("blocker-text") != case["text"]:
            fail(f"{name}: blocker-text={got.get('blocker-text')!r}, expected {case['text']!r}")
        elif not case["valid"] and case["reason"] not in got.get("blocker-invalid-reason", ""):
            fail(f"{name}: reason {got.get('blocker-invalid-reason')!r} lacks {case['reason']!r}")
    # tasks.md unreadable at the ref is the one non-zero exit.
    CASES += 1
    proc = run(["bash", os.path.join(SHARED, "validate-implement-blocker.sh"),
                os.path.join(repo, "none.json"), "HEAD", "absent.md"], cwd=repo)
    if proc.returncode == 0:
        fail("validate-implement-blocker.sh: unreadable tasks.md must exit non-zero")


def check_decide():
    import json
    cases = json.loads(read(os.path.join(FIXTURES, "decide-implement-outcome-cases.json")))
    for case in cases:
        env = {"PATH": os.environ.get("PATH", "")}
        env.update(case["env"])
        proc = run(["bash", os.path.join(SHARED, "decide-implement-outcome.sh")], env=env)
        global CASES
        CASES += 1
        name = f"decide-implement-outcome/{case['name']}"
        if proc.returncode != 0:
            fail(f"{name}: exited {proc.returncode}: {proc.stderr}")
            continue
        got = parse_kv(proc.stdout)
        for key, want in case["expect"].items():
            if got.get(key) != want:
                fail(f"{name}: {key}={got.get(key)!r}, expected {want!r}")


def check_implement_wiring():
    global CASES
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    for needle in ("wing-commander-implement-outcome", "decide-script"):
        CASES += 1
        if impl.count(needle) < 2:
            fail(f"implement.yml: both read-back arms must use {needle}")
    CASES += 1
    if "the cycle checked nothing new, so the loop is ending here" in impl:
        fail("implement.yml still carries the inline zero-progress hand-off rule")


def main():
    check_blocker()
    check_decide()
    check_classification()
    check_composite_outputs()
    check_render()
    check_finalize_wiring()
    check_prompts()
    check_implement_wiring()
    if FAILURES:
        print(f"verify-implement-stall-handoff: {len(FAILURES)} failure(s) in {CASES} case(s)")
        return 1
    print(f"verify-implement-stall-handoff: {CASES} case(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
