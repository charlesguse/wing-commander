#!/usr/bin/env python3
"""Is a review loop converging, or feeding on its own fixes?

THE FAILURE THIS MEASURES
-------------------------
A review -> fix -> review loop can keep finding real bugs and still be
going nowhere: the bugs are in code the loop itself wrote. PR #969's four
review passes found 10 cases Gate 12 would miss, and 8 of them were in the
PR's own new parsing; #954 took 15 rounds and grew into a full shell
parser. Each round looked productive. The signal was where the findings
were, not how many there were, and nothing measured it.

This script answers the parts of that question git can answer
deterministically, from the head SHAs the loop recorded at each pass
boundary:

  attribution  For each finding location on the head the latest pass
               reviewed, who wrote the line: main, the PR as first
               submitted, or the fix commits of an earlier pass k. Findings
               in pass-k lines are self-inflicted.
  churn        For each pass, how many lines it rewrote or deleted that an
               EARLIER pass had written. A fix of a fix; a pass undoing a
               pass is the extreme case.
  growth       The PR's diff size against main at every recorded head.
  trend        Real findings per pass, when the caller passes --counts.

It does not decide whether a finding is real, or whether one finding is a
re-raise of another; the review-until-clean skill's ledger does that. It
prints the numbers the skill's stop rules read, and which of those rules
trip.

THE ARITHMETIC HAS ONE HOME
---------------------------
Since spec 116 the attribution, churn and growth arithmetic, the stop rules
and their thresholds live in .github/scripts/wc_convergence.py, which the
lifecycle review gate and the board loop call too: this script is the
skill's CLI over that module and carries no copy of its own (Gate 165,
verify-convergence-single-home.py, fails on one). A threshold is tuned in
wc_convergence.THRESHOLDS, once, for the skill and both loops.

USAGE
-----
  thrash_signals.py --base origin/main --heads H0,H1,H2 \\
      [--finding path:line ...] [--counts 4,1] [--recurring N] [--json]

  H0 is the PR head before pass 1's fixes; Hk is the head after pass k.
  --finding locations are on H(n-1), the head the latest pass started
  from and reviewed -- as its report gives them. On Hn that pass's own fix
  has already rewritten those lines. --counts holds the number of real
  findings each pass reported, in order. --recurring is how many of the
  latest pass's findings the ledger marks fixed in an earlier pass. With
  --counts, the report also names the stop rules that trip (from pass 3).

  thrash_signals.py --history rounds.json [--base origin/main] [--json]
      the automated loops' own view: wc_convergence.py's `decide` over a
      recorded round history, so the skill and the loops can be compared
      on one history (SC-003).

  thrash_signals.py --self-test   builds a scratch repository and checks
                                  the attribution, churn and growth math.
"""
import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", ".github", "scripts")))
import wc_convergence as wc  # noqa: E402  (the one home of the arithmetic)

git = wc.git
rev = wc.rev


def measure(base, heads, findings, counts, cwd):
    return wc.measure(base, heads, findings, cwd, counts)


def history_from_report(report, counts, recurring=0):
    """The report as round records wc_convergence.decide() reads.

    Pass k reviewed H(k-1): its count is counts[k-1], its churn the lines
    pass k-1 rewrote of an earlier pass's, its growth H(k-1)'s diff against
    H0's. Only the latest pass's findings were attributed, so only it has a
    self-inflicted share, and only it carries --recurring.
    """
    first = report["growth"][0]["lines"]
    rounds = []
    for k, count in enumerate(counts, 1):
        latest = k == len(counts)
        si = report["self_inflicted"] if latest else {"count": 0, "of": 0}
        rounds.append({
            "round": k, "count": count,
            "attributable": si["of"], "self_inflicted": si["count"],
            "unattributable": report.get("unattributable", 0) if latest else 0,
            "churn": report["churn"][k - 2]["total"] if k > 1 else 0,
            "growth": (float(report["growth"][k - 1]["lines"]) / first - 1) if first else None,
            "recurrences": ["recurring"] * recurring if latest else [],
        })
    return rounds


