#!/usr/bin/env python3
"""Gate 152 -- the gate suite runs in a credential-free job at every site
spec 095 names (FR-001, FR-004, FR-005, FR-006).

WHY THIS EXISTS
---------------
run-local-gates.py executes every verify-*.py an agent-written branch
carries. Run in a job that holds the loop's App token, any of them could
read the token, rewrite the pristine snapshot, or append to $GITHUB_ENV /
$GITHUB_PATH for every later step (spec 095 paths 1 and 2). Spec 095 moves
each run into its own job holding `permissions: contents: read` and no App
token, returning a verdict artifact the acting job reads fail-closed. This
gate holds that shape so a later edit cannot quietly move the suite back.

WHAT IT CHECKS
--------------
For every site in wc_gate_suite_sites.SITES:
  1. the credential-free job exists and runs the
     wing-commander-contained-gate-suite composite with `site: <site>`;
  2. that job is credential-free: job-level `permissions:` present, every
     scope `read` or `none`; no `environment:` (environment secrets); no
     step that mints the App token (create-github-app-token,
     wing-commander-context); every actions/checkout step has
     `persist-credentials: false` and, if it names a `token:`, names only
     the job's own `github.token` (a secret the job references sits in its
     runner's memory, reachable by the code it runs); and no `secrets.`,
     `WC_BOT_TOKEN` or `github.token` reference anywhere else in the job
     except `container.credentials` (an image pull);
  3. the job that acts on the verdict exists, lists the gate job in its
     `needs:`, and reads it through wing-commander-gate-verdict with the
     same `site:`.
For every job in the covered workflows (wc_gate_suite_sites
.COVERED_WORKFLOWS) that is NOT credential-free by rule 2, no `run:` step
invokes run-local-gates.py and no step uses the contained composite --
except a (workflow, job, step id) listed in EXEMPT_GATE_SUITE_SITES, and an
exemption whose step no longer runs the suite is itself a failure.
Fails LOUD when the job graph cannot be determined: a covered workflow that
is missing or does not parse, a `needs:` naming a job that does not exist,
a site whose jobs are missing.

--self-test runs every fixture under fixtures/095-gate-suite/ (one per
failure branch, plus a passing one) and a set of mutations of the shipped
workflows, and asserts each is caught for its own reason.

NOTE ON GATE NUMBERING: this gate was first registered as Gate 144. It is
numbered 152, not 144: 141-146 were taken by spec 110's PR #982 and 147-148
by spec 112's PR #1003, which claimed them first among the open
lifecycle branches.

Usage: python3 .github/scripts/verify-gate-suite-credential-free.py [--self-test]
"""
import copy
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from wc_gate_suite_sites import (CONTAINED_COMPOSITE, COVERED_WORKFLOWS,  # noqa: E402
                                 EXEMPT_GATE_SUITE_SITES, SITES, Site, suite_steps)

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
FIXTURES = os.path.join(HERE, "fixtures", "095-gate-suite")
VERDICT_COMPOSITE = "wing-commander-gate-verdict"
MINTS_TOKEN = ("create-github-app-token", "wing-commander-context")
READ_SCOPES = ("read", "none")
CREDENTIAL_RE = re.compile(r"secrets\.|WC_BOT_TOKEN|github\.token|GITHUB_TOKEN")
class Undeterminable(Exception):
    pass


