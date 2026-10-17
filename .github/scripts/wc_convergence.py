#!/usr/bin/env python3
"""Is a review loop converging, or feeding on its own fixes?

The one home for the convergence arithmetic the review loops and the
review-until-clean skill share (spec 116): attribution (who wrote the line a
finding sits on), churn (lines a pass rewrote that an earlier pass wrote),
growth (diff size against the base at each recorded head), recurrence (a
finding re-raised after it was folded or fixed) and the stop decision.

A history is the list of rounds a loop has run. Round n reviewed head_n;
the fixes between head_n and head_(n+1) are "pass n". Findings in pass-k
lines are self-inflicted.

  history = [{"round": 1, "head_sha": "...",
              "findings": [{"fingerprint": "...", "file": "a.py", "line": 3}]},
             ...]

CLI:
  wc_convergence.py decide --history <json file> --base <ref> \\
      [--ledger <json file>] [--json]
"""
import argparse
import json
import os
import re
import subprocess
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")

# The only place these numbers live (FR-010).
THRESHOLDS = {
    "min_round": 3,
    "self_inflicted_share": 0.5,
    "consecutive_churn_rounds": 2,
    "growth_ratio": 0.5,
}

SIGNALS = ("count-not-falling", "self-inflicted", "recurrence",
           "churn-streak", "growth")


