#!/usr/bin/env python3
"""Gate 59 -- correlated, atomic release dispatch stays correlated and atomic.

specs/048-correlated-release-dispatch (FR-018, SC-005, Constitution VIII).
Following Gate 50/51's shape: a small, textual, line-based checker over the
raw YAML text of exactly two files -- not the derived published-stage set
(release.yml/auto-release.yml carry no workflow_call trigger, so they are
outside that set by construction; research.md D6) -- with its own
--self-test exercising each failure branch against an in-memory fixture.

specs/081-composite-aware-dispatch-gate (contracts/resolving-gate.md)
widens checks 3 and 5 below: `auto-release.yml`'s `dispatch-release` job's
own steps are the subject, but a `uses: ./.github/actions/<name>` step in
that job is resolved one level deep -- its `runs.steps[*].run` shell is
spliced into the search corpus at the position the `uses:` step occupied,
tagged with the composite's own path -- so a pure relocation of the
correlation search or the wait-before-tag-read shell into a called
composite reads as a relocation, not a deletion. A `uses:` reference whose
`action.yml` does not exist on disk, or whose own steps defer to a SECOND
local composite with the checked construct absent at the first level, is
never treated as a pass: both fail loudly, naming the unresolvable path,
because the gate never opens more than one level, let alone a third file.
Check 4 (tag-state) stays scoped to the job's own text only, for both its
positive check and its forbidden-construct scan -- FR-027 requires the
tag-state invariant to live nowhere but `auto-release.yml`'s own job, so a
relocation of *that* shell into a composite is indistinguishable from a
deletion, by design (User Story 1 scenario 7).

THE FIVE CHECKS (contracts/regression-gate.md, contracts/resolving-gate.md)
----------------------------------------------------------------------------
1. release.yml's run-name: references both inputs.version and
   inputs.attempt-token -- catches dropping the attempt token from the
   release run's title (FR-002).
2. release.yml's tag-time tip comparison (`git ls-remote origin
   "refs/heads/${DEFAULT_BRANCH}"`) sits strictly between the "Validate
   version and plan tags" and "Create tags" step markers -- catches the
   comparison being removed, or moved earlier into a request/checkout-time
   check instead of a tag-time one (FR-010a).
3. auto-release.yml's `dispatch-release` job -- its own steps, plus the
   shell of any local composite those steps call one level deep -- contains
   a correlation step referencing a createdAt (or equivalent time-bound)
   comparison *and* an attempt-token match in the same step -- catches
   reintroducing recency-based or token-only selection (FR-001-FR-003).
4. auto-release.yml's `dispatch-release` job's OWN text (never a called
   composite's, FR-027) reads a `refs/tags/` comparison to decide
   `released`, never a run's `conclusion`/`status`/`gh run watch` --
   catches letting a release be reported from a run conclusion instead of
   the tag state (FR-007, FR-007a), and catches this invariant moving into
   a composite instead of being deleted outright.
5. auto-release.yml's `dispatch-release` job -- its own steps plus any
   called composite, same resolution as check 3 -- waits for the
   correlated run's own status (`gh run view ... --json status`) before
   ever fetching tag state (T025, FR-018).

A NOTE ON CHECK 2's ORDERING
-----------------------------
research.md D7 and contracts/regression-gate.md describe check 2 as
verifying the tip comparison's line number is *after* the "Create tags"
step's own marker. Read literally that would require the refusal to run
AFTER tags are created, which contradicts FR-010/FR-011/FR-014 ("refuses
-- creating no exact tag, no floating major tag") and task T011's own
placement (the refusal step sits between "Validate version and plan tags"
and "Create tags", so it necessarily runs, and appears in the file,
*before* "Create tags"). This script checks the invariant that is actually
correct and actually true of the shipped workflow: the comparison runs
after full validation and before any tag is mutated. See the lifecycle
issue for this discrepancy between the design docs and the functional
requirement they both cite.

A NOTE ON check 3's CORRELATION-CALL MARKER
---------------------------------------------
RUN_LIST_MARKER anchors the window checks 3 searches for a createdAt/
token-match pair. It intentionally does not include `release.yml` --
`wing-commander-dispatch-and-wait`'s composite shell (the one place check
3 must also resolve through, per above) parameterizes the dispatched
workflow file (`--workflow="$WORKFLOW_FILE"`), so a marker hardcoding
`release.yml` would never match the composite's own text. Dropping the
suffix is a pure widening: it is still a prefix of `auto-release.yml`'s
own current inline text, so nothing that passes today stops passing.

USAGE
-----
    python3 .github/scripts/verify-correlated-release-dispatch.py
    python3 .github/scripts/verify-correlated-release-dispatch.py --self-test
"""
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

