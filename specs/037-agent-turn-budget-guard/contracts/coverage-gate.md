# Contract: Gate 22 (verdict self-test) and Gate 23 (coverage enumeration)

Both land in `.github/workflows/lint-workflows.yml`'s existing `lint`
job, alongside Gates 1-21 (research.md R10). Both follow this
repository's two established gate disciplines rather than inventing a
third: Gate 22 is a shipped-script-extraction-plus-mutation gate (Gate
11's shape); Gate 23 is a dynamic-enumeration-plus-self-test gate (Gate
6/7/12's shape).

## Gate 22 — the agent verdict composite classifies transcripts correctly

**Script**: `.github/scripts/verify-agent-verdict.py`

**What it does**: Extracts the shipped `run:` block(s) from
`wing-commander-agent-verdict/action.yml` (and, transitively, the
shared `.github/actions/_shared/count-turns.sh` it calls) by step name,
the same way `verify-metrics-turn-accounting.py` locates `wing-commander-metrics-summary`'s
"Render agent run metrics summary" step today. Executes it via the
shared `wc_shell_harness.py` plumbing (`resolve_bash()`, `run_step()`,
`parse_github_output()`) against synthetic transcripts covering exactly
the five representative cases FR-015 names:

| Case | Fixture | Expected `verdict` |
|---|---|---|
| Healthy but would be post-hoc-rejected | `subtype: success`, `is_error: false`, `num_turns` far above a small `max-turns` (mirrors run 31918153816's 47-vs-40 shape), counted turns comfortably below `intended-turns` | `healthy` |
| Genuinely errored | `is_error: true` | `failed` |
| Exhausted | `subtype: error_max_turns` | `exhausted` |
| Schema-violating | Out of this gate's scope by design (research.md R2) — the shared composite has no schema opinion; this case is exercised instead by whichever per-site shape-check fixture the tasks stage adds, not duplicated here | n/a |
| Unreadable transcript | Missing file, empty file, invalid JSON — three sub-cases, same as Gate 11's `case_never_fails` | `unclassifiable` |

Additional cases beyond the required five, mirroring Gate 11's existing
coverage of the same transcript shapes: no terminal result record at
all (`failed`, per research.md R3's table); over-budget-but-healthy
(`over-budget: "true"`, `verdict: healthy`); under-budget-and-healthy
(`over-budget: "false"`); a result record whose `subtype` is neither
`success` nor `error_max_turns` (`failed`).

**Mutation phase**: reintroduces, and asserts this gate catches, at
least:
- Reading `is_error`/`subtype` from anywhere other than the *last*
  `.type=="result"` record (mirrors a defect class Gate 8's header
  describes for a different action).
- Treating `unclassifiable` and `failed` as interchangeable (i.e., a
  mutation that collapses the fail-closed/fail-loud distinction FR-005
  depends on).
- Computing `over-budget` from `reported-turns` instead of
  `counted-turns` (the exact defect class Gate 11 already guards
  against for the rendering action — this gate guards the same rule for
  the verdict's own field).

**Never-fail contract check**: same shape as Gate 11's `case_never_fails`
— every fixture, including the malformed ones, must exit 0.

## Gate 23 — every agent call site carries the full protection, and a lowered ceiling is caught

**Script**: `.github/scripts/verify-gate-23.py`, with its own self-test
`.github/scripts/verify-gate-23-selftest.py` invoked as a separate
`lint-workflows.yml` step (matching Gate 6/7/12's "the detector actually
detects" precedent — a gate that has never fired is indistinguishable
from one that cannot).

**Enumeration** (research.md R8/R9 — YAML-parsed, never grepped, so a
site written in flow style or unusual indentation is not silently
missed, matching Gate 7's stated rationale for the same choice):

1. Parse every `.github/workflows/*.yml`. For every job, for every step
   whose `uses` starts with `anthropics/claude-code-action`, check
   whether its `claude_args` (rendered as YAML block-scalar text)
   contains `--max-turns`. Steps without it are out of scope (research.md
   R8) and only noted, never failed, unless newly added to a file whose
   sibling sites already carry `--max-turns` (a heuristic borrowed from
   Gate 6's conservative-default handling — flagged as a note for human
   judgment, not an automatic failure, since a legitimately unbounded
   site like `claude.yml` is a real, pre-existing case).
2. For every in-scope site, assert **all** of:
   - The step immediately preceding it (or preceding it after only
     other non-agent setup steps in the same job) is
     `uses: .../wing-commander-turn-ceiling`, and the site's
     `--max-turns` value is exactly `${{ steps.<that-step-id>.outputs.ceiling }}`
     — never a literal, never a raw `inputs.max-turns` passthrough
     (research.md R9). A regex/text match on the `--max-turns` value is
     deliberately not used alone; the referenced step id must resolve to
     an actual `wing-commander-turn-ceiling` step in the same job, the
     same resolution discipline Gate 7 uses for `input_ref()`.
   - The agent step itself carries `continue-on-error: true`.
   - Some later step in the same job, gated `if: always() && ... != 'healthy'`
     (or an equivalent expression referencing that verdict step's
     `verdict` output), both prints an `::error::`-style message and can
     exit non-zero — i.e., a genuine "fail loud" arm exists and is not
     itself unconditionally skipped.
   - A `wing-commander-agent-verdict` step exists in the same job,
     `if: always()`, positioned between the agent step and any step that
     reads its outputs.
3. Print one `note:` line per in-scope site confirming coverage (mirrors
   Gate 7's per-stage `note:` lines), so a passing run is auditable
   site-by-site, not just a bare "0 failures."
4. `sys.exit(1)` if zero in-scope sites were found at all (the
   "detector saw nothing" guard every enumeration gate in this
   repository already carries — Gate 1a, Gate 7 both fail this way
   rather than reading an empty derivation as a clean pass).

**Self-test**: runs the shipped Gate 23 logic against synthetic
workflow-file trees with (a) a known-good site (passes), (b) a site
missing `continue-on-error` (fails, names it), (c) a site whose
`--max-turns` is a literal number instead of a ceiling-step output
(fails, names it — this is the direct proof of User Story 3 Acceptance
Scenario 3), (d) a site missing the verdict step entirely (fails, names
it), (e) a site missing the fail-loud arm (fails, names it).

## Doc/registry updates required alongside both gates

- `docs/architecture.md` (research.md R12): extends the existing
  turns-divergence paragraph, names Gates 22/23.
- Gate 10's wiring registry (`wc_gate_registry.py`) picks up both new
  `verify-*.py` scripts automatically (its rule is structural — any
  `verify-*.py` under `.github/scripts/` must be invoked by some
  workflow step — not a hardcoded list), so no separate registry edit is
  needed beyond adding the `run:` step that invokes each script in
  `lint-workflows.yml`.