def _steps(job):
    steps = (job or {}).get("steps")
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _needs(job):
    needs = (job or {}).get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def credential_problems(job_id, job):
    """Rule 2: why `job` is not credential-free ([] when it is)."""
    problems = []
    perms = job.get("permissions")
    if perms is None:
        problems.append("{0}: no job-level permissions: (it inherits the caller's or "
                        "the workflow's, which this gate cannot bound)".format(job_id))
    elif isinstance(perms, dict):
        for scope, level in perms.items():
            if str(level) not in READ_SCOPES:
                problems.append("{0}: permissions {1}: {2} is above read".format(
                    job_id, scope, level))
    else:
        problems.append("{0}: permissions: {1!r} is not a per-scope read/none map".format(
            job_id, perms))
    if "environment" in job:
        problems.append("{0}: binds an environment: (its secrets would be reachable)".format(
            job_id))
    scan = {k: v for k, v in job.items() if k != "steps"}
    if isinstance(scan.get("container"), dict):
        # The image-pull credential is used by the runner before any step
        # starts; everything else under container: (its env above all)
        # reaches the steps.
        scan["container"] = {k: v for k, v in scan["container"].items() if k != "credentials"}
    if CREDENTIAL_RE.search(json.dumps(scan, default=str)):
        problems.append("{0}: names a credential outside its steps".format(job_id))
    for step in _steps(job):
        label = "{0}: step {1!r}".format(job_id, step.get("name") or step.get("id") or "?")
        uses = str(step.get("uses", ""))
        if any(m in uses for m in MINTS_TOKEN):
            problems.append("{0} mints the App token ({1})".format(label, uses))
        scan = copy.deepcopy(step)
        if uses.startswith("actions/checkout@"):
            with_ = scan.get("with") or {}
            if str(with_.get("persist-credentials", "")).lower() != "false":
                problems.append("{0}: actions/checkout without persist-credentials: "
                                "false".format(label))
            # Only the job's own read-only token: any secret a job references
            # sits in its runner's memory, which the agent-authored code it
            # runs can read (passwordless sudo on a hosted runner) -- even
            # when persist-credentials keeps it out of .git/config.
            token = str(with_.pop("token", "${{ github.token }}") or "")
            if token.replace(" ", "") != "${{github.token}}":
                problems.append("{0}: actions/checkout token {1!r} is not the job's own "
                                "github.token".format(label, token))
        if CREDENTIAL_RE.search(json.dumps(scan, default=str)):
            problems.append("{0} names a credential".format(label))
    return problems


def _uses_with_site(job, composite, site):
    for step in _steps(job):
        if composite in str(step.get("uses", "")) and \
                str((step.get("with") or {}).get("site", "")) == site:
            return True
    return False


def check_docs(docs, sites, exempt):
    """`docs`: {workflow name: parsed document}. Returns problems."""
    problems = []
    used_exemptions = set()
    for name, doc in docs.items():
        jobs = (doc or {}).get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            raise Undeterminable("{0}: no jobs: mapping".format(name))
        for job_id, job in jobs.items():
            for need in _needs(job):
                if need not in jobs:
                    raise Undeterminable("{0}: job {1!r} needs {2!r}, which does not "
                                         "exist".format(name, job_id, need))
            if not credential_problems(job_id, job or {}):
                continue
            for key, how in suite_steps(job or {}):
                if (name, job_id, key) in exempt:
                    used_exemptions.add((name, job_id, key))
                    continue
                problems.append("{0}: job {1!r} holds credentials and its step {2!r} {3} "
                                "-- the gate suite runs only in a credential-free job "
                                "(FR-001/FR-006)".format(name, job_id, key, how))
    for entry in exempt:
        if entry[0] in docs and entry not in used_exemptions:
            problems.append("{0}: exemption for job {1!r} step {2!r} is stale -- that step "
                            "no longer runs the suite; drop the entry".format(*entry))
    for site, where in sites.items():
        doc = docs.get(where.workflow)
        if doc is None:
            raise Undeterminable("site {0}: {1} not read".format(site, where.workflow))
        jobs = doc.get("jobs") or {}
        gate = jobs.get(where.gate_job)
        reader = jobs.get(where.reader)
        if gate is None or reader is None:
            raise Undeterminable("site {0}: {1} has no job {2!r}".format(
                site, where.workflow, where.gate_job if gate is None else where.reader))
        if not _uses_with_site(gate, CONTAINED_COMPOSITE, site):
            problems.append("site {0}: job {1!r} does not run {2} with site: {0}".format(
                site, where.gate_job, CONTAINED_COMPOSITE))
        # A hung suite must end as a failed step (no verdict: red), never as
        # a job timeout, which ends the job 'cancelled' -- read as a gate job
        # replaced while pending (code review of #990).
        for st in _steps(gate):
            if CONTAINED_COMPOSITE in str(st.get("uses", "")) and not st.get("timeout-minutes"):
                problems.append("site {0}: job {1!r} runs the suite with no step "
                                "timeout-minutes, so a hung suite ends the job cancelled, "
                                "not red".format(site, where.gate_job))
        for p in credential_problems(where.gate_job, gate):
            problems.append("site {0}: {1}".format(site, p))
        if where.gate_job not in _needs(reader):
            problems.append("site {0}: job {1!r} does not need {2!r}, so it cannot wait for "
                            "the verdict".format(site, where.reader, where.gate_job))
        if not _uses_with_site(reader, VERDICT_COMPOSITE, site):
            problems.append("site {0}: job {1!r} does not read the verdict through {2} with "
                            "site: {0}".format(site, where.reader, VERDICT_COMPOSITE))
    return problems