def render(report):
    lines = ["WARNING: " + w for w in report.get("warnings", [])]
    lines.append("Growth (diff vs main at each recorded head):")
    for i, g in enumerate(report["growth"]):
        label = "H{0} (before pass 1)".format(i) if i == 0 else "H{0} (after pass {0})".format(i)
        lines.append("  {0} {1}: {2} files, {3} lines".format(label, g["head"], g["files"], g["lines"]))
    lines.append("Churn (lines a pass rewrote that an earlier pass wrote):")
    if not report["churn"]:
        lines.append("  n/a (one head recorded)")
    for c in report["churn"]:
        detail = ", ".join("{0}: {1}".format(k, v) for k, v in sorted(c["rewrote_earlier_pass_lines"].items()))
        lines.append("  pass {0}: {1}{2}".format(c["pass"], c["total"], " ({0})".format(detail) if detail else ""))
    if report["findings"]:
        si = report["self_inflicted"]
        lines.append("Findings on the head the latest pass reviewed, by who wrote the line ({0} of {1} in loop-written lines):".format(si["count"], si["of"]))
        for f in report["findings"]:
            lines.append("  {0}: {1}".format(f["finding"], f["origin"]))
    if report.get("trend"):
        lines.append("Real findings per pass: {0}".format(" -> ".join(str(c) for c in report["trend"])))
    if "decision" in report:
        d = report["decision"]
        lines.append("Stop rules: {0}".format(
            "STOP and ask the owner -- tripped: " + ", ".join(d["tripped"]) if d["stop"]
            else "none tripped"))
    return "\n".join(lines)


