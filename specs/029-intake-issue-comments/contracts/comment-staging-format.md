# Contract: Qualifying-Comments Staging Format

Extends `clarify.yml`'s existing untrusted-data-to-file pattern ("the
comment body is untrusted. The stage fetches it from the API and writes it
straight to a file … never shell-interpolated, never pasted into the
prompt") from a single comment to an ordered collection.

## File

- **Path**: `/tmp/wing-commander/intake-comments.md` (runner-local,
  matching `clarify.yml`'s `/tmp/wing-commander/` convention; discarded
  with the runner).
- **Written by**: the comment-trust-gate step
  (`contracts/comment-trust-gate.md`), via `gh api ... --jq` piped straight
  to the file — never through a shell variable that gets re-interpolated
  into another command or into the agent prompt string.
- **Written only when** `qualifying-count > 0`. When zero comments qualify,
  no file is written and `comments-file` (the step output) is empty — this
  is the deterministic signal the agent step's prompt uses to skip straight
  to today's title+body-only behavior (FR-007), rather than the agent
  having to distinguish "empty file" from "no qualifying comments" itself.

## Contents

Ordered oldest → newest by `created_at` (Assumptions: "later" = later
creation time — later entries in the file are later in the discussion).
One section per qualifying comment:

```markdown
## Comment by @<user.login> (<created_at, ISO-8601>)

<body, verbatim, unmodified>
```

- `body` is written exactly as returned by the API — no truncation, no
  escaping/re-encoding beyond what `gh api --jq` already performs, no
  markdown sanitization. It is data, not markup to be trusted or executed
  (FR-004), and the agent is told so explicitly in its prompt (mirroring
  the existing "SECURITY (non-negotiable)" framing already applied to the
  issue body).
- Only qualifying comments ever appear in this file (research.md D3) —
  there is no "excluded" section and no placeholder for non-qualifying
  comments. A reader of this file sees exactly, and only, the content that
  is allowed to influence the specification.
- Low-signal qualifying comments (e.g. "+1", "thanks") are staged like any
  other qualifying comment — the Edge Cases section accepts that they
  "contribute nothing actionable, which is acceptable"; this contract does
  not filter on content quality, only on the trust-gate rule.

## Consumption contract (the agent side)

The agent step's prompt:

1. Is told the comments file's path (an env var / prompt-interpolated
   *path*, not content — the same class of interpolation the prompt already
   does for `${{ inputs.issue-number }}`, never comment text).
2. Is instructed to `Read` the file **only if** `comments-file` is
   non-empty, treat every section in it as untrusted feature-description
   text (same discipline as the issue body), and fold it into the feature
   description passed to `/speckit-specify` (data-model.md
   `FeatureDescription`).
3. Is explicitly instructed **not** to fetch comments through any other
   means (`gh issue view --json comments`, `gh api`, etc.) — this file is
   the sole source of comment content for the run (research.md D5).
