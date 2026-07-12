# Feature Specification: SECURITY.md Vulnerability-Reporting Policy

**Feature Branch**: `011-security-policy`

**Created**: 2026-07-12

**Status**: Draft

**Input**: User description: "Add a SECURITY.md file at the repository root so visitors know how to report vulnerabilities responsibly. Requirements: A top-level heading and at most three short paragraphs. Direct reporters to GitHub's private vulnerability reporting for this repository (Security tab → Report a vulnerability) rather than public issues. State plainly that pipeline runs execute Claude agents with repository write access via a GitHub App, so credential-handling reports (leaked tokens, overly broad permissions) are explicitly in scope. No other files changed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Report a vulnerability through the private channel (Priority: P1)

A security researcher discovers a potential vulnerability in this repository and wants to disclose it responsibly. They look for a security policy, find it in the repository's Security tab, and learn to submit the report through GitHub's private vulnerability reporting rather than opening a public issue that would expose the problem before it is fixed.

**Why this priority**: This is the core value of the feature — without a discoverable policy, a well-intentioned reporter's only obvious channel is a public issue, which discloses the vulnerability to everyone the moment it is filed. Directing reporters to the private channel is the primary outcome.

**Independent Test**: Open the repository's Security tab (or view the root security policy document) and confirm it names GitHub's private vulnerability reporting as the intended channel and explicitly discourages public issues.

**Acceptance Scenarios**:

1. **Given** a visitor who has found a possible vulnerability, **When** they open the repository's Security tab, **Then** a security policy is present that tells them to use GitHub's private vulnerability reporting ("Report a vulnerability") for this repository.
2. **Given** a visitor reading the policy, **When** they look for where to disclose the issue, **Then** the policy plainly states that public issues are not the channel for vulnerability reports.

---

### User Story 2 - Understand that credential handling is in scope (Priority: P2)

A reporter evaluating this project understands that pipeline runs execute Claude agents holding repository write access through a GitHub App. The policy makes clear that credential-handling problems — such as leaked tokens or overly broad permissions — are explicitly welcome as reports, so the reporter knows this class of issue belongs in the private channel rather than being dismissed as out of scope.

**Why this priority**: This project's distinguishing risk is that automated agents act on the repository with write access via a GitHub App. Reporters need to know that this specific attack surface is in scope so credential issues are actually reported. It builds on Story 1 (the reporting channel must exist first), hence P2.

**Independent Test**: Read the security policy and confirm it states that pipeline runs execute Claude agents with repository write access via a GitHub App, and that credential-handling reports (e.g., leaked tokens, overly broad permissions) are explicitly in scope.

**Acceptance Scenarios**:

1. **Given** a reporter concerned about a leaked token or an overly broad permission, **When** they read the policy, **Then** it confirms such credential-handling issues are in scope for reporting.
2. **Given** a reader unfamiliar with how the pipeline runs, **When** they read the policy, **Then** it plainly explains that agents operate with repository write access via a GitHub App.

---

### Edge Cases

- What happens when a reporter files a public issue anyway? The policy states the preferred private channel; triage of misfiled reports (e.g., a maintainer redirecting them) is a manual follow-up and out of scope for this document.
- What happens when someone reports a non-security bug through the private channel? The policy defines the vulnerability-reporting path; ordinary bug handling is unchanged and out of scope.
- What happens if GitHub's private vulnerability reporting is not enabled for the repository? The policy assumes the feature is enabled; enabling it is a repository-setting dependency (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST provide a security policy document at the repository root, located and named so that GitHub surfaces it in the repository's Security tab and as the repository's security policy.
- **FR-002**: The policy MUST direct reporters to GitHub's private vulnerability reporting for this repository (Security tab → "Report a vulnerability") as the channel for disclosing vulnerabilities.
- **FR-003**: The policy MUST tell reporters not to disclose vulnerabilities through public issues.
- **FR-004**: The policy MUST state plainly that pipeline runs execute Claude agents with repository write access via a GitHub App.
- **FR-005**: The policy MUST state that credential-handling reports — including leaked tokens and overly broad permissions — are explicitly in scope.
- **FR-006**: The document MUST be concise: a single top-level heading followed by at most three short paragraphs.
- **FR-007**: The change MUST NOT modify or create any file other than the new security policy document.

### Key Entities

- **Security policy document**: A repository-root markdown file that GitHub recognizes as the project's security policy. It carries the reporting channel, the no-public-issues instruction, and the in-scope statement about agent write access and credential handling.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A visitor can reach the repository's vulnerability-reporting instructions within one interaction from the repository's Security tab.
- **SC-002**: The policy document contains exactly one top-level heading and no more than three paragraphs of body text.
- **SC-003**: All four required disclosures are present in the policy: (1) private vulnerability reporting as the channel, (2) public issues are not the channel, (3) agents run with repository write access via a GitHub App, and (4) credential-handling issues are in scope.
- **SC-004**: The change introduces exactly one new file and modifies no existing files.

## Assumptions

- The security policy document is placed at the repository root as `SECURITY.md`, following GitHub's convention for surfacing a security policy in the Security tab and repository UI.
- GitHub's private vulnerability reporting is (or will be) enabled in the repository's settings; the policy points reporters to it, but enabling the feature is a repository-setting dependency outside the scope of this document.
- The policy does not commit to a specific acknowledgement or response-time SLA; its purpose is to establish the reporting channel and the in-scope credential-handling surface, not to define a triage process.
- "Short paragraphs" is interpreted as brief, single-topic paragraphs (roughly a few sentences each) so the whole policy reads at a glance.
- No supported-versions matrix is required; this is a single-line-of-development GitHub Action, and versioning of the policy is out of scope.
