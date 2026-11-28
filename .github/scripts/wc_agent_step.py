#!/usr/bin/env python3
"""Which workflow step is an agent step -- decided once, for Gates 23 and 50.

Gate 23 (verify-gate-23.py) asserts every agent step carries the turn-
budget protection; Gate 50 (verify-release-contract.py) asserts every
agent step declares `--model ` and `--max-turns ` (constitution II). They
used to answer "is this an agent step" differently: Gate 23 YAML-parsed
the step and required `--max-turns` inside `claude_args`, while Gate 50
counted `uses: anthropics/claude-code-action` lines and flag mentions
textually, comments included. agent-startup-check.yml's credential-less
start-up step therefore passed Gate 50 only through a comment carrying
both flags (#889, folded from #1008). The owner's decision (2026-11-28):
one predicate, here, and Gate 50 stops counting comments.

THE PREDICATE
-------------
A step is an agent step when its `uses` starts with
`anthropics/claude-code-action` AND it can reach a model: either its
`claude_args` (comments stripped) carries `--max-turns`, or its `with:`
supplies a model credential (CREDENTIAL_INPUTS). The first arm is Gate
23's old scope, kept whole. The second keeps what Gate 50's count used to
catch: a credentialed step that lost its `--max-turns` is still an agent
step, so both gates fail it instead of it leaving both gates' scope. A
step with neither -- the start-up check's action setup, which has no
credential and sends no prompt to a model -- is not an agent step for
either gate.

verify-release-contract.py's self-test fails if a second copy of the
`--max-turns`-in-`claude_args` test appears in any other script under
.github/scripts/ (CLAUDE.md "Shared logic has exactly one home").

Usage:
  from wc_agent_step import is_agent_step, claude_args_text
"""
import re

AGENT_USES_PREFIX = "anthropics/claude-code-action"

# The claude-code-action inputs that hand the action a way to reach a
# model. A non-empty value on any one of them makes the step an agent step.
CREDENTIAL_INPUTS = ("anthropic_api_key", "claude_code_oauth_token",
                     "use_bedrock", "use_vertex", "use_foundry")

# A shell comment inside a claude_args block: a `#` that starts a word,
# through the end of its line. A `#` inside a word (`foo#bar`) is not one.
_SHELL_COMMENT = re.compile(r"(^|\s)#[^\n]*")


def strip_shell_comments(text):
    """`text` with every shell comment removed, line structure kept."""
    return _SHELL_COMMENT.sub(r"\1", text or "")


def _with(step):
    w = (step or {}).get("with") if isinstance(step, dict) else None
    return w if isinstance(w, dict) else {}


def claude_args_text(step):
    """The step's `claude_args`, YAML comments already gone (the parser
    drops them) and shell comments stripped."""
    return strip_shell_comments(str(_with(step).get("claude_args") or ""))


def has_model_credential(step):
    w = _with(step)
    return any(str(w.get(k) or "").strip() for k in CREDENTIAL_INPUTS)


def is_agent_step(step):
    """True for a parsed workflow step that runs claude-code-action against
    a model -- see the module docstring for why each arm is there."""
    if not isinstance(step, dict):
        return False
    if not str(step.get("uses") or "").startswith(AGENT_USES_PREFIX):
        return False
    return "--max-turns" in claude_args_text(step) or has_model_credential(step)
