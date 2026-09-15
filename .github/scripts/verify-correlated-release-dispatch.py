#!/usr/bin/env python3
"""Gate 59 -- correlated, atomic release dispatch stays correlated and atomic.

specs/048-correlated-release-dispatch (FR-018, SC-005, Constitution VIII).
Following Gate 50/51's shape: a small, textual, line-based checker over the
raw YAML text of exactly two files -- not the derived published-stage set
(release.yml/auto-release.yml carry no workflow_call trigger, so they are
outside that set by construction; research.md D6) -- with its own
--self-test exercising each failure branch against an in-memory fixture.

THE FIVE CHECKS (contracts/regression-gate.md)
-----------------------------------------------
1. release.yml's run-name: references both inputs.version and
   inputs.attempt-token -- catches dropping the attempt token from the
   release run's title (FR-002).
2. release.yml's tag-time tip comparison (`git ls-remote origin
   "refs/heads/${DEFAULT_BRANCH}"`) sits strictly between the "Validate
   version and plan tags" and "Create tags" step markers -- catches the
   comparison being removed, or moved earlier into a request/checkout-time
   check instead of a tag-time one (FR-010a).
3. auto-release.yml's correlation step references a createdAt (or
   equivalent time-bound) comparison *and* an attempt-token match in the
   same step -- catches reintroducing recency-based or token-only
   selection (FR-001-FR-003).
4. auto-release.yml's outcome computation reads a `refs/tags/` comparison
   to decide `released`, never a run's `conclusion`/`status`/`gh run
   watch` -- catches letting a release be reported from a run conclusion
   instead of the tag state (FR-007, FR-007a).
5. auto-release.yml waits for the correlated run's own status (`gh run
   view ... --json status`) before ever fetching tag state -- catches
   reading tag state immediately after correlation, which can observe a
   correlated run still mid-flight (not yet tagged) and file a false
   "release dispatch failed" report moments before the release actually
   lands (T025, FR-018).

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

USAGE
-----
    python3 .github/scripts/verify-correlated-release-dispatch.py
    python3 .github/scripts/verify-correlated-release-dispatch.py --self-test
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import use_utf8_stdout  # noqa: E402

RELEASE_FILE = ".github/workflows/release.yml"
AUTO_RELEASE_FILE = ".github/workflows/auto-release.yml"

VALIDATE_MARKER = "name: Validate version and plan tags"
CREATE_TAGS_MARKER = "name: Create tags"
LS_REMOTE = "git ls-remote origin \"refs/heads/${DEFAULT_BRANCH}\""
RUN_LIST_MARKER = "gh run list --workflow=release.yml"
TOKEN_MATCH_MARKER = "[attempt:"
TAG_REV_PARSE = 'rev-parse -q --verify "refs/tags/'
TAG_FETCH_MARKER = 'git fetch origin "refs/tags/'
RUN_VIEW_MARKER = "gh run view"
STATUS_JSON_MARKER = "--json status"


def _find(lines, needle):
    for i, line in enumerate(lines):
        if needle in line:
            return i
    return None


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


def correlation_step_errors(auto_lines, path):
    """Check 3 -> [hit line, ::error] or []."""
    idx = _find(auto_lines, RUN_LIST_MARKER)
    if idx is None:
        return [f"::error::{path}'s dispatch-release job no longer calls "
                f"`{RUN_LIST_MARKER}` -- reintroduces recency-based "
                f"selection (the correlation search was removed, FR-001)."]
    window = auto_lines[idx:idx + 40]
    has_created_at = any("createdAt" in l for l in window)
    has_token_match = any(TOKEN_MATCH_MARKER in l for l in window)
    if has_created_at and has_token_match:
        return []
    return [f"{path}:{idx + 1}:{auto_lines[idx]}",
            "::error::auto-release.yml's correlation step must match on "
            "both a createdAt (time-bound) comparison and an attempt-token "
            "-- selecting on only one of them reintroduces recency-based "
            "selection (FR-001-FR-003)."]


def tag_state_outcome_errors(auto_lines, path):
    """Check 4 -> [hit line(s), ::error] or []."""
    has_tag_check = any(TAG_REV_PARSE in l for l in auto_lines)
    forbidden = [f"{path}:{i + 1}:{l}" for i, l in enumerate(auto_lines)
                 if "gh run watch" in l or ".conclusion" in l]
    if has_tag_check and not forbidden:
        return []
    out = list(forbidden)
    out.append("::error::auto-release.yml must decide `released` from a "
                f"'{TAG_REV_PARSE}...' comparison, never a run's "
                "conclusion/status -- lets a release be reported from a "
                "run conclusion instead of the tag state (FR-007, FR-007a).")
    return out


def wait_before_tag_read_errors(auto_lines, path):
    """Check 5 -> [hit line, ::error] or []."""
    idx = _find(auto_lines, TAG_FETCH_MARKER)
    if idx is None:
        return [f"::error::{path} no longer contains a "
                f"'{TAG_FETCH_MARKER}...' tag fetch -- update this gate "
                "alongside any rename."]
    window = auto_lines[:idx]
    has_run_view = any(RUN_VIEW_MARKER in l for l in window)
    has_status_json = any(STATUS_JSON_MARKER in l for l in window)
    if has_run_view and has_status_json:
        return []
    return [f"{path}:{idx + 1}:{auto_lines[idx]}",
            "::error::auto-release.yml must wait for the correlated run's "
            "status to reach a terminal state (a `gh run view ... --json "
            "status` poll) before this tag fetch -- reading tag state "
            "immediately after correlation can observe a correlated run "
            "still mid-flight and file a false dispatch-failed report "
            "(FR-018)."]


def contract_errors(release_lines, auto_lines, release_path, auto_path):
    return (run_name_errors(release_lines, release_path)
            + tag_time_check_errors(release_lines, release_path)
            + correlation_step_errors(auto_lines, auto_path)
            + tag_state_outcome_errors(auto_lines, auto_path)
            + wait_before_tag_read_errors(auto_lines, auto_path))


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
    out = contract_errors(release_lines, auto_lines, RELEASE_FILE, AUTO_RELEASE_FILE)
    for line in out:
        print(line)
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


def self_test():
    """Each check fails on the one mutation it exists to catch, naming only
    its own FR-018 clause, and passes on a fixture carrying every allowed
    form."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print(f"PASS {name}")
        else:
            failures += 1
            print(f"FAIL {name} {detail}")

    def errors_for(release_text, auto_text):
        return contract_errors(release_text.splitlines(), auto_text.splitlines(),
                                "release.yml", "auto-release.yml")

    out = errors_for(CLEAN_RELEASE, CLEAN_AUTO)
    check("the clean fixture passes all four checks", not out, f"got {out!r}")

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
    check("check 3: recency-only selection (token match dropped) fails, "
          "naming only its own clause",
          any("recency-based" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "run conclusion instead" in l for l in out),
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
    check("check 4: deciding `released` from a run's conclusion fails, "
          "naming only its own clause",
          any("run conclusion instead" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "recency-based" in l for l in out),
          f"got {out!r}")

    mutated = CLEAN_AUTO.replace(
        '          run_status="$(gh run view "$correlated_run_id" --json status --jq .status)"\n',
        "")
    check("check 5's mutation actually removes the pre-tag-fetch status wait",
          mutated != CLEAN_AUTO)
    out = errors_for(CLEAN_RELEASE, mutated)
    check("check 5: reading tag state with no prior status wait (a "
          "not-yet-tagged read) fails, naming only its own clause",
          any("still mid-flight" in l for l in out)
          and not any("drops the attempt token" in l
                      or "tag-time tip refusal" in l
                      or "recency-based" in l
                      or "run conclusion instead" in l for l in out),
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
