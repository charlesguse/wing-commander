# merge-evidence fixtures

Synthetic cases for `verify-merge-evidence.py` (specs/125-merge-evidence-audit).
`_base.json` holds one snapshot per kind; each `verdict-*/case.json` and
`audit-*/case.json` names a `base`, a shallow `patch` over it, and what it
`expect`s. `sc003/` is filled only by the maintainer capture (T036 / tasks.md
T029) and is empty until then.
