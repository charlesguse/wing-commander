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
`Unable to locate executable file: unzip` line in #974 and from the
structure of anthropics/claude-code-action@v1's own action.yml and
src/entrypoints/run.ts (read at v1 = 1d6de8c, 2026-10-09), not captured from
a live run. The shape they encode:
  * the action's step opens a `##[group]Run anthropics/claude-code-action@v1`
    header (ACTION_GROUP); an error before it means the job never reached
    the action (container start, image pull): could not reach subject;
  * the action's own composite steps (setup-bun, `bun install`, then ONE
    `run.ts` step that prepares, installs Claude Code and validates the
    credential) open their own groups; there is no separate prepare step;
  * run.ts logs SETUP_DONE once the Claude Code install has finished, and
    only then validates the credential, failing with
    `##[error]Action failed with error: Environment variable validation
    failed:` and the missing-credential detail on continuation lines,
    which are read as part of the error (AUTH_MARKERS).
When the action's wording changes the check turns red (`unclassified`);
edit the marker tables by hand.
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

# The action's no-credential failure, as run.ts reports it (the first
# ##[error] line plus its continuation lines).
# Only the model-credential check's own wording: a generic "authentication
# failed" (a GitHub or git auth error after setup) is not this boundary.
AUTH_MARKERS = [
    re.compile(r"(?i)\bEnvironment variable validation failed\b"),
    re.compile(r"(?i)\bANTHROPIC_API_KEY\b.*\b(not set|missing|required)\b"),
    re.compile(r"(?i)\bCLAUDE_CODE_OAUTH_TOKEN\b.*\b(not set|missing|required)\b"),
]

# The step that runs the action; errors before it are not the image's setup.
ACTION_GROUP = re.compile(r"(?i)claude-code-action")
# The runner opens each step's log with a "Run <uses or first script line>"
# group holding the echoed source and with:/env: dump; any other group
# after the action started is one the step printed while running.
STEP_HEADER = re.compile(r"Run ")
# run.ts's log line once its Claude Code install finished: the end of setup.
SETUP_DONE = re.compile(r"(?i)Claude Code installed successfully")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ?")


def _result(verdict, step=None, error=None, reason=""):
    return {"verdict": verdict, "step": step, "error": error, "reason": reason}


def _unclassified(why, error=None):
    return _result(VERDICT_UNCLASSIFIED, None, error, "%s: %s" % (REASON_UNCLASSIFIED, why))


def _error_text(lines, i):
    """The ##[error] line at i plus the continuation lines that follow it
    (a multi-line core.setFailed message prints its detail unprefixed)."""
    parts = [lines[i].strip()[len("##[error]"):].strip()]
    for cont in lines[i + 1:]:
        if not cont or cont.startswith("##[") or cont[0] not in " -\t":
            break
        parts.append(cont.strip())
    return " ".join(p for p in parts if p)


def classify(text):
    """Pure function: log text -> Verdict dict (data-model.md)."""
    if not text or not text.strip():
        return _unclassified("the log is empty or unreadable")
    lines = [TIMESTAMP.sub("", raw.rstrip("\r")) for raw in text.splitlines()]
    group = None
    in_header = False
    action_seen = False
    setup_done = False
    for i, line in enumerate(lines):
        head = line.strip()
        if head.startswith("##[group]"):
            name = head[len("##[group]"):].strip()
            if action_seen and not STEP_HEADER.match(name):
                # A group the running step printed itself (core.startGroup):
                # runtime output, not a new step and not an echoed header.
                continue
            group = name
            in_header = True
            if ACTION_GROUP.search(group):
                action_seen = True
        elif head.startswith("##[endgroup]"):
            in_header = False
        elif SETUP_DONE.search(head) and action_seen and not in_header:
            # Only runtime output: inside a group header the runner echoes
            # the step's source and with:/env: dump, where the text (say an
            # echo of it in a script) has not happened yet.
            setup_done = True
        elif head.startswith("##[error]"):
            error = _error_text(lines, i)
            if not action_seen:
                return _unclassified(
                    "an error appeared before the agent action started "
                    "(job set-up, container start or image pull)", error)
            # Positive evidence needs both: setup finished, then the
            # credential check failed. An auth-looking error during setup
            # (a registry or proxy refusing the bun download) is setup's.
            if setup_done and any(m.search(error) for m in AUTH_MARKERS):
                return _result(
                    VERDICT_COMPLETED, None, error,
                    "failed at authentication, after setup",
                )
            if not setup_done:
                return _result(
                    VERDICT_FAILED, group, error,
                    '%s: step "%s" failed: %s' % (REASON_FAILED, group, error),
                )
            return _unclassified("an error after setup is not the authentication failure", error)
    if group is None:
        return _unclassified("no step groups in the log (the job may never have started)")
    if not action_seen:
        return _unclassified("the agent action never started")
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
