# Research: A Failed `gh api` Read Never Becomes Data

Input: spec.md's own Clarifications section already resolved the covered
surface (FR-013: `gh api` only), the existing-site policy (FR-001/FR-008/
FR-014: correct or annotate everything before the gate turns on, no
baseline file), and the harness-retrofit boundary (FR-011/FR-015:
mechanically derived, not hand-listed). The Status update dated 2026-09-29
also resolved FR-003 (the lifecycle-gate diagnostic is out of FR-013's
scope and already safe). No `[NEEDS CLARIFICATION]` marker remains in
spec.md. The decisions below fix the concrete shapes — which file gains
which function, what the two new gates are named and numbered, how "safe"
is detected mechanically — that tasks.md needs before it can write
file-level tasks.

## D1: Scoping the audit — 32 capture sites across 13 files, confirmed against `main`

**Decision**: Record the live inventory this plan was written against,
rather than leave User Story 1's audit to start from a blank search.
`grep -rnE '[A-Za-z_][A-Za-z0-9_]*="?\$\(\s*gh api\b' .github/workflows
.github/actions` (excluding harness-test fixture directories) finds:

| File | Lines |
|---|---|
| `.github/actions/wing-commander-fold-commit/action.yml` | 92 |
| `.github/actions/wing-commander-metrics-persist/action.yml` | 624 |
| `.github/workflows/auto-release.yml` | 1214, 1455, 1488, 1572, 1638 |
| `.github/workflows/auto-update-spec-kit.yml` | 558, 1021, 3461 |
| `.github/workflows/board-loop.yml` | 1124, 1131 |
| `.github/workflows/lint-workflows.yml` | 4776 |
| `.github/workflows/pr-conversation.yml` | 625, 733, 734, 1799, 1800, 2632, 2633, 3385, 3522 |
| `.github/workflows/tasks.yml` | 537, 1632, 1861, 2004 |
| `.github/workflows/watchdog.yml` | 1762, 1769, 4001 |
| `.github/workflows/wing-commander-7-cleanup.yml` | 115, 128 |
| `.github/workflows/wing-commander-watchdog-test.yml` | 108, 171 |

32 sites, 11 files by this narrow (assignment-only) grep. The wider grep
`plan.md`'s Summary cites (93 lines, 20 files) also catches `gh api` used
without a variable-assignment capture — inside an `if gh api ...
>/dev/null` guard, piped straight into a consumer with no variable, or as
a bare read whose output is never retained — which FR-002 has nothing to
say about, since there is no captured variable to hold an error body.
Those are out of scope by construction, not by a second exclusion list.

**Rationale**: FR-001 requires the audit to cover the covered surface
completely; a plan that does not confirm the inventory it is sizing
against risks tasks.md under- or over-scoping User Story 1. This table is
a snapshot as of this plan's writing (main at `c80476f`) — User Story 1's
implementation re-runs the same grep rather than trusting this table
verbatim, since a concurrent spec or an unrelated PR can add or remove a
site before implementation starts (constitution: "different specs run in
parallel").

**Alternatives considered**: Leaving the inventory entirely to
implementation — rejected; the Summary's illustrative defect (D-finding
below) came directly from spot-checking this list during planning, and a
plan that does not ground its Scale/Scope in a real count is asking
tasks.md to discover the shape of the work from nothing.

## D-finding: `wing-commander-fold-commit/action.yml:92` is a real, currently-unsafe site

**Observation** (not a decision — recorded so User Story 1's task does
not have to rediscover it): `bot_login="$(gh api user --jq .login
2>/dev/null || true)"` followed by `[ -n "$bot_login" ] || bot_login="wing-
commander-bot[bot]"`. On an HTTP error, `gh api`'s JSON error body lands on
stdout regardless of `--jq`, so `bot_login` is *non-empty* on failure —
holding `{"message":...}` — and the `[ -n "$bot_login" ]` fallback never
fires, because the site's author reasoned about "empty vs. present," not
"error body vs. real login." The corrected value would then reach `git
config user.name`/`user.email`, producing a commit authored as the literal
error JSON string. This is exactly Acceptance Scenario 2's shape (failure
status swallowed by `|| true`, emptiness test relied on) and is left for
User Story 1's task to fix (smallest change: reassign `bot_login=""` in
the failure branch, or replace `2>/dev/null || true` with a form that
resets `bot_login` on non-zero exit) — this document only records that
the defect is real and where, so the audit is not starting blind.

## D2: Detection technique — raw-text scan, not YAML-parsed `run:` blocks or a shell AST

