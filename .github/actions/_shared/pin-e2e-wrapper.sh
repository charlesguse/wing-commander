#!/usr/bin/env bash
# Pins one of this repository's own wrapper workflows for an end-to-end
# test repository, and prints the pinned file on stdout. The one home of
# that rewrite: auto-release.yml's scaffold step and
# .github/scripts/provision-e2e-target.sh both call it, and
# .github/scripts/verify-e2e-provisioning-single-home.py fails if either
# goes back to an inline sed.
#
# Two rewrites, both needed once the wrapper runs in another repository:
#
#   * `uses: ./.github/workflows/<stage>` becomes
#     `uses: <pipeline-repo>/.github/workflows/<stage>@<uses-ref>`.
#   * `pipeline-ref: ${{ github.sha }}` becomes
#     `pipeline-ref: <pipeline-commit>`. Here the wrapper calls its stage
#     by local path, so github.sha is the pipeline's own commit (#1071,
#     #1077). Copied into a test repository, github.sha is that
#     repository's commit, which the pipeline repository does not have, so
#     every job that checks the pipeline out failed with "not our ref" and
#     the lifecycle sat in stage:tasks until the poll budget ran out
#     (#1083).
#
# Fails (exit 1, reason on stderr, nothing on stdout) when the file still
# calls its stage by local path after the rewrite, or still passes
# github.sha as pipeline-ref, so a reformatted wrapper line can't make
# either rewrite silently do nothing.
#
# Invoke with `bash .github/actions/_shared/pin-e2e-wrapper.sh FILE STAGE
# PIPELINE_REPO USES_REF PIPELINE_COMMIT` -- never sourced.
set -euo pipefail

if [ "$#" -ne 5 ]; then
  echo "pin-e2e-wrapper.sh: usage: FILE STAGE PIPELINE_REPO USES_REF PIPELINE_COMMIT" >&2
  exit 2
fi
file=$1 stage=$2 pipeline_repo=$3 uses_ref=$4 pipeline_commit=$5

if ! printf '%s' "$pipeline_commit" | grep -qE '^[0-9a-f]{40}$'; then
  echo "pin-e2e-wrapper.sh: PIPELINE_COMMIT must be a full 40-character commit SHA, got '$pipeline_commit'" >&2
  exit 1
fi

pinned="$(sed \
  -e "s#uses: \./\.github/workflows/${stage}#uses: ${pipeline_repo}/.github/workflows/${stage}@${uses_ref}#" \
  -e "s#pipeline-ref: \${{ *github\.sha *}}#pipeline-ref: ${pipeline_commit}#" \
  "$file")"

# Here-strings, not `printf | grep -q`: under pipefail, grep -q exiting on
# its first match can SIGPIPE a printf still writing a large file, and the
# pipeline's 141 would read as "no match" and skip the refusal.
if grep -qE "uses: \./\.github/workflows/" <<<"$pinned"; then
  echo "pin-e2e-wrapper.sh: $file still calls a stage by local path after pinning (stage '$stage')" >&2
  exit 1
fi
if grep -qE 'pipeline-ref:.*github\.sha' <<<"$pinned"; then
  echo "pin-e2e-wrapper.sh: $file still passes github.sha as pipeline-ref after pinning; in a test repository that is the test repository's commit, not the pipeline's" >&2
  exit 1
fi

printf '%s\n' "$pinned"
