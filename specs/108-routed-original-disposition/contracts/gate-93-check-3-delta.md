# Contract: Gate 93 Check 3 Delta

A delta against `.github/scripts/verify-issue-context-single-home.py`'s
`check_spec_request_bodies()` (Gate 93 check 3), for FR-012/FR-013. This
extends that existing function rather than adding a fourth `check_*`
function to `check_repo()` or a new gate script — FR-012 says explicitly
this "MUST extend the existing gate check ... rather than standing up a
second gate over the same subject."

## New assertion, added inside the existing per-site loop

For every `gh issue create ... spec-request` site `check_spec_request_
bodies()` already finds (the same `create_idx`/`creates` list its guard
check walks), scan the lines AFTER the create-guard's exit point (the same
boundary `_create_guard_problems()` already locates) for a call matching
`dispose_as_duplicate`-shaped invocation (the module contracts/
duplicate-disposition.md defines — exact matched text is an
implementation-defined regex tasks.md fixes once the module's name is
chosen, mirroring how `_is_spec_request_create()` and
`SPEC_REQUEST_BUILDER` are matched by literal substring today). If no such
call appears before the step ends, report a problem naming the site — the
same `f"{where}: ..."` message shape every other problem in this function
uses, so it prints identically to the guard's own findings.

```python
def _has_disposition_call(where, lines, create_idx):
    """Gate 93 check 3 extension (spec 108, FR-012): every spec-request
    create site must also dispose of the originating issue -- the single
    shared disposition module (contracts/duplicate-disposition.md), never
    an inline close/label/comment sequence (which the existing single-home
    check for board_spec_request_body.py already polices for the CREATE
    side; this is the same rule for the DISPOSE side)."""
```

## `sites == 0` still fails rather than passing vacuously (FR-012)

Unchanged from today's `check_spec_request_bodies()` — the existing
`if sites == 0: problems.append(...)` guard already covers this; FR-012's
"MUST fail rather than pass when it finds no spec-request site to check"
requirement is already met by the base check and needs no new code, only
confirmation it still fires (a fixture with zero sites is already among
`_self_test_spec_request_sites`'s cases per the base check's own harness).

## Fixtures (FR-012's "checked-in fixture for each failure branch")

Extends `_site_fixture`/`_create_guard_cases`'s existing synthetic-YAML
harness with:

1. **Good site**: create → guard → `dispose_as_duplicate` call → cross-link
   → marker. Passes.
2. **Bad site — create-guard-only workflow with no disposition call
   anywhere in the step**: create → guard → cross-link → marker, no
   dispose call. Fails, naming the site (mirrors `_create_guard_cases`'s
   "missing X" pattern).
3. **Bad site — disposition call BEFORE the create guard**: same
   ordering violation class `_create_guard_problems()` already flags for
   other actions; the new assertion's placement (after the guard's exit
   point) means this fixture exercises the existing guard-ordering check
   catching it too, not a second, redundant check.
4. **The real `board-loop.yml`**: passes with the three sites this feature
   adds the call to.

`check_repo()` itself needs no new dispatcher line — the new assertion
lives inside `check_spec_request_bodies()`, which `check_repo()` already
calls at line 1313 (`problems.extend(check_spec_request_bodies(BOARD_
LOOP))`), and the two other call sites in the file's own self-test harness
(the `if not check_spec_request_bodies(path)` and `problems =
check_spec_request_bodies(path)` self-test entry points) pick it up
automatically since they invoke the same function.

## Registration (FR-013)

No registry-file change: `run-local-gates.py` derives its gate list from
`wc_gate_registry.pr_time_invocations`, itself derived from scanning
`lint-workflows.yml`'s own `run:` lines for `verify-issue-context-single-
home.py` invocations (already present, unchanged by this feature) — the
extended check runs under the exact same CI and local invocation
(`python3 .github/scripts/verify-issue-context-single-home.py` and
`--self-test`) it does today.
