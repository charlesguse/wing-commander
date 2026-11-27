"""Bounded-time probe for a gate's regular expressions.

A gate's self-test calls `finishes(pattern, text)` with an input built to
make a backtracking-prone pattern take exponential time. The search runs
in a child interpreter, so a pattern that regresses fails its self-test
after `seconds` instead of hanging the job.

Used by verify-agent-startup-classifier.py, verify-hardened-push.py,
verify-snapshot-integrity-statement.py and verify-gate-suite-credential-free.py
(for wc_gate_suite_sites.SUITE_INVOCATION_RE).
"""
import subprocess
import sys

_SEARCH = "import re, sys; re.search(sys.argv[1], sys.argv[2], int(sys.argv[3]))"


def finishes(pattern, text, seconds=5.0):
    """True when the compiled `pattern` searches `text` within `seconds`."""
    try:
        subprocess.run([sys.executable, "-I", "-c", _SEARCH, pattern.pattern, text,
                        str(int(pattern.flags))],
                       timeout=seconds, check=True, capture_output=True)
    except subprocess.TimeoutExpired:
        return False
    return True
