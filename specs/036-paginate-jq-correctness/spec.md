# Feature Specification: Multi-Page `gh api` Reads Return What They Claim, and a Gate Keeps Them That Way

**Feature Branch**: `036-paginate-jq-correctness`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "`gh api --paginate --jq '<filter producing an array>'` is unparseable past the first page, and three call sites outside spec 033 still use that shape. `gh` applies `--jq` to **each page separately** and concatenates the results. So `--paginate --jq '[.[] | ...]'` emits `[...]\n[...]` — one array *per page* — not one array. Anything that then parses the whole string as a single JSON value fails. This was found and fixed for `pr-conversation.yml`'s six call sites under spec 033 T067 (`specs/033-pr-conversation-commands/tasks.md`). T067 asked for the adjacent sites to be checked and filed separately if the same class held. It does, in two files. Sites that hold — 1. `watchdog.yml:743` — annotations collector: an array endpoint with no `--jq`, so `gh` concatenates raw arrays: `[...][...]`. `jq -c '[ .[]? | ... ]'` over two inputs emits **two** arrays, so `--argjson f` gets invalid JSON and fails. The step runs under `set -uo pipefail` (no `-e`), so it does not abort — `entries` silently collapses to empty and the final `jq --argjson new \"$entries\"` fails too, leaving `signals.json` un-updated. Annotation evidence is **silently dropped** rather than reported as a failure. Bites once a job has more than one page (30) of annotations. Worth noting alongside the existing observation that `watchdog.yml` soft-fails these reads in ~35 places (`2>/dev/null || echo '[]'`), so a real failure there is already indistinguishable from 'there was no evidence to collect'. 2 & 3. `auto-update-spec-kit.yml:391` and `:799` — release detection: same shape: concatenated arrays, so `jq` emits one result per page and `latest` becomes two JSON objects on two lines; `jq -r '.tag_name'` then yields two tag names. `github/spec-kit` is already near the 30-release page boundary, so this is not hypothetical for long. Sites checked and found safe: `intake.yml:399` — `--jq '.[]'` piped through `jq -s '.'`. This is the correct form. `lint-workflows.yml:1176` — `--jq '.workflows[] | [.path,.name] | @tsv'` streams TSV lines; concatenating lines across pages is exactly right. `watchdog.yml:665`, `:740` — object endpoint with no `--jq`, consumed by `jq -r '.jobs[]?.id // empty'`, which accepts a multi-value input stream. Safe by accident, but safe. Suggested fix: same as T067 applied to `pr-conversation.yml`: stream one value per line and slurp once — `gh api \"<path>\" --paginate --jq '.[] | <per-item filter>' | jq -s '.'`. (`--slurp` also works but changes the shape to an array *of pages*, so the filter has to change too — the streaming form is the smaller edit.) Why it is worth a gate: all three sites fail *silently* (soft-failed, or producing a plausible-looking wrong value), and only past page 1 — so they pass every small-fixture test and every early-life run, then degrade invisibly. A cheap grep-level check for `--paginate --jq '['` plus 'array endpoint + `--paginate` + no `--jq`' would catch the whole class. Spec 033 added the shape to its own `quickstart.md` static-validation set; a repo-wide gate would be better. Found while fixing spec 033 T067."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The watchdog reports annotation evidence from a job that has more than one page of it (Priority: P1)

A pipeline run fails and produces more than thirty warning/failure annotations across its jobs. The watchdog collects those annotations as evidence, and every one of them reaches the evidence set that the diagnosis step reads. The maintainer who opens the watchdog's verdict sees the annotations that explain the failure, not a verdict reasoned from a silently emptied evidence set.

**Why this priority**: This is the most damaging of the three sites, because it degrades the instrument whose entire job is to notice that something is wrong. The read is soft-failed, so a failure and "there were no annotations" are the same observable outcome; the evidence set is not merely missing the annotations from page two onward, it loses *all* of them, and the write that would have added them is abandoned. A watchdog that quietly reasons from less evidence than it collected is worse than one that says it could not collect.

**Independent Test**: Present the annotation collector with a job whose annotations span more than one page, and confirm that every warning- and failure-level annotation appears in the evidence set handed to the diagnosis step — and that the evidence already gathered by earlier collectors is still there too.

**Acceptance Scenarios**:

