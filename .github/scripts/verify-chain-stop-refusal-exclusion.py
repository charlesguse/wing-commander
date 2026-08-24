#!/usr/bin/env python3
"""A refusal is still a refusal, and a healthy run is untouched.

WHY THIS EXISTS
----------------
FR-006 requires at most one notice per run: the in-job refusal callout
(research.md D1) and the survivor job's abnormal-termination arm must be
mutually exclusive by construction, not by a runtime dedup check. This
proves the construction two ways:

  1. `wing-commander-preflight`'s SHIPPED shell, driven with both Claude
     credentials empty, actually writes `refused=true` and a non-empty
     `reason` — the positive signal FR-005a requires (quickstart.md §4
     step 1). A refusal detected any other way (an absent value, an empty
     string) is exactly the defect this feature exists to close.
  2. Feeding that real `reason` value into every one of the seven
     survivor-job conditions (reusing Gate 29's own extraction/evaluator —
     `verify-chain-stop-notice.py` — rather than a second copy that could
     drift from it) proves each one evaluates `false` when the entry job's
     `refusal-reason` output is non-empty, regardless of the job's own
     `result` (quickstart.md §4 step 2).

WHAT THIS ALSO CHECKS (T022/T023 — FR-004/FR-009/SC-005)
----------------------------------------------------------
The four currently-quiet paths stay byte-for-byte quiet after this
feature's widening: a duplicate dispatch (idempotency guard skips — the
entry job still reports `success`), a closed lifecycle issue (`Note closed
lifecycle and stop` is an in-job no-op — the entry job still reports
`success`), a successful cycle, and a cancelled run. The first three are
the SAME `needs.*` shape ("entry job success, no refusal, no exhausted-
retry flag") Gate 29 already names "healthy run" — named again here,
explicitly, so a reader of THIS file's output sees the acceptance
scenario, not just an unlabelled row in a reachability gate. The fourth
(cancelled) is Gate 29's own "run cancelled" row, restated here for the
same reason.

Usage: python3 .github/scripts/verify-chain-stop-refusal-exclusion.py
Requires: bash, jq (wc_shell_harness.ensure_jq / resolve_bash).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout
from wc_chain_stop_conditions import (CALL_SITES, default_needs, evaluate,
                                      extract_condition, inputs_for)

PREFLIGHT = ".github/actions/wing-commander-preflight/action.yml"
PREFLIGHT_STEP = "Preflight (credentials, spec-kit, prerequisites)"

BASH = None


def drive_preflight_refusal(runner_temp):
    """The shipped preflight shell, credentials empty — must self-refuse."""
    step = find_step(PREFLIGHT, PREFLIGHT_STEP)
    rc, out, outputs, _ = run_step(
        BASH, step["run"], runner_temp,
        {"OAUTH_TOKEN": "", "API_KEY": "", "REQUIRE_CREDENTIAL": "true",
         "REQUIRE_SPECKIT": "false", "REQUIRE_FILES": "", "REQUIRE_META_STAGE": "",
         "SPEC_DIR": "", "USE_BEDROCK": "false", "AWS_ROLE_ARN_INPUT": "",
         "AWS_REGION_INPUT": "", "BRANCH_PREFIXES": ""},
        runner_temp)
    return rc, out, outputs


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(PREFLIGHT):
        sys.exit(f"::error::run this from the repository root; {PREFLIGHT} "
                 f"not found.")

    failures = []

    import tempfile
    runner_temp = tempfile.mkdtemp()
    try:
        rc, out, outputs = drive_preflight_refusal(runner_temp)
    finally:
        import shutil
        shutil.rmtree(runner_temp, ignore_errors=True)

    if rc == 0:
        failures.append("preflight with both credentials empty exited 0 — "
                        "it should have refused (exit 1).")
    if outputs.get("refused") != "true":
        failures.append(f"preflight's refused output={outputs.get('refused')!r}, "
                        f"expected 'true' (FR-005a's positive signal).")
    reason = outputs.get("reason", "")
    if not reason:
        failures.append("preflight's reason output is empty even though it "
                        "refused — a refusal with no reason cannot be shown "
                        "to a maintainer.")

    if failures:
        for f in failures:
            print(f"::error::{f}")
        print("Refusal-exclusion: step 1 (drive the real refusal) failed; "
              "skipping step 2 (nothing meaningful to feed the conditions).")
        sys.exit(1)

    print(f"Preflight refusal: refused=true, reason={reason!r}.")

    # Step 2: feed that reason into every one of the seven survivor-job
    # conditions, both when the entry job also failed and when it somehow
    # still reports success (a refusal is always a deliberate `exit 1`
    # inside a job that ran, so the job itself is 'failure' in every real
    # case — both are modelled to prove the exclusion holds regardless).
    for site in CALL_SITES:
        cond = extract_condition(site)
        for entry_result in ("failure", "success"):
            needs = default_needs(site)
            needs[site["entry"]] = {"result": entry_result,
                                    "outputs": {"refusal-reason": reason}}
            inputs = inputs_for(site)
            actual = evaluate(cond, needs, inputs, cancelled=False)
            if actual:
                failures.append(
                    f"{site['file']}:{site['job_id']}: survivor condition "
                    f"evaluated True with the entry job's real refusal-"
                    f"reason set (entry result={entry_result!r}) — the "
                    f"refusal and abnormal-termination paths would both "
                    f"fire for the same run (FR-006).")

    # T022/T023 — the four currently-quiet paths, named explicitly.
    QUIET_SCENARIOS = [
        ("duplicate dispatch (idempotency guard skips; entry job still "
         "succeeds)", "success", False),
        ("closed lifecycle issue (in-job no-op; entry job still succeeds)",
         "success", False),
        ("successful cycle", "success", False),
        ("cancelled run", "failure", True),
    ]
    for site in CALL_SITES:
        cond = extract_condition(site)
        inputs = dict([site["mode"]]) if site["mode"] else {}
        for label, entry_result, cancelled in QUIET_SCENARIOS:
            needs = default_needs(site)
            needs[site["entry"]] = {"result": entry_result, "outputs": {}}
            actual = evaluate(cond, needs, inputs, cancelled=cancelled)
            if actual:
                failures.append(
                    f"{site['file']}:{site['job_id']}: survivor condition "
                    f"evaluated True on {label!r} — this path must stay "
                    f"byte-for-byte quiet (FR-004/FR-009/SC-005).")

    for f in failures:
        print(f"::error::{f}")
    print(f"Refusal exclusion: {len(CALL_SITES)} call site(s) x "
          f"(2 refusal shapes + {len(QUIET_SCENARIOS)} quiet scenarios); "
          f"{len(failures)} failure(s).")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
