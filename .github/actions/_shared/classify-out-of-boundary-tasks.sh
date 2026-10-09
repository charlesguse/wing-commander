#!/usr/bin/env bash
# .github/actions/_shared/classify-out-of-boundary-tasks.sh
#
# The one home of the per-task write-boundary classification rule
# (specs/090-stage-write-boundary, research.md D3, data-model.md's
# classification table). wing-commander-write-boundary's front door calls
# this once per arm/ref, over the exact unchecked-items text
# wing-commander-tasks-checkbox-count already produced (never a second
# read of tasks.md), so the cycle and retry arms share one classifier
# (FR-006).
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/classify-out-of-boundary-tasks.sh" \
#     <unchecked-items> <no-write-paths> <tasks-path> <spec-dir>
# -- `bash file`, never the file itself, mirroring count-tasks-
# checkboxes.sh's own convention. <unchecked-items> is the literal
# multi-line text wing-commander-tasks-checkbox-count's own
# `unchecked-items` output already produced; <no-write-paths> is the same
# comma-separated, unsplit value implement.yml's own input carries;
# <tasks-path> is the spec's tasks.md path (e.g.
# specs/090-stage-write-boundary/tasks.md); <spec-dir> is that path's
# containing directory, carried through for interface parity with the
# composite's own inputs (contracts/write-boundary-mechanism.md §3).
#
# Per unchecked line: every backtick-quoted, slash-containing,
# whitespace-free token is a candidate path (research.md D3's exact
# extraction rule). A line with zero candidate tokens, or at least one
# candidate token not prefixed (literal string prefix, never substring --
# ".claude-extra/foo" does not match a ".claude/" boundary) by any
# no-write-paths entry, falls through untouched (FR-015) -- ordinary
# unfinished work, not an error. A line whose every candidate token IS
# prefixed by a no-write-paths entry is out-of-boundary: one
# findings-json entry, shaped to .github/schemas/stage-finding.schema.json,
# is emitted for it.
#
# review-gate-round-1 item 2 (prefix normalization) / review-gate-round-3
# (single-home follow-up): each no-write-paths entry is normalized to end
# in exactly one trailing slash before the prefix comparison, via the
# SAME shared helper (_shared/normalize-write-path-prefix.sh)
# wing-commander-tool-args/action.yml's compose step also calls before
# building the Edit()/Write() deny glob (`<prefix>/**`), so a
# no-trailing-slash entry like "specs" cannot over-match "specs-legacy/..."
# here while enforcement denies only "specs/**", with no second
# reimplementation of the transform to drift out of sync. Each candidate
# token also has a leading "./" stripped first, so a tasks.md line
# written with a leading "./" still classifies instead of silently
# under-matching and leaving the agent to retry a denied edit forever.
#
# Unlike count-tasks-checkboxes.sh, this script never fails the job over a
# task it cannot confidently classify -- falling through to "ordinary" is
# a valid, expected outcome (FR-015), not an error condition. Only a
# genuinely malformed invocation (a missing required argument) exits
# non-zero.
#
# review-gate-round-4 item 4: a path mentioned WITHOUT backtick quoting is
# indistinguishable from prose merely naming a path in passing and is never
# extracted as a candidate -- an accepted, narrow limitation of the
# extraction rule (spec.md Edge Cases), not a case this script silently
# mishandles. Loosening the rule to catch it risks the opposite failure
# this script exists to avoid: mis-classifying ordinary prose as
# out-of-boundary work.
#
# Emits, on stdout, key=value/heredoc-marker lines shaped for the caller
# to append straight to $GITHUB_OUTPUT (count-tasks-checkboxes.sh's own
# convention):
#   findings-json<<WING_COMMANDER_WRITE_BOUNDARY_FINDINGS_EOF
#   <JSON array, one entry per out-of-boundary unchecked line; [] if none>
#   WING_COMMANDER_WRITE_BOUNDARY_FINDINGS_EOF
#   all-unchecked-out-of-boundary=true|false
#   out-of-boundary-count=<digits>
set -uo pipefail

UNCHECKED_ITEMS="${1-}"
NO_WRITE_PATHS="${2-}"
TASKS_PATH="${3-}"
SPEC_DIR="${4-}"