def git(args, cwd=None, check=True):
    out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise SystemExit("wc_convergence: git {0} failed: {1}".format(
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
        # A commit in the freshly fetched base is main's, including merges of
        # main the loop made; it is never loop-written (research D2).
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


def validate_line(path, line, head, cwd):
    """True only when 1 <= line <= number of lines of path at head."""
    if isinstance(line, bool) or not isinstance(line, int) or line < 1 or not path:
        return False
    out = git(["show", "{0}:{1}".format(head, path)], cwd, check=False)
    if out.returncode != 0:
        return False
    text = out.stdout
    total = text.count("\n") + (0 if text == "" or text.endswith("\n") else 1)
    return 1 <= line <= total


def _toplevel(cwd):
    return git(["rev-parse", "--show-toplevel"], cwd).stdout.strip()


def measure(base, heads, findings, cwd, counts=None):
    """Attribution, churn and growth over H0 (before pass 1), H1, ...

    findings are "path:line" strings on heads[-2], the head the latest pass
    reviewed (on heads[-1] that pass's own fixes have rewritten the lines).
    """
    # Diff paths are relative to the repository root, and blame resolves
    # a path against its cwd; run from a subdirectory, every blame would
    # fail and churn and attribution would read 0.
    cwd = _toplevel(cwd)
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

    report["churn"] = [_churn(origins, heads, k, cwd) for k in range(1, len(heads))]

    reviewed = heads[-2] if len(heads) > 1 else heads[-1]
    attributed = []
    for spec in findings:
        path, _, line = spec.rpartition(":")
        if not path or not line.isdigit():
            raise SystemExit("wc_convergence: --finding wants path:line, got {0!r}".format(spec))
        commits = blame_commits(reviewed, path, int(line), 1, cwd)
        attributed.append({"finding": spec,
                           "origin": origins.of(commits[0]) if commits else "unknown"})
    report["findings"] = attributed
    in_loop = sum(1 for f in attributed if f["origin"].startswith("pass"))
    report["self_inflicted"] = {"count": in_loop, "of": len(attributed)}

    if counts:
        report["trend"] = counts
    return report


def _churn(origins, heads, k, cwd):
    rewrote = {}
    for path, start, count in removed_ranges(heads[k - 1], heads[k], cwd):
        for commit in blame_commits(heads[k - 1], path, start, count, cwd):
            label = origins.of(commit)
            if label.startswith("pass"):
                rewrote[label] = rewrote.get(label, 0) + 1
    return {"pass": k, "rewrote_earlier_pass_lines": rewrote,
            "total": sum(rewrote.values())}


def classify_recurrence(findings, ledger):
    """Split findings into (fresh, recurrences) against a resolved ledger.

    ledger is {"resolved": {fingerprint: round}, "dismissed": [fingerprint]};
    a bare mapping is read as the resolved map. Dismissed never match.
    """
    ledger = ledger or {}
    if "resolved" in ledger or "dismissed" in ledger:
        resolved = ledger.get("resolved") or {}
        dismissed = set(ledger.get("dismissed") or [])
    else:
        resolved, dismissed = ledger, set()
    fresh, recurrences = [], []
    for f in findings:
        fp = f.get("fingerprint")
        if fp in resolved and fp not in dismissed:
            recurrences.append(f)
        else:
            fresh.append(f)
    return fresh, recurrences


def compute_history(base, rounds, ledger, cwd):
    """Fill each round's signals from git. Never agent-supplied."""
    cwd = _toplevel(cwd)
    base = rev(base, cwd)
    heads = [rev(r["head_sha"], cwd) for r in rounds]
    origins = Origins(base, heads, cwd)
    first_size = diff_size(base, heads[0], cwd)["lines"] if heads else 0
    resolved = dict((ledger or {}).get("resolved") or {})
    out = []
    for i, rnd in enumerate(rounds):
        head = heads[i]
        attributable = self_inflicted = unattributable = 0
        for f in rnd.get("findings", []):
            if not validate_line(f.get("file"), f.get("line"), head, cwd):
                unattributable += 1
                continue
            attributable += 1
            commits = blame_commits(head, f["file"], f["line"], 1, cwd)
            if commits and origins.of(commits[0]).startswith("pass"):
                self_inflicted += 1
        # Only fingerprints resolved in an earlier round can recur.
        earlier = dict((fp, r) for fp, r in resolved.items() if r < rnd["round"])
        _, recurrences = classify_recurrence(rnd.get("findings", []), {
            "resolved": earlier, "dismissed": (ledger or {}).get("dismissed")})
        size = diff_size(base, head, cwd)["lines"]
        out.append({
            "round": rnd["round"],
            "count": len(rnd.get("findings", [])),
            "attributable": attributable,
            "self_inflicted": self_inflicted,
            "unattributable": unattributable,
            "churn": _churn(origins, heads, i, cwd)["total"] if i else 0,
            "growth": (float(size) / first_size - 1) if first_size else None,
            "recurrences": [f.get("fingerprint") for f in recurrences],
            "findings": rnd.get("findings", []),
        })
    return out


def decide(history, thresholds=THRESHOLDS):
    """Evaluate the FR-006 rules on computed round records.

    Returns {signals, tripped, stop, reason}. Empty tripped before round 3.
    """
    if not history:
        return {"signals": [], "tripped": [], "stop": False, "reason": None}
    signals = []
    for r in history:
        attributable = r.get("attributable", 0)
        share = None
        if r["round"] > 1 and attributable:
            share = float(r.get("self_inflicted", 0)) / attributable
        elif r["round"] == 1:
            share = 0.0
        signals.append({
            "round": r["round"], "count": r["count"],
            "self_inflicted_share": share,
            "unattributable": r.get("unattributable", 0),
            "churn": 0 if r["round"] == 1 else r.get("churn", 0),
            "growth": 0.0 if r["round"] == 1 else r.get("growth"),
            "recurrences": list(r.get("recurrences", [])),
        })
    latest = history[-1]
    tripped = []
    if latest["round"] >= thresholds["min_round"]:
        prev = history[-2] if len(history) > 1 else None
        if prev is not None and latest["count"] >= prev["count"]:
            tripped.append("count-not-falling")
        share = signals[-1]["self_inflicted_share"]
        if share is not None and share >= thresholds["self_inflicted_share"]:
            tripped.append("self-inflicted")
        if signals[-1]["recurrences"]:
            tripped.append("recurrence")
        n = thresholds["consecutive_churn_rounds"]
        recent = signals[-n:]
        if len(recent) == n and all(s["churn"] > 0 for s in recent):
            tripped.append("churn-streak")
        growth = signals[-1]["growth"]
        if growth is not None and growth > thresholds["growth_ratio"]:
            tripped.append("growth")
    stop = bool(tripped)
    return {"signals": signals, "tripped": tripped, "stop": stop,
            "reason": "not-converging" if stop else None}


def render_handoff(decision):
    rounds = decision["signals"]
    n = rounds[-1]["round"] if rounds else 0
    lines = ["<!-- wing-commander-not-converging: round={0} -->".format(n),
             "Review stopped: not converging (stall reason `not-converging`). "
             "The PR is left open and unmerged.", ""]
    lines.append("Tripped: " + (", ".join(decision["tripped"]) or "none"))
    lines.append("")
    lines.append("| Round | Findings | Self-inflicted share | Churn | Growth | Recurrences |")
    lines.append("|---|---|---|---|---|---|")
    for s in rounds:
        share = "n/a" if s["self_inflicted_share"] is None else "{0:.0%}".format(s["self_inflicted_share"])
        growth = "n/a" if s["growth"] is None else "{0:+.0%}".format(s["growth"])
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            s["round"], s["count"], share, s["churn"], growth, len(s["recurrences"])))
    unattributable = sum(s["unattributable"] for s in rounds)
    lines.append("")
    lines.append("Unattributable findings: {0}".format(unattributable))
    open_findings = decision.get("open_findings") or []
    if open_findings:
        lines.append("")
        lines.append("Open findings:")
        for f in open_findings:
            lines.append("- `{0}:{1}` {2}".format(
                f.get("file"), f.get("line") or "?", f.get("fingerprint", "")))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--history", required=True, help="JSON file: list of rounds")
    d.add_argument("--base", default="origin/main")
    d.add_argument("--ledger", help="JSON file: {resolved:{fp:round}, dismissed:[fp]}")
    d.add_argument("--json", action="store_true")
    args = parser.parse_args()
    with open(args.history, encoding="utf-8") as fh:
        rounds = json.load(fh)
    ledger = None
    if args.ledger:
        with open(args.ledger, encoding="utf-8") as fh:
            ledger = json.load(fh)
    history = compute_history(args.base, rounds, ledger, os.getcwd())
    decision = decide(history)
    decision["open_findings"] = history[-1]["findings"] if history else []
    if args.json:
        print(json.dumps(decision, indent=2))
    else:
        print(render_handoff(decision) if decision["stop"] else "converging: no signal tripped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
