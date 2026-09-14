#!/usr/bin/env python3
"""Gate 51 -- every verdict-gated issue/comment write excludes rate-limited
or is a registered handler (FR-015b, specs/047-rate-limited-verdict).

WHY THIS EXISTS
----------------
FR-015 keeps every stage's "Fail loud on non-healthy agent verdict" step red
for `rate-limited`, exactly like `exhausted`/`failed`/`unclassifiable` --
that part needs no new code, it falls out of leaving those conditions alone.
But a narrower set of steps do more than turn a step red: they write a
durable, maintainer-facing GitHub issue or comment whenever the verdict was
non-healthy. For those, a usage-window outage reading as "the pipeline is
broken" is exactly the noise specs/047-rate-limited-verdict exists to
remove -- so each such site must either narrow its own condition to exclude
`rate-limited`, or be one of the small set of sanctioned rate-limited-aware
writers this feature itself adds (the watchdog's "Report rate-limited..."
and "Ensure usage-limit issue" steps).

A plan-time hand-count of those call sites (the shape spec 037 used for its
19 turn-budget sites) is exactly the kind of list FR-015b distrusts: it goes
stale the moment a new agent-bearing stage adds an issue-writing step after
this feature lands. This gate enumerates every candidate DYNAMICALLY
(YAML-parsed, never grepped -- Gate 7/23's stated rationale for the same
choice, so a step written in flow style or unusual indentation is not
silently missed) and asserts each one still satisfies the requirement, so a
new site that reintroduces the filing fails by name instead of shipping
quietly.

WHAT COUNTS AS IN SCOPE
------------------------
Every step, in every job, in every .github/workflows/*.yml file, whose
`run:` body contains `gh issue create`, `gh issue comment`, or `gh pr
comment` (a plain substring test over the parsed `run:` string -- no shell
execution) AND whose own `if:`, or its job's own `if:`, textually
references `.outputs.verdict` (covers both `steps.<id>.outputs.verdict` and
`needs.<job>.outputs.verdict` shapes).

WHAT EACH IN-SCOPE SITE MUST HAVE, ONE OF TWO
-----------------------------------------------
(a) Its own condition (step and/or job `if:`) provably excludes the literal
    `rate-limited` -- a `!= 'rate-limited'` term ANDed into the condition,
    or an explicit allow-list none of whose values is `rate-limited`.
(b) Its `(workflow file basename, step name)` pair is registered in this
    script's own EXEMPT_SITES constant -- the small, auditable-in-one-diff
    "one place" FR-015b asks for. Grows only when a future feature adds a
    new sanctioned rate-limited-aware issue/comment writer.

Usage:
    python3 .github/scripts/verify-rate-limited-exemption.py
    python3 .github/scripts/verify-rate-limited-exemption.py --self-test
"""
import glob
import os
import re
import sys
import tempfile

import yaml

WORKFLOWS_GLOB = ".github/workflows/*.yml"

# contracts/watchdog-reporting.md's two sanctioned rate-limited-aware
# issue/comment writers -- the "only issue-facing outputs permitted for
# this class" per contracts/exemption-gate.md. Grows only when a future
# feature adds another sanctioned handler.
EXEMPT_SITES = {
    ("watchdog.yml", 'Report "rate-limited" to lifecycle issue'),
    ("watchdog.yml", "Ensure usage-limit issue"),
}

WRITE_RE = re.compile(r"gh issue create|gh issue comment|gh pr comment")
VERDICT_RE = re.compile(r"\.outputs\.verdict\b")
NOT_EQUAL_RATE_LIMITED_RE = re.compile(r"!=\s*['\"]rate-limited['\"]")
EQUALS_VALUE_RE = re.compile(
    r"\.outputs\.verdict\s*==\s*['\"]([^'\"]+)['\"]")


def excludes_rate_limited(cond):
    """True if `cond` provably excludes the literal 'rate-limited': a
    `!= 'rate-limited'` term ANDed in, or an allow-list (one or more
    `== 'x'` branches on the same output) none of whose values is
    'rate-limited'."""
    if NOT_EQUAL_RATE_LIMITED_RE.search(cond):
        return True
    values = EQUALS_VALUE_RE.findall(cond)
    if values and "rate-limited" not in values:
        return True
    return False


