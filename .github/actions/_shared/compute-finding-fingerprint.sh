#!/usr/bin/env bash
# .github/actions/_shared/compute-finding-fingerprint.sh
#
# The one home of the anchor/fallback fingerprint formula
# (specs/090-stage-write-boundary, research.md D6). Before this feature,
# this exact computation (normalize_basis / verify_anchor / the two
# hashlib.sha256(`anchor|...`/`fallback|...`) calls) lived inline in
# wing-commander-stage-findings/action.yml's "Extract, validate, cap, and
# prepare findings" step. finalize.yml's "Look up routed write-boundary
# items" step (specs/090-stage-write-boundary §6) needs to recompute the
# identical value for an unchecked tasks.md line without re-running that
# whole composite, so the formula is extracted here and both callers
# invoke it -- never a second copy (CLAUDE.md's "Shared logic has exactly
# one home"; Gate 126 (g) asserts no third sha256(anchor|...)/
# sha256(fallback|...)-shaped literal exists anywhere else under .github/.
#
# Invoke with
#   bash "$GITHUB_ACTION_PATH/../_shared/compute-finding-fingerprint.sh" \
#     <stage> <file_path> <gate_or_artifact>
# -- `bash file`, never the file itself, mirroring count-tasks-checkboxes.sh
# and read-spec-meta.sh's own convention.
#
# <file_path> is resolved against the current working directory exactly as
# wing-commander-stage-findings' own inline verify_anchor() already did:
# the anchor shape is used only when <file_path>, read from the checkout at
# invocation time, actually contains <gate_or_artifact> (normalized); any
# other case -- missing file, path escaping the checkout, or the text not
# found -- falls back to the fallback shape. Prints, on stdout,
#   fingerprint=<sha256 hex digest>
#   verified=true|false
# -- the caller reads `verified` when it needs the same "anchor
# unverifiable" note wing-commander-stage-findings' recap notes already
# compose; the fingerprint alone is all finalize.yml's lookup step needs.
set -uo pipefail

STAGE="${1:-}"
FILE_PATH="${2:-}"
GATE_OR_ARTIFACT="${3:-}"

if [ -z "$STAGE" ] || [ -z "$FILE_PATH" ] || [ -z "$GATE_OR_ARTIFACT" ]; then
  echo "compute-finding-fingerprint.sh: usage: compute-finding-fingerprint.sh <stage> <file_path> <gate_or_artifact>" >&2
  exit 1
fi

STAGE="$STAGE" FILE_PATH="$FILE_PATH" GATE_OR_ARTIFACT="$GATE_OR_ARTIFACT" python3 - <<'PYEOF'
import hashlib
import os
import re

STAGE = os.environ["STAGE"]
FILE_PATH = os.environ["FILE_PATH"]
GATE_OR_ARTIFACT = os.environ["GATE_OR_ARTIFACT"]


def normalize_basis(value):
    # \W keeps letters and digits in any script (an accented letter
    # survives); underscores go with the punctuation. Byte-for-byte the
    # same rule wing-commander-stage-findings' own inline copy used.
    return " ".join(re.sub(r"[\W_]+", " ", str(value).lower()).split())


def verify_anchor(file_path, gate_or_artifact):
    # contracts/anchor-verification.md steps 1-4: resolve file_path
    # against this step's own working directory; a path outside that tree
    # (e.g. via `..`) or that is not a readable regular file is
    # unverifiable, never a hard failure.
    cwd = os.getcwd()
    resolved = os.path.abspath(os.path.join(cwd, file_path))
    try:
        within = os.path.commonpath([cwd, resolved]) == cwd
    except ValueError:
        within = False
    if not within or not os.path.isfile(resolved):
        return False, None
    try:
        with open(resolved, encoding="utf-8", errors="replace") as fh:
            file_text = fh.read()
    except OSError:
        return False, None
    norm_gate = normalize_basis(gate_or_artifact)
    if not norm_gate:
        # research.md D1: an anchor that normalizes to empty (e.g. only
        # punctuation) is never treated as verified -- an empty string is
        # trivially "contained" in everything.
        return False, None
    if norm_gate in normalize_basis(file_text):
        return True, norm_gate
    return False, None


norm_path = normalize_basis(FILE_PATH)
verified, norm_gate = verify_anchor(FILE_PATH, GATE_OR_ARTIFACT)
if verified:
    fp = hashlib.sha256("anchor|{0}|{1}|{2}".format(
        STAGE, norm_path, norm_gate
    ).encode("utf-8")).hexdigest()
else:
    fp = hashlib.sha256("fallback|{0}|{1}".format(
        STAGE, norm_path
    ).encode("utf-8")).hexdigest()

print("fingerprint={0}".format(fp))
print("verified={0}".format("true" if verified else "false"))
PYEOF