def load(directory, names):
    docs = {}
    for name in names:
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as fh:
                docs[name] = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError) as exc:
            raise Undeterminable("{0}: {1}".format(name, exc))
    return docs


def check(docs, sites=SITES, exempt=EXEMPT_GATE_SUITE_SITES):
    try:
        return check_docs(docs, sites, exempt)
    except Undeterminable as exc:
        return ["job graph cannot be determined: {0}".format(exc)]


def run():
    try:
        docs = load(WORKFLOWS, COVERED_WORKFLOWS)
    except Undeterminable as exc:
        problems = ["job graph cannot be determined: {0}".format(exc)]
    else:
        problems = check(docs)
    for p in problems:
        print("::error::Gate 152: " + p)
    if problems:
        return 1
    print("Gate 152: the gate suite runs only in credential-free jobs at {0} site(s); "
          "{1} recorded deferral(s).".format(len(SITES), len(EXEMPT_GATE_SUITE_SITES)))
    return 0


# --- self-test ---------------------------------------------------------------

FIXTURE_SITES = {"board-fix": Site("w.yml", "gate", "publish")}
FIXTURE_CASES = (
    ("good.yml", None),
    ("app-token.yml", "mints the App token"),
    ("permissions-write.yml", "above read"),
    ("persisted-credentials.yml", "persist-credentials"),
    ("secret-in-gate.yml", "names a credential"),
    ("in-job.yml", "holds credentials and its step"),
    ("undeterminable.yml", "cannot be determined"),
    ("no-verdict-reader.yml", "does not read the verdict"),
)


