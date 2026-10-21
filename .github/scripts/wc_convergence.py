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

Each loop persists one round record per round -- its round, reviewed head
and in-scope findings' fingerprint/file/line -- as a marker appended LAST to
the review it posts on the PR (round_record_marker), and reads earlier
rounds back off the PR's reviews (read_round_records): no new datastore.

CLI:
  wc_convergence.py decide --history <json file> --base <ref> \\
      [--ledger <json file>] [--json]
  wc_convergence.py record --round N --head-sha SHA --issue I --findings F
  wc_convergence.py evaluate --reviews F --bot-login L --round N \\
      --head-sha SHA --issue I --findings F [--base REF] [--resolved fp,...] \\
      [--resolved-from-history] [--budget N] [--decision-out F] [--handoff-out F]
  wc_convergence.py render-handoff --decision F
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


def blame_file(ref, path, cwd):
    """The commit that last wrote each line of path at ref (index 0 = line
    1); empty when git cannot blame it. One call per (ref, path) answers
    every finding on that file."""
    out = git(["blame", "-l", "-s", ref, "--", path], cwd, check=False)
    if out.returncode != 0:
        return []
    return [line.split(" ", 1)[0].lstrip("^") for line in out.stdout.splitlines()]


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


def recorded_diff_lines(base, head, cwd):
    """head's diff size against base in lines, as growth measures it, for
    the round record (owner decision F2 (b), #994); None when git cannot
    measure it here (no repository, an unknown ref, no merge base). A
    record without it falls back to measuring the head itself."""
    try:
        return diff_size(rev(base, cwd), rev(head, cwd), cwd)["lines"]
    except (SystemExit, OSError, ValueError):
        return None


def _stored_diff_lines(rnd):
    value = rnd.get("diff_lines")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


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
        # FR-005, as compute_history does: a line that does not exist at
        # the reviewed head is unattributable, outside the share's
        # denominator, so the skill and the loops compute one share.
        if not validate_line(path, int(line), reviewed, cwd):
            attributed.append({"finding": spec, "origin": "unattributable"})
            continue
        commits = blame_commits(reviewed, path, int(line), 1, cwd)
        attributed.append({"finding": spec,
                           "origin": origins.of(commits[0]) if commits else "unknown"})
    report["findings"] = attributed
    in_loop = sum(1 for f in attributed if f["origin"].startswith("pass"))
    unattributable = sum(1 for f in attributed if f["origin"] == "unattributable")
    report["self_inflicted"] = {"count": in_loop, "of": len(attributed) - unattributable}
    report["unattributable"] = unattributable

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


def _resolve_heads(base, rounds, cwd):
    """(base, heads) as full SHAs, or None when any of them is unreachable.

    A loop's earlier head can be gone from the checkout (a force-push, a
    shallow fetch); the git-derived signals are then unknowable, never
    guessed, and only the count and recurrence signals are computed.
    """
    try:
        return rev(base, cwd), [rev(r["head_sha"], cwd) for r in rounds]
    except (SystemExit, KeyError, TypeError):
        return None


