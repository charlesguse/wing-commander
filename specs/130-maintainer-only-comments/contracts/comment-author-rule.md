# Contract: Comment Author Rule

This contract is live. Gate `verify-maintainer-only-comments.py` (D7) enforces it; `auto-update-spec-kit-tests/t6_reply.sh` (run by lint-workflows.yml) covers the Spec Kit updater's reply context.

## Rule

A comment admits a stage run, or reaches an agent as context, only when both hold:
- its author's `user.type` is not `Bot`;
- its `author_association` is one of `OWNER`, `MEMBER`, `COLLABORATOR`.

Nothing about authorship, issue ownership or user id is consulted.

A stage's agent may also read the pipeline's own comments (its App's `<slug>[bot]` login): they are the pipeline's output, such as the question a reply answers, not a comment that steers it.

## Where it is enforced

| Surface | Kind | Enforcement |
|---|---|---|
| `wing-commander-2-clarify.yml` | wrapper `if:` | association only |
| `clarify.yml` | published stage | the check step before `lifecycle-gate`. A refused comment ends the job successfully, with no reaction, no notice and no draft change |
| `auto-update-spec-kit.yml` | published stage, `comment-reply` job `if:` | association only. `issue-author-id` is accepted and ignored |
| `auto-update-spec-kit.yml` | published stage, `comment-reply` agent context and read-back | the context holds the issue body, the pipeline's own comments and maintainers' comments; a choice counts only when it is a label the pipeline posted (tested by `t6_reply.sh`, not by Gate 174) |
| `wing-commander-9-pr-conversation.yml` / `pr-conversation.yml` | wrapper + stage | unchanged (spec 033 FR-019) |
| `wing-commander-issue-context` | shared comment filter (intake, board loop) | association only. Excluded comments are counted |
| `_shared/auto-release-e2e-clarify-decision.sh` | e2e assertion | association only, matching the stage |

## Relay paragraph (FR-008)

- The relay paragraph is appended to the comment that asks for clarification answers, whether intake or clarify posts it, when the lifecycle issue's own `author_association` is not in the maintainer set.
- Its single home is `.github/actions/wing-commander-requester-relay-note`. No other file carries its text.
- A reply from a non-maintainer is never answered.

## Compatibility

- No published input, secret or output is removed or renamed.
- The tightening ships non-breaking (research D2).