**Decision**: Both new gates follow Gate 28's (`verify-gh-api-explicit-
method.py`) and Gate 18's (`verify-gate-18-scan.py`) precedent: a
quote-aware raw-text scan over `.github/workflows/*.yml|yaml` and
`.github/actions/**/action.yml|yaml`, not `yaml.safe_load` of `run:`
blocks and not a shell parser/AST.

**Rationale**: Gate 28's own docstring states the reason and it applies
identically here — "Raw lines, not just parsed `run:` blocks: a composite
action's `if:` expression, a heredoc body and a documentation string can
all carry a shipped invocation, and the point of a class check is that the
class cannot land anywhere in the tree." A shell AST would be strictly
more precise about control flow (distinguishing `if ! x=$(...); then` from
`x=$(...) || true` with full fidelity), but no gate in this repository
uses one today, and introducing the first would be a second detection
technology for the same class of problem Gate 18/28 already solve with
regex — the opposite of "shared logic has exactly one home" applied to
*method*, not just to code.

**Alternatives considered**: A shell AST (e.g. via `bashlex`) — rejected;
new dependency, no precedent, and the spec's own Assumptions section
already accepts the tradeoff ("the check is deterministic and static... it
may require an explicit opt-in at a site a human would call safe, and that
opt-in is the intended resolution rather than a weakening of the check").
Parsing `run:` blocks via `yaml.safe_load` first and then regexing the
block body — rejected as a needless second step; Gate 28's raw-line
approach already finds capture sites inside `if:` expressions and heredocs
that a `run:`-only parse would miss, and this feature's own scope (a
composite's `run:` step is the overwhelming majority of sites in D1) does
not need the narrower net.

## D3: Marker syntax matches Gates 18/28 exactly — `wc-gh-api-error-exempt: <reason>`

**Decision**: FR-008's opt-in marker is `# wc-gh-api-error-exempt:
<reason>`, valid on the capture's own line or the line immediately above
it (Gate 28's `EXEMPT_RE`/`_is_exempt` shape), and a marker with no
non-whitespace reason after the colon fails the gate exactly as a bare
`wc-gh-method-exempt:`/`wc-pagination-exempt:` already does.

**Rationale**: FR-008 explicitly requires "as Gates 18 and 28 already
require" — this is the spec naming the precedent, not this plan choosing
it. A third, differently-shaped marker convention would force a reader to
learn a new syntax for the same kind of exemption they have already seen
twice in this repository.

**Alternatives considered**: None seriously — the spec forecloses them.

## D4: One shared "covered subcommand" list — `wc_gh_capture.py`

**Decision**: A new shared module, `.github/scripts/wc_gh_capture.py`
(matching the `wc_*.py` naming convention `wc_gate_registry.py`'s own
docstring documents as "shared module... exempt from the wiring rule;
must be imported by something"), holds:

- `COVERED_GH_SUBCOMMANDS = ("api",)` — FR-013's one list. Widening to
  `gh pr list --json`/`gh issue view --json` later is adding a tuple entry
  plus whatever new stdout/stderr shape that subcommand needs (not
  assumed identical to `gh api`'s), not a rewrite.
- The capture-site scanner itself (D2's raw-text detector), parameterised
  so it can run either against a whole file (User Story 2's live gate) or
  against one extracted `run:` block's text (User Story 3's FR-015
  derivation — D7 below) — one function, two callers, per CLAUDE.md's
  single-home rule.

Both `verify-gh-api-error-capture.py` and `verify-gh-error-stub-
conformance.py` import this module rather than each defining their own
notion of "is this line a covered capture."

**Rationale**: FR-013 says the list "MUST be named in exactly one list
that the capture check (and FR-011's derivation) reads" — naming both
consumers explicitly. Putting it in a new module rather than in
`verify-gh-api-error-capture.py` itself (with the conformance gate
importing that script as a library) keeps a *gate script* important
convention intact: `wc_gate_registry.py`'s own docstring reserves
`verify-*.py` for scripts "MUST be invoked by a workflow" — importing one
gate script as a library from another blurs that a `verify-*.py` file is
independently a checked-in, wired gate. A `wc_`-prefixed module is exempt
from the wiring rule by the same convention and is the correct shape for
code two gates share.

**Alternatives considered**: Duplicating the tuple and the scanner into
both gate scripts — rejected outright, the exact "pasted until the first
divergent fix" failure CLAUDE.md's own worked example warns about, and
literally what FR-013 forbids in its own text.

## D5: Failure-path classification — what "exits" and "reassigns" mean mechanically

**Decision**: A capture site's failure branch (found by scanning forward
from the capture for the guard that tests its exit status — `if !
x=$(...); then`, `x=$(...) || <cmd>`, or a bare `x=$(...)` immediately
followed by a `[ $? -ne 0 ]`/`set -e` reliance) is classified **safe**
when, before the variable's next read, that branch:

1. reassigns the captured variable (`x=""`, `x="$default"`, any new
   assignment to the same name), or
2. exits the step (`exit N`, a call to a recognised fail-helper —
   `fail_infra_on_read` is the one auto-release.yml already defines and
   uses at the D1 sites; the detector treats a call to any locally-defined
   function whose body contains `exit` as an exit, not just a literal
   `exit` token, so a differently-named helper the audit introduces
   elsewhere is not invisible to the gate), or
3. leaves the loop iteration before the variable is next read (`continue`
   or `break` inside an enclosing `for`/`while` — confirmed as a real,
   already-safe pattern at `wing-commander-7-cleanup.yml:115-127`'s `if !
   runs=$(gh api ...); then ...; continue; fi`, which this plan's D1 scan
   surfaced), or
4. carries the FR-008 marker (D3).

Anything else — including a bare `x="$(gh api ...)"` with no guard at all,
one inside a pipeline (`gh api ... | jq ...`) with no `if`/`||` testing the
substitution's own status, or a guard whose taken branch only logs — is
**unsafe**.

**Rationale**: This is FR-002's definition made concrete enough to
implement as a text scan, using real examples already in the tree (D1's
inventory) rather than inventing hypothetical shapes. Recognising
`continue`/`break` as a fourth safe form is not in FR-002's literal text
("exits the step, reassigns... or carries the marker") but is required by
spec.md's own Assumption that "correcting a site means the smallest change
that makes the failure path explicit" — flagging `wing-commander-7-
cleanup.yml`'s already-correct `continue` pattern as unsafe would force a
no-op "fix" that only silences the gate, which Principle VIII's spirit
(a check that produces a finding proving nothing) argues against. The
spec's Edge Cases list ("A capture whose only consumer is inside the
failure branch that exits — no reset is needed") already treats "exits"
loosely enough to cover this; `continue` exits the *use* of the variable
for this pass exactly as `exit` exits the step for good.

**Alternatives considered**: Requiring every failure branch to either
`exit` the whole step or explicitly reassign, with no `continue`/`break`
allowance — rejected; it would fail a real, already-safe, already-shipped
site (D1's cleanup example) on day one, which is the "conservative to the
point of requiring an opt-in a human would call safe" tradeoff the spec's
Assumptions accepts only when the alternative is missing a real bug, not
when it is misclassifying a safe pattern outright.

## D6: Gate numbers — 125 and 126, re-verified before landing

**Decision**: `verify-gh-api-error-capture.py` is wired as "Gate 125" and
`verify-gh-error-stub-conformance.py` as "Gate 126" in `lint-workflows.yml`,
each with its own live-check step and `--self-test` step (the two-step
convention every numbered gate already follows). 124 is the highest gate
number present in `.github/scripts/verify-*.py` docstrings as of this
plan (`main` at `c80476f`); both numbers are re-verified immediately
before landing, since concurrent specs may claim one first.

**Rationale**: Matches this repository's sequential, assigned-at-landing
numbering convention (see spec 080's plan.md D3 for the same reasoning).
Two gates, not one, because User Story 2 and User Story 3 check different
subjects (shipped capture sites vs. harness stub conformance) and a single
failing run should not force a reader to disentangle which story's
regression fired.

**Alternatives considered**: One combined gate script with two subcommands
— rejected; `run-local-gates.py`'s `--jobs` filtering and the timing cache
both key off one script-plus-args identity per concern (spec 080's
`gate_label()`), and splitting the fixture sets for two structurally
different detectors into one file's `CASES`/`MUTATIONS` table would make a
failing mutation ambiguous about which requirement group broke.

## D7: FR-015's retrofit set is derived by re-running D4's scanner against each harness's own extracted subject text

**Decision**: For every harness-driven gate `wc_gate_registry.gate_scripts()`
already discovers that stubs `gh` (detected structurally: the script
defines a string constant fed to `run_step` as the `gh` entry on
`PATH`/`path_prepend`, the existing `STUB_GH`-naming convention every
current harness already follows), `verify-gh-error-stub-conformance.py`
extracts the same shipped `run:` text that harness's own `find_step`/
`extract_quoted_var` call names as its subject, and runs D4's capture
scanner against *that extracted text* (not the whole workflow file). A
harness is in the FR-015 retrofit set exactly when that scan finds at
least one covered capture in its own subject block.

**Rationale**: FR-015 requires the set to be "derived mechanically from
the gates and the blocks they execute, never kept as a hand-maintained
list." Reusing D4's scanner rather than writing a second detector keeps
"what counts as a covered capture" answerable exactly once — a harness
whose subject block the live capture-check gate (User Story 2) would flag
if it looked there is, by construction, a harness this gate cares about.
`verify-auto-release-specs-fallback.py` is confirmed to land in this set
today (plan.md Scale/Scope): its own subject block (the `specs/` contents
read) is one of the D1 sites, and its `STUB_GH` already stubs that read's
error arm.

**Alternatives considered**: A hand-maintained list of "harnesses that
touch `gh api`" — rejected outright by FR-015's own text. Deriving
membership from the harness's *stub* content (does `STUB_GH` contain a
`gh api` case pattern) rather than the *shipped subject's* content —
rejected; a harness could stub a `gh api` call defensively without the
shipped block actually reaching an unsafe capture, which would over-widen
the retrofit set to harnesses FR-015 does not require touching, and would
make "in scope" depend on the harness author's own choices rather than on
the shipped pipeline's actual shape.

## D8: FR-009–FR-011 enforcement is a single-home check, not a re-execution of every harness

**Decision**: `wc_shell_harness.py` gains one new function, e.g.
`gh_error_stub_arm(match_glob, status, message, stderr_extra="")`,
returning the two-line `printf`-to-stdout / `echo ... >&2` / `exit 1`
shell fragment FR-009 specifies, plus a module-level comment recording the
`gh` versions FR-012 requires (2.63.2 and 2.81.0, per spec.md's own
Assumptions — matching #497's review). `verify-gh-error-stub-
conformance.py` does not re-execute every retrofitted harness to observe
its runtime behaviour; instead, for each gate in D7's derived set, it
scans that gate script's own source for a `gh`-error-simulating arm (a
case/branch whose pattern matches a covered capture's command and whose
body is NOT a call into `wc_shell_harness.gh_error_stub_arm(...)`) and
fails on any such arm, naming the gate script (FR-011). Separately, it
scans every `.github/scripts/*.py` file for the canonical JSON-error-body
literal (the `{"message":...,"status":"...` shape) appearing anywhere
other than inside `wc_shell_harness.py` itself, catching a hand-rolled
duplicate even in a gate D7's derivation did not select (FR-010's "a
second copy" is a textual fact independent of which gates are in the
retrofit set).

**Rationale**: Re-running every harness's own `--self-test` from inside a
second gate to observe stdout/stderr at runtime would work, but it makes
the conformance gate's own runtime cost scale with the full harness suite
(`run-local-gates.py`'s documented ~1600s serial budget already comes
from three ~300s harnesses) for a question — "does this stub's source
come from the one shared place" — that is answerable by reading the
source once. This is the same choice Gate 47
(`verify-comment-canonical-pointers.py`) already made for canonical prose:
enforce "there is exactly one home" by scanning text, not by re-deriving
every consumer's behaviour and diffing it. It also means a regression is
caught the moment a hand-rolled literal is typed, before anyone runs that
harness's own (possibly slow) self-test at all.

**Alternatives considered**: Executing each retrofitted harness's
self-test and asserting its reported output contains the FR-009 shape —
rejected for the performance reason above, and because a harness's
self-test is designed to prove the *shipped workflow* behaves correctly
given the stub, not to prove the *stub itself* matches real `gh` — two
different assertions that a single "does it call the shared helper" text
check answers together without conflating them.

## D9: Migrating `verify-auto-release-specs-fallback.py`'s two stub arms is this feature's own first-party FR-015 fix, not a stretch goal

**Decision**: Because D7 places `verify-auto-release-specs-fallback.py` in
the retrofit set today, this feature's implementation replaces its two
inline `STUB_GH` error arms (the `contents/specs` and `contents/specs/`
cases, both hand-writing the 404/error JSON+stderr shape — plan.md's
Scale/Scope) with calls to the new `wc_shell_harness.gh_error_stub_arm`
helper, as part of landing User Story 3 rather than as a follow-up.

**Rationale**: SC-005 ("a deliberately introduced second copy is
reported") is only a meaningful self-test if the shipped tree has zero
copies outside the shared home once this feature lands — leaving the
existing, already-known duplicate in place would mean the new gate ships
already red on `main`, the same "wiring before the audit is done" problem
FR-014 exists to prevent for User Story 1, applied here to User Story 3.

**Alternatives considered**: Leaving the existing duplicate and scoping
this feature to "no *new* duplicates" — rejected; FR-010's text is
unconditional ("the error-response shape... MUST have exactly one home"),
not grandfathered, and the spec draws no such distinction.
