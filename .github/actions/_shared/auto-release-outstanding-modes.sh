#!/usr/bin/env bash
# Which execution modes an open auto-release:failed issue is still waiting
# on (#966) -- the one reader of the issue's record, called by
# auto-release.yml's detect ("Decide whether this run verifies"), whose
# output report's close decision consumes. Gates 52 and 64 run it against
# the bodies report's own write_failure_body and pass note actually write,
# so the writer and this reader cannot drift apart unnoticed.
#
# Input (stdin): a JSON array of strings, oldest first -- the issue body,
# then every comment the auto-release bot (github-actions[bot]) posted on
# it. Comments by anyone else are filtered out by the caller, never read
# here: only the bot's own entries are evidence.
#
# Each entry is one of:
#   - a failure report: the issue body (always), or a bot comment carrying
#     a `**Classification**:` line (report's write_failure_body, the
#     collision body, the release-failure body -- the composite comments a
#     later failure onto the open issue rather than filing a second one).
#     Its mode is the first word of its `**Mode**:` line when that word is
#     `container` or `default-runner`; anything else (no Mode line, an
#     `unknown (...)` or `not mode-specific (...)` value) is `unrecorded`.
#   - a pass note: a bot comment carrying a `**Passed mode**:` line, which
#     report posts when a success clears part of the record but not all of
#     it. Its first word is `container`, `default-runner` or `none` (a
#     success that verified nothing: the quiet day whose latest tag already
#     points at HEAD).
#   - anything else (report's own closing comment, a stray bot comment):
#     ignored.
#
# The rule: a mode's failure stays outstanding until a later pass note in
# that same mode; an unrecorded failure stays outstanding until any later
# pass note (any success disproves a failure no single mode owns). The
# issue may close only when nothing is outstanding after this run's own
# success is applied -- report applies that last step itself.
#
# Output (stdout): the outstanding set, space-separated, sorted, drawn from
# `container default-runner unrecorded` -- empty when nothing is
# outstanding. Exits non-zero (and prints nothing) on input that is not a
# JSON array of strings, so the caller can treat the record as unreadable.
#
# Invoke as `bash .github/actions/_shared/auto-release-outstanding-modes.sh
# < entries.json`, from the workspace root (see auto-release-verdict.sh for
# why auto-release.yml resolves _shared paths repo-relative).
set -euo pipefail

jq -er '
  def lines: gsub("\r"; "") | split("\n");
  def first_word($prefix):
    [lines[] | select(startswith($prefix)) | ltrimstr($prefix) | split(" ")[0]] | first;
  def failure_mode:
    (first_word("**Mode**: ") // "") as $m
    | if $m == "container" or $m == "default-runner" then $m else "unrecorded" end;
  def is_failure_report: [lines[] | select(startswith("**Classification**: "))] | length > 0;

  if type != "array" or (map(type == "string") | all | not) then error("not an array of strings") else . end
  | to_entries
  | reduce .[] as $e ({};
      ($e.value | first_word("**Passed mode**: ")) as $passed
      | if $e.key > 0 and $passed != null then
          del(.unrecorded)
          | if $passed == "container" or $passed == "default-runner" then del(.[$passed]) else . end
        elif $e.key == 0 or ($e.value | is_failure_report) then
          .[$e.value | failure_mode] = true
        else . end)
  | keys | join(" ")
'
