# Contract: GitHub Security-Policy File Convention

This feature's only external interface is a filename/location convention that
GitHub's platform recognizes automatically — there is no API, CLI, or schema.
This document records that contract so implementation and review can verify
it precisely.

## Producer / Consumer

- **Producer**: This repository (the `SECURITY.md` file added by this
  feature).
- **Consumer**: GitHub's repository UI — specifically the Security tab and
  the "Report a vulnerability" flow.

## Contract terms

1. **Path**: The file MUST be located at the repository root:
   `SECURITY.md` (GitHub also recognizes `.github/SECURITY.md` and
   `docs/SECURITY.md`, but this repository uses the root location per the
   spec's Assumptions section).
2. **Filename**: MUST be exactly `SECURITY.md` (GitHub's match is
   case-insensitive, but the canonical casing is used here).
3. **Discovery surface**: Once present, GitHub links this file from:
   - The repository's Security tab ("Security policy" section).
   - The repository's file listing at the root.
4. **Content requirements imposed by this feature's spec** (not by GitHub —
   GitHub does not validate content, only presence/location):
   - Exactly one top-level (`#`) heading.
   - At most three body paragraphs.
   - States the private-vulnerability-reporting channel and that public
     issues are not the reporting channel.
   - States that pipeline runs execute Claude agents with repository write
     access via a GitHub App, and that credential-handling reports are in
     scope.

## Out of scope

- Enabling GitHub's private vulnerability reporting feature itself is a
  repository-setting dependency, not part of this file's contract (see the
  spec's Assumptions section). This document does not verify that setting.
- No programmatic API contract exists — this is a static Markdown file
  consumed by GitHub's UI conventions only.

## Verification

Satisfied when:
- `SECURITY.md` exists at the repository root.
- Manual read-through confirms the four content requirements above (mirrors
  `data-model.md`'s validation rules and the spec's SC-001…SC-004).
