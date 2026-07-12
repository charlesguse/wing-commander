# Phase 0 Research: SECURITY.md Vulnerability-Reporting Policy

The feature spec contains no `[NEEDS CLARIFICATION]` markers — the Assumptions
section already resolves the open questions a reviewer would otherwise raise.
This document records those resolutions in the standard research format so the
decisions are traceable from the plan, and adds the supporting rationale.

## Decision: File name and location

- **Decision**: `SECURITY.md` at the repository root.
- **Rationale**: GitHub recognizes `SECURITY.md` (case-insensitive) in the
  repository root, `.github/`, or `docs/` as the repository's security policy
  and links it from the Security tab and from the "Report a vulnerability"
  flow. Root placement matches this repository's existing convention of
  keeping top-level Markdown docs (`README.md`) at the root, and matches
  FR-001's requirement that GitHub surface the document automatically.
- **Alternatives considered**: `.github/SECURITY.md` — also recognized by
  GitHub, but rejected because the spec's Assumptions section already commits
  to the repository-root location and there is no reason in this repo to
  prefer the `.github/` variant (that directory is reserved here for workflow
  and Action configuration, not policy docs).

## Decision: Reporting channel

- **Decision**: Point reporters at GitHub's private vulnerability reporting
  ("Security tab → Report a vulnerability") and explicitly tell them not to
  use public issues.
- **Rationale**: Directly satisfies FR-002 and FR-003, and is the only channel
  that avoids disclosing an unpatched vulnerability to the public the moment
  it is filed. This also matches how GitHub itself expects `SECURITY.md` to be
  used once private vulnerability reporting is enabled for a repository.
- **Alternatives considered**: An email address or external form — rejected;
  the spec explicitly scopes the channel to GitHub's private vulnerability
  reporting and introducing a second channel would contradict FR-002/FR-003
  and add operational surface (an inbox to monitor) with no spec justification.

## Decision: Credential-handling scope statement

- **Decision**: State plainly that pipeline runs execute Claude agents with
  repository write access via a GitHub App, and that credential-handling
  reports (leaked tokens, overly broad permissions) are explicitly in scope.
- **Rationale**: Satisfies FR-004/FR-005. This mirrors Constitution Principle
  V (Security — Untrusted Content Is Never Instructions), which already
  identifies GitHub App authentication and least-privilege tooling as the
  project's security posture; the policy makes that posture, and its
  associated risk surface, legible to outside reporters.
- **Alternatives considered**: Leaving the agent/credential detail out and
  relying on a generic "report any security issue" statement — rejected
  because the spec (User Story 2, FR-004, FR-005) requires this class of
  issue to be named explicitly so it isn't dismissed as out of scope by a
  cautious reporter.

## Decision: Length and structure

- **Decision**: One top-level (`#`) heading, at most three short, single-topic
  paragraphs, no sub-sections, no supported-versions table.
- **Rationale**: Satisfies FR-006/SC-002. The Assumptions section rules out a
  supported-versions matrix (single-line-of-development GitHub Action) and an
  SLA commitment, keeping the whole policy readable at a glance — three
  paragraphs are enough to cover: (1) reporting channel + no-public-issues
  instruction, (2) agent/GitHub-App write-access + credential scope, and
  optionally (3) a short closing note, if needed, with no new normative
  content beyond FR-001…FR-005.
- **Alternatives considered**: A longer, sectioned policy (scope, SLA,
  supported versions, acknowledgements) — rejected by the spec's explicit
  three-paragraph ceiling (FR-006) and by the Assumptions section, which
  scopes the document to the reporting channel and the in-scope statement only.

## Decision: Blast radius

- **Decision**: This change touches exactly one file, `SECURITY.md`; no other
  file in the repository is created, modified, or deleted.
- **Rationale**: Directly required by FR-007/SC-004, and keeps the plan
  trivially reviewable — a reviewer can verify FR-007 by checking the diff
  contains a single added file.
- **Alternatives considered**: Also linking to `SECURITY.md` from `README.md`
  — rejected; FR-007 explicitly forbids modifying any other file, and GitHub
  already surfaces `SECURITY.md` in the Security tab and repository file list
  without requiring a README cross-link.

**Output**: All decisions above resolve every open question in the spec. No
`[NEEDS CLARIFICATION]` markers remain.