if [ $# -lt 4 ]; then
  echo "classify-out-of-boundary-tasks.sh: usage: classify-out-of-boundary-tasks.sh <unchecked-items> <no-write-paths> <tasks-path> <spec-dir>" >&2
  exit 1
fi

# review-gate-round-3: normalize each no-write-paths entry through the ONE
# shared helper also called by wing-commander-tool-args/action.yml's
# compose step, before this value ever reaches the Python classifier below
# -- so there is exactly one trailing-slash canonicalization in the repo,
# never two independently-maintained copies.
NORMALIZE_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/normalize-write-path-prefix.sh"
NORMALIZED_NO_WRITE_PATHS=""
IFS=',' read -ra _nwp_items <<< "$NO_WRITE_PATHS"
for _nwp_item in "${_nwp_items[@]}"; do
  _nwp_norm="$(bash "$NORMALIZE_SCRIPT" "$_nwp_item")"
  [ -z "$_nwp_norm" ] && continue
  if [ -z "$NORMALIZED_NO_WRITE_PATHS" ]; then
    NORMALIZED_NO_WRITE_PATHS="$_nwp_norm"
  else
    NORMALIZED_NO_WRITE_PATHS="$NORMALIZED_NO_WRITE_PATHS,$_nwp_norm"
  fi
done

UNCHECKED_ITEMS="$UNCHECKED_ITEMS" NO_WRITE_PATHS="$NORMALIZED_NO_WRITE_PATHS" \
TASKS_PATH="$TASKS_PATH" SPEC_DIR="$SPEC_DIR" python3 - <<'PYEOF'
import json
import os
import re

unchecked_items = os.environ.get("UNCHECKED_ITEMS", "")
no_write_paths_raw = os.environ.get("NO_WRITE_PATHS", "")
tasks_path = os.environ["TASKS_PATH"]
# spec_dir is accepted for interface parity with the composite's own
# inputs (contracts/write-boundary-mechanism.md §3) -- every findings-json
# field this script emits is anchored to tasks_path, per data-model.md.
_spec_dir = os.environ.get("SPEC_DIR", "")

def normalize_token(token):
    while token.startswith("./"):
        token = token[2:]
    return token


# NO_WRITE_PATHS has already been through the shared normalize-write-path-
# prefix.sh helper (one trailing slash each) before reaching this process --
# only the comma-split/strip/empty-drop remains to do here.
prefixes = [p.strip() for p in no_write_paths_raw.split(",") if p.strip()]

TOKEN_RE = re.compile(r"`([^`\s]+)`")

lines = unchecked_items.split("\n") if unchecked_items else []
lines = [line for line in lines if line.strip()]

findings = []
for line in lines:
    tokens = TOKEN_RE.findall(line)
    candidates = [t for t in tokens if "/" in t]
    if not candidates:
        continue  # no path-like token -- falls through (FR-015)
    if not prefixes:
        continue  # empty boundary -- nothing ever classifies (FR-015)

    def out_of_boundary(token):
        normalized = normalize_token(token)
        return any(normalized.startswith(prefix) for prefix in prefixes)

    if not all(out_of_boundary(t) for t in candidates):
        continue  # at least one candidate is in-reach -- falls through

    out_paths = ", ".join(candidates)
    stripped = line.strip()
    title = "Task outside the write boundary: {0}".format(out_paths)
    if len(title) > 200:
        title = title[:197] + "..."
    what = ("This unchecked task names {0}, which is on the implement "
            "stage's no-write list, so the stage cannot make this edit "
            "itself.").format(out_paths)
    if len(what) > 4000:
        what = what[:3997] + "..."
    findings.append({
        "title": title,
        "what": what,
        "evidence": {
            "file_paths": [tasks_path],
            "detail": "{0}\n\nOut-of-boundary path(s): {1}".format(stripped, out_paths),
        },
        "fingerprint_basis": {
            "file_path": tasks_path,
            "gate_or_artifact": line,
        },
    })

all_out = bool(lines) and len(findings) == len(lines)

print("findings-json<<WING_COMMANDER_WRITE_BOUNDARY_FINDINGS_EOF")
print(json.dumps(findings))
print("WING_COMMANDER_WRITE_BOUNDARY_FINDINGS_EOF")
print("all-unchecked-out-of-boundary={0}".format("true" if all_out else "false"))
print("out-of-boundary-count={0}".format(len(findings)))
PYEOF
