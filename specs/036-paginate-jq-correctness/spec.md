# Feature Specification: Multi-Page `gh api` Reads Return What They Claim, and a Gate Keeps Them That Way

**Feature Branch**: `036-paginate-jq-correctness`

**Created**: 2026-08-16

**Status**: Draft

**Input**: User description: "`gh api --paginate --jq '<filter producing an array>'` is unparseable past the first page, and three call sites outside spec 033 still use that shape. `gh` applies `--jq` to **each page separately** and concatenates the results. So `--paginate --jq '[.[] | ...]'` emits `[...]\n[...]` — one array *per page* — not one array. Anything that then parses the whole string as a single JSON value fails. This was found and fixed for `pr-conversation.yml`'s six call sites under spec 033 T067 (`specs/033-pr-conversation-commands/tasks.md`). T067 asked for the adjacent sites to be checked and filed separately if the same class held. It does, in two files. Sites that hold — 1. `watchdog.yml:743` — annotations collector: an array endpoint with no `--jq`, so `gh` concatenates raw arrays: `[...][...]`. `jq -c '[ .[]? | ... ]'` over two inputs emits **two** arrays, so `--argjson f` gets invalid JSON and fails. The step runs under `set -uo pipefail` (no `-e`), so it does not abort — `entries` silently collapses to empty and the final `jq --argjson new \"$entries\"` fails too, leaving `signals.json` un-updated. Annotation evidence is **silently dropped** rather than reported as a failure. Bites once a job has more than one page (30) of annotations. Worth noting alongside the existing observation that `watchdog.yml` soft-fails these reads in ~35 places (`2>/dev/null || echo '[]'`), so a real failure there is already indistinguishable from 'there was no evidence to collect'. 2 & 3. `auto-update-spec-kit.yml:391` and `:799` — release detection: same shape: concatenated arrays, so `jq` emits one result per page and `latest` becomes two JSON objects on two lines; `jq -r '.tag_name'` then yields two tag names. `github/spec-kit` is already near the 30-release page boundary, so this is not hypothetical for long. Sites checked and found safe: `intake.yml:399` — `--jq '.[]'` piped through `jq -s '.'`. This is the correct form. `lint-workflows.yml:1176` — `--jq '.workflows[] | [.path,.name] | @tsv'` streams TSV lines; concatenating lines across pages is exactly right. `watchdog.yml:665`, `:740` — object endpoint with no `--jq`, consumed by `jq -r '.jobs[]?.id // empty'`, which accepts a multi-value input stream. Safe by accident, but safe. Suggested fix: same as T067 applied to `pr-conversation.yml`: stream one value per line and slurp once — `gh api \"<path>\" --paginate --jq '.[] | <per-item filter>' | jq -s '.'`. (`--slurp` also works but changes the shape to an array *of pages*, so the filter has to change too — the streaming form is the smaller edit.) Why it is worth a gate: all three sites fail *silently* (soft-failed, or producing a plausible-looking wrong value), and only past page 1 — so they pass every small-fixture test and every early-life run, then degrade invisibly. A cheap grep-level check for `--paginate --jq '['` plus 'array endpoint + `--paginate` + no `--jq`' would catch the whole class. Spec 033 added the shape to its own `quickstart.md` static-validation set; a repo-wide gate would be better. Found while fixing spec 033 T067."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The watchdog reports annotation evidence from a job that has more than one page of it (Priority: P1)

A pipeline run fails and produces more than thirty warning/failure annotations across its jobs. The watchdog collects those annotations as evidence, and every one of them reaches the evidence set that the diagnosis step reads. The maintainer who opens the watchdog's verdict sees the annotations that explain the failure, not a verdict reasoned from a silently emptied evidence set.

**Why this priority**: This is the most damaging of the three sites, because it degrades the instrument whose entire job is to notice that something is wrong. The read is soft-failed, so a failure and "there were no annotations" are the same observable outcome; the evidence set is not merely missing the annotations from page two onward, it loses *all* of them, and the write that would have added them is abandoned. A watchdog that quietly reasons from less evidence than it collected is worse than one that says it could not collect.

**Independent Test**: Drive the shipped annotation-collection step against a response spanning more than one page, and confirm that every warning- and failure-level annotation appears in the evidence set handed to the diagnosis step — and that the evidence already gathered by earlier collectors is still there too.

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

**Independent Test**: Drive the shipped detection step against an upstream release list long enough to span more than one page and confirm it yields one version string, that the version it yields is the highest eligible stable release, and that the release-note bundle it assembles is a single well-formed collection covering exactly the releases between the pinned and candidate versions.

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

**Independent Test**: Introduce each broken shape into a workflow file in turn and confirm the check fails, naming the offending location; then confirm it passes on the repository as it stands after User Stories 1 and 2 have landed and the two accidentally-safe watchdog reads have been rewritten into the safe-by-construction form.

