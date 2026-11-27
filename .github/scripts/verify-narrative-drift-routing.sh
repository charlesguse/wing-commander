#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's narrative-drift
# issue-exemption routing (research.md R9) — specs/046-watchdog-
# supervision-collectors, contracts/gate-coverage-046.md's
# verify-narrative-drift-routing.sh row.
#
# Two halves: (1) EXECUTE the shipped `Determine issue-filing eligibility`
# step (wc_shell_harness.find_step/run_step) against fixture classes — this
# used to be a hand copy of the step's if/else, which mutation testing found
# stayed green through the shipped "narrative-drift" literal being broken
# (constitution VIII); (2) confirm, by reading the live watchdog.yml, that
# `Ensure pipeline-defect issue` actually gates on that decision and that
# `Report finding to lifecycle issue` remains unconditional (FR-025 requires
# the mismatch to still reach the lifecycle issue even though no tracked
# issue is ever filed for it).
#
# Usage: .github/scripts/verify-narrative-drift-routing.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-narrative-drift-routing: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-narrative-drift-routing: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-narrative-drift-routing: jq and python3 are both required."
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 - "$work" <<'PY'
import os
import sys

sys.path.insert(0, ".github/scripts")
from wc_shell_harness import find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

use_utf8_stdout()
bash = resolve_bash()
workdir = sys.argv[1]
step = find_step(".github/workflows/watchdog.yml", "Determine issue-filing eligibility")
script = step["run"]
if "${{" in script:
    sys.exit("::error::verify-narrative-drift-routing: 'Determine issue-filing "
              "eligibility' now contains an unresolved ${{ }} expression this "
              "harness does not substitute.")

cases = [(cls, "true") for cls in ("narrative-drift", "denied-tool", "trusted-file-tampered")] + [
    (cls, "false") for cls in
    ("lost-progress", "stage-mismatch", "turn-budget-trend", "cost-line-missing",
     "cost-line-malformed", "spec-number-collision", "denied-tool-x",
     "narrative-drifts", "trusted-file-tampered-x", "trusted-file", "")
]
failures = []
for cls, expect in cases:
    runner_temp = os.path.join(workdir, "rt-" + cls.replace(" ", "_"))
    os.makedirs(runner_temp, exist_ok=True)
    rc, out, outputs, _ = run_step(bash, script, workdir, {"FINDING_CLASS": cls}, runner_temp)
    got = outputs.get("issueless")
    if rc != 0 or got != expect:
        failures.append(f"class {cls!r} expected issueless={expect!r}, got rc={rc} issueless={got!r}: {out}")
    else:
        print(f"::notice::verify-narrative-drift-routing: class {cls!r} correctly sets issueless={expect!r}")

if failures:
    for f in failures:
        print(f"::error::verify-narrative-drift-routing: {f}")
    sys.exit(1)
print("verify-narrative-drift-routing: shipped 'Determine issue-filing eligibility' step matches for every class.")
PY
py_rc=$?
if [ "$py_rc" -ne 0 ]; then
  reason "the shipped 'Determine issue-filing eligibility' step (executed directly, not a copy) failed one or more class fixtures — see ::error:: above"
fi

# ── The class vocabulary fails closed (#889, found by the code review of
#    #1181): EXECUTE the shipped `Resolve finding-class vocabulary` step
#    with a `gh` that fails and with one that finds no label. Both must
#    compile `class` into an enum of exactly the classes the eligibility
#    step and the evidence-validity gate name, plus `__new__`, never into
#    free text, where a synonym of an issue-exempt class would be filed as
#    a defect. A third run finds only an unrelated label (the registry a
#    fresh repo has after its first `Register new finding class`): the
#    enum must still offer exactly the eligibility step's exempt classes.
python3 - "$work" <<'PY'
import json
import os
import re
import sys

sys.path.insert(0, ".github/scripts")
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

use_utf8_stdout()
bash = resolve_bash()
ensure_jq()
work = sys.argv[1]
WF = ".github/workflows/watchdog.yml"
vocab = find_step(WF, "Resolve finding-class vocabulary")["run"]
if "${{" in vocab:
    sys.exit("::error::verify-narrative-drift-routing: 'Resolve finding-class "
             "vocabulary' now contains an unresolved ${{ }} expression this "
             "harness does not substitute.")


def arms(step_name):
    """Every class literal a `case "$FINDING_CLASS"` arm of the step names."""
    text = find_step(WF, step_name)["run"]
    m = re.search(r'case "\$FINDING_CLASS" in\n(.*?)\n\s*esac', text, re.S)
    if not m:
        sys.exit(f"::error::verify-narrative-drift-routing: no case arm list in '{step_name}'")
    found = set()
    for pat in re.findall(r"^\s*([a-z0-9|-]+)\)", m.group(1), re.M):
        found.update(pat.split("|"))
    return found


