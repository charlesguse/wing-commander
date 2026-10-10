# Contributing to Wing Commander

Thanks for your interest! This project has an unusual property: **it builds
itself through its own pipeline.** Understanding that flow is most of what you
need to contribute well.

## How changes happen here

### Features: open an issue, let the pipeline drive

Feature work flows through the Spec-Driven Development pipeline this
repository publishes (see the [README](README.md#how-it-works)):

1. **Open an issue** describing what you want in plain language — the problem
   and the outcome, not the implementation. Your issue text becomes the input
   to the spec stage, so clarity here pays off.
2. **A maintainer applies the `spec-request` label.** This is the approval
   gate — the pipeline never runs on unlabeled issues, so opening an issue
   costs nothing and triggers nothing.
3. The pipeline drafts a spec PR, asks clarification questions on your issue
   (just reply to answer), then carries the feature through plan → tasks →
   implementation → final PR, with a maintainer reviewing every merge.

You don't need to run anything locally to propose a feature — the issue *is*
the contribution.

### Small fixes: ordinary PRs are welcome

Typos, doc corrections, and small workflow fixes don't need the pipeline.
Branch off `main`, make the change, open a PR.

For workflow or script changes, run the gate suite locally first — the same
checks `lint · workflows` runs on your PR, discovered from that workflow
rather than listed here, so this command does not go stale as gates are
added:

```bash
python .github/scripts/run-local-gates.py          # all of them
python .github/scripts/run-local-gates.py sentinel # or filter by name
```

Several of these gates *execute* shell extracted from the workflows, so they
need `bash` and `jq`. On Windows the runner finds Git Bash for you (the
`bash` on `PATH` there is usually the WSL launcher, which cannot see your
environment) — but invoke it with `python`, not `python3`, which is the
Microsoft Store stub.

Plus actionlint, pinned at v1.7.7 in `release.yml`:

```bash
actionlint -no-color -ignore 'property "job_workflow_sha" is not defined' \
  .github/workflows/*.yml
```

`release.yml` also enforces published-stage invariants: no `github.event.*`
or `vars.*` reads inside stages, no hardcoded `main`, and `--model` +
`--max-turns` on every agent step.

**Adding a check?** Name it `.github/scripts/verify-*.py` (or `.sh`) and wire
it into a gate step. Gate 10 fails the build if a `verify-*` script is not
invoked by any workflow, or if a gate step names a script that does not
exist — a verifier nothing runs drifts out of sync with the code it checks
and keeps reporting success, which has already happened here once.

### Authoring rule for `gh` call sites

Gate 12 checks that every `gh` call in a `run:` block runs under a token that
can do what the call does. It can only check a call it can find, so a `gh`
call must be written in a form the shared locator
(`.github/scripts/wc_gh_callsites.py`) can prove, or Gate 12 fails the call
with the file and line.

**Allowed**: in a `run:` block, `gh` is invoked

1. as a statement-level command, or
2. as the first command of a one-level `$(...)`,

optionally preceded by `GH_TOKEN=<value>` and/or `timeout N`, with the `gh`
subcommand — and for `gh api`, the `-X`/`--method` value — written as a
literal word.

**Not allowed** (Gate 12 fails closed): `gh` inside backticks, inside a
nested `$( $( ) )`, in a `${…}` value, behind `eval`/`env`/other wrappers,
with a subcommand or method taken from a variable, in an unquoted-heredoc
body or `$'…'` string, or as a `case` arm body inside `$( )`. In a `gh api`
call, a word holding an unquoted expansion (`-f body=$X`, `${X:--X GET}`)
is not allowed either, since the shell may split it into several words and
one of them could be a method flag; quote it.

**Mentions that need no rewriting**: `gh` in a quoted string with no `$(`
or backtick, in a quoted-delimiter heredoc body, or in a comment. To mention
`gh` inside an unquoted heredoc, quote the delimiter or reword.

## Where things live

| Path | What it is |
|---|---|
| `.github/workflows/<stage>.yml` | The published stages (any workflow declaring `workflow_call`) — what adopters pin. Changes here are interface-sensitive; see versioning below. The set is derived, never listed: `python .github/scripts/wc_published_stages.py`. |
| `.github/workflows/wing-commander-*.yml` | This repo's own thin wrappers (triggers + gates only). |
| `.github/actions/wing-commander-*/` | Shared composite actions (App token, preflight, metrics). |
| `.github/scripts/verify-*.py\|.sh` | The gate checks. Each must be invoked by a workflow (enforced by Gate 10). Run them all with `run-local-gates.py`. |
| `.github/scripts/wc_*.py` | Shared support modules for those checks — stage derivation, gate registry, and the plumbing for executing shell extracted from a workflow. |
| `docs/` | Setup, adoption, and architecture guides. |
| `specs/NNN-slug/` | The historical record: every feature's spec, plan, and tasks. |
| `.specify/`, `.claude/skills/speckit-*/` | Vendored [GitHub spec-kit](https://github.com/github/spec-kit) artifacts (pinned; the version is `speckit_version` in `.specify/init-options.json`) — not this project's code; upgraded via `specify init`, not edited by hand. |

The project [constitution](.specify/memory/constitution.md) governs design
decisions (model tiering, GitHub-native surfaces, security posture,
portability). PRs that conflict with a constitution principle will be asked
to reconcile with it first.

## Versioning and breaking changes

The published stages are consumed by pinned reference
(`@v1`, `@v2`, exact tags — see [docs/adoption.md](docs/adoption.md#version-pinning)).
Renaming or removing a stage input/secret/output, changing a
behavior-affecting default, or renaming a published filename is a **breaking
change** and ships only behind a new major tag with explicit migration notes.
Releases are cut deliberately via the `release.yml` `workflow_dispatch`, never
per-merge.

## Security

Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md).
Never include live credentials in issues, specs, or workflow runs.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
