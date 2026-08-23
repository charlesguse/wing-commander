# Phase 0 Research: A Transient API Blip No Longer Kills Six Stages at Entry

spec.md carries no literal `[NEEDS CLARIFICATION]` markers — the two that
existed during `/speckit-clarify` were already resolved on 2026-08-21
(spec.md Clarifications section, checklists/requirements.md Notes): FR-009's
default treatment (retry everything not positively identified as permanent)
and FR-016's scope boundary (this feature does not touch the `implement`
silent chain-stop, tracked separately as #231). Phase 0 below resolves the
*technical* unknowns planning still had: the exact bounded budget, how to
classify a `gh` failure from its own text without over- or under-matching,
how to capture and safely render diagnostic output, and how to extend the
existing test harness to prove retry actually runs.

## D1 — Retry budget: 3 attempts, 4-second per-attempt timeout, 1-second backoff

**Decision**: Up to 3 attempts. Each attempt wraps the `gh` call in
`timeout 4` (a hang or a connection that never returns a status is one of
FR-001's named transient shapes — spec Acceptance Scenario 5 — and without
an explicit timeout it is unbounded, not merely slow). A 1-second sleep
separates attempts (none after the third). Worst case: `4 + 1 + 4 + 1 + 4 =
14` seconds, one second inside FR-003/SC-004's 15-second ceiling, leaving
margin for `gh`'s own process-startup cost, which the `timeout` wall-clock
does not otherwise account for.

**Rationale**: The spec's own Assumptions section states the count
directly ("Three attempts with a short, bounded delay is the right size...
The attempt count and delay are fixed constants rather than new inputs")
and ties it to the observed frequency (one occurrence in a hundred failed
runs). A per-attempt timeout is necessary, not optional: FR-001 explicitly
lists "a timeout" as a transient class the gate must retry, and the only
way an unresponsive `gh` process becomes a *classifiable* failure rather
than a job that eventually gets killed by GitHub's own step timeout (which
would report as a generic Actions cancellation, not this composite's
diagnostic) is to bound it explicitly and let the retry loop treat that
bound like any other failure.

**Alternatives considered**:
- *Exponential backoff* (e.g., 1s, 2s, 4s) — rejected as unnecessary
  complexity for a 3-attempt budget this small; a flat 1-second delay
  already keeps worst case inside the 15-second ceiling with margin, and
  the spec's own framing ("a bounded retry on transient classes, not a
  general resilience framework") favors the simplest mechanism that
  satisfies FR-003.
- *No per-attempt timeout, rely on the job's overall step timeout* —
  rejected: a hung first attempt would consume the entire step timeout
  before a second attempt could even start, defeating the retry's purpose
  and violating SC-004's 15-second ceiling on the gate specifically.
- *5 attempts / longer timeout* — rejected: would either exceed the
  15-second ceiling or force a smaller per-attempt timeout that risks
  classifying a merely-slow-but-healthy response as a timeout failure.

## D2 — Classification: two permanent patterns, everything else retried

**Decision**: Classify captured stderr text (falling back to a synthetic
"no diagnostic output" string when a call exits non-zero with nothing on
stderr, or exits zero with an empty state) against two permanent patterns,
checked in this order, before falling through to the transient/unclassified
retry path:

1. **Not found / not visible** — matches `Could not resolve to an.*[Ii]ssue`
   (the literal GraphQL error `gh issue view` surfaces for a missing or
   inaccessible issue number) or `HTTP 404`.
2. **Credential rejected** — matches `HTTP 401`, `Bad credentials`,
   `Resource not accessible by integration`, or scope-shaped wording
   (`requires authentication`, `insufficient .* scope`, `missing .*
   scope`).

Anything that matches neither — a recognised transient shape (`HTTP
5\d\d`, `timed out`, `Could not connect`, connection-reset wording), a
rate-limit rejection, or an unfamiliar fault — is retried. Internally, a
failure is further tagged `transient` (matches a recognised transient
pattern) or `unclassified` (matches neither list) purely so the FR-006
exhaustion message can say which; this tag never changes whether the
failure is retried, only what the final message says.

