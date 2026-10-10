#!/usr/bin/env python3
"""Compare the watchdog diagnose shadow against the acting diagnose agent.

Emits the `trial` object of specs/110-haiku-5-5-tier-trial/contracts/trial-record.md.
Deterministic (Principle IX): no model call decides agreement.

Usage:
  compare-diagnose-shadow.py --baseline-findings F --baseline-verdict V
      --shadow-findings F --shadow-verdict V --shadow-refusal true|false
      --schema S

Exit 0 for any classifiable input; exit 2 for unreadable arguments.
"""
import argparse
import json
import re
import sys

STEP = "watchdog.diagnose"
CANDIDATE = "claude-haiku-5-5"
BASELINE_LABEL = "diagnose"


def die(msg):
    print(f"compare-diagnose-shadow: {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        die(f"cannot read {what} {path}: {exc}")


def load_findings(path, what):
    """Return the findings list, or None when the file is absent/unparseable."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        return data["findings"]
    if isinstance(data, list):
        return data
    return None


def normalise(name):
    name = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return name.strip("-")


def class_of(finding):
    cls = finding.get("class")
    if cls == "__new__":
        return normalise(finding.get("proposedClass"))
    return cls


def signal_ids(finding):
    return frozenset(e.get("signalId") for e in finding.get("evidence") or []
                     if isinstance(e, dict))


def schema_valid(findings, schema):
    """Structural check against the Opus schema's findings item shape."""
    items = (schema.get("properties", {}).get("findings", {}).get("items")
             if isinstance(schema, dict) else None) or {}
    props = items.get("properties", {})
    required = items.get("required", [])
    class_enum = props.get("class", {}).get("enum")
    sid_enum = (props.get("evidence", {}).get("items", {})
                .get("properties", {}).get("signalId", {}).get("enum"))
    for f in findings:
        if not isinstance(f, dict):
            return False
        if any(k not in f for k in required):
            return False
        if class_enum is not None and f.get("class") not in class_enum:
            return False
        ev = f.get("evidence")
        if not isinstance(ev, list):
            return False
        for e in ev:
            if not isinstance(e, dict) or "signalId" not in e:
                return False
            if sid_enum is not None and e["signalId"] not in sid_enum:
                return False
    return True


def keys(findings):
    return {(class_of(f), signal_ids(f)) for f in findings}


def render_key(key):
    return f"{key[0]}:{','.join(sorted(str(s) for s in key[1]))}"


def trial(outcome, baseline_verdict, filing_agree=None, shared=None,
          agree=None, differing=None):
    return {
        "step": STEP,
        "candidate_model": CANDIDATE,
        "baseline_run_label": BASELINE_LABEL,
        "outcome": outcome,
        "baseline_verdict": baseline_verdict,
        "filing_agree": filing_agree,
        "class_shared": shared,
        "class_agree": agree,
        "differing_fields": differing or [],
    }


def compare(args, schema):
    bv = args.baseline_verdict
    if bv != "healthy":
        return trial("no-baseline", bv)
    if args.shadow_refusal == "true":
        return trial("refused", bv)
    if args.shadow_verdict == "exhausted":
        return trial("exhausted", bv)
    if args.shadow_verdict != "healthy":
        return trial("error", bv)
    shadow = load_findings(args.shadow_findings, "shadow findings")
    if shadow is None or not schema_valid(shadow, schema):
        return trial("malformed", bv)
    baseline = load_findings(args.baseline_findings, "baseline findings")
    if baseline is None or not all(
            isinstance(f, dict) and isinstance(f.get("evidence") or [], list)
            for f in baseline):
        return trial("no-baseline", bv)

    bkeys, skeys = keys(baseline), keys(shadow)
    filing_agree = bkeys == skeys
    differing = sorted(render_key(k) for k in bkeys ^ skeys)

    # Class agreement over findings sharing a signalId set.
    bclass, sclass = {}, {}
    for f in baseline:
        bclass.setdefault(signal_ids(f), set()).add(class_of(f))
    for f in shadow:
        sclass.setdefault(signal_ids(f), set()).add(class_of(f))
    shared_sets = set(bclass) & set(sclass)
    agree = 0
    for sid in shared_sets:
        if bclass[sid] == sclass[sid]:
            agree += 1
        else:
            differing.append("class:" + ",".join(sorted(str(s) for s in sid)))
    differing = sorted(set(differing))
    outcome = "agreed" if filing_agree and agree == len(shared_sets) else "disagreed"
    return trial(outcome, bv, filing_agree, len(shared_sets), agree, differing)


def main(argv):
    p = argparse.ArgumentParser()
    for name in ("baseline-findings", "baseline-verdict", "shadow-findings",
                 "shadow-verdict", "shadow-refusal", "schema"):
        p.add_argument("--" + name, required=True)
    try:
        args = p.parse_args(argv)
    except SystemExit:
        sys.exit(2)
    if args.shadow_refusal not in ("true", "false"):
        die("--shadow-refusal must be true or false")
    schema = load_json(args.schema, "schema")
    print(json.dumps(compare(args, schema), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
