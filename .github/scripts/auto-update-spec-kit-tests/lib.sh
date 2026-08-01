# Shared harness for exercising auto-update-spec-kit's extracted run: steps.
#
# Gives each step a real Actions step environment ($GITHUB_OUTPUT,
# $GITHUB_STEP_SUMMARY, $RUNNER_TEMP), puts a `gh` stub ahead of any real gh on
# PATH, and provides assertion helpers. Sourced by every tN_*.sh suite; each
# suite is also runnable on its own.

export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8 2>/dev/null || true

SP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SP" rev-parse --show-toplevel)"
# Pick an interpreter that actually RUNS. `command -v python3` succeeds on
# Windows even when it resolves to the Microsoft Store stub, which then exits
# non-zero on every invocation.
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
  echo "auto-update-spec-kit-tests: no working python3/python on PATH." >&2
  exit 2
}
export WC_PYTHON="$PY"
if ! "$PY" -c 'import yaml' >/dev/null 2>&1; then
  echo "auto-update-spec-kit-tests: PyYAML is required ($PY -m pip install pyyaml)." >&2
  exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
  cat >&2 <<'MSG'
auto-update-spec-kit-tests: `jq` is required and was not found on PATH.
  ubuntu/macOS: apt-get install jq  /  brew install jq
  Windows (Git Bash): curl -sSL -o /usr/bin/jq.exe \
    https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-windows-amd64.exe
MSG
  exit 2
fi

# ---- one-time setup: extract the shipped run: blocks, install the gh stub ---
if [ -z "${WC_TEST_WORK:-}" ]; then
  WC_TEST_WORK="$(mktemp -d)"
  export WC_TEST_WORK
  trap 'rm -rf "$WC_TEST_WORK"' EXIT
fi
export STEPS="$WC_TEST_WORK/steps"
if [ ! -d "$STEPS" ]; then
  "$PY" "$SP/extract.py" "$REPO" "$STEPS" >/dev/null || exit 2
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

# ---- Actions step environment ---------------------------------------------
new_step_env() {
  WORK="$(mktemp -d)"
  export RUNNER_TEMP="$WORK/runner-temp"; mkdir -p "$RUNNER_TEMP"
  export GITHUB_OUTPUT="$WORK/github_output"; : > "$GITHUB_OUTPUT"
  export GITHUB_STEP_SUMMARY="$WORK/step_summary"; : > "$GITHUB_STEP_SUMMARY"
  export GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-charlesguse/wing-commander}"
  export GH_STATE="$WORK/gh-state.json"
  export GH_CALLS="$WORK/gh-calls.log"; : > "$GH_CALLS"
  echo '{}' > "$GH_STATE"
}

# Read a step output the way the runner does (handles the <<HEREDOC form).
out() { "$PY" "$SP/read_output.py" "$GITHUB_OUTPUT" "$1"; }
summary() { cat "$GITHUB_STEP_SUMMARY"; }

# ---- assertions ------------------------------------------------------------
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

# Run an extracted step, rendering ${{ ... }} from the GHA_SUBST array
# (NAME=VALUE pairs). Anything not listed renders empty, matching what Actions
# does for a skipped job's outputs.
run_step() { # run_step <step-file-glob>
  local f
  f="$(ls "$STEPS"/$1 2>/dev/null | head -1)"
  if [ -z "$f" ]; then
    echo "    FAIL: no extracted step matching $1"; FAIL=$((FAIL+1)); return 1
  fi
  cp "$f" "$WORK/step.sh"
  "$PY" "$SP/subst.py" "$WORK/step.sh" "${GHA_SUBST[@]}"
  bash "$WORK/step.sh"
}