**Rationale**: FR-002 requires immediate failure be reserved for a
*positively identified* permanent condition; FR-009 requires everything
else default to retry, explicitly including failures the gate has never
seen before. A allow-list of permanent patterns (rather than a deny-list of
"looks transient") is the only shape that satisfies both: an unfamiliar
fault automatically lands in the retry bucket because it matches neither
permanent pattern, with no separate "unknown → retry" rule needed — the
retry-by-default falls out of the classifier's structure rather than being
a third branch that could itself be reverted or narrowed independently of
the other two (which is exactly the regression FR-013/US4's fourth
scenario tests for).

The credential pattern deliberately does **not** match on a bare `HTTP
403`, because `gh`'s own rate-limit errors also use HTTP 403 (`API rate
limit exceeded for installation ID ...`, or GitHub's secondary rate limit
message) and the spec's edge case is explicit that rate-limiting must be
retried, not treated as permanent (spec Edge Cases: "The API rejects the
read for rate-limiting reasons... Retried like anything else not
positively identified as permanent"). Matching only the scope/
authentication-shaped 403 text, not the bare status code, keeps the two
403 cases distinguishable: a rate-limited 403 falls through to the retry
path (and is tagged `unclassified`, since it matches no *transient*
pattern either — it is still retried, per D-above), while a genuinely
insufficient-scope 403 fails fast.

**Alternatives considered**:
- *Deny-list of known transient shapes, fail everything else* — this is
  exactly the classifier the source incident's absence of retry
  demonstrates the risk of, and precisely what the spec's clarification
  session rejected (spec.md Clarifications: "A classifier that retries
  only the failure shapes already seen would kill a stage at entry the
  next time a transient fault is worded differently"). Rejected.
- *Treat any `HTTP 403` as permanent* — rejected per the rate-limit edge
  case above; would misclassify a rate-limited retry-worthy condition as a
  credential failure and fail fast on it, regressing SC-009.
- *Distinguish rate-limit 403 by checking for a `Retry-After`/
  `x-ratelimit-*` header* — rejected: `gh issue view`'s plain-text error
  output does not expose response headers to the shell script; only the
  message body is available via stderr, so header-based detection is not
  implementable without switching to `gh api` and parsing headers
  directly, a materially larger change than this feature's scope.

## D3 — Capturing stderr and handling a hang, without restructuring the step

**Decision**: Redirect each attempt's stderr to a per-attempt temp file
(`stderr_file="$(mktemp)"`, `... 2>"$stderr_file"`) rather than combining
stdout/stderr into one stream — `--jq .state`'s stdout must stay isolated
so `state="$(...)"` still captures exactly the state value with nothing
appended, and the file is read and removed immediately after each attempt
so no per-attempt file leaks across the loop. `timeout 4 gh ...` wraps the
whole command; `timeout`'s own exit code (124 on expiry) needs no special
handling — the command substitution's overall non-zero exit already drives
the same `if ! state=... ; then` branch a `gh`-side failure would, and
`timeout`'s own message ("terminated") on stderr, if any, is captured like
any other diagnostic text.

> **Correction (2026-08-22).** The last clause above is wrong, and the
> "needs no special handling" conclusion it supports is wrong with it.
> `timeout` writes NOTHING to stderr on expiry — measured: `timeout 1 sleep
> 5` exits 124 having produced zero bytes. The familiar "terminated"
> message comes from an interactive shell's job-control reporting a signal,
> not from `timeout`, and no such shell exists in a workflow step. So a hung
> read reached the classifier as `"no diagnostic output"`, matched no
> transient pattern, and was reported as *"the failures could not be
> classified"* — for the class FR-001 names first, and in direct violation
> of SC-007. The step now branches on exit 124/137 explicitly and names the
> timeout from the exit code, which is its only witness. Covered by
> `verify-lifecycle-gate-retry.py`'s `TIMEOUT_THEN_SUCCEED` (which drives
> the real `timeout` rather than simulating its status) and
> `BUDGET_EXHAUSTED_TIMEOUT`, plus a mutation that reverts the branch.

**Rationale**: This is the smallest change that fixes the source defect's
second half (spec: "the command substitution captures stdout only, so the
actual `HTTP 502` on stderr never reaches the error text"). It keeps the
step's control flow — `if ! state=... || [ -z "$state" ]; then ...` —
structurally identical to today's, just now inside a bounded loop and with
stderr available for classification.

**Alternatives considered**:
- *`2>&1` merged capture* — rejected: would pollute `state` with the error
  text on failure, and on success would risk `gh` writing anything
  informational to stderr (e.g., a rate-limit warning on an otherwise
  successful call) into the captured state value, breaking the `case`
  statement's exact-match logic.
- *A named pipe / process substitution for stderr* — rejected as
  unnecessary complexity; a `mktemp` file per attempt is the simplest
  mechanism, mirrors patterns already used elsewhere in this repository's
  composites for capturing command output to a file, and is trivially
  cleaned up in the same loop iteration.

## D4 — Rendering diagnostic text safely (FR-018) and not exposing the token (FR-017)

**Decision**: Before any diagnostic text reaches a `::warning::` or
`::error::` line: strip `\r`/`\n` (replace with a single space), collapse
repeated whitespace, cap the result at 300 characters with a `…
(truncated)` suffix when longer, then `%`-escape the result
(`%` → `%25`) — GitHub's own workflow-command escaping rule, which also
neutralises any literal `%0A`/`%0D` sequences that might otherwise be
mis-parsed as newline-escape sequences by the runner. This produces a
single-line, bounded string safe to embed directly in a workflow command.

No additional token redaction is added. `gh issue view` authenticates via
the `GH_TOKEN` environment variable and does not echo the token's literal
value into its own stdout/stderr in normal operation (it may reference the
environment variable *name* in a diagnostic, never the value) — confirmed
by inspection of `gh`'s error-message formatting, which never interpolates
credential material into user-facing text. Nothing in the rewritten step
constructs a string containing `$GH_TOKEN` either, so FR-017 is satisfied
by the step never having the token in scope for anything it prints, not by
relying on GitHub's automatic secret-masking (which the spec's own
Assumptions section says the gate "must not rely on... alone").

**Rationale**: FR-018's edge case is explicit about long, multi-line, or
otherwise annotation-breaking diagnostic text; GitHub's workflow-command
format is itself line-oriented, so an unescaped multi-line stderr capture
(e.g., a stack trace or a multi-paragraph API error body) would visually
truncate or corrupt the annotation at the first embedded newline. Bounding
length additionally protects against a pathological response body without
needing to special-case any particular API shape.

**Alternatives considered**:
- *Truncate only, no escaping* — rejected: does not address embedded
  newlines, which is the more common real-world case (a multi-line GraphQL
  error body) and is called out explicitly in the edge case.
- *Base64 or otherwise re-encode the diagnostic* — rejected: satisfies
  "readable" (FR-018 requires the error stay *readable*) worse than a
  collapsed, escaped, capped plain-text line; a maintainer should be able
  to read the quoted text directly, not decode it.

## D5 — The empty-state case is retried, not folded into a generic failure

**Decision**: A zero-exit `gh` call that yields an empty `$state` is
treated exactly like a non-zero exit for retry purposes (it already fails
the same `|| [ -z "$state" ]` condition today) but is captured with a
synthetic diagnostic — `"gh exited 0 but returned an empty state"` — since
there is no stderr to quote in this case, and is classified `unclassified`
(matches neither permanent pattern, and matches no transient pattern
either, since there is no transient-fault text to match against).

**Rationale**: Spec Edge Cases and FR-009 both state this explicitly: "an
absent answer is not positively identified as permanent, so it takes the
recoverable path." This is structurally just one more input to the same
classifier (D2) rather than a special case — the classifier's fallthrough
already handles it correctly as long as the synthetic diagnostic text is
supplied so the eventual exhaustion message (FR-006) has something to
quote instead of an empty string.

**Alternatives considered**: None materially different — the spec's own
clarification session already closed this question; the only planning
decision left was what synthetic diagnostic text to substitute so FR-006's
"what the last attempt reported" requirement has non-empty content.

## D6 — Coverage: extend `wc_shell_harness.py`'s `gh`-stub pattern with a call counter

**Decision**: `.github/scripts/verify-lifecycle-gate-retry.py` follows
`verify-stall-restart-runbook.py`'s established shape (`.github/scripts/
verify-stall-restart-runbook.py:92-100,170-173,213`) — a `#!/bin/sh` shim
written to a `bindir/gh`, `chmod 0o755`, with `PATH` overridden via
`run_step`'s `env_extra` to prepend `bindir`. This feature's stub adds one
new mechanism that script doesn't need: a **call counter** file (e.g.
`$RUNNER_TEMP/gh_call_count`), incremented by the stub on every invocation,
so the stub's behavior (exit code, stdout, stderr) can branch on "which
call is this" — enabling "fail N times then succeed," "always fail
permanently," and "fail in an unrecognised shape" as distinct stub
configurations, generated by a small Python helper that writes the right
shell logic per test case rather than one fixed stub script.

