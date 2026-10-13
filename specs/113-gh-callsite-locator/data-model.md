# Data Model: gh call-site locator

## Token (locator output)

| Field | Type | Notes |
|---|---|---|
| `kind` | enum `call` \| `mention` | `mention` only per FR-004 clauses (a)(b)(c) |
| `position` | enum `statement` \| `subst_first` \| `disallowed` | only for `call`; `disallowed` carries `reason` |
| `reason` | str \| None | e.g. `backtick`, `nested-subst`, `variable-subcommand`, `ansi-c`, `unquoted-heredoc`, `case-arm`, `unquoted-wrapper` |
| `mention_clause` | enum `quoted` \| `quoted-heredoc` \| `comment` \| None | which FR-004 clause proved it |
| `line` | int | 1-based within the `run:` block; caller adds block offset |
| `prefix_token` | str \| None | literal value of `GH_TOKEN=<value>` |
| `timeout` | bool | `timeout N` prefix present |
| `argv` | list[str] | literal words after `gh`; a word with expansion is marked `Dynamic` |

Invariants: classification uncertainty never yields `mention` (FR-006);
the subcommand word (and method flag for `gh api`) being `Dynamic` forces
`disallowed`.

## Call site (gate input, unchanged semantics)

Existing Gate 12 record: file, line, subcommand, resolved token
(`prefix > step env > job env`; composite `inputs.*` per call site),
required `(category, level)` set, job permissions. Built from a located
`Token` with `position != disallowed`.

## Corpus scenario

`id`, `files` (synthetic tree or single `run:` snippet), `expect`
(`pass` | `permission` | `disallowed` | `unresolvable` | `unknown-subcommand`
| `unused-composite`), `changed_from_969` (bool, only pass→disallowed
allowed, FR-014), `note`.

## Waiver (single-home)

One entry in `single-home-waivers.json`: file `verify-stop-point-recording.py`,
tracker = #889 (new checklist line), reason "script-call reader pending its
own lifecycle".
