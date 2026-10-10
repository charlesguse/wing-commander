#!/usr/bin/env python3
"""Gate verdict writer and fail-closed reader (spec 095).

The single home of the verdict contract in
specs/095-agent-code-credential-containment/contracts/gate-verdict.schema.json.
A credential-free gate-suite job writes a verdict; the credential-bearing
publisher reads it. The reader FAILS CLOSED: an absent, unreadable,
unknown-keyed, mis-typed or mis-bound verdict yields outcome=fail with a
reason, never a pass.

    wc_gate_verdict.py write --site S --trusted-sha SHA --head-sha SHA \
        --outcome pass|fail --exit-code N [--first-failure TEXT] --out FILE
    wc_gate_verdict.py read --file FILE --expected-head-sha SHA \
        --trusted-sha SHA [--site S]    # step outputs on stdout
    wc_gate_verdict.py --self-test

`read` prints `outcome=`, `reason=` and `first-failure=` lines (cleaned by
wc_step_output) suitable for `>> "$GITHUB_OUTPUT"`; it exits 0 whatever the
outcome, because the caller gates on the output, not on the exit code.
"""
import argparse
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_step_output import output_line  # noqa: E402

SITES = ("board-fix", "board-review-fixup", "implement-cycle", "implement-retry")
KEYS = ("schema_version", "site", "trusted_sha", "head_sha", "outcome",
        "first_failure", "exit_code")
SHA_RE = re.compile(r"[0-9a-f]{40}")
MAX_FAILURE = 4000


def build_verdict(site, trusted_sha, head_sha, outcome, exit_code,
                  first_failure=""):
    return {
        "schema_version": 1,
        "site": site,
        "trusted_sha": trusted_sha,
        "head_sha": head_sha,
        "outcome": outcome,
        "first_failure": (first_failure or "")[:MAX_FAILURE],
        "exit_code": int(exit_code),
    }


def write_verdict(path, **kwargs):
    verdict = build_verdict(**kwargs)
    problem = validate(verdict)
    if problem:
        raise ValueError(problem)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, sort_keys=True)
        fh.write("\n")
    return verdict


def validate(data):
    """Return a reason string if `data` violates the schema, else ''."""
    if not isinstance(data, dict):
        return "verdict is not a JSON object"
    extra = sorted(set(data) - set(KEYS))
    if extra:
        return "unknown key: " + ", ".join(extra)
    missing = [k for k in KEYS if k not in data]
    if missing:
        return "missing key: " + ", ".join(missing)
    if data["schema_version"] != 1 or isinstance(data["schema_version"], bool):
        return "unsupported schema_version"
    if data["site"] not in SITES:
        return "unknown site"
    for key in ("trusted_sha", "head_sha"):
        if not isinstance(data[key], str) or not SHA_RE.fullmatch(data[key]):
            return key + " is not a 40-hex SHA"
    if data["outcome"] not in ("pass", "fail"):
        return "outcome is neither pass nor fail"
    if (not isinstance(data["first_failure"], str)
            or len(data["first_failure"]) > MAX_FAILURE):
        return "first_failure is not a string of at most 4000 characters"
    if (not isinstance(data["exit_code"], int)
            or isinstance(data["exit_code"], bool)):
        return "exit_code is not an integer"
    return ""


def read_verdict(path, expected_head_sha, trusted_sha, site=None):
    """Return (outcome, reason, first_failure). Anything but a valid,
    correctly bound verdict reads as ('fail', reason, ...)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return "fail", "verdict artifact missing", "gate verdict absent"
    except (OSError, ValueError, UnicodeDecodeError, RecursionError,
            MemoryError) as exc:
        return "fail", "verdict unreadable: {0}".format(type(exc).__name__), \
            "gate verdict unreadable"
    problem = validate(data)
    if problem:
        return "fail", problem, "gate verdict invalid"
    if data["head_sha"] != expected_head_sha:
        return "fail", "head_sha mismatch", "gate verdict is for another commit"
    if data["trusted_sha"] != trusted_sha:
        return "fail", "trusted_sha mismatch", \
            "gate verdict ran against another trusted copy"
    if site is not None and data["site"] != site:
        return "fail", "site mismatch", "gate verdict is for another site"
    if data["outcome"] == "fail":
        return "fail", "gate suite failed", data["first_failure"]
    return "pass", "gate suite passed", ""


def _self_test():
    sha_a, sha_b = "a" * 40, "b" * 40
    failures = []

    def expect(label, got, want):
        if got != want:
            failures.append("{0}: got {1!r}, want {2!r}".format(label, got, want))

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v.json")

        def raw(text):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

        def outcome():
            return read_verdict(path, sha_a, sha_b)

        expect("missing", outcome()[0], "fail")
        raw("{not json")
        expect("unparsable", outcome()[0], "fail")
        good = build_verdict("board-fix", sha_b, sha_a, "pass", 0)
        raw(json.dumps(dict(good, extra=1)))
        expect("unknown key", outcome()[1], "unknown key: extra")
        raw(json.dumps(dict(good, outcome="skipped")))
        expect("bad outcome", outcome()[0], "fail")
        raw(json.dumps(dict(good, head_sha=sha_b)))
        expect("head mismatch", outcome()[1], "head_sha mismatch")
        raw(json.dumps(dict(good, trusted_sha=sha_a)))
        expect("trusted mismatch", outcome()[1], "trusted_sha mismatch")
        raw(json.dumps(good))
        expect("valid pass", outcome()[0], "pass")
        raw(json.dumps(dict(good, outcome="fail", first_failure="Gate 3")))
        expect("valid fail", outcome(), ("fail", "gate suite failed", "Gate 3"))
        write_verdict(path, site="board-fix", trusted_sha=sha_b,
                      head_sha=sha_a, outcome="pass", exit_code=0)
        expect("writer round trip", outcome()[0], "pass")
    for failure in failures:
        print("SELF-TEST FAIL: " + failure, file=sys.stderr)
    if failures:
        return 1
    print("wc_gate_verdict self-test: ok")
    return 0


def main(argv):
    if "--self-test" in argv:
        return _self_test()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--site", required=True)
    w.add_argument("--trusted-sha", required=True)
    w.add_argument("--head-sha", required=True)
    w.add_argument("--outcome", required=True)
    w.add_argument("--exit-code", type=int, required=True)
    w.add_argument("--first-failure", default="")
    w.add_argument("--out", required=True)
    r = sub.add_parser("read")
    r.add_argument("--file", required=True)
    r.add_argument("--expected-head-sha", required=True)
    r.add_argument("--trusted-sha", required=True)
    r.add_argument("--site", required=True)
    args = parser.parse_args(argv[1:])
    if args.cmd == "write":
        try:
            write_verdict(args.out, site=args.site,
                          trusted_sha=args.trusted_sha, head_sha=args.head_sha,
                          outcome=args.outcome, exit_code=args.exit_code,
                          first_failure=args.first_failure)
        except ValueError as exc:
            print("::error::{0}".format(exc), file=sys.stderr)
            return 2
        return 0
    result = read_verdict(args.file, args.expected_head_sha,
                          args.trusted_sha, args.site)
    for key, value in zip(("outcome", "reason", "first-failure"), result):
        print(output_line(key, value))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
