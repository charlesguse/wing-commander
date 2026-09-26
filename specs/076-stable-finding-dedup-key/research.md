# Research: A Stable Finding Dedup Key

Input: `spec.md` carries no `[NEEDS CLARIFICATION]` markers — the three
clarifications already answered on #569 settle the keying strategy, the
fallback route, and the board-loop split. The decisions below fix the
concrete shapes the tasks stage needs before it can write file-level tasks:
how "occurs verbatim" is actually checked, how the two key shapes stay
unmistakable, and how FR-012/FR-013/FR-015's three gate obligations attach
to gates and comment idioms this repository already has, per CLAUDE.md's
"before pasting ... move it instead" rule and Principle VIII's "extend the
nearest existing gate" precedent (spec 056 research.md D13 is the worked
example this plan follows).

## D1: "Occurs verbatim" is a normalized-substring containment check, not a byte-exact one

**Decision**: The anchor check normalizes both sides with the existing
`norm()` (data-model.md "Fingerprint": lowercase, non-word runs collapsed to
one space, trimmed — unchanged, per the spec's Assumptions) and tests
`norm(gate_or_artifact) in norm(file_text)` as a substring containment,
where `file_text` is the named file's current content in the run's own
checkout. An anchor whose normalized form is the empty string (Edge Cases:
"an anchor containing only characters normalisation removes") is treated as
absent before the containment test ever runs — an empty string is
trivially "contained" in everything, which would make every empty anchor
falsely verify.

**Rationale**: FR-001 requires punctuation/case/spacing differences *within
the copied anchor* to be erased before the key is derived, which the
containment test must honor on both sides or a real copy-paste (e.g. the
agent drops a leading `#` or trailing colon while quoting a heading) would
be rejected as unverifiable even though it is a faithful copy. Requiring
containment of the *normalized* anchor in the *normalized* file text — not
equality against some pre-extracted list of "headings" — keeps the check
generic across the three anchor kinds the spec names (heading, job name,
gate name) without the pipeline maintaining a parser for any of them.

**Alternatives considered**: Extracting structured candidates first (YAML
job-name list for a workflow file, Markdown heading list for a doc) and
checking membership against that list — rejected; it would need a different
extractor per file type and per anchor kind, is exactly the kind of
per-artifact special-casing the "a heading, a job name, a gate name"
phrasing in FR-004 already treats as interchangeable, and gives no more
correctness than a substring test the file's raw text passes just as well
for a job name or a gate name as for a heading.

## D2: The two key shapes carry an explicit, literal discriminator

**Decision**: The hash preimage gains a fixed leading tag naming which shape
produced it:

    with-anchor key = sha256("anchor|<stage>|<norm(file_path)>|<norm(gate_or_artifact)>")
    fallback key     = sha256("fallback|<stage>|<norm(file_path)>")

**Rationale**: FR-002 requires a reviewer to re-derive the key from the
run's recorded inputs and get the same answer; a reviewer re-deriving by
hand must first know *which* formula to run. Segment count alone
(three fields vs. two) already makes collision between the two shapes
impossible, but it forces that reader to count pipe-delimited segments to
tell them apart. A literal tag makes the two shapes self-describing in the
one place a reviewer looks — the preimage string — at the cost of one
constant, and gives the FR-015 gate (D7) an unambiguous substring to check
each formula still contains.

**Alternatives considered**: Leaving the preimage as `<stage>|<norm(path)>`
for the fallback and trusting segment count alone — rejected as strictly
worse for re-derivation with no offsetting simplicity, since the tag is a
one-line change to an already-hand-derived string.

## D3: The anchor check reads the run's own checkout, relative to the working directory

**Decision**: `fingerprint_basis.file_path` is resolved the same way
`evidence.file_paths` already is: relative to the job's working directory
(`GITHUB_WORKSPACE` at runtime; a fixture's `cwd` under the harness). A
`file_path` that does not resolve to a readable file inside that tree —
missing (User Story 3's "a file that should exist and does not"), a
directory, unreadable, or resolving outside the checkout via `..`
segments — makes the anchor unverifiable; the finding takes the FR-007
fallback route. No new composite input is added: the composite already runs
inside the stage's checkout, and this is the same trust boundary
`evidence.file_paths` already crosses (agent-named paths, read but never
executed).

**Rationale**: Every other path the finding carries is already read this
way; inventing a second resolution rule (an absolute root input, a
allow-listed directory) for the anchor alone would be a second convention
where one already exists and is already trusted for the same shape of
input. Path traversal is closed the same inexpensive way FR-016-adjacent
code elsewhere in this composite treats agent-authored strings: as data to
check, never as a resource identifier to trust blindly — a resolved path
that escapes the checkout root is simply unreadable-for-this-purpose, one
more reason the anchor fails verification, not a distinct error path.

**Alternatives considered**: Failing the whole finding (dropping it) when
the file cannot be read — rejected; FR-007 already names "a file that
should exist and does not" as exactly the case the fallback route exists
for, so an unreadable path is routed, never dropped.

## D4: Rejection is recorded as a note; no new run-summary counter

**Decision**: FR-006's "record the rejection with the finding's title and
the reason ... naming the route taken" is satisfied by appending one line
to the existing `notes` list the composite already threads through to the
step summary (the same list `dropped (malformed): ...` and `dropped (cap
exceeded): ...` lines already populate), phrased to name the anchor value,
the file it was checked against, and that the finding was keyed via the
FR-007 fallback rather than dropped. No new field is added to the run
summary's `filed`/`appended`/`dropped_*` counters.

**Rationale**: The spec's Assumptions section states the run summary is
"unchanged except where FR-008 and FR-009 name a change," and neither
requirement is FR-006 or FR-007 — an anchor that fails verification is not
a drop (the finding still reaches the board under FR-007), so it must not
be counted alongside `dropped_malformed`/`dropped_cap`/`dropped_api_failure`,
each of which already means "this finding did not reach the board." Adding
a fourth counter for a case that is not a drop would misrepresent what SC-004
promises the existing three already cover accurately.

**Alternatives considered**: A new `anchor_rejected` counter distinct from
the drop counters — rejected as an unrequested widening of a summary
contract the spec explicitly scopes to unchanged-except-FR-008/FR-009; the
`notes` line already carries the same information a maintainer would use it
for, without a new field every future reader of the summary must learn.

## D5: FR-012's doc-vs-code gate extracts the shipped formula and compares literals, not prose

**Decision**: A new gate script (`verify-dedup-key-canonical-rule.py`, in
the family of `verify-single-home-idioms.py` and
`verify-metrics-summary-record-emission.py`, both of which already extract
a SHIPPED `run:` block by step name via the same `find_step` helper the
fixture harness uses rather than re-deriving it) reads
`specs/056-stage-found-defect-filing/data-model.md`'s "Fingerprint" section,
extracts its fenced formula block by a fixed marker, and asserts each
literal ingredient it names — the `norm()` regex, the `anchor|` and
`fallback|` tags (D2), and the pipe-delimited field order — appears
verbatim in the extracted "Extract, validate, cap, and prepare findings"
step of `wing-commander-stage-findings/action.yml`. A changed formula on
either side with no matching edit on the other fails, naming which literal
went missing and from which side.

**Rationale**: This is the same shape as D13's existing `check_stage_findings`
(co-occurrence of a distinguishing fragment, scanned mechanically) turned
around: instead of scanning for a stray *second* copy of the idiom
elsewhere, it scans for the *declared* copy (the doc's fenced block) staying
byte-consistent with the *shipped* copy (the action's code), which is
exactly what FR-012 asks for and what CLAUDE.md's "extend the nearest
existing gate" line asks for over inventing a fourth gate family. Extracting
the doc's formula from a fenced block (rather than parsing prose) keeps the
check mechanical: the same reason data-model.md already states the formula
as a fenced pseudocode line rather than a sentence.

**Alternatives considered**: Re-running the shipped code against a fixture
and asserting its *output* matches a value the gate computes independently
from the doc — rejected; the doc states a formula, not a table of
input/output pairs, so "independently computed from the doc" would require
the gate to parse the fenced pseudocode into an executable form, which is
more machinery than a literal-substring comparison for the same guarantee.

## D6: FR-015's split-must-stay-deliberate gate lives in the same new script

**Decision**: The same gate script adds a second check,
`check_composition_split`: it extracts both fingerprint formulas — this
feature's (D2, tagged `anchor|`/`fallback|`) from
`wing-commander-stage-findings/action.yml`, and spec 057's own
(`sha256("<issue>|<norm(title)>|<norm(file_path)>")`) from
`board-loop.yml`'s "Prepare out-of-scope findings for filing" step — and
fails if the two formula strings are textually identical (guards silent
convergence) or if either one's known distinguishing ingredient (the
`anchor|`/`fallback|` tag for this feature's; the issue-number segment for
spec 057's) is missing from its own extracted step (guards further,
undocumented divergence past what this spec already accepts). The failure
message names FR-015 as the reason the two are allowed, and required, to
keep differing.

**Rationale**: FR-015 asks for one gate that holds a *difference* in place,
which is the mirror image of every other entry in `DECLARED_HOMES`, all of
which hold a single copy in place. Bundling it into the new FR-012 script
rather than opening a fifth gate file keeps "two-consumer key composition
questions" in one place a reviewer of either spec 076 or spec 057 would
think to check.

**Alternatives considered**: Adding this check to `verify-single-home-idioms.py`
itself — rejected; that script's whole shape is "assert a declared home has
no second copy," and this check's assertion is the opposite polarity ("two
declared, independent things must NOT become one"), which reads as a
different gate wearing the same script even though it shares an extraction
helper.

## D7: FR-013's sentence stays duplicated in every prompt; the canonical-comment discipline attaches to the comment beside it, not the prompt text itself

**Decision**: The agent-facing sentence describing the anchor rule cannot be
replaced by a `-- see clarify.yml` pointer in five of the six prompts,
because the agent reads its own workflow's prompt only — it never reads
`clarify.yml`. What moves under CLAUDE.md's canonical-comment discipline is
the *rationale comment* that sits beside each copy, matching Gate 47's
existing marker/pointer mechanics exactly: `clarify.yml` carries the
canonical `#` comment stating the settled rule and citing #569
(`(canonical copy ... do not condense)`), and the other five workflows carry
a `-- see clarify.yml` pointer comment next to their own copy of the
sentence. Gate 47 (`verify-comment-canonical-pointers.py`) needs no code
change — it already resolves pointers and checks vocabulary overlap against
whatever file the marker lives in.

Byte-for-byte presence of the *sentence itself* (which the comment
mechanism cannot enforce, since it deliberately does not touch prompt text)
is instead covered the way FR-003's paragraph already is:
`verify-stage-findings-wiring.py` gains a second stable substring — the
clause naming that the value must occur verbatim and that a value which
does not still reaches the board under a fallback route, distinct from the
existing `gate_or_artifact` key-name check `check_prompt_names_keys`
already performs — required in the same six prompts the FR-003 paragraph
substring is required in.

**Rationale**: The prompt text and the explanatory comment are two
different kinds of duplication with two different mechanisms already built
for them: `verify-stage-findings-wiring.py`'s stable-substring check is this
repository's existing answer for "the same agent-facing instruction must be
present in N prompts" (FR-003's own paragraph proves the pattern), and Gate
47 is its existing answer for "the same *rationale* must not be explained
five independent ways." Reusing both is cheaper and more consistent than
inventing a mechanism that tries to make prompt strings themselves
byte-identical across six files whose surrounding prompt structure already
differs per stage.

**Alternatives considered**: A gate asserting the six copies of the
sentence are byte-identical — rejected; nothing in this repository's
existing prompt-paragraph precedent (FR-003's own paragraph, checked only
by stable-substring presence, not exact-copy) requires that stronger
guarantee, and manufacturing it for this one sentence alone would be an
inconsistent level of rigor next to the paragraph it sits beside.

## D8: Fixture additions extend the existing harness; no new fixture mechanism

**Decision**: FR-010/FR-011's fixtures are new `case_*` functions in
`.github/scripts/stage-findings-tests/run_fixtures.py`, alongside the
existing `case_fingerprint_ignores_punctuation_case_and_spacing` (which
proved the *old*, unanchored rule and is amended in place — see below —
rather than left to assert behaviour this feature replaces):

- a pair whose anchors are typed with different punctuation/case/spacing
  but both are verbatim-verifiable substrings of one fixture file's content
  the harness writes to a temp path, alongside differing titles and `what`
  text, asserting one key (FR-010's first case);
- a pair naming two genuinely different, both-verifiable anchors in that
  same fixture file, asserting two keys (FR-010's second case);
- a finding whose anchor does not occur in the named file at all, asserting
  the FR-007 fallback key, and a second such finding in the same file
  sharing that fallback key (FR-011);
- a fallback-keyed finding and an anchored finding in the same file
  asserting distinct keys from each other (FR-011's "does not collide"
  case, and the spec's Edge Cases entry on the anchored/unanchored split).

The amendment to `case_fingerprint_ignores_punctuation_case_and_spacing`:
its current third assertion ("a different word gives a different
fingerprint") exercised exactly the failure this spec fixes — an
unverified `gate_or_artifact` moving the key on wording alone — and must
become, under the new rule, either an anchor that fails verification
(routing to the fallback key, not a third distinct anchored key) or is
folded into the new pairs above; it is not deleted silently, since SC-002
requires the harness to keep proving both the same-key and different-key
directions.

**Rationale**: The harness already drives the shipped `run:` block directly
(no live `gh`, no agent) via `wc_shell_harness`, and already creates
scratch temp directories for its dedup-lookup fixtures — writing one more
fixture file for the anchor check to read against is the same technique,
not a new one. Keeping the amendment to the existing case explicit (rather
than a silent deletion) is what SC-002 and Principle VIII's "every shipped
failure branch has a checked-in fixture" together require: the old
assertion described a branch this feature removes, and its replacement must
describe the branch that takes its place, not vanish from the suite.

## D9: No migration; the compatibility note lands in spec 056's data-model.md, not a new artifact

**Decision**: FR-014's consequence (issues filed under the pre-076 key
rule no longer match) is recorded as a short dated note in
`specs/056-stage-found-defect-filing/data-model.md`'s "Fingerprint" section
— the same canonical home D5's gate reads — rather than a new file or a
second copy of the same sentence in spec 076's own artifacts. No code
change implements a migration; this decision is purely "where does the
sentence live," settling it before the tasks stage would otherwise have to
choose between spec 076's and spec 056's directories for a one-paragraph
compatibility note.

**Rationale**: Spec 056's data-model.md is already the rule's one home
(FR-012); a compatibility consequence of changing that rule is part of the
rule's own history, not a separate fact spec 076 owns going forward.
