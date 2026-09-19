# Pre-refactor verdict-construction fixtures (T002)

Captured before T022/T023 replace each site's inline `jq -n '{...}'` with a
call to `.github/actions/_shared/auto-release-verdict.sh` (T004). This is
the "before" half of the diff T024 runs against the shipped script — each
site's exact `jq -n` program, one representative set of literal input
values, and that program's byte-for-byte JSON output for those inputs.

**Correction to tasks.md's count**: tasks.md/research.md D3 describe "14
verdict-construction call sites." Re-deriving the count directly from
`auto-release.yml` (`grep -n "jq -n"`) finds **15** distinct `jq -n`
invocations building this shape: `config`×3, `reachable`×2, `reset`×2,
`speckit-version`×1, `scaffold`×3, `kickoff`×2, `poll`'s `write_verdict`
function×1, `report`'s defensive fallback×1 (3+2+2+1+3+2+1+1=15). This
matches T023's own "the remaining 10 hand-built `jq -n` verdict sites"
(config 3 + speckit-version 1 + scaffold 3 + kickoff 2 + report 1 = 10)
once `reachable`/`reset` (4, migrated in User Story 1) and `poll` (1,
migrated by T022) are subtracted: 10 + 4 + 1 = 15. The "14" in
tasks.md/research.md is off by one; this fixture file captures all 15
real sites, per T001's rule of recording baseline facts from the tree,
not from a claim about it.

All fixtures below share `HEAD_SHA=abc123` unless noted.

## 1. `config` — `WING_COMMANDER_AUTO_RELEASE_E2E_REPO` is unset (line 119-120)

```
jq -n --arg head "$HEAD_SHA" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"WING_COMMANDER_AUTO_RELEASE_E2E_REPO is unset", expected:"a repository variable set to OWNER/NAME of a pre-onboarded test repository", observed:"unset", evidence_url:"WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}'
```
Inputs: `HEAD_SHA=abc123`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"WING_COMMANDER_AUTO_RELEASE_E2E_REPO is unset","expected":"a repository variable set to OWNER/NAME of a pre-onboarded test repository","observed":"unset","evidence_url":"WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}
```

## 2. `config` — E2E_REPO shape bad (line 135-136)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"WING_COMMANDER_AUTO_RELEASE_E2E_REPO shape", expected:"OWNER/NAME", observed:$repo, evidence_url:"WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=badvalue`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"WING_COMMANDER_AUTO_RELEASE_E2E_REPO shape","expected":"OWNER/NAME","observed":"badvalue","evidence_url":"WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}
```

## 3. `config` — E2E_REPO names this repository (line 154-155)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"WING_COMMANDER_AUTO_RELEASE_E2E_REPO names this repository", expected:"a separate, dedicated, pre-onboarded test repository", observed:$repo, evidence_url:"WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"WING_COMMANDER_AUTO_RELEASE_E2E_REPO names this repository","expected":"a separate, dedicated, pre-onboarded test repository","observed":"owner/repo","evidence_url":"WING_COMMANDER_AUTO_RELEASE_E2E_REPO"}
```

## 4. `reachable` — token mint failed (line 197-198)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"wing-commander App installation on the test repository", expected:"installed on the test repository with Contents/Issues/Pull requests read-write", observed:"token mint failed", evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"wing-commander App installation on the test repository","expected":"installed on the test repository with Contents/Issues/Pull requests read-write","observed":"token mint failed","evidence_url":"owner/repo"}
```

## 5. `reachable` — unreachable / no default branch (line 209-210)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"test repository reachability", expected:"gh repo view succeeds and reports a default branch", observed:"unreachable, or has no default branch", evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"test repository reachability","expected":"gh repo view succeeds and reports a default branch","observed":"unreachable, or has no default branch","evidence_url":"owner/repo"}
```

## 6. `reset` — clone failed (line 256-257)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" --arg detail "$(tail -c 500 "$RUNNER_TEMP/auto-release-clone-err.txt")" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"cloning the test repository", expected:"a clone over the scoped App token succeeds", observed:$detail, evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`, `detail=fatal: could not read Username`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"cloning the test repository","expected":"a clone over the scoped App token succeeds","observed":"fatal: could not read Username","evidence_url":"owner/repo"}
```

## 7. `reset` — push failed (line 287-288)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" --arg detail "$(tail -c 500 "$RUNNER_TEMP/auto-release-push-err.txt")" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"resetting the test repository default branch", expected:"a force-push of the reset branch succeeds", observed:$detail, evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`, `detail=! [remote rejected]`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"resetting the test repository default branch","expected":"a force-push of the reset branch succeeds","observed":"! [remote rejected]","evidence_url":"owner/repo"}
```

## 8. `speckit-version` — no SPECKIT_SUPPORTED_VERSION line (line 321-322)

```
jq -n --arg head "$HEAD_SHA" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"resolving SPECKIT_SUPPORTED_VERSION", expected:"a SPECKIT_SUPPORTED_VERSION line in .github/actions/wing-commander-preflight/action.yml at the verified head", observed:"no such line matched", evidence_url:$head}'
```
Inputs: `HEAD_SHA=abc123` (note: `evidence_url` is `$head`, not `$repo`, at this site only)

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"resolving SPECKIT_SUPPORTED_VERSION","expected":"a SPECKIT_SUPPORTED_VERSION line in .github/actions/wing-commander-preflight/action.yml at the verified head","observed":"no such line matched","evidence_url":"abc123"}
```

