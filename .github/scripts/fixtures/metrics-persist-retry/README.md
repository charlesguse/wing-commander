# Fixtures for verify-metrics-persist-retry.sh

This gate's fixture is a live local git repository, not a static file — a
checked-in `.git` directory does not serialize cleanly and a bare repo's
value here is its behavior under a real `git push` rejection, not its bytes.
Both fixtures are built at self-test time by the script itself:

- **Eventually-successful race** (`test_concurrent_writers_both_survive`):
  a bare origin seeded with an empty `records.jsonl` on the `metrics`
  branch (mirroring R8's orphan-branch creation), two clones ("writer A",
  "writer B") racing to append distinct records, with writer B's push
  deliberately made to land second so it is rejected and must retry.

- **Sustained-contention exhaustion** (`test_sustained_contention_fails_loudly_naming_the_key`):
  the same seeded origin, with a background "hostile" writer landing one
  throwaway commit ahead of every attempt the victim writer makes, so the
  victim's push is rejected on every one of its bounded attempts.

Run `bash .github/scripts/verify-metrics-persist-retry.sh --self-test` (or
`python3 .github/scripts/run-local-gates.py metrics-persist-retry`) to build
and exercise both.
