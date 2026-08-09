#!/usr/bin/env python3
"""Behavioral tests for watchdog.yml's "Collect: step summaries" step.

WHY THIS EXISTS
---------------
That step is the pipeline's own tripwire: it scrapes each job's log for the
sentinel phrases the stages emit, and everything downstream (diagnose, the
filed issue) can only ever reason about signals this step actually collected.
A sentinel it fails to collect does not degrade the watchdog — it makes the
watchdog silently blind to one class of problem while still reporting
"inspection passed", which is the single most expensive failure shape this
repository has hit (2026-07-24, and again at 2026-07-25's determinism audit).

Nothing tested it. The step is pure shell inside a `gh api` loop, so no gate
could see it, and its two scanning passes had already grown a real conflict:

  * The legacy pass matches ordinary English words (`stalled`, `rejected`,
    `denied`, `abandon`) and is capped at ONE match per job to bound volume.
  * The emitted-token pass matches `WC-SENTINEL: <token>` and is deliberately
    uncapped, because the cap had previously made those signals unreachable.

docs/agent-friendly-workflows.md recommends writing sentinels in exactly the
form `WC-SENTINEL: stalled` — which matched BOTH passes. One event then
emitted two signals carrying the same {job, matched-sentinel} pair, and since
that pair is precisely the identity the "Stamp signal ids" step hashes
(watchdog.yml, the step-summary branch of its projection), they collapsed to
one duplicated id. Worse, the duplicate consumed the legacy pass's single
match for that job, so an unrelated genuine `denied` later in the same log was
never collected — reintroducing, for the legacy pass, the exact masking the
token pass was added to escape.

This harness EXECUTES the shipped step against synthetic job logs, with `gh`
stubbed out, and asserts what lands in signals.json. It reads the step out of
watchdog.yml at run time, so there is no second copy to drift (same discipline
as gate 4's auto-update harness and gate 5's collector fixture — the latter
added after a verifier sat green while checking a filter that did not ship).

It ends with MUTATION checks that reintroduce the conflict and assert the
suite fails. A test that cannot fail is not a test.

Usage: python3 .github/scripts/verify-sentinel-collector.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import copy
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

WATCHDOG = ".github/workflows/watchdog.yml"
STEP = "Collect: step summaries"

BASH = None

# A real job log wraps every step's own script source and env dump between
# these markers. The shipped awk filter strips those blocks, because sentinel
# words in UNEXECUTED source self-matched on essentially every run — a
# 2026-07-24 audit traced 7 false findings, one of them a filed issue, to
# exactly that.
GROUP = "##[group]Run echo hello"
ENDGROUP = "##[endgroup]"


def log(*runtime_lines, echoed=()):
    """A synthetic job log: an echoed script block, then runtime output."""
    lines = [GROUP]
    lines += [f"2026-08-08T00:00:0{i}Z {t}" for i, t in enumerate(echoed)]
    lines.append(ENDGROUP)
    lines += [f"2026-08-08T00:01:0{i}Z {t}" for i, t in enumerate(runtime_lines)]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Scenarios: job log -> the {matched-sentinel} multiset the step must collect
# --------------------------------------------------------------------------
SCENARIOS = [
    dict(
        name="the documented sentinel form is collected exactly once",
        why="docs/agent-friendly-workflows.md tells stage authors to write "
            "'WC-SENTINEL: stalled'. That line matches the emitted-token "
            "regex AND the legacy bare-word alternation, so it produced two "
            "signals for one event — and because the id is hashed from "
            "{job, matched-sentinel}, two signals with one id.",
        log=log("WC-SENTINEL: stalled - the agent stopped making progress."),
        expect=["stalled"],
    ),
    dict(
        name="a token line does not mask an unrelated legacy word",
        why="The legacy pass takes the FIRST match in the whole job log and "
            "stops. When the token line also matched it, that one match was "
            "spent on an event already reported by the token pass, and the "
            "genuine 'denied' below it was never collected at all. A sentinel "
            "that another sentinel can silence is not a safety net.",
        log=log("WC-SENTINEL: stalled - watchdog token from a stage",
                "A tool call was denied by the permission policy."),
        expect=["stalled", "denied"],
    ),
    dict(
        name="the clarification sentinels this pipeline actually emits",
        why="Both 032 sentinels in one job, which is reachable: intake can "
            "author an orphaned questionnaire and disagree with the marker "
            "scan in the same run. Distinct tokens are uncapped.",
        log=log("WARN WC-SENTINEL: clarification-orphaned - no branch found.",
                "WARN WC-SENTINEL: clarification-mismatch - scan disagreed."),
        expect=["clarification-mismatch", "clarification-orphaned"],
    ),
    dict(
        name="a token that is a prefix of another keeps its own line",
        why="The trailing boundary in the token regex stops the shorter token "
            "from borrowing the longer one's line as its excerpt, which would "
            "attach misleading evidence to a real signal.",
        log=log("WC-SENTINEL: clarification-mismatch - the short one.",
                "WC-SENTINEL: clarification-mismatched - the long one."),
        expect=["clarification-mismatch", "clarification-mismatched"],
        expect_excerpts={"clarification-mismatch": "the short one",
                         "clarification-mismatched": "the long one"},
    ),
    dict(
        name="sentinel words in echoed script source are ignored",
        why="Actions echoes each step's own source into the log between "
            "##[group] and ##[endgroup]. This scanner's own regex lives "
            "there, so without the awk strip it matches itself on every "
            "single run. This is the 2026-07-24 false-finding class.",
        log=log("nothing interesting happened",
                echoed=["sentinels='stalled|rejected|denied|abandon'",
                        "token_re='WC-SENTINEL: [a-z][a-z0-9-]*'"]),
        expect=[],
    ),
    dict(
        name="a bare legacy word is still collected",
        why="The legacy pass is not being retired here, only kept disjoint. "
            "Stage output that predates the token convention must still be "
            "seen.",
        log=log("The run was abandoned after the third retry."),
        expect=["abandon"],
    ),
    dict(
        name="the legacy pass stays capped at one match per job",
        why="Those words occur incidentally in agent prose; the cap is what "
            "bounds signal volume, and removing it is not the fix for the "
            "masking above. Only the first is collected, deliberately.",
        log=log("The request was rejected by the API.",
                "A later tool call was denied as well.",
                "The job then stalled."),
        expect=["rejected"],
    ),
]


def render_step(step):
    """The step's run: block with its `${{ }}` env wired to fixture values."""
    script = str(step["run"])
    env = {}
    for k, v in (step.get("env") or {}).items():
        v = str(v)
        if "${{" in v:
            # Both are supplied by the harness; the token is never used
            # because `gh` is stubbed.
            v = {"GH_TOKEN": "dummy-token", "RUN_ID": "12345"}.get(k, "")
        env[k] = v
    if "${{" in script:
        sys.exit(f"::error file={WATCHDOG}::the extracted run: block contains a "
                 f"${{{{ }}}} expression this harness does not resolve.")
    return script, env


