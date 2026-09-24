#!/usr/bin/env python3
"""Read-only git for board-loop.yml's read-only agent steps (#513).

WHY THIS EXISTS
---------------
triage-propose, route-propose and the reviewer are meant to be read-only.
They were granted `Bash(git log:*)`, `Bash(git diff:*)` and
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
- any short option starting with `-o` (`-o`, `-oFILE`). log/diff/show
  have no `-o` today; this keeps a later one from becoming a write.

Every argument is checked, including those after `--`: a path named like
one of these options is refused too.

The script runs git as `git --no-pager <subcommand> <args...>` and exits
with git's own status. A refused call exits 2 and runs nothing.

Gate 93 (verify-issue-context-single-home.py) fails if a read-only
board-loop agent is granted raw `Bash(git ...)`, and its `--self-test`
runs this script's refusal cases.
"""
import os
import sys

ALLOWED_SUBCOMMANDS = ("log", "diff", "show")
WRITE_OPTION = "output"
USAGE = ("usage: python3 .github/scripts/board_git_read.py "
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
        elif arg.startswith("-o"):
            return (f"refused: {arg!r} (-o can name an output file). "
                    f"This wrapper is read-only.")
    return None


def main(argv):
    reason = refusal(argv)
    if reason is not None:
        print(f"board_git_read: {reason}", file=sys.stderr)
        return 2
    os.execvp("git", ["git", "--no-pager", *argv])
    return 127  # not reached: execvp replaces this process or raises


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
