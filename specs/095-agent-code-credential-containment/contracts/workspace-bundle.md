# Contract: workspace bundle

- Artifact `wc-gate-bundle-<site>` holds `bundle.git` and `meta.json`
  (`base_sha`, `head_sha`, `site`).
- Producer: the credential-bearing job, after the agent phase. Uploads with no
  token beyond the job's default artifact access.
- Consumer 1, the `gate-suite` job (`permissions: contents: read`, no App
  token, `persist-credentials: false`): checks out `github.sha`, verifies
  `git bundle verify`, checks out `head_sha`, runs the suite. Its absence of
  credentials is the property gate `verify-gate-suite-credential-free.py` holds.
- Consumer 2, the publisher: refuses to push unless `HEAD` equals the verdict's
  `head_sha`.
- A missing, unverifiable or oversized bundle makes the gate job write
  `outcome=fail` (reason in `first_failure`); it never skips.
- The gate job treats every byte of the bundle as hostile: no `uses:` or
  script path is resolved from the bundle checkout except the suite itself,
  and the contained-gate-suite composite comes from the trusted checkout.