def stub_gh(bindir, fixture_dir):
    """A `gh` that answers the two api calls this step makes, from files."""
    path = os.path.join(bindir, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            '#!/usr/bin/env bash\n'
            '# Stub for the two `gh api` reads the collector performs.\n'
            'p="$2"\n'
            f'd="{fixture_dir}"\n'
            'case "$p" in\n'
            '  */jobs) cat "$d/jobs.json" ;;\n'
            '  */logs) id="${p#*/actions/jobs/}"; id="${id%/logs}"; '
            'cat "$d/log-$id.txt" ;;\n'
            '  *) echo "unexpected gh api path: $p" >&2; exit 1 ;;\n'
            'esac\n')
    os.chmod(path, 0o755)


def run_one(script, env, sc, tmproot):
    """Execute the collector against one fixture; return collected signals."""
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    fixtures = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)

    with open(os.path.join(runner_temp, "signals.json"), "w",
              encoding="utf-8") as fh:
        fh.write("[]")
    with open(os.path.join(fixtures, "jobs.json"), "w", encoding="utf-8") as fh:
        json.dump({"jobs": [{"id": 777, "name": "intake",
                             "conclusion": "success"}]}, fh)
    with open(os.path.join(fixtures, "log-777.txt"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write(sc["log"])

    stub_gh(bindir, fixtures.replace("\\", "/"))
    env = dict(env)
    env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    env["GITHUB_REPOSITORY"] = "charlesguse/wing-commander"

    rc, out, _, _ = run_step(BASH, script, workdir, env, runner_temp)
    with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
        signals = json.load(fh)
    for d in (workdir, runner_temp, fixtures, bindir):
        shutil.rmtree(d, ignore_errors=True)
    return rc, out, signals


def suite(script, env, tmproot):
    failures = []
    for sc in SCENARIOS:
        tag = f"[{sc['name']}]"
        rc, out, signals = run_one(script, env, sc, tmproot)
        if rc != 0:
            failures.append(f"{tag} the collector exited {rc}:\n{out}")
            continue

        got = sorted(s["facts"]["matched-sentinel"] for s in signals)
        if got != sorted(sc["expect"]):
            failures.append(
                f"{tag} wrong sentinels collected.\n"
                f"    expected: {sorted(sc['expect']) or '(none)'}\n"
                f"    actual:   {got or '(none)'}\n    {sc['why']}")

        # {job, matched-sentinel} IS the identity the "Stamp signal ids" step
        # hashes for source=step-summary, so a repeated pair is not merely
        # untidy — it is two signals with one id, i.e. one event presented to
        # diagnose as corroborating evidence for itself.
        pairs = [(s["facts"]["job"], s["facts"]["matched-sentinel"])
                 for s in signals]
        dupes = {p for p in pairs if pairs.count(p) > 1}
        if dupes:
            failures.append(
                f"{tag} the same {{job, sentinel}} pair was collected more "
                f"than once ({sorted(dupes)}). That pair is what the signal id "
                f"is hashed from, so these are duplicate ids describing a "
                f"single event. {sc['why']}")

        for tok, want in (sc.get("expect_excerpts") or {}).items():
            line = next((s["facts"]["matched-line"] for s in signals
                         if s["facts"]["matched-sentinel"] == tok), None)
            if line is None:
                continue      # already reported by the multiset check above
            if want not in line:
                failures.append(
                    f"{tag} the excerpt for {tok!r} should quote its own line "
                    f"({want!r}), got {line!r}. Evidence attached to the wrong "
                    f"line is worse than none. {sc['why']}")
    return failures


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------
def mut_overlapping_passes(script):
    """Let the legacy pass see emitted-token lines again (the shipped bug)."""
    return script.replace("""grep -Fv 'WC-SENTINEL: ' | grep -Eim1 "$sentinels\"""",
                          """grep -Eim1 "$sentinels\"""")


def mut_no_group_strip(script):
    """Scan the whole log, echoed script source included."""
    return script.replace(
        'runtime="$(printf \'%s\' "$log" | awk',
        'runtime="$(printf \'%s\' "$log" | cat)" # awk')


def mut_cap_token_pass(script):
    """Put the emitted tokens back under the legacy first-match-wins cap."""
    return script.replace(
        "token_re='WC-SENTINEL: [a-z][a-z0-9-]*'",
        "token_re='WC-SENTINEL: nothing-matches-this'")


MUTATIONS = [
    ("the legacy pass matching emitted-token lines (double-count + masking)",
     mut_overlapping_passes),
    ("scanning echoed script source as if it were runtime output",
     mut_no_group_strip),
    ("the emitted-token pass no longer matching anything", mut_cap_token_pass),
]


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()

    step = find_step(WATCHDOG, STEP)
    if step.get("continue-on-error") is not True:
        print(f"::warning file={WATCHDOG}::{STEP!r} no longer carries "
              f"continue-on-error; a collector that can fail the watchdog job "
              f"is a behavior change worth a second look.")
    script, env = render_step(step)

    tmproot = tempfile.mkdtemp()
    try:
        failures = suite(script, env, tmproot)
        for f in failures:
            print(f"::error::{f}")

        for label, mutate in MUTATIONS:
            mutated = mutate(script)
            if mutated == script:
                print(f"::error::mutation {label!r} changed nothing — the code "
                      f"it edits was rewritten. Update the mutation so this "
                      f"harness keeps proving it can fail.")
                failures.append(f"mutation inapplicable: {label}")
                continue
            broke = suite(mutated, env, tmproot)
            if broke:
                print(f"Mutation OK - {label}: {len(broke)} assertion(s) fail.")
            else:
                print(f"::error::MUTATION SURVIVED - reintroducing {label} "
                      f"broke nothing in this suite, so the suite is not "
                      f"testing that defect. Fix the scenarios, not the "
                      f"mutation.")
                failures.append(f"mutation survived: {label}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    # ASCII only: this also runs on a maintainer's Windows shell, where a
    # cp1252 stdout cannot encode a dash and the gate would die in the print
    # instead of reporting its verdict (same reason as lint-workflows gate 6).
    print(f"sentinel collector: {len(SCENARIOS)} scenario(s); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
