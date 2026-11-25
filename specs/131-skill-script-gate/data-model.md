# Data Model

Plain in-memory records inside `verify-skill-scripts.py`; nothing persists.

| Entity | Fields | Notes |
|---|---|---|
| SkillScript | `path`, `skill`, `tree` (AST), `has_self_test` | discovered by globbing `.claude/skills/*/scripts/*.py` |
| Reach | `script`, `module`, `name` or `None`, `kind` (`from-import`, `attribute`, `module`), `line` | one per cross-tree name a script uses |
| ModuleNames | `module`, `names` (frozenset of top-level names) | parsed from `.github/scripts/<module>.py` |
| Finding | `script`, `module`, `name`, `reason` (`missing-name`, `missing-module`, `self-test-failed`, `unrecognised-loader`) | printed as `skill-script: <path>: <module>.<name> <reason>`; any finding exits 1 |

Validation rules:

- A Reach with `kind=module` passes when the module file exists.
- A Reach with a name passes when the name is in ModuleNames, or is a
  submodule file next to it.
- Zero discovered skill scripts is an error (a gate with an empty subject
  fails loudly, Principle VIII).
- A SkillScript with `has_self_test` produces one subprocess run; non-zero
  exit or timeout produces a Finding.
