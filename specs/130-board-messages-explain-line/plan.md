# Implementation Plan: Board loop messages explain the line

**Branch**: `spec/130-board-messages-explain-line` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

## Summary

Add one surface-independent renderer (`wc_message_parts.py`) that turns structured
named parts into the board loop's first comment, PR-body summary and review comment,
substituting gap text for any missing part. Wire it into `board-loop.yml` where the
review body is composed (replacing the bare "No findings.") and where the fix PR is
opened. Make fixed-text messages truthful by registering them with their
configuration conditions and gating the registry. Gate: `verify-board-message-parts.py`.
See [research.md](research.md).

## Technical Context

**Language/Version**: Python 3 (scripts), GitHub Actions YAML, bash/jq in workflows
**Primary Dependencies**: existing `board_spec_request_body.fenced_section`, `wc_convergence`, `board_backlog_edit.py`, `wc_session_record.py` as precedent
**Storage**: N/A (PR comments, #889 line text)
**Testing**: `verify-*.py` gates with checked-in fixtures; `run-local-gates.py`
**Target Platform**: GitHub Actions runners
**Project Type**: CI pipeline repository
**Performance Goals**: N/A
**Constraints**: body under 57000 UTF-16 units; fencing per #580; shared logic in one home
**Scale/Scope**: board-loop fix PRs only (FR-016)

## Constitution Check

- I Guide: built through the pipeline. Pass.
- II Model tiering: no new agent invocation; review agent keeps its model and turn budget. Pass.
- III GitHub-native: all output as PR/issue comments. Pass.
- V Untrusted content: agent/backlog text fenced; no new tool permissions. Pass.
- VII Two interfaces: the module is internal (`.github/scripts`); no workflow_call input/output/secret changes planned. If the review step needs a new input on a published stage, flag it as a deliberate widening. Pass, watch.
- VIII Green check: new gate with a fixture for every failure branch; reachable via gate registry. Pass.
- IX Deterministic judgment: part presence and gap substitution in code, not prompts. Pass.
- X Bounded autonomy: no change to merge conditions, switches or classes; only message text. Pass.

Post-design re-check: unchanged, pass. No Complexity Tracking entries.

## Project Structure

```text
specs/130-board-messages-explain-line/
├── plan.md  research.md  data-model.md  quickstart.md
└── contracts/message-parts.md
.github/scripts/
├── wc_message_parts.py              # new: renderer, schema, gap text
├── board-fixed-messages.json        # new: fixed-text registry
├── verify-board-message-parts.py    # new gate + fixtures dir
├── board_readiness.py  board_prove.py   # truthful wording; options-follow hold
├── board_backlog_lines.py           # tick record (FR-017)
.github/workflows/board-loop.yml     # review body, first comment, PR body
docs/reference.md                    # per its rule, if defaults/limits change
```

**Structure Decision**: single-repo scripts plus workflow wiring; no new directories beyond fixtures.

## Complexity Tracking

None.
