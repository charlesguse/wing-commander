#!/usr/bin/env bash
# Run the local gate suite against an untrusted head and write a verdict
# (spec 095; contracts/workspace-bundle.md, gate-verdict.schema.json).
#
# Usage: contained-gate-suite.sh SITE BUNDLE_DIR TRUSTED_SHA VERDICT_OUT [HEAD_REF]
#
# Runs in a credential-free job whose working directory is the trusted
# checkout of github.sha. The head to gate comes from one of two places:
#   - a workspace bundle in BUNDLE_DIR (the board loop's fixer and
#     review-fixup: commits this run's agent made and nobody pushed yet);
#   - HEAD_REF, a branch the trusted checkout already fetched from origin
#     (implement's cycle-start suite: the spec branch, which this run did
#     not write), when it is non-empty. BUNDLE_DIR is ignored then.
# Every byte of that head is hostile: it is checked out into a separate
# worktree directory, and the verdict writer and the suite's existence
# check come from copies taken BEFORE it is. A missing, unverifiable or
# oversized bundle, or an unresolvable HEAD_REF, writes outcome=fail -- it
# never skips.
#
# The verdict is the head's own gate suite reporting on itself: a head
# that edits run-local-gates.py can make it say anything, as it always
# could. What this job contains is the credential, not the verdict's
# honesty.
set -u

site="$1"
bundle_dir="$2"
trusted_sha="$3"
verdict_out="$4"
head_ref="${5:-}"
max_bundle_bytes=$((200 * 1024 * 1024))
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
trusted_root="$(pwd -P)"

# Trusted copy of the pipeline's scripts, taken before the hostile head is
# checked out anywhere.
trusted_copy="$(mktemp -d)"
cp -R "$here/../../scripts" "$trusted_copy/scripts"
verdict_py="$trusted_copy/scripts/wc_gate_verdict.py"
# Principle VI: whether this repository has a gate suite at all is read
# from the trusted checkout (an adopter repository has none, #935), never
# from the head, which could delete it to dodge the gate.
trusted_has_suite=false
[ -f "$trusted_root/.github/scripts/run-local-gates.py" ] && trusted_has_suite=true

write_verdict() { # outcome exit_code head_sha first_failure
  python3 -I "$verdict_py" write --site "$site" --trusted-sha "$trusted_sha" \
    --head-sha "$3" --outcome "$1" --exit-code "$2" \
    --first-failure="$4" --out "$verdict_out"
}

zero_sha="0000000000000000000000000000000000000000"
is_sha() { printf '%s' "$1" | grep -Eq '^[0-9a-f]{40}$'; }

if [ -n "$head_ref" ]; then
  head_sha="$(git rev-parse --verify --quiet "refs/remotes/origin/${head_ref}^{commit}" 2>/dev/null)"
  if ! is_sha "${head_sha:-}"; then
    write_verdict fail 1 "$zero_sha" "head ref origin/$head_ref not found in the trusted checkout"
    exit 0
  fi
else
  meta="$bundle_dir/meta.json"
  bundle="$bundle_dir/bundle.git"
  if [ ! -f "$meta" ] || [ ! -f "$bundle" ]; then
    write_verdict fail 1 "$zero_sha" "workspace bundle missing"
    exit 0
  fi
  head_sha="$(jq -r '.head_sha // empty' "$meta" 2>/dev/null)"
  base_sha="$(jq -r '.base_sha // empty' "$meta" 2>/dev/null)"
  if ! is_sha "${head_sha:-}"; then
    write_verdict fail 1 "$zero_sha" "workspace bundle metadata unreadable"
    exit 0
  fi
  size="$(wc -c < "$bundle")"
  if [ "$size" -gt "$max_bundle_bytes" ]; then
    write_verdict fail 1 "$head_sha" "workspace bundle oversized"
    exit 0
  fi
  # A thin bundle needs its prerequisite commit. The trusted checkout is
  # a full-history fetch, so it normally holds it; when it does not, try
  # the origin without credentials (a public repository is readable).
  if is_sha "${base_sha:-}" && ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
    git fetch --quiet --no-tags origin "$base_sha" 2>/dev/null || true
  fi
  if ! git bundle verify "$bundle" >/dev/null 2>&1; then
    write_verdict fail 1 "$head_sha" "workspace bundle failed verification"
    exit 0
  fi
  # The bundle carries one ref, HEAD (build-gate-bundle.sh).
  if ! git fetch --quiet --no-tags "$bundle" "+HEAD:refs/wc-gate/head" 2>/dev/null; then
    write_verdict fail 1 "$head_sha" "bundle does not contain head_sha"
    exit 0
  fi
fi

if [ "$trusted_has_suite" != "true" ]; then
  write_verdict pass 0 "$head_sha" ""
  exit 0
fi
work="$(mktemp -d)/work"
if ! git worktree add --quiet --detach "$work" "$head_sha" 2>/dev/null; then
  write_verdict fail 1 "$head_sha" "head $head_sha could not be checked out"
  exit 0
fi
if [ ! -f "$work/.github/scripts/run-local-gates.py" ]; then
  write_verdict fail 1 "$head_sha" "head removed run-local-gates.py"
  exit 0
fi
log="$(mktemp)"
(cd "$work" && python3 .github/scripts/run-local-gates.py) >"$log" 2>&1
rc=$?
cat "$log"
if [ "$rc" -eq 0 ]; then
  write_verdict pass 0 "$head_sha" ""
else
  first="$(grep -m1 -E '^(FAIL|ERROR)\b' "$log" | cut -c1-500)"
  write_verdict fail "$rc" "$head_sha" "${first:-gate suite exited $rc}"
fi
exit 0