**Rationale**: This is the closest existing prior art in the repository
(the spec names it directly: "Gate 14... is how the harness drives a
shipped composite's `run:` block against a stubbed `gh`") and reuses
`wc_shell_harness.py` completely unmodified — no changes to the harness
itself are needed, only a new caller. `verify-stall-restart-runbook.py`'s
stub is fixed-behavior (always succeeds) because that gate only needs to
prove *what* was called, not vary success across calls; this feature's
stub generalizes the same call-logging idea (a file the stub writes to) to
also gate its own behavior on call count, which is the one new piece of
mechanism this feature needs from the harness ecosystem.

**Alternatives considered**:
- *Modify `wc_shell_harness.py` itself to support a stateful stub* —
  rejected: the harness's public API (`run_step`, `find_step`, etc.) needs
  no changes to support this; the per-call-count logic belongs entirely in
  the new stub shell script the test writes, keeping the shared harness
  untouched and every other gate that depends on it unaffected.
- *One stub script per scenario, hardcoded* — considered and adopted in
  spirit: each scenario in Gate 25 (retry-then-succeed, fail-N-times, always
  permanent, unrecognised-shape) gets its own small generated stub rather
  than one mega-stub with a scenario-selector environment variable, mirroring
  how `verify-stall-restart-runbook.py` keeps its stub minimal and
  purpose-built per test.

## D7 — Proving the retry is exercised, not merely shipped (FR-011–FR-014)

**Decision**: Gate 25 is structured as Gate 14 is — no separate `Gate 25
self-test` step; instead the script itself, in one `main()`, runs the
shipped step's happy/retry/fast-fail scenarios directly against the real
`action.yml` step text (via `find_step`), then applies FR-013's four
required mutations to a deep copy of that step text (revert the retry to a
single attempt; widen the permanent-pattern classifier so it also matches a
transient shape; narrow the retry so an unclassified failure fails
immediately; and — this script's own reflexive check — confirm Gate 25's
step is actually present and enabled in `lint-workflows.yml`, so the gate
cannot be silently removed without another gate noticing, per FR-014) and
asserts each mutated variant now fails the same suite that the unmutated
step passes, with the `if mutated == steps` guard `verify-stall-restart-
runbook.py:345` already establishes to catch a mutation that silently
failed to apply.

**Rationale**: FR-013 requires reverting the retry, widening it, or
narrowing it each independently fail a check — "coverage that can only
exercise the success path does not satisfy this requirement." Gate 14's
mutation-testing shape is the only existing pattern in this repository that
already does exactly this class of self-proof for a single-script gate
(the paired-self-test-step pattern used elsewhere, e.g. Gates 16/18/22/23,
is designed for gates that are themselves *detectors* checked out-of-band;
this feature's gate is closer to Gate 14's shape — a small number of
concrete behavioral scenarios plus mutation coverage — than to a detector
needing a separate self-test step).

**Alternatives considered**:
- *A paired `Gate 25 self-test` step* (the Gates 16/18/22/23 pattern) —
  rejected: that pattern fits a *detector script* whose job is to flag a
  drifted/violating file elsewhere in the repo, proven by mutating a
  fixture and rerunning the detector. This feature's gate instead directly
  executes the shipped composite step's own bash against stubs and asserts
  on its outputs — Gate 14's shape, not Gate 16's — so a second, separate
  self-test step would duplicate what the mutation-testing already proves
  in one script.