def compute_history(base, rounds, ledger, cwd):
    """Fill each round's signals from git. Never agent-supplied."""
    cwd = _toplevel(cwd)
    resolved_heads = _resolve_heads(base, rounds, cwd)
    git_ok = resolved_heads is not None
    first_size = 0
    if git_ok:
        base, heads = resolved_heads
        origins = Origins(base, heads, cwd)
        # Heads that all resolve can still be rewritten history (a rebase
        # whose old heads another ref keeps): the rebased PR commits are
        # then ancestors of the later heads only and would be labelled
        # passK, as measure() warns. Attribution and churn are unknowable,
        # the same as an unreachable head; growth reads the stored sizes.
        if any(not origins._is_ancestor(heads[k - 1], heads[k])
               for k in range(1, len(heads))):
            git_ok = False
    # Growth and the first churn are measured from round 1's head. When the
    # earliest surviving record is a later round, they are unknowable: n/a,
    # never read against a baseline that is not round 1's.
    baseline_missing = bool(rounds) and rounds[0]["round"] != 1
    resolved = dict((ledger or {}).get("resolved") or {})
    # One blame per (head, path) and one numstat per head, however many
    # findings or rounds read them.
    blames, sizes = {}, {}

    def size_of(head):
        if head not in sizes:
            sizes[head] = diff_size(base, head, cwd)["lines"]
        return sizes[head]

    if git_ok and heads:
        # A missing merge-base (shallow fetch, unrelated history) makes the
        # git-derived signals unknowable, same as an unreachable head.
        try:
            first_size = size_of(heads[0])
            for head in heads:
                size_of(head)
        except SystemExit:
            git_ok = False
    # A rebase onto main (rebase.yml force-pushes every spec/* branch)
    # leaves the earlier heads unresolvable: attribution and churn are then
    # unknowable, but growth still reads each round's diff size as its
    # record stored it at review time, or measures a head that survives
    # (the current one). Round 1's size missing leaves growth n/a.
    recorded_sizes = []
    if not git_ok:
        for rnd in rounds:
            size = _stored_diff_lines(rnd)
            if size is None:
                size = recorded_diff_lines(base, rnd.get("head_sha") or "", cwd)
            recorded_sizes.append(size)
        first_size = recorded_sizes[0] if recorded_sizes else 0
    out = []
    for i, rnd in enumerate(rounds):
        attributable = self_inflicted = unattributable = 0
        for f in rnd.get("findings", []):
            if not git_ok or not validate_line(f.get("file"), f.get("line"), heads[i], cwd):
                unattributable += 1
                continue
            attributable += 1
            key = (heads[i], f["file"])
            if key not in blames:
                blames[key] = blame_file(heads[i], f["file"], cwd)
            commits = blames[key][f["line"] - 1:f["line"]]
            if commits and origins.of(commits[0]).startswith("pass"):
                self_inflicted += 1
        # Only fingerprints resolved in an earlier round can recur.
        earlier = dict((fp, r) for fp, r in resolved.items() if r < rnd["round"])
        _, recurrences = classify_recurrence(rnd.get("findings", []), {
            "resolved": earlier, "dismissed": (ledger or {}).get("dismissed")})
        growth = churn = None
        growth_source = None
        if not git_ok and first_size and not baseline_missing \
                and recorded_sizes[i] is not None:
            growth = float(recorded_sizes[i]) / first_size - 1
            growth_source = "recorded"
        if git_ok:
            size = size_of(heads[i])
            growth = (float(size) / first_size - 1) if first_size and not baseline_missing else None
            growth_source = "git" if growth is not None else None
            if i:
                churn = _churn(origins, heads, i, cwd)["total"]
            else:
                churn = None if baseline_missing else 0
        recorded = rnd.get("count")
        out.append({
            "round": rnd["round"],
            "count": recorded if isinstance(recorded, int) and not isinstance(recorded, bool)
            else len(rnd.get("findings", [])),
            "attributable": attributable,
            "self_inflicted": self_inflicted,
            "unattributable": unattributable,
            "churn": churn,
            "growth": growth,
            "recurrences": [f.get("fingerprint") for f in recurrences],
            "findings": rnd.get("findings", []),
            "git_ok": git_ok,
            "growth_source": growth_source,
            "baseline_missing": baseline_missing,
        })
    return out


