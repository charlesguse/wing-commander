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
import atexit
import glob
import json
import os
import re
import shutil
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


_TMPDIRS = []


def _tmpdir(prefix):
    """A temp dir removed when the gate exits, pass or fail."""
    path = tempfile.mkdtemp(prefix=prefix)
    _TMPDIRS.append(path)
    return path


atexit.register(lambda: [shutil.rmtree(p, ignore_errors=True) for p in _TMPDIRS])


def git_repo_with(files):
    """A throwaway git repo committing {relpath: content}; returns its path."""
    repo = _tmpdir("wc-117-")
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
                "impl-unchecked-items", "maintainer-items", "standing-count",
                "impl-ids", "impl-unchecked-ids"):
        global CASES
        CASES += 1
        if not re.search(rf"^  {re.escape(out)}:\n(?:    .*\n)*?    value: \$\{{\{{ steps\.read\.outputs\.{re.escape(out)} \}}\}}",
                         text, re.M):
            fail(f"wing-commander-tasks-checkbox-count does not expose output '{out}'")


def render(maint_text, impl_text, routed_text=None):
    tmp = _tmpdir("wc-117-render-")
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
    # FR-007: the report is rendered after the summarising agent has run,
    # so an agent-written finalize-remaining.md can never be the report.
    import yaml
    doc = yaml.safe_load(text)
    names = [st.get("name") for st in doc["jobs"]["finalize"]["steps"]]
    CASES += 1
    try:
        if names.index("Render remaining work") < names.index(
                "Summarize change and extract remaining manual work"):
            fail("finalize.yml renders the remaining work before the summarising agent "
                 "runs, so the agent can overwrite finalize-remaining.md")
    except ValueError as exc:
        fail(f"finalize.yml: step not found ({exc})")
    action = read(os.path.join(ROOT, ".github", "actions",
                               "wing-commander-remaining-work", "action.yml"))
    CASES += 1
    if "_shared/render-remaining-work.sh" not in action:
        fail("wing-commander-remaining-work does not call _shared/render-remaining-work.sh")


def run_remaining_work_composite(renderer, impl_text):
    """Run wing-commander-remaining-work's run: block with `renderer` as its
    _shared/render-remaining-work.sh; return (proc, outputs, report-or-None)."""
    import yaml
    action = yaml.safe_load(read(os.path.join(
        ROOT, ".github", "actions", "wing-commander-remaining-work", "action.yml")))
    script = next(st["run"] for st in action["runs"]["steps"] if st.get("id") == "render")
    tmp = _tmpdir("wc-117-composite-")
    os.makedirs(os.path.join(tmp, "_shared"))
    os.makedirs(os.path.join(tmp, "action"))
    shutil.copy(renderer, os.path.join(tmp, "_shared", "render-remaining-work.sh"))
    out_file = os.path.join(tmp, "github-output")
    report = os.path.join(tmp, "finalize-remaining.md")
    env = {**os.environ, "GITHUB_ACTION_PATH": os.path.join(tmp, "action"),
           "RUNNER_TEMP": tmp, "GITHUB_OUTPUT": out_file,
           "MAINTAINER_ITEMS": "", "IMPL_ITEMS": impl_text, "ROUTED_ITEMS": "",
           "OUTPUT_PATH": report}
    proc = run(["bash", "-c", script], env=env)
    outputs = dict(line.split("=", 1) for line in
                   (read(out_file).splitlines() if os.path.exists(out_file) else []))
    return proc, outputs, (read(report) if os.path.exists(report) else None)


def check_remaining_work_composite():
    """A renderer failure must not leave a report that reads as "no manual
    work remains": the composite removes it (so finalize's "Verify agent
    output" fails on the absent file) and still exits 0 so that step runs."""
    global CASES
    impl = "- [ ] T002 Unchecked code\n"
    proc, outputs, report = run_remaining_work_composite(
        os.path.join(SHARED, "render-remaining-work.sh"), impl)
    for what, ok in (("exits 0", proc.returncode == 0),
                     ("writes the report", report is not None and "## Unfinished implementation" in report),
                     ("impl-count=1", outputs.get("impl-count") == "1"),
                     ("stalled=true", outputs.get("stalled") == "true")):
        CASES += 1
        if not ok:
            fail(f"wing-commander-remaining-work (renderer ok): expected it {what}; "
                 f"rc={proc.returncode} outputs={outputs} stderr={proc.stderr}")
    stub = os.path.join(_tmpdir("wc-117-stub-"), "render.sh")
    with open(stub, "w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\nexit 3\n")
    proc, outputs, report = run_remaining_work_composite(stub, impl)
    for what, ok in (("exits 0 (keeps Verify agent output reachable)", proc.returncode == 0),
                     ("leaves no report file", report is None),
                     ("does not claim stalled=false", outputs.get("stalled") != "false"),
                     ("reports has-remaining=unknown, never false", outputs.get("has-remaining") == "unknown")):
        CASES += 1
        if not ok:
            fail(f"wing-commander-remaining-work (renderer fails): expected it {what}; "
                 f"rc={proc.returncode} outputs={outputs} report={report!r}")


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