def self_test():
    with tempfile.TemporaryDirectory() as repo:
        def run(*args):
            git(list(args), repo)

        def write(text, name="f.py"):
            with open(os.path.join(repo, name), "w", encoding="utf-8") as fh:
                fh.write(text)

        def commit(message):
            run("add", "-A")
            run("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)
            return rev("HEAD", repo)

        run("init", "-q", "-b", "main")
        write("a\nb\nc\n")
        base = commit("main")
        run("checkout", "-q", "-b", "pr")
        write("a\nb\nc\npr1\npr2\n")
        h0 = commit("the PR as submitted")
        write("a\nb\nc\npr1-fixed\npr2\nfix1\n")
        h1 = commit("pass 1 fixes pr1 and adds fix1")
        write("a\nb\nc\npr1-fixed\npr2\nfix1-refixed\nfix2\n")
        h2 = commit("pass 2 rewrites pass 1's line and adds fix2")

        # Pass 2 reviewed H1 and reports its findings on H1's lines; line 6
        # (fix1) is pass 1's, though pass 2's own fix rewrote it on H2.
        report = measure(base, [h0, h1, h2], ["f.py:4", "f.py:6", "f.py:5", "f.py:2"], [2, 1], repo)
        origins = [f["origin"] for f in report["findings"]]
        failures = []
        if origins != ["pass1", "pass1", "pr", "main"]:
            failures.append("attribution: expected pass1, pass1, pr, main; got {0}".format(origins))
        if report["self_inflicted"] != {"count": 2, "of": 4}:
            failures.append("self-inflicted: expected 2 of 4; got {0}".format(report["self_inflicted"]))
        churn = [(c["pass"], c["rewrote_earlier_pass_lines"]) for c in report["churn"]]
        if churn != [(1, {}), (2, {"pass1": 1})]:
            failures.append("churn: expected pass 1 none, pass 2 one pass1 line; got {0}".format(churn))
        sizes = [g["lines"] for g in report["growth"]]
        if sizes != [2, 3, 4]:
            failures.append("growth: expected 2, 3, 4 changed lines; got {0}".format(sizes))
        if report["warnings"]:
            failures.append("warnings: expected none on linear history; got {0}".format(report["warnings"]))

        # The stop rules come from the shared module: before pass 3 nothing
        # trips; a third pass whose count did not fall trips.
        if wc.decide(history_from_report(report, [2, 1]))["stop"]:
            failures.append("stop rules: expected nothing to trip before pass 3")
        write("a\nb\nc\npr1-fixed\npr2\nfix1-refixed\nfix2\nfix3\n")
        h3 = commit("pass 3")
        three = measure(base, [h0, h1, h2, h3], ["f.py:2"], [2, 1, 1], repo)
        tripped = wc.decide(history_from_report(three, [2, 1, 1]))["tripped"]
        if "count-not-falling" not in tripped:
            failures.append("stop rules: expected count-not-falling at pass 3; got {0}".format(tripped))
        if "recurrence" not in wc.decide(history_from_report(three, [3, 2, 1], recurring=1))["tripped"]:
            failures.append("stop rules: expected --recurring to trip recurrence at pass 3")

        # A second loop from H0: pass 2 deletes a "-- c" line above a rewrite
        # of a pass-1 line, and rewrites a pass-1 line in a file whose name
        # has a space; all three are churn.
        run("checkout", "-q", "-b", "headers", h0)
        write("-- c\nx\nfix2\n", "g.py")
        write("y\nfix2\n", "a b.py")
        h3 = commit("pass 1 adds lines to g.py and 'a b.py'")
        write("x\nfix3\n", "g.py")
        write("y\nfix3\n", "a b.py")
        h4 = commit("pass 2 deletes '-- c' and rewrites pass 1's lines")
        report = measure(base, [h0, h3, h4], [], [], repo)
        churn = [(c["pass"], c["rewrote_earlier_pass_lines"]) for c in report["churn"]]
        if churn != [(1, {}), (2, {"pass1": 3})]:
            failures.append("header parsing: expected pass 2 to churn 3 pass1 lines "
                            "('-- c' and fix2 in g.py, fix2 in 'a b.py'); got {0}".format(churn))

        # Run from a subdirectory, the same loop measures the same.
        os.makedirs(os.path.join(repo, "sub"))
        again = measure(base, [h0, h1, h2], ["f.py:4", "f.py:6", "f.py:5", "f.py:2"], [2, 1],
                        os.path.join(repo, "sub"))
        if [f["origin"] for f in again["findings"]] != ["pass1", "pass1", "pr", "main"] \
                or [c["total"] for c in again["churn"]] != [0, 1]:
            failures.append("subdirectory: expected the same attribution and churn as "
                            "from the root; got {0}, {1}".format(
                                [f["origin"] for f in again["findings"]],
                                [c["total"] for c in again["churn"]]))

        # A pass that merges a main newer than --base is flagged.
        run("checkout", "-q", "-b", "newer-main", base)
        write("main-later\n", "m.py")
        newer = commit("main moves on")
        run("checkout", "-q", "-b", "merged", h0)
        run("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
            "merge", "-q", "--no-edit", newer)
        h0_merged = rev("HEAD", repo)
        if not measure(base, [h0, h0_merged], [], [], repo)["warnings"]:
            failures.append("stale base: expected a warning when a pass merges commits "
                            "--base does not contain")
        if measure(newer, [h0, h0_merged], [], [], repo)["warnings"]:
            failures.append("stale base: expected no warning once --base contains the merge")

        # A head rebuilt off H0's line (a rebase) is flagged, not trusted.
        run("checkout", "-q", "-b", "rebased", base)
        write("a\nb\nc\npr1\npr2\n")
        h0_rebased = commit("the PR, rebased")
        report = measure(base, [h0, h0_rebased], [], [], repo)
        if not report["warnings"]:
            failures.append("rewrite: expected a warning when H0 is not an ancestor of H1")

        for failure in failures:
            print("FAIL " + failure)
        if failures:
            return 1
        print("ok: attribution, self-inflicted share, churn, growth, stop rules, header parsing, subdirectory, stale-base and rewrite warnings")
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--heads", help="comma-separated: H0 (before pass 1), H1 (after pass 1), ...")
    parser.add_argument("--finding", action="append", default=[], help="path:line on the head the latest pass reviewed")
    parser.add_argument("--counts", help="comma-separated real findings per pass")
    parser.add_argument("--recurring", type=int, default=0,
                        help="how many of the latest pass's findings the ledger marks fixed earlier")
    parser.add_argument("--history", help="JSON file: a recorded round history (wc_convergence.py decide's input)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.history:
        with open(args.history, encoding="utf-8") as fh:
            rounds = json.load(fh)
        history = wc.compute_history(args.base, rounds, None, os.getcwd())
        decision = wc.decide(history)
        decision["open_findings"] = history[-1]["findings"] if history else []
        decision["recurrences"] = history[-1]["recurrences"] if history else []
        print(json.dumps(decision, indent=2) if args.json else
              (wc.render_handoff(decision) if decision["stop"] else "converging: no signal tripped"))
        return 0
    if not args.heads:
        parser.error("--heads is required")
    heads = [h for h in args.heads.split(",") if h]
    counts = [c.strip() for c in args.counts.split(",") if c.strip()] if args.counts else []
    if not all(c.isdigit() for c in counts):
        parser.error("--counts wants comma-separated integers, got {0!r}".format(args.counts))
    counts = [int(c) for c in counts]
    if counts and len(counts) != len(heads) - 1:
        parser.error("--counts has {0} value(s) but --heads records {1} pass(es)".format(
            len(counts), len(heads) - 1))
    report = measure(args.base, heads, args.finding, counts, os.getcwd())
    if counts:
        decision = wc.decide(history_from_report(report, counts, args.recurring))
        report["decision"] = {"tripped": decision["tripped"], "stop": decision["stop"]}
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
