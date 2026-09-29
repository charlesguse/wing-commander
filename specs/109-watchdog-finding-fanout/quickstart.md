# Quickstart: Validating Watchdog Dedup That Survives Partial Signal Overlap and Class Fan-Out

Prerequisites: a repo checkout with `gh` authenticated as a maintainer,
`jq`, and either a scratch tracker (a throwaway repo/labels) or the
self-test harness the fixtures below run through (`run-local-gates.py` —
see `research.md`'s open item on the exact gate number). This quickstart
amends `specs/015-pipeline-watchdog/quickstart.md` additively — every
scenario there (detection, clean-run, missing-evidence, self-dispatch cap,
self-inspection, concurrency, coexistence, untrusted content) is unchanged
and not repeated here; only the exact-match dedup scenario (015's
open/closed dedup scenario) gains the overlap and multi-match companions
below. Every scenario maps to one Acceptance Scenario in `spec.md` and is
also a checked-in fixture (FR-020–FR-022), not only a manual demonstration
(Constitution VIII).

## Scenario A — Partial overlap attaches to the same issue across three citation sets (US1, SC-001)

1. Replay, in order, three findings of one class: citing `{A,B}`, then
   `{A,C,D}`, then `{D}` alone (the `#729`/`#732`/`#765` shape).
2. Expected: the first files a `pipeline-defect` issue whose body carries
   both the `fingerprint=` marker and a `signal-ids=A,B` marker. The
   second comments on that same issue (`signal-ids=A,C,D`, "matched on A,
   new: C, D"). The third also comments on it (`signal-ids=D`, "matched on
   D, new: (none)") even though `D` was never in the original body — only
   in the second occurrence's comment. `gh issue list --label
   pipeline-defect --state all` shows exactly one issue for this class,
   with two recurrence comments.

## Scenario B — Disjoint citation sets file a second issue (US1, Acceptance Scenario 2)

1. Given the issue from Scenario A (matchable set `{A,C,D}` after two
   occurrences), replay a finding of the same class citing `{E,F}`.
2. Expected: a *new* `pipeline-defect` issue is created — no id in common
   with the existing one's matchable set, so nothing links them.

## Scenario C — A converging implement cycle's red gate suite files nothing; a stalled or finalize-red one still files (US2, SC-002)

1. Replay run 36484099706's finding set (or a fixture shaped like it: six
   findings across six classes, every one citing only `gate-suite-failure`
   signal ids) with a `Collect: cycle outcome` artifact recorded as
   `converged=false, handoff=false`.
2. Expected: zero `pipeline-defect` issues created; the lifecycle issue
   carries six reports, each naming the `converging-gate-suite`
   suppression and its reason — never `data-integrity` or `unknown`.
3. Replay the identical finding set again, this time with the `stalled`
   label set (or `spec-meta` stage `stalled`).
4. Expected: all six are filed as normal `pipeline-defect` issues.
5. Replay again with the cycle-outcome artifact recorded as
   `handoff=true` (finalize reached, suite still red).
6. Expected: all six are filed as normal.
7. Replay again with no `Collect: cycle outcome` artifact at all
   (undeterminable state).
8. Expected: all six are filed as normal — the suppression never applies
   on a guess (FR-010).

## Scenario D — A run with both gate-suite and unrelated evidence suppresses only the gate-suite findings (US2, Acceptance Scenario 5)

1. Replay a converging-cycle run whose findings include four citing only
   `gate-suite-failure` ids and one citing a `tool-denial` id (unrelated
   evidence, same run).
2. Expected: the four gate-suite findings are suppressed
   (`converging-gate-suite`); the `tool-denial` finding is triaged and, if
   it matches nothing, filed exactly as it would be without this feature.

## Scenario E — The `{stage, tool}` denial separation survives unchanged (US3, SC-003)

1. Replay the three runs behind `#761`/`#764`/`#780` (or a fixture with
   three distinct `{stage, tool}` denial pairs).
2. Expected: three separate `pipeline-defect` issues, exactly as today —
   confirm the three issues' matchable id sets are pairwise disjoint (each
   pair's `tool-denial` signal id is unique to its `{stage, tool}`).

## Scenario F — Chained overlap: multi-match attaches to the lowest-numbered issue and names the other (US1/US3, FR-007, Edge Case)

1. Given two open issues of one class, issue X citing `{A,B}` (lower
   number) and issue Y citing `{B,C}` (higher number), replay a finding
   citing `{A,C}`.
2. Expected: exactly one write — a comment on issue X (the lower number).
   That comment's text names issue Y as another match. Issue Y receives no
   comment, is not closed, not relabeled, not reopened. Neither the
   dedup-search step's outcome nor the lifecycle-issue report calls this
   `data-integrity`.

## Scenario G — A finding whose only overlap is with a closed issue still files new (US1, FR-006, Edge Case)

1. Given a closed `pipeline-defect` issue whose recorded matchable set is
   `{A,B}`, replay a finding of the same class citing `{A,C}` (partial
   overlap with the closed issue only, no open issue matches).
2. Expected: a new issue is created — the closed issue is not reopened,
   not commented on. (Contrast with the *exact*-fingerprint case, which
   still reopens a closed issue exactly as it does today.)

## Scenario H — Truncated candidate list reads as `unknown`, never as `none` (US1/US4, FR-016)

1. Simulate (fixture) a class label with exactly 200 open+closed
   `pipeline-defect` issues, so `gh issue list --limit 200` returns a
   full page.
2. Expected: the dedup outcome is `unknown` regardless of whether any of
   the 200 fetched candidates would have matched — reported as a lookup
   that could not be trusted, never silently treated as "nothing found."

## Scenario I — The mutation fixture proves each of the above can fail its own subject (US4, SC-005)

For each of Scenarios A, C, E, F, run the checked-in fixture's companion
mutation (`tasks.md`/gate detail): reverting overlap matching to
exact-set equality, reverting the FR-009 filing condition to "always
file," and reverting the `tool-denial` id projection to a shared key.
Expected: each mutation makes the PR-time gate suite (`python3
.github/scripts/run-local-gates.py`) fail, and the failure names the
specific fixture whose subject it broke — confirming these are checks
that can fail, not decorations (Constitution VIII).
