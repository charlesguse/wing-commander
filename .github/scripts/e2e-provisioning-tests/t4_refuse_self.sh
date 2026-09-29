#!/usr/bin/env bash
# FR-007 / quickstart step 6's first command: refuse to target this
# repository itself, and refuse a malformed --repo shape, before any gh
# call is made.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# Mirrors provision-e2e-target.sh's own this_repo_from_git(): derives
# OWNER/NAME from this checkout's own git remote, stripping any embedded
# credential, so this test does not need to hardcode a repository name that
# would be wrong for a fork.
this_repo() {
  local url rest
  url="$(git -C "$REPO" config --get remote.origin.url 2>/dev/null)" || return 1
  case "$url" in
    *github.com[:/]*) rest="${url#*github.com[:/]}" ;;
    *) return 1 ;;
  esac
  rest="${rest%.git}"; rest="${rest%/}"
  [ -n "$rest" ] && printf '%s' "$rest"
}

echo "--- Scenario 4: refuse to target this repository (FR-007) ---"
new_gh_state
SELF="$(this_repo)"
if [ -z "$SELF" ]; then
  echo "t4_refuse_self: could not resolve this repository from git remote -- skipping this suite" >&2
  echo "passed: 0   failed: 0"
  exit 0
fi
OUT="$(bash "$PROVISION_SCRIPT" --repo "$SELF" --profile auto-release 2>&1)"
check "T4 self-target exits non-zero" "$?" "1"
check_contains "T4 self-target names the reason" "$OUT" "FR-007"
check "T4 self-target makes zero gh calls" "$(wc -l < "$GH_CALLS" | tr -d ' ')" "0"

echo "--- FR-014 (research.md D7): GITHUB_REPOSITORY alone resolves a self-target refusal, distinct from the unresolved case (T045) ---"
new_gh_state
REAL_GIT="$(command -v git)"
FAKEGIT_DIR="$(mktemp -d)"
cat > "$FAKEGIT_DIR/git" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do
  if [ "\$a" = "remote.origin.url" ]; then
    exit 1
  fi
done
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$FAKEGIT_DIR/git"
export GITHUB_REPOSITORY="wc-user/wc-e2e-self-via-env"
OUT="$(PATH="$FAKEGIT_DIR:$PATH" bash "$PROVISION_SCRIPT" --repo wc-user/wc-e2e-self-via-env --profile spec-kit-scratch 2>&1)"
RC=$?
check "T4 GITHUB_REPOSITORY self-target exits non-zero" "$RC" "1"
check_contains "T4 GITHUB_REPOSITORY self-target names FR-007, not the unresolved-self message" "$OUT" "FR-007"
check_not_contains "T4 GITHUB_REPOSITORY self-target is distinct from the unresolved case (T045)" \
  "$OUT" "could not determine this repository"
check "T4 GITHUB_REPOSITORY self-target makes zero gh calls" "$(wc -l < "$GH_CALLS" | tr -d ' ')" "0"
unset GITHUB_REPOSITORY
rm -rf "$FAKEGIT_DIR"

echo "--- malformed --repo shapes are refused before any gh call ---"
for bad in "not-a-pair" "too/many/slashes" "/leading-slash" "trailing-slash/"; do
  new_gh_state
  OUT="$(bash "$PROVISION_SCRIPT" --repo "$bad" --profile auto-release 2>&1)"
  check "T4 malformed '$bad' exits non-zero" "$?" "1"
  check "T4 malformed '$bad' makes zero gh calls" "$(wc -l < "$GH_CALLS" | tr -d ' ')" "0"
done

echo "--- unrecognized flags and an out-of-range --profile are also refused, with no interactive prompt ---"
new_gh_state
printf '' | bash "$PROVISION_SCRIPT" --repo wc-user/x --profile bogus-profile >/dev/null 2>&1
check "T4 out-of-range --profile exits non-zero" "$?" "1"
new_gh_state
printf '' | bash "$PROVISION_SCRIPT" --repo wc-user/x --profile auto-release --unknown-flag >/dev/null 2>&1
check "T4 unrecognized flag exits non-zero" "$?" "1"

report "T4 refuse self"
