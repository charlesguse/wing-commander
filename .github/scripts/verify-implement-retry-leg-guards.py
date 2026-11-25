#!/usr/bin/env python3
"""implement.yml's escalation retry starts clean, skips an agent that never
started, and its step pointers name steps that exist.

WHY THIS EXISTS
---------------
Three Maintenance backlog (#889) defects in the implement job's retry leg:

1. The cycle agent's transcript stays at
   $RUNNER_TEMP/claude-execution-output.json, and the retry agent step
   writes its own only once its agent starts. A retry that failed in its
   own setup therefore handed its agent-ran signal (`started`), verdict,
   metrics and refusal probe the cycle's transcript (found by the code
   review of #978). The progress step already clears the file first; the
   retry now does the same, under exactly the retry step's own guard.
2. The retry ran even when the cycle's agent never started
   (`steps.agent-ran-cycle.outputs.started == 'false'`, e.g. an image
   missing unzip). It uses the same image, so it failed the same way on a
   more expensive model (found by the code review of #978). Every
   retry-due step now carries `started != 'false'`.
3. A `mirrors "<step>"` comment named a step since renamed (found by the
   code review of #1088). A pointer to a step that does not exist sends a
   maintainer looking for nothing.

Checks (on implement.yml's `implement` job):
  clear     a step running `rm -f "$RUNNER_TEMP/claude-execution-output.json"`
            sits after the cycle agent and before the retry agent, with no
            agent step between it and the retry, and its `if:` EVALUATES
            the same as the retry step's over every combination of the
            values the two guards read (wc_gha_expr; no text matching).
  started   every retry-due step (its `if:` reads inputs.escalation-model),
            the retry step among them, is skipped when the cycle agent
            never started and runs when it started or never reported, with
            every other condition set so the retry is due.
  pointers  every `mirrors "<name>"` comment in every workflow names a
            step `name:` in that same file.

Usage: verify-implement-retry-leg-guards.py [--root DIR]
       verify-implement-retry-leg-guards.py --self-test
"""
import argparse
import itertools
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate_if  # noqa: E402

WORKFLOW = ".github/workflows/implement.yml"
WORKFLOWS_DIR = ".github/workflows"
JOB = "implement"
CYCLE_ID = "cycle"
RETRY_ID = "retry"
AGENT_USES = "anthropics/claude-code-action"
TRANSCRIPT = "$RUNNER_TEMP/claude-execution-output.json"
STARTED = "steps.agent-ran-cycle.outputs.started"
KNOWN = ("steps.", "inputs.")
REF_RE = re.compile(r"\b((?:steps|inputs)\.[A-Za-z0-9_.\-]+)")
MIRRORS_RE = re.compile(r'#.*?\bmirrors\s+"([^"]+)"', re.I)
# The two model references a retry-leg guard compares with each other; each
# is tried at both ids. Every other reference is tried at each string
# literal the two guards hold, plus unset and one value neither names.
MODEL_REFS = ("steps.effective-model.outputs.model", "inputs.escalation-model")
MODEL_IDS = ("model-a", "model-b")
LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")
# The retry is due: lifecycle open, not skipped, the cycle not ok, on a
# tier below the escalation one, tools composed, preflight ready.
DUE = {"steps.lifecycle-gate.outputs.is-open": "true",
       "steps.guard.outputs.skip": "",
       "steps.outcome.outputs.ok": "false",
       "steps.effective-model.outputs.model": "model-a",
       "inputs.escalation-model": "model-b",
       "steps.tool-args-retry.outputs.allowed-tools": "Read",
       "steps.gate-suite-preflight-retry.outputs.ready": "true",
       "steps.project.outputs.project": "proj"}


def guard(step):
    return str(step.get("if", "true"))


def is_agent(step):
    return str(step.get("uses", "")).startswith(AGENT_USES)


def clears_transcript(step):
    run = str(step.get("run", "")).strip()
    return run in ('rm -f "{0}"'.format(TRANSCRIPT), "rm -f {0}".format(TRANSCRIPT))


def refs(*exprs):
    out = set()
    for e in exprs:
        out.update(REF_RE.findall(e))
    return sorted(out)


