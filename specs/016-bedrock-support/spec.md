# Feature Specification: AWS Bedrock Support for Consuming Repositories

**Feature Branch**: `016-bedrock-support`

**Created**: 2026-07-22

**Status**: Draft

**Input**: User description: "Can't use Bedrock in a consuming repository. `use_bedrock` needs to be passed through to be set by consuming repos. The expectation is that the repo will configure AWS credentials using the configure-aws-credentials action and then set the use_bedrock flag in the Wing Commander action. Don't worry about testing Bedrock all the way through, that will be tested in the other repository after the implementation is done on this side."

## User Scenarios & Testing *(mandatory)*

The pipeline is adopted by other repositories, which call its stages (intake,
clarify, plan, tasks, implement, finalize, and the supporting rebase/watchdog
stages) to run spec-driven development. Every stage runs an AI agent, and today
those agents can only reach the model through the Anthropic API (an Anthropic
API key or an OAuth token). Some adopters run in AWS environments where their
governance, billing, and data-residency requirements mean the model must be
served through **AWS Bedrock** instead of the Anthropic API directly.

This feature lets a consuming repository declare that the pipeline's agents
should use AWS Bedrock as the model provider, supplying AWS credentials the way
they already do for other AWS-backed actions, without changing anything about
what the pipeline stages produce.

### User Story 1 - Run the pipeline against AWS Bedrock (Priority: P1)

As a maintainer of a consuming repository that must serve the model through AWS
Bedrock, I want to enable a Bedrock flag when I call the pipeline stages and
provide my AWS credentials, so that every agent in the lifecycle sends its
model requests to Bedrock in my AWS account instead of to the Anthropic API.

**Why this priority**: This is the requester's stated, blocking need — today
Bedrock cannot be used at all from a consuming repository. Delivering the
pass-through of the Bedrock flag (and the AWS configuration it needs) is the
whole feature.

**Independent Test**: A consuming repository configures AWS credentials and
enables the Bedrock flag when calling a stage, and the stage's agent completes
its work with model requests served by Bedrock — with no Anthropic API key or
OAuth token supplied.

**Acceptance Scenarios**:

1. **Given** a consuming repository that has enabled the Bedrock flag and supplied valid AWS configuration, **When** any pipeline stage runs, **Then** that stage's agent uses AWS Bedrock for its model calls and completes its work.
2. **Given** the Bedrock flag is enabled, **When** a stage runs without an Anthropic API key or OAuth token, **Then** the run does not fail for lack of an Anthropic credential.
3. **Given** the Bedrock flag is enabled, **When** the required AWS configuration is missing or invalid, **Then** the stage fails with a clear message naming what AWS configuration is missing, rather than failing opaquely or silently falling back to the Anthropic API.

---

### User Story 2 - Existing (Anthropic) adopters are unaffected (Priority: P2)

As a maintainer of a repository that uses the Anthropic API or OAuth token today,
I want the Bedrock capability to be off by default, so that adopting a version of
the pipeline that supports Bedrock changes nothing about my existing runs.

**Why this priority**: Preserves current behavior for every existing adopter and
for the pipeline's own dogfooded runs; essential for trust but subordinate to
delivering the Bedrock capability itself.

**Independent Test**: With the Bedrock flag left at its default (unset), run the
pipeline exactly as today using an Anthropic API key or OAuth token, and confirm
identical behavior.

**Acceptance Scenarios**:

1. **Given** a repository that does not set the Bedrock flag, **When** the pipeline runs with an Anthropic API key or OAuth token, **Then** behavior is identical to today (no regression).
2. **Given** the Bedrock flag is left unset, **When** a stage runs, **Then** no AWS configuration is required and none is requested.

---

### User Story 3 - Consistent, documented enablement across every stage (Priority: P3)

As an adopter, I want to enable Bedrock the same way for every stage that runs an
agent, and I want documentation that tells me exactly how to do it, so that I can
run the entire lifecycle on Bedrock without discovering per-stage inconsistencies.

**Why this priority**: The value of the feature is only realized when the *whole*
lifecycle can run on Bedrock; a single stage that still requires an Anthropic key
would block an adopter. Documentation is what makes the capability adoptable.

**Independent Test**: Enable Bedrock across the full set of stages a lifecycle
exercises and confirm each accepts the same configuration surface, and that the
adoption documentation describes the credentials-plus-flag setup.

**Acceptance Scenarios**:

1. **Given** the set of stages that run an agent, **When** a consumer enables Bedrock, **Then** every such stage exposes the same Bedrock enablement surface and behaves consistently.
2. **Given** the adoption documentation, **When** a maintainer reads it, **Then** it describes how to configure AWS credentials and set the Bedrock flag when calling the pipeline.

---

### Edge Cases