1. **Given** an inspected run with one job whose annotations fill more than one page, **When** the annotation collector runs, **Then** every warning- and failure-level annotation from every page appears in the evidence set exactly once.
2. **Given** the same run, **When** the annotation collector finishes, **Then** the evidence contributed by the collectors that ran before it is unchanged and still present.
3. **Given** an inspected run with several jobs, each with more than one page of annotations, **When** the collector runs, **Then** annotations from every job are present, and no job's annotations displace another's.
4. **Given** an inspected run whose jobs have fewer annotations than one page, **When** the collector runs, **Then** the result is identical to today's behaviour.
5. **Given** a job that genuinely has no warning- or failure-level annotations, **When** the collector runs, **Then** the evidence set is unchanged and the run is not reported as having failed to read.

---

### User Story 2 - Spec Kit release detection resolves exactly one latest version once upstream passes the page boundary (Priority: P1)

Upstream publishes its thirty-first release. The auto-update chain's detection step still resolves exactly one latest eligible version, compares it against the pinned version correctly, and — when a bump is warranted — carries that single version, and only the release notes between pinned and candidate, into every step that follows.

**Why this priority**: The failure here is worse than an abort, because it is not one. The comparison step produces a value that *looks* like a version and is actually two versions on two lines; nothing rejects it, so the wrong value flows into the candidate identity, the settle counter, the branch name, the PR title, and the model prompt that judges the upgrade. Upstream is already near the boundary, so this converts from latent to live without any change on this side.

**Independent Test**: Point the detection step at an upstream release list long enough to span more than one page and confirm it yields one version string, that the version it yields is the highest eligible stable release, and that the release-note bundle it assembles is a single well-formed collection covering exactly the releases between the pinned and candidate versions.

**Acceptance Scenarios**:

1. **Given** an upstream release list spanning more than one page, **When** the detection step resolves the latest eligible release, **Then** it produces exactly one version identifier.
2. **Given** the same list, **When** the latest eligible release is on a page after the first, **Then** that release is the one selected — pagination must not truncate the search to the first page either.
3. **Given** the same list, **When** the newest releases are pre-releases, **Then** they are excluded and the newest stable release is selected, regardless of which page it fell on.
4. **Given** a candidate newer than the pinned version and an upstream list spanning more than one page, **When** the release-note bundle is assembled, **Then** it is a single well-formed collection containing every stable release above the pinned version and at or below the candidate, and nothing else.
5. **Given** an upstream list that fits in one page, **When** either step runs, **Then** the outcome is identical to today's behaviour.

---

### User Story 3 - A reviewer cannot merge a new instance of this defect (Priority: P1)

Someone adds a paginated API read whose output is consumed as a single JSON document. Before the change can merge, a repository-wide check fails and names the file, the line, and what is wrong with the shape — rather than the change passing every check, working in every test with a small fixture, and degrading invisibly months later when real data crosses the page boundary.

**Why this priority**: The three fixes are worth one run each; the gate is worth every future run. This defect class has now been found twice — six sites in one workflow, three more in two others — and both times only by a human reading the code, because the failure mode is defined by being invisible to tests that use small fixtures. This project's own operating principle is that a rule which is not machine-checked is a rule that decays; a comment in one workflow and a line in one feature's quickstart demonstrably did not stop the same class landing elsewhere.

**Independent Test**: Introduce each broken shape into a workflow file in turn and confirm the check fails, naming the offending location; then confirm it passes on the repository as it stands after User Stories 1 and 2 have landed.

**Acceptance Scenarios**:

1. **Given** a paginated read whose filter collects its results into an array, **When** the check runs, **Then** it fails and names the file and line.
2. **Given** a paginated read of an endpoint that returns an array with no per-item filter, whose output is then consumed as a single JSON document, **When** the check runs, **Then** it fails and names the file and line.
3. **Given** the repository with User Stories 1 and 2 applied, **When** the check runs, **Then** it passes.
4. **Given** a paginated read written in the correct streaming-and-slurping form, **When** the check runs, **Then** it passes.
5. **Given** a paginated read whose output is consumed as a stream of values, one per line, rather than as a single document, **When** the check runs, **Then** it passes.
6. **Given** the check itself is disabled, removed, or made unreachable, **When** the repository's checks run, **Then** a check fails — the gate is wired into the same registry that proves every other gate is actually run.
7. **Given** the check is present and correct, **When** its own self-test runs, **Then** the self-test demonstrates the check failing on a known-bad input, so a gate that has silently stopped detecting anything cannot pass as a healthy one.

---

### User Story 4 - The failure is named where a maintainer will meet it (Priority: P2)

