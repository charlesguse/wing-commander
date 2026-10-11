# Contract: authoring rule for `gh` call sites

To be published verbatim as one section in the contributor documentation
(FR-001/FR-002); every other mention points at it.

**Allowed**: in a `run:` block, `gh` is invoked
1. as a statement-level command, or
2. as the first command of a one-level `$(...)`,

optionally preceded by `GH_TOKEN=<value>` and/or `timeout N`, with the `gh`
subcommand — and for `gh api`, the `-X`/`--method` value — written as a
literal word.

**Not allowed** (Gate 12 fails closed): `gh` inside backticks, inside a
nested `$( $( ) )`, in a `${…}` value, in a command word that could expand
to `gh` across an expansion or glob (`${X:-g}h`, `g$X`, `$HOME/bin/gh`,
`${CMD}`, `{g,}h`),
by a path (`/usr/bin/gh`), behind `eval`/`env`/other wrappers,
with a subcommand or method taken from a variable, in an unquoted-heredoc
body or `$'…'` string, or as a `case` arm body inside `$( )`. In a `gh api`
call, a word holding an unquoted expansion (`-f body=$X`, `${X:--X GET}`)
is not allowed either, since the shell may split it into several words and
one of them could be a method flag; quote it. A command word that is one
bare `$CMD` or `$(…)` is not checked, so never run `gh` through one.

**Mentions that need no rewriting**: `gh` in a quoted string with no `$(`
or backtick, in a quoted-delimiter heredoc body, or in a comment. To mention
`gh` inside an unquoted heredoc, quote the delimiter or reword.
