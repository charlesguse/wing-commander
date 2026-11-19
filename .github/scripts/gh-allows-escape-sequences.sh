#!/usr/bin/env bash
# gh-allows-escape-sequences.sh -- exit 0 when this runner's `gh api` takes
# `--allow-escape-sequences`, 1 when it does not.
#
# Why: a newer gh refuses to output a raw (non-JSON) response body that
# contains terminal escape sequences unless `--allow-escape-sequences` is
# passed. The check is on the content, not on the terminal: `gh api ... >
# file` is refused the same way (gh 2.100.0, pkg/cmd/api/api.go ->
# iostreams.CopyGuardedContent; only `--silent` skips it). gh then exits 1,
# writes nothing, and prints a message with no `HTTP <code>` in it. A job log
# carries ANSI colour codes, so every read of one fails there. An older gh
# has no such flag and rejects it as unknown, so a job-log read passes the
# flag only when this gh's own `gh api --help` lists it.
#
# Usage, at each job-log read (the call itself stays literal in the caller's
# step, where Gate 12 resolves its token and can see every flag):
#   esc=0; bash <pipeline checkout>/.github/scripts/gh-allows-escape-sequences.sh && esc=1
#   if [ "$esc" = 1 ]; then gh api ".../actions/jobs/$id/logs" --allow-escape-sequences > f
#   else gh api ".../actions/jobs/$id/logs" > f; fi
#
# The one home of that probe (CLAUDE.md "Shared logic has exactly one
# home"): agent-startup-check.yml's classify step and the
# wing-commander-fetch-job-logs composite both call it, and Gate 60
# (verify-single-home-idioms.py, check `gh-escape-probe`) fails on a copy of
# the probe anywhere else under .github/, and on a job-log read that is not
# paired with this script. It lives in .github/scripts, not
# .github/actions/_shared, because a published workflow may not reach into
# _shared (Gate 60's promotion check) and the classify step's pipeline
# checkout already carries .github/scripts. `gh api --help` makes no request
# and needs no token.
#
# Never errors out: a missing gh, or one whose help cannot be read, exits 1,
# so the caller's read runs without the flag, as it did before this script.
gh api --help 2>/dev/null | grep -q -e '--allow-escape-sequences'