A maintainer who encounters this shape — reading a review diff, or reading the check's failure output — is told what is wrong and what the correct form is, without having to reconstruct the pagination semantics from scratch. The knowledge that currently lives in one workflow's inline comments and one feature's quickstart becomes something the repository states once, in the place a maintainer working on any workflow would look.

**Why this priority**: The gate stops the defect merging; this stops it being written in the first place, and makes the gate's failure self-explanatory instead of a puzzle. It delivers real value but nothing is broken without it, so it sits below the fixes and the gate.

**Independent Test**: Have someone unfamiliar with the defect read only the check's failure message and confirm they can rewrite the offending call correctly without further help.

**Acceptance Scenarios**:

1. **Given** the check fails on a call site, **When** a maintainer reads its output, **Then** the output states why the shape is wrong and shows the correct form.
2. **Given** a maintainer writing a new paginated read, **When** they consult the repository's own guidance for workflow authors, **Then** the required form is stated there.

---

### Edge Cases

- **A paginated read of an endpoint that returns an array, consumed as a stream** (each value handled independently rather than parsed as one document): correct today, and must remain permitted — the fix is not "never paginate without a filter".
- **A paginated read whose filter emits non-JSON lines** (for example tab-separated text): concatenating lines across pages is exactly right, and must remain permitted.
- **A paginated read of an endpoint that returns an object with an array inside it** (`{"jobs": [...]}`): pagination concatenates whole objects, so a consumer that accepts a multi-value stream is correct while one that parses a single document is not. The two look nearly identical in the source; the check must not treat "currently works" as "obviously intended". See the open question in FR-011.
- **A read where pagination is capped by an explicit page limit** that makes more than one page impossible: still worth writing in the safe form, because the cap is one edit away from being raised.
- **A read that legitimately needs one array per page**: no such use exists in the repository today, and if one arrives it must be able to declare itself rather than be silently exempt.
- **The paginated read fails outright** (API error, rate limit, missing permission): distinct from "the response had no items", and today indistinguishable at many call sites. See the open question in FR-010.
- **A page boundary that falls exactly on the last item**, so the second page is empty: the collected result must be identical to the single-page case, with no trailing empty element.
- **The defect class appearing outside workflow files** — in a composite action's shell, or in a checked-in script: the same failure with the same invisibility, so the check's reach must be defined by where shell lives, not by one directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every paginated API read in the repository whose result is consumed as a single JSON document MUST yield exactly one well-formed document covering every page, not one document per page.
- **FR-002**: The watchdog's annotation collection MUST include every warning- and failure-level annotation from every page of every job in the inspected run, and MUST preserve the evidence gathered by the collectors that ran before it.
- **FR-003**: The auto-update chain's release detection MUST resolve exactly one latest eligible version from an upstream release list of any length, and that version MUST be the highest eligible one across all pages.
- **FR-004**: The auto-update chain's release-note assembly MUST produce a single well-formed collection covering exactly the eligible releases above the pinned version and at or below the candidate, from an upstream release list of any length.
- **FR-005**: The three fixes MUST NOT change behaviour for inputs that fit within a single page; a run against present-day data MUST produce the same outcome before and after.
- **FR-006**: The repository MUST carry an automated check that fails when a paginated API read is written in a form that cannot produce a single well-formed document for its consumer, and that check MUST cover every location in the repository where such a read can be written — workflow files, composite actions, and checked-in scripts alike — rather than a named subset of files.
- **FR-007**: The check MUST identify each offending location by file and line, and MUST state both what is wrong and the required form, so that its output alone is enough to correct the call.
- **FR-008**: The check MUST NOT flag the forms that are correct: a paginated read consumed as a stream of independent values, a paginated read whose filter emits non-JSON lines, and a paginated read already written in the streaming-and-slurping form.
- **FR-009**: The check MUST be wired into the repository's existing gate registry so that a gate which stops being run is itself a failure, and it MUST carry a self-test that demonstrates the check failing on a known-bad input — a detector that has stopped detecting MUST NOT be able to pass as a healthy one.
- **FR-010**: [NEEDS CLARIFICATION: The watchdog soft-fails roughly thirty-five of its evidence reads (`2>/dev/null || echo '[]'`), so a read that fails and a read that found nothing are indistinguishable — which is why this defect stayed invisible. Does this feature also make a failed evidence read distinguishable from an empty one across the watchdog's collectors, or is that a separate follow-up and this feature fixes only the three pagination sites plus the gate?]
- **FR-011**: [NEEDS CLARIFICATION: Two paginated reads in the watchdog are correct only because their consumer happens to accept a multi-value stream — described in the source issue as "safe by accident, but safe". Should the check flag these too, requiring them to be rewritten into a form that is safe by construction, or should it flag only shapes that are actually broken and leave the accidentally-safe ones as they are?]
- **FR-012**: [NEEDS CLARIFICATION: A static check cannot see that shell logic is wrong — this project already learned that when three defects shipped past its static gates and were caught only by an executable harness. Should the three fixed sites also gain executable multi-page coverage (an upstream response spanning more than one page, driven through the shipped step), and if so for which sites — the auto-update pair, which already has such a harness, the watchdog site, which does not, or all three?]
- **FR-013**: The check MUST NOT depend on a hand-maintained list of exempt files or call sites, because a list makes an omission invisible and every newly written site born exempt. Any exemption a genuinely unusual read requires MUST be declared at that read, visible in the diff that introduces it.
- **FR-014**: The repository's guidance for workflow authors MUST state the required form for paginated reads, so the rule exists somewhere a maintainer looks before writing the call, not only in the failure message afterwards.
- **FR-015**: The fixes MUST NOT widen any published stage workflow's declared inputs, outputs, or secrets, and MUST NOT change any adopter-visible behaviour other than the correctness of the reads themselves.

### Key Entities

- **Paginated read**: a single request for a collection that spans more than one response page, where the pages are fetched automatically and their results concatenated.
- **Page boundary**: the response size at which a second page begins — thirty items by default. Every defect in this class is invisible below it and certain above it.
- **Annotation evidence**: the warning- and failure-level annotations the watchdog collects from an inspected run's jobs, and folds into the evidence set its diagnosis reads.
- **Upstream release list**: the list of Spec Kit releases the auto-update chain reads to decide whether a newer version exists and to assemble the notes for one.
- **Pagination shape gate**: the repository-wide automated check that rejects paginated reads which cannot produce a single well-formed document for their consumer.

## Out of Scope

- **Any change to what the watchdog concludes from its evidence.** This feature restores annotations that were being dropped; the diagnosis logic that consumes them is untouched.
- **Any change to the auto-update chain's upgrade policy** — which versions are eligible, when a candidate settles, or what is proposed. Only the correctness of reading the release list changes.
- **Raising or lowering the page size** of any read, or introducing explicit page caps. The fix is to read every page correctly, not to read fewer.
- **Revisiting the six sites already fixed under spec 033.** They are the reference form; this feature brings the remaining sites to it and generalises the rule.
- **A general audit of every shell construct in the repository.** The gate covers this one defect class.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With an inspected run whose annotations span more than one page, one hundred percent of its warning- and failure-level annotations reach the watchdog's evidence set — up from zero percent today.
- **SC-002**: With an upstream release list spanning more than one page, release detection resolves exactly one version identifier, and it is the highest eligible one — where today it resolves two or more.
- **SC-003**: Every paginated read in the repository either produces a single well-formed document for its consumer or is consumed as a stream by construction; the count of reads that satisfy neither is zero.
- **SC-004**: Reintroducing any of the broken shapes into any workflow, composite action, or checked-in script causes a check to fail before merge, in every case, without a human noticing it first.
- **SC-005**: Removing, disabling, or breaking the new check causes a check to fail.
- **SC-006**: A maintainer given only the check's failure output can rewrite the offending call into a correct form without consulting anything else.
- **SC-007**: Runs against present-day, single-page data produce identical outcomes before and after this feature — zero behavioural change below the page boundary.

## Assumptions

- The correct form is already established and proven in this repository: stream one value per line under pagination and collect once at the end, as the intake stage and the six sites fixed under spec 033 do. This feature applies that form rather than inventing one.
- The default page size is thirty items, and neither the watchdog's annotation reads nor the upstream release list is expected to stay below it.
- The upstream release list is already close enough to the boundary that this converts from latent to live without any change on this side; the fix is therefore time-sensitive independently of the watchdog site.
- The repository already has a place for repository-wide static checks, a registry that proves each one is actually run, and a precedent for gates that carry their own self-tests. The new check joins that arrangement rather than establishing a new one.
- The three sites are the complete set outside spec 033: the source issue states that the other paginated reads in the repository were examined individually and found correct. This feature re-derives that list from the code rather than trusting the line numbers in the issue, which have already drifted.
- Fixing these reads does not require any additional API permission or token scope; the same requests are made, only their results are assembled correctly.
- The transient pipeline checkout that appears under the repository root during a run is not part of the repository's own source and is not in the check's scope.
