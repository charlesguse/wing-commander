#!/usr/bin/env python3
"""Single home of the review-finding triage rule (spec 128).

Sort each finding by the first of these that fits:

1. fix-now  -- a reviewer finding that is in scope.
2. record   -- out of scope and it can fail *silently* (with a one-line
               description of how); or important/security; or the class is
               unreadable (fail toward visibility).
3. drop     -- out of scope and it can only fail loudly, or cannot change
               any output at all.
4. reject   -- claims to fail silently but gives no one-line description.

Pure: no I/O, no environment, no network. Both call sites (the lifecycle
review gate and the stage-findings composite) import this module; neither
reimplements the rule (verify-finding-triage-report.py enforces that).
"""

REASON_IN_SCOPE = "in scope"
REASON_SILENT = "can fail silently"
REASON_NEVER_DROPPED = "never dropped (important/security)"
REASON_UNREADABLE = "class unreadable"
REASON_LOUD = "fails loudly"
REASON_NONE = "no output change"
REASON_REJECT = "silent, no description"

CLASSES = ("silent", "loud", "none")


def _description(finding):
    """The one-line silent description, or None when absent/empty/multi-line."""
    text = finding.get("silent_description")
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text or "\n" in text or "\r" in text:
        return None
    return text


def _never_dropped(finding):
    return finding.get("severity") == "important" or finding.get("security") is True


def route(finding, in_scope):
    """-> (outcome, reason); outcome in fix-now / record / drop / reject."""
    if in_scope is True:
        return "fix-now", REASON_IN_SCOPE
    cls = finding.get("failure_class")
    if cls == "silent":
        if _description(finding) is None:
            return "reject", REASON_REJECT
        return "record", REASON_SILENT
    if _never_dropped(finding):
        return "record", REASON_NEVER_DROPPED
    if cls == "loud":
        return "drop", REASON_LOUD
    if cls == "none":
        return "drop", REASON_NONE
    return "record", REASON_UNREADABLE


def route_all(findings, in_scope_of):
    """-> [(finding, outcome, reason)]; `in_scope_of(finding)` gives the flag."""
    out = []
    for finding in findings:
        outcome, reason = route(finding, in_scope_of(finding))
        out.append((finding, outcome, reason))
    return out


def _code_span(title):
    text = str(title).replace("`", "").replace("<!--", "< !--")
    text = " ".join(text.split())
    return "`" + text + "`"


def render_triaged(records):
    """Markdown, one line per drop/reject record; "" if none.

    Each record is a dict with title, outcome and reason.
    """
    lines = []
    for rec in records:
        outcome = rec.get("outcome")
        if outcome == "drop":
            lines.append("- {0} -- dropped: {1}".format(
                _code_span(rec.get("title", "")), rec.get("reason", "")))
        elif outcome == "reject":
            lines.append("- {0} -- rejected: silent, no description".format(
                _code_span(rec.get("title", ""))))
    return "\n".join(lines)


def silent_note(finding):
    """The one-line description for a recorded finding's body, else None."""
    if finding.get("failure_class") != "silent":
        return None
    return _description(finding)
