# Contract: Labels and Cross-Links

## New label

| Label | Added to | Applied when | Cleared by |
|---|---|---|---|
| `board:stalled` | `docs/setup.md`'s manual label table (research.md D22) | round-budget exhaustion (FR-030), post-push backstop breach (FR-021), already-fixed hand-over (FR-012) | a human removing the label — the sole condition FR-010 reads for re-eligibility |

No `.github/labels.yml` or other machine-readable label config is
introduced — this repository documents labels manually today, and this
feature adds one row to that existing table rather than a new mechanism.

## Cross-links (FR-045)

Every artifact the loop creates outside the originating issue is
cross-linked onto it via `wing-commander-outstanding-task-item`
(research.md D9), the same composite spec 056's filing step already
reuses:

| Artifact | Phrase posted |
|---|---|
| Fix PR | `Fix opened` |
| `spec-request` spin-off | `Routed to spec-request` |
| Out-of-scope review-finding issue | `Found by the code review of #<PR>` |
| Prove-step re-drive | `Re-driven to prove the fix` |

Every phrase links the artifact's URL, matching the composite's existing
`"- [ ] $PHRASE — $ARTIFACT_URL"` shape — no second hand-written link
format (FR-045).
