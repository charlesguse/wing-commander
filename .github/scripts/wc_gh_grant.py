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
    "strace", "ltrace", "busybox", "parallel", "find",
))
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
    return command_grants_gh(m.group(1).split(":", 1)[0])


def command_grants_gh(command):
    tokens = command.replace("'", " ").replace('"', " ").split()
    word = command_word(tokens)
    if word.rstrip("*") == "gh":
        return True
    if word in LAUNCHER_WORDS:
        return any(os.path.basename(t).rstrip("*;") == "gh" for t in tokens)
    return False
