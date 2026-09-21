#!/usr/bin/env python3
"""Gate 73 -- watchdog.yml's clean path: a run with nothing to weigh is
decided by code inside `collect`, never by the diagnose agent.

Before spec 058 every inspection that got as far as reading evidence paid
for the diagnose agent, including the overwhelmingly common one where the
nine collectors all reported and produced no signal at all. The agent's only
possible verdict there was "passed inspection", which is a fact the
aggregate step already holds. FR-011/FR-018/FR-019 move that verdict into a
deterministic step in `collect` and widen `diagnose`'s guard so it skips.

That is three conditions balanced against each other, and every one of them
has a plausible-looking wrong version:

  * skip diagnose on an empty signal set, but NOT when every collector
    failed -- that is the "could not inspect" degradation (FR-013), a
    different event that must still reach its own reporter;
  * post the pass from `collect`, but NOT when the `aggregate` step itself
    failed -- its outputs are stale then, and a "passed inspection" written
    over a step that crashed is exactly the fabricated clean bill of health
    the watchdog exists to prevent (spec.md's edge case);
  * keep the signal-bearing path byte-for-byte as it was (FR-012) -- the
    agent must still run whenever there IS something to weigh.

So this gate evaluates the SHIPPED expressions -- `diagnose`'s `if:`, and
the `if:` of both reporter steps in `collect` -- against five fixtures of
the aggregate state, and EXECUTES the shipped `run:` block of the new
reporter for the two fixtures that reach it, asserting the wording. Reading
the text for substrings instead would pass through a reordered clause or a
misplaced `!`, which is the whole class of defect here.

Five mutations (the signal clauses dropped from diagnose, the
aggregate-outcome guard dropped, the signal-empty guard dropped, the
evidence-available guard dropped, the full-pass wording reworded) must each
break an assertion, so the gate proves it can see the drift it exists for.
It reads one workflow file and runs one extracted shell block; it makes no
network call.

Wiring: lint-workflows.yml, Gate 73. Fixtures are inline (the aggregate
state is five small dicts, not a file tree).
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gha_expr import evaluate, interpolate, truthy  # noqa: E402
from wc_shell_harness import (find_job, find_step, resolve_bash,  # noqa: E402
                              run_step, use_utf8_stdout)

WF = os.path.join(".github", "workflows", "watchdog.yml")
COLLECT_JOB = "collect"
DIAGNOSE_JOB = "diagnose"
# The new deterministic reporter, and the two steps whose behavior it must
# not disturb.
PASS_STEP = 'Report "passed inspection" to lifecycle issue (empty signal set, no agent)'
COULD_NOT_STEP = 'Report "could not inspect" to lifecycle issue'
# diagnose's own passed-inspection reporter: a DIFFERENT event (the agent ran
# and found nothing actionable after weighing real signals, FR-012). Its two
# wordings are the ones PASS_STEP relocates, so they must stay byte-identical.
AGENT_PASS_STEP = 'Report "passed inspection" to lifecycle issue'
AGENT_ACTION = "anthropics/claude-code-action"

ISSUE = "4321"
RUN_URL = "https://example.invalid/runs/9001"


# --------------------------------------------------------------------------
# The subject: the real expressions and the real shell, lifted from the file
# --------------------------------------------------------------------------
def body_lines(run_text):
    """Every `body=` assignment in a shipped run: block, in file order."""
    return [line.strip() for line in run_text.splitlines()
            if line.strip().startswith("body=")]


def load_subject():
    collect, diagnose = find_job(WF, COLLECT_JOB), find_job(WF, DIAGNOSE_JOB)
    pass_step = find_step(WF, PASS_STEP)
    subject = {
        "diagnose:if": str(diagnose.get("if") or ""),
        "pass:if": str(pass_step.get("if") or ""),
        "pass:env": dict(pass_step.get("env") or {}),
        "pass:run": str(pass_step.get("run") or ""),
        "couldnot:if": str(find_step(WF, COULD_NOT_STEP).get("if") or ""),
        "agent-pass:run": str(find_step(WF, AGENT_PASS_STEP).get("run") or ""),
        # "no agent step" is only a meaningful claim if the agent lives in
        # the job that skips and nowhere in the job that does not.
        "collect:uses": [str(s.get("uses") or "") for s in collect.get("steps") or []],
        "diagnose:uses": [str(s.get("uses") or "") for s in diagnose.get("steps") or []],
    }
    for key in ("diagnose:if", "pass:if", "pass:run", "couldnot:if"):
        if not subject[key].strip():
            sys.exit(f"::error file={WF}::{key} is empty -- nothing to evaluate. "
                     f"Removing one of these guards is the regression this gate "
                     f"exists for.")
    if not subject["pass:env"]:
        sys.exit(f"::error file={WF}::the {PASS_STEP!r} step declares no env: -- "
                 f"this gate builds the step's environment from that block so a "
                 f"renamed variable cannot pass unnoticed.")
    return subject


# --------------------------------------------------------------------------
# The fixtures: five shapes of the aggregate step's result
# --------------------------------------------------------------------------
# expect = (the new reporter runs, "could not inspect" runs, diagnose runs)
FIXTURES = [
    dict(label="full pass (9/9 collectors reported, no signal)",
         outcome="success", evidence="true", signals="[]",
         failed="0", total="9", collect_result="success",
         expect=(True, False, False)),
    dict(label="partial pass (2 collectors failed, no signal)",
         outcome="success", evidence="true", signals="[]",
         failed="2", total="9", collect_result="success",
         expect=(True, False, False)),
    dict(label="every collector failed (FR-013 degradation)",
         outcome="success", evidence="false", signals="[]",
         failed="9", total="9", collect_result="success",
         expect=(False, True, False)),
    # The aggregate step died leaving the outputs of an earlier, healthy
    # read: a pass posted here would be a fabricated clean bill of health.
    dict(label="aggregate step itself failed (stale full-pass outputs)",
         outcome="failure", evidence="true", signals="[]",
         failed="0", total="9", collect_result="failure",
         expect=(False, False, False)),
    dict(label="one signal present (FR-012 regression guard)",
         outcome="success", evidence="true",
         signals='[{"id":"a1b2c3d4","signal-kind":"branch-drift"}]',
         failed="0", total="9", collect_result="success",
         expect=(False, False, True)),
]


def step_ctx(fx):
    return {
        "steps.aggregate.outcome": fx["outcome"],
        "steps.aggregate.outputs.evidence-available": fx["evidence"],
        "steps.aggregate.outputs.signals": fx["signals"],
        "steps.aggregate.outputs.collectors-failed": fx["failed"],
        "steps.aggregate.outputs.collectors-total": fx["total"],
    }


def job_ctx(fx):
    """diagnose's context. verify-image-prerequisites is modelled 'skipped',
    the no-image shape spec 058's User Story 1 made the common one -- so this
    fixture set also proves the clean path survives that skip."""
    return {
        "cancelled()": False,
        "needs.verify-image-prerequisites.result": "skipped",
        "needs.collect.result": fx["collect_result"],
        "needs.collect.outputs.evidence-available": fx["evidence"],
        "needs.collect.outputs.signals": fx["signals"],
    }


def env_for(subject, fx):
    """The step's environment, built from the env: block it actually ships."""
    ctx = dict(step_ctx(fx))
    ctx.update({"steps.ctx.outputs.token": "stub-token",
                "steps.spec-slug.outputs.lifecycle-issue": ISSUE,
                "steps.run-meta.outputs.url": RUN_URL})
    return {k: interpolate(str(v), ctx) for k, v in subject["pass:env"].items()}


