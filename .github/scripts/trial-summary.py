#!/usr/bin/env python3
"""Deterministic Haiku 5.5 trial summary from the metrics branch alone.

Reads records.jsonl (one metrics record per line) and prints Markdown:

* Diagnose shadow: runs, agreement, refusal / exhaustion / malformed counts,
  median turns and cost per run on each model, and meets / misses / sample
  too small against the FR-017 bar (200 compared runs; (a) >= 95% filing
  agreement, (b) >= 90% class agreement over shared findings, (c) refused +
  exhausted + malformed <= 2% of compared runs; error and no-baseline runs
  are excluded from every denominator).
* Implement opt-in: per lifecycle issue with a top-level model of
  claude-haiku-5-5, cycles, escalation tiers, refusals, exhaustions and total
  cost, beside the median Sonnet lifecycle. No verdict.

Model identity is always the record's top-level `model`; a claude-haiku-5-5
`per_model` entry on another model's record is Claude Code's helper and is
never counted. See specs/110-haiku-5-5-tier-trial/research.md D12.

With --since (the WING_COMMANDER_DIAGNOSE_SHADOW_SINCE date), the diagnose
section counts only records in the trial window trial-bound.py counts: dated
on or after SINCE, an undated record counting as inside it. A restarted
trial is then summarised over its own window, the one its bound closes.
The window and run_label rules are imported from
.github/actions/_shared/trial-bound.py, their one home. The two counts still
differ by design: the cap also counts comparator errors and shadow records
with no trial object (spend the bar does not judge); FR-017's compared runs
do not. verify-trial-summary.py holds that difference exact.

Usage: trial-summary.py --records records.jsonl [--since YYYY-MM-DD]
Exit 2 for a missing or unparseable records file or SINCE.
"""
import argparse
import importlib.util
import os
import json
import math
import re
import statistics
import sys

HAIKU = "claude-haiku-5-5"
MIN_COMPARED = 200
FAILED = {"refused", "exhausted", "malformed"}
IMPLEMENT_LABELS = {"cycle", "retry"}


