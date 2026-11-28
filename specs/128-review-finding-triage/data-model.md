# Data model: Review finding triage (spec 128)

## Finding (extended)

Existing fields are unchanged (`title`, `what`, `evidence`,
`fingerprint_basis`; reviewer findings also `in_scope`, `line`). New, all
optional on the wire:

| Field | Type | Meaning |
|-------|------|---------|
| `failure_class` | `"silent" \| "loud" \| "none"` | How the defect fails. Absent or any other value = *unreadable*. |
| `silent_description` | one-line string | How it fails silently. Required when `failure_class` is `silent`. |
| `severity` | `"important" \| "nit" \| "pre_existing"` | Code-review vocabulary. Absent = nit. |
| `security` | boolean | Absent = false. |

## Routing outcome

Returned by `wc_finding_triage.route(finding, in_scope)`:

| `outcome` | `reason` | When |
|-----------|----------|------|
| `fix-now` | `in scope` | reviewer finding with `in_scope` true (gate only) |
| `record` | `can fail silently` | out of scope, class silent with description |
| `record` | `never dropped (important/security)` | out of scope, class loud/none, severity important or security true |
| `record` | `class unreadable` | out of scope, class absent or unrecognised, FR-009 fail-toward-visibility |
| `drop` | `fails loudly` | out of scope, class loud, not important/security |
| `drop` | `no output change` | out of scope, class none, not important/security |
| `reject` | `silent, no description` | class silent, `silent_description` absent/empty/multi-line (any severity) |

A stage-found proposal has no PR: `in_scope` is passed as false, so it never
yields `fix-now`.

Precedence, first match wins: reviewer in-scope → fix-now; silent without
description → reject; silent → record; important/security → record;
absent/unrecognised class → record; loud → drop (fails loudly); none → drop
(no output change).

## Triage record

`{title, outcome, reason}` per non-recorded, non-fix-now finding. State:
`state.json.triaged_out` (stage-findings) and the `triage` annotation on each
entry of `lifecycle-review-findings.json` (gate). The rendered list is a
pure function of these records: `render_triaged(records) -> markdown`.

## State transitions

None persistent. A dropped finding has no durable artifact except its line in
the round's review body / the run's step summary; a rejected one additionally
emits a warning annotation.
