#!/usr/bin/env python3
"""Gate 167 -- finalize and the review gate wait on buildable tasks (specs/123 FR-010).

Drives `finalize-wait/` fixtures (a `<name>.tasks.md` plus a `<name>.expected`
of `key=value` lines) through count-tasks-checkboxes.sh, derives the
refuse/proceed decision the two consumers make (refuse iff the buildable
unchecked count is above zero), and checks that finalize.yml and
lifecycle-review-gate.yml read the shared counter -- no second counter.

Drives `review-gate-skip/` fixtures through lifecycle-review-gate.yml's own
skip block, extracted verbatim from the workflow and run in bash against a
throwaway repo whose `refs/remotes/origin/spec/999-x` holds the fixture's
tasks.md (none when the fixture has no `.tasks.md`: an unreadable count
must not skip the PR). `<name>.expected` pins `skip=true|false`.
"""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
spec = importlib.util.spec_from_file_location(
    "vbc", os.path.join(HERE, "verify-buildable-classification.py"))
vbc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbc)


def check_fixtures(failures):
    d = os.path.join(vbc.FIXTURES, "finalize-wait")
    names = sorted(f[: -len(".tasks.md")] for f in os.listdir(d) if f.endswith(".tasks.md"))
    if not names:
        failures.append("no finalize-wait fixtures found")
    for name in names:
        proc = vbc.run_counter(open(os.path.join(d, name + ".tasks.md")).read())
        if proc.returncode != 0:
            failures.append(f"{name}: counter exited {proc.returncode}")
            continue
        got = vbc.parse_outputs(proc.stdout)
        n = got.get("buildable-unchecked-count", "")
        got["refuse"] = "true" if n.isdigit() and int(n) > 0 else "false"
        for line in open(os.path.join(d, name + ".expected")).read().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if got.get(k) != v:
                    failures.append(f"finalize-wait/{name}: {k} expected {v!r}, got {got.get(k)!r}")


SKIP_BLOCK_RE = re.compile(
    r"^( *)if buildable_out=\"\$\(bash \.wc-pristine-repo/\.github/actions/_shared/"
    r"count-tasks-checkboxes\.sh .*?^\1fi$", re.S | re.M)


def review_gate_skip_block():
    gate = open(os.path.join(ROOT, ".github", "workflows", "lifecycle-review-gate.yml")).read()
    m = SKIP_BLOCK_RE.search(gate)
    return m.group(0) if m else None


def check_review_gate_skip(failures):
    block = review_gate_skip_block()
    if block is None:
        failures.append("lifecycle-review-gate.yml lost its buildable-task skip block "
                        "(if buildable_out=\"$(bash .wc-pristine-repo/.../count-tasks-checkboxes.sh ...) ... fi)")
        return
    d = os.path.join(vbc.FIXTURES, "review-gate-skip")
    if not os.path.isdir(d):
        failures.append("review-gate-skip fixture directory missing")
        return
    names = sorted(f[: -len(".expected")] for f in os.listdir(d) if f.endswith(".expected"))
    if not names:
        failures.append("no review-gate-skip fixtures found")
    script = ("set -uo pipefail\nfor _ in once; do\n" + block +
              "\necho selected\ndone\n")
    for name in names:
        expected = {}
        env = dict(os.environ, head_ref="spec/999-x", slug="999-x", number="1",
                   GITHUB_STEP_SUMMARY=os.devnull)
        env.pop("GATE_SUITE_READY", None)
        for line in open(os.path.join(d, name + ".expected")).read().splitlines():
            if line.startswith("env:") and "=" in line:
                k, v = line[4:].split("=", 1)
                env[k] = v
            elif "=" in line:
                k, v = line.split("=", 1)
                expected[k] = v
        tasks = os.path.join(d, name + ".tasks.md")
        with tempfile.TemporaryDirectory() as tmp:
            os.symlink(ROOT, os.path.join(tmp, ".wc-pristine-repo"))
            vbc.git(tmp, "init", "-q")
            if os.path.exists(tasks):
                os.makedirs(os.path.join(tmp, "specs", "999-x"))
                with open(os.path.join(tmp, "specs", "999-x", "tasks.md"), "w") as fh:
                    fh.write(open(tasks).read())
                meta = os.path.join(d, name + ".spec-meta.json")
                if os.path.exists(meta):
                    with open(os.path.join(tmp, "specs", "999-x", "spec-meta.json"), "w") as fh:
                        fh.write(open(meta).read())
                vbc.git(tmp, "add", "specs")
            vbc.git(tmp, "commit", "-q", "--allow-empty", "-m", "x")
            vbc.git(tmp, "update-ref", "refs/remotes/origin/spec/999-x", "HEAD")
            proc = subprocess.run(["bash", "-c", script], cwd=tmp, env=env,
                                  capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"review-gate-skip/{name}: skip block exited {proc.returncode}: {proc.stderr.strip()}")
            continue
        got = {"skip": "false" if "selected" in proc.stdout.split() else "true"}
        for k, v in expected.items():
            if got.get(k) != v:
                failures.append(f"review-gate-skip/{name}: {k} expected {v!r}, got {got.get(k)!r}")


