#!/usr/bin/env bash
# Run the local gate suite against an untrusted workspace bundle and write a
# verdict (spec 095; contracts/workspace-bundle.md, gate-verdict.schema.json).
#
# Usage: contained-gate-suite.sh SITE BUNDLE_DIR TRUSTED_SHA VERDICT_OUT
#
# Runs in a credential-free job whose workspace is the trusted checkout of
# github.sha. Every byte of the bundle is hostile: the only thing taken from
# it is the commit history, checked out into a separate directory; the suite
# script itself is the trusted copy's. A missing, unverifiable or oversized
# bundle writes outcome=fail -- it never skips.
set -u

site="$1"
bundle_dir="$2"
trusted_sha="$3"
verdict_out="$4"
max_bundle_bytes=$((200 * 1024 * 1024))
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
verdict_py="$here/../../scripts/wc_gate_verdict.py"

write_verdict() { # outcome exit_code head_sha first_failure
  python3 "$verdict_py" write --site "$site" --trusted-sha "$trusted_sha" \
    --head-sha "$3" --outcome "$1" --exit-code "$2" \
    --first-failure "$4" --out "$verdict_out"
}

zero_sha="0000000000000000000000000000000000000000"
meta="$bundle_dir/meta.json"
bundle="$bundle_dir/bundle.git"
if [ ! -f "$meta" ] || [ ! -f "$bundle" ]; then
  write_verdict fail 1 "$zero_sha" "workspace bundle missing"
  exit 0
fi
head_sha="$(jq -r '.head_sha // empty' "$meta" 2>/dev/null)"
case "$head_sha" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
  *) head_sha="" ;;
esac
if [ "${#head_sha}" -ne 40 ]; then
  write_verdict fail 1 "$zero_sha" "workspace bundle metadata unreadable"
  exit 0
fi
size="$(wc -c < "$bundle")"
if [ "$size" -gt "$max_bundle_bytes" ]; then
  write_verdict fail 1 "$head_sha" "workspace bundle oversized"
  exit 0
fi
if ! git bundle verify "$bundle" >/dev/null 2>&1; then
  write_verdict fail 1 "$head_sha" "workspace bundle failed verification"
  exit 0
fi
if ! git fetch --quiet "$bundle" "+refs/*:refs/wc-gate/*" 2>/dev/null \
    || ! git checkout --quiet --detach "$head_sha" 2>/dev/null; then
  write_verdict fail 1 "$head_sha" "bundle does not contain head_sha"
  exit 0
fi

suite=".github/scripts/run-local-gates.py"
if [ ! -f "$suite" ]; then
  # Principle VI: a branch that predates the suite has nothing to run.
  write_verdict pass 0 "$head_sha" ""
  exit 0
fi
log="$(mktemp)"
python3 "$suite" >"$log" 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  write_verdict pass 0 "$head_sha" ""
else
  first="$(grep -m1 -iE 'fail|error' "$log" | cut -c1-500)"
  write_verdict fail "$rc" "$head_sha" "${first:-gate suite exited $rc}"
fi
exit 0