RELEASE_FILE = ".github/workflows/release.yml"
AUTO_RELEASE_FILE = ".github/workflows/auto-release.yml"
DISPATCH_RELEASE_JOB = "dispatch-release"

VALIDATE_MARKER = "name: Validate version and plan tags"
CREATE_TAGS_MARKER = "name: Create tags"
LS_REMOTE = "git ls-remote origin \"refs/heads/${DEFAULT_BRANCH}\""
# See "A NOTE ON check 3's CORRELATION-CALL MARKER" above -- no `release.yml`
# suffix, so this also matches the generic composite's own shell.
RUN_LIST_MARKER = "gh run list --workflow="
TOKEN_MATCH_MARKER = "[attempt:"
TAG_REV_PARSE = 'rev-parse -q --verify "refs/tags/'
TAG_FETCH_MARKER = 'git fetch origin "refs/tags/'
RUN_VIEW_MARKER = "gh run view"
STATUS_JSON_MARKER = "--json status"

JOB_KEY_RE = re.compile(r"^  [A-Za-z_][\w-]*:\s*$")
USES_RE = re.compile(r"uses:\s*(\S+)")


def _find(lines, needle):
    for i, line in enumerate(lines):
        if needle in line:
            return i
    return None


def _find_tagged(corpus, needle):
    """Like _find, but over a (path, lineno, text) tuple corpus."""
    for i, (_path, _lineno, text) in enumerate(corpus):
        if needle in text:
            return i
    return None


def _is_local_composite(uses_value):
    return uses_value.startswith("./.github/actions/")


def _composite_action_path(uses_value):
    return uses_value[len("./"):] + "/action.yml"


def _composite_text(path, resolve):
    """The raw text of a local composite's action.yml, or None if it does
    not resolve. `resolve`, when given, stands in for the filesystem (an
    in-memory {path: text} map) so --self-test never touches real files."""
    if resolve is not None:
        return resolve.get(path)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _resolve_composite(path, resolve):
    """One level of `uses:` resolution (research.md D3).

    Returns None if the path does not resolve (hard-fail case a). Otherwise
    returns (lines, further_uses): `lines` is the composite's own
    `runs.steps[*].run` shell text, in step order; `further_uses` is the
    original `uses:` value of a second-level local composite reference
    found among the composite's own steps, or None. The gate never opens
    that second-level reference -- it is reported, not resolved.
    """
    text = _composite_text(path, resolve)
    if text is None:
        return None
    doc = yaml.safe_load(text) or {}
    steps = ((doc.get("runs") or {}).get("steps")) or []
    lines = []
    further_uses = None
    for step in steps:
        step = step or {}
        run_text = step.get("run")
        if run_text is not None:
            lines.extend(str(run_text).splitlines())
        uses_val = step.get("uses")
        if further_uses is None and isinstance(uses_val, str) and _is_local_composite(uses_val):
            further_uses = uses_val
    return lines, further_uses