def _paragraphs(text, start, end):
    """Every prompt paragraph from a line starting `start` to the line ending
    `end`, with indentation stripped (the arms differ only in indent)."""
    pat = rf"^[ \t]*{re.escape(start)}.*?{re.escape(end)}$"
    return [re.sub(r"\n[ \t]+", "\n", m.group(0).strip())
            for m in re.finditer(pat, text, re.M | re.S)]


def prompt_parity_failures(impl, tasks, kinds):
    """The [maintainer]/blocker prose is necessarily repeated in each agent
    prompt (a prompt cannot point at another), so the copies are held
    byte-identical here and the blocker kinds are held to the validator's
    closed list -- the drift CLAUDE.md's single-home rule guards against."""
    out = []
    for name, text, start, end in (
            ("implement.yml blocker paragraph", impl,
             "Tasks marked `[maintainer]` are for the repository owner", "the next cycle runs."),
            ("tasks.yml maintainer paragraph", tasks,
             "Maintainer tasks: a task only the repository owner", "guidance in prose.")):
        paras = _paragraphs(text, start, end)
        if len(paras) != 2:
            out.append(f"{name}: expected one copy in each of the 2 prompts, found {len(paras)}")
        elif paras[0] != paras[1]:
            out.append(f"{name}: the two prompt copies differ")
        if name.startswith("implement") and paras:
            for kind in kinds:
                if kind not in paras[0]:
                    out.append(f"{name}: does not list blocker kind {kind!r} the validator accepts")
    return out


def check_prompt_parity():
    global CASES
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    tasks = read(os.path.join(ROOT, ".github", "workflows", "tasks.yml"))
    validator = read(os.path.join(SHARED, "validate-implement-blocker.sh"))
    m = re.search(r"^  ([a-z-]+(?:\|[a-z-]+)+)\) ;;$", validator, re.M)
    kinds = m.group(1).split("|") if m else []
    CASES += 1
    if not kinds:
        fail("validate-implement-blocker.sh: could not read its closed kind list")
    CASES += 1
    for msg in prompt_parity_failures(impl, tasks, kinds):
        fail(msg)
    # The check must catch a drifted copy (self-test on mutated text).
    first = impl.index("missing-tool, missing-permission")
    drifted = impl[:first] + impl[first:].replace("missing-tool, missing-permission", "missing-tool, missing-secret", 1)
    CASES += 1
    if not prompt_parity_failures(drifted, tasks, kinds):
        fail("prompt parity check did not catch a drifted blocker paragraph")


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
        path = os.path.join(repo, f"blocker-{case['name']}.json")
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


