#!/usr/bin/env bash
# Single home for the GitHub App JWT sign + installation-token mint this
# feature adds (specs/071-agent-push-credential, research.md D2/D3/D6).
# Never referenced from outside this composite's own directory -- Gate 99
# check 3 depends on that, and no second copy of this JWT-construction
# shape may exist anywhere else in this repository.
#
# Invoked by git itself, via the `!bash <this path>` credential.helper
# wing-commander-agent-push-credential/action.yml installs, with `get` on
# stdin (protocol/host lines this script never needs to read: the target
# is always github.com and is fixed by WC_AGENT_PUSH_OWNER/WC_AGENT_PUSH_REPO,
# not by whatever git passes on stdin). Never invoked directly by any
# workflow step.
#
# On success: stdout is exactly "username=x-access-token\npassword=<token>\n",
# exit 0. On failure: stdout empty, stderr's first line exactly
# "wing-commander-agent-push-credential: mint failed: <reason>", exit 1.
# Never retries internally -- retry policy for the agent's own next push
# attempt is prompt guidance (research.md D7), not this script's job.
set -u
set -o pipefail

fail() {
  echo "wing-commander-agent-push-credential: mint failed: $1" >&2
  exit 1
}

b64url() {
  base64 | tr '+/' '-_' | tr -d '=\n'
}

key_path="${WC_AGENT_PUSH_KEY_PATH:-}"
app_id="${WC_AGENT_PUSH_APP_ID:-}"
owner="${WC_AGENT_PUSH_OWNER:-}"
repo="${WC_AGENT_PUSH_REPO:-}"

if [ -z "$key_path" ] || [ ! -r "$key_path" ]; then
  fail "key-unreadable"
fi

now="$(date +%s)"
iat=$((now - 60))
exp=$((now + 540))

header='{"alg":"RS256","typ":"JWT"}'
payload="$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$iat" "$exp" "$app_id")"

header_b64="$(printf '%s' "$header" | b64url)"
payload_b64="$(printf '%s' "$payload" | b64url)"
signing_input="${header_b64}.${payload_b64}"

signature_b64="$(printf '%s' "$signing_input" | openssl dgst -sha256 -sign "$key_path" 2>/dev/null | b64url)"
if [ -z "$signature_b64" ]; then
  fail "key-unreadable"
fi

jwt="${signing_input}.${signature_b64}"

cache_path="${RUNNER_TEMP:-/tmp}/wc-agent-push-installation-id"

if [ -s "$cache_path" ]; then
  installation_id="$(cat "$cache_path")"
else
  install_response="$(curl -sS -w '\n%{http_code}' \
    -H "Authorization: Bearer $jwt" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${owner}/${repo}/installation")" || fail "installation-lookup-failed"
  install_status="${install_response##*$'\n'}"
  install_body="${install_response%$'\n'*}"
  case "$install_status" in
    2??) ;;
    *) fail "installation-lookup-failed" ;;
  esac
  installation_id="$(printf '%s' "$install_body" | jq -r '.id // empty')"
  if [ -z "$installation_id" ]; then
    fail "installation-lookup-failed"
  fi
  printf '%s' "$installation_id" > "$cache_path"
fi

token_response="$(curl -sS -w '\n%{http_code}' -X POST \
  -H "Authorization: Bearer $jwt" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/app/installations/${installation_id}/access_tokens")" || fail "token-mint-failed"
token_status="${token_response##*$'\n'}"
token_body="${token_response%$'\n'*}"
case "$token_status" in
  2??) ;;
  *) fail "token-mint-failed" ;;
esac

token="$(printf '%s' "$token_body" | jq -r '.token // empty')"
if [ -z "$token" ]; then
  fail "token-mint-failed"
fi

printf 'username=x-access-token\npassword=%s\n' "$token"
