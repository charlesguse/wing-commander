One place to see which specs are real work, which are in flight, and which are parked.

**Lanes**
- **Roadmap (this issue):** specs the owner chooses. Only the owner applies `spec-request`; the pipeline and local sessions file spec-shaped work as `spec-proposal` and list it under "Proposed".
- **Maintenance (#889):** small defects found by stages, reviews and the watchdog.

### Goals
- [ ] **Auto-fix that finishes without the owner.**
  - [x] Spec-shaped work is filed as `spec-proposal`, not `spec-request` (#901).

### Proposed (waiting on the owner's `spec-request`)
- Spec 123 lever (b), follow-up: low-progress handling. Deferred until lever (a)'s effect is measured; no issue yet.
- #1110: the lifecycle review gate converges. Owner asked for it 2026-11-06.
- #1174: `verify-hardened-push` fails in the implement sandbox with a linked-worktree push error. Filed by the board loop 2026-11-22.
- #1215: board loop messages explain the line. Owner direction 2026-11-25.

On 2026-10-16, 17 bot-filed proposals that were really small defects (#997–#1049) were folded into #889 or closed as already fixed, at the owner's direction.

### Owner decisions
- [x] 2026-11-22: #1098: lower the Haiku shadow trial's bar to 50 compared runs.

### Parked
- #1192: the gate registry's shell reader misreads shell shapes (parked 2026-11-25). From backlog line `bl-84505865`.
