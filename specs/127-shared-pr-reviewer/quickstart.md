# Quickstart: validating the shared reviewer (127)

Prerequisites: the implement stage's changes merged to a branch, `python .github/scripts/run-local-gates.py` green.

1. **Unit and fixture tests** (no agent): run the gate suite. Covered: identity assignment and citation checks (Story 2 scenarios 1-7, SC-004), open-set folding incl. comment-shaped dismissals ignored (scenario 8), blocking rule, verdict order incl. missing code-run (SC-004 last clause), run confirmation cases (SC-002), budget/hand-off (Story 5), `read_round_records` ignoring a shared record (Story 3.4).
2. **Refusal drill**: dispatch the wrapper from a non-default ref; expect no agent step run, no comment, a refusal in the summary (SC-003). Dispatch on a spec/final PR number; same.
3. **Isolation drill** (SC-008): run the code-run job against the checked-in hostile fixture tree; the verifier asserts no secret visible, staged JSON unaffected by overwrite attempts, a third command not run, and agent jobs have no write token.
4. **Live round**: on a real session fix PR, dispatch from `main` on the head the hand review covers; expect exactly one record comment, no push/label/merge/approval (SC-001), record confirmed by the reader script.
5. **Memory**: dispatch round 2 with a requester dismissal for one open finding; expect the dismissal in the new record and the finding absent from the open set; the comparison script lists the pair beside the hand review (SC-007).
6. **Budget**: dispatch until 5 confirmed rounds, then once more; expect no agent and a hand-off record.

Contracts: `contracts/round-record.md`. Data: `data-model.md`.
