#!/usr/bin/env python3
"""Whether an agent step may push: the one definition the gates share.

is_push_capable(step, steps_by_id) -> True when the agent step's composed
--allowedTools grant `Bash(git push:*)` as a whole comma-separated entry,
either inline (`--allowedTools "..."` in the step) or through the
`default-allowed-tools` of the wing-commander-tool-args step whose
`steps.<id>.outputs.allowed-tools` the step reads. A deny list
(`--disallowedTools "...,Bash(git push:*)"`) is not a grant.

Gate 122 (verify-agent-push-credential-helper.py) asks it which agent
steps need the stranded-commit rescue; Gate 121
(verify-commit-message-scratch-path.py) asks it which sites must render
the no-upstream push sentence (#1167). Gate 121 also fails if another
copy of this predicate reappears under .github/scripts/ (CLAUDE.md,
"Shared logic has exactly one home"): a second copy added for #1167
matched a bare `Bash(git push` substring and read a deny list as a grant.
Gate 80 (verify-spec-branch-push-concurrency.py) imports PUSH_GRANT_RE,
and Gate 121 fails on another module that spells the grant regex.
"""
import re

# The grant regex's own escaped spelling of the entry; Gate 121's check
# also fails on a module outside this one that spells it (a pasted copy
# of PUSH_GRANT_RE, as Gate 80 held until #889).
PUSH_GRANT_TOKEN = r"Bash\(git push:\*\)"
PUSH_GRANT_RE = re.compile(r"(?:^|,)\s*" + PUSH_GRANT_TOKEN + r"\s*(?:,|$)")
ALLOWED_TOOLS_REF_RE = re.compile(r"steps\.([\w-]+)\.outputs\.allowed-tools")
INLINE_ALLOWED_TOOLS_RE = re.compile(r"--allowedTools\s+\"([^\"]*)\"")

# The function names that make up the predicate; Gate 121's single-home
# check fails on a definition of any of them outside this module.
PREDICATE_NAMES = ("is_push_capable", "composed_allowed_tools", "grants_push")


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_strings(v)


def step_text(step):
    return "\n".join(walk_strings(step))


def composed_allowed_tools(step, steps_by_id):
    """-> the agent step's own composed --allowedTools text, or ''."""
    text = step_text(step)
    m = ALLOWED_TOOLS_REF_RE.search(text)
    if m:
        ref_step = steps_by_id.get(m.group(1))
        if ref_step is None:
            return ""
        return str((ref_step.get("with") or {}).get("default-allowed-tools", ""))
    m2 = INLINE_ALLOWED_TOOLS_RE.search(text)
    if m2:
        return m2.group(1)
    return ""


def is_push_capable(step, steps_by_id):
    return bool(PUSH_GRANT_RE.search(composed_allowed_tools(step, steps_by_id)))