def _job_lines(auto_lines, job_name):
    """The (start, end) index range of `job_name`'s own lines in `auto_lines`
    (job key line inclusive, up to but excluding the next top-level job key
    or EOF), or (None, None) if the job cannot be found."""
    start = None
    for i, line in enumerate(auto_lines):
        if line == f"  {job_name}:":
            start = i
            break
    if start is None:
        return None, None
    end = len(auto_lines)
    for i in range(start + 1, len(auto_lines)):
        if JOB_KEY_RE.match(auto_lines[i]):
            end = i
            break
    return start, end


def _second_level_error(further_uses):
    return (f"::error::the resolved composite itself defers to a further "
            f"local composite reference ({further_uses}) -- Gate 59 "
            f"resolves one level deep only and never opens a second file; "
            f"move the checked shell so it does not require a second "
            f"level, or update this gate.")


def run_name_errors(release_lines, path):
    """Check 1 -> [hit line, ::error] or []."""
    for i, line in enumerate(release_lines):
        if line.strip().startswith("run-name:"):
            if "inputs.version" in line and "inputs.attempt-token" in line:
                return []
            return [f"{path}:{i + 1}:{line}",
                    "::error::release.yml's run-name: must reference both "
                    "inputs.version and inputs.attempt-token -- drops the "
                    "attempt token from the release run's title (FR-002)."]
    return [f"::error::{path} declares no run-name: -- drops the attempt "
            f"token from the release run's title (FR-002)."]


def tag_time_check_errors(release_lines, path):
    """Check 2 -> [hit line(s), ::error] or []."""
    validate_idx = _find(release_lines, VALIDATE_MARKER)
    create_idx = _find(release_lines, CREATE_TAGS_MARKER)
    if validate_idx is None or create_idx is None:
        return [f"::error::{path}: could not locate the "
                f"'{VALIDATE_MARKER}' / '{CREATE_TAGS_MARKER}' step "
                f"markers -- update this gate alongside any rename."]
    for i in range(validate_idx + 1, create_idx):
        if LS_REMOTE in release_lines[i]:
            return []
    for i, line in enumerate(release_lines):
        if LS_REMOTE in line:
            return [f"{path}:{i + 1}:{line}",
                    "::error::release.yml's tag-time tip comparison must "
                    "run strictly between 'Validate version and plan tags' "
                    "and 'Create tags' -- outside that window it removes "
                    "the tag-time tip refusal (moved into a request/"
                    "checkout-time check instead, FR-010a)."]
    return ["::error::release.yml no longer contains a "
            f"'{LS_REMOTE}' comparison -- removes the tag-time tip "
            "refusal (FR-010a)."]


def correlation_step_errors(corpus, further_uses=None):
    """Check 3 -> [hit line, ::error] or []. `corpus` is a (path, lineno,
    text) tuple list -- auto-release.yml's dispatch-release job's own
    lines, with any resolved local composite spliced in (research.md D1)."""
    idx = _find_tagged(corpus, RUN_LIST_MARKER)
    if idx is None:
        if further_uses:
            return [_second_level_error(further_uses)]
        return [f"::error::{AUTO_RELEASE_FILE}'s dispatch-release job no "
                f"longer calls `{RUN_LIST_MARKER}` -- reintroduces "
                "recency-based selection (the correlation search was "
                "removed, FR-001)."]
    window = corpus[idx:idx + 40]
    has_created_at = any("createdAt" in text for _p, _l, text in window)
    has_token_match = any(TOKEN_MATCH_MARKER in text for _p, _l, text in window)
    if has_created_at and has_token_match:
        return []
    if further_uses:
        return [_second_level_error(further_uses)]
    path, lineno, text = corpus[idx]
    return [f"{path}:{lineno}:{text}",
            "::error::auto-release.yml's correlation step must match on "
            "both a createdAt (time-bound) comparison and an attempt-token "
            "-- selecting on only one of them reintroduces recency-based "
            "selection (FR-001-FR-003)."]


