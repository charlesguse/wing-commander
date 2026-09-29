# Data Model: A Failed `gh api` Read Never Becomes Data

This feature persists nothing new (research.md: no storage layer). Every
entity below is a shape read back from the checked-out tree — workflow and
action YAML text, `.github/scripts/verify-*.py` source — at gate-run time,
giving each of spec.md's Key Entities a concrete, code-level shape.

## Capture site

One place in a workflow or composite action where the output of a covered
`gh` read is assigned to a shell variable via command substitution.

| Field | Type | Source | Notes |
|---|---|---|---|
| `file` | string | repo-relative path | `.github/workflows/*.yml`\|`.yaml` or `.github/actions/**/action.yml`\|`.yaml` only (research.md D2's scope; `.github/scripts/` is out of the audit boundary per spec.md Assumptions, except where the harness-conformance gate reads gate source directly — a different entity, see "Stub arm" below) |
| `line` | int | 1-indexed line number | used verbatim in the gate's failure message (SC-006) |
| `variable` | string | the assignment target's name | e.g. `bot_login`, `slug`, `existing` |
| `subcommand` | string | the `gh` word immediately after `gh` | MUST be a member of `wc_gh_capture.COVERED_GH_SUBCOMMANDS` (today: `("api",)`, FR-013) for the site to be in scope at all; a `gh issue view`/`gh pr list`/etc. capture is not a capture site for this feature's purposes |
| `guard_form` | enum: `if-negated` \| `or-fallback` \| `bare` \| `pipeline` | derived from the text immediately surrounding the capture | `if ! x=$(...); then` / `x=$(...) \|\| <cmd>` / no guard at all / `gh api ... \| <cmd>` with no status test — informs classification (research.md D5) but is not itself the safety verdict |

## Failure path

The code a capture site reaches when the read exits non-zero.

| Field | Type | Notes |
|---|---|---|
| `classification` | enum: `exits` \| `reassigns` \| `loop-exits` \| `opted-in` \| `unsafe` | research.md D5's four safe forms plus the default. `loop-exits` covers `continue`/`break` before the variable's next read — confirmed necessary by the real `wing-commander-7-cleanup.yml:115` pattern found during planning (research.md D1's finding, D5's rationale) |
| `evidence` | string (quoted source text) | the specific token/call the classifier matched — `exit 1`, `fail_infra_on_read`, `continue`, the reassignment's new value, or the marker's reason text — surfaced in the failure message so SC-006 holds without reading the gate's source |

## Capture check (Gate — User Story 2)

The PR-time check that classifies every capture site and fails on an
unsafe one, together with its self-test.

| Field | Type | Source | Notes |
|---|---|---|---|
| `script` | string | `.github/scripts/verify-gh-api-error-capture.py` | discovered by `wc_gate_registry.gate_scripts()`'s existing mechanical convention — no registry change needed |
| `covered_subcommands` | tuple of string | `wc_gh_capture.COVERED_GH_SUBCOMMANDS` | FR-013's one list; imported, never redefined, by this gate and by the conformance gate's FR-015 derivation |
| `exempt_marker` | regex | `# wc-gh-api-error-exempt: <reason>`, same-line or immediately-preceding line | research.md D3; a bare marker (no non-whitespace reason) is itself a failure, matching Gates 18/28 |
| `self_test_cases` | list of `(name, text, expect_fail, must_mention)` | in-source `CASES` table | Gate 28's own shape; one case per research.md D5 classification branch, plus the #497 shape (FR-007's explicit requirement) |
| `self_test_mutations` | list of `(label, Detector)` | in-source `MUTATIONS` table | each must flip at least one fixture's verdict (SC-003: "zero mutations passing") |

## Harness error response (shared, User Story 3's single home)

The single canonical description of what a failing covered `gh` read
emits on each stream, consumed by every harness stub that simulates one.

| Field | Type | Source | Notes |
|---|---|---|---|
| `home` | string | `.github/scripts/wc_shell_harness.py` | the one file allowed to contain the literal JSON-error-body / stderr-line shape (research.md D8) |
| `builder` | function | `gh_error_stub_arm(match_glob, status, message, stderr_extra="")` | returns the shell fragment (`printf` to stdout, `echo ... >&2`, `exit 1`) every retrofitted stub's error arm must call instead of hand-writing |
| `observed_versions` | tuple of string | module-level comment beside `builder` | `("2.63.2", "2.81.0")` — FR-012, sourced from spec.md's Assumptions / the #497 review |

## Stub arm (an entity the conformance gate reads, not a capture site)

One `gh`-stubbing case/branch inside an existing harness-driven gate
script's source.

| Field | Type | Source | Notes |
|---|---|---|---|
| `gate_script` | string | repo-relative path under `.github/scripts/` | member of the FR-015 retrofit set (below) |
| `simulates_error` | bool | does this arm's body `exit` non-zero | only error-simulating arms are in scope for FR-009/FR-011; a success arm is not |
| `calls_shared_home` | bool | does the arm's body invoke `wc_shell_harness.gh_error_stub_arm(...)` (or paste its literal return value verbatim — treated the same by the textual check) rather than a hand-written JSON/stderr literal | `False` is the FR-011 failure condition |

## Retrofit set (FR-015)

The harness-driven gates required to use the shared home.

| Field | Type | Source | Notes |
|---|---|---|---|
| `members` | list of gate script paths | **derived, not stored**: for each `wc_gate_registry.gate_scripts()` entry that stubs `gh` (structural detection: a `STUB_GH`-shaped constant fed to `wc_shell_harness.run_step`), extract its own subject `run:` text (via that harness's existing `find_step`/`extract_quoted_var` call) and run the Capture check's scanner against it | membership = "this harness's own subject block contains a covered capture" (research.md D7); `verify-auto-release-specs-fallback.py` confirmed a member today |
| non-members | — | any harness-driven gate whose subject block has zero covered captures | takes the FR-009 shape only when next added or modified (spec.md: "Other stubs take the shared shape only when new or modified") — not required to change by this feature |

## Non-goals / explicitly out of scope for this data model

- No new persisted record, schema, or JSON file — FR-014 explicitly
  forbids a baseline/allowlist file of accepted existing sites.
- No state transitions. Every entity above is recomputed fresh on each
  gate run from the checked-out tree.
- No model/agent judgment anywhere in this data model — every field is
  computed by deterministic text scanning (constitution IX), matching the
  existing `verify-gh-api-explicit-method.py`/`verify-gate-18-scan.py`
  precedent this feature's two new gates follow.
