#!/usr/bin/env python3
"""Gate: every transcript/metrics-record upload declares retention-days: 90.

WHY THIS EXISTS
---------------
specs/043-durable-metrics-record User Story 4: every existing
claude-execution-output* transcript upload, and every new metrics-record*
upload, must declare retention-days: 90 explicitly rather than inherit the
repository default (which starts expiring transcripts 2026-10-03). The
requester's own inventory of "14" call sites drifted from the measured 16 —
exactly the class of silent gap a hardcoded count reproduces. This gate is
discovery-based: it finds every actions/upload-artifact@* step whose `name:`
matches the transcript or metrics-record pattern and asserts
retention-days: 90 is present, so a NEW call site added later without
declaring retention fails this gate by construction (FR-033).

WHAT IT CHECKS
--------------
Every .github/workflows/*.yml `actions/upload-artifact@*` step whose
`with.path` ends with `claude-execution-output.json` or
`wing-commander-metrics-record.json` — the two file names
contracts/emission-contract.md fixes as `transcript-path` and
`record-path`'s defaults, and every real call site uses unmodified — must
declare `with.retention-days: 90`. Missing or any other value is a failure,
named by file and step.

WHY `path`, NOT `name` (MF-F6)
-------------------------------
This gate used to key discovery on `with.name`'s prefix
(claude-execution-output*/metrics-record*). `name` is the artifact's
DOWNLOAD label — every consumer of it (wing-commander-metrics-persist's
`gh run download -p 'metrics-record*'`, this repository's own naming
convention) picks it freely, so a call site that uploads the SAME file
under an unconventional name (a typo, a rename that missed this gate's
pattern list) silently evaded the retention check entirely, despite
uploading the exact file this feature exists to retain. `path` is what the
step actually reads off disk before uploading anything, and every real
call site writes to the SAME fixed path (the composite actions' own
`transcript-path`/`record-path` defaults) — a far narrower surface a
future site is far less likely to accidentally dodge.
"""
import argparse
import glob
import os
import shutil
import sys
import tempfile

import yaml

WORKFLOWS_DIR = ".github/workflows"
PATTERNS = ("claude-execution-output.json", "wing-commander-metrics-record.json")


def _rel(root, path):
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return rel[2:] if rel.startswith("./") else rel


def _matches(path):
    if not isinstance(path, str):
        return False
    return any(path.endswith(p) for p in PATTERNS)


