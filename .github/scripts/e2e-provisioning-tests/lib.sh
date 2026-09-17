# Shared harness for exercising provision-e2e-target.sh and
# e2e-provisioning/checks.sh against a stubbed `gh`.
#
# Adapted from .github/scripts/auto-update-spec-kit-tests/lib.sh: a real
# Actions-shaped environment, a `gh` stub ahead of any real gh on PATH, and
# assertion helpers. This harness calls the shipped scripts directly (they
# are standalone entry points, not extracted `run:` blocks), so it carries
# none of that harness's extract.py/run_step machinery.

SP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SP" rev-parse --show-toplevel)"
PROVISION_SCRIPT="$REPO/.github/scripts/provision-e2e-target.sh"

wc_find_python() {
  local c
  for c in "${WC_PYTHON:-}" python3 python py; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys' >/dev/null 2>&1; then
      command -v "$c"; return 0
    fi
  done
  return 1
}
PY="$(wc_find_python)" || {
  echo "e2e-provisioning-tests: no working python3/python on PATH." >&2
  exit 2
}
export WC_PYTHON="$PY"
if ! command -v jq >/dev/null 2>&1; then
  echo "e2e-provisioning-tests: \`jq\` is required and was not found on PATH." >&2
  exit 2
fi

if [ -z "${WC_TEST_WORK:-}" ]; then
  WC_TEST_WORK="$(mktemp -d)"
  export WC_TEST_WORK
  trap 'rm -rf "$WC_TEST_WORK"' EXIT
fi
if [ ! -x "$WC_TEST_WORK/bin/gh" ]; then
  mkdir -p "$WC_TEST_WORK/bin"
  printf '#!/usr/bin/env bash\nexec %q %q "$@"\n' "$PY" "$SP/gh_stub.py" > "$WC_TEST_WORK/bin/gh"
  chmod +x "$WC_TEST_WORK/bin/gh"
fi
case ":$PATH:" in
  *":$WC_TEST_WORK/bin:"*) ;;
  *) PATH="$WC_TEST_WORK/bin:$PATH"; export PATH ;;
esac

PASS=0; FAIL=0; FAILED_NAMES=()

# new_gh_state -- a fresh $GH_STATE/$GH_CALLS pair for one scenario.
#
# WC_SOURCE_CONTAINER_IMAGE defaults to "" (set, not unset) -- "this
# repository pins no image" is itself a valid value (FR-017) -- so
# container_image_pin's check has a deterministic source of truth without
# every scenario needing to seed a second, fake "this repository" entry in
# $GH_STATE just to answer that one element. A scenario that cares about a
# real pinned value overrides the export after calling this.
new_gh_state() {
  WORK="$(mktemp -d)"
  export GH_STATE="$WORK/gh-state.json"
  export GH_CALLS="$WORK/gh-calls.log"; : > "$GH_CALLS"
  echo '{"repos": {}}' > "$GH_STATE"
  export GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-charlesguse/wing-commander}"
  export WC_SOURCE_CONTAINER_IMAGE=""
}

# gh_state_set OWNER/NAME KEY JSON_VALUE -- seed/mutate one repo's field.
gh_state_set() {
  local full="$1" key="$2" value="$3" tmp
  tmp="$(mktemp)"
  jq --arg full "$full" --arg key "$key" --argjson value "$value" \
    '.repos[$full] //= {} | .repos[$full][$key] = $value' "$GH_STATE" > "$tmp"
  mv "$tmp" "$GH_STATE"
}

# gh_state_get OWNER/NAME KEY -- read one repo's field back (raw).
gh_state_get() {
  jq -r --arg full "$1" --arg key "$2" '.repos[$full][$key]' "$GH_STATE"
}

WRAPPER_FILES_FOR_TESTS=(
  wing-commander-1-intake.yml wing-commander-2-clarify.yml wing-commander-3-plan.yml
  wing-commander-4-tasks.yml wing-commander-5-implement.yml wing-commander-6-finalize.yml
  wing-commander-7-cleanup.yml wing-commander-rebase.yml
)
SCRATCH_MARKER_FOR_TESTS="Wing Commander E2E scratch target — provisioned by provision-e2e-target.sh, do not use for real work"

# seed_fully_onboarded OWNER/NAME [with-app-installation(true|false, default true)]
# -- a repo state with every auto-release element already in place, so a
# test can start from "already onboarded" without driving the privileged
# actions that would normally produce it.
seed_fully_onboarded() {
  local full="$1" with_install="${2:-true}" tmp contents="{}" f
  for f in "${WRAPPER_FILES_FOR_TESTS[@]}"; do
    contents="$(jq --arg f ".github/workflows/$f" --arg v "content-for-$f" '.[$f] = $v' <<<"$contents")"
  done
  tmp="$(mktemp)"
  jq --arg full "$full" --arg desc "$SCRATCH_MARKER_FOR_TESTS" --argjson install "$with_install" --argjson contents "$contents" \
    '.repos[$full] = {exists: true, description: $desc, diskUsage: 100, defaultBranch: "main",
      secrets: ["CLAUDE_CODE_OAUTH_TOKEN"], labels: ["spec-request"],
      variables: {"WING_COMMANDER_CONTAINER_IMAGE": ""}, contents: $contents, installation: $install}' \
    "$GH_STATE" > "$tmp"
  mv "$tmp" "$GH_STATE"
}

check() { # check <label> <actual> <expected>
  if [ "$2" = "$3" ]; then
    PASS=$((PASS+1)); printf '    ok   %s = %s\n' "$1" "$2"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES+=("$1"); printf '    FAIL %s: expected %s, got %s\n' "$1" "$3" "$2"
  fi
}
check_contains() { # check_contains <label> <haystack> <needle>
  if printf '%s' "$2" | grep -qF -- "$3"; then
    PASS=$((PASS+1)); printf '    ok   %s contains %s\n' "$1" "$3"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES+=("$1"); printf '    FAIL %s: expected to contain %s\n      got: %s\n' "$1" "$3" "$2"
  fi
}
check_not_contains() { # check_not_contains <label> <haystack> <needle>
  if printf '%s' "$2" | grep -qF -- "$3"; then
    FAIL=$((FAIL+1)); FAILED_NAMES+=("$1"); printf '    FAIL %s: expected NOT to contain %s\n      got: %s\n' "$1" "$3" "$2"
  else
    PASS=$((PASS+1)); printf '    ok   %s does not contain %s\n' "$1" "$3"
  fi
}

report() {
  echo
  echo "==================== $1 ===================="
  echo "passed: $PASS   failed: $FAIL"
  if [ "$FAIL" -gt 0 ]; then
    printf '  failing: %s\n' "${FAILED_NAMES[@]}"
    return 1
  fi
  return 0
}
