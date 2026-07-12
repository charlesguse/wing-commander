# Quickstart: Validate the SECURITY.md Policy

This feature has no build, install, or run step — it is a single Markdown
file. Validation is a manual read-through plus a couple of local checks.

## Prerequisites

- The implementation PR has added `SECURITY.md` at the repository root.
- No other file in the diff.

## Validate structurally (FR-006, FR-007, SC-002, SC-004)

From the repository root, on the implementation branch:

```bash
git diff --stat main...HEAD          # expect exactly one file: SECURITY.md
grep -c '^# ' SECURITY.md            # expect exactly 1 (one top-level heading)
awk 'BEGIN{RS=""} END{print NR}' SECURITY.md   # expect <= 4 (1 heading "paragraph" + <=3 body paragraphs)
```

## Validate content (FR-002…FR-005, SC-001, SC-003)

Read `SECURITY.md` and confirm each of the four required disclosures is
present, matching `data-model.md`'s validation rules and
`contracts/security-md-convention.md`:

1. Directs reporters to GitHub's private vulnerability reporting (Security
   tab → "Report a vulnerability") for this repository.
2. States that public issues are not the channel for vulnerability reports.
3. States that pipeline runs execute Claude agents with repository write
   access via a GitHub App.
4. States that credential-handling reports (leaked tokens, overly broad
   permissions) are explicitly in scope.

## Validate GitHub surfacing (SC-001)

On GitHub (after merge to the repository's default branch, or by previewing
the branch):

1. Open the repository's **Security** tab.
2. Confirm a "Security policy" section appears and links to `SECURITY.md`.
3. Confirm reaching the reporting instructions took exactly one interaction
   (one click) from the Security tab.

## Expected outcome

All checks above pass with no follow-up changes to any file other than
`SECURITY.md`.