def decide(history, thresholds=THRESHOLDS, budget=None):
    """Evaluate the FR-006 rules on computed round records.

    Returns {signals, tripped, stop, reason}. Empty tripped before round 3.
    budget is the first round the loop's own budget stops (the loop stops
    it whatever this says, FR-009); a trip on that same round names the
    budget as the reason and still lists the tripped signals.
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
        if (prev is not None and prev["round"] == latest["round"] - 1
                and latest["count"] > 0 and latest["count"] >= prev["count"]):
            tripped.append("count-not-falling")
        share = signals[-1]["self_inflicted_share"]
        if share is not None and share >= thresholds["self_inflicted_share"]:
            tripped.append("self-inflicted")
        if signals[-1]["recurrences"]:
            tripped.append("recurrence")
        # Round 2's churn is 0 by construction (pass 1 cannot rewrite an
        # earlier pass's lines), so with two consecutive rounds required the
        # streak can first trip at round 4, whatever min_round says.
        n = thresholds["consecutive_churn_rounds"]
        recent = signals[-n:]
        # In a row: a round with no record (a parse-failed round) breaks
        # the streak, as it does count-not-falling's comparison.
        if (len(recent) == n and all(s["round"] == recent[0]["round"] + j for j, s in enumerate(recent))
                and all((s["churn"] or 0) > 0 for s in recent)):
            tripped.append("churn-streak")
        growth = signals[-1]["growth"]
        if growth is not None and growth > thresholds["growth_ratio"]:
            tripped.append("growth")
    stop = bool(tripped)
    reason = "not-converging" if stop else None
    if stop and budget is not None and latest["round"] >= budget:
        reason = "budget-spent"
    return {"signals": signals, "tripped": tripped, "stop": stop,
            "reason": reason}


ROUND_MARKER = "wing-commander-convergence-round"
ROUND_MARKER_RE = re.compile(
    r"<!--\s*" + re.escape(ROUND_MARKER) + r":\s*(\{.*?\})\s*-->", re.DOTALL)
ROUND_MARKER_OPEN_RE = re.compile(r"<!--\s*" + re.escape(ROUND_MARKER) + r":")
MAX_RECORDED_FINDINGS = 50
# The reviewer's file_path has no schema bound (its title has 120): the
# record keeps at most this many characters of it, so the round record --
# reserved out of the review body's 57000-unit budget -- stays bounded. A
# real repository path is far shorter; a longer one only loses attribution.
MAX_RECORDED_PATH = 256
# The bound that holds: marker_json escapes every non-ASCII character and
# every `<`/`>` (up to 12 characters each), so MAX_RECORDED_PATH alone
# leaves the record unbounded. The marker is ASCII, so this many characters
# is this many UTF-16 units; entries past it are dropped, never the count.
MAX_RECORD_CHARS = 20000
# The hand-off is pasted into an issue comment beside other text, under
# GitHub's 65536-character limit; it lists at most this many open findings.
MAX_HANDOFF_FINDINGS = 25


def round_findings(findings, issue):
    """The in-scope reviewer findings of one round, as round-record entries.

    The fingerprint is wc_review_finding_fingerprint's (unchanged, research
    D4); `line` is the reviewer's optional line (D5), never part of it.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from wc_review_finding_fingerprint import fingerprint
    out = []
    for f in findings or []:
        if not isinstance(f, dict) or f.get("in_scope") is not True:
            continue
        path = str((f.get("fingerprint_basis") or {}).get("file_path") or "")
        line = f.get("line")
        out.append({"fingerprint": fingerprint(issue, f.get("title", ""), path),
                    "file": path[:MAX_RECORDED_PATH],
                    "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
                    "title": str(f.get("title", ""))})
    return out


def round_record_marker(round_, head_sha, entries, diff_lines=None):
    """The HTML-comment marker a loop appends, LAST, to the review body it
    posts on the PR for one round (data-model "Review round record").
    Titles stay out of it: the record carries identifiers only, plus the
    head's diff size against the base (recorded_diff_lines) when measured,
    which growth reads once a rebase has made the head unresolvable."""
    # count is the round's whole in-scope count; only the first
    # MAX_RECORDED_FINDINGS entries are kept, so a later round's trend
    # reads count, never len(findings).
    payload = {"round": round_, "head_sha": head_sha, "count": len(entries),
               "findings": [{"fingerprint": e["fingerprint"], "file": e["file"],
                             "line": e["line"]}
                            for e in entries[:MAX_RECORDED_FINDINGS]]}
    if isinstance(diff_lines, int) and not isinstance(diff_lines, bool) and diff_lines >= 0:
        payload["diff_lines"] = diff_lines
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from board_item_marker import marker_json
    # The file path is the reviewer's: marker_json keeps a `-->` in it
    # from ending the marker early.
    marker = "<!-- {0}: {1} -->".format(ROUND_MARKER, marker_json(payload))
    while len(marker) > MAX_RECORD_CHARS and payload["findings"]:
        payload["findings"].pop()
        marker = "<!-- {0}: {1} -->".format(ROUND_MARKER, marker_json(payload))
    return marker


