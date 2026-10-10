#!/usr/bin/env python3
"""Classify the log of an agent-action start-up run (spec 112, #974).

The job under test runs anthropics/claude-code-action@v1 inside the image
with no model credential. The action's setup steps (Install Bun and the
like) either complete and the action then fails at authentication, or a
setup step fails because the image lacks something. This script reads the
job log and returns exactly one verdict:

  setup-completed  exit 0  the first error came after setup and matches the
                           authentication marker table (positive evidence)
  setup-failed     exit 1  the first error is inside a setup group; the
                           group is named and the error line quoted verbatim
  unclassified     exit 2  anything else: empty/missing/truncated log, no
                           error, a non-auth error after setup, an image that
                           was never pulled, no group markers

Evidence note (research D3 / task T001): the fixtures under
agent-startup-fixtures/ are `# synthetic` -- hand-written from the
`Unable to locate executable file: unzip` line in #974, not captured from a
live run. The wording recorded here is the assumption they encode:
  * setup groups are the `##[group]` blocks opened before the action's
    prepare step (a group whose header contains "prepare");
  * the no-credential failure is an `##[error]` line from the prepare step
    matching AUTH_MARKERS below.
When the action's wording changes the check turns red (`unclassified`);
edit AUTH_MARKERS by hand.
"""
import argparse
import json
import re
import sys

VERDICT_COMPLETED = "setup-completed"
VERDICT_FAILED = "setup-failed"
VERDICT_UNCLASSIFIED = "unclassified"

EXIT_CODES = {VERDICT_COMPLETED: 0, VERDICT_FAILED: 1, VERDICT_UNCLASSIFIED: 2}

REASON_FAILED = "setup failed in image"
REASON_UNCLASSIFIED = "could not reach subject"

# The action's no-credential failure, as the prepare step reports it.
AUTH_MARKERS = [
    re.compile(r"(?i)\bANTHROPIC_API_KEY\b.*\b(not set|missing|required)\b"),
    re.compile(r"(?i)\bCLAUDE_CODE_OAUTH_TOKEN\b.*\b(not set|missing|required)\b"),
    re.compile(r"(?i)\bno (api key|credential|oauth token)\b"),
    re.compile(r"(?i)\bauthentication (failed|error)\b"),
]

PREPARE_GROUP = re.compile(r"(?i)prepare")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")


def _result(verdict, step=None, error=None, reason=""):
    return {"verdict": verdict, "step": step, "error": error, "reason": reason}


def _unclassified(why, error=None):
    return _result(VERDICT_UNCLASSIFIED, None, error, "%s: %s" % (REASON_UNCLASSIFIED, why))


def classify(text):
    """Pure function: log text -> Verdict dict (data-model.md)."""
    if not text or not text.strip():
        return _unclassified("the log is empty or unreadable")
    group = None
    prepare_seen = False
    for raw in text.splitlines():
        line = TIMESTAMP.sub("", raw).strip()
        if line.startswith("##[group]"):
            group = line[len("##[group]"):].strip()
            if PREPARE_GROUP.search(group):
                prepare_seen = True
        elif line.startswith("##[error]"):
            error = line[len("##[error]"):].strip()
            if group is None:
                return _unclassified("an error appeared before any setup step ran", error)
            if not prepare_seen:
                return _result(
                    VERDICT_FAILED, group, error,
                    '%s: step "%s" failed: %s' % (REASON_FAILED, group, error),
                )
            if any(m.search(error) for m in AUTH_MARKERS):
                return _result(
                    VERDICT_COMPLETED, None, error,
                    "failed at authentication, after setup",
                )
            return _unclassified("an error after setup is not the authentication failure", error)
    if group is None:
        return _unclassified("no step groups in the log (the job may never have started)")
    return _unclassified("no error was found (the action did not fail at authentication)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", help="job log file")
    ap.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = ap.parse_args(argv)
    text = ""
    if args.log:
        try:
            with open(args.log, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
    result = classify(text)
    if args.json:
        print(json.dumps(result))
    else:
        print("%s: %s" % (result["verdict"], result["reason"]))
    return EXIT_CODES[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
