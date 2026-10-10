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

Usage: trial-summary.py --records records.jsonl
Exit 2 for a missing or unparseable records file.
"""
import argparse
import json
import statistics
import sys

HAIKU = "claude-haiku-5-5"
MIN_COMPARED = 200
NOT_COMPARED = {"error", "no-baseline"}
FAILED = {"refused", "exhausted", "malformed"}


def load(path):
    records = []
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except (OSError, ValueError) as exc:
        print(f"trial-summary: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    return records


def label(rec):
    return rec.get("run_label") or (rec.get("run") or {}).get("run_label")


def turns(rec):
    t = rec.get("turns") or {}
    return t.get("counted") if t.get("available") else None


def cost(rec):
    return rec.get("cost_usd") if rec.get("cost_available") else None


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def fmt(value, money=False):
    if value is None:
        return "n/a"
    return f"${value:.4f}" if money else f"{value:g}"


def pct(num, den):
    return f"{100 * num / den:.1f}%" if den else "n/a"


def diagnose_section(records):
    shadow = [r for r in records if label(r) == "diagnose-shadow"
              and isinstance(r.get("trial"), dict)]
    opus = [r for r in records if label(r) == "diagnose"]
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
    shared = sum(r["trial"].get("class_shared") or 0 for r in judged)
    cagree = sum(r["trial"].get("class_agree") or 0 for r in judged)
    failed = sum(counts.get(o, 0) for o in FAILED)
    lines = ["## Diagnose shadow", "",
             f"- Shadow runs with a trial record: {len(shadow)}",
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
             f"- Errors (reported separately): {counts.get('error', 0)}; "
             f"no-baseline: {counts.get('no-baseline', 0)}",
             "",
             "| Model | Runs | Median turns | Median cost |",
             "|---|---|---|---|"]
    for name, group in (("Opus diagnose (acting)", opus),
                        (HAIKU + " shadow", shadow)):
        lines.append(f"| {name} | {len(group)} | "
                     f"{fmt(median([turns(r) for r in group]))} | "
                     f"{fmt(median([cost(r) for r in group]), True)} |")
    lines.append("")
    if n < MIN_COMPARED:
        verdict = "sample too small"
    else:
        ok = (filing / n >= 0.95 and shared > 0 and cagree / shared >= 0.90
              and failed / n <= 0.02)
        verdict = "meets" if ok else "misses"
    lines.append(f"**Diagnose bar ({MIN_COMPARED} compared runs): {verdict}**")
    return lines


def lifecycle_stats(recs, start_model):
    cost_total = sum(cost(r) or 0 for r in recs)
    # Escalations are cycles that ran above the tier the lifecycle opted
    # into, so a Haiku, Sonnet, Haiku sequence counts one, not two.
    tiers = [str(r.get("model")) for r in recs
             if r.get("model") != start_model]
    return {"cycles": len(recs), "escalations": tiers,
            "refusals": sum(1 for r in recs if r.get("refusal") is True),
            "exhaustions": sum(1 for r in recs
                               if str(r.get("outcome")) == "exhausted"),
            "cost": cost_total}


def implement_section(records):
    by_issue = {}
    for r in records:
        if r.get("stage") != "implement":
            continue
        issue = (r.get("spec") or {}).get("issue")
        if issue is None:
            continue
        by_issue.setdefault(issue, []).append(r)
    haiku, sonnet = {}, []
    for issue, recs in sorted(by_issue.items()):
        # A record without a timestamp sorts last, never first.
        recs.sort(key=lambda r: (not r.get("emitted_at"), r.get("emitted_at") or ""))
        models = [str(r.get("model", "")) for r in recs]
        if HAIKU in models:
            haiku[issue] = lifecycle_stats(recs, HAIKU)
        elif all(m.startswith("claude-sonnet") for m in models):
            # Only pure-Sonnet lifecycles form the baseline (no Opus cycle).
            sonnet.append(lifecycle_stats(recs, models[0]))
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
    args = p.parse_args(argv)
    records = load(args.records)
    out = ["# Haiku 5.5 trial summary", ""]
    out += diagnose_section(records) + [""] + implement_section(records)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