**Acceptance Scenarios**:

1. **Given** a paginated read whose filter collects its results into an array, **When** the check runs, **Then** it fails and names the file and line.
2. **Given** a paginated read of an endpoint that returns an array or an object, with no per-item filter, **When** the check runs, **Then** it fails and names the file and line — whether or not its consumer happens to tolerate one value per page.
3. **Given** the repository with User Stories 1 and 2 applied and the two accidentally-safe watchdog reads rewritten, **When** the check runs, **Then** it passes.
4. **Given** a paginated read written in the correct streaming-and-slurping form, **When** the check runs, **Then** it passes.
5. **Given** a paginated read whose per-item filter emits one JSON value per line and whose consumer handles those values as a stream rather than as a single document, **When** the check runs, **Then** it passes.
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

### User Story 5 - The watchdog says when it could not see, instead of behaving as though there was nothing to see (Priority: P2)

An evidence read fails — a rate limit, a missing permission, an API error. The watchdog records that collector as untrusted, still reaches a verdict from the evidence it did gather, and tells the diagnosis step which collectors it could not trust. The maintainer reading the verdict can tell "there was no evidence of this kind" from "I could not look".

**Why this priority**: This is the condition that hid the defect in the first three stories: roughly thirty-five of the watchdog's evidence reads soft-fail to an empty result, so a broken read and a clean run are the same observable outcome. Fixing the annotation collector removes one cause of a silently reduced evidence set; this removes the property that made it — and any future cause — invisible. It sits below the three P1 stories because the release-detection fix is time-sensitive and this story is the larger surface: it touches every collector and the evidence the diagnosis reads, so it must not delay them.

**Independent Test**: Make one collector's read fail while the others succeed, and confirm the run still produces a verdict, that the failed collector is named as untrusted in what the diagnosis step reads, and that a collector which genuinely found nothing is not named.

**Acceptance Scenarios**:

1. **Given** an evidence read that fails, **When** the collector runs, **Then** the failure is recorded as a failed read and not as an empty result.
2. **Given** a collector whose read genuinely returns nothing, **When** it runs, **Then** it is recorded as an empty result and is not reported as untrusted.
3. **Given** one collector whose read fails and others that succeed, **When** the watchdog runs, **Then** it still reaches a verdict, the successful collectors' evidence is intact, and the diagnosis step is told which collector could not be trusted.
4. **Given** a run in which every evidence read succeeds, **When** the watchdog runs, **Then** the outcome is identical to today's behaviour and nothing is reported as untrusted.

---

### Edge Cases