# --------------------------------------------------------------------------
# The assertions
# --------------------------------------------------------------------------
def run_reporter(subject, fx, bash):
    """Execute the shipped reporter with a `gh` stub; return its argv list."""
    work = tempfile.mkdtemp()
    try:
        bindir = os.path.join(work, "bin")
        os.makedirs(bindir)
        log = os.path.join(work, "gh.log")
        stub = os.path.join(bindir, "gh")
        with open(stub, "w", encoding="utf-8", newline="\n") as fh:
            fh.write('#!/usr/bin/env bash\n'
                     'for a in "$@"; do printf \'%s\\n\' "$a"; done >> "$WC_GH_LOG"\n')
        os.chmod(stub, 0o755)
        env = env_for(subject, fx)
        env.update({"WC_GH_LOG": log,
                    "PATH": bindir + os.pathsep + os.environ.get("PATH", "")})
        rc, out, _outputs, summary = run_step(
            bash, subject["pass:run"], work, env, work)
        argv = []
        if os.path.exists(log):
            with open(log, encoding="utf-8") as fh:
                argv = fh.read().splitlines()
        return rc, out, argv, summary
    finally:
        shutil.rmtree(work, ignore_errors=True)


def suite(subject, bash):
    """Every broken assertion, as a message. Empty = the clean path holds."""
    broke = []

    # The agent must live in the job that skips, and only there -- otherwise
    # "diagnose skipped" would not mean "no agent ran" (SC-013).
    if not any(AGENT_ACTION in u for u in subject["diagnose:uses"]):
        broke.append(f"the {DIAGNOSE_JOB!r} job no longer runs {AGENT_ACTION} -- "
                     f"this gate's 'diagnose skipped means no agent ran' claim "
                     f"rests on it; re-point the gate if the agent moved.")
    if any(AGENT_ACTION in u for u in subject["collect:uses"]):
        broke.append(f"the {COLLECT_JOB!r} job now runs {AGENT_ACTION} -- the "
                     f"clean path is supposed to invoke no agent at all")

    # Relocated, not reworded (contracts/watchdog-clean-path-delta.md): the
    # two wordings in collect's new reporter are the two from diagnose's.
    if body_lines(subject["pass:run"]) != body_lines(subject["agent-pass:run"]):
        broke.append("collect's passed-inspection wording has drifted from "
                     "diagnose's -- spec 058 relocates those two strings, it "
                     "does not reword them; one copy was edited alone")

    for fx in FIXTURES:
        where = fx["label"]
        sctx, jctx = step_ctx(fx), job_ctx(fx)
        try:
            got = (truthy(evaluate(subject["pass:if"], sctx)),
                   truthy(evaluate(subject["couldnot:if"], sctx)),
                   truthy(evaluate(subject["diagnose:if"], jctx)))
        except (ValueError, IndexError) as exc:
            broke.append(f"{where}: an expression did not evaluate: {exc}")
            continue
        for name, g, w in zip(("the passed-inspection reporter",
                               "the could-not-inspect reporter",
                               "the diagnose job"), got, fx["expect"]):
            if g != w:
                broke.append(f"{where}: {name} runs={g}, expected {w}")

        if not got[0]:
            continue

        # It runs -- so what does it say? The wording is the contract
        # (FR-019: a partial pass names both counts), asserted here rather
        # than compared against the shipped string it would be copying.
        rc, out, argv, summary = run_reporter(subject, fx, bash)
        if rc != 0:
            broke.append(f"{where}: the reporter exited {rc}: {out.strip()[:200]}")
            continue
        if argv[:2] != ["issue", "comment"] or (len(argv) > 2 and argv[2] != ISSUE):
            broke.append(f"{where}: expected `gh issue comment {ISSUE}`, got "
                         f"{argv[:3]} (summary fallback: {summary.strip()[:120]!r})")
            continue
        body = argv[-1]
        if "passed inspection" not in body:
            broke.append(f"{where}: the posted body does not record a pass: {body!r}")
        if int(fx["failed"]) > 0:
            reported = int(fx["total"]) - int(fx["failed"])
            for needle in (f"on {reported} of {fx['total']}",
                           f"{fx['failed']} collector(s) errored"):
                if needle not in body:
                    broke.append(f"{where}: a partial pass must name both counts; "
                                 f"{needle!r} missing from {body!r}")
        elif "of 9" in body or "errored" in body:
            broke.append(f"{where}: a full pass must not qualify itself with "
                         f"collector counts: {body!r}")
        if RUN_URL not in body:
            broke.append(f"{where}: the posted body does not link the inspected "
                         f"run: {body!r}")
    return broke


