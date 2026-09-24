#!/usr/bin/env python3
"""Gate 96 -- wing-commander-issue-context's trust-filter jq behaves
correctly (#499 code review round 4).

WHY THIS EXISTS
----------------
The composite's qualification rule (a comment counts only when
`user.type != "Bot"` AND (`author_association` is OWNER/MEMBER/
COLLABORATOR OR the comment's author is the issue's own author, by id))
had no behavioural coverage of its own -- Gate 93 checks that nothing
ELSE re-implements it, and Gate 27/47 check documentation agreement, but
nothing had ever run the shipped jq programs over real comment shapes and
checked the counts, the ordering, or the "nothing qualifies -> no file
written" contract. This gate EXECUTES the real "Fetch issue and comments,
apply the trust filter" step (read out of
wing-commander-issue-context/action.yml at run time, so there is no
second copy to drift) against a stubbed `gh` returning one issue and six
comments covering every branch of the rule.

WHAT IT CHECKS
--------------
Six comments: a Bot (excluded outright, never counted as excluded-human
either), a NONE-association non-author (excluded, DOES count as
excluded-human), the issue's own author commenting with NONE association
(qualifies via the id clause, not the association clause), and one each
of MEMBER/OWNER/COLLABORATOR (qualify via the association clause) --
submitted to the stub out of `created_at` order, so ordering in
comments.md/context.md is a real assertion, not an accident of input
order. Asserts: total-count, qualifying-count, excluded-human-count;
comments.md's sections appear in oldest-to-newest order and contain
exactly the four qualifying logins, never the excluded two; context.md
carries an "## Issue" section plus the same comment sections.

A second fixture (only the Bot and the NONE non-author comment) asserts
the zero-qualifying contract: comments-file is the empty string and
comments.md is NOT written at all (context.md still is, title+body only).

MUTATION: `or .user.id == $aid` dropped from all three jq programs (the
qualifying-count filter, the excluded-human-count filter, and the
comments.md template) -- the issue author's own NONE-association comment
must then stop qualifying, proving this gate would catch that clause
being silently dropped.

Usage: python3 .github/scripts/verify-issue-context-trust-filter.py
Requires: bash, jq. See wc_shell_harness.py for running this on Windows.
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (  # noqa: E402
    ensure_jq, find_step, resolve_bash, run_step, use_utf8_stdout)

ACTION = os.path.join(".github", "actions", "wing-commander-issue-context",
                      "action.yml")
STEP = "Fetch issue and comments, apply the trust filter"
BASH = None

REPOSITORY = "acme/widgets"
# PID-suffixed (#499 round 5 review, optional item): DIR below is
# /tmp/wing-commander/issue-context-<ISSUE>, and each fixture run() rm
# -rf's it afterward -- a fixed value would collide with a concurrent run
# of this same gate (or, in principle, a real issue of this number).
ISSUE = f"gate96-test-9999999-{os.getpid()}"
AUTHOR_ID = 1000
AUTHOR_LOGIN = "reporter"

ISSUE_JSON = json.dumps({
    "title": "Something is broken",
    "body": "Steps to reproduce...",
    "user": {"login": AUTHOR_LOGIN, "id": AUTHOR_ID, "type": "User"},
})


def _comment(login, uid, utype, assoc, created_at, body):
    return {
        "user": {"login": login, "id": uid, "type": utype},
        "author_association": assoc,
        "created_at": created_at,
        "body": body,
    }


# Deliberately out of created_at order in the array itself, so a harness
# that only checks membership (not ordering) could not pass vacuously.
#
# bot-member (#499 round 5 review): a Bot whose author_association is
# MEMBER, not NONE. Every other bot fixture here has NONE association, so
# it is excluded by BOTH the bot check and the association check --
# dropping `select(.user.type != "Bot")` from just the comments.md jq
# (leaving it in the two counting jqs) would go unnoticed, since the
# association check alone still excludes a NONE-association bot. A
# MEMBER-association bot passes the association check on its own, so it
# is excluded ONLY by the bot filter -- exactly what that specific
# mutation removes, and exactly what makes this fixture catch it.
ALL_COMMENTS = [
    _comment("some-bot", 9001, "Bot", "NONE", "2024-01-01T00:00:00Z", "bot noise"),
    _comment("collab1", 5000, "User", "COLLABORATOR", "2024-01-06T00:00:00Z", "collab note"),
    _comment(AUTHOR_LOGIN, AUTHOR_ID, "User", "NONE", "2024-01-02T00:00:00Z", "reporter followup"),
    _comment("rando", 2000, "User", "NONE", "2024-01-05T00:00:00Z", "random passerby"),
    _comment("member1", 3000, "User", "MEMBER", "2024-01-04T00:00:00Z", "member note"),
    _comment("owner1", 4000, "User", "OWNER", "2024-01-03T00:00:00Z", "owner note"),
    _comment("bot-member", 9002, "Bot", "MEMBER", "2024-01-07T00:00:00Z", "bot pretending to be a member"),
]
# Oldest -> newest among the four that qualify: reporter(02), owner1(03),
# member1(04), collab1(06). bot-member never qualifies despite its
# MEMBER association, and despite sorting after everything else.
EXPECTED_ORDER = [AUTHOR_LOGIN, "owner1", "member1", "collab1"]
EXPECTED_EXCLUDED_LOGINS = {"some-bot", "rando", "bot-member"}

ZERO_QUALIFYING_COMMENTS = [
    _comment("some-bot", 9001, "Bot", "NONE", "2024-01-01T00:00:00Z", "bot noise"),
    _comment("rando", 2000, "User", "NONE", "2024-01-05T00:00:00Z", "random passerby"),
]

STUB_GH_TEMPLATE = r'''#!/usr/bin/env bash
case "$*" in
  "api repos/%(repo)s/issues/%(issue)s")
    printf '%%s\n' '%(issue_json)s'
    exit 0
    ;;
  "api repos/%(repo)s/issues/%(issue)s/comments --paginate --jq .[]")
    printf '%%s\n' %(comment_lines)s
    exit 0
    ;;
  *)
    echo "gate-96 stub gh: unrecognized invocation: $*" >&2
    exit 1
    ;;
esac
'''


def _build_stub_gh(comments):
    lines = " ".join(f"'{json.dumps(c)}'" for c in comments)
    text = STUB_GH_TEMPLATE % {
        "repo": REPOSITORY,
        "issue": ISSUE,
        "issue_json": ISSUE_JSON,
        "comment_lines": lines,
    }
    return text


def run_fixture(script, comments, tmproot):
    workdir = tempfile.mkdtemp(dir=tmproot)
    runner_temp = tempfile.mkdtemp(dir=tmproot)
    bindir = tempfile.mkdtemp(dir=tmproot)
    dest_dir = f"/tmp/wing-commander/issue-context-{ISSUE}"
    gh_path = os.path.join(bindir, "gh")
    with open(gh_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_build_stub_gh(comments))
    os.chmod(gh_path, 0o755)
    env = {
        "GH_TOKEN": "dummy-token",
        "REPOSITORY": REPOSITORY,
        "ISSUE": ISSUE,
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    try:
        rc, out, outputs, _summary = run_step(BASH, script, workdir, env, runner_temp)
        comments_md = None
        comments_md_path = os.path.join(dest_dir, "comments.md")
        if os.path.isfile(comments_md_path):
            with open(comments_md_path, encoding="utf-8") as fh:
                comments_md = fh.read()
        context_md = None
        context_md_path = os.path.join(dest_dir, "context.md")
        if os.path.isfile(context_md_path):
            with open(context_md_path, encoding="utf-8") as fh:
                context_md = fh.read()
        return rc, out, outputs, comments_md, context_md
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(runner_temp, ignore_errors=True)
        shutil.rmtree(bindir, ignore_errors=True)
        shutil.rmtree(dest_dir, ignore_errors=True)


def check_full_fixture(script, label_prefix=""):
    failures = []
    tmproot = tempfile.mkdtemp()
    try:
        rc, out, outputs, comments_md, context_md = run_fixture(
            script, ALL_COMMENTS, tmproot)
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    prefix = f"{label_prefix}full fixture"
    if rc != 0:
        return [f"{prefix}: step exited {rc}: {out}"]

    if outputs.get("total-count") != "7":
        failures.append(f"{prefix}: total-count={outputs.get('total-count')!r}, expected '7'")
    if outputs.get("qualifying-count") != "4":
        failures.append(f"{prefix}: qualifying-count={outputs.get('qualifying-count')!r}, expected '4'")
    if outputs.get("excluded-human-count") != "1":
        failures.append(f"{prefix}: excluded-human-count={outputs.get('excluded-human-count')!r}, expected '1' (neither bot -- NONE-association or MEMBER-association -- may count as excluded-human)")

    if not comments_md:
        failures.append(f"{prefix}: comments.md was not written despite qualifying-count=4")
        return failures

    positions = [comments_md.find(f"@{login}") for login in EXPECTED_ORDER]
    if any(p == -1 for p in positions):
        failures.append(f"{prefix}: comments.md is missing one of {EXPECTED_ORDER}: {comments_md!r}")
    elif positions != sorted(positions):
        failures.append(
            f"{prefix}: comments.md's sections are not in oldest-to-newest "
            f"order {EXPECTED_ORDER} (positions {positions}): {comments_md!r}")
    for login in EXPECTED_EXCLUDED_LOGINS:
        if f"@{login}" in comments_md:
            failures.append(f"{prefix}: comments.md wrongly includes excluded commenter @{login}")

    if context_md is None:
        failures.append(f"{prefix}: context.md was not written")
    else:
        if "## Issue" not in context_md:
            failures.append(f"{prefix}: context.md has no '## Issue' section: {context_md!r}")
        for login in EXPECTED_ORDER:
            if f"@{login}" not in context_md:
                failures.append(f"{prefix}: context.md is missing @{login}'s comment section")
        for login in EXPECTED_EXCLUDED_LOGINS:
            if f"@{login}" in context_md:
                failures.append(f"{prefix}: context.md wrongly includes excluded commenter @{login}")
    return failures


def check_zero_qualifying_fixture(script, label_prefix=""):
    failures = []
    tmproot = tempfile.mkdtemp()
    try:
        rc, out, outputs, comments_md, context_md = run_fixture(
            script, ZERO_QUALIFYING_COMMENTS, tmproot)
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    prefix = f"{label_prefix}zero-qualifying fixture"
    if rc != 0:
        return [f"{prefix}: step exited {rc}: {out}"]

    if outputs.get("qualifying-count") != "0":
        failures.append(f"{prefix}: qualifying-count={outputs.get('qualifying-count')!r}, expected '0'")
    if outputs.get("comments-file", "") != "":
        failures.append(f"{prefix}: comments-file output is {outputs.get('comments-file')!r}, expected empty")
    if comments_md is not None:
        failures.append(f"{prefix}: comments.md WAS written despite zero qualifying comments: {comments_md!r}")
    if context_md is None:
        failures.append(f"{prefix}: context.md was not written")
    elif "## Issue" not in context_md:
        failures.append(f"{prefix}: context.md has no '## Issue' section: {context_md!r}")
    return failures


# --- Mutation: drop `or .user.id == $aid` from all three jq programs. ----

AUTHOR_ID_CLAUSE_RE = re.compile(r'\s*or \.user\.id == \$aid')


def mut_drop_author_id_clause(script):
    new_script, n = AUTHOR_ID_CLAUSE_RE.subn("", script)
    if n < 3:
        sys.exit(f"::error::verify-issue-context-trust-filter: expected at "
                 f"least 3 occurrences of the author-id clause in {ACTION}, "
                 f"found {n} -- the step text may have changed shape; "
                 f"update this harness alongside it.")
    return new_script


# --- Mutation: drop `select(.user.type != "Bot") | ` from ONLY the
# comments.md-writing jq (identified by its trailing `sort_by(.created_at)`,
# which is unique to that program among the composite's three -- the two
# counting jqs stay untouched, matching a plausible real regression where
# only the rendering jq drifts). #499 round 5 review. ------------------

COMMENTS_MD_BOT_FILTER_GOOD = (
    'select(.user.type != "Bot") | select(.author_association == "OWNER" '
    'or .author_association == "MEMBER" or .author_association == '
    '"COLLABORATOR" or .user.id == $aid)] | sort_by(.created_at)'
)
COMMENTS_MD_BOT_FILTER_BROKEN = (
    'select(.author_association == "OWNER" or .author_association == '
    '"MEMBER" or .author_association == "COLLABORATOR" or .user.id == '
    '$aid)] | sort_by(.created_at)'
)


def mut_drop_comments_md_bot_filter(script):
    if script.count(COMMENTS_MD_BOT_FILTER_GOOD) != 1:
        sys.exit(f"::error::verify-issue-context-trust-filter: expected "
                 f"exactly one occurrence of the comments.md jq's bot "
                 f"filter in {ACTION}, found "
                 f"{script.count(COMMENTS_MD_BOT_FILTER_GOOD)} -- the step "
                 f"text may have changed shape; update this harness "
                 f"alongside it.")
    return script.replace(COMMENTS_MD_BOT_FILTER_GOOD,
                          COMMENTS_MD_BOT_FILTER_BROKEN, 1)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    if not os.path.isfile(ACTION):
        sys.exit(f"::error::run this from the repository root; {ACTION} not found.")

    step = find_step(ACTION, STEP)
    if step is None:
        sys.exit(f"::error file={ACTION}::step {STEP!r} not found.")
    script = str(step["run"])
    if "${{" in script:
        sys.exit(f"::error file={ACTION}::the extracted run: block contains "
                 f"a ${{{{ }}}} expression this harness does not resolve.")

    failures = check_full_fixture(script)
    failures += check_zero_qualifying_fixture(script)

    mutated = mut_drop_author_id_clause(script)
    mutated_failures = check_full_fixture(mutated, label_prefix="mutation (author-id clause dropped): ")
    # The mutation must make the author's own NONE-association comment
    # stop qualifying -- i.e. the full-fixture assertions above (which
    # assume it qualifies) must now fail.
    if not mutated_failures:
        failures.append(
            "mutation (author-id clause dropped) did NOT change the full "
            "fixture's outcome -- this gate would not catch the author-id "
            "clause being silently dropped from the trust filter.")
    else:
        print(f"note: mutation (author-id clause dropped) confirmed "
              f"caught: {mutated_failures}")

    mutated_bot = mut_drop_comments_md_bot_filter(script)
    mutated_bot_failures = check_full_fixture(
        mutated_bot, label_prefix="mutation (comments.md bot filter dropped): ")
    # The mutation must let bot-member (Bot, MEMBER association) into
    # comments.md/context.md -- the two counting jqs are untouched, so
    # qualifying-count/excluded-human-count stay correct and only the
    # rendered-file assertions can catch this.
    if not mutated_bot_failures:
        failures.append(
            "mutation (comments.md bot filter dropped) did NOT change the "
            "full fixture's outcome -- this gate would not catch "
            "select(.user.type != \"Bot\") being silently dropped from "
            "just the comments.md-writing jq.")
    else:
        print(f"note: mutation (comments.md bot filter dropped) confirmed "
              f"caught: {mutated_bot_failures}")

    for f in failures:
        print(f"::error::Gate 96: {f}")
    if failures:
        print(f"Gate 96: {len(failures)} failure(s).")
        return 1
    print("Gate 96: the trust-filter jq's counts, ordering, and "
          "zero-qualifying contract all behave correctly, and dropping "
          "either the author-id clause or the comments.md bot filter is "
          "caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