- **A paginated read consumed as a stream** (each value handled independently rather than parsed as one document): permitted, provided the read itself emits one item per line. Consuming a stream is not what makes a read safe; emitting one item per line is. A read that relies on its consumer to tolerate page-shaped values is flagged (FR-011).
- **A paginated read whose filter emits non-JSON lines** (for example tab-separated text): concatenating lines across pages is exactly right, and must remain permitted.
- **A paginated read of an endpoint that returns an object with an array inside it** (`{"jobs": [...]}`): pagination concatenates whole objects, so the read emits one object per page rather than one item per line. This is flagged whatever its consumer does — the two watchdog reads of this shape work today only because their consumer tolerates a multi-value stream, and they are rewritten. The check does not have to tell "currently works" from "actually intended", because neither passes.
- **A read where pagination is capped by an explicit page limit** that makes more than one page impossible: still worth writing in the safe form, because the cap is one edit away from being raised.
- **A read that legitimately needs one array per page**: no such use exists in the repository today, and if one arrives it must be able to declare itself rather than be silently exempt.
- **The paginated read fails outright** (API error, rate limit, missing permission): distinct from "the response had no items", and today indistinguishable at many call sites. Every watchdog evidence read must report the two differently, and the diagnosis step must be told which collectors it cannot trust (FR-010, FR-016).
- **A watchdog collector fails while others succeed**: the run still reaches a verdict from the evidence that was gathered, with the failed collector named as untrusted rather than silently contributing nothing (FR-017).
- **A page boundary that falls exactly on the last item**, so the second page is empty: the collected result must be identical to the single-page case, with no trailing empty element.
- **The defect class appearing outside workflow files** — in a composite action's shell, or in a checked-in script: the same failure with the same invisibility, so the check's reach must be defined by where shell lives, not by one directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every paginated API read in the repository whose result is consumed as a single JSON document MUST yield exactly one well-formed document covering every page, not one document per page.
- **FR-002**: The watchdog's annotation collection MUST include every warning- and failure-level annotation from every page of every job in the inspected run, and MUST preserve the evidence gathered by the collectors that ran before it.
- **FR-003**: The auto-update chain's release detection MUST resolve exactly one latest eligible version from an upstream release list of any length, and that version MUST be the highest eligible one across all pages.
- **FR-004**: The auto-update chain's release-note assembly MUST produce a single well-formed collection covering exactly the eligible releases above the pinned version and at or below the candidate, from an upstream release list of any length.
- **FR-005**: The three fixes MUST NOT change behaviour for inputs that fit within a single page; a run against present-day data MUST produce the same outcome before and after.
- **FR-006**: The repository MUST carry an automated check that fails when a paginated API read is written in a form that is not safe by construction — one that emits page-shaped values rather than one item per line — and that check MUST cover every location in the repository where such a read can be written — workflow files, composite actions, and checked-in scripts alike — rather than a named subset of files.
- **FR-007**: The check MUST identify each offending location by file and line, and MUST state both what is wrong and the required form, so that its output alone is enough to correct the call.
- **FR-008**: The check MUST NOT flag the forms that are safe by construction: a paginated read whose per-item filter emits one JSON value per line — whether its consumer slurps that stream once or handles each value independently — and a paginated read whose filter emits non-JSON lines such as tab-separated text.
- **FR-009**: The check MUST be wired into the repository's existing gate registry so that a gate which stops being run is itself a failure, and it MUST carry a self-test that demonstrates the check failing on a known-bad input — a detector that has stopped detecting MUST NOT be able to pass as a healthy one.
- **FR-010**: Every one of the watchdog's evidence reads MUST distinguish a read that failed from a read that legitimately returned nothing. A read that fails MUST NOT be recorded as an empty result, and the distinction MUST hold for all of the watchdog's collectors, not only the annotation collector this feature otherwise repairs.
- **FR-011**: The check MUST flag every paginated read that is not safe by construction, including a read that is correct today only because its consumer happens to tolerate a multi-value stream. The two such reads in the watchdog MUST be rewritten into the safe-by-construction form; a read whose correctness depends on an unstated property of its consumer MUST NOT pass.
- **FR-012**: All three fixed sites MUST gain executable coverage that drives them with a response spanning more than one page: the two auto-update sites through the existing harness that extracts and runs the shipped steps against a stubbed API, and the watchdog's annotation collector through equivalent coverage stood up for it, since no such harness exists there today. Reverting any one of the three fixes MUST fail a test, not only the static check.
- **FR-013**: The check MUST NOT depend on a hand-maintained list of exempt files or call sites, because a list makes an omission invisible and every newly written site born exempt. Any exemption a genuinely unusual read requires MUST be declared at that read, visible in the diff that introduces it.
- **FR-014**: The repository's guidance for workflow authors MUST state the required form for paginated reads, so the rule exists somewhere a maintainer looks before writing the call, not only in the failure message afterwards.
- **FR-015**: The fixes MUST NOT widen any published stage workflow's declared inputs, outputs, or secrets, and MUST NOT change any adopter-visible behaviour other than the correctness of the reads themselves and the newly reported trustworthiness of each evidence read.
- **FR-016**: The watchdog's diagnosis step MUST be told which collectors could not be trusted for the run being diagnosed, so that a verdict reasoned from an incomplete evidence set is identifiable as one rather than presenting as a verdict reasoned from complete evidence.
- **FR-017**: Reporting a failed evidence read MUST NOT abort the watchdog run or discard the evidence that other collectors gathered successfully — a collector that could not read is recorded as untrusted and the run continues to a verdict.
- **FR-018**: The two watchdog reads rewritten under FR-011 MUST continue to yield the same job identifiers they yield today for a single-page run, and MUST yield the identifiers from every page for a run that spans more than one.

### Key Entities

- **Paginated read**: a single request for a collection that spans more than one response page, where the pages are fetched automatically and their results concatenated.
- **Page boundary**: the response size at which a second page begins — thirty items by default. Every defect in this class is invisible below it and certain above it.
- **Annotation evidence**: the warning- and failure-level annotations the watchdog collects from an inspected run's jobs, and folds into the evidence set its diagnosis reads.
- **Upstream release list**: the list of Spec Kit releases the auto-update chain reads to decide whether a newer version exists and to assemble the notes for one.
- **Pagination shape gate**: the repository-wide automated check that rejects paginated reads which are not safe by construction — those that do not emit one item per line under pagination, regardless of what their consumer tolerates.
- **Read outcome**: for each of the watchdog's evidence reads, whether it succeeded (with or without items) or failed, carried alongside the evidence itself so the diagnosis step can tell the two apart.
- **Multi-page harness**: executable coverage that drives a shipped workflow step against a stubbed API response spanning more than one page. It exists for the auto-update chain today and must be stood up for the watchdog's annotation collector.

## Out of Scope

