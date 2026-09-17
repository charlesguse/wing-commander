#!/usr/bin/env bash
# One deterministic check function per OnboardingElement (data-model.md),
# plus assemble_report(), which both provision-e2e-target.sh (privileged,
# local) and the generalized auto-update-spec-kit-scratch-preflight.yml
# (read-only, CI) source and call — the single home FR-008/FR-010 require.
#
# Every check function takes (owner, name) and returns 0 for ready, 1 for
# not-ready. Every check makes only read calls (FR-009: never inspects a
# secret's value, only its presence).
set -uo pipefail

SCRATCH_MARKER="Wing Commander E2E scratch target — provisioned by provision-e2e-target.sh, do not use for real work"

WRAPPER_FILES=(
  wing-commander-1-intake.yml
  wing-commander-2-clarify.yml
  wing-commander-3-plan.yml
  wing-commander-4-tasks.yml
  wing-commander-5-implement.yml
  wing-commander-6-finalize.yml
  wing-commander-7-cleanup.yml
  wing-commander-rebase.yml
)

# ---- repository -------------------------------------------------------
check_repository() { # check_repository OWNER NAME
  gh repo view "$1/$2" >/dev/null 2>&1
}
remaining_action_repository() {
  printf 'Repository %s/%s does not exist yet. Run provision-e2e-target.sh --repo %s/%s --profile <profile> (without --check-only) to create it.' "$1" "$2" "$1" "$2"
}

# ---- app_installation (the one DeclaredManualStep, remedy: manual) -----
check_app_installation() { # check_app_installation OWNER NAME
  gh api "repos/$1/$2/installation" >/dev/null 2>&1
}
remaining_action_app_installation() {
  printf 'Install the wing-commander App on %s/%s: https://github.com/settings/installations' "$1" "$2"
}

# ---- scratch_marker (research.md D3) -----------------------------------
# ready iff the repository does not exist yet (nothing to conflict with),
# has zero commits (diskUsage == 0), or its description already carries the
# marker this script writes on first successful provisioning. Any other
# pre-existing, non-empty, unmarked repository is not ready — and this is
# the check provision-e2e-target.sh refuses on, before any privileged
# action, per FR-007/data-model.md D3.
check_scratch_marker() { # check_scratch_marker OWNER NAME
  local owner="$1" name="$2" json disk desc
  if ! gh repo view "$owner/$name" >/dev/null 2>&1; then
    return 0
  fi
  json="$(gh repo view "$owner/$name" --json description,diskUsage 2>/dev/null)" || return 1
  disk="$(jq -r '.diskUsage // 0' <<<"$json")"
  [ "$disk" = "0" ] && return 0
  desc="$(jq -r '.description // ""' <<<"$json")"
  [ "$desc" = "$SCRATCH_MARKER" ]
}
remaining_action_scratch_marker() {
  local owner="$1" name="$2" desc
  desc="$(gh repo view "$owner/$name" --json description -q .description 2>/dev/null)"
  printf '%s/%s already has commits and its description does not carry the scratch marker, so it cannot be established as a reusable scratch verification target. Found description: %s' "$owner" "$name" "${desc:-<none>}"
}

# ---- claude_credential (auto-release only) -----------------------------
check_claude_credential() { # check_claude_credential OWNER NAME
  gh secret list --repo "$1/$2" 2>/dev/null | awk '{print $1}' | grep -qE '^(CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY)$'
}
remaining_action_claude_credential() {
  printf 'Export CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY in this shell, then re-run provision-e2e-target.sh --repo %s/%s --profile auto-release to write it to %s/%s as a repository secret.' "$1" "$2" "$1" "$2"
}

# ---- spec_request_label (auto-release only) ----------------------------
check_spec_request_label() { # check_spec_request_label OWNER NAME
  gh label view spec-request --repo "$1/$2" >/dev/null 2>&1
}
remaining_action_spec_request_label() {
  printf 'Run provision-e2e-target.sh --repo %s/%s --profile auto-release (without --check-only) to create the spec-request label on %s/%s.' "$1" "$2" "$1" "$2"
}

# ---- wrapper_set (auto-release only) -----------------------------------
check_wrapper_set() { # check_wrapper_set OWNER NAME
  local owner="$1" name="$2" f
  for f in "${WRAPPER_FILES[@]}"; do
    gh api "repos/$owner/$name/contents/.github/workflows/$f" >/dev/null 2>&1 || return 1
  done
  return 0
}
remaining_action_wrapper_set() {
  printf 'Run provision-e2e-target.sh --repo %s/%s --profile auto-release (without --check-only) to push the eight wing-commander-*.yml wrapper workflows to %s/%s'\''s default branch.' "$1" "$2" "$1" "$2"
}

# ---- container_image_pin (auto-release only) ---------------------------
# "This repository's own pinned value" is read once (research.md D4) so the
# two cannot drift into a second literal. `WC_SOURCE_CONTAINER_IMAGE`, when
# SET (even to an empty string -- FR-017: no pinned image is itself a valid
# pinned value), is trusted as that value -- the generalized readiness-check
# workflow sets it directly from `vars.WING_COMMANDER_CONTAINER_IMAGE`,
# because the token it hands checks.sh is scoped only to the target and
# cannot read this repository's own variables back via the API. Unset
# (the local, maintainer-run path), it is derived live from this checkout's
# own repository.
this_repo_container_image() {
  if [ -n "${WC_SOURCE_CONTAINER_IMAGE+set}" ]; then
    printf '%s' "$WC_SOURCE_CONTAINER_IMAGE"
    return 0
  fi
  local self
  self="${GITHUB_REPOSITORY:-}"
  if [ -z "$self" ]; then
    self="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" || return 1
  fi
  gh variable list --repo "$self" --json name,value -q '.[] | select(.name=="WING_COMMANDER_CONTAINER_IMAGE") | .value' 2>/dev/null
}
check_container_image_pin() { # check_container_image_pin OWNER NAME
  local owner="$1" name="$2" want got
  want="$(this_repo_container_image)" || return 1
  got="$(gh variable list --repo "$owner/$name" --json name,value -q '.[] | select(.name=="WING_COMMANDER_CONTAINER_IMAGE") | .value' 2>/dev/null)"
  [ "$got" = "$want" ]
}
remaining_action_container_image_pin() {
  printf 'Run provision-e2e-target.sh --repo %s/%s --profile auto-release (without --check-only) to set WING_COMMANDER_CONTAINER_IMAGE on %s/%s to match this repository'\''s own pinned value.' "$1" "$2" "$1" "$2"
}

# ---- ReadinessReport assembly (data-model.md, contracts/readiness-report.schema.json) --
assemble_report() { # assemble_report OWNER NAME PROFILE
  local owner="$1" name="$2" profile="$3" key ready action entry
  local elements_json="[]" all_ready=true
  while IFS= read -r key; do
    [ -n "$key" ] || continue
    if "check_$key" "$owner" "$name"; then
      ready=true; action=""
    else
      ready=false; all_ready=false
      action="$("remaining_action_$key" "$owner" "$name")"
    fi
    entry="$(jq -n --arg key "$key" --argjson ready "$ready" --arg action "$action" \
      '{key: $key, ready: $ready, remaining_action: (if $ready then null else $action end)}')"
    elements_json="$(jq --argjson e "$entry" '. + [$e]' <<<"$elements_json")"
  done < <(profile_elements "$profile") || return 1
  jq -n --arg target "$owner/$name" --arg profile "$profile" --argjson elements "$elements_json" \
    --argjson ready "$all_ready" --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{target: $target, profile: $profile, elements: $elements, ready: $ready, generated_at: $generated_at}'
}
