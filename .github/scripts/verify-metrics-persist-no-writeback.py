#!/usr/bin/env python3
"""Gate — the metrics persistence layer has no write path back to the
origin pipeline run's status, checks, or comments
(specs/043-durable-metrics-record, tasks.md Phase 9 T066, FR-019/FR-019a).

WHY THIS EXISTS
---------------
"A persistence failure never disturbs the run it reports on" is true today
by construction — wing-commander-metrics-persist/action.yml only ever
receives run-id/destination-branch/destination-path as inputs (no
github.event.* about the origin run's checks/comments), and metrics-
persist.yml is triggered out-of-band via workflow_run, a separate workflow
run with its own status. But nothing FAILS if a future change reintroduces
a back-reference — the guarantee was designed, never enforced. This is the
static check that makes it enforced: it scans the persistence layer's own
files for any call shaped like a write to the origin run's checks/statuses/
deployments, or any mutating `gh` call whose target is not the destination
branch (git push) or the spec's own lifecycle issue comment
(`issues/.../comments`).

This does not touch wing-commander-metrics-summary or any pipeline stage —
those emit records but never write to the metrics branch or a lifecycle
issue's rollup region themselves; only the persistence layer does.
"""
import glob
import os
import re
import sys

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures", "metrics-persist-no-writeback")

SUBJECT_FILES = [
    ".github/actions/wing-commander-metrics-persist/action.yml",
    ".github/workflows/metrics-persist.yml",
    ".github/workflows/wing-commander-metrics-persist.yml",
]

# Any of these appearing anywhere in the persistence layer is a write path
# back to the origin run's checks/status, or a PR/issue mutation this layer
# has no business making — the layer only ever writes to destination-branch
# (git push) and the spec's own lifecycle issue's rollup comment.
FORBIDDEN_PATTERNS = [
    (re.compile(r"/check-runs"), "writes to a commit's check-runs"),
    (re.compile(r"/statuses\b"), "writes to a commit's combined status"),
    (re.compile(r"/deployments"), "writes to a deployment"),
    (re.compile(r"\bgh\s+run\s+(rerun|cancel)\b"),
     "reruns/cancels a workflow run"),
    (re.compile(r"\bgh\s+pr\s+(comment|review|merge|close)\b"),
     "mutates a pull request via the gh PR shorthand"),
    (re.compile(r"\bgh\s+issue\s+(comment|close)\b"),
     "mutates an issue via the gh issue shorthand (the shipped rollup "
     "always goes through 'gh api .../issues/.../comments' explicitly)"),
]

# A mutating `gh api --method POST|PATCH|PUT|DELETE` call is only legitimate
# when its target is the lifecycle issue's comments endpoint (create or
# update) — anything else is an undeclared write path.
MUTATING_METHOD = re.compile(r"--method\s+(POST|PATCH|PUT|DELETE)\b")
ALLOWED_COMMENTS_ENDPOINT = re.compile(r"issues/[^\s\"']*comments")


def _window(lines, i, span=2):
    lo, hi = max(0, i - span), min(len(lines), i + span + 1)
    return "\n".join(lines[lo:hi])


def scan_text(text):
    """-> list of violation strings; empty means clean."""
    violations = []
    for pattern, why in FORBIDDEN_PATTERNS:
        m = pattern.search(text)
        if m:
            violations.append(f"{why} (matched {m.group(0)!r})")

    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = MUTATING_METHOD.search(line)
        if not m:
            continue
        ctx = _window(lines, i)
        if not ALLOWED_COMMENTS_ENDPOINT.search(ctx):
            violations.append(
                f"mutating 'gh api --method {m.group(1)}' call near line "
                f"{i + 1} does not target the lifecycle issue's comments "
                f"endpoint (issues/.../comments) — an undeclared write "
                f"path: {line.strip()!r}")
    return violations


def scan_file(path):
    with open(path, encoding="utf-8") as f:
        return scan_text(f.read())


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
def _fixture_files():
    if not os.path.isdir(FIXTURES_DIR):
        return []
    return sorted(glob.glob(os.path.join(FIXTURES_DIR, "*.txt")))


def self_test():
    bad = 0
    total = 0
    for path in _fixture_files():
        total += 1
        name = os.path.basename(path)
        violations = scan_file(path)
        if not violations:
            bad += 1
            print(f"[FAIL] {name}: expected this fixture's reintroduced "
                  f"write-back to be caught, but the scan found nothing")
        else:
            print(f"[ok] {name}: caught ({violations[0]})")
    if total == 0:
        print(f"[FAIL] no fixtures found under {FIXTURES_DIR}")
        return 1
    print(f"verify-metrics-persist-no-writeback self-test: "
          f"{total - bad}/{total} fixtures behaved as specified.")
    return 1 if bad else 0


def main():
    if "--self-test" in sys.argv:
        return self_test()

    total_violations = 0
    for rel in SUBJECT_FILES:
        if not os.path.isfile(rel):
            print(f"::error::verify-metrics-persist-no-writeback: {rel} "
                  f"does not exist — this gate's subject list has drifted "
                  f"from the checked-in persistence layer.")
            total_violations += 1
            continue
        violations = scan_file(rel)
        if violations:
            total_violations += len(violations)
            for v in violations:
                print(f"::error file={rel}::verify-metrics-persist-no-writeback: {v}")
        else:
            print(f"verify-metrics-persist-no-writeback: {rel}: clean")
    return 1 if total_violations else 0


if __name__ == "__main__":
    sys.exit(main())