def check_task_identity():
    """Owner decision A on #992: an id that was unchecked implementation work
    at the cycle base and is retagged [maintainer], reworded as a standing
    instruction or deleted at the tip stays outstanding. Both refs go through
    the shipped count script, then the shipped stop rule."""
    global CASES
    base = ("- [x] T001 Done in `a.sh`\n- [ ] T002 Write `b.sh`\n"
            "- [ ] T003 Write `c.sh`\n- [ ] T004 Write `d.sh`\n- [ ] T005 Write `e.sh`\n")
    tip = ("- [x] T001 Done in `a.sh`\n- [ ] T002 [maintainer] Write `b.sh`\n"
           "- [ ] T003 Keep the gates green\n- [x] T005 Write `e.sh`\n- [ ] T009 [maintainer] Re-drive a run\n")
    repo = git_repo_with({"tasks.md": base})
    with open(os.path.join(repo, "tasks.md"), "w", encoding="utf-8") as fh:
        fh.write(tip)
    run(["git", "commit", "-qam", "tip"], cwd=repo)
    counts = {}
    for ref in ("HEAD~1", "HEAD"):
        proc = run(["bash", os.path.join(SHARED, "count-tasks-checkboxes.sh"), ref, "tasks.md"], cwd=repo)
        counts[ref] = parse_kv(proc.stdout)
    env = {"PATH": os.environ.get("PATH", ""), "OK": "true", "TRUNCATED": "false",
           "IMPL_CHECKED_BASE": counts["HEAD~1"].get("impl-checked-count", ""),
           "IMPL_CHECKED_TIP": counts["HEAD"].get("impl-checked-count", ""),
           "IMPL_UNCHECKED_TIP": counts["HEAD"].get("impl-unchecked-count", ""),
           "IMPL_UNCHECKED_IDS_BASE": counts["HEAD~1"].get("impl-unchecked-ids", ""),
           "IMPL_IDS_TIP": counts["HEAD"].get("impl-ids", ""),
           "ITERATION": "5", "MAX_ITERATIONS": "5"}
    got = parse_kv(run(["bash", os.path.join(SHARED, "decide-implement-outcome.sh")], env=env).stdout)
    CASES += 1
    if got.get("converged") != "false" or got.get("dropped-ids") != "T002 T003 T004":
        fail(f"task identity: retagged/reworded/deleted ids must stay outstanding; "
             f"converged={got.get('converged')!r} dropped-ids={got.get('dropped-ids')!r}")
    CASES += 1
    if "T002, T003, T004" not in got.get("stall-comment", ""):
        fail(f"task identity: the stall comment must name the ids; got {got.get('stall-comment')!r}")
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    for needle in ("IMPL_UNCHECKED_IDS_BASE: ${{ steps.checkbox-base-cycle.outputs.impl-unchecked-ids }}",
                   "IMPL_IDS_TIP: ${{ steps.checkbox-tip-cycle.outputs.impl-ids }}",
                   "IMPL_UNCHECKED_IDS_BASE: ${{ steps.checkbox-base-retry.outputs.impl-unchecked-ids }}",
                   "IMPL_IDS_TIP: ${{ steps.checkbox-tip-retry.outputs.impl-ids }}"):
        CASES += 1
        if needle not in impl:
            fail(f"implement.yml: a read-back arm does not pass {needle!r} to the stop rule")


def _workflow_step(name):
    import yaml
    doc = yaml.safe_load(read(os.path.join(ROOT, ".github", "workflows", "implement.yml")))
    return next(st for job in doc["jobs"].values()
                for st in job.get("steps", []) if st.get("name") == name)


def _run_block(script, cwd, env_over):
    """Run a run: block with a fresh GITHUB_OUTPUT; return (proc, outputs)."""
    tmp = _tmpdir("wc-117-step-")
    out_file = os.path.join(tmp, "github-output")
    env = {**os.environ, "GITHUB_OUTPUT": out_file, "RUNNER_TEMP": tmp,
           "GITHUB_STEP_SUMMARY": os.path.join(tmp, "summary"), **env_over}
    proc = run(["bash", "-e", "-c", script], cwd=cwd, env=env)
    return proc, parse_kv(read(out_file) if os.path.exists(out_file) else "")


