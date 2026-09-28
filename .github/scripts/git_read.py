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
An agent runs it with `python3 -I` (no PYTHON* environment, no script
directory on sys.path) by a path its job put a trusted copy at:
- board-loop.yml's triage-propose and route-propose run in a checkout of
  this repository's default branch, so they run
  `python3 -I .github/scripts/git_read.py`;
- board-loop.yml's reviewer runs in a checkout of a branch an agent
  wrote, so it runs the read-only snapshot its job takes from
  $GITHUB_SHA before any agent step (#583/#589):
  `python3 -I <runner.temp>/wc-pristine/scripts/git_read.py`;
- the published stages (workflow_call) check the pipeline repository out
  at `.wing-commander-pipeline` beside the consumer's tree, so their
  agents run
  `python3 -I .wing-commander-pipeline/.github/scripts/git_read.py`.
The relative paths are relative to the workspace, so every such agent
also has `cd`, `pushd` and `popd` denied. The step's grant and its prompt
must name the same path. Gate 93 (verify-issue-context-single-home.py)
checks both.

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
  `-poS` are refused;
- any long option that reads or runs something outside the repository's
  history, under any abbreviation or longer spelling: `--no-index`
  (diffs two arbitrary files, `.git/config` with its persisted token
  header included), `--ext-diff` and `--textconv` (run configured
  commands). `--text` stays allowed;
- for `diff`, any path argument outside the work tree (lexically or once
  symlinks resolve): given one, git diff compares plain files, an
  implicit `--no-index`. The wrapper also refuses to run outside a work
  tree at all, where every diff is one.
`log` and `show` read only objects, so a path outside the repository
there is an error, not a read.

Every argument is checked, including those after `--`: a path named like
one of these options is refused too.

The script runs git as `git --no-pager -c diff.external= -c
core.pager=cat <subcommand> --no-ext-diff --no-textconv <args...>`, with
GIT_EXTERNAL_DIFF, GIT_PAGER and every GIT_CONFIG* variable dropped from
its environment, and exits with git's own status. A refused call exits 2
and runs nothing.

Gate 93 (verify-issue-context-single-home.py) fails if a read-only
agent step in any workflow is granted raw `Bash(git ...)`, and its
`--self-test` runs this script's refusal cases.
"""
import os
import subprocess
import sys

ALLOWED_SUBCOMMANDS = ("log", "diff", "show")
WRITE_OPTION = "output"
# Long options refused because they read or run something outside the
# repository's object store: `--no-index` diffs two arbitrary files, and
# `--ext-diff`/`--textconv` run configured commands. Each is refused under
# every abbreviation git could accept (a prefix of the name) and every
# longer spelling (a name that starts with it). `--text` (-a) is a real
# option and a prefix of `textconv`, so a textconv abbreviation must be
# longer than `text` to be refused.
READ_OUTSIDE_OPTIONS = {"no-index": 1, "ext-diff": 1, "textconv": 5}
# Always passed: no external diff driver, no textconv filter, no pager.
GIT_GLOBAL_OPTIONS = ("--no-pager", "-c", "diff.external=",
                      "-c", "core.pager=cat")
SUBCOMMAND_OPTIONS = ("--no-ext-diff", "--no-textconv")
# Environment that could point git at another config, diff driver or
# pager. Dropped before git runs.
DROPPED_ENV = ("GIT_EXTERNAL_DIFF", "GIT_PAGER")
DROPPED_ENV_PREFIXES = ("GIT_CONFIG",)
USAGE = ("usage: python3 -I <pipeline checkout>/.github/scripts/git_read.py "
         "{log|diff|show} [<git options and arguments>...]")


def _outside(arg, cwd, toplevel):
    """Whether `arg`, read as a path from `cwd`, lies outside `toplevel`,
    lexically or once symlinks are resolved."""
    for resolve in (os.path.abspath, os.path.realpath):
        path = resolve(os.path.join(cwd, arg))
        top = resolve(toplevel)
        if path != top and not path.startswith(top.rstrip(os.sep) + os.sep):
            return True
    return False


def refusal(argv, cwd=None, toplevel=None):
    """Why `argv` (the arguments after the script name) is refused, or
    None when it may run. With `toplevel` (the work tree's root) and
    `cwd`, a `diff` path argument outside the work tree is refused too:
    git then diffs the two paths as plain files (an implicit
    `--no-index`), which reads any file, `.git/config` included."""
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
            for option, min_len in READ_OUTSIDE_OPTIONS.items():
                if len(name) >= min_len and (option.startswith(name)
                                             or name.startswith(option)):
                    return (f"refused: {arg!r} (--{option} or an "
                            f"abbreviation of it) reads or runs something "
                            f"outside the repository's history. This "
                            f"wrapper reads commits only.")
        elif arg.startswith("-") and _cluster_uses_o(arg[1:]):
            return (f"refused: {arg!r} uses -o, which can name an output "
                    f"file. This wrapper is read-only.")
    if subcommand == "diff" and toplevel is not None:
        for arg in argv[1:]:
            if arg == "--" or (arg.startswith("-") and arg != "-"):
                continue
            if _outside(arg, cwd or os.getcwd(), toplevel):
                return (f"refused: {arg!r} is outside the work tree, and "
                        f"git diff given such a path compares plain files "
                        f"(an implicit --no-index). This wrapper reads "
                        f"commits only.")
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


def clean_env(environ):
    """`environ` without the variables in DROPPED_ENV/DROPPED_ENV_PREFIXES."""
    return {k: v for k, v in environ.items()
            if k not in DROPPED_ENV
            and not k.startswith(DROPPED_ENV_PREFIXES)}


def command(argv):
    """The git command line a permitted `argv` runs."""
    return ["git", *GIT_GLOBAL_OPTIONS, argv[0], *SUBCOMMAND_OPTIONS,
            *argv[1:]]


def main(argv):
    env = clean_env(os.environ)
    reason = refusal(argv)
    if reason is None:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, env=env)
        if top.returncode != 0 or not top.stdout.strip():
            reason = ("refused: not inside a git work tree, where git diff "
                      "compares plain files. This wrapper reads commits "
                      "only.")
        else:
            reason = refusal(argv, os.getcwd(), top.stdout.strip())
    if reason is not None:
        print(f"git_read: {reason}", file=sys.stderr)
        return 2
    os.execvpe("git", command(argv), env)
    return 127  # not reached: execvpe replaces this process or raises


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