def void_round_record_marker():
    """The marker a loop appends, LAST, in place of a round record when its
    round has none (a parse-failed round): read_round_records skips it, and
    as the body's last opener it keeps a record forged in the reviewer text
    shown above it from being read as this App's own."""
    return "<!-- {0}: {{}} -->".format(ROUND_MARKER)


def read_round_records(comments, bot_login):
    """Every round record this App posted, newest per round, by round.

    comments: REST-shaped reviews or comments ({body, user: {login, type},
    submitted_at|created_at}). Only the App's own bot-authored bodies count,
    and only the LAST marker opener in a body (agent text quoted earlier in
    the same body cannot forge one) -- board_item_marker's rules, reused.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from board_item_marker import is_loop_marker_author, last_marker_match
    by_round = {}
    for c in comments or []:
        if not isinstance(c, dict) or not is_loop_marker_author(c, bot_login):
            continue
        match = last_marker_match(c.get("body") or "", ROUND_MARKER_RE, ROUND_MARKER_OPEN_RE)
        if not match:
            continue
        try:
            rec = json.loads(match.group(1))
        except ValueError:
            continue
        # A record that fails any check is skipped whole: compute_history
        # reads round as a number and each finding as a mapping, so one
        # malformed record would otherwise fail every later run.
        if not isinstance(rec, dict) or isinstance(rec.get("round"), bool) \
                or not isinstance(rec.get("round"), int) or rec["round"] < 1 \
                or not isinstance(rec.get("head_sha"), str) \
                or not isinstance(rec.get("findings"), list) \
                or not all(isinstance(f, dict) for f in rec["findings"]):
            continue
        stamp = c.get("submitted_at") or c.get("created_at") or ""
        if rec["round"] not in by_round or stamp >= by_round[rec["round"]][0]:
            by_round[rec["round"]] = (stamp, rec)
    return [by_round[k][1] for k in sorted(by_round)]


def evaluate(records, current, base, cwd, resolved=None, budget=None,
             resolved_from_history=False, pending=None, dismissed=None):
    """One loop round's convergence decision (FR-004..FR-009).

    records: earlier rounds' records (read_round_records); only those
    before current["round"] are used. current: this round's record with
    its entries (round_findings). resolved: fingerprints already folded
    (lifecycle gate's marker); resolved_from_history also counts every
    earlier round's findings as fixed (the board loop, whose review-fixup
    fixes each round's in-scope findings before the next review). pending:
    folded fingerprints whose fold task is still open in tasks.md -- a
    finding the loop already knows is waiting is counted like any other but
    is not a recurrence. dismissed: fingerprints a maintainer dismissed --
    the ledger's dismissed list, never a recurrence, and subtracted from every
    round's count and left out of the open findings, so count-not-falling
    and the hand-off read only findings the loop still owes. Pending
    findings stay counted: the loop still owes their fold.
    """
    dismissed = set(dismissed or [])
    rounds = [_without_dismissed(r, dismissed)
              for r in records if r["round"] < current["round"]]
    rounds.append(_without_dismissed(current, dismissed))
    # A folded fingerprint was resolved in the first round that raised it,
    # so that round's own row never counts it as a recurrence; one no
    # earlier record carries resolves before round 1.
    first_raised = {}
    for r in rounds[:-1]:
        for f in r.get("findings", []):
            first_raised.setdefault(f.get("fingerprint"), r["round"])
    pending = set(pending or [])
    ledger = {"resolved": dict((fp, first_raised.get(fp, 0)) for fp in (resolved or [])
                               if fp not in pending),
              "dismissed": sorted(dismissed)}
    if resolved_from_history:
        for r in rounds[:-1]:
            for f in r.get("findings", []):
                ledger["resolved"].setdefault(f.get("fingerprint"), r["round"])
    history = compute_history(base, rounds, ledger, cwd)
    decision = _annotated(decide(history, budget=budget), history)
    # Identifiers only: the decision crosses job outputs, and the
    # reviewer's free-text title is never part of it.
    decision["open_findings"] = [
        {"fingerprint": f.get("fingerprint"), "file": f.get("file"), "line": f.get("line")}
        for f in current.get("findings", []) if f.get("fingerprint") not in dismissed]
    return decision


def _annotated(decision, history):
    """decision plus what render_handoff reads off the history: the latest
    round's recurrences, and which git-derived signals could be computed."""
    decision["recurrences"] = history[-1]["recurrences"] if history else []
    decision["git_ok"] = bool(history and history[-1].get("git_ok"))
    decision["growth_recorded"] = any(r.get("growth_source") == "recorded" for r in history)
    decision["baseline_missing"] = bool(history and history[-1].get("baseline_missing"))
    return decision


def decide_history(base, rounds, ledger, cwd):
    """`decide --history`'s decision over a recorded history: the one the
    review-until-clean skill's --history prints too (SC-003)."""
    history = compute_history(base, rounds, ledger, cwd)
    decision = _annotated(decide(history), history)
    decision["open_findings"] = history[-1]["findings"] if history else []
    return decision


def _without_dismissed(rnd, dismissed):
    """rnd with its count less the dismissed entries (count - |dismissed
    and entries|). A record past MAX_RECORDED_FINDINGS keeps its whole
    count, so a dismissed finding beyond the kept entries stays counted.
    The entries themselves stay: attribution and recurrence read them, and
    the ledger's dismissed list already keeps them out of recurrences."""
    findings = rnd.get("findings", [])
    recorded = rnd.get("count")
    if not isinstance(recorded, int) or isinstance(recorded, bool):
        recorded = len(findings)
    hits = sum(1 for f in findings if f.get("fingerprint") in dismissed)
    return dict(rnd, count=max(recorded - hits, 0))


def _inert(text):
    return str(text or "").replace("<", "&lt;").replace(">", "&gt;")


def _pct(value, signed=False):
    if value is None:
        return "n/a"
    return ("{0:+.0%}" if signed else "{0:.0%}").format(value)


def render_handoff(decision):
    rounds = decision["signals"]
    n = rounds[-1]["round"] if rounds else 0
    lines = []
    if not decision.get("stop"):
        # No rule tripped (the board loop's budget-spent stall still lists
        # the signals): neither the not-converging marker nor its lead.
        lines.append("Convergence signals: no rule tripped.")
    elif decision.get("reason") == "budget-spent":
        lines.append("<!-- wing-commander-not-converging: round={0} -->".format(n))
        lines.append("Review stopped: the round budget is spent (stall reason "
                     "`budget-spent`). The PR is left open and unmerged.")
    else:
        lines.append("<!-- wing-commander-not-converging: round={0} -->".format(n))
        lines.append("Review stopped: not converging (stall reason "
                     "`not-converging`). The PR is left open and unmerged.")
    lines.append("")
    lines.append("Tripped: " + (", ".join(decision["tripped"]) or "none"))
    if decision.get("git_ok") is False:
        lines.append("")
        if decision.get("growth_recorded"):
            lines.append("An earlier round's head is unreachable from this "
                         "checkout (the branch was rebased or force-pushed), "
                         "so self-inflicted share and churn could not be "
                         "computed; growth is read from the diff size each "
                         "round's record stored at review time.")
        else:
            lines.append("An earlier round's head is unreachable from this "
                         "checkout (the branch was rebased or force-pushed), "
                         "so self-inflicted share, churn and growth could not "
                         "be computed: round 1's record stores no diff size.")
    if decision.get("baseline_missing"):
        lines.append("")
        lines.append("Round 1's record is missing, so growth and the first "
                     "round's churn could not be computed.")
    lines.append("")
    lines.append("| Round | Findings | Self-inflicted share | Churn | Growth | Recurrences |")
    lines.append("|---|---|---|---|---|---|")
    for s in rounds:
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            s["round"], s["count"], _pct(s["self_inflicted_share"]),
            "n/a" if s["churn"] is None else s["churn"],
            _pct(s["growth"], signed=True), len(s["recurrences"])))
    unattributable = sum(s["unattributable"] for s in rounds)
    lines.append("")
    lines.append("Unattributable findings: {0}".format(unattributable))
    open_findings = decision.get("open_findings") or []
    if open_findings:
        lines.append("")
        lines.append("Open in-scope findings:")
        recurring = set(decision.get("recurrences") or [])
        for f in open_findings[:MAX_HANDOFF_FINDINGS]:
            # The path is the reviewer's, and the hand-off is posted under
            # the App's identity: `<`/`>` as entities, so a path carrying
            # `<!-- ... -->` never reads back as an App-authored marker.
            lines.append("- `{0}:{1}` {2}{3}".format(
                _inert(f.get("file")), f.get("line") or "?", _inert(f.get("fingerprint", "")),
                " (recurring)" if f.get("fingerprint") in recurring else ""))
        if len(open_findings) > MAX_HANDOFF_FINDINGS:
            lines.append("- {0} more open in-scope finding(s) not listed.".format(
                len(open_findings) - MAX_HANDOFF_FINDINGS))
    return "\n".join(lines)


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_outputs(path, pairs):
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in pairs:
            fh.write("{0}={1}\n".format(k, v))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide", help="signals and decision over a recorded history")
    d.add_argument("--history", required=True, help="JSON file: list of rounds")
    d.add_argument("--base", default="origin/main")
    d.add_argument("--ledger", help="JSON file: {resolved:{fp:round}, dismissed:[fp]}")
    d.add_argument("--json", action="store_true")

    r = sub.add_parser("record", help="print one round's record marker")
    r.add_argument("--round", type=int, required=True)
    r.add_argument("--head-sha", required=True)
    r.add_argument("--issue", required=True)
    r.add_argument("--findings", required=True, help="JSON file: the round's reviewer findings")

    e = sub.add_parser("evaluate", help="a loop round's convergence decision")
    e.add_argument("--reviews", required=True,
                   help="JSON file: the PR's reviews (REST shape) carrying earlier round records")
    e.add_argument("--bot-login", required=True)
    e.add_argument("--round", type=int, required=True)
    e.add_argument("--head-sha", required=True)
    e.add_argument("--issue", required=True)
    e.add_argument("--findings", required=True, help="JSON file: this round's reviewer findings")
    e.add_argument("--base", default="origin/main")
    e.add_argument("--resolved", default="", help="comma-separated already-folded fingerprints")
    e.add_argument("--resolved-from-history", action="store_true")
    e.add_argument("--budget", type=int)
    e.add_argument("--decision-out", help="write the decision JSON here")
    e.add_argument("--handoff-out", help="write the hand-off markdown here")
    e.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))

    h = sub.add_parser("render-handoff", help="render a decision JSON as the hand-off")
    h.add_argument("--decision", required=True)
    args = parser.parse_args()

    if args.cmd == "record":
        entries = round_findings(_load_json(args.findings), args.issue)
        print(round_record_marker(args.round, args.head_sha, entries))
        return 0
    if args.cmd == "render-handoff":
        print(render_handoff(_load_json(args.decision)))
        return 0
    if args.cmd == "evaluate":
        entries = round_findings(_load_json(args.findings), args.issue)
        current = {"round": args.round, "head_sha": args.head_sha, "findings": entries}
        records = read_round_records(_load_json(args.reviews), args.bot_login)
        decision = evaluate(records, current, args.base, os.getcwd(),
                            resolved=[f for f in args.resolved.split(",") if f],
                            budget=args.budget,
                            resolved_from_history=args.resolved_from_history)
        if args.decision_out:
            with open(args.decision_out, "w", encoding="utf-8") as fh:
                json.dump(decision, fh)
        if args.handoff_out:
            with open(args.handoff_out, "w", encoding="utf-8") as fh:
                fh.write(render_handoff(decision) + "\n")
        _write_outputs(args.github_output, [
            ("stop", "true" if decision["stop"] else "false"),
            ("reason", decision["reason"] or ""),
            ("tripped", ",".join(decision["tripped"])),
            ("recurrences", str(len(decision["recurrences"])))])
        print(json.dumps({k: decision[k] for k in ("stop", "reason", "tripped", "recurrences")}))
        return 0

    rounds = _load_json(args.history)
    ledger = _load_json(args.ledger) if args.ledger else None
    decision = decide_history(args.base, rounds, ledger, os.getcwd())
    if args.json:
        print(json.dumps(decision, indent=2))
    else:
        print(render_handoff(decision) if decision["stop"] else "converging: no signal tripped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
