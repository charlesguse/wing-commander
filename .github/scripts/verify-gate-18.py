#!/usr/bin/env python3
"""Self-test for lint-workflows.yml's Gate 18 (contracts/pagination-shape-gate.md).

Gate 18 passing against a healthy fleet proves nothing: a gate that never
fires is indistinguishable from one whose detection logic is broken. Gate 5
exists because a verifier sat green for weeks while checking a code path
that did not ship, so every detector here carries one of these.

The defect Gate 18 exists for: under `--paginate`, `gh api` applies
whatever `--jq` filter it is given to EACH page separately and concatenates
the raw outputs — it does not slurp first. A filter that collects results
into an array (`--jq '[...]'`), or no `--jq` at all, resolves to
page-shaped garbage once a read passes its first page, and the failure is
silent (spec 036, issue #182). This self-test drives Gate 18's own detection logic against a
fixture table covering every shape contracts/pagination-shape-gate.md
documents, including reach beyond `.github/workflows/` (a composite action,
a checked-in `.sh` file) and the declared-exemption escape hatch.

Drift-proofing: Gate 18's source is EXTRACTED from lint-workflows.yml at run
time rather than copied here, so there is no second copy to fall out of sync
(same discipline as verify-gate-16.py).

Usage: python3 .github/scripts/verify-gate-18.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

LINT_WORKFLOW = ".github/workflows/lint-workflows.yml"
SCAN_SCRIPT = ".github/scripts/verify-gate-18-scan.py"


def extract_gate(path=SCAN_SCRIPT):
    """Return Gate 18's python source.

    Read from the shipped script rather than copied here, for exactly the
    reason it was previously extracted from the workflow heredoc: there
    must be no second copy to fall out of sync (verify-gate-16.py's
    discipline). What #213 changed is only WHERE the single copy lives -
    a file the gate registry can see and run-local-gates.py can run,
    instead of a heredoc that matched neither.
    """
    if not os.path.exists(path):
        sys.exit("::error::verify-gate-18 could not find {0!r}. Gate 18's "
                 "repository scan is expected to live in that file; if it "
                 "moved, update this script and lint-workflows.yml "
                 "together.".format(path))
    return io.open(path, encoding="utf-8").read()


# ---------------------------------------------------------------- fixtures
#
# Every fixture line below that shows a BROKEN `--paginate` shape is test
# data for the temp fixture repos this self-test builds — never a real
# invocation this script makes. Each such line carries its own
# `# wc-pagination-exempt:` comment so that Gate 18, when it scans the REAL
# repository (including this very file, a checked-in .py script), does not
# flag its own fixture table.

ARRAY_COLLECTING = 'gh api "repos/x/y/z" --paginate --jq \'[.[] | select(.a)]\''  # wc-pagination-exempt: fixture text for Gate 18's self-test, not a real invocation
NO_FILTER_ARRAY = 'gh api "repos/x/y/releases" --paginate'  # wc-pagination-exempt: fixture text for Gate 18's self-test, not a real invocation
NO_FILTER_OBJECT = 'gh api "repos/x/y/actions/runs/1/jobs" --paginate'  # wc-pagination-exempt: fixture text for Gate 18's self-test, not a real invocation
STREAM_OBJECT = 'gh api "repos/x/y/z" --paginate --jq \'.[] | {a:.a}\' | jq -s \'.\''
NON_JSON_LINES = 'gh api "repos/x/y/z" --paginate --jq \'.[] | [.a,.b] | @tsv\''
NESTED_BRACKET = 'gh api "repos/x/y/z" --paginate --jq \'.[] | select(.x == ["a"])\''
EXEMPTED_WITH_REASON = 'gh api "repos/x/y/z" --paginate --jq \'[.[] | select(.a)]\'  # wc-pagination-exempt: legacy per-page array, kept intentionally'  # wc-pagination-exempt: fixture text for Gate 18's self-test
BARE_EXEMPT = 'gh api "repos/x/y/z" --paginate --jq \'[.[] | select(.a)]\'  # wc-pagination-exempt'  # wc-pagination-exempt: fixture text for Gate 18's self-test, the inner marker is deliberately bare

# The shipped, post-fix forms of the three distinct filter shapes this
# feature's five call sites use (research.md D1) — proves the detector does
# not false-positive on any of them (the regression case: reverting any one
# of the real fixes back to an array-collecting or no-filter shape must make
# Gate 18 fail again against the real repository, per quickstart.md step 3).
SHIPPED_JOBS_STREAM = 'gh api "repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/jobs" --paginate --jq \'.jobs[]\' 2>/dev/null | jq -s \'.\''
SHIPPED_ANNOTATIONS_STREAM = 'gh api "repos/$GITHUB_REPOSITORY/check-runs/$job_id/annotations" --paginate --jq \'.[] | select(.annotation_level=="warning") | {source:"annotations"}\' 2>/dev/null | jq -s \'.\''
SHIPPED_RELEASES_STREAM = 'gh api repos/github/spec-kit/releases --paginate --jq \'.[] | select(.prerelease == false)\' 2>/dev/null | jq -s \'.\''

# intake.yml:399 and lint-workflows.yml's own Gate 1 both split a
# `--paginate` call's `--jq` argument onto a backslash-continued line — a
# real, legitimate shape a purely per-line scanner would misreport as
# no-filter. These fixtures prove the detector joins continuations before
# judging, in both directions (a safe split call must not fail; a broken
# one must still be caught even when split).
SPLIT_SAFE_LINE1 = 'gh api "repos/x/y/z" --paginate \\'  # wc-pagination-exempt: fixture text for Gate 18's self-test, not a real invocation
SPLIT_SAFE_LINE2 = "  --jq '.[] | {a:.a}' | jq -s '.'"
SPLIT_BROKEN_LINE1 = 'gh api "repos/x/y/z" --paginate \\'  # wc-pagination-exempt: fixture text for Gate 18's self-test, not a real invocation
SPLIT_BROKEN_LINE2 = "  --jq '[.[] | select(.a)]'"


def wf(run_lines, step_name="Step"):
    """A one-job, one-step published workflow whose step's run: is exactly
    `run_lines`, formatted as a literal block scalar so line numbers in the
    written file match `run_lines` 1:1 (Gate 18 locates run: blocks by
    scanning raw file text, not by re-serializing YAML)."""
    indented = "\n".join(("          " + l) if l else "" for l in run_lines)
    return ("name: fixture\n"
            "on:\n"
            "  workflow_call: {}\n"
            "jobs:\n"
            "  job:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: " + step_name + "\n"
            "        run: |\n"
            + indented + "\n")


def action_yml(run_lines, step_name="Step"):
    """A one-step composite action, same line-number guarantee as wf()."""
    indented = "\n".join(("        " + l) if l else "" for l in run_lines)
    return ("name: fixture-action\n"
            "runs:\n"
            "  using: composite\n"
            "  steps:\n"
            "    - name: " + step_name + "\n"
            "      run: |\n"
            + indented + "\n")


CASES = [
    # name, files, expect_fail, must_mention

    ("T067's exact shape: a --jq filter collecting results into an array",
     {".github/workflows/w.yml": wf([ARRAY_COLLECTING])},
     True, ("array-collecting", "jq -s")),

    ("no --jq at all, on an array endpoint",
     {".github/workflows/w.yml": wf([NO_FILTER_ARRAY])},
     True, ("no-filter",)),

    ("no --jq at all, on an object endpoint ({\"jobs\":[...]} shape) — "
     "flagged regardless of the consumer's own tolerance (FR-011)",
     {".github/workflows/w.yml": wf([NO_FILTER_OBJECT])},
     True, ("no-filter",)),

    ("--jq '.[] | {...}' piped to jq -s '.' downstream",
     {".github/workflows/w.yml": wf([STREAM_OBJECT])},
     False, ()),

    ("--jq '.[] | [.a,.b] | @tsv' (non-JSON lines)",
     {".github/workflows/w.yml": wf([NON_JSON_LINES])},
     False, ()),

    ("a literal '[' inside the filter, not at the top level — anchors on "
     "the outermost shape only",
     {".github/workflows/w.yml": wf([NESTED_BRACKET])},
     False, ()),

    ("a FAIL-shaped call carrying a same-line exemption with a reason",
     {".github/workflows/w.yml": wf([EXEMPTED_WITH_REASON])},
     False, ()),

    ("a FAIL-shaped call carrying a bare exemption with no reason: still fails",
     {".github/workflows/w.yml": wf([BARE_EXEMPT])},
     True, ("array-collecting",)),

    ("the same FAIL shape inside a composite action's action.yml",
     {".github/actions/foo/action.yml": action_yml([ARRAY_COLLECTING])},
     True, ("array-collecting",)),

    ("the same FAIL shape inside a checked-in .sh file",
     {"scripts/foo.sh": ARRAY_COLLECTING + "\n"},
     True, ("array-collecting",)),

    ("the shipped, fixed forms of all three distinct filter shapes this "
     "feature's call sites use: none flagged (the regression case)",
     {".github/workflows/w.yml": wf([SHIPPED_JOBS_STREAM,
                                     SHIPPED_ANNOTATIONS_STREAM,
                                     SHIPPED_RELEASES_STREAM])},
     False, ()),

    ("a --paginate call whose --jq argument is on a backslash-continued "
     "line (intake.yml's, and Gate 1's own, real shape) is still recognized",
     {".github/workflows/w.yml": wf([SPLIT_SAFE_LINE1, SPLIT_SAFE_LINE2])},
     False, ()),

    ("an array-collecting --jq split across a backslash continuation is "
     "still caught, not hidden by the join",
     {".github/workflows/w.yml": wf([SPLIT_BROKEN_LINE1, SPLIT_BROKEN_LINE2])},
     True, ("array-collecting",)),
]


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if not os.path.isfile(LINT_WORKFLOW):
        sys.exit(f"::error::run this from the repository root; {LINT_WORKFLOW} not found.")

    gate_src = extract_gate()
    root = tempfile.mkdtemp(prefix="verify_gate18_")
    gate_path = os.path.join(root, "gate18.py")
    io.open(gate_path, "w", encoding="utf-8").write(gate_src)

    failures = []
    try:
        for name, files, expect_fail, must_mention in CASES:
            case_dir = tempfile.mkdtemp(prefix="case_", dir=root)
            for rel, body in files.items():
                full = os.path.join(case_dir, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                io.open(full, "w", encoding="utf-8", newline="\n").write(body)

            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            proc = subprocess.run([sys.executable, gate_path], cwd=case_dir,
                                  capture_output=True, text=True, env=env,
                                  encoding="utf-8", errors="replace")
            out = (proc.stdout or "") + (proc.stderr or "")
            fired = proc.returncode != 0

            problems = []
            if fired != expect_fail:
                problems.append(
                    f"expected the gate to {'FAIL' if expect_fail else 'PASS'}, "
                    f"it {'FAILED' if fired else 'PASSED'}")
            for token in must_mention:
                if token not in out:
                    problems.append(f"error text never mentions {token!r}")
            if expect_fail and "line=" not in out:
                problems.append("a failing site was not reported with a line= location")

            if problems:
                failures.append((name, problems, out.strip()))
                print(f"FAIL  {name}")
                for p in problems:
                    print(f"        - {p}")
                for line in out.strip().splitlines():
                    print(f"        | {line}")
            else:
                print(f"ok    {name}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print(f"::error file={LINT_WORKFLOW}::Gate 18 self-test: "
              f"{len(failures)} of {len(CASES)} scenarios behaved wrongly. Gate 18's "
              f"detection logic does not do what its name claims, so a green Gate 18 "
              f"on the real fleet means nothing.")
        return 1
    print(f"Gate 18 self-test: all {len(CASES)} scenarios behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