# --------------------------------------------------------------------------
# Mutations -- each guard must be load-bearing (constitution VIII)
# --------------------------------------------------------------------------
def mut_diagnose_ignores_signals(subject):
    s = dict(subject)
    s["diagnose:if"] = (subject["diagnose:if"]
                        .replace(" && needs.collect.outputs.signals != ''", "")
                        .replace(" && needs.collect.outputs.signals != '[]'", ""))
    return s


def mut_pass_ignores_aggregate_outcome(subject):
    s = dict(subject)
    s["pass:if"] = subject["pass:if"].replace(
        "steps.aggregate.outcome == 'success' &&", "")
    return s


def mut_pass_ignores_empty_signal_set(subject):
    s = dict(subject)
    s["pass:if"] = subject["pass:if"].replace(
        "(steps.aggregate.outputs.signals == '' || "
        "steps.aggregate.outputs.signals == '[]')", "true")
    return s


def mut_pass_ignores_evidence_available(subject):
    s = dict(subject)
    s["pass:if"] = subject["pass:if"].replace(
        "steps.aggregate.outputs.evidence-available != 'false' &&", "")
    return s


def mut_full_pass_reworded(subject):
    s = dict(subject)
    s["pass:run"] = subject["pass:run"].replace(
        "run passed inspection. No problems detected.",
        "run inspected on 0 of 9 evidence collectors; nothing errored.")
    return s


MUTATIONS = [
    ("diagnose stops keying on the signal set", mut_diagnose_ignores_signals),
    ("the reporter stops gating on aggregate's outcome",
     mut_pass_ignores_aggregate_outcome),
    ("the reporter stops requiring an empty signal set",
     mut_pass_ignores_empty_signal_set),
    ("the reporter stops requiring readable evidence",
     mut_pass_ignores_evidence_available),
    ("the full-pass wording is reworded in collect alone", mut_full_pass_reworded),
]


def main():
    use_utf8_stdout()
    bash = resolve_bash()
    subject = load_subject()
    failures = suite(subject, bash)
    for f in failures:
        print(f"::error::{f}")
    mutation_failures = 0
    for label, mutate in MUTATIONS:
        mutated = mutate(subject)
        if mutated == subject:
            print(f"::error::mutation {label!r} changed nothing -- the expression "
                  f"it targets has moved; update the mutation with it.")
            mutation_failures += 1
            continue
        if suite(mutated, bash):
            print(f"Mutation OK - {label}.")
        else:
            print(f"::error::MUTATION SURVIVED - {label} broke nothing in this gate.")
            mutation_failures += 1
    print(f"Gate 73: {len(FIXTURES)} aggregate shape(s), {len(MUTATIONS)} "
          f"mutation(s); {len(failures)} failure(s), "
          f"{mutation_failures} mutation failure(s).")
    return 1 if failures or mutation_failures else 0


if __name__ == "__main__":
    sys.exit(main())
