#!/usr/bin/env bash
# Writes WING_COMMANDER_CONTAINER_IMAGE=<image>@<digest> to this repository
# and to the end-to-end test repository, after both image checks passed
# (specs/111-reference-image-pin-sync, contracts/pin-sync-script.md). The
# single home of the write: no workflow carries its own copy.
#
# Inputs (environment): SYNC_TOKEN, IMAGE, DIGEST, THIS_REPO, E2E_REPO,
# CHECKS_PASSED, RUN_NUMBER, OUTCOME_FILE, GITHUB_STEP_SUMMARY. The ambient
# GH_TOKEN (the workflow token) is used only to list this workflow's runs;
# SYNC_TOKEN is exported as GH_TOKEN for every other gh call and is never
# echoed.
set -euo pipefail

: "${OUTCOME_FILE:?OUTCOME_FILE is required}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
VAR=WING_COMMANDER_CONTAINER_IMAGE
WORKFLOW=wing-commander-e2e-reference-image.yml
AMBIENT_TOKEN="${GH_TOKEN:-}"
SYNC_TOKEN="${SYNC_TOKEN:-}"
E2E_REPO="${E2E_REPO:-}"
THIS_REPO="${THIS_REPO:-}"
IMAGE="${IMAGE:-}"
DIGEST="${DIGEST:-}"
CHECKS_PASSED="${CHECKS_PASSED:-}"
RUN_NUMBER="${RUN_NUMBER:-0}"
EXPECTED="${IMAGE}@${DIGEST}"

RECORDS="$(mktemp)"
trap 'rm -f "$RECORDS"' EXIT

# The sync set: this repository, plus the test repository when configured.
SYNC_SET=("$THIS_REPO")
if [ -n "$E2E_REPO" ] && [ "${E2E_REPO,,}" != "${THIS_REPO,,}" ]; then
  SYNC_SET+=("$E2E_REPO")
fi

record() { # repo status reason held expected
  jq -cn --arg repo "$1" --arg status "$2" --arg reason "$3" \
    --arg held "$4" --arg expected "$5" \
    '{repo:$repo,status:$status,reason:$reason,held:$held,expected:$expected}' >> "$RECORDS"
}

record_all() { # status reason
  local r
  for r in "${SYNC_SET[@]}"; do record "$r" "$1" "$2" "" "$EXPECTED"; done
}

finish() {
  if [ -z "$E2E_REPO" ]; then
    record "test repository" skipped "no test repository configured" "" ""
  fi
  jq -s '.' "$RECORDS" > "$OUTCOME_FILE"
  {
    echo "### Reference-image pin sync"
    echo ""
    echo "| Repository | Status | Reason | Held | Expected |"
    echo "|---|---|---|---|---|"
    jq -r '.[] | "| `\(.repo)` | \(.status) | \(.reason) | `\(.held)` | `\(.expected)` |"' "$OUTCOME_FILE"
  } >> "$SUMMARY"
  if jq -e 'any(.[]; .status == "failed")' "$OUTCOME_FILE" > /dev/null; then
    exit 1
  fi
  exit 0
}

sync_gh() { GH_TOKEN="$SYNC_TOKEN" gh "$@"; }

# 1. The image checks must have passed.
if [ "$CHECKS_PASSED" != "true" ]; then
  record_all skipped "image check did not pass"
  finish
fi

# 2. Validate the inputs before any API call.
repo_re='^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$'
bad=""
[[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || bad="digest is not sha256:<64 hex>"
[[ "$IMAGE" =~ ^[A-Za-z0-9._/:-]+$ ]] || bad="image name is empty or malformed"
for r in "${SYNC_SET[@]}"; do
  [[ "$r" =~ $repo_re ]] || bad="repository name is malformed"
done
if [ -n "$bad" ]; then
  record_all failed "$bad"
  finish
fi

# 3. A newer successful run has already synced: do not move the pin back.
newer=""
if runs="$(GH_TOKEN="$AMBIENT_TOKEN" gh run list --repo "$THIS_REPO" --workflow "$WORKFLOW" \
  --status success --json number --jq '.[].number' 2> /dev/null)"; then
  while IFS= read -r n; do
    if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt "$RUN_NUMBER" ] && { [ -z "$newer" ] || [ "$n" -gt "$newer" ]; }; then
      newer="$n"
    fi
  done <<< "$runs"
fi
if [ -n "$newer" ]; then
  record_all skipped "superseded by run ${newer}"
  finish
fi

# 4. The credential must reach exactly the sync set.
if [ -z "$SYNC_TOKEN" ]; then
  record_all failed "WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN is not set"
  finish
fi
if ! reach="$(sync_gh api 'user/repos?affiliation=owner,collaborator,organization_member' \
  --paginate --jq '.[].full_name' 2> /dev/null)"; then
  record_all failed "WING_COMMANDER_REFERENCE_IMAGE_SYNC_TOKEN was rejected when listing reachable repositories"
  finish
fi
reach_sorted="$(printf '%s\n' "$reach" | tr '[:upper:]' '[:lower:]' | sed '/^$/d' | sort -u)"
want_sorted="$(printf '%s\n' "${SYNC_SET[@]}" | tr '[:upper:]' '[:lower:]' | sort -u)"
if [ "$reach_sorted" != "$want_sorted" ]; then
  extra="$(comm -13 <(printf '%s\n' "$want_sorted") <(printf '%s\n' "$reach_sorted") | paste -sd, -)"
  missing="$(comm -23 <(printf '%s\n' "$want_sorted") <(printf '%s\n' "$reach_sorted") | paste -sd, -)"
  msg="credential reaches ${extra:-nothing extra}"
  [ -n "$missing" ] && msg="${msg}; does not reach ${missing}"
  record_all failed "$msg"
  finish
fi

# 5. Probe every repository before writing any.
declare -A HELD
for r in "${SYNC_SET[@]}"; do
  if ! HELD["$r"]="$(sync_gh api "repos/${r}/actions/variables/${VAR}" --jq .value 2> /dev/null)"; then
    record_all failed "could not read ${VAR} on ${r}"
    finish
  fi
done

# 6. Write only what differs.
for r in "${SYNC_SET[@]}"; do
  held="${HELD[$r]}"
  if [ "$held" = "$EXPECTED" ]; then
    record "$r" current "already current" "$held" "$EXPECTED"
  elif sync_gh variable set "$VAR" --repo "$r" --body "$EXPECTED" > /dev/null 2>&1; then
    record "$r" written "pin updated" "$held" "$EXPECTED"
  else
    record "$r" failed "write refused" "$held" "$EXPECTED"
  fi
done

# 7. Report.
finish
