#!/usr/bin/env bash
# The one home for "is this lifecycle issue open?" -- a live, retried
# `gh issue view --json state` read (specs/022-gate-closed-lifecycle,
# specs/039-lifecycle-gate-retry). Two composites run it, each from its own
# $GITHUB_ACTION_PATH, never a workspace-relative path:
#   - wing-commander-lifecycle-gate (step `Check lifecycle issue state`),
#     the front door every stage workflow uses;
#   - wing-commander-board-stop-check (step `closed-check`), whose former
#     nested `uses: ./.github/actions/wing-commander-lifecycle-gate`
#     resolved against the CALLER's $GITHUB_WORKSPACE, not the composite's
#     own trusted checkout (#1210) -- a composite cannot name a sibling
#     composite relative to itself, but it can run a sibling script.
# Gate 25 (verify-lifecycle-gate-retry.py) drives this file under a stubbed
# `gh` and mutates it; verify-board-stop-check.py drives it through the
# board-stop-check step from a workspace with no .github/ in it.
#
# Usage: lifecycle-issue-state.sh gh issue view "$ISSUE_NUMBER" --json state --jq .state
# The read command itself is the caller's argv, not this file's: Gate 12
# (verify-gate-12-token-permissions.py) resolves each gh call's token from
# the composite step that makes it and refuses a gh call inside a _shared
# script, so each calling step names the `gh issue view` with its own
# GH_TOKEN env and this file supplies the timeout, retry and
# classification around it.
#
# Env: GH_TOKEN, ISSUE_NUMBER (and GH_REPO when the cwd is not a checkout).
# Writes `state` and `is-open` to $GITHUB_OUTPUT; exits non-zero rather
# than guessing.
set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "::error::wing-commander-lifecycle-gate: lifecycle-issue-state.sh was called with no read command (expected: gh issue view \"\$ISSUE_NUMBER\" --json state --jq .state)."
  exit 1
fi

max_attempts=3
read_timeout=4
attempt=0
state=""
last_diagnostic=""
last_class_phrase=""

sanitize() {
  local text="$1"
  text="$(printf '%s' "$text" | tr '\r\n\t' '   ')"
  text="$(printf '%s' "$text" | tr -s ' ')"
  if [ "${#text}" -gt 300 ]; then
    text="${text:0:300}… (truncated)"
  fi
  printf '%s' "${text//%/%25}"
}

while [ "$attempt" -lt "$max_attempts" ]; do
  attempt=$((attempt + 1))
  stderr_file="$(mktemp)"

  if state="$(timeout "$read_timeout" "$@" 2>"$stderr_file")"; then
    diagnostic="$(cat "$stderr_file")"
    rm -f "$stderr_file"
    if [ -n "$state" ]; then
      break
    fi
    [ -z "$diagnostic" ] && diagnostic="gh exited 0 but returned an empty state"
  else
    rc=$?
    diagnostic="$(cat "$stderr_file")"
    rm -f "$stderr_file"
    # A `timeout` expiry is the transient class FR-001 names first,
    # and it is the one that says nothing for itself: `timeout` exits
    # 124 having written NOTHING to stderr (the familiar "terminated"
    # line comes from an interactive shell's job control, not from
    # `timeout`). Left alone, the hung read reaches the classifier as
    # "no diagnostic output", matches no transient pattern, and is
    # reported as unclassifiable - the uninformative message this
    # gate exists to remove, on the exact fault that motivated it.
    # Name it from the exit code, which is the only witness there is.
    # 137 covers a SIGKILL escalation should a --kill-after ever be
    # added; today only 124 can occur.
    if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
      if [ -n "$diagnostic" ]; then
        diagnostic="timed out after ${read_timeout}s (exit $rc); last output before the timeout: $diagnostic"
      else
        diagnostic="timed out after ${read_timeout}s with no response (exit $rc)"
      fi
    fi
    [ -z "$diagnostic" ] && diagnostic="no diagnostic output"
  fi

  # `gh issue view --json` reads through GraphQL, whose
  # not-found errors name the node they could not resolve: "Could
  # not resolve to an Issue with the number N" when the issue is
  # missing, but "Could not resolve to a Repository with the name
  # 'owner/repo'" when the token cannot see the repository at all.
  # Matching only the Issue form left the repository form matching
  # nothing here AND nothing in the credential branch below, so a
  # plain permission problem spent the whole retry budget and was
  # then reported as "the failures could not be classified" - the
  # uninformative verdict this gate exists to remove, on a fault
  # that is permanent by definition and worth zero retries.
  if printf '%s' "$diagnostic" | grep -qiE 'Could not resolve to an? .*(issue|repository)|HTTP 404'; then
    safe="$(sanitize "$diagnostic")"
    echo "::error::wing-commander-lifecycle-gate: could not determine state of issue #$ISSUE_NUMBER — the issue or the repository could not be resolved. It may not exist, or the token may lack access to it (issues: read on this repository). ($safe)"
    exit 1
  fi

  if printf '%s' "$diagnostic" | grep -qiE 'HTTP 401|Bad credentials|Resource not accessible by integration|requires authentication|insufficient .*scope|missing .*scope'; then
    safe="$(sanitize "$diagnostic")"
    echo "::error::wing-commander-lifecycle-gate: the token used to authenticate this request was rejected: $safe"
    exit 1
  fi

  if printf '%s' "$diagnostic" | grep -qiE 'HTTP 5[0-9]{2}|timed out|Could not connect|connection reset'; then
    last_class_phrase="the failures were a recognised transient class"
  else
    last_class_phrase="the failures could not be classified"
  fi
  last_diagnostic="$diagnostic"
  state=""

  safe="$(sanitize "$diagnostic")"
  echo "::warning::wing-commander-lifecycle-gate: attempt $attempt/$max_attempts to read state of issue #$ISSUE_NUMBER failed: $safe"

  if [ "$attempt" -lt "$max_attempts" ]; then
    sleep 1
  fi
done

if [ -z "$state" ]; then
  safe="$(sanitize "$last_diagnostic")"
  echo "::error::wing-commander-lifecycle-gate: could not determine state of issue #$ISSUE_NUMBER after $attempt retried attempts; $last_class_phrase. Last attempt reported: $safe"
  exit 1
fi

echo "state=$state" >> "$GITHUB_OUTPUT"

# `gh issue view --json` reads through GitHub's GraphQL API, which
# reports the state as OPEN/CLOSED — uppercase, unlike the REST
# API's open/closed. cleanup.yml's "Idempotency check" has always
# compared against CLOSED for exactly this reason. Match
# case-insensitively so a casing change upstream cannot brick the
# gate, and refuse to guess on anything else: an unrecognized value
# must fail loudly rather than fall through to "closed" and
# silently skip every downstream step, which is precisely how the
# original lowercase comparison made all five gated stages inert
# while still reporting success.
case "$(printf '%s' "$state" | tr '[:upper:]' '[:lower:]')" in
  open)
    echo "is-open=true" >> "$GITHUB_OUTPUT"
    ;;
  closed)
    echo "is-open=false" >> "$GITHUB_OUTPUT"
    ;;
  *)
    echo "::error::wing-commander-lifecycle-gate: unrecognized state '$state' for issue #$ISSUE_NUMBER — expected OPEN or CLOSED. Refusing to guess whether this lifecycle is open."
    exit 1
    ;;
esac