def same_guard(a, b):
    """None when `a` and `b` evaluate alike everywhere, else a witness."""
    names = refs(a, b)
    lits = sorted(set(LITERAL_RE.findall(a + "\n" + b)) | {"", "x"})
    domains = [MODEL_IDS if n in MODEL_REFS else lits for n in names]
    for values in itertools.product(*domains):
        ctx = dict(zip(names, values))
        ra, rb = evaluate_if(a, ctx, KNOWN), evaluate_if(b, ctx, KNOWN)
        if ra != rb:
            return ctx, ra, rb
    return None


def check_clear(steps):
    errs = []
    ids = [s.get("id") for s in steps]
    if RETRY_ID not in ids or CYCLE_ID not in ids:
        return ["clear: the implement job has no step with id {0!r} or {1!r}; if "
                "either was renamed, update this gate with it".format(CYCLE_ID, RETRY_ID)]
    ci, ri = ids.index(CYCLE_ID), ids.index(RETRY_ID)
    window = [i for i in range(ci + 1, ri) if clears_transcript(steps[i])]
    if not window:
        return ["clear: no step between the cycle agent and the retry agent runs "
                "rm -f \"{0}\", so a retry that fails in its own setup reads the "
                "cycle's transcript as its own".format(TRANSCRIPT)]
    k = window[-1]
    between = [steps[i].get("name") for i in range(k + 1, ri) if is_agent(steps[i])]
    if between:
        errs.append("clear: agent step(s) {0} run between the transcript clear and "
                    "the retry, so the retry can still read their transcript".format(between))
    try:
        w = same_guard(guard(steps[k]), guard(steps[ri]))
    except ValueError as exc:
        return errs + ["clear: cannot evaluate the guards: {0}".format(exc)]
    if w is not None:
        errs.append("clear: {0!r}'s if: and the retry's if: differ at {1} "
                    "(clear={2}, retry={3}); the clear must run exactly when the "
                    "retry does".format(steps[k].get("name"), w[0], w[1], w[2]))
    return errs


def check_started(steps):
    errs = []
    family = [s for s in steps if "inputs.escalation-model" in guard(s)
              and "steps.outcome.outputs.ok" in guard(s)]
    if not any(s.get("id") == RETRY_ID for s in family):
        errs.append("started: the retry step's if: no longer reads "
                    "inputs.escalation-model and steps.outcome.outputs.ok; "
                    "update this gate's retry-due family with it")
    for s in family:
        name = s.get("name")
        try:
            for started, want in (("false", False), ("true", True), ("", True)):
                ctx = dict(DUE)
                ctx[STARTED] = started
                got = evaluate_if(guard(s), ctx, KNOWN)
                if got != want:
                    errs.append("started: {0!r} {1} when the cycle agent's started "
                                "is {2!r}; a retry-due step must skip exactly when "
                                "the cycle agent never started".format(
                                    name, "runs" if got else "is skipped", started))
        except ValueError as exc:
            errs.append("started: cannot evaluate {0!r}'s if: {1}".format(name, exc))
    return errs


def step_names(doc):
    names = set()
    for job in ((doc or {}).get("jobs") or {}).values():
        for s in (job or {}).get("steps") or []:
            if s.get("name"):
                names.add(str(s["name"]))
    return names


_NAMES = {}


def check_pointers(files):
    """files: {path: text}."""
    errs = []
    for path, text in sorted(files.items()):
        if "mirrors" not in text.lower():
            continue
        if text not in _NAMES:
            _NAMES[text] = step_names(yaml.safe_load(text))
        names = _NAMES[text]
        for n, line in enumerate(text.splitlines(), 1):
            for target in MIRRORS_RE.findall(line):
                if target not in names:
                    errs.append("pointers: {0}:{1} says it mirrors {2!r}, but no step "
                                "in that file has that name".format(path, n, target))
    return errs


def run_checks(stage_text, workflow_texts):
    doc = yaml.safe_load(stage_text) or {}
    steps = ((doc.get("jobs") or {}).get(JOB) or {}).get("steps") or []
    if not steps:
        return ["{0} has no {1!r} job steps".format(WORKFLOW, JOB)]
    return check_clear(steps) + check_started(steps) + check_pointers(workflow_texts)


