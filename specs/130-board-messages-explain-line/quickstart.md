# Quickstart: validating spec 130

Prerequisites: repository checkout, Python 3.

1. Gate suite: `python .github/scripts/run-local-gates.py` (includes
   `verify-board-message-parts.py` once built). Expect pass.
2. Renderer fixtures: `python3 -I .github/scripts/verify-board-message-parts.py`
   Expect: every fixture renders all parts; each missing-part fixture shows gap text.
3. Negative check: temporarily delete a part from a rendered fixture expectation;
   the gate must fail (Constitution VIII).
4. Fixed text: the gate's enumeration mode renders each registered message for each
   auto-merge x kill-switch x class combination; expect zero contradictions.
5. After merge (prove-after-merge): drive the board loop on one backlog line; check
   the first comment has all six parts, the review comment all five and names the id,
   and the ticked line carries the one-line record with a link (the #1202 / bl-b9677278
   shape is the reference). SC-005.

Contract: [contracts/message-parts.md](contracts/message-parts.md).
Data: [data-model.md](data-model.md).