def scan(workflows_glob):
    """(checked_count, failures) -- failures is [((path, job, step), msg)]."""
    failures = []
    checked = 0
    for path in sorted(glob.glob(workflows_glob)):
        try:
            wf = yaml.safe_load(open(path, encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            failures.append(((path, "-", "-"),
                             f"could not parse this workflow as YAML ({exc}) "
                             f"-- cannot confirm its issue/comment writers "
                             f"exclude rate-limited, so this gate fails "
                             f"rather than silently dropping the file."))
            continue
        for job_name, job in (wf.get("jobs") or {}).items():
            job_cond = str((job or {}).get("if") or "")
            for step in (job or {}).get("steps") or []:
                run = str(step.get("run") or "")
                if not WRITE_RE.search(run):
                    continue
                step_cond = str(step.get("if") or "")
                combined = " && ".join(c for c in (job_cond, step_cond) if c)
                if not VERDICT_RE.search(combined):
                    continue
                checked += 1
                step_name = step.get("name") or step.get("id") or "<unnamed>"
                site = (path, job_name, step_name)
                key = (os.path.basename(path), step_name)
                if key in EXEMPT_SITES:
                    continue
                if excludes_rate_limited(combined):
                    continue
                failures.append((site,
                    f"writes an issue/comment gated on a non-healthy "
                    f"verdict (condition: {combined!r}) but neither "
                    f"excludes 'rate-limited' nor is a registered "
                    f"EXEMPT_SITES handler -- a usage-window outage here "
                    f"would file/comment as though the run had crashed."))
    return checked, failures


def main():
    checked, failures = scan(WORKFLOWS_GLOB)
    for site, msg in failures:
        print(f"::error file={site[0]}::Gate 51: job {site[1]!r} step "
              f"{site[2]!r}: {msg}")
    if checked == 0:
        print("::error::Gate 51: found zero verdict-gated issue/comment-"
              "writing steps across every .github/workflows/*.yml file. "
              "Either none exist, or this gate's detection is broken -- "
              "both are worth stopping the build over.")
        return 1
    print(f"Gate 51: {checked} verdict-gated issue/comment-writing site(s) "
          f"checked; {len(failures)} failure(s).")
    return 1 if failures else 0


# --- self-test ---------------------------------------------------------
# Gate 6/7/12/23's precedent: a synthetic fixture proving the detector can
# fail its own subject, not just pass every real site by coincidence
# (constitution VIII).

CASE_A_NARROWED = """\
name: finalize
on:
  workflow_call: {}
jobs:
  finalize:
    runs-on: ubuntu-latest
    steps:
      - name: Fail loudly rather than opening a PR with incomplete content
        if: needs.summarize.outputs.verdict != 'healthy' && needs.summarize.outputs.verdict != 'rate-limited'
        run: |
          gh pr comment "$PR" --body "incomplete"
"""

CASE_B_REGISTERED = """\
name: watchdog
on:
  workflow_call: {}
jobs:
  diagnose:
    runs-on: ubuntu-latest
    steps:
      - name: Report "rate-limited" to lifecycle issue
        if: steps.diagnose-verdict.outputs.verdict == 'rate-limited'
        run: |
          gh issue comment "$ISSUE" --body "usage window exhausted"
"""

CASE_C_UNPROTECTED = """\
name: cleanup
on:
  workflow_call: {}
jobs:
  teardown:
    runs-on: ubuntu-latest
    steps:
      - name: Report a non-healthy summarize verdict
        if: steps.summarize-verdict.outputs.verdict != 'healthy'
        run: |
          gh issue create --title "broken" --body "the run failed"
"""


def self_test():
    failed = []

    def check(label, fname, body, expect_fail, name_fragment=None):
        root = tempfile.mkdtemp(prefix="verify_gate51_")
        with open(os.path.join(root, fname), "w", encoding="utf-8") as fh:
            fh.write(body)
        _checked, failures = scan(os.path.join(root, "*.yml"))
        fired = len(failures) > 0
        if fired != expect_fail:
            failed.append(f"{label}: expected the gate to "
                          f"{'FAIL' if expect_fail else 'PASS'}, it "
                          f"{'FAILED' if fired else 'PASSED'} "
                          f"({failures!r})")
            return
        if expect_fail and name_fragment:
            if not any(name_fragment in site[2] for site, _msg in failures):
                failed.append(f"{label}: failed, but not naming "
                              f"{name_fragment!r} ({failures!r})")
                return
        print(f"ok    {label}")

    check("(a) a correctly-narrowed site passes",
          "finalize.yml", CASE_A_NARROWED, expect_fail=False)
    check("(b) a correctly-registered EXEMPT_SITES site passes",
          "watchdog.yml", CASE_B_REGISTERED, expect_fail=False)
    check("(c) an unprotected, unregistered verdict-gated writer fails, by name",
          "cleanup.yml", CASE_C_UNPROTECTED, expect_fail=True,
          name_fragment="Report a non-healthy summarize verdict")

    if failed:
        print(f"::error::Gate 51 self-test: {len(failed)} check(s) behaved "
              f"wrongly: {'; '.join(failed)}. Gate 51's detection logic "
              f"does not do what its name claims, so a green Gate 51 on the "
              f"real fleet means nothing.")
        return 1
    print("Gate 51 self-test: all 3 checks behaved as expected.")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