def scan_file(path, source):
    """-> [failure strings] for one workflow file's source."""
    failures = []
    try:
        parsed = yaml.safe_load(source) or {}
    except yaml.YAMLError as exc:
        return ["{0}: could not parse YAML ({1})".format(path, exc)]
    for jname, job in (parsed.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses") or ""
            if not str(uses).startswith("actions/upload-artifact@"):
                continue
            with_block = step.get("with") or {}
            artifact_path = with_block.get("path")
            if not _matches(artifact_path):
                continue
            step_label = step.get("name", "(unnamed step)")
            name = with_block.get("name")
            retention = with_block.get("retention-days")
            if retention != 90:
                failures.append(
                    "{0}: job '{1}' step '{2}' (artifact '{3}', path '{4}') "
                    "does not declare retention-days: 90 (found: "
                    "{5!r})".format(
                        path, jname, step_label, name, artifact_path, retention))
    return failures


def evaluate(root="."):
    base = os.path.join(root, *WORKFLOWS_DIR.split("/"))
    if not os.path.isdir(base):
        return ["{0} does not exist under {1!r}".format(WORKFLOWS_DIR, root)], 0
    failures = []
    sites = 0
    for path in sorted(glob.glob(os.path.join(base, "*.yml"))):
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        rel = _rel(root, path)
        file_failures = scan_file(rel, source)
        failures.extend(file_failures)
        # Count every discovered site (pass or fail) so the summary line
        # reflects the discovered population, not just the failures.
        try:
            parsed = yaml.safe_load(source) or {}
        except yaml.YAMLError:
            continue
        for job in (parsed.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses") or ""
                if not str(uses).startswith("actions/upload-artifact@"):
                    continue
                if _matches((step.get("with") or {}).get("path")):
                    sites += 1
    return failures, sites


# ----------------------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------------------
GOOD = """\
name: good
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - name: Upload Claude execution log
        uses: actions/upload-artifact@v6
        with:
          name: claude-execution-output
          path: /tmp/claude-execution-output.json
          if-no-files-found: ignore
          retention-days: 90
"""

MISSING_RETENTION = """\
name: missing retention
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - name: Upload Claude execution log
        uses: actions/upload-artifact@v6
        with:
          name: claude-execution-output
          path: /tmp/claude-execution-output.json
          if-no-files-found: ignore
"""

WRONG_RETENTION = """\
name: wrong retention
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - name: Upload metrics record
        uses: actions/upload-artifact@v6
        with:
          name: metrics-record
          path: /tmp/wing-commander-metrics-record.json
          retention-days: 30
"""

UNRELATED_ARTIFACT = """\
name: unrelated
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - name: Upload unrelated artifact
        uses: actions/upload-artifact@v6
        with:
          name: some-other-thing
          path: /tmp/y.json
"""

# MF-F6: the actual regression this gate exists to close. A site can name
# its artifact anything (upload-artifact's `name:` is only a download
# label) while still writing the SAME transcript file this feature must
# retain — the old name-prefix discovery let exactly this evade the gate.
UNCONVENTIONAL_NAME_MATCHING_PATH = """\
name: unconventional name, real transcript path
on:
  workflow_call:
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - name: Upload something
        uses: actions/upload-artifact@v6
        with:
          name: build-log-42
          path: ${{ runner.temp }}/claude-execution-output.json
          if-no-files-found: ignore
"""

FIXTURES = [
    ("a declared 90-day retention passes",
     {"good.yml": GOOD}, None),
    ("a missing retention-days is caught, named by file/step/artifact",
     {"missing.yml": MISSING_RETENTION},
     "missing.yml: job 'go' step 'Upload Claude execution log' "
     "(artifact 'claude-execution-output', path "
     "'/tmp/claude-execution-output.json') does not declare "
     "retention-days: 90"),
    ("a non-90 retention-days is caught",
     {"wrong.yml": WRONG_RETENTION},
     "wrong.yml: job 'go' step 'Upload metrics record' "
     "(artifact 'metrics-record', path "
     "'/tmp/wing-commander-metrics-record.json') does not declare "
     "retention-days: 90"),
    ("an unrelated artifact upload is not this gate's subject",
     {"unrelated.yml": UNRELATED_ARTIFACT}, None),
    ("an unconventionally named artifact is still caught by its real path (MF-F6)",
     {"unconventional.yml": UNCONVENTIONAL_NAME_MATCHING_PATH},
     "unconventional.yml: job 'go' step 'Upload something' "
     "(artifact 'build-log-42', path "
     "'${{ runner.temp }}/claude-execution-output.json') does not declare "
     "retention-days: 90"),
]


def self_test():
    bad = 0
    for name, files, expect in FIXTURES:
        root = tempfile.mkdtemp(prefix="wc-retention-")
        try:
            workflows = os.path.join(root, ".github", "workflows")
            os.makedirs(workflows)
            for fname, source in files.items():
                with open(os.path.join(workflows, fname), "w",
                          encoding="utf-8", newline="\n") as handle:
                    handle.write(source)
            failures, _ = evaluate(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        joined = " | ".join(failures)
        if expect is None:
            if failures:
                bad += 1
                print("[FAIL] {0}: expected a clean pass, got: {1}".format(
                    name, joined))
            else:
                print("[ok] {0}: clean".format(name))
        elif expect not in joined:
            bad += 1
            print("[FAIL] {0}: expected a failure containing {1!r}, got: "
                  "{2}".format(name, expect, joined))
        else:
            print("[ok] {0}: caught".format(name))
    print("verify-transcript-retention-declared self-test: {0}/{1} fixtures "
          "behaved as specified.".format(len(FIXTURES) - bad, len(FIXTURES)))
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description="Every discovered transcript/metrics-record "
                    "upload-artifact step declares retention-days: 90")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    failures, sites = evaluate(args.root)
    for f in failures:
        print("::error::verify-transcript-retention-declared: {0}".format(f))
    print("verify-transcript-retention-declared: {0} site(s) discovered, "
          "{1} failure(s).".format(sites, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
