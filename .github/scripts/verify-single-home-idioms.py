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
   quote-tolerant, and tolerant of equivalent rewrites (#575): a
   parenthesised or reversed condition (`(type=="array")`,
   `"array"==type`), the test in an `elif` arm, and an optional or
   parenthesised splice (`.[]?`, `(.[])`). The per-document
   `then . else [.] end` wrap is a different, legitimate idiom and is
   not matched.

7. branch-advance-capture (specs/068-plan-tasks-branch-advance research.md
   R10): the "after"/"commits" branch-advance git plumbing -- co-occurrence,
   file-wide, of the refspec-form `git fetch origin "+refs/heads/$...` fetch
   (its `+` force-update prefix is what distinguishes it from several
   other, unrelated `git fetch origin "refs/heads/$..."` idioms elsewhere
   in the fleet) and a `..`-range `git rev-list --count "$..."` read
   (watchdog.yml's own since-created/head-sha arms use this shape too, but
   never alongside the refspec fetch, so co-occurrence -- not either
   fragment alone -- is what the declared home uniquely carries). Extracted
   from implement.yml's former inline step so implement, plan, and tasks
   share one copy (FR-011/FR-012).

8. gha-expr-evaluator (code review of #940): a gate script that
   evaluates a shipped `if:` itself instead of through
   `.github/scripts/wc_gha_expr.py`. Five gate scripts and a shared
   module each carried one (a Python `eval` of a transpiled expression,
   or a regex `==`/`!=` term parser split on `&&`), and none read `==`
   with GitHub's case-insensitive rule. Scans every `.github/scripts/**/*.py`, not the
   workflows: these copies live in gates, not in steps. Matched by any of
   three signs: `&&` replaced with Python's `and`; `eval(` sandboxed with
   `__builtins__`; or `.split("&&")` in a file that also compiles an
   `(==|!=)` alternation. A pattern-matching gate that only reads
   comparisons (verify-gate-24.py) splits on nothing and is not matched.

Plus a promotion-prevention pass (FR-025): every `workflow_call`-only
stage workflow and every non-underscore-prefixed composite action scanned
for any reference resolving into a `_shared/` path.

Plus a composite-checkout-order pass (maintainer review of #607, fold
leg-0 and leg-1; extended by fold leg-2, issue #757): every workflow
job's own step list scanned for a local `uses: ./...` step preceding
the `actions/checkout@` step that actually populates the directory it
resolves from -- a root-relative reference (`./.github/actions/...`)
needs a preceding checkout with no `path:` (the workspace root); a
sidecar-relative reference (e.g.
`./.wc-pristine-repo/.github/actions/...`) needs a preceding checkout
whose `with.path` matches that same first path segment -- an unrelated
root checkout does not satisfy it, and vice versa. Such a step cannot
resolve its action.yml from the not-yet-checked-out directory and fails
at run time, not gate time. Leg-2 also flags a job's path-scoped sidecar
checkout that precedes its own root checkout even with no local action
step involved: actions/checkout@v5's prepareExistingDirectory wipes the
sidecar directory when the root checkout runs after it.

Plus a shared-path-workdir pass (#889): a workflow `run:` step whose
effective `working-directory:` (its own, or its job's `defaults.run`) is
anything but the workspace root must not name a `.github/actions/_shared/`
helper by a bare repo-relative path -- that path then resolves inside the
other directory (auto-release.yml's scaffold step runs in the test
repository's clone, where no such helper exists), so the call fails only
on the error path it exists to report. Anchor it at `$GITHUB_WORKSPACE/`
instead.

Plus a substitution-fallback pass (#889, #959): a command substitution
whose body ends `|| echo ...` / `|| printf ...` -- in a workflow or
composite `run:`, or a `.github/actions/**/*.sh` script -- appends its
fallback to whatever the command printed before failing (jq's `[]`
then `[]` again). The one home for the fallback is the assignment:
`x="$(cmd)" || x='[]'`. The `[ ... ] && echo a || echo b` test ternary
is exempt; anything else safe is waived with its reason.

Waivers: `.github/scripts/single-home-waivers.json`, same shape as Gate
31's `stage-invariant-waivers.json` -- `{file, check, pattern, count,
issue, reason}`, stale-checked in both directions (`issue` -- open, or
null with a permanent marker -- is Gate 124's to check).

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
    # specs/074-serialized-fold-dispatch: the reset-to-empty-orphan-branch
    # fragment moved out of orphan-branch-reset/action.yml's own inline
    # shell into this plain script once fold-queue-ledger.sh needed the
    # same reset from inside its own retry loop (a bash script, which
    # cannot `uses:` a composite) -- see orphan-branch-empty-tree.sh.
    "orphan-reset": ".github/actions/_shared/orphan-branch-empty-tree.sh",
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
    # issue #462 (code review of #451), idiom updated by #085: the
    # kill-switch/stop-request recheck -- paginate the issue's own comments,
    # obtain a decision from board_stop_check.py's documented CLI (pipe a
    # payload into it), and `gh run cancel` whatever earlier run it names --
    # was pasted near-verbatim into all six of board-loop.yml's jobs.
    # board_stop_check.py's own docstring already called find_stop_request()
    # "the reusable check every job's own... step also performs," but never
    # the surrounding gh/bash orchestration around it; this check is the
    # structural scan that catches a THIRD paste the way every other idiom
    # in this gate already does.
    "board-stop-check": ".github/actions/wing-commander-board-stop-check/action.yml",
    # #572: the transcript normaliser. count-turns.sh,
    # wing-commander-agent-verdict and wing-commander-metrics-summary all
    # call it; a fourth inline copy is what this check catches.
    "transcript-normalise": ".github/actions/_shared/normalise-transcript.sh",
    # specs/068-plan-tasks-branch-advance research.md R10 (CLAUDE.md: "add
    # the 'single home' check to the nearest existing gate"): the
    # "after"/"commits" branch-advance git plumbing, extracted from
    # implement.yml's own former inline step so implement/plan/tasks share
    # one copy.
    "branch-advance-capture": ".github/actions/wing-commander-branch-advance/action.yml",
    # specs/062-lifecycle-review-gate T012/T015: the `gh api .../reviews
    # -f event=COMMENT` review-posting call. board-loop.yml's reviewer job
    # is repointed at this composite (T013); lifecycle-review-gate.yml's
    # `review` job (US1) is this check's reason to exist -- a second
    # caller landing with its own inline copy instead.
    "post-review-comment": ".github/actions/wing-commander-post-review-comment/action.yml",
    # specs/062-lifecycle-review-gate T028/T030: the review-finding
    # fingerprint formula (sha256("<issue>|<norm(title)>|<norm(file_path)>"))
    # board-loop.yml's out-of-scope filing step computed inline before this
    # extraction (T029). lifecycle-review-gate.yml's `disposition` job (US2,
    # T037) is this module's second caller -- the reason a structural check
    # is worth having, the same way check_post_review_comment protects
    # wing-commander-post-review-comment. Deliberately distinct from
    # wing-commander-stage-findings' own similarly-shaped
    # sha256(STAGE|norm(file_path)|norm(gate_or_artifact)) idiom (spec 056):
    # REVIEW_FINDING_FINGERPRINT_RE keys on the `issue_number` argument name
    # that formula never uses, so the two checks do not collide.
    "review-finding-fingerprint": ".github/scripts/wc_review_finding_fingerprint.py",
    # Code review of #940: the GitHub-expression evaluator every gate that
    # evaluates a shipped `if:` uses -- see check_gha_expr_evaluator.
    "gha-expr-evaluator": ".github/scripts/wc_gha_expr.py",
    # specs/113-gh-callsite-locator FR-011 (CLAUDE.md: "add the 'single home'
    # check to the nearest existing gate"): the one module that finds `gh`
    # call sites in a `run:` block. Gate 12 and Gate 28 import it; a script
    # growing a shell scanner of its own is what this check catches.
    "gh-callsite-locator": ".github/scripts/wc_gh_callsites.py",
    # specs/062-lifecycle-review-gate T031/T042: the append-tasks.md-
    # section/flip-stage/union-actor/commit+push fold sequence.
    # pr-conversation.yml's `act` job (T033) and lifecycle-review-gate.yml's
    # `disposition` job (T038) are this composite's two callers -- a THIRD,
    # independent paste of the sequence is what this check catches.
    "fold-commit": ".github/actions/wing-commander-fold-commit/action.yml",
    # specs/062-lifecycle-review-gate T034/T042: the re-read-tip/bump-
    # iteration/dispatch sequence. pr-conversation.yml's `dispatch-once` job
    # (T036) and lifecycle-review-gate.yml's `disposition` job (T038) are
    # this composite's two callers.
    "fold-dispatch": ".github/actions/wing-commander-fold-dispatch/action.yml",
    # specs/084-board-loop-single-home-idioms, issue #607: the marker-write
    # bootstrap (sys.path.insert + `from board_item_marker import
    # write_marker`) was pasted at 17 call sites across 6 board-loop.yml
    # jobs; this feature moved every site to a `board_item_marker.py`
    # command-line entrypoint. A re-paste of the old inline bootstrap at a
    # new site is what this check catches.
    "marker-write": ".github/scripts/board_item_marker.py",
    # specs/084-board-loop-single-home-idioms, issue #607: the PR-branch
    # resolution idiom (`gh pr view ... --json headRefName` plus the
    # `pr-number=`/`branch=` GITHUB_OUTPUT write) was pasted at both the
    # review and readiness jobs' own steps; this feature moved both to the
    # resolve-pr-branch composite. A re-paste of the old inline read at a
    # new site is what this check catches.
    "pr-branch": ".github/actions/_shared/resolve-pr-branch/action.yml",
}
CHECK_NAMES = tuple(DECLARED_HOMES) + ("promotion", "composite-checkout-order",
                                        "shared-path-workdir",
                                        "substitution-fallback")

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
POST_REVIEW_COMMENT_RE = re.compile(
    r'gh\s+api\b[^\n]*reviews\b[^\n]*-f\s+event=COMMENT')
# specs/062-lifecycle-review-gate T028/T030: keys on the `issue_number`
# argument name, which spec 056's own similarly-shaped
# sha256("{0}|{1}|{2}".format(STAGE, ...)) fingerprint idiom never uses.
REVIEW_FINDING_FINGERPRINT_RE = re.compile(
    r'hashlib\.sha256\(\s*"\{0\}\|\{1\}\|\{2\}"\.format\(\s*issue_number\b')
# specs/062-lifecycle-review-gate T031/T042: the actor-tolerant
# pending_re_review_from union this composite alone performs.
FOLD_COMMIT_RE = re.compile(
    r'\.pending_re_review_from\s*=\s*\(\(\(\.pending_re_review_from')
# specs/062-lifecycle-review-gate T034/T042: fetching the spec branch by
# name and re-dispatching implement-workflow with a bumped iteration --
# distinct from every other `git fetch origin "refs/heads/$...` idiom in
# this repository (branch-advance-capture's own fetch always force-updates
# with a `+` prefix; this one never does).
FOLD_DISPATCH_RE = re.compile(
    r'git fetch --quiet origin "refs/heads/\$\{?SPEC_BRANCH\}?"')
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
# issue #462, idiom updated by #085: `gh run cancel` alone is ordinary
# gh-CLI usage that also appears in pr-conversation.yml's own (unrelated)
# stop procedure, so co-occurrence with fact 1 below -- unique to this
# idiom -- is what keeps this check from false-positiving there, the same
# reasoning check_dispatch_and_wait already documents for its own fragment
# set. Fact 1 matches either the post-085 CLI invocation
# (`board_stop_check.py`) or the pre-085 import style (`from
# board_stop_check import find_stop_request`), so a paste of either idiom
# is caught regardless of which era it copies (FR-009).
BOARD_STOP_CHECK_DECISION_RE = re.compile(
    r"board_stop_check\.py|from board_stop_check import find_stop_request")
BOARD_STOP_CHECK_CANCEL = "gh run cancel"
# #572: the splice step of the transcript normaliser. `.[]` in the
# then-branch is what distinguishes it from the per-document
# `if type=="array" then . else [.] end` wrap used by fallback reads.
# #575: equivalent rewrites are matched too -- the condition parenthesised
# or reversed (`(type=="array")`, `"array"==type`), the splice optional or
# parenthesised (`.[]?`, `(.[])`), the else-branch parenthesised, and the
# array test moved into an `elif` arm.
_TN_ARRAY = r'["\']array["\']'
_TN_COND = (r'\(?\s*(?:type\s*==\s*' + _TN_ARRAY + r'|' + _TN_ARRAY +
            r'\s*==\s*type)\s*\)?')
_TN_SPLICE = r'\(?\s*\.\[\]\??\s*\)?'
_TN_SELF = r'\(?\s*\.\s*\)?'
TRANSCRIPT_NORMALISE_RE = re.compile(
    r'\b(?:el)?if\s*' + _TN_COND + r'\s*then\s+' + _TN_SPLICE + r'\s*else\s+'
    + _TN_SELF + r'\s*end\b')
MODE_TAG_FRAGMENT_RE = re.compile(r"\{\s*mode\s*:\s*\$[A-Za-z_][A-Za-z0-9_]*\s*\}")
SHARED_REF_RE = re.compile(r"\.github/actions/_shared/[A-Za-z0-9_.\-/]+")
# specs/068-plan-tasks-branch-advance research.md R10: the branch-advance
# capture's "after"/"commits" git plumbing. The refspec-form fetch (the `+`
# force-update prefix is what distinguishes it from the fleet's several
# other, unrelated `git fetch origin "refs/heads/$..."` idioms, e.g.
# implement.yml's/plan.yml's/tasks.yml's default-branch-divergence checks,
# none of which use the `+` prefix) co-occurring with a `..`-range
# `git rev-list --count "$..."` read (watchdog.yml's own since-created/
# head-sha arms use this shape too, but never alongside the refspec fetch
# above -- verified empirically against the tree once this feature's own
# T003 refactor landed) is what only the declared home carries.
BRANCH_ADVANCE_FETCH_FRAGMENT = 'git fetch origin "+refs/heads/$'
BRANCH_ADVANCE_REVLIST_RE = re.compile(
    r'git rev-list --count "\$[A-Za-z_][A-Za-z0-9_]*\.\.')
# specs/084-board-loop-single-home-idioms research.md D6: the marker-write
# bootstrap's three fragments, all appearing together in one subject file.
MARKER_WRITE_FRAGMENTS = (
    "sys.path.insert",
    "board_item_marker",
    "write_marker",
)
# specs/084-board-loop-single-home-idioms research.md D5: co-occurrence of
# the PR-branch read and the pair of GITHUB_OUTPUT writes it feeds, scoped
# per-step (like check_failure_issue/check_token_mint) so pr-conversation.yml's
# two structurally similar but conceptually distinct headRefName reads --
# neither of which writes this pr-number=/branch= pair -- do not false-positive.
PR_BRANCH_FRAGMENTS = (
    "gh pr view",
    "headRefName",
    'echo "pr-number=',
    'echo "branch=',
)

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


class _LineMap(dict):
    """A YAML mapping that remembers where it sat in the source.

    `line` is the mapping's own 1-based start line and `key_lines` maps
    each scalar key to the 1-based line it was written on. Both are
    attributes, never dict keys, so they cannot collide with a real step
    key or show up in `.items()` (issue #758)."""

    line = 0
    key_lines = None


class _LineMarkedLoader(yaml.SafeLoader):
    """SafeLoader whose mappings are _LineMap, so a per-step finding can
    name the violating step's own line. Re-finding the step's text with
    `text.find(run.splitlines()[0])` returned the first occurrence
    anywhere in the file, which for a common opener like
    `set -uo pipefail` is an earlier, unrelated step (issue #758)."""


def _construct_line_map(loader, node):
    data = _LineMap()
    data.line = node.start_mark.line + 1
    data.key_lines = {}
    yield data
    data.update(loader.construct_mapping(node))
    for key_node, _value in node.value:
        if isinstance(key_node, yaml.ScalarNode):
            data.key_lines[key_node.value] = key_node.start_mark.line + 1


_LineMarkedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_line_map)


def load_yaml(root, path):
    try:
        return yaml.load(read(root, path), Loader=_LineMarkedLoader) or {}
    except (yaml.YAMLError, OSError):
        return None


def step_key_line(step, key):
    """1-based line of a step's own `key:` (the step's start line if the
    key's position is unknown) -- see _LineMarkedLoader."""
    key_lines = getattr(step, "key_lines", None) or {}
    return key_lines.get(key) or getattr(step, "line", 0) or 1


def step_run_line(step):
    """1-based line of a step's own `run:` key -- step_key_line()."""
    return step_key_line(step, "run")


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
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if LABEL_CREATE_RE.search(run) and ISSUE_LOOKUP_RE.search(run):
                    findings.append(Finding(
                        path, "failure-issue",
                        step_run_line(step),
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
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if OUTSTANDING_TASK_RE.search(run):
                    findings.append(Finding(
                        path, "outstanding-task-item",
                        step_run_line(step),
                        'gh issue comment ... "- [ ] ..."'))
    return findings


# --------------------------------------------------------------------------
# Check: post-review-comment (per-step, single-fragment)
# --------------------------------------------------------------------------
def check_post_review_comment(root="."):
    home = DECLARED_HOMES["post-review-comment"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if POST_REVIEW_COMMENT_RE.search(run):
                    findings.append(Finding(
                        path, "post-review-comment",
                        step_run_line(step),
                        'gh api -X POST ... reviews ... -f event=COMMENT'))
    return findings


# --------------------------------------------------------------------------
# Check: review-finding-fingerprint (per-step, single-fragment)
# --------------------------------------------------------------------------
def check_review_finding_fingerprint(root="."):
    home = DECLARED_HOMES["review-finding-fingerprint"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if REVIEW_FINDING_FINGERPRINT_RE.search(run):
                    findings.append(Finding(
                        path, "review-finding-fingerprint",
                        step_run_line(step),
                        'hashlib.sha256("{0}|{1}|{2}".format(issue_number, ...))'))
    return findings


# --------------------------------------------------------------------------
# Check: gha-expr-evaluator (file-wide, over .github/scripts -- code review
# of #940)
# --------------------------------------------------------------------------
THIS_GATE = ".github/scripts/verify-single-home-idioms.py"
GHA_EXPR_TRANSPILE_RE = re.compile(
    r"""\.replace\(\s*["']&&["']\s*,\s*["']\s*and\b""")
GHA_EXPR_EVAL_RE = re.compile(r"\beval\s*\(")
GHA_EXPR_SPLIT_RE = re.compile(r"""\.split\(\s*["']&&["']\s*\)""")
GHA_EXPR_TERM_RE = re.compile(
    r"\((?:\?P<\w+>|\?:)?(?:==\\?\|!=|!=\\?\|==)\)")


def script_files(root="."):
    """Every *.py under .github/scripts/**, repo-relative."""
    base = os.path.join(root, ".github", "scripts")
    found = []
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                found.append(os.path.relpath(path, root).replace(os.sep, "/"))
    return sorted(found)


def check_gha_expr_evaluator(root="."):
    home = DECLARED_HOMES["gha-expr-evaluator"]
    findings = []
    for path in script_files(root):
        # This gate names the three signs itself, in its docstring and its
        # self-test pastes.
        if path in (home, THIS_GATE):
            continue
        text = read(root, path)
        m = GHA_EXPR_TRANSPILE_RE.search(text)
        if m is None and "__builtins__" in text:
            m = GHA_EXPR_EVAL_RE.search(text)
        if m is None and GHA_EXPR_TERM_RE.search(text):
            m = GHA_EXPR_SPLIT_RE.search(text)
        if m is not None:
            findings.append(Finding(path, "gha-expr-evaluator",
                                    line_of(text, m.start()), m.group(0)))
    return findings


# --------------------------------------------------------------------------
# Check: gh-callsite-locator (file-wide, over .github/scripts -- specs/113
# FR-011)
# --------------------------------------------------------------------------
# A shell scanner is a script that skips heredoc bodies (a regex opening
# `<<-?[ \t]*` or `<<-?\s*` and capturing the delimiter) AND steps through
# `$(` by index (`startswith("$(", i)`): the two things a scanner needs to
# tell a command from text. Either sign alone is common -- a regex that
# finds a heredoc to read its body, a `$(` search in a fixture -- so only
# the pair is a second locator. Matched on the SOURCE text of the scanner.
SCANNER_HEREDOC_RE = re.compile(r"<<-\?(?:\[ \\t\]|\\s)\*")
SCANNER_SUBST_RE = re.compile(r"""startswith\(\s*["']\$\(["']\s*,""")


def check_gh_callsite_locator(root="."):
    home = DECLARED_HOMES["gh-callsite-locator"]
    findings = []
    for path in script_files(root):
        # This gate names both signs itself, in this comment and its pastes.
        if path in (home, THIS_GATE):
            continue
        text = read(root, path)
        m = SCANNER_HEREDOC_RE.search(text)
        if m is not None and SCANNER_SUBST_RE.search(text):
            findings.append(Finding(
                path, "gh-callsite-locator", line_of(text, m.start()),
                "shell scanner: a heredoc-opener regex plus `$(` stepping"))
    return findings


# --------------------------------------------------------------------------
# Check: fold-commit (per-step, single-fragment)
# --------------------------------------------------------------------------
def check_fold_commit(root="."):
    home = DECLARED_HOMES["fold-commit"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if FOLD_COMMIT_RE.search(run):
                    findings.append(Finding(
                        path, "fold-commit", step_run_line(step),
                        '.pending_re_review_from = (((.pending_re_review_from ...'))
    return findings


# --------------------------------------------------------------------------
# Check: fold-dispatch (per-step, single-fragment)
# --------------------------------------------------------------------------
def check_fold_dispatch(root="."):
    home = DECLARED_HOMES["fold-dispatch"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if FOLD_DISPATCH_RE.search(run):
                    findings.append(Finding(
                        path, "fold-dispatch", step_run_line(step),
                        'git fetch --quiet origin "refs/heads/${SPEC_BRANCH}"'))
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
# Check: board-stop-check (YAML-structural, per job / composite step-list --
# issue #462, reworked #085/research.md D7)
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
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            run_text = "\n".join(str((step or {}).get("run") or "") for step in steps)
            decision_match = BOARD_STOP_CHECK_DECISION_RE.search(run_text)
            if decision_match and BOARD_STOP_CHECK_CANCEL in run_text:
                # The step that obtains the decision, by its own run: key
                # -- never text.find(), whose first match in the file can
                # sit in another job's step list (#882's class).
                decision_step = next(
                    step for step in steps
                    if BOARD_STOP_CHECK_DECISION_RE.search(
                        str((step or {}).get("run") or "")))
                findings.append(Finding(
                    path, "board-stop-check", step_run_line(decision_step),
                    f"{decision_match.group(0)!r} (obtains a stop decision) + "
                    f"'gh run cancel' (performs a cancellation), in the same "
                    f"step list"))
    return findings


# --------------------------------------------------------------------------
# Check: marker-write (per-step co-occurrence of the sys.path/import/call
# bootstrap -- specs/084-board-loop-single-home-idioms research.md D6).
# Per-step, NOT file-wide like check_board_stop_check: board-loop.yml still
# legitimately carries several unrelated `sys.path.insert(0,
# ".github/scripts")` + `board_item_marker` bootstraps for
# read_marker_with_timestamp() (a different public function -- reading a
# marker, never writing one), plus this file's own header comment
# mentioning "write_marker()" in prose. A file-wide scan false-positives on
# that combination even with zero inline write-bootstraps left; scoping to
# one step's own `run:` text (as check_failure_issue/check_pr_branch
# already do) does not, since neither the unrelated read-bootstraps nor the
# header comment ever share a step with a `write_marker` mention.
# --------------------------------------------------------------------------
def check_marker_write(root="."):
    home = DECLARED_HOMES["marker-write"]
    home_dir = home.rsplit("/", 1)[0] + "/"
    findings = []
    for path in all_subject_files(root):
        if path == home or path.startswith(home_dir):
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if all(fragment in run for fragment in MARKER_WRITE_FRAGMENTS):
                    findings.append(Finding(
                        path, "marker-write", step_run_line(step),
                        "sys.path.insert + board_item_marker + write_marker "
                        "co-occurrence"))
    return findings


# --------------------------------------------------------------------------
# Check: pr-branch (per-step co-occurrence of the headRefName read and the
# pr-number=/branch= GITHUB_OUTPUT writes -- research.md D5)
# --------------------------------------------------------------------------
def check_pr_branch(root="."):
    home = DECLARED_HOMES["pr-branch"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = str((step or {}).get("run") or "")
                if not run:
                    continue
                if all(fragment in run for fragment in PR_BRANCH_FRAGMENTS):
                    findings.append(Finding(
                        path, "pr-branch", step_run_line(step),
                        "gh pr view ... headRefName + pr-number=/branch= "
                        "GITHUB_OUTPUT co-occurrence"))
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
                    mint_ids.append((idx, step.get("id"), step))
            for idx, step_id, mint_step in mint_ids:
                if not step_id:
                    continue
                needle = f"steps.{step_id}.outcome"
                for later in steps[idx + 1:]:
                    later = later or {}
                    haystack = " ".join(str(later.get(k) or "")
                                        for k in ("if", "run")) + " ".join(
                        str(v) for v in (later.get("env") or {}).values())
                    if needle in haystack:
                        # The mint step's own uses: line, never the first
                        # text match of its id, which an earlier
                        # steps.<id>.outputs read or comment wins (#882).
                        findings.append(Finding(
                            path, "token-mint", step_key_line(mint_step, "uses"),
                            f"continue-on-error create-github-app-token "
                            f"(id: {step_id}) + a later read of its .outcome"))
                        break
    return findings


# --------------------------------------------------------------------------
# Check: branch-advance-capture (file-wide co-occurrence, specs/068-plan-
# tasks-branch-advance research.md R10)
# --------------------------------------------------------------------------
def check_branch_advance_capture(root="."):
    home = DECLARED_HOMES["branch-advance-capture"]
    findings = []
    for path in all_subject_files(root):
        if path == home:
            continue
        text = read(root, path)
        if BRANCH_ADVANCE_FETCH_FRAGMENT in text and \
                BRANCH_ADVANCE_REVLIST_RE.search(text):
            offset = text.index(BRANCH_ADVANCE_FETCH_FRAGMENT)
            findings.append(Finding(
                path, "branch-advance-capture", line_of(text, offset),
                BRANCH_ADVANCE_FETCH_FRAGMENT))
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
# --------------------------------------------------------------------------
# Check: composite-checkout-order (structural, no single declared home --
# maintainer review of #607, fold leg-0: board-loop.yml's review and
# readiness jobs called the new resolve-pr-branch composite as their first
# step, before any actions/checkout@ step existed in the job, so the
# composite's action.yml could not be resolved from the not-yet-checked-out
# workspace and every review/readiness run failed at run time instead of
# at gate time. Extended in fold leg-1: the original "any checkout@ step
# seen so far" test passed a sidecar-relative reference
# (./.wc-pristine-repo/...) merely because an earlier, unrelated
# root-workspace checkout had already run -- it never confirmed the
# specific directory the reference resolves from had actually been
# checked out. A bare `./.github/...` reference (this fleet's only
# root-relative form) still needs a preceding checkout with no `path:`;
# every other first path segment names a sidecar directory (e.g.
# `.wc-pristine-repo`, `.wing-commander-pipeline`) and now needs a
# preceding checkout whose own `with.path` matches that exact segment --
# a root checkout, however early, never satisfies it.
#
# Extended again in fold leg-2 (issue #757, found by the code review of
# #683): neither leg above catches a path-scoped sidecar checkout placed
# BEFORE the job's own root checkout, even when no local `uses: ./...`
# step is involved at all. actions/checkout@v5's prepareExistingDirectory
# removes every entry in a workspace directory that lacks its own `.git`
# before checking out -- so a root checkout that runs after a sidecar
# checkout wipes the sidecar (a write-protected one fails the removal with
# EACCES; an unprotected one is silently deleted). PR #683 shipped exactly
# this ordering, in board-loop's review and readiness jobs, with the whole
# gate suite green; it was caught only by manual review. This pass now
# also flags a job with a root checkout whose first path-scoped checkout
# precedes it -- the root checkout must be the job's first
# `actions/checkout@` step of any kind.
# --------------------------------------------------------------------------
ROOT_ACTIONS_SEGMENT = ".github"


def check_local_action_before_checkout(root="."):
    """A local `uses: ./...` step resolves its action.yml relative to
    whichever checked-out directory its first path segment names -- the
    workspace root for a bare `./.github/actions/...` reference, or a
    sidecar directory like `.wc-pristine-repo` for
    `./.wc-pristine-repo/.github/actions/...` -- and a workflow job that
    calls one before the checkout that actually populates that directory
    fails at run time ("Did you forget to run actions/checkout") instead
    of failing here. Composite actions' own `runs.steps` execute inside
    the CALLER's already-checked-out workspace, so only workflow jobs
    (doc["jobs"]) are scanned -- never an action.yml's own `runs.steps`.

    Also flags a path-scoped (sidecar) `actions/checkout@` step that
    precedes the job's own root `actions/checkout@` step (no `path:`):
    that root checkout's `prepareExistingDirectory` removes the sidecar
    directory on the way to populating the workspace root (issue #757)."""
    findings = []
    for path in all_subject_files(root):
        doc = load_yaml(root, path)
        if not isinstance(doc, dict) or not doc.get("jobs"):
            continue
        for job_id, steps in _step_lists(doc):
            seen_root = False
            seen_scoped = set()
            scoped_before_root = None
            scoped_before_root_with = None
            for step in steps:
                uses = str((step or {}).get("uses") or "")
                if not uses:
                    continue
                if uses.startswith("actions/checkout@"):
                    scoped_path = (step.get("with") or {}).get("path")
                    if scoped_path:
                        seen_scoped.add(scoped_path)
                        if not seen_root and scoped_before_root is None:
                            scoped_before_root = scoped_path
                            scoped_before_root_with = step.get("with")
                    else:
                        seen_root = True
                elif uses.startswith("./"):
                    first_seg = uses[2:].split("/", 1)[0]
                    if first_seg == ROOT_ACTIONS_SEGMENT:
                        ok, where = seen_root, "the workspace root"
                    else:
                        ok, where = first_seg in seen_scoped, f"path: {first_seg}"
                    if not ok:
                        # This step's own uses: line, never the first job
                        # that calls the same local action (#882).
                        findings.append(Finding(
                            path, "composite-checkout-order",
                            step_key_line(step, "uses"),
                            f"job {job_id!r}: {uses} resolved before the "
                            f"actions/checkout@ step for {where}"))
            if seen_root and scoped_before_root is not None:
                # The scoped checkout's own `path:` line, never an earlier
                # step's identical `path:` in the same job (code review of
                # #939, the same rule as #882's).
                findings.append(Finding(
                    path, "composite-checkout-order",
                    step_key_line(scoped_before_root_with, "path"),
                    f"job {job_id!r}: a path-scoped actions/checkout@ step "
                    f"(path: {scoped_before_root}) precedes the job's root "
                    f"actions/checkout@ step -- the root checkout removes "
                    f"the sidecar on its way to populating the workspace"))
    return findings


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


# --------------------------------------------------------------------------
# shared-path-workdir (#889): auto-release.yml's scaffold step runs under
# `working-directory: e2e-test-repo` yet called
# `bash .github/actions/_shared/auto-release-verdict.sh`, which resolved
# inside the test repository's clone -- every one of its failure verdicts
# would have died "No such file or directory" instead of naming the failure.
# A bare `.github/actions/_shared/...` reference is only right from the
# workspace root; anywhere else it must be anchored ($GITHUB_WORKSPACE/ or
# ${{ github.workspace }}/).
# --------------------------------------------------------------------------
ROOT_WORKDIRS = ("", ".", "./", "${{ github.workspace }}", "$GITHUB_WORKSPACE",
                 "${GITHUB_WORKSPACE}")
# An optional leading `./` is the same bare repo-relative path (#960 review).
BARE_SHARED_REF_RE = re.compile(r"(?<![\w}/.$-])(?:\./)?\.github/actions/_shared/[A-Za-z0-9_.\-/]+")
SHARED_PATH_WORKDIR_HINT = ("\"$GITHUB_WORKSPACE/.github/actions/_shared/...\" "
                            "(a bare repo-relative path resolves inside the "
                            "step's working-directory)")


def check_shared_path_workdir(root="."):
    findings = []
    for path in _relativize(root, workflow_files(root)):
        doc = load_yaml(root, path)
        if not isinstance(doc, dict):
            continue
        # A workflow-level `defaults.run` applies too, under any job's own
        # (#960 review).
        wf_wd = str(((doc.get("defaults") or {}).get("run") or {})
                    .get("working-directory") or "")
        for job_id, job in (doc.get("jobs") or {}).items():
            job = job or {}
            job_wd = str(((job.get("defaults") or {}).get("run") or {})
                         .get("working-directory") or wf_wd)
            for step in job.get("steps") or []:
                step = step or {}
                run = step.get("run")
                if not run:
                    continue
                wd = str(step.get("working-directory") or job_wd).strip()
                # A trailing slash names the same directory
                # (`${{ github.workspace }}/` is the root; #960 second review),
                # but `/` itself is the filesystem root, not "" (#960 third
                # review).
                if wd != "/" and wd.rstrip("/") in ROOT_WORKDIRS:
                    continue
                m = BARE_SHARED_REF_RE.search(str(run))
                if m:
                    findings.append(Finding(
                        path, "shared-path-workdir", step_run_line(step),
                        f"job {job_id!r}: {m.group(0)} under "
                        f"working-directory: {wd}"))
    return findings


# --------------------------------------------------------------------------
# substitution-fallback (#889, #959): `x="$(cmd || echo '[]')"` appends
# the fallback to whatever `cmd` already printed when `cmd` prints and then
# exits non-zero -- jq emitting `[]` before failing on a later document gave
# `[]\n[]`, which every downstream `--argjson` rejected. The fallback
# belongs at the assignment, where it replaces instead of appends:
# `x="$(cmd)" || x='[]'`. One rule for every workflow `run:`, composite
# `run:` and `.github/actions/**/*.sh` script.
#
# Exempt without a waiver: the test ternary, `$([ "$a" = x ] && echo y ||
# echo z)` -- every command left of the `||` but the last is a `[`/`[[`/
# `test` that prints nothing, and the last is the `echo`/`printf` itself,
# so at most one of the two echoes ever prints. Nothing else is guessed
# safe: a command that "cannot print on failure" is fixed or waived with
# its reason, never inferred here.
#
# A `$(` is found anywhere in the text, including inside a single-quoted
# literal outside any substitution: modelling the outer quoting would let
# an apostrophe in a heredoc body desync it and hide every real site after
# it. That errs toward a finding, which a waiver can name.
# --------------------------------------------------------------------------
SUBST_FALLBACK_HINT = ('x="$(cmd)" || x=\'fallback\' (an assignment-level '
                       'fallback replaces what cmd printed; one inside the '
                       '$( ) appends to it)')
_SF_FALLBACK_RE = re.compile(r"(?:echo|printf)(?:\s|$)")
_SF_TEST_RE = re.compile(r"(?:\[\[?|test)(?:\s|$)")
_SF_BLOCK_KEY_RE = re.compile(r"\brun:\s*[|>][-+0-9]*\s*(?:#.*)?$")


def _scan_substitution(text, start):
    """Parse the `$( ... )` whose body begins at `start` (just past the
    `$(`). Returns (end, ops): `end` is the index of the closing `)` (or
    None if unbalanced), `ops` the (kind, index) of each `&&`/`||`/`|`/
    `;`/newline at the body's own top level -- outside quotes and nested
    substitutions/subshells. A newline is recorded only where it separates
    commands: not at the body's start, after `&&`/`||`/`|`/`|&`/`;` (bash
    continues the list across any blank or comment lines there) or after
    another newline. Heredoc bodies are not modelled; a run block that
    needs one inside a substitution is rare enough to waive."""
    stack = ["sub"]
    ops = []
    cont = True  # no command since the body's start or the last operator
    i, n = start, len(text)
    while i < n:
        c = text[i]
        top = stack[-1]
        if top == "dq":
            if c == "\\":
                i += 2
                continue
            if c == '"':
                stack.pop()
            elif text.startswith("$(", i):
                stack.append("sub")
                i += 2
                continue
            i += 1
            continue
        # top is "sub" (a `$(` or a bare `(` subshell)
        comment = c == "#" and (i == start or text[i - 1] in " \t\n;")
        if (len(stack) == 1 and c not in " \t\n" and not comment
                and text[i:i + 2] != "\\\n"):
            cont = False
        if c == "\\":
            i += 2
            continue
        if c == "'":
            close = text.find("'", i + 1)
            i = n if close < 0 else close + 1
            continue
        if c == '"':
            stack.append("dq")
            i += 1
            continue
        if comment:
            nl = text.find("\n", i)
            i = n if nl < 0 else nl
            continue
        if text.startswith("$(", i) or c == "(":
            stack.append("sub")
            i += 2 if c == "$" else 1
            continue
        if c == ")":
            stack.pop()
            if not stack:
                return i, ops
            i += 1
            continue
        if len(stack) == 1:
            two = text[i:i + 2]
            if two in ("&&", "||", "|&"):
                ops.append((two if two != "|&" else "|", i))
                cont = True
                i += 2
                continue
            if c == "|" or c == ";":
                ops.append((c, i))
                cont = True
            elif c == "\n" and not cont:
                ops.append(("\n", i))
                cont = True
        i += 1
    return None, ops


def substitution_fallbacks(text):
    """Every `$( ... )` in `text` whose body ends `|| echo ...` or
    `|| printf ...`, minus the test ternary. Yields (offset, body)."""
    for m in re.finditer(r"\$\((?!\()", text):
        start = m.end()
        end, ops = _scan_substitution(text, start)
        if end is None:
            continue
        ors = [i for kind, i in ops if kind == "||"]
        if not ors:
            continue
        last_or = ors[-1]
        # The `||` must be the body's last list operator: one followed by
        # another command (`... || printf x\n done`, a loop's body) is not
        # a fallback for the whole substitution.
        if any(i > last_or and (kind != "\n" or text[i:end].strip())
               for kind, i in ops):
            continue
        # Past any comment lines bash skips after a line-ending `||`.
        tail = re.sub(r"^(?:\s*#[^\n]*\n)*\s*", "", text[last_or + 2:end])
        if not _SF_FALLBACK_RE.match(tail):
            continue
        # The test ternary: `[ ... ] && [ ... ] && echo a || echo b` --
        # every command before the final `||` joined by `&&` alone (no
        # earlier `||`, `|`, `;` or newline), each a test but the last.
        cuts = [start] + [i + 2 for kind, i in ops
                          if kind == "&&" and i < last_or] + [last_or]
        segs = [text[a:b].strip() for a, b in zip(cuts, cuts[1:])]
        if (len(segs) >= 2 and _SF_FALLBACK_RE.match(segs[-1])
                and all(_SF_TEST_RE.match(s) for s in segs[:-1])
                and all(kind == "&&" for kind, i in ops if i < last_or)):
            continue
        yield m.start(), " ".join(text[start:end].replace("\\\n", " ").split())


def check_substitution_fallback(root="."):
    findings = []
    for path in all_subject_files(root):
        if path.endswith(".sh"):
            text = read(root, path)
            for off, body in substitution_fallbacks(text):
                findings.append(Finding(path, "substitution-fallback",
                                        line_of(text, off), body))
            continue
        doc = load_yaml(root, path)
        if doc is None:
            continue
        lines = read(root, path).split("\n")
        for _ctx, steps in _step_lists(doc):
            for step in steps:
                run = (step or {}).get("run")
                if not isinstance(run, str) or not run:
                    continue
                base = step_run_line(step)
                # A block scalar's first line sits under the `run:` key --
                # read off the key's own line, since a one-line `run: |`
                # body carries no inner newline to tell it from `run: x`.
                if _SF_BLOCK_KEY_RE.search(lines[base - 1] if base <= len(lines) else ""):
                    base += 1
                for off, body in substitution_fallbacks(run):
                    findings.append(Finding(
                        path, "substitution-fallback",
                        base + run.count("\n", 0, off), body))
    return findings


ALL_CHECKS = {
    "orphan-reset": check_orphan_reset,
    "extraheader-refresh": check_extraheader_refresh,
    "failure-issue": check_failure_issue,
    "outstanding-task-item": check_outstanding_task_item,
    "post-review-comment": check_post_review_comment,
    "review-finding-fingerprint": check_review_finding_fingerprint,
    "fold-commit": check_fold_commit,
    "fold-dispatch": check_fold_dispatch,
    "stage-findings": check_stage_findings,
    "size-path-backstop": check_size_path_backstop,
    "dispatch-and-wait": check_dispatch_and_wait,
    "board-stop-check": check_board_stop_check,
    "transcript-normalise": check_transcript_normalise,
    "gha-expr-evaluator": check_gha_expr_evaluator,
    "gh-callsite-locator": check_gh_callsite_locator,
    "verdict-shape": check_verdict_shape,
    "token-mint": check_token_mint,
    "mode-tag-shape": check_mode_tag_shape,
    "branch-advance-capture": check_branch_advance_capture,
    "marker-write": check_marker_write,
    "pr-branch": check_pr_branch,
    "promotion": check_promotion,
    "composite-checkout-order": check_local_action_before_checkout,
    "shared-path-workdir": check_shared_path_workdir,
    "substitution-fallback": check_substitution_fallback,
}


# --------------------------------------------------------------------------
# Waivers -- same shape as stage-invariant-waivers.json (Gate 31)
# --------------------------------------------------------------------------
# `issue` is not here: whether a waiver cites an OPEN issue or is marked
# permanent is verify-waiver-citations.py's (Gate 124) one rule for every
# register.
REQUIRED_WAIVER_FIELDS = ("file", "check", "pattern", "count", "reason")


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
        if f.check == "shared-path-workdir":
            home = SHARED_PATH_WORKDIR_HINT
        elif f.check == "substitution-fallback":
            home = SUBST_FALLBACK_HINT
        else:
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
          "        stop_decision_json=\"$(jq -n --slurpfile comments "
          "\"$RUNNER_TEMP/board-stop-check-comments.json\" '{comments: "
          "$comments[0]}' | python3 .github/scripts/board_stop_check.py)\"\n"
          "        cancel_run_id=\"$(jq -r '.cancel_run_id // empty' "
          "<<<\"$stop_decision_json\")\"\n"
          "        GH_TOKEN=\"$CANCEL_TOKEN\" gh run cancel "
          "\"$cancel_run_id\" -R \"$GITHUB_REPOSITORY\" 2>/dev/null || true\n")
    _write(root, DECLARED_HOMES["gha-expr-evaluator"],
          "def evaluate(expr, ctx):\n    return Parser(expr, ctx).parse()\n")
    _write(root, DECLARED_HOMES["gh-callsite-locator"],
          "def locate(script):\n    return []\n")
    _write(root, DECLARED_HOMES["transcript-normalise"],
          "#!/usr/bin/env bash\n"
          "jq -cs 'map(if type==\"array\" then .[] else . end) "
          "| map(objects)' \"$1\"\n")
    _write(root, DECLARED_HOMES["branch-advance-capture"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        git fetch origin \"+refs/heads/$branch:refs/remotes/"
          "origin/$branch\"\n"
          "        commits=\"$(git rev-list --count "
          "\"$BEFORE_SHA..$after_sha\")\"\n")
    _write(root, DECLARED_HOMES["post-review-comment"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        gh api -X POST \"repos/$GITHUB_REPOSITORY/pulls/$PR/"
          "reviews\" -f event=COMMENT -F body=@\"$BODY_FILE\"\n")
    _write(root, DECLARED_HOMES["review-finding-fingerprint"],
          "#!/usr/bin/env python3\n"
          "import hashlib\n"
          "import re\n\n\n"
          "def norm(value):\n"
          "    return \" \".join(re.sub(r\"[\\W_]+\", \" \", "
          "str(value).lower()).split())\n\n\n"
          "def fingerprint(issue_number, title, file_path):\n"
          "    return hashlib.sha256(\"{0}|{1}|{2}\".format(\n"
          "        issue_number, norm(title), norm(file_path)\n"
          "    ).encode(\"utf-8\")).hexdigest()\n")
    _write(root, DECLARED_HOMES["fold-commit"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        jq --arg actor \"$ACTOR_LOGIN\" '\n"
          "          .stage = \"implement\"\n"
          "          | .pending_re_review_from = (((.pending_re_review_from "
          "// []) + (if $actor == \"\" then [] else [$actor] end)) | unique)\n"
          "        ' \"$SPEC_DIR/spec-meta.json\" > /tmp/m.json\n")
    _write(root, DECLARED_HOMES["fold-dispatch"],
          "runs:\n  using: composite\n  steps:\n"
          "    - shell: bash\n      run: |\n"
          "        git fetch --quiet origin \"refs/heads/${SPEC_BRANCH}\" "
          "|| true\n")
    _write(root, DECLARED_HOMES["marker-write"],
          "#!/usr/bin/env python3\n"
          "import argparse\n"
          "\n"
          "\n"
          "def write_marker(step, round, pr, branch, base_sha):\n"
          "    return step\n"
          "\n"
          "\n"
          "def main():\n"
          "    parser = argparse.ArgumentParser()\n"
          "    parser.add_argument(\"--step\", required=True)\n"
          "    parser.add_argument(\"--round\", type=int, default=0)\n"
          "    parser.add_argument(\"--pr\", type=int, default=None)\n"
          "    parser.add_argument(\"--branch\", default=None)\n"
          "    parser.add_argument(\"--base-sha\", default=None)\n"
          "    args = parser.parse_args()\n"
          "    print(write_marker(args.step, args.round, args.pr, args.branch, "
          "args.base_sha))\n"
          "\n"
          "\n"
          "if __name__ == \"__main__\":\n"
          "    main()\n")
    _write(root, DECLARED_HOMES["pr-branch"],
          "inputs:\n  pr-number:\n    required: true\n  token:\n    required: true\n"
          "  round:\n    required: false\n    default: \"\"\n"
          "runs:\n  using: composite\n  steps:\n"
          "    - id: resolve\n      shell: bash\n      env:\n"
          "        GH_TOKEN: ${{ inputs.token }}\n"
          "        PR_NUMBER: ${{ inputs.pr-number }}\n"
          "      run: |\n"
          "        set -euo pipefail\n"
          "        branch=\"$(gh pr view \"$PR_NUMBER\" --json headRefName "
          "--jq .headRefName)\"\n"
          "        { echo \"pr-number=$PR_NUMBER\"; echo \"branch=$branch\"; } "
          ">> \"$GITHUB_OUTPUT\"\n")
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


def selftest_third_paste_passes(check_key, paste_path, paste_content):
    case = f"{paste_path} carries one sign of {check_key} only and is not flagged"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        _write(tmp, paste_path, paste_content)
        findings, hard = evaluate(tmp)
        hits = [f for f in findings if f.check == check_key and f.path == paste_path]
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif hits:
            fail(f"[{case}] unexpected {check_key} finding: {hits[0]}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_composite_checkout_order_line_attribution():
    """Issue #757 fold leg-2 follow-up: when the same sidecar `path:`
    literal recurs across jobs (as `.wc-pristine-repo` does across
    board-loop.yml's own jobs), the scoped_before_root finding must point
    at the offending job's own step, not at the first occurrence of the
    literal anywhere earlier in the file."""
    case = "composite-checkout-order line attribution survives a repeated path literal"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        paste_path = ".github/workflows/third-checkout-order-repeated-literal.yml"
        content = (
            "on: push\n"
            "jobs:\n"
            "  a:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v5\n"
            "      - uses: actions/checkout@v5\n"
            "        with:\n"
            "          path: .wc-pristine-repo\n"
            "  b:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v5\n"
            "        with:\n"
            "          path: .wc-pristine-repo\n"
            "      - uses: actions/checkout@v5\n"
        )
        lines = content.splitlines()
        first_occurrence = lines.index("          path: .wc-pristine-repo")
        second_occurrence = lines.index(
            "          path: .wc-pristine-repo", first_occurrence + 1)
        expected_line = second_occurrence + 1
        _write(tmp, paste_path, content)
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings
                if f.check == "composite-checkout-order" and f.path == paste_path
                and "job 'b'" in f.text]
        if not hits:
            fail(f"[{case}] expected a composite-checkout-order finding for "
                f"job 'b' at {paste_path}, got: {findings}")
        elif hits[0].line != expected_line:
            fail(f"[{case}] job 'b' finding pointed at line {hits[0].line}, "
                f"expected {expected_line} (job 'b' own step, not the earlier "
                f"use of the same path literal in job 'a')")
        else:
            note(f"[{case}] passed ({hits[0].path}:{hits[0].line})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# One violating run: body per check that locates its finding with
# step_run_line(); selftest_per_step_line_attribution prefixes each with a
# shared `set -uo pipefail` opener (issue #758).
PER_STEP_LINE_CASES = (
    ("marker-write",
     "          python3 -c \"import sys; "
     "sys.path.insert(0, '.github/scripts'); "
     "from board_item_marker import write_marker; "
     "write_marker('x', 1, 2, 'b', 'sha')\"\n"),
    ("pr-branch",
     "          head=$(gh pr view 1 --json headRefName --jq .headRefName)\n"
     "          echo \"pr-number=1\" >> \"$GITHUB_OUTPUT\"\n"
     "          echo \"branch=${head}\" >> \"$GITHUB_OUTPUT\"\n"),
    ("failure-issue",
     "          gh label create \"third:failed\" --color B60205 --force\n"
     "          gh issue list --label \"third:failed\" --state open "
     "--json number --jq '.[0].number // empty'\n"),
    ("outstanding-task-item",
     "          gh issue comment \"$N\" --body \"- [ ] a third paste "
     "\u2014 $URL\"\n"),
    ("post-review-comment",
     "          gh api -X POST \"repos/$R/pulls/1/reviews\" -f body=x -f event=COMMENT\n"),
    ("review-finding-fingerprint",
     "          python3 - <<'PYEOF'\n"
     "          import hashlib\n"
     "          fp = hashlib.sha256(\"{0}|{1}|{2}\".format(\n"
     "              issue_number, norm(title), norm(file_path)\n"
     "          ).encode(\"utf-8\")).hexdigest()\n"
     "          PYEOF\n"),
    ("fold-commit",
     "          jq --arg actor \"$ACTOR_LOGIN\" '\n"
     "            .stage = \"implement\"\n"
     "            | .pending_re_review_from = (((.pending_re_review_from "
     "// []) + (if $actor == \"\" then [] else [$actor] end)) | unique)\n"
     "          ' \"$SPEC_DIR/spec-meta.json\" > /tmp/m.json\n"),
    ("fold-dispatch",
     "          git fetch --quiet origin \"refs/heads/${SPEC_BRANCH}\" "
     "|| true\n"),
)


def selftest_per_step_line_attribution(check_key, violating_body):
    """Issue #758: a per-step finding must name the violating step's own
    line. The decoy step opens its `run:` with the same common line
    (`set -uo pipefail`) earlier in the file; re-finding that text, as the
    per-step checks once did, reported the decoy's line instead (PR #683:
    board-loop.yml:298 reported at :176)."""
    case = f"{check_key} line attribution survives a shared first run: line"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        paste_path = f".github/workflows/third-{check_key}-shared-opener.yml"
        content = (
            "on: push\n"
            "jobs:\n"
            "  x:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Decoy sharing the opener\n"
            "        shell: bash\n"
            "        run: |\n"
            "          set -uo pipefail\n"
            "          echo unrelated\n"
            "      - name: Real violation\n"
            "        shell: bash\n"
            "        run: |\n"
            "          set -uo pipefail\n"
            + violating_body
        )
        lines = content.splitlines()
        decoy_run = lines.index("        run: |") + 1
        expected_line = lines.index("        run: |", decoy_run) + 1
        _write(tmp, paste_path, content)
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings
                if f.check == check_key and f.path == paste_path]
        if len(hits) != 1:
            fail(f"[{case}] expected exactly one {check_key} finding at "
                f"{paste_path}, got: {findings}")
        elif hits[0].line != expected_line:
            fail(f"[{case}] finding pointed at line {hits[0].line}, expected "
                f"{expected_line} (the violating step's own run: key, not "
                f"the decoy step's shared `set -uo pipefail`)")
        else:
            note(f"[{case}] passed ({hits[0].path}:{hits[0].line})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest_decoy_line(case, check_key, paste_path, content, expected_text, job=None):
    """#882: the finding names the violating step's own line, the one
    holding `expected_text`, not an earlier decoy holding the same text."""
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        lines = content.splitlines()
        first = lines.index(expected_text)
        expected_line = lines.index(expected_text, first + 1) + 1
        _write(tmp, paste_path, content)
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings if f.check == check_key and f.path == paste_path
                and (job is None or "job {0!r}".format(job) in f.text)]
        if len(hits) != 1:
            fail(f"[{case}] expected exactly one {check_key} finding at {paste_path}, "
                 f"got: {findings}")
        elif hits[0].line != expected_line:
            fail(f"[{case}] finding pointed at line {hits[0].line}, expected "
                 f"{expected_line} (the violating step's own line, not the decoy's)")
        else:
            note(f"[{case}] passed ({hits[0].path}:{hits[0].line})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_token_mint_line_attribution():
    """#882: an earlier step reading steps.<id>.outputs mentions the mint
    step's id first; the finding must still name the mint step."""
    _selftest_decoy_line(
        "token-mint line attribution survives an earlier mention of the id",
        "token-mint", ".github/workflows/third-token-decoy.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - id: other\n"
        "        uses: actions/create-github-app-token@v3\n"
        "      - shell: bash\n        env:\n"
        "          T: ${{ steps.mint.outputs.token }}\n"
        "        run: echo hi\n"
        "      - id: mint\n        continue-on-error: true\n"
        "        uses: actions/create-github-app-token@v3\n"
        "      - shell: bash\n        env:\n"
        "          OUTCOME: ${{ steps.mint.outcome }}\n"
        "        run: echo hi\n",
        "        uses: actions/create-github-app-token@v3")


def selftest_local_action_line_attribution():
    """#882: job a calls the local action correctly after its checkout;
    job b calls the same action before any checkout. The finding names
    job b's own step, not job a's earlier, identical uses: line."""
    _selftest_decoy_line(
        "composite-checkout-order line attribution survives a repeated local uses:",
        "composite-checkout-order", ".github/workflows/third-checkout-order-decoy.yml",
        "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v5\n"
        "      - uses: ./.github/actions/widget\n"
        "  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: ./.github/actions/widget\n"
        "      - uses: actions/checkout@v5\n",
        "      - uses: ./.github/actions/widget", job="b")


def selftest_scoped_checkout_line_attribution():
    """Code review of #939: an earlier step in the same job carries the
    identical `path:` line; the finding names the path-scoped checkout's
    own, not the first textual match after the job's header."""
    _selftest_decoy_line(
        "composite-checkout-order line attribution survives an earlier identical path:",
        "composite-checkout-order", ".github/workflows/third-scoped-checkout-decoy.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/upload-artifact@v4\n"
        "        with:\n"
        "          path: .wc-pristine-repo\n"
        "      - uses: actions/checkout@v5\n"
        "        with:\n"
        "          path: .wc-pristine-repo\n"
        "      - uses: actions/checkout@v5\n",
        "          path: .wc-pristine-repo", job="x")


def selftest_board_stop_check_line_attribution():
    """Code review of #939: job a references board_stop_check.py with no
    cancellation (a legitimate consumer); job b pastes the whole idiom.
    The finding names job b's decision step, not job a's earlier match."""
    _selftest_decoy_line(
        "board-stop-check line attribution survives an earlier job's identical decision",
        "board-stop-check", ".github/workflows/third-board-stop-decoy.yml",
        "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          python3 .github/scripts/board_stop_check.py < in.json\n"
        "  b:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          python3 .github/scripts/board_stop_check.py < in.json\n"
        "      - shell: bash\n        run: gh run cancel \"$ID\"\n",
        "        run: |")


def selftest_per_document_wrap_passes():
    """#575: loosening the transcript-normalise regex must not start
    flagging the per-document wrap -- the legitimate fallback read the
    agent-verdict composite and implement.yml's refusal probe both keep --
    in any of the spellings the loosened pattern tolerates for the splice."""
    case = "the per-document `then . else [.] end` wrap is not flagged"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        paste_path = ".github/workflows/per-document.yml"
        _write(tmp, paste_path,
              "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
              "      - shell: bash\n        run: |\n"
              "          jq -r 'if type==\"array\" then . else [.] end "
              "| map(objects)' \"$T\"\n"
              "          jq -r 'if (type == \"array\") then . else [.] end' "
              "\"$T\"\n"
              "          jq -r 'if \"array\"==type then (.) else [.] end' "
              "\"$T\"\n")
        findings, hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "transcript-normalise"]
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif hits:
            fail(f"[{case}] the per-document wrap was flagged: {hits}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_board_stop_check_no_cancel_no_finding():
    case = "board_stop_check.py referenced with no cancellation is not flagged"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        paste_path = ".github/workflows/dry-run-reporter.yml"
        _write(tmp, paste_path,
              "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
              "      - shell: bash\n        run: |\n"
              "          gh api \"repos/$GITHUB_REPOSITORY/issues/$N/comments\" "
              "--paginate --jq '.[]' | jq -s '.' > \"$RUNNER_TEMP/comments.json\"\n"
              "          jq -n --slurpfile comments \"$RUNNER_TEMP/comments.json\" "
              "'{comments: $comments[0]}' | python3 .github/scripts/board_stop_check.py\n")
        findings, hard = evaluate(tmp)
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
            return
        hits = [f for f in findings if f.check == "board-stop-check" and f.path == paste_path]
        if hits:
            fail(f"[{case}] unexpected board-stop-check finding(s): {hits}")
        else:
            note(f"[{case}] passed")
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


def selftest_marker_write_cli_resolves_symbolic_steps_under_dash_i():
    """Maintainer review of #607 (fold leg-1): board_item_marker.py's CLI
    must resolve --step BREACH_STEP/AWAITING_MERGE_STEP even under
    `python3 -I` (which excludes the script's own directory from sys.path)
    invoked from a cwd other than the script's own -- reproducing
    board-loop.yml's real `python3 -I
    "$RUNNER_TEMP/wc-pristine/scripts/board_item_marker.py"` invocation
    shape, not the declared-home text scans above (which cannot catch a
    runtime ModuleNotFoundError)."""
    case = "marker-write CLI resolves symbolic steps under python3 -I from a foreign cwd"
    script = os.path.abspath(DECLARED_HOMES["marker-write"])
    other_cwd = tempfile.mkdtemp(prefix="wc-marker-write-cwd-")
    env = {"PATH": os.environ.get("PATH", "")}
    ok = True
    try:
        for token, expected in (("BREACH_STEP", "breach"), ("AWAITING_MERGE_STEP", "awaiting-merge")):
            result = subprocess.run(
                [sys.executable, "-I", script, "--step", token, "--pr", "1"],
                cwd=other_cwd, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                ok = False
                fail(f"[{case}] --step {token} exited {result.returncode}: "
                    f"{result.stderr.strip()[-400:]}")
            elif '"step": "{0}"'.format(expected) not in result.stdout:
                ok = False
                fail(f"[{case}] --step {token} did not resolve to step={expected!r}: "
                    f"{result.stdout.strip()[:200]!r}")
        if ok:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(other_cwd, ignore_errors=True)


def selftest_shared_path_workdir_anchored_passes():
    case = "shared-path-workdir: an anchored or root-run _shared/ path passes"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        _write(tmp, ".github/workflows/anchored-shared-path.yml",
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        working-directory: sub\n        run: |\n"
               "          bash \"$GITHUB_WORKSPACE/.github/actions/_shared/auto-release-verdict.sh\" a\n"
               "          bash ${{ github.workspace }}/.github/actions/_shared/auto-release-verdict.sh a\n"
               "          cp ../e2e-source/.github/actions/_shared/x.sh .\n"
               "      - shell: bash\n        run: |\n"
               "          bash .github/actions/_shared/auto-release-verdict.sh a\n"
               # The workspace root written with a trailing slash is still
               # the root (#960 second review).
               "      - shell: bash\n        working-directory: ${{ github.workspace }}/\n        run: |\n"
               "          bash .github/actions/_shared/auto-release-verdict.sh a\n"
               "      - shell: bash\n        working-directory: $GITHUB_WORKSPACE/\n        run: |\n"
               "          bash .github/actions/_shared/auto-release-verdict.sh a\n")
        findings, hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "shared-path-workdir"]
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif hits:
            fail(f"[{case}] unexpected finding(s): {hits}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_shared_path_workdir_waivable():
    case = "shared-path-workdir: a waiver naming the check is accepted and suppresses it"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        path = ".github/workflows/waived-shared-path.yml"
        _write(tmp, path,
               "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
               "      - shell: bash\n        working-directory: sub\n        run: |\n"
               "          bash .github/actions/_shared/auto-release-verdict.sh a\n")
        _write(tmp, WAIVERS_PATH, json.dumps({"waivers": [{
            "file": path, "check": "shared-path-workdir",
            "pattern": "auto-release-verdict", "count": 1, "issue": "#1",
            "reason": "self-test"}]}))
        findings, hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "shared-path-workdir"]
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif hits:
            fail(f"[{case}] waived finding(s) still reported: {hits}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


SUBST_FALLBACK_WF = ("on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
                     "    steps:\n      - shell: bash\n        run: |\n")


def selftest_substitution_fallback_safe_shapes_pass():
    case = ("substitution-fallback: the assignment-level fallback, the test "
            "ternary (also opened on its own line, or continued past a "
            "blank line), `|| true` and a loop body's `||` pass")
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        _write(tmp, ".github/workflows/safe-subst.yml", SUBST_FALLBACK_WF +
               "          a=\"$(jq -c '.x' \"$f\" 2>/dev/null)\" || a='[]'\n"
               "          b=$(printf '%s' \"$r\" | jq length) || b=0\n"
               "          c=\"$([ \"$x\" = y ] && [ -n \"$z\" ] && echo true || echo false)\"\n"
               "          d=\"$(jq -r '.n' \"$f\" 2>/dev/null || true)\"\n"
               "          e=\"$(jq -r '.[]' \"$f\" | while read -r n; do\n"
               "            [ -d \"$n\" ] || printf '%s\\n' \"$n\"\n"
               "          done)\"\n"
               "          g=\"$(\n"
               "            [ -f \"$f\" ] &&\n\n"
               "            echo y || echo n\n"
               "          )\"\n")
        _write(tmp, ".github/actions/_shared/safe-subst.sh",
               "#!/usr/bin/env bash\n"
               "n=\"$(git rev-list --count \"$a..HEAD\" 2>/dev/null)\" || n=0\n")
        findings, hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "substitution-fallback"]
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif hits:
            fail(f"[{case}] unexpected finding(s): {hits}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_substitution_fallback_waivable():
    case = "substitution-fallback: a waiver naming the check suppresses it"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        path = ".github/workflows/waived-subst.yml"
        _write(tmp, path, SUBST_FALLBACK_WF +
               "          t=\"$(date -u -d \"$at\" +%s 2>/dev/null || echo 0)\"\n")
        _write(tmp, WAIVERS_PATH, json.dumps({"waivers": [{
            "file": path, "check": "substitution-fallback",
            "pattern": r"^date -u -d ", "count": 1, "issue": "#1",
            "reason": "self-test"}]}))
        findings, hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "substitution-fallback"]
        if hard:
            fail(f"[{case}] unexpected hard failure(s): {hard}")
        elif hits:
            fail(f"[{case}] waived finding(s) still reported: {hits}")
        else:
            note(f"[{case}] passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_substitution_fallback_line():
    """The finding names the substitution's own line, not the `run:` key."""
    case = "substitution-fallback: the finding names the substitution's line"
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        path = ".github/workflows/subst-line.yml"
        content = (SUBST_FALLBACK_WF + "          set -uo pipefail\n"
                   "          echo unrelated\n"
                   "          x=\"$(jq -c '.' \"$f\" || echo '[]')\"\n")
        _write(tmp, path, content)
        expected = content.splitlines().index(
            "          x=\"$(jq -c '.' \"$f\" || echo '[]')\"") + 1
        findings, _hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "substitution-fallback"]
        if [h.line for h in hits] != [expected]:
            fail(f"[{case}] expected one finding at line {expected}, got {hits}")
        else:
            note(f"[{case}] passed ({path}:{expected})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_substitution_fallback_line_one_line_block():
    """A one-line `run: |` body: the finding names the body's line, not
    the `run:` key one line above it."""
    case = ("substitution-fallback: a one-line `run: |` finding names the "
            "body's line")
    tmp = tempfile.mkdtemp(prefix="wc-single-home-")
    try:
        _clean_tree(tmp)
        path = ".github/workflows/subst-line-one.yml"
        body = "          x=\"$(jq -c '.' \"$f\" || echo '[]')\""
        content = SUBST_FALLBACK_WF + body + "\n"
        _write(tmp, path, content)
        expected = content.splitlines().index(body) + 1
        findings, _hard = evaluate(tmp)
        hits = [f for f in findings if f.check == "substitution-fallback"]
        if [h.line for h in hits] != [expected]:
            fail(f"[{case}] expected one finding at line {expected}, got {hits}")
        else:
            note(f"[{case}] passed ({path}:{expected})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def selftest_substitution_fallback_semantics():
    """Pins the rule's reason in a real bash: a command that prints and
    then fails makes the in-substitution fallback APPEND (#959's
    `[]\n[]`), and the assignment-level fallback REPLACE."""
    global BASH
    case = "substitution-fallback: in-$( ) appends, assignment-level replaces"
    if BASH is None:
        BASH = resolve_bash()
    script = ("emit() { echo '[]'; return 1; }\n"
              "a=\"$(emit || echo '[]')\"\n"
              "b=\"$(emit)\" || b='[]'\n"
              "printf '%s|%s' \"$a\" \"$b\"\n")
    out = subprocess.run([BASH, "-c", script], capture_output=True,
                         text=True).stdout
    if out != "[]\n[]|[]":
        fail(f"[{case}] expected '[]\\n[]|[]', got {out!r}")
    else:
        note(f"[{case}] passed")


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
        "          stop_decision_json=\"$(jq -n --slurpfile comments "
        "\"$RUNNER_TEMP/board-stop-check-comments.json\" '{comments: "
        "$comments[0]}' | python3 .github/scripts/board_stop_check.py)\"\n"
        "          cancel_run_id=\"$(jq -r '.cancel_run_id // empty' "
        "<<<\"$stop_decision_json\")\"\n"
        "          GH_TOKEN=\"$CANCEL_TOKEN\" gh run cancel "
        "\"$cancel_run_id\" -R \"$GITHUB_REPOSITORY\" 2>/dev/null || true\n")
    # #085 (research.md D7's third named self-test direction): fact 1
    # (references board_stop_check.py) with no fact 2 (no cancellation) is a
    # legitimate non-loop consumer -- e.g. a hypothetical dry-run reporter --
    # and must NOT be flagged.
    selftest_board_stop_check_no_cancel_no_finding()
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
    # #575: equivalent rewrites of the same splice -- each is a paste the
    # literal-spelling regex let through.
    for label, program in (
        ("parenthesised condition",
         "map(if (type==\"array\") then .[] else . end)"),
        ("reversed condition",
         "map(if \"array\"==type then .[] else . end)"),
        ("optional splice",
         "map(if type==\"array\" then .[]? else . end)"),
        ("parenthesised splice",
         "map(if type==\"array\" then (.[]) else . end)"),
        ("all four at once",
         "map(if (\"array\" == type) then (.[]?) else (.) end)"),
        ("elif arm",
         "map(if type==\"object\" then . "
         "elif type==\"array\" then .[] else . end)"),
    ):
        slug = label.replace(" ", "-")
        selftest_third_paste_fails(
            "transcript-normalise",
            f".github/workflows/third-normalise-{slug}.yml",
            "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - shell: bash\n        run: |\n"
            f"          jq -cs '{program}' \"$T\"\n")
    selftest_per_document_wrap_passes()
    # Code review of #940: each shape the five gate scripts and
    # wc_chain_stop_conditions.py carried before moving onto wc_gha_expr.
    for slug, body in (
        ("transpile", "e = expr.replace(\"&&\", \" and \")\n"),
        ("eval", "ok = eval(src, {\"__builtins__\": {}}, ctx)\n"),
        ("term-split",
         "TERM = re.compile(r\"(\\w+)\\s*(==|!=)\\s*'([^']*)'\")\n"
         "terms = expr.split(\"&&\")\n"),
        ("named-term-split",
         "TERM = re.compile(r\"(?P<lhs>\\w+)\\s*(?P<op>==|!=)\")\n"
         "for term in expr.split(\"&&\"):\n    pass\n"),
    ):
        selftest_third_paste_fails(
            "gha-expr-evaluator", f".github/scripts/verify-third-{slug}.py",
            "import re\n" + body)
    # specs/113-gh-callsite-locator FR-011: a second shell scanner -- both
    # signs together -- is caught; either sign alone is not.
    selftest_third_paste_fails(
        "gh-callsite-locator", ".github/scripts/verify-third-scanner.py",
        "import re\n"
        "HEREDOC = re.compile(r\"<<-?[ \\t]*\\\\?(['\\\"]?)([\\w]+)\\1\")\n"
        "def scan(text, i):\n"
        "    if text.startswith(\"$(\", i):\n        return i + 2\n")
    selftest_third_paste_passes(
        "gh-callsite-locator", ".github/scripts/verify-third-heredoc-only.py",
        "import re\n"
        "HEREDOC = re.compile(r\"<<-?[ \\t]*\\\\?(['\\\"]?)([\\w]+)\\1\")\n")
    selftest_third_paste_passes(
        "gh-callsite-locator", ".github/scripts/verify-third-subst-only.py",
        "def scan(text, i):\n    if text.startswith(\"$(\", i):\n        return i + 2\n")
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
        "branch-advance-capture", ".github/workflows/third-branch-advance.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          git fetch origin \"+refs/heads/$b:refs/remotes/origin/$b\"\n"
        "          commits=\"$(git rev-list --count \"$before..$after\")\"\n")
    selftest_third_paste_fails(
        "token-mint", ".github/workflows/third-token.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - id: mint\n        continue-on-error: true\n"
        "        uses: actions/create-github-app-token@v3\n"
        "      - shell: bash\n        env:\n"
        "          OUTCOME: ${{ steps.mint.outcome }}\n"
        "        run: echo hi\n")
    selftest_third_paste_fails(
        "review-finding-fingerprint",
        ".github/workflows/third-review-finding.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          python3 - <<'PYEOF'\n"
        "          import hashlib\n"
        "          fp = hashlib.sha256(\"{0}|{1}|{2}\".format(\n"
        "              issue_number, norm(title), norm(file_path)\n"
        "          ).encode(\"utf-8\")).hexdigest()\n"
        "          PYEOF\n")
    selftest_third_paste_fails(
        "fold-commit", ".github/workflows/third-fold-commit.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          jq --arg actor \"$ACTOR_LOGIN\" '\n"
        "            .stage = \"implement\"\n"
        "            | .pending_re_review_from = (((.pending_re_review_from "
        "// []) + (if $actor == \"\" then [] else [$actor] end)) | unique)\n"
        "          ' \"$SPEC_DIR/spec-meta.json\" > /tmp/m.json\n")
    selftest_third_paste_fails(
        "fold-dispatch", ".github/workflows/third-fold-dispatch.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          git fetch --quiet origin \"refs/heads/${SPEC_BRANCH}\" "
        "|| true\n")
    selftest_third_paste_fails(
        "marker-write", ".github/workflows/third-marker-write.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          python3 -c \"import sys; "
        "sys.path.insert(0, '.github/scripts'); "
        "from board_item_marker import write_marker; "
        "print(write_marker('stalled', 0, None, None, None))\"\n")
    selftest_third_paste_fails(
        "pr-branch", ".github/workflows/third-pr-branch.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - id: pr\n        shell: bash\n        run: |\n"
        "          set -uo pipefail\n"
        "          branch=\"$(gh pr view \"$PR_NUMBER\" -R "
        "\"$GITHUB_REPOSITORY\" --json headRefName --jq .headRefName)\"\n"
        "          { echo \"pr-number=$PR_NUMBER\"; echo \"branch=$branch\"; } "
        ">> \"$GITHUB_OUTPUT\"\n")
    selftest_third_paste_fails(
        "composite-checkout-order", ".github/workflows/third-checkout-order.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - id: pr\n        uses: ./.github/actions/_shared/resolve-pr-branch\n"
        "        with:\n          pr-number: 1\n"
        "      - uses: actions/checkout@v5\n")
    # fold leg-1: a root-workspace checkout does not populate a sidecar
    # directory -- a `./.wc-pristine-repo/...` reference preceded only by
    # an unrelated root checkout must still be caught, not waved through
    # by the mere presence of some earlier actions/checkout@ step.
    selftest_third_paste_fails(
        "composite-checkout-order",
        ".github/workflows/third-checkout-order-sidecar.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v5\n"
        "      - id: pr\n"
        "        uses: ./.wc-pristine-repo/.github/actions/_shared/resolve-pr-branch\n"
        "        with:\n          pr-number: 1\n")
    # fold leg-2 (issue #757, found by the code review of #683): a
    # path-scoped sidecar checkout placed before the job's root checkout
    # must be caught even with no local `uses: ./...` step at all -- the
    # root checkout's prepareExistingDirectory wipes the sidecar at run
    # time, not gate time.
    selftest_third_paste_fails(
        "composite-checkout-order",
        ".github/workflows/third-checkout-order-sidecar-before-root.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v5\n"
        "        with:\n          path: .wc-pristine-repo\n"
        "      - uses: actions/checkout@v5\n")
    # #889: a bare _shared/ helper path under a non-root working-directory
    # fails; the same step anchored at $GITHUB_WORKSPACE/ is clean (the
    # clean tree's harmless.yml carries no such step, so add one here).
    selftest_third_paste_fails(
        "shared-path-workdir", ".github/workflows/third-shared-path-workdir.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        working-directory: sub\n        run: |\n"
        "          bash .github/actions/_shared/auto-release-verdict.sh a b\n")
    selftest_third_paste_fails(
        "shared-path-workdir", ".github/workflows/third-shared-path-job-default.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
        "    defaults:\n      run:\n        working-directory: sub\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          source .github/actions/_shared/helper.sh\n")
    # #960 review: a `./`-prefixed bare path, and a workflow-level
    # defaults.run working-directory, are the same defect.
    selftest_third_paste_fails(
        "shared-path-workdir", ".github/workflows/third-shared-path-dot-slash.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        working-directory: sub\n        run: |\n"
        "          bash ./.github/actions/_shared/auto-release-verdict.sh a b\n")
    selftest_third_paste_fails(
        "shared-path-workdir", ".github/workflows/third-shared-path-workflow-default.yml",
        "on: push\ndefaults:\n  run:\n    working-directory: sub\n"
        "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        run: |\n"
        "          source .github/actions/_shared/helper.sh\n")
    # #960 third review: the filesystem root `/` is not the workspace
    # root, even though stripping its trailing slash leaves "".
    selftest_third_paste_fails(
        "shared-path-workdir", ".github/workflows/third-shared-path-fs-root.yml",
        "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - shell: bash\n        working-directory: /\n        run: |\n"
        "          bash .github/actions/_shared/auto-release-verdict.sh a b\n")
    selftest_shared_path_workdir_anchored_passes()
    selftest_shared_path_workdir_waivable()
    # #889/#959: a fallback printed inside the substitution -- the jq
    # case, the pipeline case, a multi-line gh call, a composite step, and
    # a _shared/ script -- fails.
    selftest_third_paste_fails(
        "substitution-fallback", ".github/workflows/third-subst-jq.yml",
        SUBST_FALLBACK_WF + "          hold_back=\"$(jq -c '[.[] | "
        "select(.held)]' \"$missing_file\" 2>/dev/null || echo '[]')\"\n")
    selftest_third_paste_fails(
        "substitution-fallback", ".github/workflows/third-subst-pipeline.yml",
        SUBST_FALLBACK_WF + "          set -o pipefail\n"
        "          n=\"$(printf '%s' \"$raw\" | jq 'length' 2>/dev/null "
        "|| printf 0)\"\n")
    selftest_third_paste_fails(
        "substitution-fallback", ".github/workflows/third-subst-multiline.yml",
        SUBST_FALLBACK_WF + "          prs=$(gh pr list --json number \\\n"
        "            --jq '.' 2>/dev/null \\\n"
        "            || echo '[]')\n")
    selftest_third_paste_fails(
        "substitution-fallback", ".github/actions/third-subst/action.yml",
        "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: |\n"
        "        echo \"json=$(jq -c . \"$P\" 2>/dev/null || printf '{}')\"\n")
    selftest_third_paste_fails(
        "substitution-fallback", ".github/actions/_shared/third-subst.sh",
        "#!/usr/bin/env bash\nx=\"$(gh api \"$u\" --jq .n || echo 0)\"\n")
    # A bare `||` ending a line continues the list: the fallback on the
    # next line is still inside the substitution.
    selftest_third_paste_fails(
        "substitution-fallback", ".github/workflows/third-subst-or-newline.yml",
        SUBST_FALLBACK_WF + "          n=\"$(jq length \"$f\" 2>/dev/null ||\n"
        "            echo 0)\"\n")
    selftest_third_paste_fails(
        "substitution-fallback",
        ".github/workflows/third-subst-or-comment.yml",
        SUBST_FALLBACK_WF + "          n=\"$(jq length \"$f\" 2>/dev/null || # none\n"
        "\n            echo 0)\"\n")
    # Not a test ternary: a non-test command (`jq`) runs before the last
    # `||`, so its output and the fallback's can both land.
    selftest_third_paste_fails(
        "substitution-fallback", ".github/workflows/third-subst-fake-ternary.yml",
        SUBST_FALLBACK_WF + "          v=\"$([ -f a ] || jq . f && echo y "
        "|| echo n)\"\n")
    selftest_substitution_fallback_safe_shapes_pass()
    selftest_substitution_fallback_waivable()
    selftest_substitution_fallback_line()
    selftest_substitution_fallback_line_one_line_block()
    selftest_substitution_fallback_semantics()
    selftest_composite_checkout_order_line_attribution()
    selftest_token_mint_line_attribution()
    selftest_board_stop_check_line_attribution()
    selftest_local_action_line_attribution()
    selftest_scoped_checkout_line_attribution()
    # Every per-step check that reports step_run_line() gets the same
    # decoy test, so one regressing to a first-text-match lookup fails here.
    for check_key, body in PER_STEP_LINE_CASES:
        selftest_per_step_line_attribution(check_key, body)
    selftest_waived_copy_passes()
    selftest_stale_waiver_fails()
    selftest_promotion_fails()
    selftest_missing_declared_home_fails_loud()
    selftest_marker_write_cli_resolves_symbolic_steps_under_dash_i()
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
