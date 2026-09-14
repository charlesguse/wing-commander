#!/usr/bin/env python3
"""Gate 53 -- each cross-workflow idiom this feature consolidated has
exactly one home, and no published surface resolves an internal helper
(specs/049-single-home-release-idioms).

WHY THIS EXISTS
---------------
`auto-release.yml` re-typed three of `auto-update-spec-kit.yml`'s
hardest-won shell idioms (scoped App-token mint + reachability check,
orphan-branch force-reset, durable failure issue) instead of consuming a
shared definition, and separately hand-built its own fail-infra verdict
object at every site instead of one helper. specs/049 consolidated each
into exactly one home under `.github/actions/_shared/`. This gate is the
structural scan FR-023 requires -- not an assertion that the two known
consumers call the shared definitions (which could not have failed for
the case that produced the issue this feature fixes), but a scan able to
catch a THIRD, unknown site pasting the idiom anywhere under
`.github/workflows/` or `.github/actions/`.

NOTE ON GATE NUMBERING: research.md/tasks.md for this feature call this
"Gate 52," the highest gate number on `main` at plan time. By the time
this feature's own branch was rebased past #317-and-later, Gate 52 had
already been taken by verify-auto-release-report.py (#325/#335). This
gate is Gate 53 -- the next number actually free in the current tree, per
T001's rule of verifying baseline facts against the real tree rather than
a claim about it.

FOUR CHECKS, per contracts/single-home-gate.md
-----------------------------------------------
1. orphan-reset: literal co-occurrence, in one file, of the three
   fragments that only appear together in the orphan-branch-reset idiom's
   own shell. File-wide scope is safe here -- verified empirically
   against the real tree that none of these three fragments appears
   anywhere outside the declared composite once this feature's own
   refactor lands.

2. failure-issue: co-occurrence of a `gh label create ... --force` call
   and a `gh issue list ... --label "..." --state open --json number --jq
   '.[0].number // empty'`-shaped lookup. UNLIKE the contract's literal
   "in one file" wording, this check is scoped to a single STEP's own
   `run:` text, not the whole file: both fragments, individually, are
   common idioms this repository already uses for entirely unrelated
   labels (a `spec:<slug>` lookup, a `stage:done` label create, a
   `rebase:blocked` escalation). A file-wide scan was verified against the
   real tree to false-positive on six unrelated files
   (auto-update-spec-kit.yml, rebase.yml, tasks.yml, watchdog.yml,
   plan.yml, finalize.yml) that each carry both generic fragments for
   unrelated purposes -- exactly the "reads as evidence while proving
   nothing" failure constitution VIII exists to prevent. Per-step scope
   matches how the real duplicated idiom actually manifested (one step
   doing lookup-then-create-or-comment) and clears all six real files.

3. verdict-shape: a `jq` invocation whose surrounding text contains all
   six field names together. File-wide, per contract -- this shape is
   distinctive enough that no other legitimate jq program in the fleet
   carries all six names.

4. token-mint: YAML-parsed (never grepped, matching Gate 51's stated
   rationale) -- a job (or a composite action's own step list) containing
   both a step with `continue-on-error: true` invoking
   `actions/create-github-app-token@*`, and a later step in the same
   job/step-list whose `if:`/`env:`/`run:` references that step's
   `.outcome` output.

Plus a promotion-prevention pass (FR-025): every `workflow_call`-only
stage workflow and every non-underscore-prefixed composite action scanned
for any reference resolving into a `_shared/` path.

Waivers: `.github/scripts/single-home-waivers.json`, same shape as Gate
31's `stage-invariant-waivers.json` -- `{file, check, pattern, count,
issue, reason}`, stale-checked in both directions.

Byte-identity check (FR-009, contracts/verdict-helper.md): runs the
shipped `_shared/auto-release-verdict.sh` against each of the 15 sites'
real captured inputs (specs/049-single-home-release-idioms/verdict-
fixtures.md) and diffs its stdout against the pre-refactor `jq -n`
output captured for the same inputs. Lives here, alongside this gate's
self-test harness, per contracts/verdict-helper.md.

`--self-test`: synthetic tempdir fixtures (Gate 47 style) prove each
check can fail, a waiver suppresses what it names, a stale waiver fails,
and the promotion check fails on both a stage and a composite reaching
into `_shared/`.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_gate_registry import workflow_files  # noqa: E402
from wc_published_stages import published_stages  # noqa: E402
from wc_shell_harness import resolve_bash, use_utf8_stdout  # noqa: E402

import yaml  # noqa: E402

ACTIONS_DIR = ".github/actions"
WAIVERS_PATH = ".github/scripts/single-home-waivers.json"
VERDICT_SCRIPT = ".github/actions/_shared/auto-release-verdict.sh"

DECLARED_HOMES = {
    "orphan-reset": ".github/actions/_shared/orphan-branch-reset/action.yml",
    "failure-issue": ".github/actions/_shared/durable-failure-issue/action.yml",
    "verdict-shape": ".github/actions/_shared/auto-release-verdict.sh",
    "token-mint": ".github/actions/_shared/scoped-app-token/action.yml",
}
CHECK_NAMES = tuple(DECLARED_HOMES) + ("promotion",)

ORPHAN_FRAGMENTS = (
    "checkout --quiet --orphan",
    "git rm -rq --cached",
    "find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf",
)
LABEL_CREATE_RE = re.compile(r"gh label create\b[^\n]*--force")
ISSUE_LOOKUP_RE = re.compile(
    r"gh issue list\b[^\n]*--label\b[^\n]*--state open\b[^\n]*"
    r"--json number\b[^\n]*--jq\b[^\n]*\.\[0\]\.number // empty")
VERDICT_FIELDS = ("outcome", "verified_head", "failing_check", "expected",
                  "observed", "evidence_url")
SHARED_REF_RE = re.compile(r"\.github/actions/_shared/[A-Za-z0-9_.\-/]+")

Finding = namedtuple("Finding", ["path", "check", "line", "text"])

failures = []


def fail(msg):
    failures.append(msg)
    print(f"::error::{msg}")


def note(msg):
    print(f"note: {msg}")


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def action_files(root="."):
    """Every action.yml/action.yaml and *.sh under .github/actions/**."""
    base = os.path.join(root, ACTIONS_DIR)
    found = []
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            if name in ("action.yml", "action.yaml") or name.endswith(".sh"):
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                found.append(rel)
    return sorted(found)


def _relativize(root, paths):
    """wc_gate_registry's workflow_files() strips a leading './' but does
    not relativize against an arbitrary `root` -- correct for the real
    gate run (root="."), but --self-test's tempdir roots get back
    absolute paths, which breaks every path comparison (declared-home
    exclusion, waiver matching, self-test assertions) that assumes a
    root-relative path."""
    out = []
    for p in paths:
        if os.path.isabs(p):
            p = os.path.relpath(p, root).replace(os.sep, "/")
        out.append(p)
    return out


def all_subject_files(root="."):
    return sorted(_relativize(root, workflow_files(root)) + action_files(root))


def read(root, path):
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return fh.read()


def load_yaml(root, path):
    try:
        return yaml.safe_load(read(root, path)) or {}
    except (yaml.YAMLError, OSError):
        return None


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


# --------------------------------------------------------------------------
# Check 1: orphan-branch-reset (file-wide literal co-occurrence)
# --------------------------------------------------------------------------
def check_orphan_reset(root="."):
    home = DECLARED_HOMES["orphan-reset"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        if all(frag in text for frag in ORPHAN_FRAGMENTS):
            offset = text.index(ORPHAN_FRAGMENTS[0])
            findings.append(Finding(path, "orphan-reset", line_of(text, offset),
                                    ORPHAN_FRAGMENTS[0]))
    return findings


# --------------------------------------------------------------------------
# Check 2: durable-failure-issue (per-step co-occurrence)
# --------------------------------------------------------------------------
def _step_lists(doc):
    """Every (context, [steps]) in a workflow or composite action doc."""
    if not isinstance(doc, dict):
        return []
    out = []
    for job_id, job in (doc.get("jobs") or {}).items():
        out.append((job_id, (job or {}).get("steps") or []))
    runs = doc.get("runs") or {}
    if runs.get("steps"):
        out.append(("runs", runs["steps"]))
    return out


def check_failure_issue(root="."):
    home = DECLARED_HOMES["failure-issue"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        text = read(root, path)
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if LABEL_CREATE_RE.search(run) and ISSUE_LOOKUP_RE.search(run):
                    offset = text.find(run.splitlines()[0]) if run.splitlines() else 0
                    findings.append(Finding(
                        path, "failure-issue",
                        line_of(text, max(offset, 0)),
                        "gh label create ... --force + gh issue list ... "
                        "--jq '.[0].number // empty'"))
    return findings


# --------------------------------------------------------------------------
# Check 3: verdict-shape (file-wide, all six field names near a jq call)
# --------------------------------------------------------------------------
def check_verdict_shape(root="."):
    home = DECLARED_HOMES["verdict-shape"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        for m in re.finditer(r"\bjq\b", text):
            window = text[m.start():m.start() + 600]
            if all(field in window for field in VERDICT_FIELDS):
                findings.append(Finding(path, "verdict-shape", line_of(text, m.start()),
                                        "jq"))
                break
    return findings


# --------------------------------------------------------------------------
# Check 4: token-mint (YAML-structural, per job / composite step-list)
# --------------------------------------------------------------------------
CREATE_TOKEN_RE = re.compile(r"^actions/create-github-app-token@")


def check_token_mint(root="."):
    home = DECLARED_HOMES["token-mint"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        text = read(root, path)
        for _ctx, steps in _step_lists(doc):
            mint_ids = []
            for idx, step in enumerate(steps):
                step = step or {}
                uses = str(step.get("uses") or "")
                if step.get("continue-on-error") is True and CREATE_TOKEN_RE.match(uses):
                    mint_ids.append((idx, step.get("id")))
            for idx, step_id in mint_ids:
                if not step_id:
                    continue
                needle = f"steps.{step_id}.outcome"
                for later in steps[idx + 1:]:
                    later = later or {}
                    haystack = " ".join(str(later.get(k) or "")
                                        for k in ("if", "run")) + " ".join(
                        str(v) for v in (later.get("env") or {}).values())
                    if needle in haystack:
                        offset = text.find(str(step_id))
                        findings.append(Finding(
                            path, "token-mint", line_of(text, max(offset, 0)),
                            f"continue-on-error create-github-app-token "
                            f"(id: {step_id}) + a later read of its .outcome"))
                        break
    return findings


# --------------------------------------------------------------------------
# Promotion-prevention pass (FR-025)
# --------------------------------------------------------------------------
# research.md D1/D2: auto-update-spec-kit.yml IS a workflow_call-only
# published stage, and it is ALSO this feature's own declared consumer of
# the three shared composites, reached deliberately through its existing
# self-checkout convention -- not an accidental promotion. That is a real,
# reasoned exception, so it goes through the SAME waiver file every other
# exception in this gate does (single-home-waivers.json), stale-checked
# like any other, rather than a bespoke unconditional skip with no count
# to keep it honest if this file ever reaches into _shared/ a fourth,
# unintended way.
def check_promotion(root="."):
    findings = []
    for path in _relativize(root, published_stages(root)):
        text = read(root, path)
        for m in SHARED_REF_RE.finditer(text):
            findings.append(Finding(path, "promotion", line_of(text, m.start()),
                                    m.group(0)))
    actions_base = os.path.join(root, ACTIONS_DIR)
    if os.path.isdir(actions_base):
        for name in sorted(os.listdir(actions_base)):
            if name.startswith("_"):
                continue
            for fname in ("action.yml", "action.yaml"):
                candidate = os.path.join(ACTIONS_DIR, name, fname)
                if not os.path.isfile(os.path.join(root, candidate)):
                    continue
                text = read(root, candidate)
                for m in SHARED_REF_RE.finditer(text):
                    findings.append(Finding(candidate, "promotion",
                                            line_of(text, m.start()), m.group(0)))
    return findings


ALL_CHECKS = {
    "orphan-reset": check_orphan_reset,
    "failure-issue": check_failure_issue,
    "verdict-shape": check_verdict_shape,
    "token-mint": check_token_mint,
    "promotion": check_promotion,
}


# --------------------------------------------------------------------------
# Waivers -- same shape as stage-invariant-waivers.json (Gate 31)
# --------------------------------------------------------------------------
REQUIRED_WAIVER_FIELDS = ("file", "check", "pattern", "count", "reason", "issue")


def load_waivers(root="."):
    path = os.path.join(root, *WAIVERS_PATH.split("/"))
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError) as exc:
        return [], [f"{WAIVERS_PATH} could not be read ({exc}). A waiver file "
                    f"that does not parse would otherwise silently waive "
                    f"nothing while looking like a register."]
    waivers = data.get("waivers") if isinstance(data, dict) else data
    if not isinstance(waivers, list):
        return [], [f'{WAIVERS_PATH} must contain a "waivers" list.']
    return waivers, []


def check_waiver_shape(waivers):
    out = []
    for index, waiver in enumerate(waivers):
        where = f"{WAIVERS_PATH} entry {index}"
        if not isinstance(waiver, dict):
            out.append(f"{where} is not an object.")
            continue
        missing = [f for f in REQUIRED_WAIVER_FIELDS if not waiver.get(f)]
        if missing:
            out.append(f"{where} ({waiver.get('file', '?')}) is missing "
                       f"{', '.join(missing)}.")
            continue
        if waiver["check"] not in CHECK_NAMES:
            out.append(f"{where} waives check {waiver['check']!r}, which is "
                       f"not one of {', '.join(CHECK_NAMES)}.")
            continue
        try:
            re.compile(waiver["pattern"])
        except re.error as exc:
            out.append(f"{where} has an invalid pattern {waiver['pattern']!r}: {exc}")
        if not isinstance(waiver["count"], int):
            out.append(f"{where} count must be an integer, got {waiver['count']!r}.")
    return out


def apply_waivers(findings, waivers):
    failures_local = []
    waived = set()
    for index, waiver in enumerate(waivers):
        where = f"{WAIVERS_PATH} entry {index}"
        pattern = re.compile(waiver["pattern"])
        matched = [f for f in findings
                   if f.path == waiver["file"] and f.check == waiver["check"]
                   and pattern.search(f.text)]
        if not matched:
            failures_local.append(
                f"{where} waives {waiver['check']} in {waiver['file']} with "
                f"pattern {waiver['pattern']!r}, and nothing matches it any "
                f"more. Remove the waiver.")
            continue
        if len(matched) != waiver["count"]:
            direction = "MORE" if len(matched) > waiver["count"] else "FEWER"
            failures_local.append(
                f"{where} declares {waiver['count']} finding(s) of "
                f"{waiver['check']} in {waiver['file']}, but {len(matched)} "
                f"match -- {direction} than granted.")
            continue
        waived.update(id(f) for f in matched)
    return [f for f in findings if id(f) not in waived], failures_local


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------
def evaluate(root="."):
    findings = []
    hard_failures = []

    subjects = workflow_files(root)
    if not subjects:
        hard_failures.append("no .github/workflows/*.yml files discovered -- "
                             "this gate is about to check nothing.")

    for check, home in DECLARED_HOMES.items():
        if not os.path.isfile(os.path.join(root, *home.split("/"))):
            hard_failures.append(f"declared home for {check!r} ({home}) does "
                                 f"not exist on disk.")

    if hard_failures:
        return findings, hard_failures

    for check, fn in ALL_CHECKS.items():
        findings.extend(fn(root))

    waivers, waiver_load_failures = load_waivers(root)
    hard_failures.extend(waiver_load_failures)
    if not waiver_load_failures:
        hard_failures.extend(check_waiver_shape(waivers))
    if not hard_failures:
        findings, waiver_failures = apply_waivers(findings, waivers)
        hard_failures.extend(waiver_failures)

    return findings, hard_failures


def report(findings, hard_failures):
    for msg in hard_failures:
        fail(f"verify-single-home-idioms: {msg}")
    for f in findings:
        home = DECLARED_HOMES.get(f.check, "(promotion: no single home -- "
                                            "an internal helper must not be "
                                            "resolved from a published surface)")
        fail(f"verify-single-home-idioms: {f.path}:{f.line}: {f.check} "
            f"({f.text}) -- see {home}")


# --------------------------------------------------------------------------
# Byte-identity check (FR-009) -- the shipped script against real fixtures
# --------------------------------------------------------------------------
BASH = None

VERDICT_FIXTURES = [
    (["fail-infra", "abc123", "WING_COMMANDER_AUTO_RELEASE_E2E_REPO is unset",
      "a repository variable set to OWNER/NAME of a pre-onboarded test repository",
      "unset", "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "WING_COMMANDER_AUTO_RELEASE_E2E_REPO is unset",
      "expected": "a repository variable set to OWNER/NAME of a pre-onboarded test repository",
      "observed": "unset", "evidence_url": "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}),
    (["fail-infra", "abc123", "WING_COMMANDER_AUTO_RELEASE_E2E_REPO shape",
      "OWNER/NAME", "badvalue", "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "WING_COMMANDER_AUTO_RELEASE_E2E_REPO shape",
      "expected": "OWNER/NAME", "observed": "badvalue",
      "evidence_url": "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}),
    (["fail-infra", "abc123", "WING_COMMANDER_AUTO_RELEASE_E2E_REPO names this repository",
      "a separate, dedicated, pre-onboarded test repository", "owner/repo",
      "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "WING_COMMANDER_AUTO_RELEASE_E2E_REPO names this repository",
      "expected": "a separate, dedicated, pre-onboarded test repository",
      "observed": "owner/repo", "evidence_url": "WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}),
    (["fail-infra", "abc123", "wing-commander App installation on the test repository",
      "installed on the test repository with Contents/Issues/Pull requests read-write",
      "token mint failed", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "wing-commander App installation on the test repository",
      "expected": "installed on the test repository with Contents/Issues/Pull requests read-write",
      "observed": "token mint failed", "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "test repository reachability",
      "gh repo view succeeds and reports a default branch",
      "unreachable, or has no default branch", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "test repository reachability",
      "expected": "gh repo view succeeds and reports a default branch",
      "observed": "unreachable, or has no default branch", "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "cloning the test repository",
      "a clone over the scoped App token succeeds",
      "fatal: could not read Username", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "cloning the test repository",
      "expected": "a clone over the scoped App token succeeds",
      "observed": "fatal: could not read Username", "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "resetting the test repository default branch",
      "a force-push of the reset branch succeeds", "! [remote rejected]", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "resetting the test repository default branch",
      "expected": "a force-push of the reset branch succeeds",
      "observed": "! [remote rejected]", "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "resolving SPECKIT_SUPPORTED_VERSION",
      "a SPECKIT_SUPPORTED_VERSION line in .github/actions/wing-commander-preflight/action.yml at the verified head",
      "no such line matched", "abc123"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "resolving SPECKIT_SUPPORTED_VERSION",
      "expected": "a SPECKIT_SUPPORTED_VERSION line in .github/actions/wing-commander-preflight/action.yml at the verified head",
      "observed": "no such line matched", "evidence_url": "abc123"}),
    (["fail-infra", "abc123", "scaffolding the test repository",
      "uvx available on the runner", "uvx not found", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "scaffolding the test repository",
      "expected": "uvx available on the runner", "observed": "uvx not found",
      "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "specify init in the test repository",
      "specify init exits 0", "error: could not resolve version", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "specify init in the test repository",
      "expected": "specify init exits 0", "observed": "error: could not resolve version",
      "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "pushing the scaffolded fixture",
      "a force-push of the scaffold succeeds", "! [remote rejected] main -> main", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "pushing the scaffolded fixture",
      "expected": "a force-push of the scaffold succeeds",
      "observed": "! [remote rejected] main -> main", "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "creating the kickoff issue",
      "gh issue create succeeds", "HTTP 403: Forbidden", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "creating the kickoff issue",
      "expected": "gh issue create succeeds", "observed": "HTTP 403: Forbidden",
      "evidence_url": "owner/repo"}),
    (["fail-infra", "abc123", "labelling the kickoff issue spec-request",
      "the spec-request label exists and gh issue edit succeeds",
      "HTTP 404: Not Found", "owner/repo"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "labelling the kickoff issue spec-request",
      "expected": "the spec-request label exists and gh issue edit succeeds",
      "observed": "HTTP 404: Not Found", "evidence_url": "owner/repo"}),
    (["fail-timeout", "abc123", "end-to-end run reaching a terminal state",
      "closed with stage:done, or stage:stalled, within the poll budget",
      "still open with labels [] after 6900s", "https://github.com/owner/repo/issues/1"],
     {"outcome": "fail-timeout", "verified_head": "abc123",
      "failing_check": "end-to-end run reaching a terminal state",
      "expected": "closed with stage:done, or stage:stalled, within the poll budget",
      "observed": "still open with labels [] after 6900s",
      "evidence_url": "https://github.com/owner/repo/issues/1"}),
    (["pass", "abc123", "", "", "", "https://github.com/owner/repo/issues/1"],
     {"outcome": "pass", "verified_head": "abc123", "failing_check": None,
      "expected": None, "observed": None,
      "evidence_url": "https://github.com/owner/repo/issues/1"}),
    (["fail-infra", "abc123", "verify-e2e produced no verdict",
      "a JSON verdict from verify-e2e on every path",
      "the job stopped before any step wrote one (job result: failure)",
      "https://github.com/owner/repo/actions/runs/999"],
     {"outcome": "fail-infra", "verified_head": "abc123",
      "failing_check": "verify-e2e produced no verdict",
      "expected": "a JSON verdict from verify-e2e on every path",
      "observed": "the job stopped before any step wrote one (job result: failure)",
      "evidence_url": "https://github.com/owner/repo/actions/runs/999"}),
]


def check_verdict_byte_identity(root="."):
    global BASH
    script = os.path.join(root, *VERDICT_SCRIPT.split("/"))
    if not os.path.isfile(script):
        return [f"{VERDICT_SCRIPT} does not exist -- cannot run the "
                f"byte-identity check against it."]
    if BASH is None:
        BASH = resolve_bash()
    out = []
    for args, expected in VERDICT_FIXTURES:
        proc = subprocess.run([BASH, script] + args, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            out.append(f"auto-release-verdict.sh exited {proc.returncode} for "
                       f"args {args!r}: {proc.stderr.strip()}")
            continue
        try:
            got = json.loads(proc.stdout)
        except ValueError:
            out.append(f"auto-release-verdict.sh did not print valid JSON for "
                       f"args {args!r}: {proc.stdout!r}")
            continue
        if got != expected:
            out.append(f"auto-release-verdict.sh output differs for args "
                       f"{args!r}: got {got!r}, want {expected!r}")
    return out


# --------------------------------------------------------------------------
# --self-test
# --------------------------------------------------------------------------
def _write(root, rel, content):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def _clean_tree(root):
    _write(root, DECLARED_HOMES["orphan-reset"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        checkout --quiet --orphan\n"
          "        git rm -rq --cached\n"
          "        find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf\n")
    _write(root, DECLARED_HOMES["failure-issue"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        gh label create \"$L\" --force\n"
          "        gh issue list --label \"$L\" --state open --json number "
          "--jq '.[0].number // empty'\n")
    _write(root, DECLARED_HOMES["verdict-shape"],
          "#!/usr/bin/env bash\n"
          "jq -n '{outcome:$outcome, verified_head:$head, "
          "failing_check:$f, expected:$e, observed:$o, evidence_url:$u}'\n")
    _write(root, DECLARED_HOMES["token-mint"],
          "runs:\n  using: composite\n  steps:\n"
          "    - id: mint\n      continue-on-error: true\n"
          "      uses: actions/create-github-app-token@v3\n"
          "    - shell: bash\n      env:\n"
          "        OUTCOME: ${{ steps.mint.outcome }}\n"
          "      run: echo hi\n")
    _write(root, ".github/workflows/harmless.yml",
          "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
          "      - run: echo hi\n")


def selftest_clean_tree_passes():
    case = "clean tree passes"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif findings:
            fail(f"[{case}] unexpected finding(s): {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_third_paste_fails(check_key, paste_path, paste_content):
    case = f"a third paste of {check_key} fails, naming the shared home"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        _write(tmp, paste_path, paste_content)
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings if f.check == check_key and f.path == paste_path]
        if not hits:
            fail(f"[{case}] expected a {check_key} finding at {paste_path}, "
                f"got: {findings}")
        else:
            note(f"[{case}] passed ({hits[0].path}:{hits[0].line})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_waived_copy_passes():
    case = "a waived copy passes"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        paste_path = ".github/workflows/third.yml"
        _write(tmp, paste_path,
              "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
              "      - shell: bash\n        run: |\n"
              "          checkout --quiet --orphan\n"
              "          git rm -rq --cached\n"
              "          find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf\n")
        _write(tmp, WAIVERS_PATH, json.dumps({"waivers": [
            {"file": paste_path, "check": "orphan-reset",
             "pattern": re.escape(ORPHAN_FRAGMENTS[0]), "count": 1,
             "issue": "#326", "reason": "fixture"}]}))
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif findings:
            fail(f"[{case}] waiver did not suppress the finding: {findings}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_stale_waiver_fails():
    case = "a stale waiver (zero matches) fails"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        _write(tmp, WAIVERS_PATH, json.dumps({"waivers": [
            {"file": ".github/workflows/nonexistent-anymore.yml",
             "check": "orphan-reset", "pattern": "checkout --quiet --orphan",
             "count": 1, "issue": "#326", "reason": "fixture"}]}))
        _, hard = evaluate(tmp)
        if not hard:
            fail(f"[{case}] expected a hard failure for a waiver matching "
                f"nothing, got none")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_promotion_fails():
    case = "a published stage or a non-underscore composite resolving _shared/ fails"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        _write(tmp, ".github/workflows/published-stage.yml",
              "on:\n  workflow_call: {}\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
              "    steps:\n      - uses: ./.github/actions/_shared/orphan-branch-reset\n")
        _write(tmp, ".github/actions/some-public-composite/action.yml",
              "runs:\n  using: composite\n  steps:\n"
              "    - run: bash .github/actions/_shared/count-turns.sh\n"
              "      shell: bash\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        stage_hit = any(f.check == "promotion" and f.path == ".github/workflows/published-stage.yml"
                        for f in findings)
        composite_hit = any(f.check == "promotion" and
                            f.path == ".github/actions/some-public-composite/action.yml"
                            for f in findings)
        if not stage_hit:
            fail(f"[{case}] published stage resolving _shared/ was not caught")
        if not composite_hit:
            fail(f"[{case}] non-underscore composite resolving _shared/ was not caught")
        if stage_hit and composite_hit:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_missing_declared_home_fails_loud():
    case = "a missing declared home fails loudly, not silently"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        os.remove(os.path.join(tmp, *DECLARED_HOMES["orphan-reset"].split("/")))
        _, hard = evaluate(tmp)
        if not hard:
            fail(f"[{case}] expected a hard failure when a declared home is "
                f"missing, got none")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_selftest():
    use_utf8_stdout()
    selftest_clean_tree_passes()
    selftest_third_paste_fails(
        "orphan-reset", ".github/workflows/third-orphan.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          checkout --quiet --orphan\n"
        "          git rm -rq --cached\n"
        "          find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf\n")
    selftest_third_paste_fails(
        "failure-issue", ".github/workflows/third-failure-issue.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          gh label create \"third:failed\" --color B60205 --force\n"
        "          gh issue list --label \"third:failed\" --state open "
        "--json number --jq '.[0].number // empty'\n")
    selftest_third_paste_fails(
        "verdict-shape", ".github/workflows/third-verdict.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          jq -n --arg outcome ok --arg head h --arg fc f --arg e e "
        "--arg o o --arg u u '{outcome:$outcome, verified_head:$head, "
        "failing_check:$fc, expected:$e, observed:$o, evidence_url:$u}'\n")
    selftest_third_paste_fails(
        "token-mint", ".github/workflows/third-token.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - id: mint\n        continue-on-error: true\n"
        "        uses: actions/create-github-app-token@v3\n"
        "      - shell: bash\n        env:\n"
        "          OUTCOME: ${{ steps.mint.outcome }}\n"
        "        run: echo hi\n")
    selftest_waived_copy_passes()
    selftest_stale_waiver_fails()
    selftest_promotion_fails()
    selftest_missing_declared_home_fails_loud()
    print(f"verify-single-home-idioms --self-test: {len(failures)} failure(s).")
    return 1 if failures else 0


# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    use_utf8_stdout()

    if args.self_test:
        sys.exit(run_selftest())

    findings, hard_failures = evaluate(".")
    report(findings, hard_failures)

    byte_identity_failures = check_verdict_byte_identity(".")
    for msg in byte_identity_failures:
        fail(f"verify-single-home-idioms: byte-identity: {msg}")

    total = len(findings) + len(hard_failures) + len(byte_identity_failures)
    print(f"verify-single-home-idioms: {total} failure(s).")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
