#!/usr/bin/env bash
# PreToolUse reminder: the constitution is amended by /speckit-constitution.
#
# WHY THIS EXISTS
# ---------------
# Nothing can verify that a skill was RUN. The skill leaves no artifact
# behind to check, so "was the process followed" is not a question any
# check can answer. What CAN be observed is the moment the change is about
# to happen, and that is all this hook does: it fires when an agent reaches
# for Edit/Write on the constitution and says what the skill would have
# done for it.
#
# Deliberately advisory. It emits a reminder and exits 0; it never denies
# the tool call. A hard block would be the wrong instrument for something
# scoped this narrowly -- this hook binds only Claude Code sessions in this
# checkout, so it cannot bind an edit made through the GitHub web UI, a
# fresh clone, or another agent. Stopping the honest path while the other
# ones stay open buys friction, not coverage.
#
# The real miss it is aimed at: the README numbered principle list lost
# principle VI at 1.2.0 and nobody noticed until the 1.4.0 amendment, two
# minor versions later. That propagation audit is the skill step 4 that a
# hand-edit skips.
#
# Fails open by construction. Absent jq, malformed stdin, or no file_path
# at all, every path lands on the default case and exits 0 silently: a
# broken reminder must not become a broken Edit tool.
set -uo pipefail

# Built from its character code so that no literal backslash appears in
# this file. Quoted heredocs in this sandbox eat one level of escaping, and
# a mangled separator here would silently match nothing -- which is exactly
# the failure this hook cannot report, since saying nothing is also what it
# does when it correctly decides not to fire.
bs="$(awk 'BEGIN { printf "%c", 92 }')"

raw="$(jq -r '.tool_input.file_path // ""' 2>/dev/null || true)"

# The separator is DOUBLED for tr, which reads a two-character run as one
# literal backslash. A lone one makes GNU tr warn "unescaped backslash at
# end of string is not portable" on stderr -- once per Edit and once per
# Write, for the whole session. Measured, not guessed. Do not simplify.
path="$(printf '%s' "$raw" | tr "$bs$bs" '/')"

case "$path" in
  */.specify/memory/constitution.md|.specify/memory/constitution.md) ;;
  *) exit 0 ;;
esac

reminder="REMINDER: .specify/memory/constitution.md is amended through the /speckit-constitution skill, not by hand. The skill picks the semver bump, prepends a Sync Impact Report, and runs the propagation audit over .specify/templates/, the README numbered principle list, and docs/. A hand-edit reliably misses one of those: the README list lost principle VI at 1.2.0 and it went unnoticed for two minor versions. Prefer running /speckit-constitution and applying its output. This is advice, not a gate -- proceeding is allowed."

jq -n --arg r "$reminder" '{
  systemMessage: $r,
  hookSpecificOutput: { hookEventName: "PreToolUse", additionalContext: $r }
}'
exit 0