## 9. `scaffold` — uvx not found (line 365-366)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"scaffolding the test repository", expected:"uvx available on the runner", observed:"uvx not found", evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"scaffolding the test repository","expected":"uvx available on the runner","observed":"uvx not found","evidence_url":"owner/repo"}
```

## 10. `scaffold` — specify init failed (line 378-379)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" --arg detail "$(tail -c 500 "$RUNNER_TEMP/auto-release-scaffold-install.log")" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"specify init in the test repository", expected:"specify init exits 0", observed:$detail, evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`, `detail=error: could not resolve version`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"specify init in the test repository","expected":"specify init exits 0","observed":"error: could not resolve version","evidence_url":"owner/repo"}
```

## 11. `scaffold` — push failed (line 413-414)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" --arg detail "$(tail -c 500 "$RUNNER_TEMP/auto-release-scaffold-push-err.txt")" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"pushing the scaffolded fixture", expected:"a force-push of the scaffold succeeds", observed:$detail, evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`, `detail=! [remote rejected] main -> main`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"pushing the scaffolded fixture","expected":"a force-push of the scaffold succeeds","observed":"! [remote rejected] main -> main","evidence_url":"owner/repo"}
```

## 12. `kickoff` — issue create failed (line 448-449)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" --arg detail "$(tail -c 500 "$RUNNER_TEMP/auto-release-kickoff-err.txt")" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"creating the kickoff issue", expected:"gh issue create succeeds", observed:$detail, evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`, `detail=HTTP 403: Forbidden`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"creating the kickoff issue","expected":"gh issue create succeeds","observed":"HTTP 403: Forbidden","evidence_url":"owner/repo"}
```

## 13. `kickoff` — label failed (line 460-461)

```
jq -n --arg head "$HEAD_SHA" --arg repo "$E2E_REPO" --arg detail "$(tail -c 500 "$RUNNER_TEMP/auto-release-label-err.txt")" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"labelling the kickoff issue spec-request", expected:"the spec-request label exists and gh issue edit succeeds", observed:$detail, evidence_url:$repo}'
```
Inputs: `HEAD_SHA=abc123`, `E2E_REPO=owner/repo`, `detail=HTTP 404: Not Found`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"labelling the kickoff issue spec-request","expected":"the spec-request label exists and gh issue edit succeeds","observed":"HTTP 404: Not Found","evidence_url":"owner/repo"}
```

## 14. `poll` — `write_verdict` (line 491-498)

```
jq -n --arg outcome "$1" --arg head "$HEAD_SHA" --arg failing_check "$2" \
      --arg expected "$3" --arg observed "$4" --arg url "$ISSUE_URL" \
  '{outcome:$outcome, verified_head:$head,
    failing_check: (if $failing_check == "" then null else $failing_check end),
    expected: (if $expected == "" then null else $expected end),
    observed: (if $observed == "" then null else $observed end),
    evidence_url:$url}'
```
This is the model `_shared/auto-release-verdict.sh` (T004) extracts
verbatim. Two representative call shapes:

Fail-timeout inputs: `outcome=fail-timeout`, `head=abc123`,
`failing_check=end-to-end run reaching a terminal state`,
`expected=closed with stage:done, or stage:stalled, within the poll budget`,
`observed=still open with labels [] after 6900s`,
`url=https://github.com/owner/repo/issues/1`

```json
{"outcome":"fail-timeout","verified_head":"abc123","failing_check":"end-to-end run reaching a terminal state","expected":"closed with stage:done, or stage:stalled, within the poll budget","observed":"still open with labels [] after 6900s","evidence_url":"https://github.com/owner/repo/issues/1"}
```

Pass inputs: `outcome=pass`, `head=abc123`, `failing_check=`, `expected=`,
`observed=`, `url=https://github.com/owner/repo/issues/1` (the empty-string
→ `null` coercion this site alone exercises today):

```json
{"outcome":"pass","verified_head":"abc123","failing_check":null,"expected":null,"observed":null,"evidence_url":"https://github.com/owner/repo/issues/1"}
```

## 15. `report` job — defensive fallback (line 898-899)

```
jq -n --arg head "$HEAD_SHA" --arg url "$RUN_URL" --arg observed "$no_verdict_observed" \
  '{outcome:"fail-infra", verified_head:$head, failing_check:"verify-e2e produced no verdict", expected:"a JSON verdict from verify-e2e on every path", observed:$observed, evidence_url:$url}'
```
Inputs: `HEAD_SHA=abc123`, `RUN_URL=https://github.com/owner/repo/actions/runs/999`,
`observed=the job stopped before any step wrote one (job result: failure)`

Output:
```json
{"outcome":"fail-infra","verified_head":"abc123","failing_check":"verify-e2e produced no verdict","expected":"a JSON verdict from verify-e2e on every path","observed":"the job stopped before any step wrote one (job result: failure)","evidence_url":"https://github.com/owner/repo/actions/runs/999"}
```
