# Contract: FR-012, FR-013, FR-015 — gate coverage

## `verify-dedup-key-canonical-rule.py` (NEW)

Registered in `lint-workflows.yml` (so `run-local-gates.py` picks it up
automatically per Principle VIII), bundling both new checks this feature
needs — the two are related (both hold a written-down rule in place
against silent code drift) and share the same extraction helper, matching
how `verify-single-home-idioms.py` already bundles multiple named checks in
one script.

### `check_canonical_rule_sync` (FR-012)

- Reads `specs/056-stage-found-defect-filing/data-model.md`, extracts the
  "Fingerprint" section's fenced formula block by a fixed marker.
- Reads the shipped "Extract, validate, cap, and prepare findings" step out
  of `.github/actions/wing-commander-stage-findings/action.yml` (via the
  same `find_step`-style extraction `.github/scripts/stage-findings-tests/run_fixtures.py`
  already uses — no second, drifting parse of the same YAML).
- Asserts every literal the doc's formula names — the `norm()` regex, the
  `anchor|` / `fallback|` shape tags (research.md D2), and the
  pipe-delimited segment order for each shape — appears verbatim in the
  extracted code.
- Fails loudly, naming which literal is missing and from which side, on any
  divergence. Fails loudly (not "0 checked, pass") if either source file is
  missing or the fenced block cannot be found — Principle VIII's "loud
  rather than vacuous" rule.

**Fixture** (FR-030's discipline, applied here too): a scratch copy of the
action file with one shape tag changed, asserted to fail naming that tag; a
scratch copy of the doc with the fenced block's `norm()` line altered,
asserted to fail; the real files, post-implementation, asserted to pass.

### `check_composition_split` (FR-015)

- Extracts this feature's fingerprint formula (as above) and spec 057's own,
  `sha256("<issue>|<norm(title)>|<norm(file_path)>")`, from `board-loop.yml`'s
  "Prepare out-of-scope findings for filing" step.
- Fails if the two extracted formula strings are textually identical
  (guards silent convergence).
- Fails if either formula is missing its own distinguishing ingredient —
  this feature's `anchor|`/`fallback|` tag, or spec 057's issue-number
  segment (guards further, undocumented divergence past what FR-015
  accepts).
- The failure message names FR-015 as the reason the two are required to
  differ, so a future reader who trips this gate is pointed at the
  requirement, not left to guess why sameness is treated as a bug.

**Fixture**: a scratch `board-loop.yml` step whose formula is edited to
match this feature's byte-for-byte, asserted to fail as "converged"; a
scratch step missing the issue-number segment, asserted to fail as
"diverged"; the real two files, post-implementation, asserted to pass.

## `verify-stage-findings-wiring.py` (EXTENDED), FR-013

Gains a second stable substring alongside the existing
`PARAGRAPH_SUBSTRING` ("do not attempt to file it yourself") check: the
clause stating that `gate_or_artifact` must occur verbatim in the named
file and that a value which does not still reaches the board under a
fallback route rather than being dropped. Checked in the same six stage
prompts the FR-003 paragraph is already checked in, using the same
"scans every step's own `with.prompt` field" technique (never a whole-file
substring scan — see that gate's own docstring on why the whole-file form
would go blind to the regression it exists to catch).

**Fixture**: the existing paragraph-without-step / step-without-paragraph
self-test pairs gain a mirrored pair for the new substring; the real six
workflows, post-implementation, asserted to pass.

## Gate 47 (`verify-comment-canonical-pointers.py`) — no code change, new markers

Per research.md D7: `clarify.yml` gains the canonical
`(canonical copy ... do not condense)` marker comment beside its copy of
the anchor-rule sentence, stating the settled rule and citing #569; the
other five stage workflows gain a `-- see clarify.yml` pointer comment
beside their own copy. Gate 47 already validates both halves mechanically
(pointer resolves; vocabulary overlaps; marker is pointed at from
elsewhere) — this is a documentation/comment change the existing gate picks
up for free, not a gate change.

## `.github/scripts/stage-findings-tests/run_fixtures.py` (EXTENDED), FR-010/FR-011

See research.md D8 and `contracts/anchor-verification.md`'s fixture table
for the full list of new `case_*` functions and the one existing case
(`case_fingerprint_ignores_punctuation_case_and_spacing`) amended in place
rather than left asserting the pre-076 rule.
