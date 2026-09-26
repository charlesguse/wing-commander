# Contract: `script-grant-waivers.json` schema and shipped content

FR-006/FR-007 require a waiver file distinct in shape from the repository's
existing pattern+count waiver files (research.md D4). This contract fixes
the schema and the exact two entries the repository needs on day one
(research.md D0), so tasks.md writes the file once, against a decided shape.

## Schema

```json
{
  "$comment": [
    "Registered absent-by-design script grants for Gate 27's script-grant",
    "existence check (.github/scripts/verify-stage-tool-lists.py, check 3).",
    "See specs/082-script-grant-existence-scope.",
    "",
    "Unlike single-home-waivers.json / stage-invariant-waivers.json /",
    "spec-branch-push-waivers.json, this file has no `pattern` or `count`",
    "field: FR-006 requires each entry to name the EXACT granted path, not a",
    "prefix, glob, or regex, so an entry cannot silently widen to cover a",
    "path it was never reasoned about.",
    "",
    "Every entry is stale-checked in the direction that matters here: if the",
    "named path EXISTS in the working tree, the gate fails, naming the entry",
    "-- the reason it was recorded as absent has stopped being true, and the",
    "grant should be checked for real rather than waived."
  ],
  "waivers": [
    {
      "path": "<exact granted path, interpreter prefix and leading ./ already stripped>",
      "issue": "#<tracking issue>",
      "reason": "<why this path is expected to be absent from a checkout>"
    }
  ]
}
```

**Field notes**:
- `path` is compared byte-for-byte, case-sensitively, against the same
  repository-relative string `_grant_path()` (contracts/gate-27-extension.md
  §2) produces for a granted token — i.e. already stripped of any
  `bash `/`sh `/`python `/`python3 -I ` prefix and any leading `./`.
- `issue` and `reason` are documentation only; the gate does not parse them,
  matching how `single-home-waivers.json`'s `issue`/`reason` fields are
  read by a human, not by `verify-single-home-idioms.py`'s comparison logic.

## Shipped content (research.md D0)

```json
{
  "$comment": [ "... (see Schema above) ..." ],
  "waivers": [
    {
      "path": ".wing-commander-pipeline/.github/scripts/git_read.py",
      "issue": "#599",
      "reason": "`.wing-commander-pipeline/` is the pipeline's own run-time-checked-out copy of itself, created by a checkout step during a workflow run and never committed to this repository (git status shows it untracked, not gitignored, in exactly the sessions that create it). Four grants resolve here today: implement.yml's implement.post-progress-comment, pr-conversation.yml's pr-conversation.classify, watchdog.yml's watchdog.diagnose (all three composite call sites), and auto-update-spec-kit.yml's evaluate-path job's bare claude_args --allowedTools (see specs/082's research.md D0). One entry covers all four, since FR-006 waives the exact path, not the site."
    },
    {
      "path": "e2e-scratch/.specify/scripts/bash/create-new-feature.sh",
      "issue": "#436",
      "reason": "e2e-scratch/ is created at run time by auto-update-spec-kit.yml's e2e provisioning step from a candidate Spec Kit release under test and is never committed. Both spellings of the grant (bare and `bash <path>`, on the 'Run e2e agent-driven stage' step) resolve to this same path; one entry covers both, since FR-006 waives the exact path, not the literal grant string."
    }
  ]
}
```

## Verification

`load_waivers()` (contracts/gate-27-extension.md §4) parses this file with
`json.load` — a malformed file is an uncaught `json.JSONDecodeError`, exactly
the class of loud failure Constitution VIII expects (the file is committed
and reviewed like code; it is not user input the gate needs to degrade
gracefully against). `--self-test`'s new mutation (research.md D9, case 6)
exercises the reverse-direction staleness check against a synthetic
temp-directory fixture, not against either of the two real entries above —
neither real entry is expected to ever resolve, so mutating them in place
would require deleting a real, load-bearing pipeline-checkout convention
just to test the gate, which the self-test's existing fixture pattern
(`tempfile.mkdtemp()`) avoids entirely.