def check_wiring(failures):
    wf = os.path.join(ROOT, ".github", "workflows")
    fin = open(os.path.join(wf, "finalize.yml")).read()
    if not re.search(r"steps\.checkbox-tip-finalize\.outputs\.buildable-unchecked-count", fin):
        failures.append("finalize.yml must read the composite's buildable-unchecked-count")
    if "Refuse to finalize while buildable tasks remain" not in fin:
        failures.append("finalize.yml lost its buildable-wait refusal step")
    # FR-015/FR-015a: the refusal is a clean hand-off, not a failure.
    m = re.search(r"id: buildable-wait\n.*?(?=\n      - name:)", fin, re.S)
    step = m.group(0) if m else ""
    if re.search(r"^\s*exit 1\s*$", step, re.M):
        failures.append("finalize.yml buildable-wait refusal must not end with a bare `exit 1`")
    for needle in ("WC_BUILDABLE_REFUSED=true", "reason="):
        if needle not in step:
            failures.append(f"finalize.yml buildable-wait refusal missing {needle!r}")
    # Single home: the hand-off lives in the shared helper, not inline.
    code = "\n".join(l for l in step.splitlines() if not l.lstrip().startswith("#"))
    for needle in ("stage:stalled", '.stage = "stalled"', "gh issue comment", "git push"):
        if needle in code:
            failures.append(f"finalize.yml buildable-wait step holds an inline copy of the stalled hand-off ({needle!r})")
    if "wing-commander-stalled-handoff" not in fin:
        failures.append("finalize.yml must call the wing-commander-stalled-handoff composite")
    check_handoff_composite(failures)
    if "steps.buildable-wait.outputs.reason" not in fin:
        failures.append("finalize.yml refusal-reason output must include the buildable-wait reason")
    for sid in ("title", "pr", "verify-pr", "flip-label", "announce-summary",
                "announce-pr", "commit-metadata", "remaining"):
        m2 = re.search(r"id: %s\n\s+if: ([^\n]*)" % re.escape(sid), fin)
        if not m2 or "env.WC_BUILDABLE_REFUSED != 'true'" not in m2.group(1):
            failures.append(f"finalize.yml step {sid} must be gated on the buildable-wait refusal")
    imp = open(os.path.join(wf, "implement.yml")).read()
    if "buildable item(s) remain, so $NEXT_WORKFLOW was not dispatched" not in imp:
        failures.append("implement.yml post_handoff_remaining_work must skip the finalize dispatch while buildable tasks remain")
    # FR-015a: the skip branch ends in stalled through the shared helper and
    # never promises finalization.
    m3 = re.search(r"skip_finalize=false\n.*?return 0\n", imp, re.S)
    skip = m3.group(0) if m3 else ""
    if not skip or "WC_STALLED_HANDOFF=true" not in skip:
        failures.append("implement.yml skip branch must request the stalled hand-off (WC_STALLED_HANDOFF=true)")
    if "the final PR will carry this remaining work" in skip.split('else\n', 1)[0]:
        failures.append("implement.yml skip branch must not promise finalization")
    if "wing-commander-stalled-handoff" not in imp or "env.WC_STALLED_HANDOFF == 'true'" not in imp:
        failures.append("implement.yml must call wing-commander-stalled-handoff when the skip branch fires")
    if re.search(r'"\$closing"', imp) is None or "the lifecycle is **stalled**" not in imp:
        failures.append("implement.yml skip-branch comment must say the lifecycle is stalled")
    gate = open(os.path.join(wf, "lifecycle-review-gate.yml")).read()
    if "_shared/count-tasks-checkboxes.sh" not in gate or "buildable-unchecked-count" not in gate:
        failures.append("lifecycle-review-gate.yml select must read the shared counter's buildable-unchecked-count")
    for name, text in (("finalize.yml", fin), ("lifecycle-review-gate.yml", gate)):
        if re.search(r"grep[^\n]*-c[^\n]*\[ \]", text):
            failures.append(f"{name} holds a second unchecked-task counter")