def _mutations():
    def gate_write(docs):
        docs["board-loop.yml"]["jobs"]["gate-suite-fix"]["permissions"]["contents"] = "write"

    def gate_ctx(docs):
        docs["implement.yml"]["jobs"]["gate-suite-implement-cycle"]["steps"].insert(
            1, {"name": "ctx", "uses": "./.wing-commander-pipeline/.github/actions/"
                "wing-commander-context"})

    def suite_back_in_fix(docs):
        docs["board-loop.yml"]["jobs"]["fix"]["steps"].append(
            {"id": "gate-suite-again", "run": "set +e\npython3 .github/scripts/run-local-gates.py\n"})

    def suite_back_in_review(docs):
        docs["board-loop.yml"]["jobs"]["review"]["steps"].append(
            {"id": "x", "uses": "./.wc-pristine-repo/.github/actions/" + CONTAINED_COMPOSITE})

    def gate_job_gone(docs):
        del docs["implement.yml"]["jobs"]["gate-suite-implement-cycle"]
        docs["implement.yml"]["jobs"]["implement"]["needs"].remove("gate-suite-implement-cycle")

    def container_env_secret(docs):
        docs["implement.yml"]["jobs"]["gate-suite-implement-cycle"]["container"]["env"][
            "TOK"] = "${{ secrets.speckit-app-private-key }}"

    def pat_checkout(docs):
        for st in docs["implement.yml"]["jobs"]["gate-suite-implement-cycle"]["steps"]:
            if st.get("name") == "Checkout pipeline repository (shared composite actions)":
                st["with"]["token"] = "${{ secrets.pipeline-repo-token || github.token }}"

    def no_step_timeout(docs):
        for st in docs["board-loop.yml"]["jobs"]["gate-suite-fix"]["steps"]:
            st.pop("timeout-minutes", None)

    def reader_not_waiting(docs):
        docs["board-loop.yml"]["jobs"]["review-fixup-publish"]["needs"].remove(
            "gate-suite-review-fixup")

    def stale_exemption(docs):
        steps = docs["implement.yml"]["jobs"]["implement"]["steps"]
        for s in steps:
            if s.get("id") == "gate-suite-retry":
                s["run"] = "true\n"

    def retry_unexempted(docs):
        return {}

    return (
        ("gate-suite-fix granted contents: write", gate_write, "above read"),
        ("gate-suite-implement-cycle mints the App token", gate_ctx, "mints the App token"),
        ("the suite runs in fix again", suite_back_in_fix, "holds credentials and its step"),
        ("review uses the contained composite itself", suite_back_in_review,
         "holds credentials and its step"),
        ("gate-suite-implement-cycle removed", gate_job_gone, "cannot be determined"),
        ("a secret in the gate job's container env", container_env_secret,
         "names a credential outside its steps"),
        ("the implement gate job checks the pipeline out with pipeline-repo-token",
         pat_checkout, "is not the job's own github.token"),
        ("gate-suite-fix's suite step loses its timeout", no_step_timeout,
         "no step timeout-minutes"),
        ("review-fixup-publish no longer needs its gate job", reader_not_waiting,
         "cannot wait for the verdict"),
        ("the retry exemption outlives its step", stale_exemption, "is stale"),
        ("the retry site without its exemption", retry_unexempted,
         "holds credentials and its step 'gate-suite-retry'"),
    )


def self_test():
    failures = []
    for name, expect in FIXTURE_CASES:
        try:
            docs = load(FIXTURES, (name,))
        except Undeterminable as exc:
            got = ["job graph cannot be determined: {0}".format(exc)]
        else:
            docs = {"w.yml": docs[name]}
            got = check(docs, sites=FIXTURE_SITES, exempt={})
        if expect is None and got:
            failures.append("fixture {0} should pass: {1}".format(name, got))
        elif expect is not None and not any(expect in p for p in got):
            failures.append("fixture {0} not caught for {1!r}: {2}".format(name, expect, got))
        else:
            print("note: fixture {0}: {1}".format(name, got[0] if got else "passes"))
    base = load(WORKFLOWS, COVERED_WORKFLOWS)
    shipped = check(base)
    if shipped:
        failures += ["the shipped workflows already fail: " + p for p in shipped]
    for label, mutate, expect in _mutations():
        docs = copy.deepcopy(base)
        exempt = mutate(docs)
        got = check(docs, exempt=EXEMPT_GATE_SUITE_SITES if exempt is None else exempt)
        if any(expect in p for p in got):
            print("note: mutation caught ({0}): {1}".format(
                label, next(p for p in got if expect in p)))
        else:
            failures.append("mutation {0!r} not caught for {1!r}: {2}".format(label, expect, got))
    for f in failures:
        print("::error::Gate 152 self-test: " + f)
    if failures:
        return 1
    print("Gate 152 self-test: {0} fixture(s) and {1} mutation(s), each caught for its own "
          "reason.".format(len(FIXTURE_CASES), len(_mutations())))
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else run())
