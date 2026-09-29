#!/usr/bin/env python3
"""Gate — wing-commander-post-review-comment's own `run:` step emits
exactly the `gh api -X POST ... reviews -f event=COMMENT -F body=@<file>`
call against a stubbed `gh`, and board-loop.yml's reviewer job now calls
the composite rather than an inline `gh api` block
(specs/062-lifecycle-review-gate T012/T014).

WHY THIS EXISTS
---------------
This composite was extracted from board-loop.yml's reviewer job so
lifecycle-review-gate.yml's `review` job (US1) can become a second caller
without pasting the same `gh api -X POST .../reviews -f event=COMMENT`
call a second time. Running the SHIPPED step (via wc_shell_harness.run_step,
not a copy of it) is the whole point — a copy could sit green for weeks
while checking a filter that did not ship.

    python3 .github/scripts/verify-post-review-comment-composite.py
    python3 .github/scripts/verify-post-review-comment-composite.py --self-test
"""
import os
import re
import stat
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (find_step, resolve_bash, run_step,  # noqa: E402
                               use_utf8_stdout)

ACTION = ".github/actions/wing-commander-post-review-comment/action.yml"
STEP_NAME = "Post the review on the PR"
BOARD_LOOP_FILE = ".github/workflows/board-loop.yml"

GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" > "$GH_STUB_LOG"
for a in "$@"; do
  case "$a" in body=@*) cp "${a#body=@}" "$GH_STUB_BODY" ;; esac
