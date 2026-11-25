One place to see which specs are real work, which are in flight, and which are parked.

**Lanes**
- **Roadmap (this issue):** specs the owner chooses. Only the owner applies `spec-request`; the pipeline and local sessions file spec-shaped work as `spec-proposal` and list it under "Proposed".
- **Maintenance (#889):** small defects found by stages, reviews and the watchdog.

### Goals
- [ ] **Auto-fix that finishes without the owner.**
  - [x] Spec-shaped work is filed as `spec-proposal`, not `spec-request` (#901).

### Proposed (waiting on the owner's `spec-request`)
Order agreed by the owner on 2026-11-25. Promote the next one when the previous one is past clarify.
1. #1188: workflow security after a post on dangerous Actions triggers. Owner direction 2026-11-23.
2. #1206: no gate runs the `.claude/skills/*/scripts` self-tests. Filed by the board loop 2026-11-24.
3. #1180: `run-local-gates.py` cannot complete within the 10-minute tool limit. Filed by the board loop 2026-11-22.

Not yet ordered (filed by the board loop; the owner places each in the Proposed order):
- #4242: Roadmap Proposed lines for loop-filed proposals. Filed by the board loop 2026-11-25 from Maintenance backlog line `bl-0123abcd`.

Not specs:
- #1167 (`trusted-file-tampered`) is already settled by #1181.
- Spec 123 lever (b), follow-up: low-progress handling. Deferred until lever (a)'s effect is measured; no issue yet.

Handled as fix PRs instead (owner, 2026-11-25): #1174, #1185, #1204, #1209, #1210 and #1211.

On 2026-10-16, 17 bot-filed proposals that were really small defects (#997–#1049) were folded into #889 or closed as already fixed, at the owner's direction.

### Owner decisions
- [x] 2026-11-22: #1098: lower the Haiku shadow trial's bar to 50 compared runs.

### Parked
- #1192: the gate registry's shell reader misreads shell shapes (parked 2026-11-25). From backlog line `bl-84505865`.
