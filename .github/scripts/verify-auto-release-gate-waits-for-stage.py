#!/usr/bin/env python3
"""auto-release.yml's poll merges a stage's PR only once that stage has
reported it, by moving the issue to its own stage label.

WHY THIS EXISTS
---------------
The plan agent opens the plan PR inside its own step. The plan stage's
next deterministic step, "Verify plan PR and flip stage label", then looks
for that PR with `--state open` and only after finding it writes
`stage:plan`. The poll merged any mergeable plan PR on its next 30-second
pass. When that pass fell between the two, the verify step found no open
PR and failed before writing the label, while the merge still started
tasks. The lifecycle reached `stage:done` and the pass check failed on a
timeline with no `stage:plan` (#930). finalize.yml's "Flip stage label"
follows its own open-PR check the same way, behind `stage:review`.

So a gate PR is merged only when the issue carries the label its stage
writes after verifying it (`stage:plan` for plan/, `stage:review` for
spec/, nothing for the spec-draft PR, which stays a draft until clarify
is done). A stage that never writes it ends the attempt as that gate's
fail-gate-stall after GATE_BLOCKED_ALLOWANCE_SECONDS, or when the poll
budget runs out first, never as a generic timeout and never by merging.

This harness EXECUTES the shipped poll step (wc_shell_harness.run_step)
against a `gh` stub that serves one gate PR as mergeable and a sequence of
issue labels, with `sleep` stubbed out, and records every merge. Each
MUTATION reverts one rule and asserts the suite then fails.

Usage: python3 .github/scripts/verify-auto-release-gate-waits-for-stage.py
Requires: bash, jq.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout  # noqa: E402

WORKFLOW = ".github/workflows/auto-release.yml"
STEP = "Poll the test repository to a verdict"
REPO = "wc-fixture/test-repo"
SLUG = "070-foo"
SHARED = ["auto-release-verdict.sh", "auto-release-e2e-clarify-decision.sh",
          "auto-release-e2e-merge-decision.sh", "auto-release-e2e-gate-allowance-decision.sh"]

BASE_ENV = {
    "GH_TOKEN": "dummy-gh-token", "HARNESS_TOKEN": "dummy-harness-token",
    "HARNESS_LOGIN": "machine-acct", "E2E_REPO": REPO, "DEFAULT_BRANCH": "main",
    "ISSUE": "42", "ISSUE_URL": "https://github.com/{0}/issues/42".format(REPO),
    "HEAD_SHA": "a" * 40, "POLL_BUDGET_SECONDS": "2",
    "GATE_BLOCKED_ALLOWANCE_SECONDS": "1200", "MAX_CLARIFICATION_ROUNDS": "3",
    "MODE": "default-runner",
}

# STUB_GATE names the one gate whose PR is open and mergeable (plan/ or
# spec/); every other gate has no PR. STUB_LABELS is a file of comma-
# separated label sets, one per `issue view`, the last repeating.
# STUB_MERGES records each `gh pr merge`.
STUB_GH = r'''#!/usr/bin/env bash
case "$*" in
  "api repos/wc-fixture/test-repo/issues/42 --jq .user.id")
    printf '1\n'; exit 0 ;;
  "api repos/wc-fixture/test-repo/issues/42/comments --paginate --jq"*)
    exit 0 ;;
  "pr list --repo wc-fixture/test-repo --state open --json headRefName,title")
    printf '%s\n' '[{"headRefName":"spec-draft/070-foo","title":"spec-draft: 070-foo (#42)"}]'; exit 0 ;;
  "pr list --repo wc-fixture/test-repo --head "*" --json number,headRefName,baseRefName,mergeable,mergeStateStatus,isDraft,state,statusCheckRollup")
    head="${6}"
    if [ "${head%%070-foo}" = "$STUB_GATE" ]; then
      base="main"; [ "$STUB_GATE" = "plan/" ] && base="spec/070-foo"
      printf '[{"number":9,"headRefName":"%s","baseRefName":"%s","mergeable":"MERGEABLE","mergeStateStatus":"CLEAN","isDraft":false,"state":"OPEN","statusCheckRollup":[]}]\n' "$head" "$base"
    else
      printf '[]\n'
    fi
    exit 0 ;;
  "pr merge 9 --merge --repo wc-fixture/test-repo")
    echo merged >> "$STUB_MERGES"; exit 0 ;;
  "issue view 42 --repo wc-fixture/test-repo --json state,labels")
    n="$(cat "$STUB_COUNTER" 2>/dev/null || echo 0)"
    echo $((n + 1)) > "$STUB_COUNTER"
    total="$(wc -l < "$STUB_LABELS")"
    idx=$((n + 1)); [ "$idx" -gt "$total" ] && idx="$total"
    set_="$(sed -n "${idx}p" "$STUB_LABELS")"
    printf '%s' "$set_" | jq -Rc '{state: "OPEN", labels: (split(",") | map(select(length > 0)) | map({name: .}))}'
    exit 0 ;;
  *)
    echo "unexpected gh invocation: $*" >&2; exit 1 ;;
esac
'''

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-auto-release-gate-waits-for-stage: {0} -- {1}".format(name, detail))


def run(script, gate, label_seq, **env_over):
    """-> (rc, out, verdict dict, merge count, issue views)."""
    root = tempfile.mkdtemp(prefix="wc-ar-gate-wait-")
    try:
        workdir = tempfile.mkdtemp(dir=root)
        runner_temp = tempfile.mkdtemp(dir=root)
        bindir = tempfile.mkdtemp(dir=root)
        shared = os.path.join(workdir, ".github", "actions", "_shared")
        os.makedirs(shared)
        for name in SHARED:
            shutil.copyfile(os.path.join(".github", "actions", "_shared", name),
                            os.path.join(shared, name))
        for name, body in (("gh", STUB_GH), ("sleep", "#!/usr/bin/env bash\nexit 0\n")):
            path = os.path.join(bindir, name)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
        labels = os.path.join(root, "labels")
        with open(labels, "w", newline="\n") as fh:
            fh.write("\n".join(label_seq) + "\n")
        merges = os.path.join(root, "merges")
        counter = os.path.join(root, "counter")
        open(merges, "w").close()
        env = dict(BASE_ENV)
        env.update({"STUB_GATE": gate, "STUB_LABELS": labels, "STUB_MERGES": merges,
                    "STUB_COUNTER": counter})
        env.update(env_over)
        env["PATH"] = bindir + os.pathsep + os.environ["PATH"]
        rc, out, outputs, _ = run_step(BASH, script, workdir, env, runner_temp)
        try:
            verdict = json.loads(outputs.get("verdict", ""))
        except ValueError:
            verdict = {}
        n_merges = len(open(merges).read().split())
        views = int(open(counter).read()) if os.path.exists(counter) else 0
        return rc, out, verdict, n_merges, views
    finally:
        shutil.rmtree(root, ignore_errors=True)


def suite(script, quiet=False):
    failed = []

    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
        if not quiet:
            check(name, cond, detail)

    rc, out, v, merges, views = run(script, "plan/", ["stage:spec"])
    ck("a mergeable plan PR is not merged while the issue lacks stage:plan",
       rc == 0 and merges == 0 and views > 1, "rc={0} merges={1} views={2}\n{3}".format(rc, merges, views, out))
    ck("... and the attempt ends as the plan gate's stall naming stage:plan, not a timeout",
       v.get("outcome") == "fail-gate-stall" and v.get("failing_check") == "plan PR merge"
       and "stage:plan" in (v.get("expected") or "") and "stage:spec" in (v.get("observed") or ""),
       "verdict={0}".format(v))

    rc, out, v, merges, views = run(script, "plan/", ["stage:spec", "stage:spec", "stage:plan"])
    ck("the plan PR is merged once the plan stage has written stage:plan",
       rc == 0 and merges == 1 and v.get("outcome") == "fail-timeout",
       "rc={0} merges={1} verdict={2}\n{3}".format(rc, merges, v, out))

    rc, out, v, merges, views = run(script, "spec/", ["stage:implement"])
    ck("a mergeable finalize PR waits for stage:review the same way",
       rc == 0 and merges == 0 and v.get("failing_check") == "finalize PR merge"
       and "stage:review" in (v.get("expected") or ""),
       "rc={0} merges={1} verdict={2}\n{3}".format(rc, merges, v, out))
    rc, out, v, merges, views = run(script, "spec/", ["stage:implement", "stage:review"])
    ck("the finalize PR is merged once the issue is at stage:review",
       rc == 0 and merges == 1, "rc={0} merges={1}\n{2}".format(rc, merges, out))

    rc, out, v, merges, views = run(script, "plan/", ["stage:spec"],
                                    GATE_BLOCKED_ALLOWANCE_SECONDS="0", POLL_BUDGET_SECONDS="3")
    ck("the wait is bounded by GATE_BLOCKED_ALLOWANCE_SECONDS inside the poll budget",
       rc == 0 and merges == 0 and v.get("outcome") == "fail-gate-stall"
       and "was mergeable for 0s" in (v.get("observed") or ""),
       "rc={0} merges={1} verdict={2}\n{3}".format(rc, merges, v, out))
    return failed


MUTATIONS = (
    ("the stage-label wait removed",
     'if [ -n "$ready_label" ] && ! printf \',%s,\' "$labels" | grep -q ",${ready_label},"; then',
     "if false; then"),
    ("plan's ready label dropped", '[plan/]="stage:plan"', '[plan/]=""'),
    ("finalize's ready label dropped", '[spec/]="stage:review"', '[spec/]=""'),
    ("the wait's timer left running once the label arrives",
     'gate_unreported_since[$prefix]=""\n' + ' ' * 16 + 'if merge_err=',
     'if merge_err='),
    ("the poll-budget clamp for an unreported PR removed",
     'if [ -n "${gate_unreported_since[$prefix]}" ]; then', "if false; then"),
)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    script = str(find_step(WORKFLOW, STEP)["run"])
    if "${{" in script:
        sys.exit("::error file={0}::the poll step's run: block holds a ${{{{ }}}} expression; "
                 "this harness cannot execute it.".format(WORKFLOW))
    for name, old, _new in MUTATIONS:
        if script.count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches the poll step exactly "
                     "once. Update the mutation with the step.".format(WORKFLOW, name))
    suite(script)
    for name, old, new in MUTATIONS:
        check("mutation caught: " + name, bool(suite(script.replace(old, new), quiet=True)),
              "the suite stayed green with this rule reverted")
    if failures:
        print("verify-auto-release-gate-waits-for-stage: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-auto-release-gate-waits-for-stage: ok")


if __name__ == "__main__":
    main()