exempt = arms("Determine issue-filing eligibility")
named = exempt | arms("Evidence validity gate")
if not {"narrative-drift", "denied-tool"} <= exempt:
    sys.exit("::error::verify-narrative-drift-routing: could not read the "
             f"eligibility step's exempt arms (got {sorted(exempt)})")

failures = []
for case, gh_body, want in (("query-fails", "exit 1", named),
                            ("no-labels", "echo '[]'", named),
                            ("partial-registry", "echo '[\"unrelated-class\"]'",
                             exempt | {"unrelated-class"})):
    d = os.path.join(work, "vocab-" + case)
    bindir = os.path.join(d, "bin")
    os.makedirs(bindir)
    with open(os.path.join(bindir, "gh"), "w", newline="\n") as fh:
        fh.write("#!/usr/bin/env bash\n" + gh_body + "\n")
    os.chmod(os.path.join(bindir, "gh"), 0o755)
    with open(os.path.join(d, "watchdog-signals.json"), "w") as fh:
        json.dump([{"id": "s1"}], fh)
    rc, out, outputs, _ = run_step(bash, vocab, d, {
        "PATH": bindir + os.pathsep + os.environ["PATH"],
        "GH_TOKEN": "x", "GITHUB_REPOSITORY": "o/r",
        "LABEL_PREFIX": "\U0001F415 · "}, d)
    try:
        cls = json.loads(outputs.get("schema", ""))["properties"]["findings"]["items"]["properties"]["class"]
    except (ValueError, KeyError, TypeError):
        failures.append(f"{case}: rc={rc}, no parseable schema output: {out}")
        continue
    enum = set(cls.get("enum") or [])
    want = want | {"__new__"}
    if rc != 0 or enum != want:
        failures.append(f"{case}: rc={rc}, class schema {json.dumps(cls)} is not "
                        f"a fixed enum of exactly {sorted(want)} (missing "
                        f"{sorted(want - enum)}, extra {sorted(enum - want)})")
    else:
        print(f"::notice::verify-narrative-drift-routing: {case}: class is the expected fixed enum")

if failures:
    for f in failures:
        print(f"::error::verify-narrative-drift-routing: {f}")
    sys.exit(1)
PY
if [ "$?" -ne 0 ]; then
  reason "the shipped 'Resolve finding-class vocabulary' step does not fail closed to an enum of exactly the classes the eligibility and evidence-validity steps name, or drops an issue-exempt class from a partial registry — see ::error:: above"
fi

# ── Confirm the live wiring: Ensure pipeline-defect issue gates on
#    issueless, Report finding to lifecycle issue remains unconditional.
WATCHDOG_YML=".github/workflows/watchdog.yml"
if [ -f "$WATCHDOG_YML" ]; then
  if grep -A10 'name: Ensure pipeline-defect issue' "$WATCHDOG_YML" | grep -q "steps.decision.outputs.issueless != 'true'"; then
    note "Ensure pipeline-defect issue carries the issueless skip condition"
  else
    reason "Ensure pipeline-defect issue no longer carries steps.decision.outputs.issueless != 'true' — a narrative-drift Finding could file a tracked issue (FR-025 violation)"
  fi

  if grep -A3 'name: Report finding to lifecycle issue' "$WATCHDOG_YML" | grep -q "if: always() && steps.finding.outcome == 'success'"; then
    note "Report finding to lifecycle issue remains unconditional (always(), gated only on the body having loaded)"
  else
    reason "Report finding to lifecycle issue's if: condition changed shape — FR-025 requires it stay unconditional so a narrative-drift Finding still reaches the lifecycle issue"
  fi

  if grep -A40 'name: Report finding to lifecycle issue' "$WATCHDOG_YML" | grep -q 'ISSUELESS'; then
    note "Report finding to lifecycle issue reads ISSUELESS and carries its own issue-exempt wording"
  else
    reason "Report finding to lifecycle issue no longer reads ISSUELESS — the issue-exempt path has no distinct wording from the coexistence-suppressed branch (research.md R9)"
  fi

  if grep -q 'name: Determine issue-filing eligibility' "$WATCHDOG_YML"; then
    note "Determine issue-filing eligibility step is present in triage"
  else
    reason "Determine issue-filing eligibility step is missing from watchdog.yml's triage job"
  fi
else
  reason "cannot find $WATCHDOG_YML to verify the routing wiring — run this from the repository root"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-narrative-drift-routing: all assertions passed."
  exit 0
fi

echo "❌ verify-narrative-drift-routing: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
