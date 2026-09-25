#!/usr/bin/env python3
"""Read-only git for the pipeline's read-only agent steps (#513, #518).

WHY THIS EXISTS
---------------
Some agent steps are meant to be read-only: board-loop.yml's
triage-propose, route-propose and reviewer, implement.yml's progress
composer, watchdog.yml's diagnose and pr-conversation.yml's classify.
They were granted `Bash(git log:*)`, `Bash(git diff:*)` and/or
`Bash(git show:*)`, and each of those subcommands takes `--output=<path>`
(or `--output <path>`), which writes the command's output to any path the
runner user can write. For example:

    git log -1 --format='format:ANYTHING' --output=/any/path

Claude Code's Bash rules match the command text as a prefix, so an allow
rule for `git log` allows `git log ... --output=...` too (confirmed with
Claude Code 2.1.282 in `-p` mode). A deny rule cannot close it reliably
either: it has to spell every form the option can take. So these agents
get no raw git grant at all. They get this script, which runs only
`git log`, `git diff` or `git show` and refuses any argument that could
name a file to write.

WHERE IT LIVES AND HOW AGENTS REACH IT
--------------------------------------
This file is the one copy (#518 moved it here from board_git_read.py).
An agent runs it by the path its job checked the pipeline out at,
relative to the workspace:
- board-loop.yml runs in this repository's own checkout, so its agents
  run `python3 .github/scripts/git_read.py`;
- the published stages (workflow_call) check the pipeline repository out
  at `.wing-commander-pipeline` beside the consumer's tree, so their
  agents run `python3 .wing-commander-pipeline/.github/scripts/git_read.py`.
The step's grant and its prompt must name the same path. Gate 93
(verify-issue-context-single-home.py) checks the grant.

WHAT IT REFUSES
---------------
- any subcommand other than log, diff or show (and no global options: the
  subcommand must be the first argument, so `-c`, `-C` and `--git-dir`
  cannot come first);
- any long option whose name is a prefix of `output` (`--o`, `--out`,
  `--outp=...`, `--output`, `--output=...`), or that starts with `output`
  (`--output-indicator-new=+` and the like). Git 2.43's log/diff/show
  accept only the exact `--output`, but git's parse-options library
  accepts unambiguous prefixes of long options in other commands, so a
  later git could accept `--outp=` here too;
- any short option cluster (one `-`, not `--`) in which `o` is used as
  an option letter: `-o`, `-oFILE`, `-po`. log/diff/show have no `-o`
  today; this keeps a later one from becoming a write. The cluster is
  read left to right, and scanning stops at the first letter in
  VALUE_LETTERS, because the rest of the cluster is that option's value
  (`-Sfoo`, `-Gfoo.*`, `-U3`, `-L1,5:foo.py`, `-Oorderfile`). So
  `-Sfoo` and `-pSfoo` pass (the `o` is pickaxe text), but `-po` and
  `-poS` are refused.

Every argument is checked, including those after `--`: a path named like
one of these options is refused too.

The script runs git as `git --no-pager <subcommand> <args...>` and exits
with git's own status. A refused call exits 2 and runs nothing.

Gate 93 (verify-issue-context-single-home.py) fails if a read-only
agent step in any workflow is granted raw `Bash(git ...)`, and its
`--self-test` runs this script's refusal cases.
"""
import os
import sys

ALLOWED_SUBCOMMANDS = ("log", "diff", "show")
WRITE_OPTION = "output"
USAGE = ("usage: python3 <pipeline checkout>/.github/scripts/git_read.py "
         "{log|diff|show} [<git options and arguments>...]")


def refusal(argv):
    """Why `argv` (the arguments after the script name) is refused, or
    None when it may run."""
    if not argv:
        return USAGE
    subcommand = argv[0]
    if subcommand not in ALLOWED_SUBCOMMANDS:
        return (f"refused: {subcommand!r} is not one of "
                f"{', '.join(ALLOWED_SUBCOMMANDS)}. {USAGE}")
    for arg in argv[1:]:
        if arg.startswith("--"):
            name = arg[2:].split("=", 1)[0]
            if name and (WRITE_OPTION.startswith(name)
                         or name.startswith(WRITE_OPTION)):
                return (f"refused: {arg!r} can write a file (git's "
                        f"--output option or an abbreviation of it). "
                        f"This wrapper is read-only.")
        elif arg.startswith("-") and _cluster_uses_o(arg[1:]):
            return (f"refused: {arg!r} uses -o, which can name an output "
                    f"file. This wrapper is read-only.")
    return None


# Short options of git log/diff/show whose value is the rest of the
# cluster (`-S<string>`, `-G<regex>`, `-U<n>`, `-M<n>`, `-C<n>`,
# `-B<n>/<m>`, `-l<n>`, `-O<orderfile>`, `-X<param>`, `-I<regex>`,
# `-L<range>:<file>`, `-n<number>`). An `o` after one of them is part of
# the value, not an option letter.
VALUE_LETTERS = frozenset("SGUMCBlOXILn")


def _cluster_uses_o(letters):
    for letter in letters:
        if letter == "o":
            return True
        if letter in VALUE_LETTERS:
            return False
    return False


def main(argv):
    reason = refusal(argv)
    if reason is not None:
        print(f"git_read: {reason}", file=sys.stderr)
        return 2
    os.execvp("git", ["git", "--no-pager", *argv])
    return 127  # not reached: execvp replaces this process or raises


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
