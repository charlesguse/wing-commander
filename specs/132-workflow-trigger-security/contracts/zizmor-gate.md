# Contract: `verify-zizmor.py`

**Layer**: consuming instrument (a repo-internal gate); no published-contract change.

## Invocation
`python3 .github/scripts/verify-zizmor.py [--self-test] [--root DIR]`

Registered in the gate registry; invoked by lint-workflows.yml and by `run-local-gates.py` with identical arguments. Triggered by changes to `.github/workflows/**`, `.github/actions/**`, `.github/zizmor.yml`, `zizmor-pin.txt`, `zizmor-findings-waivers.json` and the script.

## Behaviour
1. Verify `zizmor --version` equals the pin; otherwise exit 1 ("analyser missing or wrong version").
2. Discover the file set by glob (`.github/workflows/*.y*ml`, `.github/actions/**/action.y*ml`). Empty set: exit 1.
3. Run `zizmor --offline --format json --config .github/zizmor.yml <paths>`. Unparsable output: exit 1.
4. Map each finding to `(file, audit, location)`; subtract register records.
5. Exit 1 listing `file:line audit` for each unwaived finding, and each stale record by key.
6. Check `.github/zizmor.yml` carries a non-empty reason for the disabled `self-repository` audit.
7. Exit 0 only when 4–6 are clean.

## Fixtures (one per failure branch)
unwaived finding; stale record; analyser missing; wrong version; empty file set; unparsable output; self-repository reason removed; tag-pinned action outside the trusted set; second trusted-publisher copy; analyser `unpinned-uses` policy differing from the home.

## Register schema
See [findings-register.schema.json](findings-register.schema.json).
