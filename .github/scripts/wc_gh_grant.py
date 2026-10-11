"""The one home of "does this Bash grant run `gh`?" (spec 101).

Gate 93 check 4b (verify-issue-context-single-home.py) and the diagnose
shadow gate (verify-diagnose-shadow-acts-on-nothing.py) both import it, so
the two detectors cannot drift (CLAUDE.md "Shared logic has exactly one
home").
"""
import os
import re

# Words that run another command. A grant that starts with one of these
# (after any `VAR=x` assignments) can reach `gh` through arguments that
# take their own values (`env -u X gh`, `sudo -u root gh`, `timeout 5 gh`,
# `bash -c 'gh ...'`), so for these the whole grant is searched for a `gh`
# word instead of trusting the first non-option token.
LAUNCHER_WORDS = frozenset((
    "env", "command", "exec", "sudo", "nohup", "time", "builtin", "xargs",
    "timeout", "nice", "ionice", "setsid", "stdbuf", "watch", "doas", "bash",
    "sh", "zsh", "dash", "eval", "script", "chroot", "unshare", "flock",
    "strace", "ltrace", "busybox", "parallel", "find", "su", "runuser",
    "nsenter", "systemd-run", "taskset", "numactl", "tmux", "ssh", "perl",
))
# Interpreters run whatever their code argument says: only a script path is
# safe to grant, so a `-c`/`-e` flag or no script at all can reach `gh`.
INTERPRETER_WORDS = frozenset((
    "bash", "sh", "zsh", "dash", "python", "python3", "perl", "ruby", "node",
))
CODE_FLAGS = frozenset(("-c", "-e", "-E", "-m", "-p"))
SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;&|\n`]|\$\(")
ENV_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
BASH_RE = re.compile(r"Bash\((.*)\)", re.S)


def command_word(tokens):
    """Basename of the first token that is not a `VAR=x` assignment."""
    for t in tokens:
        if ENV_ASSIGNMENT_RE.match(t):
            continue
        return os.path.basename(t)
    return ""


def grants_gh(tool):
    """True for a `Bash(...)` grant that runs `gh` in any spelling:
    `Bash(gh:*)`, `Bash(/usr/bin/gh ...)`, `Bash(env gh ...)`,
    `Bash(env -u X gh ...)`, `Bash(GH_TOKEN=x gh ...)`, `Bash(bash -c gh)`.
    `Bash(ls docs/gh:*)` runs `ls`, so it is not one."""
    m = BASH_RE.fullmatch(tool.strip())
    if not m:
        return False
    body = m.group(1)
    # Only a trailing `:*` (or bare `:`) is the prefix-match suffix; a colon
    # elsewhere (`PATH=/a:/b gh`) belongs to the command.
    open_ended = False
    for suffix in (":*", ":"):
        if body.endswith(suffix):
            body = body[:-len(suffix)]
            open_ended = True
            break
    return command_grants_gh(body, open_ended)


def command_grants_gh(command, open_ended=False):
    """`open_ended` is True when the grant ended in `:*`, so a launcher or
    interpreter with no further arguments can still be given any command."""
    for segment in SEGMENT_SPLIT_RE.split(command):
        if _segment_grants_gh(segment, open_ended):
            return True
    return False


def _segment_grants_gh(segment, open_ended):
    tokens = segment.replace("'", " ").replace('"', " ").split()
    word = command_word(tokens)
    if word.rstrip("*") == "gh":
        return True
    if word in LAUNCHER_WORDS or word in INTERPRETER_WORDS:
        if any(os.path.basename(t).rstrip("*;") == "gh" for t in tokens):
            return True
        args = tokens[[i for i, t in enumerate(tokens)
                       if os.path.basename(t) == word][0] + 1:]
        if word in INTERPRETER_WORDS:
            if any(a in CODE_FLAGS for a in args):
                return True
            if open_ended and not [a for a in args if not a.startswith("-")]:
                return True
        elif open_ended and not args:
            return True
    return False
