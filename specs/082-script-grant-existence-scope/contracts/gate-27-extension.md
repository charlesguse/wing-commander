# Contract: Gate 27 (`verify-stage-tool-lists.py`) script-grant existence check, widened

FR-001 through FR-013 require the check enforced today (narrow: one surface,
one hardcoded prefix) to become the check the docstring already claims to be
scoped narrower than: any `Bash(<path>)` grant at any of three surfaces,
resolved against the tree or waived. This contract fixes the shape of the
widening so tasks.md implements against a decided interface rather than
reopening the design research.md already settled.

All of the below lands inside `.github/scripts/verify-stage-tool-lists.py`.
No other file changes except the new waiver JSON (contracts/waiver-schema.md)
and the module docstring (this file's "Docstring replacement" section).

## 1. Shared workflow loader (research.md D2/D6)

```python
def _load_workflows(root="."):
    """-> ({path: parsed_doc}, [error, ...]).

    Every collector below reads from this map instead of re-globbing and
    re-parsing .github/workflows/*.yml|*.yaml itself.
    """
    docs = {}
    errors = []
    paths = []
    for pat in WORKFLOW_GLOBS:
        paths.extend(glob.glob(
            os.path.join(root, WORKFLOW_DIR, pat).replace(os.sep, "/")))
    for path in sorted(set(paths)):
        rel = path.replace(os.sep, "/")
        try:
            with io.open(path, encoding="utf-8") as fh:
                docs[rel] = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            errors.append(
                "{0} could not be parsed as YAML and was skipped: {1}".format(
                    rel, exc))
    return docs, errors
```

`collect_sites` is rewritten to take `docs` (or call `_load_workflows`
itself and iterate the returned map) instead of its own inline glob loop;
its per-file body (the `for job in ... for step in ...` loop) is unchanged.

## 2. Token extraction and classification (research.md D1)

```python
GRANT_TOKEN = re.compile(
    r"^Bash\((?:(?:bash|sh|python|python3)(?:\s+-\S+)*\s+)?"
    r"([^\s:)]+)[^)]*\)$")


def _classify_grant_token(token):
    """-> repository-relative path, or None if `token` is a bare command.

    A leading `./` or any `/` makes it a path (FR-003); a bare command
    (`jq`, `git`, `yamllint`) has neither and returns None.
    """
    if token.startswith("./"):
        return token[2:]
    if "/" in token:
        return token
    return None


def _grant_path(tool):
    """-> repository-relative path for `tool` (a `Bash(...)` string), or
    None if it names no path (bare command) or is unresolvable (FR-008:
    contains an unexpanded `${{ ... }}` expression, checked on the RAW
    string before token extraction, since an expression may itself embed
    whitespace `GRANT_TOKEN` would otherwise mis-split on).
    """
    if "${{" in tool:
        return None
    m = GRANT_TOKEN.match(tool)
    if not m:
        return None
    return _classify_grant_token(m.group(1))
```

`SCRIPT_GRANT` and its hardcoded `.specify/scripts/bash/` prefix are removed
entirely — `GRANT_TOKEN` + `_classify_grant_token` replace it and apply to
every surface, including the previously-special-cased `.specify` grants
(which still resolve correctly: `.specify/scripts/bash/setup-plan.sh`
contains `/`, so `_classify_grant_token` returns it unchanged).

## 3. Two new collectors (research.md D2/D3)

```python
def collect_reusable_workflow_grants(docs):
    """-> [(site_label, [tool, ...]), ...] for jobs calling a local
    reusable workflow (`uses: ./.github/workflows/...`), reading
    `with.extra-allowed-tools` / `with.allowed-tools-override`.
    """
    sites = []
    for rel, doc in docs.items():
        for job_name, job in (doc.get("jobs") or {}).items():
            uses = str((job or {}).get("uses", ""))
            if not uses.startswith("./.github/workflows/"):
                continue
            with_ = job.get("with") or {}
            for key in ("extra-allowed-tools", "allowed-tools-override"):
                val = with_.get(key)
                if val is None:
                    continue
                label = "{0}:{1} ({2})".format(rel, job_name, key)
                sites.append((label, split_tools(str(val))))
    return sites


_ALLOWED_TOOLS_RE = (
    re.compile(r'--allowedTools\s+"([^"]*)"'),
    re.compile(r"--allowedTools\s+'([^']*)'"),
)


def _extract_allowed_tools(claude_args):
    for pattern in _ALLOWED_TOOLS_RE:
        m = pattern.search(claude_args)
        if m:
            return m.group(1)
    return None


def collect_claude_args_grants(docs):
    """-> [(site_label, [tool, ...]), ...] for claude-code-action steps
    whose `with.claude_args` carries a bare `--allowedTools "..."` string.
    """
    sites = []
    for rel, doc in docs.items():
        for job_name, job in (doc.get("jobs") or {}).items():
            for idx, step in enumerate((job or {}).get("steps") or []):
                if "claude-code-action" not in str((step or {}).get("uses", "")):
                    continue
                claude_args = (step.get("with") or {}).get("claude_args")
                if not claude_args:
                    continue
                allowed = _extract_allowed_tools(str(claude_args))
                if allowed is None:
                    continue
                step_name = step.get("name") or step.get("id") or "step[{0}]".format(idx)
                label = "{0}:{1}:{2!r}".format(rel, job_name, step_name)
                sites.append((label, split_tools(allowed)))
    return sites
```

Both return the same `(site_label, [tool, ...])` shape `collect_sites`
already exposes for its allowed-tools half, so the existence checker below
treats all three uniformly.

## 4. Waiver loading and the widened existence check (research.md D4)

```python
WAIVER_FILE = ".github/scripts/script-grant-waivers.json"


def load_waivers(root="."):
    """-> ({path: entry}, [error, ...])."""
    path = os.path.join(root, WAIVER_FILE)
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {w["path"]: w for w in data.get("waivers", [])}, []


def check_grant_existence(all_sites, waivers, root="."):
    """-> list of failure strings.

    `all_sites` is the concatenation of collect_sites()'s (label, allowed)
    pairs (allowed half only) with collect_reusable_workflow_grants() and
    collect_claude_args_grants()'s output — every surface, uniformly.
    """
    failures = []
    exists = {}
    waived_paths_seen = set()
    for label, tools in all_sites:
        for tool in tools:
            rel = _grant_path(tool)
            if rel is None:
                continue
            if rel in waivers:
                waived_paths_seen.add(rel)
                continue
            if rel not in exists:
                exists[rel] = _script_exists(root, rel)
            if not exists[rel]:
                failures.append(
                    "{0!r} grants {1!r}, but {2} does not exist in this "
                    "repository and carries no waiver in {3} - a stale "
                    "entry in a load-bearing list; drop the grant and any "
                    "prompt text that describes the step it ran, or add a "
                    "waiver entry if the path is absent by design.".format(
                        label, tool, rel, WAIVER_FILE))
    for rel, entry in waivers.items():
        if _script_exists(root, rel):
            failures.append(
                "{0} waives {1!r} (#{2}) as absent by design, but it now "
                "exists in the working tree - the waiver has gone stale; "
                "drop the entry.".format(
                    WAIVER_FILE, rel, entry.get("issue", "?")))
    return failures
```

`check_script_grants` (the old, composite-only, `.specify`-only function) is
removed; `run()` calls `check_grant_existence` with the concatenation of all
three collectors' output and the loaded waiver map instead.

## 5. `run()` wiring

```python
def run(root="."):
    docs, load_errors = _load_workflows(root)
    with io.open(os.path.join(root, TABLE_DOC), encoding="utf-8") as fh:
        table, errors, relative = parse_table(fh.read())
    sites, site_errors = collect_sites(root)  # unchanged signature; may be
                                               # rewired internally to use docs
    all_grant_sites = (
        [(label, allowed) for label, (allowed, _disallowed) in sites.items()]
        + collect_reusable_workflow_grants(docs)
        + collect_claude_args_grants(docs))
    waivers, waiver_errors = load_waivers(root)
    return (load_errors + site_errors + errors + waiver_errors +
            compare(sites, table, relative) +
            check_inspection_set(table) + check_mandated_commands(table) +
            check_grant_existence(all_grant_sites, waivers, root))
```

## 6. Docstring replacement (FR-013)

"WHAT IT CHECKS" bullet 3 becomes:

> 3. Every `Bash(<path>)` grant — at a `wing-commander-tool-args` composite
>    call site's `default-allowed-tools`, a reusable-workflow caller's
>    `extra-allowed-tools`/`allowed-tools-override`, or a bare
>    `claude-code-action` step's `claude_args --allowedTools` string — names
>    a script that exists, once any interpreter prefix (bare, `bash `, `sh `,
>    `./`, `python `/`python3 `, with an optional flag) is stripped and the
>    remaining token is a path (a leading `./` or a contained `/`) rather
>    than a bare command (`jq`, `git status`). A path absent from the
>    checkout by design (a run-time-provisioned directory) is recorded, with
>    its exact text and a reason, in `script-grant-waivers.json` — an entry
>    whose path *does* resolve is itself a failure, so the record cannot
>    outlive its reason. Spec Kit stopped shipping `update-agent-context.sh`
>    and both plan sites kept granting it, with the prompt still describing
>    the step it ran (#426); the same failure mode is now caught regardless
>    of which of the three surfaces carries the stale grant or which
>    directory the script lives in.

"WHAT IT DOES NOT CHECK"'s closing sentence becomes:

> Check 3 resolves every granted path at the three surfaces named above; a
> `Bash(<path>)` grant written anywhere else under `.github/workflows/` is a
> fourth surface the check does not yet cover, and adding it is a new
> finding, not a gap this check silently absorbs (specs/082).

The SELF-TEST section's closing sentence gains: "...and granting a script at
a reusable-workflow-caller or bare-`claude_args` surface that does not
exist, plus a waiver entry that has gone stale (specs/082)."

## `--self-test` wiring

See data-model.md item 5 / research.md D9 for the six new mutations. Each is
wired into `self_test()` the same way the existing ghost-grant replay and
case-mismatch fixture already are: call the function under test, assert the
failure list has the expected shape, increment `bad` and print `[FAIL]` on a
miss. No change to `--self-test`'s CLI surface or exit-code contract (0 clean,
1 with failures).