- **AWS configuration must reach a stage that runs as a called workflow**: Adopters call the pipeline's stages as reusable workflows, which execute in their own isolated jobs. AWS credentials that a consumer sets up in their own calling job do not automatically carry into the pipeline's stage job, so the feature must define how the AWS configuration Bedrock needs (credentials/role and region) actually reaches the agent inside each stage. [NEEDS CLARIFICATION: how does the AWS configuration reach each stage — does the pipeline accept an AWS role/region (and run credential configuration inside each stage), or does it require AWS credentials passed as secrets, or does it expect the consumer to configure credentials some other way given reusable-workflow job isolation?]
- **Default model identifiers under Bedrock**: The stages default to Anthropic model names for their agents. Bedrock addresses models by different identifiers, so a run that enables Bedrock but leaves the default Anthropic model names in place could reference a model Bedrock does not recognize. [NEEDS CLARIFICATION: when Bedrock is enabled, must the consumer supply Bedrock-compatible model identifiers through the existing per-stage model settings (pure pass-through), or should the pipeline translate its default Anthropic model tiers to Bedrock equivalents?]
- **Both an Anthropic credential and the Bedrock flag are supplied**: The feature must have a defined, non-ambiguous precedence — enabling Bedrock takes effect (the run uses Bedrock) even if an Anthropic credential is also present, rather than a race between providers.
- **Region and any inference-profile requirements**: Bedrock requests are region-scoped; a run must have the region configuration it needs, or fail with a clear message (see FR-009).
- **End-to-end validation happens elsewhere**: Per the request, the full Bedrock round-trip is validated in a separate consuming repository after this side is implemented; this feature's acceptance is that the flag and its required configuration are correctly plumbed through and that defaults remain safe.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST allow a consuming repository to select AWS Bedrock as the model provider for the pipeline's AI agents, via a pass-through flag set when the consumer calls a stage.
- **FR-002**: The Bedrock option MUST be exposed consistently across every pipeline stage that runs an AI agent, so a repository can run the entire lifecycle on Bedrock.
- **FR-003**: The pipeline MUST route the AWS configuration Bedrock requires (credentials and region) to the agent within each stage so that model requests reach the consumer's AWS account. [NEEDS CLARIFICATION: the exact delivery mechanism for AWS configuration into an isolated stage job — see Edge Cases.]
- **FR-004**: When Bedrock is selected, the pipeline MUST NOT require an Anthropic API key or OAuth token, and the absence of those credentials MUST NOT fail the run.
- **FR-005**: The Bedrock option MUST be off by default; a repository that does not opt in MUST continue to use the Anthropic API/OAuth path with behavior identical to today (no regression).
- **FR-006**: When Bedrock is selected, the consumer MUST be able to specify Bedrock-compatible model identifiers for each stage's agent, and the pipeline MUST convey them to the agent. [NEEDS CLARIFICATION: pass-through of consumer-supplied Bedrock model IDs vs. pipeline translation of its default model tiers — see Edge Cases.]
- **FR-007**: The Bedrock flag and its associated AWS configuration MUST be settable only through trusted pipeline configuration (stage inputs/secrets/repository configuration); they MUST NOT be settable by, or inferred from, untrusted issue or comment content.
- **FR-008**: When Bedrock is selected but the AWS configuration it requires is missing or invalid, the pipeline MUST fail with a clear, actionable message identifying what is missing, rather than failing opaquely or silently falling back to the Anthropic API.
- **FR-009**: Enabling Bedrock MUST NOT change any pipeline behavior other than the model provider used — the same stages, human review gates, artifacts, and lifecycle bookkeeping MUST apply.
- **FR-010**: If both an Anthropic credential and the Bedrock flag are supplied, the pipeline MUST resolve the provider deterministically (enabling Bedrock takes effect) rather than leaving the choice ambiguous.
- **FR-011**: The adoption documentation MUST describe how a consuming repository enables Bedrock — configuring AWS credentials and setting the Bedrock flag when calling the pipeline — consistent with the existing adoption guide.

### Key Entities *(include if data involved)*

- **Model Provider Selection**: The per-run choice of where an agent's model requests are served — the existing Anthropic API/OAuth path or AWS Bedrock. Attributes: which provider is active, whether it was explicitly enabled, and its default (Anthropic).
- **Bedrock Configuration**: The consumer-supplied, trusted configuration required to serve requests through Bedrock — the enablement flag, the AWS credentials/role, the AWS region, and any Bedrock-compatible model identifiers. Owned by the consuming repository, never derived from untrusted content.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A consuming repository can run every stage that uses an agent with model requests served by AWS Bedrock, providing only AWS configuration and the Bedrock flag — with no Anthropic API key or OAuth token.
- **SC-002**: With the Bedrock flag unset, 100% of existing runs behave identically to today, including repositories using an Anthropic API key or OAuth token (no regression).
- **SC-003**: A consumer enables Bedrock using only configuration in their own calling setup — they make no changes to the pipeline itself.
- **SC-004**: When AWS configuration is missing while Bedrock is enabled, the run fails with a message that names the missing configuration in 100% of such cases.
- **SC-005**: A maintainer can determine, from the adoption documentation alone, exactly what to configure to run the pipeline on Bedrock.

## Assumptions

- **Scope is AWS Bedrock only.** The request names Bedrock; other providers (e.g., Google Vertex) are out of scope for this feature, even though the same pass-through mechanism might later generalize to them.
- **The underlying agent already supports a Bedrock mode.** Enabling Bedrock is a matter of plumbing the flag and AWS configuration through the pipeline's stages to the agent; this feature does not implement a Bedrock client itself.
- **End-to-end Bedrock validation happens in a separate consuming repository** after this side is implemented (per the request). Acceptance here is correct plumbing of the flag and configuration plus safe, unchanged defaults — not a live Bedrock round-trip in this repository's own tests.
- **Model tiering defaults remain Anthropic model names** unless the consumer overrides them for Bedrock; the default (non-Bedrock) path is unchanged.
- **"Configured by consuming repos"** means the flag and AWS configuration are trusted maintainer/adopter configuration supplied through the pipeline's calling surface, consistent with how the pipeline already treats other secrets and inputs.
