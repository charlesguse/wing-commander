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
to `gh` across an expansion, brace list or glob (`${X:-g}h`, `g$X`,
`$HOME/bin/gh`, `{g,}h`), by a path (`/usr/bin/gh`), behind `env`/`sudo`/
`xargs`/other wrappers, with a subcommand or method taken from a variable,
in an unquoted-heredoc body or `$'…'` string, or as a `case` arm body
inside `$( )`. In a `gh api` call, a word holding an unquoted expansion
(`-f body=$X`, `${X:--X GET}`) is not allowed either, since the shell may
split it into several words and one of them could be a method flag; quote
it.

**Strings a shell runs are not read** (owner decision 2026-10-12, option
(c) on #993, which keeps the locator small): any `gh` word anywhere in a
string or stream that a shell or evaluator executes fails as a disallowed
form, however it is quoted. That covers the arguments of
`sh`/`bash`/`zsh`/`dash -c`, `eval`, `trap`, `source`/`.`, `ssh`, `su -c`
and `docker`/`podman exec|run … sh -c`; a backtick body; the body of a
heredoc or here-string fed to a shell or evaluator; and anything piped or
process-substituted into a shell (every `gh` earlier in the `run:` block
that is not itself an allowed call counts). `gh` spelled across quotes or
an expansion in such a string (`sh -c 'g""h api'`, `g$X`, `${X:-g}h`)
fails too. A string with no `gh` in it passes untouched.

**Variables as commands**: a command word that is a variable or expansion
(`$CMD`, `"$@"`, `${X:-…}`, the `$SUDO` of `$SUDO gh`), and an `eval`,
backtick or unquoted heredoc body holding an expansion, fails as a
disallowed form when the `run:` block also holds a `gh` word that is
neither a located call nor a provable mention (`GH=gh`, `set -- gh api x`).
Gate 12 cannot see what a variable holds, so never run `gh` through one.

**Mentions that need no rewriting**: `gh` in a quoted string with no `$(`
or backtick, in a quoted-delimiter heredoc body, or in a comment, unless
a shell runs that string or body as a script. To mention
`gh` inside an unquoted heredoc, quote the delimiter or reword.
