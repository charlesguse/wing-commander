# Data Model: 095

## Workspace bundle (artifact `wc-gate-bundle-<site>`)

| Field | Notes |
|-------|-------|
| `bundle.git` | `git bundle` of `<base-sha>..<head-sha>` |
| `meta.json` | `{ "base_sha", "head_sha", "site" }` |

Produced by the credential-bearing job after its agent phase and any local
commit; consumed only by the gate job and the publisher. Content-addressed:
`head_sha` is the identity.

## Gate verdict (artifact `wc-gate-verdict-<site>`)

Schema: [contracts/gate-verdict.schema.json](contracts/gate-verdict.schema.json).

| Field | Type | Rule |
|-------|------|------|
| `schema_version` | int | `1` |
| `site` | enum | `board-fix`, `board-review-fixup`, `implement-cycle` (`implement-retry` if R6 keeps it) |
| `trusted_sha` | sha | must equal `github.sha` of the reading run |
| `head_sha` | sha | must equal the SHA about to be pushed |
| `outcome` | enum | `pass` \| `fail` — nothing else is accepted |
| `first_failure` | string | raw first `FAIL` line or `gate suite exited <rc>`; untrusted text |
| `exit_code` | int | suite exit status |

## Reader result (step outputs)

`outcome` (`pass`/`fail`), `first-failure` (sanitised via `wc_step_output.py`),
`reason` (why the reader chose `fail` when the artifact was absent or invalid).

## State transitions

```text
agent done → bundle uploaded → gate-suite job → verdict uploaded
           → reader: valid & pass ──→ kill-switch re-check → push
           → reader: valid & fail ──→ stalled comment (fenced), no push
           → reader: absent/invalid/mismatch/cancelled ──→ treated as fail
```

## Hardened push call (composite inputs)

`branch`, `token` (from the credential-bearing job only), `expected-head-sha`.
Fixed internally: `core.hooksPath=/dev/null`, empty `GIT_CONFIG_GLOBAL`,
`GIT_CONFIG_NOSYSTEM=1`, explicit URL from `github.server_url` + repository.
