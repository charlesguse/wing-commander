#!/usr/bin/env python3
"""Fixture check for pr-conversation.yml's relay-confirmation matching.

WHY THIS EXISTS
---------------
The relayed-request resume path (T047/T054, FR-022) used to trigger on a
bare substring match for "confirm" over the whole comment body. Two separate
places did it: `classify-and-announce`'s "Check for relay confirmation" step
(a `grep -qiE`) and `act`'s "Relayed-request risk-confirmation gate" (a jq
`test(...)`).

That is not a narrow bug. When it matched, the resume path SKIPPED THE
CLASSIFY AGENT ENTIRELY and re-announced/re-acted on a stored classification
instead — so an ordinary "can you confirm CI is green?" left the
maintainer's actual request unclassified, unanswered, and un-routed, while
mutating the repository in a way nobody had just asked for (T069).

The fix makes resume opt-in on an explicit phrase that the risk-warning
comment itself states verbatim. Three things have to stay true, and none of
them are self-evident from reading either expression alone:

  1. the phrase the risk-warning comment TELLS the maintainer to reply with
  2. the phrase `classify-and-announce` triggers resume on
  3. the phrase `act`'s risk gate accepts as confirmation

If any one drifts, relay confirmation either silently never resumes
(deadlock: the stage keeps re-asking forever) or goes back to firing on
incidental words. So this checks all three against the same fixture bodies.

Drift-proofing: all three expressions are EXTRACTED from the shipped
workflow at run time, never copied here. If the workflow changes, this runs
the changed expressions.

Usage: python3 .github/scripts/verify-relay-confirmation-phrase.py
"""
import io
import re
import sys

import yaml

WORKFLOW = ".github/workflows/pr-conversation.yml"

# Bodies that MUST resume the blocked classification.
POSITIVE = [
    "wing-commander: confirm relay",
    "wing-commander: confirm relay — go ahead",
    "Looks fine to me.\n\nwing-commander: confirm relay",
    "WING-COMMANDER: CONFIRM RELAY",
    "wing-commander:confirm relay",
    "wing-commander:  confirm   relay",
]

# Bodies that MUST NOT. The first is T069's own reported case; the rest are
# the ordinary PR chatter the old bare-substring match swept in.
NEGATIVE = [
    "can you confirm CI is green?",
    "Confirmed, that matches what I saw.",
    "This is still unconfirmed — leaving it for now.",
    "Please confirm the release notes before merging.",
    "I'd like confirmation from the security reviewer first.",
    "confirm relay",                      # missing the wing-commander: anchor
    "wing-commander: confirm",            # missing the object
    "wing-commander: stop relay",
    "Nothing actionable here, thanks!",
]


def _steps(wf):
    for job_name, job in (wf.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            yield job_name, (step or {})


def extract(path=WORKFLOW):
    """-> (grep_ere, jq_regex, marker_comment_text) read out of the workflow."""
    wf = yaml.safe_load(io.open(path, encoding="utf-8")) or {}
    grep_ere = jq_regex = marker = None

    for job_name, step in _steps(wf):
        run = step.get("run") or ""
        name = step.get("name", "")

        if name == "Check for relay confirmation":
            m = re.search(r"grep -qiE '([^']+)'", run)
            if m:
                grep_ere = m.group(1)

        if name == "Relayed-request risk-confirmation gate":
            m = re.search(r'test\("\(\?i\)([^"]+)"\)', run)
            if m:
                jq_regex = m.group(1)
            # the risk-warning comment body this same step posts
            for line in run.splitlines():
                if "to accept this risk and proceed" in line:
                    marker = line

    missing = [n for n, v in (("grep pattern", grep_ere),
                              ("jq test regex", jq_regex),
                              ("risk-warning comment text", marker)) if not v]
    if missing:
        sys.exit(f"::error file={path}::verify-relay-confirmation-phrase could "
                 f"not extract: {', '.join(missing)}. The steps it keys on were "
                 f"renamed or reshaped — update this script and the workflow "
                 f"together rather than letting the check quietly stop "
                 f"covering anything.")
    return grep_ere, jq_regex, marker


def to_python(pattern, jq_string=False):
    """POSIX ERE / Oniguruma -> Python re. Both engines agree on the small
    subset these patterns use; only the bracket class needs translating.

    jq_string: the pattern was read out of a jq STRING literal, where `\\s`
    is how you write the one-character escape `\\s` that the regex engine
    finally sees. Undo that level before handing it to Python, or every
    escape silently becomes a literal backslash and nothing matches."""
    if jq_string:
        pattern = pattern.replace("\\\\", "\\")
    return pattern.replace("[[:space:]]", r"\s")


def main():
    grep_ere, jq_regex, marker = extract()

    # The phrase the comment tells a maintainer to type, read back out of the
    # comment itself: whatever is inside the backticks.
    m = re.search(r"\\?`([^`]*confirm[^`]*)\\?`", marker)
    if not m:
        print(f"::error file={WORKFLOW}::the risk-warning comment does not "
              f"state the confirmation phrase in backticks, so a maintainer "
              f"is told to 'reply confirming' without being told with what. "
              f"Line: {marker.strip()}")
        return 1
    # the comment is written in shell, where the backticks are escaped
    stated_phrase = m.group(1).strip().rstrip("\\").strip()

    engines = {
        "classify-and-announce resume trigger (grep -qiE)": to_python(grep_ere),
        "act risk-confirmation gate (jq test)": to_python(jq_regex, jq_string=True),
    }

    failures = []

    # 1. The phrase the comment states must itself be accepted by both.
    for label, pat in engines.items():
        if not re.search(pat, stated_phrase, re.I):
            failures.append(
                f"the risk-warning comment tells the maintainer to reply "
                f"{stated_phrase!r}, but the {label} does not match that "
                f"phrase — every confirmation would be ignored and the "
                f"request would deadlock, re-asking forever")
        else:
            print(f"ok    stated phrase {stated_phrase!r} is accepted by the {label}")

    # 2. Both engines must agree, body for body.
    for label, pat in engines.items():
        for body in POSITIVE:
            if not re.search(pat, body, re.I):
                failures.append(f"{label}: should resume on {body!r}, does not")
        for body in NEGATIVE:
            if re.search(pat, body, re.I):
                failures.append(
                    f"{label}: must NOT resume on {body!r}. Matching it skips "
                    f"the classify agent, so this comment's real request is "
                    f"never answered and a stored classification is re-acted "
                    f"on instead (T069)")
        if not any(f.startswith(label) for f in failures):
            print(f"ok    {label}: {len(POSITIVE)} positive / "
                  f"{len(NEGATIVE)} negative bodies all classified correctly")

    print()
    if failures:
        for f in failures:
            print(f"::error file={WORKFLOW}::relay confirmation phrase: {f}")
        print(f"relay confirmation phrase: {len(failures)} failure(s).")
        return 1
    print(f"relay confirmation phrase: 3 expressions agree on "
          f"{len(POSITIVE) + len(NEGATIVE)} fixture bodies; 0 failure(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
