#!/usr/bin/env python3
"""Gate 167 -- finalize and the review gate wait on buildable tasks (specs/123 FR-010).

Drives `finalize-wait/` fixtures (a `<name>.tasks.md` plus a `<name>.expected`
of `key=value` lines) through count-tasks-checkboxes.sh, derives the
refuse/proceed decision the two consumers make (refuse iff the buildable
unchecked count is above zero), and checks that finalize.yml and
lifecycle-review-gate.yml read the shared counter -- no second counter.
"""
import importlib.util
import os
import re
import sys

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


def check_wiring(failures):
    wf = os.path.join(ROOT, ".github", "workflows")
    fin = open(os.path.join(wf, "finalize.yml")).read()
    if not re.search(r"steps\.checkbox-tip-finalize\.outputs\.buildable-unchecked-count", fin):
        failures.append("finalize.yml must read the composite's buildable-unchecked-count")
    if "Refuse to finalize while buildable tasks remain" not in fin:
        failures.append("finalize.yml lost its buildable-wait refusal step")
    gate = open(os.path.join(wf, "lifecycle-review-gate.yml")).read()
    if "_shared/count-tasks-checkboxes.sh" not in gate or "buildable-unchecked-count" not in gate:
        failures.append("lifecycle-review-gate.yml select must read the shared counter's buildable-unchecked-count")
    for name, text in (("finalize.yml", fin), ("lifecycle-review-gate.yml", gate)):
        if re.search(r"grep[^\n]*-c[^\n]*\[ \]", text):
            failures.append(f"{name} holds a second unchecked-task counter")


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
    check_wiring(failures)
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("finalize buildable wait: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
