# Contract: shared module additions

Two existing/new modules gain the shared surface both new gates (and the
retrofitted harness) import — this is the "exactly one home" plumbing
research.md D4/D8 describe, documented once here rather than re-derived
from each gate's own contract.

## `wc_gh_capture.py` (NEW)

```python
COVERED_GH_SUBCOMMANDS: tuple[str, ...]   # ("api",) today — FR-013

def find_capture_sites(text: str, file: str) -> list[CaptureSite]:
    """Every covered-`gh`-subcommand command-substitution capture in
    `text` (research.md D2's raw-text scan). `file` is carried through
    for failure-message attribution only — this function is called both
    against a whole workflow/action file's text (User Story 2) and
    against one extracted `run:` block's text (User Story 3's FR-015
    derivation, research.md D7), so it must not assume `text` is a full
    YAML document."""

def classify_failure_path(text: str, site: CaptureSite) -> Classification:
    """research.md D5's four safe forms (exits / reassigns / loop-exits /
    opted-in) or `unsafe`, plus the `evidence` string data-model.md's
    Failure path entity records."""
```

`find_capture_sites` and `classify_failure_path` are the two functions
`verify-gh-api-error-capture.py` calls directly and
`verify-gh-error-stub-conformance.py`'s retrofit-set derivation (contract:
gh-error-stub-conformance-cli.md step 1) calls against each harness's
extracted subject text. Neither new gate re-implements site-finding or
classification independently.

## `wc_shell_harness.py` (existing — additions only)

```python
# gh's observed two-stream error shape (FR-012). Re-verify this comment's
# version list whenever a stub built from gh_error_stub_arm starts
# failing against a newer `gh` on a maintainer's machine -- that is the
# signal the two-stream behaviour changed, not that the stub is wrong.
# Observed: gh 2.63.2, gh 2.81.0 (#497 code review, 2026-08).
def gh_error_stub_arm(match_glob: str, status: str, message: str,
                       stderr_extra: str = "") -> str:
    """One `case` arm's body: stdout gets the JSON error body (the `--jq`
    filter, if any, is never applied -- this is the whole point, #497),
    stderr gets `gh: <message> (HTTP <status>)` plus any `stderr_extra`,
    exit code 1. `match_glob` is the caller's own `case "$*" in` pattern
    (this function returns only the body between `)` and `;;`, so callers
    keep authoring their own dispatch the way every existing STUB_GH
    already does -- this is not a second stub-authoring framework, only
    the one repeated fragment CLAUDE.md's single-home rule applies to)."""
```

Existing harness scripts that stub `gh`'s error path but are **not** in
the FR-015 retrofit set (research.md D7/D9) are unaffected — they keep
their current stub bodies until next modified, per spec.md ("Other stubs
take the shared shape only when new or modified").

## Consumers this feature touches

| File | Change |
|---|---|
| `.github/scripts/wc_gh_capture.py` | NEW — `COVERED_GH_SUBCOMMANDS`, `find_capture_sites`, `classify_failure_path` |
| `.github/scripts/wc_shell_harness.py` | + `gh_error_stub_arm` and its version comment |
| `.github/scripts/verify-gh-api-error-capture.py` | NEW — imports `wc_gh_capture` |
| `.github/scripts/verify-gh-error-stub-conformance.py` | NEW — imports `wc_gh_capture` and `wc_shell_harness` |
| `.github/scripts/verify-auto-release-specs-fallback.py` | its two `STUB_GH` error arms call `gh_error_stub_arm(...)` instead of hand-writing the literal (research.md D9) |
