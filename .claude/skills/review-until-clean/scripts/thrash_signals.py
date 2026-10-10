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
prints the numbers the skill's stop rules read.

USAGE
-----
  thrash_signals.py --base origin/main --heads H0,H1,H2 \\
      [--finding path:line ...] [--counts 4,1,1] [--json]

  H0 is the PR head before pass 1's fixes; Hk is the head after pass k.
  --finding locations are on H(n-1), the head the latest pass started
  from and reviewed -- as its report gives them. On Hn that pass's own fix
  has already rewritten those lines. --counts holds the number of real
  findings each pass reported, in order.

  thrash_signals.py --self-test   builds a scratch repository and checks
                                  the attribution, churn and growth math.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def git(args, cwd=None, check=True):
    out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise SystemExit("thrash_signals: git {0} failed: {1}".format(
            " ".join(args), out.stderr.strip()))
    return out


def rev(ref, cwd):
    return git(["rev-parse", "--verify", ref + "^{commit}"], cwd).stdout.strip()


class Origins(object):
    """Maps a commit to the segment of the loop that introduced it."""

    def __init__(self, base, heads, cwd):
        self.base = base
        self.heads = heads
        self.cwd = cwd
        self._cache = {}

    def _is_ancestor(self, commit, ref):
        return git(["merge-base", "--is-ancestor", commit, ref],
                   self.cwd, check=False).returncode == 0

    def of(self, commit):
        if commit not in self._cache:
            if self._is_ancestor(commit, self.base):
                label = "main"
            elif self._is_ancestor(commit, self.heads[0]):
                label = "pr"
            else:
                label = "unrecorded"
                for k in range(1, len(self.heads)):
                    if self._is_ancestor(commit, self.heads[k]):
                        label = "pass{0}".format(k)
                        break
            self._cache[commit] = label
        return self._cache[commit]


def blame_commits(ref, path, start, count, cwd):
    """The commit that last wrote each line in [start, start+count) at ref."""
    out = git(["blame", "-l", "-s", "-L", "{0},+{1}".format(start, count),
               ref, "--", path], cwd, check=False)
    if out.returncode != 0:
        return []
    commits = []
    for line in out.stdout.splitlines():
        token = line.split(" ", 1)[0].lstrip("^")
        if token:
            commits.append(token)
    return commits


def removed_ranges(old, new, cwd):
    """(path, start, count) for every old-side range a diff rewrites or deletes."""
    out = git(["-c", "core.quotePath=false", "diff", "-U0", "--no-renames",
               "--no-color", old, new], cwd).stdout
    ranges = []
    path = None
    in_header = False
    for line in out.splitlines():
        # A deleted line reading "-- x" shows up as "--- x" inside a hunk, so
        # "--- " names a file only in the header between "diff --git" and the
        # first "@@". Git ends the name with a tab when it contains a space.
        if line.startswith("diff --git "):
            in_header, path = True, None
        elif in_header and line.startswith("--- "):
            target = line[4:]
            if target.endswith("\t"):
                target = target[:-1]
            path = target[2:] if target.startswith("a/") else None
        elif line.startswith("@@"):
            in_header = False
            if not path:
                continue
            match = HUNK_RE.match(line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) is not None else 1
                if count:
                    ranges.append((path, start, count))
    return ranges


def diff_size(base, head, cwd):
    merge_base = git(["merge-base", base, head], cwd).stdout.strip()
    out = git(["diff", "--numstat", "--no-renames", merge_base, head], cwd).stdout
    files = lines = 0
    for row in out.splitlines():
        added, deleted, _path = row.split("\t", 2)
        files += 1
        if added != "-":
            lines += int(added) + int(deleted)
    return {"files": files, "lines": lines}


def measure(base, heads, findings, counts, cwd):
    # Diff paths are relative to the repository root, and blame resolves
    # a path against its cwd; run from a subdirectory, every blame would
    # fail and churn and attribution would read 0.
    cwd = git(["rev-parse", "--show-toplevel"], cwd).stdout.strip()
    base = rev(base, cwd)
    heads = [rev(h, cwd) for h in heads]
    origins = Origins(base, heads, cwd)
    report = {"base": base, "heads": heads}

    report["growth"] = [dict(diff_size(base, h, cwd), head=h[:12]) for h in heads]

    # Attribution reads ancestry against the recorded heads; a rebase or
    # force-push between two of them gives the PR's commits new SHAs that
    # only the later head contains, which would label them passK.
    report["warnings"] = [
        "H{0} is not an ancestor of H{1}: history was rewritten between "
        "them, so attribution and churn are unreliable".format(k - 1, k)
        for k in range(1, len(heads))
        if not origins._is_ancestor(heads[k - 1], heads[k])]
    # A pass that merged main brings in main commits; if --base predates
    # that merge they are not its ancestors and would be labelled passK.
    for k in range(1, len(heads)):
        merges = git(["rev-list", "--merges", "--parents", heads[k - 1] + ".." + heads[k]],
                     cwd).stdout.split("\n")
        if any(not origins._is_ancestor(parent, base)
               for line in merges if line
               for parent in line.split()[2:]
               if not origins._is_ancestor(parent, heads[k - 1])):
            report["warnings"].append(
                "pass {0} merged commits --base does not contain: fetch the base "
                "branch, or they are counted as pass {0}'s".format(k))

    churn = []
    for k in range(1, len(heads)):
        rewrote = {}
        for path, start, count in removed_ranges(heads[k - 1], heads[k], cwd):
            for commit in blame_commits(heads[k - 1], path, start, count, cwd):
                label = origins.of(commit)
                if label.startswith("pass"):
                    rewrote[label] = rewrote.get(label, 0) + 1
        churn.append({"pass": k, "rewrote_earlier_pass_lines": rewrote,
                      "total": sum(rewrote.values())})
    report["churn"] = churn

    # The latest pass reviewed heads[-2]; its findings' line numbers are
    # that head's, and on heads[-1] its own fixes own those lines.
    reviewed = heads[-2] if len(heads) > 1 else heads[-1]
    attributed = []
    for spec in findings:
        path, _, line = spec.rpartition(":")
        if not path or not line.isdigit():
            raise SystemExit("thrash_signals: --finding wants path:line, got {0!r}".format(spec))
        commits = blame_commits(reviewed, path, int(line), 1, cwd)
        attributed.append({"finding": spec,
                           "origin": origins.of(commits[0]) if commits else "unknown"})
    report["findings"] = attributed
    in_loop = sum(1 for f in attributed if f["origin"].startswith("pass"))
    report["self_inflicted"] = {"count": in_loop, "of": len(attributed)}

    if counts:
        report["trend"] = counts
    return report


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
        print("ok: attribution, self-inflicted share, churn, growth, header parsing, subdirectory, stale-base and rewrite warnings")
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--heads", help="comma-separated: H0 (before pass 1), H1 (after pass 1), ...")
    parser.add_argument("--finding", action="append", default=[], help="path:line on the head the latest pass reviewed")
    parser.add_argument("--counts", help="comma-separated real findings per pass")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
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
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