def load(path):
    records = []
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    if not isinstance(rec, dict):
                        raise ValueError(f"line {lineno}: record is not an object")
                    records.append(rec)
    except (OSError, ValueError) as exc:
        print(f"trial-summary: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    return records


def _load_bound():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "actions", "_shared", "trial-bound.py")
    spec = importlib.util.spec_from_file_location("trial_bound", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BOUND = _load_bound()
label = _BOUND.label
readable_trial = _BOUND.readable_trial
# FR-017's not-compared outcomes, from the same home as the cap's.
NOT_COMPARED = _BOUND.NOT_COUNTED


DIGITS = re.compile(r"[0-9]+")


def scalar(value):
    """A JSON string or integer id as a string, else None (never an
    unhashable key). A numeric id is canonical decimal, so 972, "972" and
    "0972" are one id."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return str(int(text)) if DIGITS.fullmatch(text) else text


def number(value):
    """A finite JSON number, else None: a string, an object, NaN or an
    infinity where a count or a cost belongs is read as absent, never
    summed into a TypeError or a nan."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) \
            and math.isfinite(value):
        return value
    return None


def run_id(rec):
    run = rec.get("run")
    return scalar(run.get("workflow_run_id")) if isinstance(run, dict) else None


def turns(rec):
    t = rec.get("turns")
    if not isinstance(t, dict) or not t.get("available"):
        return None
    return number(t.get("counted"))


def cost(rec):
    return number(rec.get("cost_usd")) if rec.get("cost_available") else None


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def fmt(value, money=False):
    if value is None:
        return "n/a"
    return f"${value:.4f}" if money else f"{value:g}"


def pct(num, den):
    return f"{100 * num / den:.1f}%" if den else "n/a"


def in_window(rec, since):
    """trial-bound.py's window (its in_window); no SINCE means every record."""
    return since is None or _BOUND.in_window(rec, since)


def diagnose_section(records, since=None):
    records = [r for r in records if in_window(r, since)]
    all_shadow = [r for r in records if label(r) == "diagnose-shadow"]
    shadow = [r for r in all_shadow if readable_trial(r) is not None]
    # Both model rows cover the compared runs only (a no-baseline run never
    # called the shadow; an error run is infrastructure), the acting row
    # matched to them by workflow run, so both describe one population.
    compared_shadow = [r for r in shadow
                       if r["trial"].get("outcome") not in NOT_COMPARED]
    shadow_runs = {run_id(r) for r in compared_shadow} - {None}
    opus = [r for r in records if label(r) == "diagnose"
            and run_id(r) in shadow_runs]
    counts = {}
    for r in shadow:
        o = r["trial"].get("outcome")
        counts[o] = counts.get(o, 0) + 1
    compared = [r for r in shadow if r["trial"].get("outcome") not in NOT_COMPARED]
    n = len(compared)
    agreed = counts.get("agreed", 0)
    outcomes = (", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                or "none")
    # (a) filing agreement: refused / exhausted / malformed count as not agreeing.
    filing = sum(1 for r in compared if r["trial"].get("filing_agree") is True
                 and r["trial"].get("outcome") not in FAILED)
    # (b) only runs that reached the findings comparison carry class counts.
    judged = [r for r in compared
              if r["trial"].get("outcome") in ("agreed", "disagreed")]
    shared = sum(number(r["trial"].get("class_shared")) or 0 for r in judged)
    cagree = sum(number(r["trial"].get("class_agree")) or 0 for r in judged)
    failed = sum(counts.get(o, 0) for o in FAILED)
    # A comparator crash is this pipeline's defect, not infrastructure:
    # named on its own so it is never mistaken for a 429 (trial-record).
    comparator_errors = sum(1 for r in shadow
                            if r["trial"].get("error_source") == "comparator")
    window = (f"since {since.isoformat()}" if since is not None
              else "all records")
    lines = ["## Diagnose shadow", "",
             f"- Window: {window}",
             f"- Shadow runs with a trial record: {len(shadow)}"
             f" (without a readable one: {len(all_shadow) - len(shadow)})",
             f"- Compared runs (error and no-baseline excluded): {n}",
             f"- Outcomes: {outcomes}",
             f"- Fully agreed: {agreed}",
             f"- (a) Filing agreement: {pct(filing, n)} (bar 95%)",
             f"- (b) Class agreement on shared findings: {pct(cagree, shared)}"
             f" ({cagree}/{shared}, bar 90%)",
             f"- (c) Refused + exhausted + malformed: {failed} "
             f"({pct(failed, n)} of compared, bar at most 2%); "
             f"refused={counts.get('refused', 0)}, "
             f"exhausted={counts.get('exhausted', 0)}, "
             f"malformed={counts.get('malformed', 0)}",
             f"- Errors (reported separately): {counts.get('error', 0)}, of "
             f"which comparator errors: {comparator_errors}; "
             f"no-baseline: {counts.get('no-baseline', 0)}",
             "",
             "| Model | Runs | Median turns | Median cost |",
             "|---|---|---|---|"]
    for name, group in (("Opus diagnose (acting, same runs)", opus),
                        (HAIKU + " shadow (compared runs)", compared_shadow)):
        lines.append(f"| {name} | {len(group)} | "
                     f"{fmt(median([turns(r) for r in group]))} | "
                     f"{fmt(median([cost(r) for r in group]), True)} |")
    lines.append("")
    if n < MIN_COMPARED:
        verdict = "sample too small"
    else:
        ok = (filing / n >= 0.95 and (shared == 0 or cagree / shared >= 0.90)
              and failed / n <= 0.02)
        verdict = "meets" if ok else "misses"
    lines.append(f"**Diagnose bar ({MIN_COMPARED} compared runs): {verdict}**")
    if n >= MIN_COMPARED and shared == 0:
        # (b) is vacuous with nothing to compare (review-gate round 3);
        # say so, so the verdict is not read as a class measurement.
        lines.append("Bar (b) was not measured: no finding was raised by "
                     "both models on a shared signal set.")
    return lines


def lifecycle_stats(recs):
    cost_total = sum(cost(r) or 0 for r in recs)
    # An escalation is implement's one-tier-up retry, which it records under
    # run_label "retry" on the escalation model. A cycle that merely ran on
    # that tier is not another one: a truncated retry's carry-forward keeps
    # its tier (implement.yml "Resolve effective model"), so Haiku, retry
    # on Sonnet, Sonnet, Sonnet is one escalation, not three.
    tiers = [str(r.get("model")) for r in recs if label(r) == "retry"]
    return {"cycles": len(recs), "escalations": tiers,
            "refusals": sum(1 for r in recs if r.get("refusal") is True),
            "exhaustions": sum(1 for r in recs
                               if str(r.get("outcome")) == "exhausted"),
            "cost": cost_total}


def implement_section(records):
    by_issue = {}
    for r in records:
        # Only the implement agent's own cycles: the stage also writes
        # "progress comment" records on the summary tier (claude-haiku-5-5
        # by default) and a transcript-less "branch advance" record, and
        # either would make every lifecycle look like a Haiku opt-in.
        if r.get("stage") != "implement" or label(r) not in IMPLEMENT_LABELS:
            continue
        spec = r.get("spec")
        issue = scalar(spec.get("issue")) if isinstance(spec, dict) else None
        if issue is None:
            continue
        by_issue.setdefault(issue, []).append(r)
    haiku, sonnet = {}, []
    # Numeric order (#972 before #1001), any non-numeric key after.
    for issue, recs in sorted(by_issue.items(), key=lambda kv: (
            not DIGITS.fullmatch(kv[0]),
            int(kv[0]) if DIGITS.fullmatch(kv[0]) else 0, kv[0])):
        # A record without a timestamp sorts last, never first.
        recs.sort(key=lambda r: (not r.get("emitted_at"), str(r.get("emitted_at") or "")))
        models = [str(r.get("model", "")) for r in recs]
        if HAIKU in models:
            haiku[issue] = lifecycle_stats(recs)
        elif all(m.startswith("claude-sonnet") for m in models):
            # Only pure-Sonnet lifecycles form the baseline (no Opus cycle).
            sonnet.append(lifecycle_stats(recs))
    lines = ["## Implement opt-in (`model:haiku`)", ""]
    if sonnet:
        base = (f"median Sonnet lifecycle over {len(sonnet)}: cycles "
                f"{fmt(median([s['cycles'] for s in sonnet]))}, refusals "
                f"{fmt(median([s['refusals'] for s in sonnet]))}, exhaustions "
                f"{fmt(median([s['exhaustions'] for s in sonnet]))}, cost "
                f"{fmt(median([s['cost'] for s in sonnet]), True)}")
    else:
        base = "no Sonnet lifecycle on the metrics branch"
    lines.append(f"- Baseline: {base}")
    lines += ["", "| Issue | Cycles | Escalations (tier) | Refusals | "
              "Exhaustions | Total cost |", "|---|---|---|---|---|---|"]
    if not haiku:
        lines.append("| none | | | | | |")
    for issue, s in haiku.items():
        esc = f"{len(s['escalations'])} ({', '.join(s['escalations'])})" \
            if s["escalations"] else "0"
        lines.append(f"| #{issue} | {s['cycles']} | {esc} | {s['refusals']} | "
                     f"{s['exhaustions']} | {fmt(s['cost'], True)} |")
    lines += ["", "No numeric verdict: the owner judges from these figures "
              "and the final-PR review."]
    return lines


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--records", required=True)
    p.add_argument("--since", default="")
    args = p.parse_args(argv)
    since = None
    if args.since.strip():
        try:
            since = _BOUND.parse_date(args.since)
        except ValueError as exc:
            print(f"trial-summary: unreadable --since: {exc}", file=sys.stderr)
            return 2
    records = load(args.records)
    out = ["# Haiku 5.5 trial summary", ""]
    out += diagnose_section(records, since) + [""] + implement_section(records)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
