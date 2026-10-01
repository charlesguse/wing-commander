# Contract: Closed-Without-Landing Notice

For FR-017. A new step in `board-loop.yml`'s `select` job, sibling to its
existing "Detect a merge whose proof run never started (FR-010b)" step —
that step's own header already calls `select` "the natural periodic check
point" for this shape of orphan-detection scan, and this feature reuses
that same job rather than adding a new scheduled workflow (research.md's
Dependencies note: no workflow listens for `issues: closed` today, and this
feature does not add one — it extends the existing cron-driven scan
instead).

## Detection (research.md D8)

1. List CLOSED issues labelled `spec-request`, authored by the loop's own
   bot login (`bot-login`, the same input `wing-commander-board-stop-check`
   already receives) — these are exactly the issues the loop itself filed.
2. For each, find the `specs/<NNN-slug>/spec-meta.json` whose `issue` field
   equals its number (a checkout of `main`, same as any other step in this
   job that reads repository content).
3. If that `spec-meta.json`'s `stage` never reached the finalize stage's
   terminal completed value, this spec-request "closed without its work
   landing" (FR-017's phrase).
4. If no `spec-meta.json` names this issue at all (intake never produced a
   spec from it), it also counts as "closed without its work landing" —
   there is no further stage to have completed.

## Notice (FR-017, idempotent)

Two comments, one per closure (never re-posted on a later run that finds
the same already-notified closure):

- On the **originating issue** disposed of by this spec-request (found via
  its own `spec_request` marker field, data-model.md): "reopening it
  returns the request to the board."
- On the **closed spec-request** itself: the same fact, stated where its
  own lifecycle ended (Principle IV: "Any manual step that survives must
  be reported explicitly to the lifecycle issue").

Idempotency is checked the same way the disposition module's own
comment-presence check works (contracts/duplicate-disposition.md step 4/6):
before posting, the step looks for its own previously-posted notice comment
(a recognizable marker, e.g. an HTML comment following the
`wing-commander-board-item` marker's own convention) on the target issue,
and skips posting if found.

## Relationship to re-admission (D6)

This notice does not itself change eligibility — a maintainer reopening
the originating issue after reading the notice is what triggers the
eligibility carve-out (contracts/eligibility-and-readmission-delta.md),
already keyed off the spec-request's live state resolving CLOSED. The
notice's only job is telling the maintainer that reopening is the action
available to them (Principle IV: no manual step survives unreported).
