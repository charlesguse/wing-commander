# Contract: `wc_finding_triage` (internal, `.github/scripts/`)

Layer: this repository's internal scripts (not the adopter-pinned surface;
no workflow input, secret or output is added or renamed — Principle VII).

## API

```python
route(finding: dict, in_scope: bool | None) -> tuple[str, str]
    # (outcome, reason); outcome in {"fix-now","record","drop","reject"}
    # in_scope True  -> reviewer finding in scope
    # in_scope False -> out of scope, or a stage proposal
route_all(findings, in_scope_of) -> list[Triaged]   # Triaged = (finding, outcome, reason)
render_triaged(records: list[dict]) -> str
    # markdown; one line per drop/reject: "- `<title>` -- dropped: <reason>"
    # or "- `<title>` -- rejected: silent, no description"; "" if none.
silent_note(finding) -> str | None
    # the one-line description for a recorded finding's body, else None
```

## Guarantees

1. `route` never returns `drop` for `severity == "important"` or
   `security is True`.
2. `route` never returns `drop` for a finding whose class is absent or
   unrecognised.
3. `route` returns `reject` for silent + no/invalid description, for any
   severity; `reject` is never rendered as dropped.
4. Same `finding` and `in_scope` give the same result on both call sites.
5. `render_triaged` lists every `drop` and `reject` record exactly once, with
   its literal reason; titles are rendered as code spans with backticks
   removed and `<!--` broken.
6. Pure: no I/O, no environment, no network.

## Wire changes (optional fields, schemas accept them)

`board-review-finding.schema.json` and `stage-finding.schema.json` gain
`failure_class`, `silent_description`, `severity`, `security`; none is
`required`; an unrecognised `failure_class` value must still pass schema
validation (the router treats it as absent).

## Consumers

- `lifecycle-review-gate.yml`: review job *extract* (annotate), *Compose the
  review body* (render), disposition *Partition…* (filter before `[:3]`).
- `wing-commander-stage-findings/action.yml`: *Extract, validate, cap, and
  prepare findings* (filter before cap) and *Emit summary* (render).
- NOT consumed by `board-loop.yml` or `pr-conversation.yml` (out of scope).

## Gate

`verify-finding-triage-report.py` (see plan.md): runs on every PR.
