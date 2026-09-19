# Contract: FR-010 through FR-016, FR-023, FR-025, FR-026 — Gate 60 and its waiver file

`research.md` D7/D8/D9 explain the detection strategy per idiom, the
waiver-file reuse, and the promotion-prevention scan. This is the one
genuinely new gate script this feature adds — modeled directly on
`verify-metrics-summary-record-emission.py` (literal-fragment scan) and
`verify-stage-invariants.py` (waiver loading/stale-checking), both already
reviewed and merged.

## `.github/scripts/verify-single-home-idioms.py` (NEW — Gate 60)

**What it scans**: every `.github/workflows/*.yml` and everything under
`.github/actions/**` (FR-010's stated subject — "whether or not the
copying site is one of the two known consumers").

**Four checks, each excluding its own declared home**:

1. **Orphan-reset** — co-occurrence, in one file, of `checkout --quiet
   --orphan`, `git rm -rq --cached`, and the `find . -mindepth 1 -maxdepth
   1 ! -name .git -exec rm -rf` clause. Declared home:
   `_shared/orphan-branch-reset/action.yml`.
2. **Durable-failure-issue** — co-occurrence, in one file, of a `gh label
   create ... --force` call and a `gh issue list ... --label "..."
   --state open --json number --jq '.[0].number // empty'`-shaped lookup.
   Declared home: `_shared/durable-failure-issue/action.yml`.
3. **Verdict-shape** — a `jq` program whose text contains all six of
   `outcome`, `verified_head`, `failing_check`, `expected`, `observed`,
   `evidence_url`. Declared home: `_shared/auto-release-verdict.sh`.
4. **Token-mint** — YAML-parsed (never grepped, matching Gate 51's own
   stated rationale for parsing over grepping): a job containing both (a)
   a step with `continue-on-error: true` and `uses:` matching
   `actions/create-github-app-token@*`, and (b) a later step in the same
   job whose `if:`/`env:`/`run:` references that step's `.outcome` output.
   Declared home: `_shared/scoped-app-token/action.yml`.

Each check's failure message: `::error file=<path>::verify-single-home-idioms: <file>:<line>: <detail> -- see .github/actions/_shared/<home>` — naming both the offending site and the shared definition (FR-011).

**Promotion-prevention pass (FR-025)**: using `wc_published_stages.py`'s
existing discovery (the same helper Gate 31/48 already use), scan every
`workflow_call`-only stage workflow and every `.github/actions/<name>`
whose `<name>` does not start with `_` for a `uses:` or sourced-script
reference resolving to `_shared/` (either
`./.wing-commander-pipeline/.github/actions/_shared/...` or
`./.github/actions/_shared/...`). Any hit fails, naming the resolving site
and the internal path it reached.

**Waiver file — `.github/scripts/single-home-waivers.json`** (FR-026):
schema identical to `stage-invariant-waivers.json`
(`{file, check, pattern, count, issue, reason}` per entry, `check` one of
`token-mint`/`orphan-reset`/`failure-issue`/`verdict-shape`/`promotion`).
Loaded and stale-checked exactly like Gate 31's waivers (a waiver matching
zero findings fails; a waiver whose match count differs from its declared
`count` fails) — reusing `verify-stage-invariants.py`'s
`load_waivers`/`check_waiver_shape`/`apply_waivers` shape rather than
re-deriving it. A reason expressed only as a code comment does not
suppress a finding — only an entry in this file does (FR-026).

**Fail-loud on no subject (FR-014)**: zero `.github/workflows/*.yml` files
discovered, or none of the four declared-home paths existing on disk, is
a hard failure (`::error::` + non-zero exit), never a silent 0-findings
pass — matching constitution VIII's "a gate that cannot reach its subject
... MUST fail loudly."

**Self-test** (`--self-test` flag, Gate 47's synthetic-tempdir style,
since the real call sites cannot be mutated in place to prove detection):
one synthetic fixture per check proving (a) a clean tree with only the
declared home passes, (b) a second copy of the idiom anywhere — including
a name that is neither `auto-release.yml` nor `auto-update-spec-kit.yml` —
fails and names both sites (FR-023's explicit "not merely an assertion
that the two known consumers call the shared definitions" bar), (c) a
waived copy passes, (d) a stale waiver (matching zero, or a different
count than declared) fails, (e) a `workflow_call` stage or non-underscore
composite resolving `_shared/` fails the promotion check.

## Wiring (FR-012, FR-013, FR-016)

Added to `lint-workflows.yml`'s existing sequential gate job as "Gate 60 —
each of the three cross-workflow idioms and the fail-infra verdict shape
has exactly one home, and no published surface resolves an internal
helper," `if: "!cancelled()"` (not suppressible by an unrelated gate
sharing the job, per constitution VIII), plus a second "Gate 60 self-test"
step running `--self-test`. `run-local-gates.py` picks both up automatically
via its existing derivation from `lint-workflows.yml` (no separate
registration needed — see research.md D7's registry note). The job's
trigger paths already include `.github/workflows/**` and
`.github/actions/**` (confirmed: this is the same job every other gate in
the 3000+-line `lint-workflows.yml` already runs in, so FR-013's "the gate
MUST be triggered by changes to the workflows, shared definitions, and
waiver file it checks" is satisfied by the existing job trigger plus
adding `.github/scripts/single-home-waivers.json` to the workflow's path
filter if that filter is scoped narrower than `.github/**` — checked at
implementation time against the actual current trigger list).

## Gate 10 interaction

Gate 10 (`wc_gate_registry.py`'s convention check) requires
`verify-single-home-idioms.py` be invoked by a workflow step in the same
PR that adds it, matching every other `verify-*.py` script's obligation —
no special-casing needed.
