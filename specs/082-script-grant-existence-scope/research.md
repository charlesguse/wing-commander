# Research: Every Granted Script Is Checked, Not Just The `.specify` Ones At Composite Call Sites

Each decision below resolves one design question the spec (#599) left to the
plan stage. spec.md carried no `[NEEDS CLARIFICATION]` markers — the three
decisions the lifecycle issue reserved for the owner (FR-003, FR-004, FR-006)
are already answered in spec.md's Clarifications section — so every decision
here is a planning decision turning the spec's FRs into a shape tasks.md can
execute, not a clarification-driven one.

## D0 — Refreshed inventory (spec.md's "Inventory freshness" instruction)

**Decision**: The spec's own Overview inventory was taken before PR #613
renamed `board_git_read.py` → `git_read.py` and added grants rooted at the
run-time-checked-out `.wing-commander-pipeline/` path. Re-deriving it against
`main` as of 2026-09-26 (`grep -n 'Bash([^)]*/[^)]*)' .github/workflows/*.yml`,
cross-checked file by file) finds:

**Composite call sites (`wing-commander-tool-args`), granting a path outside
`.specify/scripts/bash/`:**

| Workflow | step-label | Granted path (after prefix-stripping) | Disposition |
|---|---|---|---|
| board-loop.yml:969 | `board-loop.triage-propose` | `.github/scripts/git_read.py` | resolves |
| board-loop.yml:1306 | `board-loop.route-propose` | `.github/scripts/git_read.py` | resolves |
| board-loop.yml:2366 | `board-loop.reviewer` | `${{ runner.temp }}/wc-pristine/scripts/git_read.py` | **skip** — unexpanded expression (FR-008) |
| implement.yml:833 | `implement.cycle` | `.github/scripts/run-local-gates.py` | resolves |
| implement.yml:1401 | `implement.retry` | `.github/scripts/run-local-gates.py` | resolves |
| implement.yml:2043 | `implement.post-progress-comment` | `.wing-commander-pipeline/.github/scripts/git_read.py` | **waiver** |
| pr-conversation.yml:813 | `pr-conversation.classify` | `.wing-commander-pipeline/.github/scripts/git_read.py` | **waiver** (same path) |
| watchdog.yml:2267 | `watchdog.diagnose` | `.wing-commander-pipeline/.github/scripts/git_read.py` | **waiver** (same path) |

**Reusable-workflow caller `extra-allowed-tools`/`allowed-tools-override`:**

| Workflow | Job | Granted path(s) | Disposition |
|---|---|---|---|
| wing-commander-5-implement.yml:96 | `implement` | `.github/scripts/run-local-gates.py`, `.github/scripts/auto-update-spec-kit-tests/run-tests.sh` | both resolve |

**Bare `claude_args --allowedTools` on a `claude-code-action` step:**

| Workflow | Job / step | Granted path(s) | Disposition |
|---|---|---|---|
| auto-update-spec-kit.yml:1105 | `evaluate-path` / "Decide upgrade path" | `.wing-commander-pipeline/.github/scripts/git_read.py` | **waiver** (same path as above) |
| auto-update-spec-kit.yml:2049 | `prepare` / "Run e2e agent-driven stage" | `e2e-scratch/.specify/scripts/bash/create-new-feature.sh` (2 spellings) | **waiver** |

Counted by script name, the way the spec's own SC-002 counts them: **7**
`git_read.py` occurrences (2 resolve, 4 share one waiver entry, 1 is skipped
as an expression), **3** `run-local-gates.py` occurrences (all resolve,
unchanged from the spec's filed count), **1** `run-tests.sh` occurrence
(resolves, unchanged), **2** spellings of `create-new-feature.sh` (share one
waiver entry, unchanged) — **13** grant occurrences total across the widened
scope, needing exactly **2** waiver entries. `.specify/scripts/bash/*` grants
at composite sites (the already-checked case) are unaffected and are not
re-listed here. No grant was found at `allowed-tools-override` (unused for a
script path anywhere today) or at any surface this spec's Assumptions
declare out of scope.

**Rationale**: The spec explicitly instructs "the plan stage MUST re-derive
[the inventory] against `main` as of planning day, and the counts in SC-002
follow that refreshed inventory rather than the numbers written here." The
table above is that re-derivation; SC-002's numbers in the shipped docstring
and issue comment follow it, not the spec's illustrative filing-time numbers.

**Alternatives considered**: Using the spec's filed numbers verbatim —
rejected, the spec itself forbids this ("the inventory is illustrative... not
a work list").

## D1 — Generalizing the path/token classifier (FR-001/FR-002/FR-003)

**Decision**: Replace `SCRIPT_GRANT`'s hardcoded
`\.specify/scripts/bash/[^:\s)]+` capture with a two-stage classifier:

1. A regex extracts the first whitespace/colon/paren-delimited token inside
   `Bash(...)`, after an optional interpreter prefix consisting of one of
   `bash`, `sh`, `python`, `python3`, followed by zero or more `-flag` tokens
   (so `python3 -I <path>` and a bare `<path>` both yield the same captured
   token) — this generalizes the two spellings `SCRIPT_GRANT` already had
   (bare, `bash `) to the four the repository ships (`bash `, `sh `, `./`,
   `python `/`python3 ` with an optional flag), per FR-002.
2. A pure function classifies the captured token: it is a **path** if it
   starts with `./` (stripped once to form the repository-relative path) or
   contains a `/` anywhere (used as-is, already repository-relative); it is a
   **bare command** otherwise (`jq`, `git status`, `yamllint`) and raises
   nothing (FR-003). Neither a file extension nor a directory allow-list
   participates in the test, so a path in a directory the check has never
   seen before (`e2e-scratch/...`, `.wing-commander-pipeline/...`) is still
   classified as a path and resolved or waived — never silently ignored for
   living outside `.specify/scripts/bash/`.

**Rationale**: FR-001 requires dropping the hardcoded prefix outright; FR-003
states the path/bare-command test in exactly these terms ("a leading `./` or
contains a `/`... the leading `./` is then stripped again"), so the function
is a direct transcription of the requirement rather than a new design.
Splitting "extract the token" (regex) from "classify the token" (pure
function) keeps the regex simple (no path-shape knowledge inside it) and
keeps the classification testable independent of parsing — a smaller surface
for the self-test's bare-command and expression-valued mutations (D9) to
target directly.

**Alternatives considered**: Widening the regex to capture the path
inline (folding classification into the regex, e.g. requiring a `/` in the
capture group) — rejected because it cannot express "leading `./` alone with
no other `/`" as a path (`./foo.sh`) without either a second alternation or a
lookahead, and because Constitution IX prefers judgment in a plain function a
reviewer can step through over judgment folded into a regex's structure.

## D2 — The three grant surfaces (FR-004) and a shared workflow loader

**Decision**: One shared loader, `_load_workflows(root)` → `({path: doc},
[error, ...])`, replaces the glob-and-`yaml.safe_load` block `collect_sites`
already has inline; it wraps the YAML parse in `try`/`except
yaml.YAMLError`, appending a failure naming the file rather than raising
(D7), and is the single place all three collectors below read workflow YAML
from — consistent with this repository's "shared logic has exactly one home"
rule (CLAUDE.md), since the three collectors would otherwise triple the same
glob-and-parse block.

Three collectors read that shared map, one per surface FR-004 names:

1. **Composite** (existing, unchanged mechanism): `collect_sites` — a step
   whose `uses` contains `wing-commander-tool-args`, keyed by `step-label`.
2. **Reusable-workflow caller** (new): for every job whose `uses` starts with
   `./.github/workflows/` (a local reusable-workflow call, as opposed to a
   composite action under `.github/actions/`), read `with.extra-allowed-tools`
   and `with.allowed-tools-override` if present. Site identity: workflow file
   + job name (see D3 — this surface has no step, since a reusable-workflow-
   call job has no `steps:` list of its own).
3. **Bare `claude_args`** (new): for every step whose `uses` contains
   `claude-code-action`, read `with.claude_args` if present and extract the
   `--allowedTools "..."` value with a regex tolerant of either quote
   character (`--allowedTools\s+"([^"]*)"` tried first, `'([^']*)'` second).
   Site identity: workflow file + job name + step `name` (falling back to
   `id`, then to the step's index, if `name` is absent).

A `Bash(<path>)` grant written anywhere else under `.github/workflows/` (a
raw `run:` step's own shell, a job-level `env:`, etc.) is explicitly out of
scope per FR-004's closing sentence and is not collected by any of the three.

**Rationale**: FR-004 names exactly these three surfaces and no more; D0's
refreshed inventory confirms these are the only three the repository actually
uses today (no grant appears anywhere else). The shared loader is not
required by any FR directly, but Constitution VIII requires each gate to be
reachable and correct, and tripling a glob+parse block is exactly the kind of
duplication CLAUDE.md's "shared logic has exactly one home" section calls out
by name — consolidating it here, while touching this code anyway, is cheaper
than leaving three copies for a future editor to keep in sync.

**Alternatives considered**: A fourth, generic "grep every `Bash(...)`
literal anywhere in a workflow file" collector — rejected outright by FR-004's
own text ("not `every Bash(<path>)` anywhere under `.github/workflows/`");
it would also flag `Bash(...)` literals inside comments and prose, which the
existing YAML-structured collectors never see in the first place.

## D3 — Identifying a non-composite grant in a failure message (FR-005)

**Decision**: The failure message for a composite-site grant is unchanged
(names the `step-label`). For the two new surfaces:

- Reusable-workflow caller: `"<workflow file>:<job> (<input-name>)"` — e.g.
  `wing-commander-5-implement.yml:implement (extra-allowed-tools)`. There is
  no third "step" component for this surface, because the grant is a
  `with:` value on the job that calls the reusable workflow, not on a step
  inside it — a reusable-workflow-call job has no `steps:` list at all. FR-005
  says "workflow file, job and step" because it is describing both new
  surfaces at once; where a surface has no step, the message names the two
  components that exist and the input key that carries the grant, so the site
  is still uniquely identifiable from the message alone.
- Bare `claude_args`: `"<workflow file>:<job>:<step name>"` — e.g.
  `auto-update-spec-kit.yml:evaluate-path:"Decide upgrade path"`. All three
  components exist for this surface and are all included.

**Rationale**: FR-005's requirement is "identify the grant" without a
`step-label` — the goal is that a maintainer reading the failure can find the
exact YAML to fix without grepping. Workflow file + job (+ step where one
exists) is the minimum that is always unique in this repository (job names
are unique per workflow file; `claude-code-action` step names are unique per
job in every current file). Including the specific input name
(`extra-allowed-tools` vs. `allowed-tools-override`) for surface 2 costs
nothing and removes any ambiguity when a job someday sets both.

**Alternatives considered**: Inventing a synthetic label for surfaces 2/3
(e.g. `"wing-commander-5-implement.implement"`, mimicking the composite's
`stage.step` convention) — rejected: it implies a join key into
`stage-interfaces.md`'s table that does not exist for these surfaces (per the
spec's Assumptions, that table is not growing rows for them), so a synthetic
label would look like a table key without being one.

## D4 — The waiver file (FR-006/FR-007)

**Decision**: New file `.github/scripts/script-grant-waivers.json`, structured
as a `$comment` block (repository convention, see `single-home-waivers.json`)
plus a `"waivers"` list of objects `{"path": "<exact granted, already-
prefix-stripped path>", "issue": "#NNN", "reason": "<why this path cannot
exist in the checkout>"}`. No `pattern`, `glob`, or `count` field — FR-006
explicitly rules those out ("a prefix pattern, glob or in-script constant
MUST NOT stand in for an entry"), which is why this file's schema is *not*
copied from `single-home-waivers.json`/`stage-invariant-waivers.json` (both
pattern+count-shaped) even though it lives beside them.

The check loads the file once per run, builds a `{path: entry}` map, and:

- when a grant's classified path is not found on disk, checks the waiver map
  before reporting a failure — a hit is silently accepted (no failure, no
  separate "pass" line, matching the existing check's behavior for a
  resolved script);
- separately, for every entry in the waiver map, checks whether the path
  *does* resolve on disk — a hit here is FR-007's staleness failure ("waiver
  for `<path>` (#<issue>) no longer applies: the path now exists in the
  working tree — drop the entry or the reason has gone stale").

Per D0, this file ships with exactly two entries:
`.wing-commander-pipeline/.github/scripts/git_read.py` (#599, or the
originating pipeline-checkout spec — the pipeline's own run-time-checked-out
copy of itself, never committed) and
`e2e-scratch/.specify/scripts/bash/create-new-feature.sh` (#436, the
run-time-provisioned e2e scratch directory the spec's Overview already
names).

**Rationale**: FR-006 is explicit about the schema shape (exact paths, one
file, no pattern/glob/constant substitute) and FR-007 is explicit about the
staleness direction (a waiver that now resolves is itself a failure) — both
are transcribed directly into the check's behavior above. Loading once per
run and building a map (rather than scanning the list per grant) keeps the
lookup O(1) per grant, consistent with FR-011's existing memoization
discipline.

**Alternatives considered**: One waiver entry per *site* rather than per
*path* (e.g. four entries for `.wing-commander-pipeline/.github/scripts/git_read.py`,
one per composite/claude_args site that grants it) — rejected: FR-006 says
"each entry names the exact granted path," not the site, and a per-site
waiver would need updating every time a new call site adopted the same
already-recorded, already-understood absence — the exact kind of debt a
single canonical record (CLAUDE.md's "shared logic has exactly one home")
argues against.

## D5 — Skipping an expression-valued grant (FR-008)

**Decision**: Before attempting to match a comma-split tool string against
the `Bash(...)` token-extraction regex, check whether the raw string contains
`${{`. If it does, skip it outright — no token extraction, no path
classification, no failure, and no "resolved" tally entry. This one check
covers every shape the repository has: a whole-value passthrough
(`extra-allowed-tools: ${{ inputs.extra-allowed-tools }}`, which is not even
wrapped in `Bash(...)`), a `Bash(...)` grant whose *path* embeds an
expression (`Bash(python3 -I ${{ runner.temp }}/wc-pristine/scripts/git_read.py:*)`,
D0's board-loop.reviewer case), and a `--allowedTools` value that is itself
`${{ steps.<id>.outputs.allowed-tools }}` (every composite-fed
`claude_args` in the repository today) — the last of these is already
covered independently by the composite surface, so skipping it here at the
`claude_args` surface avoids double-reporting the same underlying grant,
not just avoiding a false failure.

**Rationale**: FR-008 requires exactly this — skip, don't fail, and don't
count the skip as a verified pass. Checking the raw string before regex
extraction (rather than checking the extracted token) is what makes the
board-loop.reviewer case work at all: `${{ runner.temp }}` contains a space,
so the token-extraction regex would either fail to match (silently, which
already produces the right "no failure" outcome by accident) or capture only
`${{` (wrong, if the regex were written more permissively). Checking the raw
string first makes the skip explicit and correct regardless of how the
extraction regex is shaped, rather than relying on an accidental non-match.

**Alternatives considered**: Only skipping when the *whole* grant value is an
expression (treating an embedded expression like `${{ runner.temp }}/...` as
a resolution failure since "most of it is a literal path") — rejected: the
literal text after substitution is exactly what the spec's edge cases say is
"not a repository-relative path" until a runner actually expands it, and
Gate 27 has no access to that expansion; failing it would be a false
positive on a grant that may be entirely correct at run time.

## D6 — Malformed workflow handling (FR-009)

**Decision**: `_load_workflows` (D2) catches `yaml.YAMLError` per file,
appends `"<file> could not be parsed as YAML: <error>"` to its error list,
and continues to the next file rather than propagating the exception. Every
collector receives only the successfully-parsed subset of the map; the
accumulated parse errors are added to `run()`'s returned failure list the
same way `collect_sites`' existing `errors` already are.

**Rationale**: Today, an unparseable workflow crashes the whole script with
an uncaught `yaml.YAMLError` — loud, but not "reported as a failure" in the
gate's own vocabulary (no `::error::Gate 27: ...`-prefixed line, and every
*other* file's checks never run because the crash happens before `run()`
returns anything). FR-009 requires a reported failure, not a crash that
happens to also be non-zero-exit; catching per file also means one malformed
workflow does not hide every other file's real findings behind a stack trace.

**Alternatives considered**: Leaving the uncaught exception as-is on the
theory that a non-zero exit code already satisfies "not skipped silently" —
rejected: FR-009 says "reported as a failure," and this gate's own failure
vocabulary is a list of `::error::`-prefixed strings other checks already
use; a Python traceback is not that, and it aborts before the other N-1
files are even attempted.

## D7 — Memoization and one-failure-per-pair (FR-011)

**Decision**: The existing `exists` memoization dict in `check_script_grants`
is kept and reused across all three surfaces — one cache, keyed by the
resolved repository-relative path, shared by composite-site lookups,
reusable-workflow-caller lookups, and `claude_args` lookups alike, since the
underlying filesystem check (`_script_exists`) is identical regardless of
which surface produced the path. The failure list itself is still built by
iterating `(site, tool)` pairs once each (no site produces the same tool
string twice, since `collect_sites`/the two new collectors each visit a given
YAML location once), so "one failure per distinct (grant site, path) pair"
falls out of not iterating any site twice, with no separate dedup set needed.

**Rationale**: FR-011 is already how the existing code behaves for the one
surface it covers today; widening the surfaces without widening the
memoization key space would mean the same script granted at both a composite
site and a `claude_args` site (D0's `.wing-commander-pipeline/.github/scripts/git_read.py`,
which appears at four distinct sites in four different ways) triggers four
separate `os.listdir` calls instead of one — exactly the repeated lookup
FR-011 and the existing code comment ("the directory listing behind
`_script_exists` isn't free to repeat") already guard against.

**Alternatives considered**: A per-surface cache (three dicts instead of one)
— rejected as strictly worse for no benefit: the four sites sharing
`.wing-commander-pipeline/.github/scripts/git_read.py` span two different
surfaces (composite and `claude_args`), so a per-surface cache would still
repeat the lookup across surfaces.

## D8 — Docstring and scope-statement update (FR-013)

**Decision**: The module docstring's "WHAT IT CHECKS" bullet 3 and the
"Scoped to `.specify/scripts/bash/` only... is not this check's job yet"
sentence in "WHAT IT DOES NOT CHECK" are rewritten to state the new scope in
the same terms: every `Bash(<path>)` grant found at any of the three named
surfaces (composite, reusable-workflow caller, bare `claude_args`), for any
token classified as a path per D1, resolves against the tree or carries a
waiver entry — with the same case-sensitivity guarantee, the same
"a fourth surface is a new finding, not a gap this check silently covers"
boundary FR-004 draws, and a pointer to the new waiver file. The exact
replacement prose is fixed in contracts/gate-27-extension.md so tasks.md
edits the docstring verbatim rather than re-deriving wording.

**Rationale**: FR-013 requires the reader be able to tell in-scope from
out-of-scope "without reading the regex" — the same standard the existing
docstring already tried to meet for the narrower scope, so the fix is a
faithful widening of the same sentences, not a rewrite in a new voice.

## D9 — Self-test additions (FR-012/SC-004)

**Decision**: Six new mutation-style assertions are added to `self_test()`,
matching FR-012's own enumeration exactly:

1. A composite-site grant for a non-`.specify` script that does not exist
   (e.g. a synthetic `.github/scripts/zzz-does-not-exist.py`, following the
   existing ghost-script naming convention) → one failure naming the site and
   the path.
2. A synthetic reusable-workflow-caller fixture (a temp-directory workflow,
   following `_write_fixture`'s existing pattern) whose `extra-allowed-tools`
   grants a missing script → one failure naming the workflow file and job.
3. A synthetic `claude-code-action` fixture whose `claude_args`
   `--allowedTools` grants a missing script → one failure naming the workflow
   file, job, and step.
4. A bare-command grant (`Bash(jq:*)`) at any surface → asserted to raise
   nothing.
5. An expression-valued grant (`Bash(python3 -I ${{ runner.temp }}/x.py:*)`)
   → asserted to raise nothing (distinct from case 4: this one has a `/` and
   would be misclassified as a resolvable path if D5's raw-string check were
   ever removed, so the mutation targets that specific regression).
6. A waiver entry for a path that resolves in a temp fixture tree → asserted
   to produce the FR-007 staleness failure.

Plus the existing baseline assertion ("the real repository should be clean")
is re-run against the widened check, now covering all three surfaces and
both real waiver entries — proving D0's "13 occurrences, 2 waivers, repo
green" claim mechanically rather than only in this document's prose.

**Rationale**: FR-012 names these six cases verbatim as what the self-test
"MUST prove"; Constitution VIII requires every shipped failure branch to have
a checked-in fixture, and the existing `self_test()`/`_mutations()`/
`_collector_fixtures()` structure is exactly where each of the six belongs,
following the file's own established pattern (a synthetic, never-real
fixture name for cases that must never start passing by accident, a
`tempfile.mkdtemp()` fixture tree for cases needing a real filesystem, per
the existing case-mismatch mutation).

**Alternatives considered**: Testing surfaces 2/3 only against the real
repository's own two live sites (`wing-commander-5-implement.yml`,
`auto-update-spec-kit.yml`) rather than synthetic fixtures — rejected: those
sites are already correct (D0), so a mutation against them would need to
temporarily corrupt real workflow content in memory the way the composite
ghost-grant mutation already does for `plan.direct-commit`; doing so is
viable and arguably simpler than a `tempfile` fixture, and tasks.md may
choose either implementation as long as the mutation exercises the collector
code path, not just the classifier — the fixture-vs.-in-memory-mutation
choice is left to tasks.md as an implementation detail with no behavioral
difference, since both approaches produce the identical assertion (one
failure naming the right site).