def load(root):
    wdir = os.path.join(root, WORKFLOWS_DIR)
    texts = {}
    for f in sorted(os.listdir(wdir)):
        if f.endswith((".yml", ".yaml")):
            with open(os.path.join(wdir, f), encoding="utf-8") as fh:
                texts[os.path.join(WORKFLOWS_DIR, f)] = fh.read()
    return texts[WORKFLOW], texts


def mutate_steps(stage_text, fn):
    doc = yaml.safe_load(stage_text)
    fn(doc["jobs"][JOB]["steps"])
    return yaml.safe_dump(doc, sort_keys=False)


def _find(steps, pred):
    return next(i for i, s in enumerate(steps) if pred(s))


def _drop_started(cond):
    return re.sub(r"\s*" + re.escape(STARTED) + r" != 'false' &&", "", cond)


def self_test(root):
    stage, texts = load(root)
    base = run_checks(stage, texts)
    if base:
        print("self-test: the shipped workflows must pass first:\n  " + "\n  ".join(base),
              file=sys.stderr)
        return 1

    def drop_clear(steps):
        del steps[_find(steps, clears_transcript)]

    def clear_after_retry(steps):
        k = _find(steps, clears_transcript)
        s = steps.pop(k)
        steps.insert(_find(steps, lambda x: x.get("id") == RETRY_ID) + 1, s)

    def clear_wrong_guard(steps):
        s = steps[_find(steps, clears_transcript)]
        s["if"] = _drop_started(s["if"])

    def clear_unguarded(steps):
        steps[_find(steps, clears_transcript)].pop("if")

    def agent_between(steps):
        ri = _find(steps, lambda x: x.get("id") == RETRY_ID)
        steps.insert(ri, {"name": "stray agent", "uses": AGENT_USES + "@v1"})

    def retry_ignores_started(steps):
        for s in steps:
            if s.get("id") in (RETRY_ID,) or clears_transcript(s):
                s["if"] = _drop_started(s["if"])

    def suite_ignores_started(steps):
        s = steps[_find(steps, lambda x: x.get("id") == "gate-suite-retry")]
        s["if"] = s["if"].replace(" && " + STARTED + " != 'false'", "")

    def retry_inverts_started(steps):
        for s in steps:
            if s.get("id") == RETRY_ID or clears_transcript(s):
                s["if"] = s["if"].replace(STARTED + " != 'false'", STARTED + " == 'false'")

    cases = [("no transcript clear", drop_clear, "clear:"),
             ("clear after the retry", clear_after_retry, "clear:"),
             ("clear guard drops started", clear_wrong_guard, "clear:"),
             ("clear unguarded", clear_unguarded, "clear:"),
             ("agent between clear and retry", agent_between, "clear:"),
             ("retry ignores started", retry_ignores_started, "started:"),
             ("retry gate suite ignores started", suite_ignores_started, "started:"),
             ("retry runs only when not started", retry_inverts_started, "started:")]
    bad = 0
    for name, fn, prefix in cases:
        mutated = mutate_steps(stage, fn)
        errs = run_checks(mutated, dict(texts, **{WORKFLOW: mutated}))
        if not any(e.startswith(prefix) for e in errs):
            print("self-test: mutation {0!r} passed (want a {1} failure): {2}".format(
                name, prefix, errs), file=sys.stderr)
            bad += 1
    stale = stage.replace('mirrors "Run the cycle-start gate suite (credential-free)"',
                          'mirrors "Run local gate suite (cycle)"')
    if stale == stage:
        print("self-test: the retry suite's mirrors pointer is missing", file=sys.stderr)
        bad += 1
    elif not any(e.startswith("pointers:") for e in
                 run_checks(stale, dict(texts, **{WORKFLOW: stale}))):
        print("self-test: a pointer to a renamed step passed", file=sys.stderr)
        bad += 1
    if bad:
        return 1
    print("self-test ok ({0} mutations and a stale pointer each fail)".format(len(cases)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test(args.root)
    stage, texts = load(args.root)
    errs = run_checks(stage, texts)
    for e in errs:
        print("::error file={0}::verify-implement-retry-leg-guards: {1}".format(WORKFLOW, e))
    if errs:
        return 1
    print("verify-implement-retry-leg-guards: the retry clears the cycle transcript, "
          "skips a cycle agent that never started, and every mirrors pointer resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
