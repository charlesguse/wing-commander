#!/usr/bin/env bash
# Deterministic fixture check for watchdog.yml's "Collect: spec collision"
# step (id: collect-spec-collision) — specs/046-watchdog-supervision-
# collectors, contracts/gate-coverage-046.md's
# verify-spec-collision-collector.sh row.
#
# FILTER below is EXTRACTED from watchdog.yml's live SPEC_COLLISION_FILTER
# at run time (wc_shell_harness.extract_quoted_var), not a hand-typed copy —
# mutation testing found a hand copy here stayed green through a shipped
# collision-threshold break (constitution VIII). The first half feeds that
# filter claimant fixtures directly.
#
# The second half EXECUTES the whole shipped step (wc_shell_harness.
# find_step/run_step), with `gh` stubbed to a canned `gh pr list` and a
# real `specs/` tree in the working directory, the way its siblings
# verify-final-pr-claims-collector.sh and verify-branch-drift-sha-
# baseline.py do (#898): the bash that builds pr_claimants from the PR
# list and the branch prefixes, dir_claimants from the directory listing,
# and writes signals.json/collector-outcomes.json, plus the scope guard,
# never ran before.
#
# Usage: .github/scripts/verify-spec-collision-collector.sh
# Exit code: 0 = all assertions passed; 1 = an assertion failed.

set -uo pipefail

fail_reasons=()
note() { echo "::notice::verify-spec-collision-collector: $1"; }
reason() { fail_reasons+=("$1"); echo "::error::verify-spec-collision-collector: $1"; }

if ! command -v jq >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "::error::verify-spec-collision-collector: jq and python3 are both required."
  exit 1
fi

FILTER="$(python3 - <<'PY'
import sys
sys.path.insert(0, ".github/scripts")
from wc_shell_harness import extract_quoted_var
print(extract_quoted_var(".github/workflows/watchdog.yml", "SPEC_COLLISION_FILTER"))
PY
)"

run_filter() { jq -c "$FILTER" <<<"$1"; }

# ── Positive: two open PRs sharing the same numeric prefix (046).
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"},{"pr":305,"branch":"spec-draft/046-a-different-feature","number":"046"}],"dir_claimants":[]}')"
note "two-open-PR fixture output: $out"
if [ "$(jq '.[0].facts.claimants | length' <<<"$out" 2>/dev/null || echo 0)" != "2" ]; then
  reason "two open PRs sharing number 046 must produce a collision naming both, got $out"
else
  note "two open PRs sharing a number correctly produced a collision naming both"
fi

# ── Positive: one open PR matching an existing specs/ directory on main.
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"}],"dir_claimants":[{"dir":"specs/046-old-landed-spec","number":"046"}]}')"
note "PR-vs-directory fixture output: $out"
kinds="$(jq -c '[.[0].facts.claimants[].kind] | sort' <<<"$out" 2>/dev/null || echo '[]')"
if [ "$kinds" != '["main-directory","open-pr"]' ]; then
  reason "an open PR matching an existing specs/ directory must produce a collision naming both an open-pr and a main-directory claimant, got $out"
else
  note "PR-vs-main-directory correctly produced a collision naming both claimant kinds"
fi

# ── Negative: every open PR has a distinct number → no signal.
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"},{"pr":312,"branch":"spec-draft/047-unrelated","number":"047"}],"dir_claimants":[]}')"
if [ "$out" != "[]" ]; then
  reason "every open PR carrying a distinct number must produce no signal, got $out"
else
  note "all-distinct numbers correctly produced no signal"
fi

# ── Negative: a PR observed twice (the same run re-inspected) must not
#    self-collide (FR-028) — jq's `unique` on the projected {kind,pr,branch}
#    object collapses an exact duplicate to one claimant.
out="$(run_filter '{"own_number":"046","pr_claimants":[{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"},{"pr":301,"branch":"spec-draft/046-watchdog-supervision-collectors","number":"046"}],"dir_claimants":[]}')"
if [ "$out" != "[]" ]; then
  reason "the same PR observed twice must not self-collide, got $out"
