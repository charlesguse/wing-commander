#!/usr/bin/env python3
"""Gate - docs/adoption.md's sample event policy covers every wrapper event.

specs/132-workflow-trigger-security (FR-020, SC-006), research.md D9.

THE RULE
--------
`docs/adoption.md` carries one fenced block whose info string is
`yaml wc-event-policy`. Its YAML has an `events:` mapping, one key per
GitHub event. Every event under `on:` of every
`.github/workflows/wing-commander-*.yml` must be a key of that mapping. A
missing block, an unparsable block, or an event the block lacks fails; the
output names the event and the wrapper that uses it. An event the block lists
that no wrapper uses is allowed (adopters' own wrappers may use it).

Usage:
    python3 .github/scripts/verify-adopter-event-policy.py [--root DIR]
    python3 .github/scripts/verify-adopter-event-policy.py --self-test
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys
import tempfile

import yaml

DOC_PATH = "docs/adoption.md"
BLOCK_RE = re.compile(
    r"^```[ \t]*yaml[ \t]+wc-event-policy[ \t]*\n(.*?)^```[ \t]*$",
    re.S | re.M)


def wrapper_events(root, problems=None):
    """-> {event: [wrapper basename, ...]}. A wrapper that cannot be read as
    a workflow mapping is appended to `problems` rather than skipped."""
    out = {}
    problems = [] if problems is None else problems
    pattern = os.path.join(root, ".github", "workflows", "wing-commander-*.yml")
    for p in sorted(glob.glob(pattern)):
        try:
            with io.open(p, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            problems.append("{0}: cannot be parsed, so its events are "
                            "unknown.".format(os.path.basename(p)))
            continue
        if not isinstance(doc, dict):
            problems.append("{0}: is not a workflow mapping, so its events "
                            "are unknown.".format(os.path.basename(p)))
            continue
        on = doc.get("on", doc.get(True))
        if isinstance(on, str):
            events = [on]
        elif isinstance(on, (list, dict)):
            events = [str(e) for e in on]
        else:
            events = []
        for e in events:
            out.setdefault(e, []).append(os.path.basename(p))
    return out


def policy_events(root):
    """-> (set | None, failure | None)."""
    try:
        with io.open(os.path.join(root, DOC_PATH), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, "{0}: missing.".format(DOC_PATH)
    m = BLOCK_RE.search(text)
    if not m:
        return None, ("{0}: no fenced ```yaml wc-event-policy block.".format(
            DOC_PATH))
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return None, "{0}: wc-event-policy block is not valid YAML ({1}).".format(
            DOC_PATH, e)
    ev = data.get("events") if isinstance(data, dict) else None
    if not isinstance(ev, dict) or not ev:
        return None, ("{0}: wc-event-policy block needs a non-empty `events:` "
                      "mapping.".format(DOC_PATH))
    return {str(k) for k in ev}, None


def evaluate(root):
    failures = []
    events = wrapper_events(root, failures)
    if not events:
        failures.append("no wing-commander-*.yml wrapper with an `on:` event "
                        "was found; refusing to pass on an empty set.")
    listed, fail = policy_events(root)
    if fail:
        failures.append(fail)
        return failures
    for e in sorted(events):
        if e not in listed:
            failures.append("event `{0}` (used by {1}) is missing from the "
                            "wc-event-policy block in {2}.".format(
                                e, ", ".join(events[e]), DOC_PATH))
    return failures


def _tree(wrappers, doc):
    d = tempfile.mkdtemp(prefix="event-policy-selftest-")
    files = {"docs/adoption.md": doc}
    for name, on in wrappers.items():
        files[".github/workflows/" + name] = on
    for rel, text in files.items():
        if text is None:
            continue
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
    return d


def _doc(events):
    body = "".join("  {0}: {{}}\n".format(e) for e in events)
    return "# Doc\n\n```yaml wc-event-policy\nevents:\n{0}```\n".format(body)


def self_test():
    wf = {"wing-commander-a.yml": "on:\n  issues:\n    types: [opened]\n"
                                  "  schedule:\n    - cron: '0 0 * * *'\njobs: {}\n"}
    cases = [
        ("every event listed", wf, _doc(["issues", "schedule"]), None),
        ("missing event", wf, _doc(["issues"]), "event `schedule`"),
        ("block absent", wf, "# Doc\n", "no fenced"),
        ("empty events", wf, "```yaml wc-event-policy\nevents: {}\n```\n",
         "non-empty"),
        ("no wrappers", {}, _doc(["issues"]), "empty set"),
        ("unparsable wrapper fails",
         dict(wf, **{"wing-commander-c.yml": "on: [push\njobs: {"}),
         _doc(["issues", "schedule"]), "cannot be parsed"),
        ("string on",{"wing-commander-b.yml": "on: push\njobs: {}\n"},
         _doc(["issues"]), "event `push`"),
    ]
    bad = 0
    for name, wrappers, doc, want in cases:
        d = _tree(wrappers, doc)
        try:
            got = evaluate(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        ok = (not got) if want is None else any(want in g for g in got)
        if not ok:
            bad += 1
            print("SELF-TEST FAIL: {0}: wanted {1!r}, got {2}".format(
                name, want, got))
    if bad:
        return 1
    print("verify-adopter-event-policy self-test: {0} cases ok.".format(
        len(cases)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    failures = evaluate(args.root)
    for f in failures:
        print("::error::verify-adopter-event-policy: {0}".format(f))
    if failures:
        return 1
    print("verify-adopter-event-policy: every wrapper event is in the sample "
          "policy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
