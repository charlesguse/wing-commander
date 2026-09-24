#!/usr/bin/env python3
"""Gate 60 -- each cross-workflow idiom this feature consolidated has
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
already been taken by verify-auto-release-report.py (#325/#335), so this
gate first became Gate 53 -- the next number free in this branch's own
tree, per T001's rule of verifying baseline facts against the real tree
rather than a claim about it. By the time of the maintainer's review of
PR #347, spec 046's PR #341 had registered Gates 53-58 on `main` and
spec 048's PR #342 had taken 59, so this gate moved again, to Gate 60 --
the next number actually free.

SIX CHECKS, per contracts/single-home-gate.md (plus a spec 052 addition)
-----------------------------------------------
1. orphan-reset: literal co-occurrence, in one file, of the three
   fragments that only appear together in the orphan-branch-reset idiom's
   own shell. File-wide scope is safe here -- verified empirically
   against the real tree that none of these three fragments appears
   anywhere outside the declared composite once this feature's own
   refactor lands.

1b. extraheader-refresh (spec 052, second maintainer review of PR #407,
    FR-020/FR-021 hole (a) -- "add the extraheader/set-url origin idiom to
    Gate 60 as the one-home check CLAUDE.md asks for"): co-occurrence, in
    one file, of the `git remote set-url origin` fragment and a regex
    match for the extraheader-unset idiom unique to
    wing-commander-refresh-remote's own shell -- clearing
    actions/checkout@v5's persisted `http.https://github.com/.extraheader`
    entry before rewriting the remote URL (research.md D2's correction).
    Verified empirically that "git remote set-url origin" alone, without
    the extraheader-clear fragment, appears in two unrelated legitimate
    idioms already (orphan-branch-reset, a test script), so co-occurrence
    -- not the bare set-url fragment -- is what this check keys on. The
    extraheader-unset side matches by regex, not literal string (third
    maintainer review of PR #407, FR-020/FR-021 hole (b)): the original
    literal fragment required `--local` and double-quoting the config key
    exactly as wing-commander-refresh-remote spells it, so `git config
    --unset-all http.https://github.com/.extraheader` (no `--local`, no
    quotes) -- the same idiom, a different but equally valid spelling --
    evaded it.

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

5. mode-tag-shape: specs/054-e2e-container-coverage originally threaded
   `mode`/`container_image_configured` onto the verdict by piping every
   one of `auto-release-verdict.sh`'s 12 call sites through a second,
   pasted `jq --arg mode "$MODE" '. + {mode:$mode} + (...)'` instead of
   folding the two fields into the shared script itself -- undetected by
   the verdict-shape check above, since that pasted pipe carries none of
   the six field names it looks for. The mode-tagging jq now lives solely
   inside `auto-release-verdict.sh` (its `mode`/`container-image-
   configured` become two additional, optional positional arguments); this
   check scans for the `{mode:$<var>}` fragment (any jq variable name, not
   only the original paste's `$mode` -- #391 item 4, second review of #373:
   the literal `$mode` spelling let a pipe that renamed only the `--arg`
   binding, e.g. `--arg tag_mode "$MODE" '. + {mode:$tag_mode} + (...)'`,
   evade the check while keeping the same JSON shape) co-occurring with
   `container_image_configured` anywhere else, so a THIRD reappearance of
   the pasted shape is caught the same way a third verdict-shape paste is.

6. transcript-normalise (#572): the jq program that turns an agent
   execution transcript (one array, one object, NDJSON, concatenated
   documents) into one flat array -- `if type=="array" then .[] else .
   end` spliced over `jq -s` input. It was pasted into
   wing-commander-agent-verdict (#551) and then needed by count-turns.sh
   and wing-commander-metrics-summary too; it now lives solely in
   `_shared/normalise-transcript.sh`. Matched by regex, whitespace- and
   quote-tolerant. The per-document `then . else [.] end` wrap is a
   different, legitimate idiom and is not matched.

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
    # specs/056-stage-found-defect-filing, research.md D8: promoted out of
    # _shared/ and given the wing-commander- prefix because a published
    # composite (wing-commander-stage-findings) is now a second, deliberate
    # caller -- Gate 60's own promotion-prevention check already forbids a
    # published composite from resolving a _shared/ path.
    "failure-issue": ".github/actions/wing-commander-durable-failure-issue/action.yml",
    "verdict-shape": ".github/actions/_shared/auto-release-verdict.sh",
    "token-mint": ".github/actions/_shared/scoped-app-token/action.yml",
    "mode-tag-shape": ".github/actions/_shared/auto-release-verdict.sh",
    # spec 052, second maintainer review of PR #407 (FR-020/FR-021 hole (a)):
    # the post-agent authenticated-remote refresh's own idiom -- clearing
    # actions/checkout@v5's persisted extraheader before rewriting the
    # remote URL, without which the rewrite is a silent no-op (research.md
    # D2's correction) -- gets the same one-home check every other idiom in
    # this gate does, so a rogue THIRD paste (e.g. a "fix" applied directly
    # at a call site instead of to the shared composite) is caught.
    "extraheader-refresh": ".github/actions/wing-commander-refresh-remote/action.yml",
    # specs/056-stage-found-defect-filing, research.md D9: pr-conversation.yml's
    # own header comment calls this "the ONE shared mechanism every
    # SpinOffArtifact posts through" -- a second caller (wing-commander-
    # stage-findings) makes a structural one-home check worth having, the
    # same way check_failure_issue already protects durable-failure-issue.
    "outstanding-task-item": ".github/actions/wing-commander-outstanding-task-item/action.yml",
    # specs/056-stage-found-defect-filing, research.md D10/D13: the
    # proposal-validate-fingerprint-file-cross-link sequence must not be
    # re-pasted into a stage workflow directly -- FR-032.
    "stage-findings": ".github/actions/wing-commander-stage-findings/action.yml",
    # specs/057-autonomous-board-loop, research.md D5 (T027): the
    # small-change file/line-count formula. pr-conversation.yml's own call
    # site is NOT yet repointed at this composite (T021, still open -- see
    # the waiver below and issue #408) -- board-loop.yml is, and this check
    # exists so a THIRD site cannot paste the formula a second, independent
    # time while T021 is outstanding.
    "size-path-backstop": ".github/actions/wing-commander-size-path-backstop/action.yml",
    # specs/057-autonomous-board-loop, research.md D14 (T056): the
    # dispatch-then-correlate-by-attempt-token-then-wait-to-terminal idiom.
    # auto-release.yml's own dispatch-release job is NOT yet repointed at
    # this composite (T054, still open -- see the waiver below and issue
    # #408); board-loop.yml's prove step is, and this check exists so a
    # THIRD site cannot paste the correlate-and-poll loop a second,
    # independent time while T054 is outstanding.
    "dispatch-and-wait": ".github/actions/wing-commander-dispatch-and-wait/action.yml",
    # issue #462 (code review of #451): the kill-switch/stop-request
    # recheck -- paginate the issue's own comments, hand them to
    # board_stop_check.find_stop_request(), and `gh run cancel` whatever
    # it names -- was pasted near-verbatim into all six of board-loop.yml's
    # jobs. board_stop_check.py's own docstring already called
    # find_stop_request() "the reusable check every job's own... step also
    # performs," but never the surrounding gh/bash orchestration around it;
    # this check is the structural scan that catches a THIRD paste the way
    # every other idiom in this gate already does.
    "board-stop-check": ".github/actions/wing-commander-board-stop-check/action.yml",
    # #572: the transcript normaliser. count-turns.sh,
    # wing-commander-agent-verdict and wing-commander-metrics-summary all
    # call it; a fourth inline copy is what this check catches.
    "transcript-normalise": ".github/actions/_shared/normalise-transcript.sh",
}
CHECK_NAMES = tuple(DECLARED_HOMES) + ("promotion",)

ORPHAN_FRAGMENTS = (
    "checkout --quiet --orphan",
    "git rm -rq --cached",
    "find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf",
)
EXTRAHEADER_FRAGMENTS = (
    'git config --local --unset-all "http.https://github.com/.extraheader"',
    "git remote set-url origin",
)
# Third maintainer review of PR #407 (FR-020/FR-021 hole (b)): the literal
# fragment above depends on an exact spelling -- `--local` present and the
# config key double-quoted. `git config --unset-all
# http.https://github.com/.extraheader` (no `--local`, no quotes) is the
# same idiom and evaded the literal-string check entirely. This regex
# matches the unset-all fragment regardless of `--local` and quoting; the
# `git remote set-url origin` fragment needs no such tolerance (it has no
# optional flag or quoting variant in this repo's shell style).
EXTRAHEADER_UNSET_RE = re.compile(
    r'git config(?:\s+--local)?\s+--unset-all\s+"?'
    r'http\.https://github\.com/\.extraheader"?')
LABEL_CREATE_RE = re.compile(r"gh label create\b[^\n]*--force")
ISSUE_LOOKUP_RE = re.compile(
    r"gh issue list\b[^\n]*--label\b[^\n]*--state open\b[^\n]*"
    r"--json number\b[^\n]*--jq\b[^\n]*\.\[0\]\.number // empty")
OUTSTANDING_TASK_RE = re.compile(r'gh issue comment\b[^\n]*"- \[ \] ')
SIZE_PATH_BACKSTOP_FRAGMENT = r'select(test("^[+-]") and (test("^(\\+\\+\\+|---)") | not))'
# specs/057-autonomous-board-loop research.md D14: correlating a dispatched
# run by an attempt-token carried in its own run-name -- never by recency --
# and then polling it to a terminal status. All four fragments together are
# the idiom; any subset alone is ordinary gh-CLI usage (release.yml's
# run-name carries "[attempt:" and nothing else here, and is not a second
# copy). The `--json` field list is matched as displayTitle,createdAt --
# specifically the composite's own correlate-by-recency-among-same-titled-
# rows field set, not just "a gh run list call that reads displayTitle" --
# because specs/060-self-redrive-concurrency research.md D4's
# directed_proof_group_busy() reads a databaseId/displayTitle/status trio
# (an occupancy check, board_stand_down.py's own idiom generalized, never a
# run's recency) and board-loop.yml's own select job already reads
# createdAt for an unrelated reason (issue listing), so createdAt alone
# would false-positive on the real tree even before this feature.
DISPATCH_WAIT_FRAGMENTS = (
    "gh workflow run",
    "gh run list --workflow=",
    "displayTitle,createdAt",
    "[attempt:",
)
VERDICT_FIELDS = ("outcome", "verified_head", "failing_check", "expected",
                  "observed", "evidence_url")
# issue #462: `gh run cancel` alone is ordinary gh-CLI usage that also
# appears in pr-conversation.yml's own (unrelated) stop procedure, so
# co-occurrence with the other two fragments -- both unique to this
# idiom's own shell -- is what keeps this check from false-positiving
# there, the same reasoning check_dispatch_and_wait already documents for
# its own fragment set.
BOARD_STOP_CHECK_FRAGMENTS = (
    "from board_stop_check import find_stop_request",
    "gh run cancel",
    "board-stop-check-comments.json",
)
# #572: the splice step of the transcript normaliser. `.[]` in the
# then-branch is what distinguishes it from the per-document
# `if type=="array" then . else [.] end` wrap used by fallback reads.
TRANSCRIPT_NORMALISE_RE = re.compile(
    r'if\s+type\s*==\s*["\']array["\']\s+then\s+\.\[\]\s+else\s+\.\s+end')
MODE_TAG_FRAGMENT_RE = re.compile(r"\{\s*mode\s*:\s*\$[A-Za-z_][A-Za-z0-9_]*\s*\}")
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
# Check 1b: extraheader-refresh (file-wide literal co-occurrence, spec 052)
# --------------------------------------------------------------------------
def check_extraheader_refresh(root="."):
    home = DECLARED_HOMES["extraheader-refresh"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        m = EXTRAHEADER_UNSET_RE.search(text)
        if m and EXTRAHEADER_FRAGMENTS[1] in text:
            findings.append(Finding(path, "extraheader-refresh", line_of(text, m.start()),
                                    m.group(0)))
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
# Check: outstanding-task-item (per-step, single-fragment)
# --------------------------------------------------------------------------
def check_outstanding_task_item(root="."):
    home = DECLARED_HOMES["outstanding-task-item"]
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
                if OUTSTANDING_TASK_RE.search(run):
                    offset = text.find(run.splitlines()[0]) if run.splitlines() else 0
                    findings.append(Finding(
                        path, "outstanding-task-item",
                        line_of(text, max(offset, 0)),
                        'gh issue comment ... "- [ ] ..."'))
    return findings


# --------------------------------------------------------------------------
# Check: stage-findings (file-wide co-occurrence of the fingerprint formula
# and the schema-validation call -- research.md D13)
# --------------------------------------------------------------------------
def check_stage_findings(root="."):
    home = DECLARED_HOMES["stage-findings"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        if "sha256" in text and "fingerprint_basis" in text and "validate_finding" in text:
            offset = text.find("fingerprint_basis")
            findings.append(Finding(
                path, "stage-findings", line_of(text, offset),
                "sha256(...) + fingerprint_basis + validate_finding co-occurrence"))
    return findings


# --------------------------------------------------------------------------
# Check: transcript-normalise (file-wide regex, #572)
# --------------------------------------------------------------------------
def check_transcript_normalise(root="."):
    home = DECLARED_HOMES["transcript-normalise"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        for m in TRANSCRIPT_NORMALISE_RE.finditer(text):
            findings.append(Finding(path, "transcript-normalise",
                                    line_of(text, m.start()), m.group(0)))
    return findings


# --------------------------------------------------------------------------
# Check: size-path-backstop (file-wide, the small-change file/line-count
# formula -- specs/057-autonomous-board-loop research.md D5)
# --------------------------------------------------------------------------
def check_size_path_backstop(root="."):
    home = DECLARED_HOMES["size-path-backstop"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        if SIZE_PATH_BACKSTOP_FRAGMENT in text:
            offset = text.index(SIZE_PATH_BACKSTOP_FRAGMENT)
            findings.append(Finding(
                path, "size-path-backstop", line_of(text, offset),
                SIZE_PATH_BACKSTOP_FRAGMENT))
    return findings


# --------------------------------------------------------------------------
# Check: dispatch-and-wait (file-wide co-occurrence of the correlate-by-
# attempt-token search and the dispatch that mints it --
# specs/057-autonomous-board-loop research.md D14)
# --------------------------------------------------------------------------
def check_dispatch_and_wait(root="."):
    home = DECLARED_HOMES["dispatch-and-wait"]
    # The home's whole directory, not just action.yml: a future fixture or
    # helper placed beside the composite is part of the one home, never a
    # second copy of the idiom.
    home_dir = home.rsplit("/", 1)[0] + "/"
    findings = []
    for path in all_subject_files(root):
        if path == home or path.startswith(home_dir):
            continue
        text = read(root, path)
        if all(fragment in text for fragment in DISPATCH_WAIT_FRAGMENTS):
            offset = text.find("gh run list --workflow=")
            findings.append(Finding(
                path, "dispatch-and-wait", line_of(text, max(offset, 0)),
                "gh workflow run + gh run list --workflow= + displayTitle + "
                "[attempt: co-occurrence"))
    return findings


# --------------------------------------------------------------------------
# Check: board-stop-check (file-wide co-occurrence of the find_stop_request
# import, the gh run cancel call, and the paginated-comments filename --
# issue #462)
# --------------------------------------------------------------------------
def check_board_stop_check(root="."):
    home = DECLARED_HOMES["board-stop-check"]
    # The home's whole directory, same reasoning as check_dispatch_and_wait:
    # a future fixture or helper placed beside the composite is part of the
    # one home, never a second copy of the idiom.
    home_dir = home.rsplit("/", 1)[0] + "/"
    findings = []
    for path in all_subject_files(root):
        if path == home or path.startswith(home_dir):
            continue
        text = read(root, path)
        if all(fragment in text for fragment in BOARD_STOP_CHECK_FRAGMENTS):
            offset = text.find(BOARD_STOP_CHECK_FRAGMENTS[0])
            findings.append(Finding(
                path, "board-stop-check", line_of(text, max(offset, 0)),
                "from board_stop_check import find_stop_request + gh run "
                "cancel + board-stop-check-comments.json co-occurrence"))
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
# Check 5: mode-tag-shape (file-wide, the pasted mode/container-image-
# configured tagging pipe -- see module docstring)
# --------------------------------------------------------------------------
def check_mode_tag_shape(root="."):
    home = DECLARED_HOMES["mode-tag-shape"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        for m in MODE_TAG_FRAGMENT_RE.finditer(text):
            window = text[max(0, m.start() - 200):m.start() + 400]
            if "container_image_configured" in window:
                findings.append(Finding(
                    path, "mode-tag-shape", line_of(text, m.start()),
                    "jq '. + {mode:$<var>} + (...container_image_configured...)'"))
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
                candidate = os.path.join(ACTIONS_DIR, name, fname).replace(os.sep, "/")
                if not os.path.isfile(os.path.join(root, candidate)):
                    continue
                text = read(root, candidate)
                for m in SHARED_REF_RE.finditer(text):
                    findings.append(Finding(candidate, "promotion",
                                            line_of(text, m.start()), m.group(0)))
    return findings


ALL_CHECKS = {
    "orphan-reset": check_orphan_reset,
    "extraheader-refresh": check_extraheader_refresh,
    "failure-issue": check_failure_issue,
    "outstanding-task-item": check_outstanding_task_item,
    "stage-findings": check_stage_findings,
    "size-path-backstop": check_size_path_backstop,
    "dispatch-and-wait": check_dispatch_and_wait,
    "board-stop-check": check_board_stop_check,
    "transcript-normalise": check_transcript_normalise,
    "verdict-shape": check_verdict_shape,
    "token-mint": check_token_mint,
    "mode-tag-shape": check_mode_tag_shape,
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
    _write(root, DECLARED_HOMES["outstanding-task-item"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        gh issue comment \"$ISSUE_NUMBER\" --body \"- [ ] "
          "$PHRASE — $ARTIFACT_URL\"\n")
    _write(root, DECLARED_HOMES["stage-findings"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        python3 - <<'PYEOF'\n"
          "        fp = sha256(stage + fingerprint_basis['file_path'])\n"
          "        ok, reason = validate_finding(item)\n"
          "        PYEOF\n")
    _write(root, DECLARED_HOMES["size-path-backstop"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        select(test(\"^[+-]\") and (test(\"^(\\\\+\\\\+\\\\+|---)\") | not))\n")
    _write(root, DECLARED_HOMES["dispatch-and-wait"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        gh workflow run \"$WORKFLOW_FILE\" -f "
          "\"attempt-token=${ATTEMPT_TOKEN}\"\n"
          "        gh run list --workflow=\"$WORKFLOW_FILE\" --json "
          "databaseId,displayTitle,createdAt,url -L 20\n"
          "        case \"$row_title\" in *\"[attempt:${ATTEMPT_TOKEN}]\"*) ;; "
          "*) continue ;; esac\n")
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
    _write(root, DECLARED_HOMES["extraheader-refresh"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        git config --local --unset-all "
          "\"http.https://github.com/.extraheader\" 2>/dev/null || true\n"
          "        git remote set-url origin "
          "\"https://x-access-token:${TOKEN}@github.com/repo.git\"\n")
    _write(root, DECLARED_HOMES["board-stop-check"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        gh api \"repos/$GITHUB_REPOSITORY/issues/$N/comments\" "
          "--paginate --jq '.[]' | jq -s '.' > "
          "\"$RUNNER_TEMP/board-stop-check-comments.json\"\n"
          "        # from board_stop_check import find_stop_request\n"
          "        GH_TOKEN=\"$CANCEL_TOKEN\" gh run cancel "
          "\"$stop_run_id\" -R \"$GITHUB_REPOSITORY\" 2>/dev/null || true\n")
    _write(root, DECLARED_HOMES["transcript-normalise"],
          "#!/usr/bin/env bash\n"
          "jq -cs 'map(if type==\"array\" then .[] else . end) "
          "| map(objects)' \"$1\"\n")
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
        "extraheader-refresh", ".github/workflows/third-extraheader.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          git config --local --unset-all "
        "\"http.https://github.com/.extraheader\" 2>/dev/null || true\n"
        "          git remote set-url origin "
        "\"https://x-access-token:${TOKEN}@github.com/repo.git\"\n")
    # Third maintainer review of PR #407 (FR-020/FR-021 hole (b)): the same
    # idiom, spelled without `--local` and without quoting the config key,
    # must be caught too -- not only the exact spelling the composite uses.
    selftest_third_paste_fails(
        "extraheader-refresh", ".github/workflows/third-extraheader-bare.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          git config --unset-all "
        "http.https://github.com/.extraheader 2>/dev/null || true\n"
        "          git remote set-url origin "
        "\"https://x-access-token:${TOKEN}@github.com/repo.git\"\n")
    selftest_third_paste_fails(
        "failure-issue", ".github/workflows/third-failure-issue.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          gh label create \"third:failed\" --color B60205 --force\n"
        "          gh issue list --label \"third:failed\" --state open "
        "--json number --jq '.[0].number // empty'\n")
    selftest_third_paste_fails(
        "outstanding-task-item", ".github/workflows/third-outstanding-task.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          gh issue comment \"$N\" --body \"- [ ] a third paste "
        "\u2014 $URL\"\n")
    selftest_third_paste_fails(
        "stage-findings", ".github/workflows/third-stage-findings.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          python3 - <<'PYEOF'\n"
        "          fp = sha256(stage + fingerprint_basis['file_path'])\n"
        "          ok, reason = validate_finding(item)\n"
        "          PYEOF\n")
    selftest_third_paste_fails(
        "size-path-backstop", ".github/workflows/third-size-path-backstop.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          jq '[.[] | select(test(\"^[+-]\") and "
        "(test(\"^(\\\\+\\\\+\\\\+|---)\") | not))] | length'\n")
    selftest_third_paste_fails(
        "dispatch-and-wait", ".github/workflows/third-dispatch-and-wait.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          gh workflow run other.yml -f \"attempt-token=${token}\"\n"
        "          rows=\"$(gh run list --workflow=other.yml --json "
        "databaseId,displayTitle,createdAt,url -L 20)\"\n"
        "          case \"$row_title\" in *\"[attempt:${token}]\"*) ;; "
        "*) continue ;; esac\n")
    selftest_third_paste_fails(
        "board-stop-check", ".github/workflows/third-board-stop-check.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          gh api \"repos/$GITHUB_REPOSITORY/issues/$N/comments\" "
        "--paginate --jq '.[]' | jq -s '.' > "
        "\"$RUNNER_TEMP/board-stop-check-comments.json\"\n"
        "          # from board_stop_check import find_stop_request\n"
        "          GH_TOKEN=\"$CANCEL_TOKEN\" gh run cancel "
        "\"$stop_run_id\" -R \"$GITHUB_REPOSITORY\" 2>/dev/null || true\n")
    selftest_third_paste_fails(
        "transcript-normalise",
        ".github/actions/wing-commander-third/action.yml",
        "runs:\n  using: composite\n  steps:\n"
        "    - shell: bash\n      run: |\n"
        "        jq -cs 'map(if type==\"array\" then .[] else . end)' "
        "\"$T\" > \"$OUT\"\n")
    # Re-spaced, with the jq program in a workflow instead of a composite.
    selftest_third_paste_fails(
        "transcript-normalise", ".github/workflows/third-normalise.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          jq -s '[.[] | if type == \"array\"  then .[] else . end]' "
        "\"$T\"\n")
    selftest_third_paste_fails(
        "verdict-shape", ".github/workflows/third-verdict.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          jq -n --arg outcome ok --arg head h --arg fc f --arg e e "
        "--arg o o --arg u u '{outcome:$outcome, verified_head:$head, "
        "failing_check:$fc, expected:$e, observed:$o, evidence_url:$u}'\n")
    selftest_third_paste_fails(
        "mode-tag-shape", ".github/workflows/third-mode-tag.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          bash .github/actions/_shared/auto-release-verdict.sh "
        "\"fail-infra\" \"$HEAD_SHA\" \"c\" \"e\" \"o\" \"$E2E_REPO\" | "
        "jq --arg mode \"$MODE\" '. + {mode:$mode} + (if $mode == "
        "\"container\" then {container_image_configured: true} else {} end)'\n")
    # #391 item 4 (second review of #373): the same paste with only the jq
    # `--arg` binding renamed -- `$mode` becomes `$tag_mode` -- keeps the
    # identical JSON shape but evaded the literal-`$mode` regex.
    selftest_third_paste_fails(
        "mode-tag-shape", ".github/workflows/third-mode-tag-renamed-var.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          bash .github/actions/_shared/auto-release-verdict.sh "
        "\"fail-infra\" \"$HEAD_SHA\" \"c\" \"e\" \"o\" \"$E2E_REPO\" | "
        "jq --arg tag_mode \"$MODE\" '. + {mode:$tag_mode} + (if $tag_mode == "
        "\"container\" then {container_image_configured: true} else {} end)'\n")
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
