# Phase 1 Data Model: SECURITY.md Vulnerability-Reporting Policy

This feature has no application data, database, or runtime state. The only
"entity" is the policy document itself, modeled here as content structure and
validation rules rather than a data schema.

## Entity: Security Policy Document

A single repository-root Markdown file that GitHub recognizes as the project's
security policy.

| Field | Description | Source |
|---|---|---|
| Top-level heading | Exactly one `#` heading naming the policy | FR-006, SC-002 |
| Reporting-channel statement | Directs reporters to GitHub's private vulnerability reporting (Security tab → "Report a vulnerability") for this repository | FR-002, SC-003(1) |
| No-public-issues statement | States that public issues are not the channel for vulnerability reports | FR-003, SC-003(2) |
| Agent write-access statement | States that pipeline runs execute Claude agents with repository write access via a GitHub App | FR-004, SC-003(3) |
| Credential-scope statement | States that credential-handling reports (leaked tokens, overly broad permissions) are explicitly in scope | FR-005, SC-003(4) |

### Validation rules

- Exactly one top-level heading (SC-002).
- At most three body paragraphs total (FR-006, SC-002).
- All four statements above must each be present somewhere in the body text;
  they are not required to map one-to-one with paragraphs — a single
  paragraph may combine more than one statement (e.g., the reporting-channel
  and no-public-issues statements naturally sit together) as long as the
  three-paragraph ceiling holds (SC-003).
- No other file in the repository is created or modified (FR-007, SC-004).

### State / lifecycle

None. This is a static document with no transitions, workflow states, or
versioning beyond ordinary Git history. The Assumptions section of the spec
explicitly rules out a supported-versions matrix and an SLA commitment.

### Relationships

None. The document stands alone; it is not referenced by or generated from
any other spec artifact, and (per FR-007) no other file is updated to link to
it.
