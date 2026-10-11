#!/usr/bin/env bash
# Stubbed `gh` for verify-reference-image-pin-sync.py. The harness copies it
# to <tmp>/bin/gh and points STUB_DIR at a per-case directory:
#   reach              one full_name per line: what `api user/repos` returns
#   reach_fail         present: `api user/repos` fails with HTTP 401
#   runs.json          the JSON array `run list` filters with its own --jq
#   run_list_fail      present: `run list` fails
#   jobs/<id>-<a>.json the JSON object `run view <id> --attempt <a>` filters
#                      with its own --jq (absent: the view fails)
#   vars/<o>__<r>      the held value of the variable (absent: the read 404s)
#   probe_fail         repositories (one per line) whose variable read is refused (403)
#   set_fail           repositories (one per line) refusing every variable write (403)
#   set_fail_expected  repositories (one per line) refusing a write of any value
#                      other than the one they hold (the permission probe passes)
#   log                every invocation, one line each, appended here
set -u
echo "GH_TOKEN=${GH_TOKEN:-} $*" >> "${STUB_DIR}/log"

listed() { [ -f "${STUB_DIR}/$1" ] && grep -qxiF -- "$2" "${STUB_DIR}/$1"; }
arg_after() { # flag args...
  local flag="$1" prev="" a
  shift
  for a in "$@"; do
    [ "$prev" = "$flag" ] && { printf '%s' "$a"; return; }
    prev="$a"
  done
}

case "${1:-} ${2:-}" in
  "api user/repos"*)
    if [ -f "${STUB_DIR}/reach_fail" ]; then
      echo "gh: Bad credentials (HTTP 401)" >&2
      exit 1
    fi
    [ -f "${STUB_DIR}/reach" ] && cat "${STUB_DIR}/reach"
    exit 0
    ;;
  "api repos/"*)
    repo="${2#repos/}"
    repo="${repo%%/actions/*}"
    if listed probe_fail "$repo"; then
      echo "gh: Resource not accessible by personal access token (HTTP 403)" >&2
      exit 1
    fi
    f="${STUB_DIR}/vars/${repo/\//__}"
    if [ ! -f "$f" ]; then
      echo "gh: Not Found (HTTP 404)" >&2
      exit 1
    fi
    cat "$f"
    echo
    exit 0
    ;;
  "variable set")
    repo="$(arg_after --repo "$@")"
    body="$(arg_after --body "$@")"
    f="${STUB_DIR}/vars/${repo/\//__}"
    held=""
    [ -f "$f" ] && held="$(cat "$f")"
    if listed set_fail "$repo" || { listed set_fail_expected "$repo" && [ "$body" != "$held" ]; }; then
      echo "REFUSED ${repo} ${body}" >> "${STUB_DIR}/log"
      echo "gh: Resource not accessible by personal access token (HTTP 403)" >&2
      exit 1
    fi
    printf '%s' "$body" > "$f"
    exit 0
    ;;
  "run view")
    f="${STUB_DIR}/jobs/${3:-}-$(arg_after --attempt "$@").json"
    [ -f "$f" ] || exit 1
    exec jq -r "$(arg_after --jq "$@")" "$f"
    ;;
  "run list")
    [ -f "${STUB_DIR}/run_list_fail" ] && exit 1
    if [ -f "${STUB_DIR}/runs.json" ]; then
      exec jq -r "$(arg_after --jq "$@")" "${STUB_DIR}/runs.json"
    fi
    exit 0
    ;;
esac
echo "gh-stub: unexpected call: $*" >&2
exit 2