def tag_state_outcome_errors(job_corpus):
    """Check 4 -> [hit line(s), ::error] or []. `job_corpus` is the
    dispatch-release job's OWN lines only -- never a resolved composite's,
    per FR-027 -- so this shell moving into a composite reads as a
    deletion, same as removing it outright (User Story 1 scenario 7)."""
    has_tag_check = any(TAG_REV_PARSE in text for _p, _l, text in job_corpus)
    forbidden = [f"{path}:{lineno}:{text}" for path, lineno, text in job_corpus
                 if "gh run watch" in text or ".conclusion" in text]
    if has_tag_check and not forbidden:
        return []
    out = list(forbidden)
    out.append("::error::auto-release.yml must decide `released` from a "
                f"'{TAG_REV_PARSE}...' comparison, never a run's "
                "conclusion/status -- lets a release be reported from a "
                "run conclusion instead of the tag state (FR-007, FR-007a).")
    return out


def wait_before_tag_read_errors(corpus, further_uses=None):
    """Check 5 -> [hit line, ::error] or []. Same corpus as check 3."""
    idx = _find_tagged(corpus, TAG_FETCH_MARKER)
    if idx is None:
        return [f"::error::{AUTO_RELEASE_FILE} no longer contains a "
                f"'{TAG_FETCH_MARKER}...' tag fetch -- update this gate "
                "alongside any rename."]
    window = corpus[:idx]
    has_run_view = any(RUN_VIEW_MARKER in text for _p, _l, text in window)
    has_status_json = any(STATUS_JSON_MARKER in text for _p, _l, text in window)
    if has_run_view and has_status_json:
        return []
    if further_uses:
        return [_second_level_error(further_uses)]
    path, lineno, text = corpus[idx]
    return [f"{path}:{lineno}:{text}",
            "::error::auto-release.yml must wait for the correlated run's "
            "status to reach a terminal state (a `gh run view ... --json "
            "status` poll) before this tag fetch -- reading tag state "
            "immediately after correlation can observe a correlated run "
            "still mid-flight and file a false dispatch-failed report "
            "(FR-018)."]


def _find_local_uses(job_corpus):
    """The first (index, uses-value) of a local-composite `uses:` step in
    `job_corpus`, or (None, None) if the job calls no local composite."""
    for i, (_path, _lineno, text) in enumerate(job_corpus):
        m = USES_RE.search(text)
        if m and _is_local_composite(m.group(1)):
            return i, m.group(1)
    return None, None


def _evaluate(release_lines, auto_lines, release_path, auto_path, resolve=None):
    """Runs all five checks; returns (errors, attribution). `attribution`
    maps a passing check's own name to the tagged source that satisfied it
    (FR-005) -- populated only for checks that passed."""
    errors = list(run_name_errors(release_lines, release_path))
    errors += tag_time_check_errors(release_lines, release_path)
    attribution = {}

    job_start, job_end = _job_lines(auto_lines, DISPATCH_RELEASE_JOB)
    if job_start is None:
        errors.append(f"::error::could not locate the "
                      f"'{DISPATCH_RELEASE_JOB}:' job in {auto_path} -- "
                      f"update this gate alongside any rename.")
        return errors, attribution

    job_corpus = [(auto_path, job_start + i + 1, line)
                  for i, line in enumerate(auto_lines[job_start:job_end])]

    composite_idx, composite_uses = _find_local_uses(job_corpus)
    further_uses = None
    if composite_idx is None:
        corpus_3_5 = job_corpus
    else:
        composite_path = _composite_action_path(composite_uses)
        resolved = _resolve_composite(composite_path, resolve)
        if resolved is None:
            errors.append(
                f"::error::{auto_path}'s {DISPATCH_RELEASE_JOB} job calls "
                f"{composite_uses}, which does not exist -- unresolvable "
                f"composite reference.")
            errors += tag_state_outcome_errors(job_corpus)
            return errors, attribution
        comp_lines, further_uses = resolved
        comp_corpus = [(composite_path, i + 1, line)
                       for i, line in enumerate(comp_lines)]
        corpus_3_5 = (job_corpus[:composite_idx] + comp_corpus
                      + job_corpus[composite_idx + 1:])

    check3 = correlation_step_errors(corpus_3_5, further_uses)
    check4 = tag_state_outcome_errors(job_corpus)
    check5 = wait_before_tag_read_errors(corpus_3_5, further_uses)
    errors += check3 + check4 + check5

    if not check3:
        loc = _check_attribution(corpus_3_5, RUN_LIST_MARKER)
        if loc:
            attribution["check 3 (correlation)"] = loc
    if not check4:
        attribution["check 4 (tag-state)"] = auto_path
    if not check5:
        loc = _check_attribution(corpus_3_5, RUN_VIEW_MARKER)
        if loc:
            attribution["check 5 (wait-before-tag-read)"] = loc
    return errors, attribution


