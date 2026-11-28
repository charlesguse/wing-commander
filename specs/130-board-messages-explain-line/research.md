# Research: Board loop messages explain the line (spec 130)

No `[NEEDS CLARIFICATION]` markers remain in spec.md. The decisions below
settle the build choices the spec leaves to the plan.

## D1. One renderer module, surface-independent

- **Decision**: a new `.github/scripts/wc_message_parts.py` holds the part
  names, the result schema fragment, gap text and the renderer for both
  part sets (explanation, review). It knows nothing of the board loop.
- **Rationale**: FR-008 requires the schema and gate to be reusable by later
  surfaces; follow-up #1249 reuses the explanation renderer. Same shape as
  `wc_session_record.py` (refuses a record with a part missing).
- **Alternatives**: inline Python in `board-loop.yml` (rejected: CLAUDE.md
  "shared logic has exactly one home", and gates cannot import it).

## D2. Fencing reuse

- **Decision**: agent-written and backlog text is rendered through
  `board_spec_request_body.fenced_section` and `utf16_len` (the helpers the
  review body already uses, #562/#580). Only labels and fixed text sit outside.
- **Alternatives**: a new fence helper (rejected: second home).

## D3. Review comment: gap text at render time, schema at the agent

- **Decision**: the review agent's result schema gains an optional
  `report` object with the five parts. The renderer substitutes gap text for
  any absent/empty part (FR-007) and never emits "No findings." as the verdict;
  the clean case reads "no open findings on the fix for <id>" plus the parts.
  Parse failure keeps today's "Inconclusive" body (never "no findings").
- **Rationale**: the existing `Compose the review body` step is the one place
  the string is produced (board-loop.yml, around the `lines.append("No findings.")`).
  Making the parts optional in the schema keeps older runs rendering with gaps
  rather than failing.
- **Alternatives**: required parts in the schema (rejected: a missing part
  would drop the round as malformed, contradicting FR-007's gap-text rule).

## D4. First comment and PR body

- **Decision**: the fix step's agent returns the explanation parts; a
  deterministic step renders the first comment (parts FR-001..FR-003, one-screen
  lead, `<details>` overflow per FR-018) and a short PR-body summary (FR-004),
  passing the summary through the existing spec 121 closing-keyword refusal.
  "Options follow" is a legal Options value; a later comment must list them
  before readiness (FR-003). Readiness is blocked deterministically by
  `board_readiness.py` when the PR's first comment says options follow and no
  later options comment exists. (Readiness hold removed by owner decision,
  2026-11-28: the later comment still lists them, and readiness does not
  wait for it.)
- **Alternatives**: agent posts the comment itself (rejected: IX, and it
  could omit a part).

## D5. Fixed-text enumeration

- **Decision**: a registry `FIXED_MESSAGES` in `wc_message_parts.py`'s sibling
  data file `.github/scripts/board-fixed-messages.json` lists each fixed
  message (id, source file, variants keyed by auto-merge x kill switch x PR
  class, the claims each variant makes). A gate renders every variant for
  every configuration and fails on a claim a configuration contradicts, and on
  a fixed message in `board-loop.yml`/`board_*.py` that is not registered.
- **Known instances**: `board_readiness.py` "never merges, approves, or
  enables auto-merge" (being removed by a separate quick fix; this plan covers
  the rule and any remaining instances) and `board_prove.py` line 101
  "merged PR's own required checks" (main has no required checks).
- **Alternatives**: grep for banned phrases only (rejected: cannot check
  claims against configurations, FR-009/FR-011).

## D6. Backlog record (FR-017)

- **Decision**: extend the existing tick path in `board_backlog_lines.py` /
  `board_backlog_edit.py` with a one-line "decided: ... (link)" suffix, using
  the existing fetch-apply-write-readback edit.
- **Alternatives**: separate comment on #889 (rejected: the line should carry its own why).

## D7. Gate

- **Decision**: new `verify-board-message-parts.py`, registered in the gate
  registry and in lint-workflows.yml via the same path as sibling
  `verify-board-*` gates, with fixtures per part missing (Constitution VIII:
  every failure branch has a fixture).
- **Out of scope** (FR-016): lifecycle-review-gate, pr-conversation, watchdog,
  and the one-decision route (#1249).

## Decisions made without clarification

None; no markers in spec.md.