HANDOFF = os.path.join(ROOT, ".github", "actions", "wing-commander-stalled-handoff", "action.yml")


def check_handoff_composite(failures, path=HANDOFF):
    """The hand-off's one home: the composite's own steps, in order -- the
    spec-meta commit and push, then the label, then the marker comment --
    each a separate step with no if:/continue-on-error, so a failure skips
    the rest. No `_shared/` script may hold it: Gate 12 cannot resolve the
    token of a gh call inside one."""
    import yaml
    act = yaml.safe_load(open(path)) or {}
    steps = [st or {} for st in ((act.get("runs") or {}).get("steps") or [])]
    # Sourcing _shared/git-push-hardening.sh before the push is required
    # (Gate 150); running a _shared script or composite is the hand-off
    # moving out of this file again.
    if any(re.search(r"\bbash\b[^\n]*_shared/", str(st.get("run", ""))) or "_shared/" in str(st.get("uses", ""))
           for st in steps):
        failures.append("wing-commander-stalled-handoff must hold the hand-off in its own steps, not a _shared/ script")

    def first(needle):
        return next((i for i, st in enumerate(steps) if needle in str(st.get("run", ""))), None)
    push, label, comment = first("git push || exit 1"), first("gh issue edit"), first("gh issue comment")
    if None in (push, label, comment) or not push < label < comment:
        failures.append("wing-commander-stalled-handoff must run the spec-meta push, the label and the comment "
                        f"as separate steps in that order (found push={push}, label={label}, comment={comment})")
    for i, st in enumerate(steps):
        if "if" in st or st.get("continue-on-error"):
            failures.append(f"wing-commander-stalled-handoff step {i} must not carry if:/continue-on-error "
                            "(a failure must skip every later write)")
    code = "\n".join(str(st.get("run", "")) for st in steps)
    for needle in ('.stage = "stalled"', "stage:stalled", "iteration=${NEXT_ITER}", "grep -qF"):
        if needle not in code:
            failures.append(f"wing-commander-stalled-handoff missing {needle!r}")


def check_watchdog_handoff(failures):
    """FR-015 hand-off (stage stalled + stalled label) yields no stage-mismatch."""
    fx = os.path.join(vbc.FIXTURES, "watchdog-handoff", "stalled-handoff.expected")
    if not os.path.exists(fx):
        failures.append("watchdog-handoff fixture missing")
        return
    state = dict(l.split("=", 1) for l in open(fx).read().splitlines() if "=" in l)
    wd = open(os.path.join(ROOT, ".github", "workflows", "watchdog.yml")).read()
    m = re.search(r'id: collect-spec-meta\n.*?(?=\n      - name:)', wd, re.S)
    body = m.group(0) if m else ""
    skips = ('"$META_STAGE" = "stalled"' in body and '"$STALLED_LABEL" = "true"' in body
             and "exit 0" in body.split('"$STALLED_LABEL" = "true"', 1)[-1][:400])
    if state.get("meta-stage") == "stalled" and state.get("stalled-label") == "true" and not skips:
        failures.append("watchdog collect-spec-meta must skip a stalled hand-off (stage stalled + label)")


def main():
    failures = []
    check_watchdog_handoff(failures)
    check_fixtures(failures)
    check_review_gate_skip(failures)
    check_wiring(failures)
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("finalize buildable wait: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