def _check_attribution(corpus, needle):
    idx = _find_tagged(corpus, needle)
    return corpus[idx][0] if idx is not None else None


def contract_errors(release_lines, auto_lines, release_path, auto_path, resolve=None):
    errors, _attribution = _evaluate(release_lines, auto_lines, release_path,
                                     auto_path, resolve)
    return errors


def _lines(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def run_gate():
    if not os.path.isfile(RELEASE_FILE) or not os.path.isfile(AUTO_RELEASE_FILE):
        print(f"::error::run this from the repository root; {RELEASE_FILE} "
              f"and {AUTO_RELEASE_FILE} must both exist.")
        return 1
    release_lines = _lines(RELEASE_FILE)
    auto_lines = _lines(AUTO_RELEASE_FILE)
    out, attribution = _evaluate(release_lines, auto_lines, RELEASE_FILE,
                                 AUTO_RELEASE_FILE)
    for line in out:
        print(line)
    for name, location in attribution.items():
        print(f"Gate 59: {name} satisfied in {location}")
    print(f"Gate 59: {RELEASE_FILE} and {AUTO_RELEASE_FILE} checked.")
    return 1 if out else 0


# A fixture exercising every allowed form of all four checks.
CLEAN_RELEASE = (
    'name: "release"\n'
    "on:\n"
    "  workflow_dispatch:\n"
    "    inputs:\n"
    "      version:\n"
    "        type: string\n"
    "      attempt-token:\n"
    "        type: string\n"
    'run-name: "release ${{ inputs.version }} [attempt:${{ inputs.attempt-token }}]"\n'
    "jobs:\n"
    "  release:\n"
    "    steps:\n"
    "      - name: Checkout\n"
    "        uses: actions/checkout@v5\n"
    "      - name: Validate version and plan tags\n"
    "        run: echo plan\n"
    "      - name: Refuse to tag unless the requested commit is still the branch tip\n"
    "        if: inputs.commit != ''\n"
    "        run: |\n"
    '          current_tip="$(git ls-remote origin "refs/heads/${DEFAULT_BRANCH}" | cut -f1)"\n'
    "      - name: Create tags\n"
    "        run: |\n"
    '          git tag -a "$TAG"\n')

CLEAN_AUTO = (
    "jobs:\n"
    "  dispatch-release:\n"
    "    steps:\n"
    "      - name: Dispatch release.yml and correlate its run\n"
    "        run: |\n"
    '          token="x"\n'
    '          rows="$(gh run list --workflow=release.yml --json databaseId,displayTitle,createdAt,url -L 20)"\n'
    '          case "$row_title" in\n'
    '            *"[attempt:${token}]"*) ;;\n'
    "          esac\n"
    '          created_epoch="$(date -u -d "$row_created" +%s)"\n'
    '          run_status="$(gh run view "$correlated_run_id" --json status --jq .status)"\n'
    '          git fetch origin "refs/tags/${VERSION}:refs/tags/${VERSION}"\n'
    '          if git rev-parse -q --verify "refs/tags/${VERSION}^{commit}" >/dev/null; then\n'
    "            tag_matches=true\n"
    "          fi\n")

# research.md D5: a resolved composite's shell carrying checks 3 and 5's
# allowed constructs, and the fixture whose dispatch-release job reaches it
# through a `uses:` step instead of inlining the shell.
DISPATCH_COMPOSITE_PATH = ".github/actions/wing-commander-dispatch-and-wait/action.yml"

CLEAN_COMPOSITE = (
    "runs:\n"
    "  using: composite\n"
    "  steps:\n"
    "    - name: Dispatch and correlate\n"
    "      run: |\n"
    '        rows="$(gh run list --workflow="$WORKFLOW_FILE" --json databaseId,displayTitle,createdAt,url -L 20)"\n'
    '        case "$row_title" in\n'
    '          *"[attempt:${ATTEMPT_TOKEN}]"*) ;;\n'
    "        esac\n"
    '        run_status="$(gh run view "$correlated_run_id" --json status --jq .status)"\n')

CLEAN_AUTO_VIA_COMPOSITE = (
    "jobs:\n"
    "  dispatch-release:\n"
    "    steps:\n"
    "      - name: Dispatch release.yml and correlate its run\n"
    "        uses: ./.github/actions/wing-commander-dispatch-and-wait\n"
    "      - name: Decide release outcome from tag state\n"
    "        run: |\n"
    '          git fetch origin "refs/tags/${VERSION}:refs/tags/${VERSION}"\n'
    '          if git rev-parse -q --verify "refs/tags/${VERSION}^{commit}" >/dev/null; then\n'
    "            tag_matches=true\n"
    "          fi\n")

RESOLVE_CLEAN_COMPOSITE = {DISPATCH_COMPOSITE_PATH: CLEAN_COMPOSITE}

# research.md D5 (d): check 4's shell relocated into a composite -- the ONE
# arrangement it must still fail in (FR-027) -- with checks 3/5 untouched
# (inline) so only the tag-state clause fires.
TAG_DECIDER_COMPOSITE_PATH = ".github/actions/wing-commander-tag-decider/action.yml"

TAG_DECIDER_COMPOSITE = (
    "runs:\n"
    "  using: composite\n"
    "  steps:\n"
    "    - name: Decide\n"
    "      run: |\n"
    '        git fetch origin "refs/tags/${VERSION}:refs/tags/${VERSION}"\n'
    '        if git rev-parse -q --verify "refs/tags/${VERSION}^{commit}" >/dev/null; then\n'
    "          tag_matches=true\n"
    "        fi\n")

CLEAN_AUTO_CHECK4_VIA_COMPOSITE = (
    "jobs:\n"
    "  dispatch-release:\n"
    "    steps:\n"
    "      - name: Dispatch release.yml and correlate its run\n"
    "        run: |\n"
    '          token="x"\n'
    '          rows="$(gh run list --workflow=release.yml --json databaseId,displayTitle,createdAt,url -L 20)"\n'
    '          case "$row_title" in\n'
    '            *"[attempt:${token}]"*) ;;\n'
    "          esac\n"
    '          run_status="$(gh run view "$correlated_run_id" --json status --jq .status)"\n'
    "      - name: Decide release outcome from tag state\n"
    "        uses: ./.github/actions/wing-commander-tag-decider\n")

RESOLVE_TAG_DECIDER = {TAG_DECIDER_COMPOSITE_PATH: TAG_DECIDER_COMPOSITE}

# research.md D5 (f): the job's composite resolves, but itself defers to a
# second-level local composite with no construct at the first level.
DEFERRING_COMPOSITE = (
    "runs:\n"
    "  using: composite\n"
    "  steps:\n"
    "    - name: Delegate further\n"
    "      uses: ./.github/actions/wing-commander-dispatch-and-wait-inner\n")

RESOLVE_DEFERRING_COMPOSITE = {DISPATCH_COMPOSITE_PATH: DEFERRING_COMPOSITE}


def self_test():
    """Each check fails on the one mutation it exists to catch, naming only
    its own FR-018 clause, and passes on a fixture carrying every allowed
    form -- inline (today's shape) or resolved through a called composite
    (specs/081-composite-aware-dispatch-gate)."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    def errors_for(release_text, auto_text, resolve=None):
        return contract_errors(release_text.splitlines(), auto_text.splitlines(),
                                "release.yml", "auto-release.yml", resolve)

    # (a) clean, fully inline (today's shape) -- passes.
    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO)
    check("the clean fixture passes all four checks", not out, f"got {out!r}")

    # (a, second half) clean, checks 3 & 5 relocated into a composite the
    # job calls -- passes (SC-001's first half).
    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO_VIA_COMPOSITE, RESOLVE_CLEAN_COMPOSITE)
    check("checks 3 & 5 relocated into a called composite still passes",
          not out, f"got {out!r}")
    _errs, attribution = _evaluate(
        CLEAN_RELEASE.splitlines(), CLEAN_AUTO_VIA_COMPOSITE.splitlines(),
        "release.yml", "auto-release.yml", RESOLVE_CLEAN_COMPOSITE)
    check("the composite-resolved pass attributes checks 3 & 5 to the "
          "composite's own path (FR-005)",
          attribution.get("check 3 (correlation)") == DISPATCH_COMPOSITE_PATH
          and attribution.get("check 5 (wait-before-tag-read)") == DISPATCH_COMPOSITE_PATH,
          f"got {attribution!r}")

    mutated = CLEAN_RELEASE.replace(
        ' [attempt:${{ inputs.attempt-token }}]', '')
    out = errors_for(mutated, CLEAN_AUTO)
    check("check 1: a run-name missing the attempt token fails, naming only "
          "its own clause",
          any("drops the attempt token" in l for l in out)
          and not any("tag-time tip refusal" in l or "recency-based" in l
                      or "run conclusion instead" in l for l in out),
          f"got {out!r}")

    mutated = CLEAN_RELEASE.replace(
        "      - name: Validate version and plan tags\n"
        "        run: echo plan\n"
        "      - name: Refuse to tag unless the requested commit is still the branch tip\n"
        "        if: inputs.commit != ''\n"
        "        run: |\n"
        '          current_tip="$(git ls-remote origin "refs/heads/${DEFAULT_BRANCH}" | cut -f1)"\n'
        "      - name: Create tags\n",
        "      - name: Refuse to tag unless the requested commit is still the branch tip\n"
        "        if: inputs.commit != ''\n"
        "        run: |\n"
        '          current_tip="$(git ls-remote origin "refs/heads/${DEFAULT_BRANCH}" | cut -f1)"\n'
        "      - name: Validate version and plan tags\n"
        "        run: echo plan\n"
        "      - name: Create tags\n")
    check("check 2's mutation actually reorders the step",
          mutated != CLEAN_RELEASE)
    out = errors_for(mutated, CLEAN_AUTO)
    check("check 2: the tip comparison moved before validation fails, "
          "naming only its own clause",
          any("tag-time tip refusal" in l for l in out)
          and not any("drops the attempt token" in l or "recency-based" in l
                      or "run conclusion instead" in l for l in out),
          f"got {out!r}")

    mutated = CLEAN_AUTO.replace(
        '          case "$row_title" in\n'
        '            *"[attempt:${token}]"*) ;;\n'
        "          esac\n", "")
    check("check 3's mutation actually removes the token match",
          mutated != CLEAN_AUTO)
    out = errors_for(CLEAN_RELEASE, mutated)
    check("check 3: recency-only selection (token match dropped), inline, "
          "fails naming only its own clause",
          any("recency-based" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "run conclusion instead" in l for l in out),
          f"got {out!r}")

    mutated_composite = CLEAN_COMPOSITE.replace(
        '        case "$row_title" in\n'
        '          *"[attempt:${ATTEMPT_TOKEN}]"*) ;;\n'
        "        esac\n", "")
    check("check 3's composite mutation actually removes the token match",
          mutated_composite != CLEAN_COMPOSITE)
    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO_VIA_COMPOSITE,
                      {DISPATCH_COMPOSITE_PATH: mutated_composite})
    check("check 3: recency-only selection (token match dropped), "
          "composite-resolved, fails naming only its own clause",
          any("recency-based" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "run conclusion instead" in l
                      or "still mid-flight" in l for l in out),
          f"got {out!r}")

    mutated = CLEAN_AUTO.replace(
        '          if git rev-parse -q --verify "refs/tags/${VERSION}^{commit}" >/dev/null; then\n'
        "            tag_matches=true\n"
        "          fi\n",
        '          if gh run watch "$run_id" --exit-status; then\n'
        "            tag_matches=true\n"
        "          fi\n")
    check("check 4's mutation actually swaps the tag check for a run watch",
          mutated != CLEAN_AUTO)
    out = errors_for(CLEAN_RELEASE, mutated)
    check("check 4: deciding `released` from a run's conclusion, inline, "
          "fails naming only its own clause",
          any("run conclusion instead" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "recency-based" in l for l in out),
          f"got {out!r}")

    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO_CHECK4_VIA_COMPOSITE,
                      RESOLVE_TAG_DECIDER)
    check("check 4: the tag-state shell relocated into a composite fails "
          "naming only its own clause -- a relocation of THIS invariant is "
          "indistinguishable from a deletion, by design (FR-027, scenario 7)",
          any("run conclusion instead" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "recency-based" in l
                      or "still mid-flight" in l for l in out),
          f"got {out!r}")

    mutated = CLEAN_AUTO.replace(
        '          run_status="$(gh run view "$correlated_run_id" --json status --jq .status)"\n',
        "")
    check("check 5's mutation actually removes the pre-tag-fetch status wait",
          mutated != CLEAN_AUTO)
    out = errors_for(CLEAN_RELEASE, mutated)
    check("check 5: reading tag state with no prior status wait, inline, "
          "fails naming only its own clause",
          any("still mid-flight" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "recency-based" in l
                      or "run conclusion instead" in l for l in out),
          f"got {out!r}")

    mutated_composite = CLEAN_COMPOSITE.replace(
        '        run_status="$(gh run view "$correlated_run_id" --json status --jq .status)"\n',
        "")
    check("check 5's composite mutation actually removes the pre-tag-fetch "
          "status wait",
          mutated_composite != CLEAN_COMPOSITE)
    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO_VIA_COMPOSITE,
                      {DISPATCH_COMPOSITE_PATH: mutated_composite})
    check("check 5: reading tag state with no prior status wait, "
          "composite-resolved, fails naming only its own clause",
          any("still mid-flight" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "recency-based" in l
                      or "run conclusion instead" in l for l in out),
          f"got {out!r}")

    # (e) the job's uses: names a composite path that does not exist --
    # fails loudly naming that path, never a pass (SC-004, D3 case 1).
    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO_VIA_COMPOSITE, {})
    check("an unresolvable composite reference fails loudly, naming the "
          "exact path, never a pass (SC-004)",
          bool(out) and any(
              "./.github/actions/wing-commander-dispatch-and-wait" in l
              and "does not exist" in l for l in out),
          f"got {out!r}")

    # (f) the job's composite resolves, but itself defers to a second-level
    # uses: with no construct at the first level -- fails loudly naming the
    # second-level reference (D3 case 3).
    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO_VIA_COMPOSITE,
                      RESOLVE_DEFERRING_COMPOSITE)
    check("a composite that defers to a second-level local composite fails "
          "loudly, naming that second-level reference, without opening it",
          bool(out) and any(
              "./.github/actions/wing-commander-dispatch-and-wait-inner" in l
              for l in out),
          f"got {out!r}")

    print(f"{failures} failure(s).")
    return 1 if failures else 0


def main(argv):
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit(f"unknown arguments {argv!r}; takes --self-test or nothing.")
    return run_gate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