- **Any change to the watchdog's diagnostic reasoning.** This feature restores annotations that were being dropped and tells the diagnosis step which collectors could not be trusted. How the diagnosis weighs its evidence, and what it concludes from a given evidence set, is untouched — the only new input is the trustworthiness of each read.
- **Retrying, backing off, or otherwise recovering from a failed evidence read.** This feature makes a failed read visible; making it succeed is a different problem.
- **Any change to the auto-update chain's upgrade policy** — which versions are eligible, when a candidate settles, or what is proposed. Only the correctness of reading the release list changes.
- **Raising or lowering the page size** of any read, or introducing explicit page caps. The fix is to read every page correctly, not to read fewer.
- **Revisiting the six sites already fixed under spec 033.** They are the reference form; this feature brings the remaining sites to it and generalises the rule.
- **A general audit of every shell construct in the repository.** The gate covers this one defect class.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With an inspected run whose annotations span more than one page, one hundred percent of its warning- and failure-level annotations reach the watchdog's evidence set — up from zero percent today.
- **SC-002**: With an upstream release list spanning more than one page, release detection resolves exactly one version identifier, and it is the highest eligible one — where today it resolves two or more.
- **SC-003**: Every paginated read in the repository is safe by construction — it emits one item per line under pagination, or non-JSON lines; the count of reads whose correctness depends on what their consumer tolerates is zero, down from two today.
- **SC-004**: Reintroducing any of the broken shapes into any workflow, composite action, or checked-in script causes a check to fail before merge, in every case, without a human noticing it first.
- **SC-005**: Removing, disabling, or breaking the new check causes a check to fail.
- **SC-006**: A maintainer given only the check's failure output can rewrite the offending call into a correct form without consulting anything else.
- **SC-007**: Runs against present-day, single-page data in which every read succeeds produce identical outcomes before and after this feature — zero behavioural change below the page boundary.
- **SC-008**: Every one of the watchdog's evidence reads reports a failed read differently from an empty one; the count of reads that still collapse a failure into "there was no evidence" is zero, down from roughly thirty-five today.
- **SC-009**: With one collector's read forced to fail, the watchdog still reaches a verdict and the diagnosis step can name that collector as untrusted — where today the same run is indistinguishable from one with nothing to report.
- **SC-010**: Each of the three fixed sites is exercised by an executable test that drives the shipped step against a response spanning more than one page; reverting any one of the three fixes fails a test, not only the static check.

## Assumptions

- The correct form is already established and proven in this repository: stream one value per line under pagination and collect once at the end, as the intake stage and the six sites fixed under spec 033 do. This feature applies that form rather than inventing one.
- The default page size is thirty items, and neither the watchdog's annotation reads nor the upstream release list is expected to stay below it.
- The upstream release list is already close enough to the boundary that this converts from latent to live without any change on this side; the fix is therefore time-sensitive independently of the watchdog site.
- The repository already has a place for repository-wide static checks, a registry that proves each one is actually run, and a precedent for gates that carry their own self-tests. The new check joins that arrangement rather than establishing a new one.
- The three sites are the complete set outside spec 033: the source issue states that the other paginated reads in the repository were examined individually and found correct. This feature re-derives that list from the code rather than trusting the line numbers in the issue, which have already drifted.
- Fixing these reads does not require any additional API permission or token scope; the same requests are made, only their results are assembled correctly.
- The transient pipeline checkout that appears under the repository root during a run is not part of the repository's own source and is not in the check's scope.
- The auto-update chain's existing harness — which extracts and runs the shipped `run:` blocks against a stubbed API — can be pointed at a response spanning more than one page without being restructured. The watchdog has no equivalent, so standing one up is part of this feature's cost rather than a reuse of something already there.
- The watchdog's evidence set has somewhere to carry per-collector read outcomes, or can be given one, without changing what the diagnosis concludes from the evidence itself.
- The two accidentally-safe watchdog reads can be rewritten into the safe-by-construction form without changing the job identifiers their consumers receive; the rewrite is a shape change, not a behaviour change.

## Clarifications

### Session 2026-08-16

- Q: Does this feature also make the watchdog's soft-failed evidence reads distinguishable from empty ones, or does it fix only the three pagination sites plus the gate? → A: In scope for all of the watchdog's evidence reads — every collector distinguishes a failed read from an empty one, and the diagnosis step is told which collectors could not be trusted (FR-010, FR-016, FR-017; User Story 5).
- Q: Should the gate flag the two paginated reads that are correct only because their consumer happens to accept a multi-value stream? → A: Flag them — the gate requires every paginated read to be safe by construction, and those two are rewritten into the streaming-and-slurping form (FR-008, FR-011, FR-018).
- Q: Do the three fixed sites gain executable multi-page coverage, and if so for which of them? → A: All three — the auto-update pair through its existing harness, and equivalent multi-page coverage built for the watchdog's annotation collector (FR-012, SC-010).