else
  note "the same PR observed twice correctly did not self-collide"
fi

# ── The shipped step itself, executed (#898). The scope guard (#750:
#    resolved-stage, not the old display-name comparison) is exercised by
#    running it, not by grepping for its text.
if ! python3 - <<'PY'
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, ".github/scripts")
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

use_utf8_stdout()
ensure_jq()
BASH = resolve_bash()
WATCHDOG = ".github/workflows/watchdog.yml"
STEP = "Collect: spec collision"
SCRIPT = find_step(WATCHDOG, STEP)["run"]
if "${{" in SCRIPT:
    sys.exit(f"::error file={WATCHDOG}::verify-spec-collision-collector could not "
             f"resolve every ${{{{ }}}} expression in {STEP!r}.")

# `gh pr list --json number,headRefName` prints the JSON array itself; a
# fail-list file makes the call fail the way an API error does.
STUB_GH = r"""#!/usr/bin/env bash
d=__FIXTURE_DIR__
if [ "$1" = "pr" ] && [ "$2" = "list" ]; then
  [ -f "$d/fail-list" ] && { echo "HTTP 502" >&2; exit 1; }
  cat "$d/pr-list.json"
  exit 0
fi
echo "unexpected gh invocation: $*" >&2
exit 1
"""


def run_case(*, prs=(), dirs=(), stage="intake", stage_source="name", conclusion="success",
             slug="046-watchdog-supervision-collectors", fail_list=False,
             draft_prefix="", spec_prefix=""):
    tmp = tempfile.mkdtemp()
    try:
        workdir, runner_temp, bindir, fixtures = (os.path.join(tmp, d) for d in
                                                   ("work", "rt", "bin", "fx"))
        for d in (workdir, runner_temp, bindir, fixtures):
            os.makedirs(d)
        for name in dirs:
            os.makedirs(os.path.join(workdir, "specs", name))
        with open(os.path.join(fixtures, "pr-list.json"), "w", encoding="utf-8") as fh:
            json.dump([{"number": n, "headRefName": b} for n, b in prs], fh)
        if fail_list:
            open(os.path.join(fixtures, "fail-list"), "w").close()
        with open(os.path.join(bindir, "gh"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(STUB_GH.replace("__FIXTURE_DIR__", "'" + fixtures + "'"))
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        for name in ("signals.json", "collector-outcomes.json"):
            with open(os.path.join(runner_temp, name), "w", encoding="utf-8") as fh:
                fh.write("[]")
        env = {"GITHUB_REPOSITORY": "charlesguse/wing-commander", "GH_TOKEN": "dummy",
               "RESOLVED_STAGE": stage, "RESOLVED_STAGE_SOURCE": stage_source,
               "RUN_CONCLUSION": conclusion, "SLUG": slug,
               "SPEC_DRAFT_PREFIX": draft_prefix, "SPEC_PREFIX": spec_prefix,
               "PATH": bindir + os.pathsep + os.environ["PATH"]}
        rc, out, _outputs, _summary = run_step(BASH, SCRIPT, workdir, env, runner_temp)
        with open(os.path.join(runner_temp, "signals.json"), encoding="utf-8") as fh:
            signals = json.load(fh)
        with open(os.path.join(runner_temp, "collector-outcomes.json"), encoding="utf-8") as fh:
            outcomes = json.load(fh)
        return rc, out, signals, outcomes
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


failures = []


def check(tag, cond, detail):
    if cond:
        print(f"::notice::verify-spec-collision-collector: [executed: {tag}] ok")
    else:
        failures.append(tag)
        print(f"::error::verify-spec-collision-collector: [executed: {tag}] {detail}")


def claimants(signals):
    return [c for s in signals if s.get("source") == "spec-collision"
            for c in s["facts"]["claimants"]]


def outcome(outcomes):
    return [o["outcome"] for o in outcomes if o.get("collector") == "collect-spec-collision"]


rc, out, sig, oc = run_case(prs=[(301, "spec-draft/046-watchdog-supervision-collectors"),
                                 (305, "spec/046-a-different-feature"),
                                 (312, "spec-draft/047-unrelated"),
                                 (320, "feature/046-not-a-spec-branch")])
check("two open PRs under the draft and spec prefixes collide, with no specs/ directory yet",
      rc == 0 and sorted(c.get("pr") for c in claimants(sig)) == [301, 305]
      and outcome(oc) == ["ok"],
      f"rc={rc} signals={sig} outcomes={oc}\n{out}")

rc, out, sig, oc = run_case(prs=[(301, "spec-draft/046-watchdog-supervision-collectors")],
                            dirs=["046-old-landed-spec", "045-other", "notes"])
check("an open PR and a specs/ directory on main collide",
      rc == 0 and sorted(c["kind"] for c in claimants(sig)) == ["main-directory", "open-pr"]
      and any(c.get("dir") == "specs/046-old-landed-spec" for c in claimants(sig)),
      f"rc={rc} signals={sig}\n{out}")

rc, out, sig, oc = run_case(prs=[(301, "spec-draft/046-watchdog-supervision-collectors"),
                                 (312, "spec-draft/047-unrelated")], dirs=["047-x"])
check("distinct numbers produce no signal and an ok outcome",
      rc == 0 and sig == [] and outcome(oc) == ["ok"], f"rc={rc} signals={sig} outcomes={oc}\n{out}")

rc, out, sig, oc = run_case(prs=[(301, "drafts/046-a"), (305, "specs-live/046-b")],
                            draft_prefix="drafts/", spec_prefix="specs-live/")
check("configured branch prefixes are honoured",
      rc == 0 and sorted(c.get("pr") for c in claimants(sig)) == [301, 305],
      f"rc={rc} signals={sig}\n{out}")

rc, out, sig, oc = run_case(fail_list=True, dirs=["046-a", "046-b"])
check("a failed gh pr list records outcome failed and still reads specs/",
      rc == 0 and outcome(oc) == ["failed"] and len(claimants(sig)) == 2,
      f"rc={rc} signals={sig} outcomes={oc}\n{out}")

rc, out, sig, oc = run_case(stage="plan", prs=[(301, "spec-draft/046-a"), (305, "spec/046-b")])
check("a non-intake run is out of scope: no signal, no outcome",
      rc == 0 and sig == [] and oc == [], f"rc={rc} signals={sig} outcomes={oc}\n{out}")

rc, out, sig, oc = run_case(stage="", stage_source="", prs=[(301, "spec-draft/046-a"),
                                                          (305, "spec/046-b")])
check("an unidentified stage records outcome unresolved, no signal",
      rc == 0 and sig == [] and outcome(oc) == ["unresolved"],
      f"rc={rc} signals={sig} outcomes={oc}\n{out}")

rc, out, sig, oc = run_case(conclusion="cancelled", prs=[(301, "spec-draft/046-a"),
                                                        (305, "spec/046-b")])
check("a cancelled run is skipped", rc == 0 and sig == [] and oc == [],
      f"rc={rc} signals={sig} outcomes={oc}\n{out}")

sys.exit(1 if failures else 0)
PY
then
  reason "the shipped \"Collect: spec collision\" step misbehaved under execution (see the [executed: ...] errors above)"
else
  note "the shipped step, executed, enumerates claimants, records outcomes and keeps its scope guard"
fi

if [ "${#fail_reasons[@]}" -eq 0 ]; then
  echo "✅ verify-spec-collision-collector: all assertions passed."
  exit 0
fi

echo "❌ verify-spec-collision-collector: ${#fail_reasons[@]} assertion(s) failed:"
for r in "${fail_reasons[@]}"; do echo "- $r"; done
exit 1