done
exit 0
"""


def _write_gh_stub(bindir):
    path = os.path.join(bindir, "gh")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GH_STUB)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def run_composite_step(root=".", attribution=""):
    """Runs the shipped 'Post the review on the PR' step against a stubbed
    `gh`; returns (rc, output, gh_call_line, posted_body)."""
    bash = resolve_bash()
    step = find_step(os.path.join(root, ACTION), STEP_NAME)
    run = step.get("run") or ""

    workdir = tempfile.mkdtemp(prefix="wc-post-review-comment-")
    bindir = tempfile.mkdtemp(prefix="wc-post-review-comment-bin-")
    _write_gh_stub(bindir)
    log_path = os.path.join(workdir, "gh-call.log")

    env_extra = {
        "GITHUB_REPOSITORY": "owner/repo",
        "PR_NUMBER": "123",
        "BODY_FILE": os.path.join(workdir, "body.md"),
        "GH_STUB_LOG": log_path,
        "GH_STUB_BODY": os.path.join(workdir, "posted-body.md"),
        "ATTRIBUTION": attribution,
        "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
    }
    open(env_extra["BODY_FILE"], "w", encoding="utf-8").write("hello\n")

    rc, output, _outputs, _summary = run_step(
        bash, run, workdir, env_extra, workdir)

    gh_call = ""
    if os.path.isfile(log_path):
        gh_call = open(log_path, encoding="utf-8").read()
    posted = ""
    if os.path.isfile(env_extra["GH_STUB_BODY"]):
        posted = open(env_extra["GH_STUB_BODY"], encoding="utf-8").read()
    return rc, output, gh_call, posted


def board_loop_calls_composite(root="."):
    """True if board-loop.yml's reviewer job calls the composite (a
    `uses: ./.wc-pristine-repo/.github/actions/wing-commander-post-review-
    comment` step -- the trusted copy Gate 104 requires; a bare
    `./.github/...` path also counts here, Gate 104 rejects it) rather than
    its own inline `gh api -X POST .../reviews -f event=COMMENT`."""
    path = os.path.join(root, BOARD_LOOP_FILE)
    if not os.path.isfile(path):
        return False, False
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    doc = yaml.safe_load(text) or {}
    calls_composite = False
    has_inline = bool(re.search(
        r"gh api[^\n]*reviews[^\n]*-f event=COMMENT", text))
    for job in (doc.get("jobs") or {}).values():
        for step in (job or {}).get("steps") or []:
            uses = str((step or {}).get("uses") or "")
            if uses.strip().endswith(
                    ".github/actions/wing-commander-post-review-comment"):
                calls_composite = True
    return calls_composite, has_inline


def run():
    failures = 0

    rc, output, gh_call, posted = run_composite_step()
    if rc != 0:
        failures += 1
        print("::error::verify-post-review-comment-composite: the shipped "
              "step exited {0}: {1}".format(rc, output))

    call_line = gh_call.strip()
    if "-X POST" not in call_line or "repos/owner/repo/pulls/123/reviews" not in call_line:
        failures += 1
        print("::error::verify-post-review-comment-composite: expected a "
              "POST to the PR's reviews endpoint, got: {0!r}".format(call_line))
    if "-f event=COMMENT" not in call_line:
        failures += 1
        print("::error::verify-post-review-comment-composite: expected "
              "-f event=COMMENT, got: {0!r}".format(call_line))
    if "-F body=@" not in call_line:
        failures += 1
        print("::error::verify-post-review-comment-composite: expected a "
              "-F body=@<file> flag, got: {0!r}".format(call_line))
    if not failures:
        print("[ok] the shipped step calls gh api with exactly "
              "-f event=COMMENT -F body=@<body-file>: {0!r}".format(call_line))

    if posted != "hello\n":
        failures += 1
        print("::error::verify-post-review-comment-composite: with no "
              "attribution the posted body must be the body file unchanged, "
              "got: {0!r}".format(posted))

    # board-loop.yml's directed-proof-run attribution (FR-011), absorbed
    # from main's inline prepend: the line, a blank line, then the body.
    rc, output, _call, posted = run_composite_step(attribution="_Directed._")
    if rc != 0 or posted != "_Directed._\n\nhello\n":
        failures += 1
        print("::error::verify-post-review-comment-composite: attribution "
              "was not prepended as '<line>\\n\\n<body>' (rc={0}): "
              "{1!r}".format(rc, posted))
    else:
        print("[ok] a non-empty attribution is prepended before the body")

    calls_composite, has_inline = board_loop_calls_composite()
    if not calls_composite:
        failures += 1
        print("::error::verify-post-review-comment-composite: {0}'s "
              "reviewer job no longer calls wing-commander-post-review-"
              "comment.".format(BOARD_LOOP_FILE))
    if has_inline:
        failures += 1
        print("::error::verify-post-review-comment-composite: {0} still "
              "contains an inline 'gh api -X POST .../reviews -f "
              "event=COMMENT' call -- it must be replaced by the "
              "composite (CLAUDE.md's shared-logic rule).".format(BOARD_LOOP_FILE))
    if calls_composite and not has_inline:
        print("[ok] {0}'s reviewer job calls the composite and no longer "
              "carries an inline call.".format(BOARD_LOOP_FILE))

    print("verify-post-review-comment-composite: {0} failure(s).".format(failures))
    return 1 if failures else 0


def self_test():
    """A missing step name fails loudly (find_step's own sys.exit), and
    board_loop_calls_composite() distinguishes 'calls the composite' from
    'still has the inline call' in both directions."""
    failures = 0

    def check(name, cond, detail=""):
        nonlocal failures
        if cond:
            print("PASS {0}".format(name))
        else:
            failures += 1
            print("FAIL {0} {1}".format(name, detail))

    tmp = tempfile.mkdtemp(prefix="wc-post-review-comment-selftest-")

    # Fixture: calls the composite, no inline call.
    clean_dir = os.path.join(tmp, "clean")
    os.makedirs(os.path.join(clean_dir, ".github/workflows"), exist_ok=True)
    with open(os.path.join(clean_dir, BOARD_LOOP_FILE), "w", encoding="utf-8") as fh:
        fh.write(
            "on: push\njobs:\n  reviewer:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: ./.github/actions/wing-commander-post-review-comment\n"
            "        with:\n          token: x\n          pr-number: 1\n"
            "          body-file: b.md\n")
    calls_composite, has_inline = board_loop_calls_composite(clean_dir)
    check("clean fixture calls the composite", calls_composite)
    check("clean fixture carries no inline call", not has_inline)

    # Fixture: still has the inline call, no composite call.
    dirty_dir = os.path.join(tmp, "dirty")
    os.makedirs(os.path.join(dirty_dir, ".github/workflows"), exist_ok=True)
    with open(os.path.join(dirty_dir, BOARD_LOOP_FILE), "w", encoding="utf-8") as fh:
        fh.write(
            "on: push\njobs:\n  reviewer:\n    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: |\n"
            "          gh api -X POST \"repos/$R/pulls/$N/reviews\" "
            "-f event=COMMENT -F body=@b.md\n")
    calls_composite, has_inline = board_loop_calls_composite(dirty_dir)
    check("dirty fixture does not resolve as calling the composite", not calls_composite)
    check("dirty fixture's inline call is detected", has_inline)

    print("{0} failure(s).".format(failures))
    return 1 if failures else 0


def main(argv):
    use_utf8_stdout()
    if argv == ["--self-test"]:
        return self_test()
    if argv:
        sys.exit("unknown arguments {0!r}; takes --self-test or nothing.".format(argv))
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