def check_task_identity_across_cycles():
    """Owner decision C on #992: a retag in cycle 1 must not let cycle 2
    converge. Cycle 1's dropped-ids go through the shipped "Record
    truncated-cycle count" step into spec-meta.json's dropped_task_ids;
    cycle 2's shipped wing-commander-implement-outcome reads them at its
    base and the shipped stop rule keeps them outstanding. A maintainer
    removing the id from dropped_task_ids, or the id coming back as
    implementation work, releases it."""
    global CASES
    import yaml
    spec_dir, slug, prefix = "specs/117-x", "117-x", "spec/"
    tasks = f"{spec_dir}/tasks.md"
    meta = f"{spec_dir}/spec-meta.json"
    repo = git_repo_with({
        tasks: "- [x] T001 Done in `a.sh`\n- [ ] T002 Write `b.sh`\n- [ ] T003 Write `c.sh`\n",
        meta: json.dumps({"stage": "implement", "iteration": 1}) + "\n"})
    origin = _tmpdir("wc-117-origin-")
    run(["git", "init", "-q", "--bare", origin])
    for args in (["branch", "-M", prefix + slug], ["remote", "add", "origin", origin],
                 ["push", "-q", "origin", prefix + slug]):
        run(["git"] + args, cwd=repo)

    def commit(files, msg):
        for rel, content in files.items():
            with open(os.path.join(repo, rel), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
        run(["git", "commit", "-qam", msg], cwd=repo)
        run(["git", "push", "-q", "origin", prefix + slug], cwd=repo)
        return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

    action = yaml.safe_load(read(os.path.join(
        ROOT, ".github", "actions", "wing-commander-implement-outcome", "action.yml")))
    outcome_script = next(st["run"] for st in action["runs"]["steps"] if st.get("id") == "validate")
    record_script = _workflow_step("Record truncated-cycle count")["run"]

    def cycle(base, tip, iteration="2"):
        _, comp = _run_block(outcome_script, repo, {
            "GITHUB_ACTION_PATH": os.path.join(ROOT, ".github", "actions",
                                               "wing-commander-implement-outcome"),
            "BLOCKER_PATH": os.path.join(_tmpdir("wc-117-b-"), "none.json"),
            "REF": tip, "TASKS_PATH": tasks, "META_REF": base})
        counts = {}
        for ref in (base, tip):
            proc = run(["bash", os.path.join(SHARED, "count-tasks-checkboxes.sh"), ref, tasks], cwd=repo)
            counts[ref] = parse_kv(proc.stdout)
        env = {"PATH": os.environ.get("PATH", ""), "OK": "true", "TRUNCATED": "false",
               "IMPL_CHECKED_BASE": counts[base].get("impl-checked-count", ""),
               "IMPL_CHECKED_TIP": counts[tip].get("impl-checked-count", ""),
               "IMPL_UNCHECKED_TIP": counts[tip].get("impl-unchecked-count", ""),
               "IMPL_UNCHECKED_IDS_BASE": counts[base].get("impl-unchecked-ids", ""),
               "IMPL_IDS_TIP": counts[tip].get("impl-ids", ""),
               "CARRIED_DROPPED_IDS": comp.get("carried-dropped-ids", ""),
               "ITERATION": iteration, "MAX_ITERATIONS": "5"}
        got = parse_kv(run(["bash", comp.get("decide-script") or os.path.join(
            SHARED, "decide-implement-outcome.sh")], env=env).stdout)
        proc, rec = _run_block(record_script, repo, {
            "SLUG": slug, "SPEC_DIR": spec_dir, "SPEC_PREFIX": prefix,
            "TRUNCATED": "false", "TIER": "", "BOT_SLUG": "gate",
            "DROPPED_IDS": got.get("dropped-ids", ""), "DROPPED_KNOWN": "true"})
        if rec.get("push") == "true":
            run(["git", "push", "-q", "origin", "HEAD:" + prefix + slug], cwd=repo)
        recorded = json.loads(read(os.path.join(repo, meta))).get("dropped_task_ids")
        head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        return got, recorded, head, proc

    def meta_with(**fields):
        m = json.loads(read(os.path.join(repo, meta)))
        m.update(fields)
        return {meta: json.dumps({k: v for k, v in m.items() if v is not None}) + "\n"}

    retagged = ("- [x] T001 Done in `a.sh`\n- [ ] T002 [maintainer] Write `b.sh`\n"
                "- [x] T003 Write `c.sh`\n")
    c0 = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    c1 = commit({tasks: retagged}, "cycle 1: retag T002")
    got, recorded, c2, proc = cycle(c0, c1)
    CASES += 1
    if got.get("converged") != "false" or recorded != ["T002"]:
        fail(f"across cycles: cycle 1's retag must be persisted; converged={got.get('converged')!r} "
             f"dropped_task_ids={recorded!r} stderr={proc.stderr}")
    c3 = commit(meta_with(iteration=5), "cycle 2: nothing new")
    got, recorded, _, _ = cycle(c2, c3, iteration="5")
    CASES += 1
    if got.get("converged") != "false" or got.get("dropped-ids") != "T002" or recorded != ["T002"]:
        fail(f"across cycles: a retag in cycle 1 let cycle 2 converge; converged={got.get('converged')!r} "
             f"dropped-ids={got.get('dropped-ids')!r} dropped_task_ids={recorded!r}")
    CASES += 1
    if "T002" not in got.get("stall-comment", "") or "dropped_task_ids" not in got.get("stall-comment", ""):
        fail(f"across cycles: the cap's stall comment must name the carried id and how to "
             f"accept it; got {got.get('stall-comment')!r}")
    # A maintainer accepting the retag removes the id from dropped_task_ids.
    c5 = commit(meta_with(dropped_task_ids=None), "maintainer: accept the T002 retag")
    got, recorded, _, _ = cycle(c5, c5)
    CASES += 1
    if got.get("converged") != "true" or recorded is not None:
        fail(f"across cycles: a maintainer removing the id from dropped_task_ids must release it; "
             f"converged={got.get('converged')!r} dropped_task_ids={recorded!r}")
    # An id back as implementation work leaves the set.
    c7 = commit(meta_with(dropped_task_ids=["T002"]), "carry T002 again")
    c8 = commit({tasks: "- [x] T001 Done in `a.sh`\n- [x] T002 Write `b.sh`\n- [x] T003 Write `c.sh`\n"},
                "cycle 3: T002 done")
    got, recorded, _, _ = cycle(c7, c8)
    CASES += 1
    if got.get("converged") != "true" or recorded is not None:
        fail(f"across cycles: an id back as implementation work must leave the set; "
             f"converged={got.get('converged')!r} dropped_task_ids={recorded!r}")
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    for needle in ("CARRIED_DROPPED_IDS: ${{ steps.blocker-cycle.outputs.carried-dropped-ids }}\n",
                   "CARRIED_DROPPED_IDS: ${{ steps.blocker-retry.outputs.carried-dropped-ids }} "
                   "${{ steps.outcome.outputs.dropped-ids }}\n",
                   "PRIMARY_DROPPED_IDS: ${{ steps.outcome.outputs.dropped-ids }}",
                   "RETRY_DROPPED_IDS: ${{ steps.retry-outcome.outputs.dropped-ids }}",
                   "DROPPED_IDS: ${{ steps.final.outputs.dropped-ids }}",
                   "DROPPED_KNOWN: ${{ steps.final.outputs.dropped-known }}"):
        CASES += 1
        if needle not in impl:
            fail(f"implement.yml: the dropped-id carry is not wired: missing {needle!r}")
    doc = yaml.safe_load(impl)
    steps = {st.get("id"): st for job in doc["jobs"].values() for st in job.get("steps", [])}
    for sid in ("blocker-cycle", "blocker-retry"):
        CASES += 1
        if ((steps.get(sid) or {}).get("with") or {}).get("meta-ref") != "${{ steps.base.outputs.base-sha }}":
            fail(f"implement.yml: {sid} must read dropped_task_ids at the cycle base")
    for sid in ("outcome", "retry-outcome"):
        CASES += 1
        body = (steps.get(sid) or {}).get("run", "")
        if 'echo "dropped-ids=$dropped_ids"' not in body or 'echo "dropped-known=$dropped_known"' not in body:
            fail(f"implement.yml: {sid} must output dropped-ids and dropped-known")


def check_write_boundary_input():
    """The write-boundary classifier must see implementation tasks only: an
    unchecked [maintainer] or standing line names no out-of-boundary path,
    so on the raw list it keeps all-unchecked-out-of-boundary false and a
    lifecycle whose only implementation work is out of reach grinds to the
    cap instead of routing. Both arms' wiring, then the shipped classifier
    on the shipped count's output."""
    global CASES
    import yaml
    doc = yaml.safe_load(read(os.path.join(ROOT, ".github", "workflows", "implement.yml")))
    steps = {st.get("id"): st for job in doc["jobs"].values() for st in job.get("steps", [])}
    for arm in ("cycle", "retry"):
        got = ((steps.get(f"write-boundary-{arm}") or {}).get("with") or {}).get("unchecked-items")
        CASES += 1
        if got != f"${{{{ steps.checkbox-tip-{arm}.outputs.impl-unchecked-items }}}}":
            fail(f"implement.yml: write-boundary-{arm} classifies {got!r}, not the tip's "
                 "implementation-only impl-unchecked-items")
    proc = count_script("- [ ] T001 Edit `.claude/settings.json`\n"
                        "- [ ] T002 [maintainer] Merge the PR\n- [ ] Keep the gates green\n")
    m = re.search(r"^impl-unchecked-items<<(\S+)\n(.*?)^\1$", proc.stdout, re.M | re.S)
    items = m.group(2) if m else ""
    res = run(["bash", os.path.join(SHARED, "classify-out-of-boundary-tasks.sh"),
               items, ".claude/", "specs/117-x/tasks.md", "specs/117-x"], cwd=ROOT)
    CASES += 1
    if "all-unchecked-out-of-boundary=true" not in res.stdout:
        fail(f"write boundary: only out-of-reach implementation work must route; "
             f"items={items!r} stdout={res.stdout!r} stderr={res.stderr}")


def check_implement_wiring():
    global CASES
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    for needle in ("wing-commander-implement-outcome", "decide-script"):
        CASES += 1
        if impl.count(needle) < 2:
            fail(f"implement.yml: both read-back arms must use {needle}")
    # FR-003: the truncated-cycle progress test (Arm A) counts
    # implementation tasks only, in both arms.
    CASES += 1
    if (impl.count('"${IMPL_CHECKED_TIP:-0}" -gt "${IMPL_CHECKED_BASE:-0}"') < 2
            or '"${CHECKED_TIP:-0}" -gt "${CHECKED_BASE:-0}"' in impl):
        fail("implement.yml: Arm A must compare implementation checked counts in both arms")
    CASES += 1
    if "the cycle checked nothing new, so the loop is ending here" in impl:
        fail("implement.yml still carries the inline zero-progress hand-off rule")


def run_dispatch_step(env_over):
    """Run implement.yml's shipped "Dispatch next step" body with a logging
    `gh` stub; return (proc, gh-calls, step-summary)."""
    import yaml
    doc = yaml.safe_load(read(os.path.join(ROOT, ".github", "workflows", "implement.yml")))
    script = next(st["run"] for job in doc["jobs"].values()
                  for st in job.get("steps", []) if st.get("name") == "Dispatch next step")
    tmp = _tmpdir("wc-117-dispatch-")
    calls = os.path.join(tmp, "calls")
    summary = os.path.join(tmp, "summary")
    with open(os.path.join(tmp, "gh"), "w", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$GH_CALLS"\n')
    os.chmod(os.path.join(tmp, "gh"), 0o755)
    env = {**os.environ, "PATH": tmp + os.pathsep + os.environ["PATH"],
           "GH_CALLS": calls, "GITHUB_STEP_SUMMARY": summary,
           "APP_TOKEN": "a", "DISPATCH_TOKEN": "d", "SPEC_DIR": "specs/117-x",
           "ISSUE": "1", "ITERATION": "5", "MAX": "5", "CONVERGED": "false",
           "TRUNCATED": "false", "TRUNCATED_COUNT": "1", "HANDOFF": "false",
           "ROUTED": "false", "REASON": "", "STALL_COMMENT": "", "TIER": "t",
           "REMAINING": "- [ ] T002 x", "SELF_WORKFLOW": "self.yml",
           "NEXT_WORKFLOW": "next.yml", "COST_LINE": "",
           "GITHUB_SERVER_URL": "https://github.example",
           "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "1"}
    env.update(env_over)
    proc = run(["bash", "-e", "-c", script], env=env)
    return (proc, read(calls) if os.path.exists(calls) else "",
            read(summary) if os.path.exists(summary) else "")


def check_dispatch_stall_reporting():
    """FR-006 on the dispatch step's terminal branches: a routed hand-off at
    the cap keeps its write-boundary reason AND the stall comment; a
    truncated cycle at the cap still names the count; a blocker hand-off's
    step summary does not blame the iteration cap."""
    global CASES
    stall = "Implement stopped with 1 implementation task(s) still unchecked: the iteration cap (5) was reached."
    wb = "the only remaining work is outside the implement stage's write boundary: T002"
    cases = (
        ("routed at the cap", {"HANDOFF": "true", "ROUTED": "true", "REASON": wb,
                               "STALL_COMMENT": stall}, (wb, stall)),
        ("truncated at the cap", {"TRUNCATED": "true", "STALL_COMMENT": stall}, (stall,)),
    )
    for name, over, want in cases:
        proc, calls, _ = run_dispatch_step(over)
        for needle in want:
            CASES += 1
            if proc.returncode != 0 or needle not in calls:
                fail(f"dispatch step ({name}): the issue comment lacks {needle!r}; "
                     f"rc={proc.returncode} calls={calls!r} stderr={proc.stderr}")
    blocker = "Implement stopped with 2 implementation task(s) still unchecked: the agent reported a blocker: missing-tool: no jq (T007)."
    proc, calls, summary = run_dispatch_step({"ITERATION": "1", "HANDOFF": "true",
                                              "STALL_COMMENT": blocker})
    CASES += 1
    if proc.returncode != 0 or "iteration cap" in summary or blocker not in summary:
        fail(f"dispatch step (blocker hand-off at cycle 1 of 5): the step summary must "
             f"quote the stop reason, not the iteration cap; summary={summary!r}")


def check_review_stage_comment():
    global CASES
    impl = read(os.path.join(ROOT, ".github", "workflows", "implement.yml"))
    m = re.search(r"- name: Explain skipped dispatch at review stage\n(.*?)\n\n", impl, re.S)
    CASES += 1
    if not m:
        fail("implement.yml: no 'Explain skipped dispatch at review stage' step")
        return
    step = m.group(1)
    for needle in ("steps.guard.outputs.skip == 'true'",
                   "steps.meta.outputs.stage == 'review'",
                   "comment on the implementation PR", "Maintainer Feedback"):
        CASES += 1
        if needle not in step:
            fail(f"implement.yml: the review-stage explanation step lacks {needle!r}")


def check_reentry_remaining():
    """FR-011: the Maintainer Feedback re-dispatch reply names the cycles
    remaining, floor 0. The arithmetic block is extracted from
    pr-conversation.yml and run, so the gate exercises the shipped text."""
    global CASES
    text = read(os.path.join(ROOT, ".github", "workflows", "pr-conversation.yml"))
    m = re.search(r"          remaining=0\n(.*?\n          fi\n)", text, re.S)
    CASES += 1
    if not m:
        fail("pr-conversation.yml: the re-dispatch reply computes no 'remaining' count")
        return
    for needle in ("max-iterations:", "MAX_ITERATIONS: ${{ inputs.max-iterations }}",
                   "Cycles remaining under the iteration cap"):
        CASES += 1
        if needle not in text:
            fail(f"pr-conversation.yml lacks {needle!r}")
    snippet = "remaining=0\n" + m.group(1)
    for nxt, cap, want in (("4", "5", "1"), ("5", "5", "0"), ("7", "5", "0")):
        CASES += 1
        res = run(["bash", "-c", snippet + 'echo "$remaining"'],
                  env={**os.environ, "next": nxt, "MAX_ITERATIONS": cap})
        if res.stdout.strip() != want:
            fail(f"remaining-count iteration {nxt} of {cap}: got {res.stdout.strip()!r}, want {want!r}")


def check_review_explained_lookup():
    """The review-stage dedupe is keyed on (recorded iteration, dispatched
    iteration) (owner decision B on #992) and counts only bot-authored
    explanations: a re-delivered notification stays quiet, a new review trip
    or a different manual dispatch posts again, and a public commenter
    quoting the marker silences nothing. The shipped lookup runs against a
    `gh` stub that applies its --jq to a fixture comment list, and the
    marker is taken from the shipped explanation body."""
    global CASES
    import json
    import yaml
    doc = yaml.safe_load(read(os.path.join(ROOT, ".github", "workflows", "implement.yml")))
    steps = [st for job in doc["jobs"].values() for st in job.get("steps", [])]
    script = next(st["run"] for st in steps
                  if st.get("name") == "Check for an earlier review-stage explanation")
    body = next(st["with"]["body"] for st in steps
                if st.get("name") == "Explain skipped dispatch at review stage")
    m = re.search(r"<!-- wing-commander-review-explained: .*? -->", body)
    CASES += 1
    if not m:
        fail("implement.yml: the review-stage explanation carries no dedupe marker")
        return
    posted = (m.group(0).replace("${{ steps.meta.outputs.recorded-iteration }}", "4")
              .replace("${{ inputs.iteration }}", "5"))
    summary = "> Implement did nothing: this lifecycle is already in review"
    cases = (
        ("re-delivered notification", "Bot", posted, "4", "5", "true"),
        ("a different manual dispatch", "Bot", posted, "4", "7", "false"),
        ("a new review trip", "Bot", posted, "9", "5", "false"),
        ("a human quoting the marker", "User", posted, "4", "5", "false"),
        ("a legacy explanation with no marker", "Bot", summary, "4", "5", "false"),
    )
    for label, who, text, recorded, dispatched, want in cases:
        tmp = _tmpdir("wc-117-explained-")
        comments = os.path.join(tmp, "comments.json")
        with open(comments, "w", encoding="utf-8") as fh:
            json.dump([{"user": {"type": who}, "body": f"{summary}\n> body {text}"}], fh)
        with open(os.path.join(tmp, "gh"), "w", encoding="utf-8") as fh:
            # `gh api .../comments` serves the REST array; `gh issue view
            # --json comments` would serve {"comments": [...]}.
            fh.write('#!/bin/sh\nshape=.\n[ "$1" = issue ] && shape=\'{comments: .}\'\n'
                     'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q="$2"; shift; done\n'
                     'jq "$shape" "$COMMENTS" | jq -r "${q:-.}"\n')
        os.chmod(os.path.join(tmp, "gh"), 0o755)
        out = os.path.join(tmp, "out")
        env = {**os.environ, "PATH": tmp + os.pathsep + os.environ["PATH"],
               "COMMENTS": comments, "GITHUB_OUTPUT": out,
               "GH_REPO": "o/r", "ISSUE_NUMBER": "1",
               "RECORDED": recorded, "ITERATION": dispatched}
        proc = run(["bash", "-e", "-c", script], env=env)
        got = parse_kv(read(out)).get("explained") if os.path.exists(out) else None
        CASES += 1
        if got != want:
            fail(f"review-stage dedupe ({label}): explained={got!r}, want {want!r}; "
                 f"stderr={proc.stderr}")


def check_reentry_lifecycle_notice():
    """FR-011 names the lifecycle issue: the shipped reply step must post
    the remaining-cycle count there, not only on the PR."""
    global CASES
    import yaml
    doc = yaml.safe_load(read(os.path.join(ROOT, ".github", "workflows", "pr-conversation.yml")))
    script = next(st["run"] for job in doc["jobs"].values()
                  for st in job.get("steps", []) if st.get("name") == "Reply to this review's fold(s)")
    tmp = _tmpdir("wc-117-reentry-")
    calls = os.path.join(tmp, "calls")
    with open(os.path.join(tmp, "gh"), "w", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$GH_CALLS"\n')
    os.chmod(os.path.join(tmp, "gh"), 0o755)
    env = {**os.environ, "PATH": tmp + os.pathsep + os.environ["PATH"],
           "GH_CALLS": calls, "RUNNER_TEMP": tmp,
           "GITHUB_STEP_SUMMARY": os.path.join(tmp, "summary"),
           "FOLDED": "true", "PR_NUMBER": "7", "SPEC_DIR": "specs/117-x",
           "ISSUE": "42", "DISPATCHED": "true", "NEXT_ITERATION": "4",
           "FOLDED_SUMMARY": "- a fold", "RUN_URL": "", "MAX_ITERATIONS": "5"}
    proc = run(["bash", "-c", script], env=env)
    got = read(calls) if os.path.exists(calls) else ""
    CASES += 1
    if proc.returncode != 0 or not re.search(
            r"^issue comment 42 .*Cycles remaining under the iteration cap after this one: 1\.", got, re.M):
        fail(f"pr-conversation.yml: a re-dispatch must tell lifecycle issue #42 the cycles "
             f"remaining (FR-011); rc={proc.returncode} gh calls={got!r} stderr={proc.stderr}")


def check_single_home():
    """No copy of the classification, stop rule or remaining-work rendering
    in a workflow run: block outside the _shared scripts (CLAUDE.md "Shared
    logic has exactly one home")."""
    global CASES
    forbidden = {
        "the [maintainer] classification": "is_maintainer(",
        "the standing-instruction table": "is_standing(",
        "the zero-progress hand-off rule": "checked nothing new, so the loop",
        "the remaining-work headings": "printf '## Unfinished",
    }
    for path in sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))):
        if os.path.basename(path) == "lint-workflows.yml":
            continue
        text = read(path)
        for what, needle in forbidden.items():
            CASES += 1
            if needle in text:
                fail(f"{os.path.basename(path)} carries {what} ({needle!r}); its one home is "
                     ".github/actions/_shared/")
    # The gate itself runs the way run-local-gates.py derives it from lint-workflows.yml.
    CASES += 1
    lint = read(os.path.join(ROOT, ".github", "workflows", "lint-workflows.yml"))
    if "run: python3 .github/scripts/verify-implement-stall-handoff.py" not in lint:
        fail("lint-workflows.yml does not invoke verify-implement-stall-handoff.py")


def main():
    check_review_stage_comment()
    check_reentry_remaining()
    check_single_home()
    check_blocker()
    check_decide()
    check_task_identity()
    check_task_identity_across_cycles()
    check_write_boundary_input()
    check_classification()
    check_composite_outputs()
    check_render()
    check_finalize_wiring()
    check_remaining_work_composite()
    check_prompts()
    check_implement_wiring()
    check_dispatch_stall_reporting()
    check_prompt_parity()
    check_reentry_lifecycle_notice()
    check_review_explained_lookup()
    if FAILURES:
        print(f"verify-implement-stall-handoff: {len(FAILURES)} failure(s) in {CASES} case(s)")
        return 1
    print(f"verify-implement-stall-handoff: {CASES} case(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
