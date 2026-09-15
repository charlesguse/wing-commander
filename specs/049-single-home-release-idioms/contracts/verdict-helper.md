# Contract: FR-008, FR-009 — the fail-infra verdict has one shape

`research.md` D3 explains why this is a plain script, not a composite, and
why it sits outside FR-022's three-composite requirement (it is
single-workflow shared logic, not cross-workflow). `data-model.md`'s
"Internal helper... fail-infra verdict" table gives the field shape.

## `.github/actions/_shared/auto-release-verdict.sh` (NEW)

Positional/env args: `outcome`, `head`, `failing_check`, `expected`,
`observed`, `evidence_url`. Prints one line of JSON to stdout:
```
{outcome:$outcome, verified_head:$head,
 failing_check: (if $failing_check == "" then null else $failing_check end),
 expected: (if $expected == "" then null else $expected end),
 observed: (if $observed == "" then null else $observed end),
 evidence_url:$evidence_url}
```
— i.e. the exact `jq -n` program `write_verdict` (today's `poll` step,
`auto-release.yml:497-506`) already runs, extracted verbatim into a
standalone, `bash`-invoked script (matching the `_shared/count-turns.sh`
invocation idiom: `bash .github/actions/_shared/auto-release-verdict.sh
... `, never sourced, never relying on its executable bit).

## Call sites (15, all in `auto-release.yml`)

Every site listed in `data-model.md`'s internal-helper table keeps its own
`GITHUB_OUTPUT` heredoc framing
(`echo 'verdict<<AUTO_RELEASE_VERDICT_EOF'` / `echo
'AUTO_RELEASE_VERDICT_EOF'`) and its own arguments (each site's
`failing_check`/`expected`/`observed`/`evidence_url` text is unchanged —
this is a refactor of *construction*, not of *content*, per the spec's
"behaviour-preserving by default" assumption); only the `jq -n '{...}'`
invocation is replaced by
`bash .github/actions/_shared/auto-release-verdict.sh "$OUTCOME" "$HEAD_SHA" "$FAILING_CHECK" "$EXPECTED" "$OBSERVED" "$EVIDENCE_URL"`.
The `poll` step's own `write_verdict`/`emit_verdict` bash functions are
replaced the same way, and `emit_verdict`'s framing (the only site that
already separates "build" from "emit" into two named functions) becomes
the model every other site's framing already resembles once its `jq -n`
line moves out.

## Byte-identity test (FR-009)

A test captures each of the 15 sites' current literal inputs (extracted
once, before the refactor lands, from the current `jq -n` arguments at
each site) and asserts the new script's stdout for those same inputs is
byte-identical to what the old inline `jq -n` produced for them today.
This lives alongside Gate 60's self-test (contracts/single-home-gate.md)
since both need the same "run the shipped script for real" harness
(`wc_shell_harness.run_step()`, the pattern `verify-metrics-summary-record-emission.py`
already uses).

## Gate coverage

Gate 60 fails on any `jq` program, anywhere under `.github/workflows/` or
`.github/actions/` outside this script's own file, whose text contains all
six field names (`outcome`, `verified_head`, `failing_check`, `expected`,
`observed`, `evidence_url`) together.
