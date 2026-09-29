# Quickstart: Validating A Failed `gh api` Read Never Becomes Data

Prerequisites: a checkout with this feature implemented, `python3` on
PATH.

## 0. Confirm the scoping this plan was written against (research.md D1)

```bash
grep -rnE '[A-Za-z_][A-Za-z0-9_]*="?\$\(\s*gh api\b' .github/workflows .github/actions | grep -v '/tests/'
```

Expected: zero results classified `unsafe` by the new gate below once
User Story 1's audit has landed — every site is either already safe,
corrected, or carries a `# wc-gh-api-error-exempt: <reason>` marker
(FR-001/FR-014). Re-running this grep is how a reviewer confirms the
audit's inventory did not silently shrink between planning and
implementation.

## 1. The capture-check gate (User Story 2, FR-001/002/005/006/007/008/013/014)

```bash
python .github/scripts/verify-gh-api-error-capture.py --self-test
python .github/scripts/verify-gh-api-error-capture.py
```

Expected: the self-test's fixture list (contracts/gh-api-capture-check-
cli.md) all pass; the live run reports zero unsafe sites and zero bare
markers against this repository's real tree (SC-001).

To see it fail (constitution VIII: prove the gate can fail its own
subject):

```bash
cp .github/actions/wing-commander-fold-commit/action.yml /tmp/fold-commit-orig.yml
# Simulate reintroducing the #497 shape: a capture whose failure branch
# only logs, never reassigns or exits.
python - <<'PY'
import re
p = ".github/actions/wing-commander-fold-commit/action.yml"
text = open(p).read()
text = text.replace(
    'bot_login="$(gh api user --jq .login 2>/dev/null || true)"',
    'if ! bot_login="$(gh api user --jq .login 2>/dev/null)"; then\n'
    '          echo "::warning::could not resolve bot login"\n'
    '        fi'
)
open(p, "w").write(text)
PY
python .github/scripts/verify-gh-api-error-capture.py
# expect: ::error:: naming action.yml, the bot_login line, "bot_login",
# and one of reassign/exit/wc-gh-api-error-exempt
mv /tmp/fold-commit-orig.yml .github/actions/wing-commander-fold-commit/action.yml
```

## 2. Non-covered subcommands are ignored (FR-013's boundary)

```bash
grep -n "gh issue view" .github/actions/wing-commander-lifecycle-gate/action.yml
python .github/scripts/verify-gh-api-error-capture.py
```

Expected: the lifecycle-gate's `gh issue view --json state --jq .state`
capture (spec.md's Status update — resolved as out of FR-013's scope) is
never mentioned in the gate's output, passing or failing — it is not a
`gh api` call at all.

## 3. The harness stub-conformance gate (User Story 3, FR-009/010/011/012/015)

```bash
python .github/scripts/verify-gh-error-stub-conformance.py --self-test
python .github/scripts/verify-gh-error-stub-conformance.py
```

Expected: the self-test's fixtures (contracts/gh-error-stub-conformance-
cli.md) all pass, including the retrofit-set derivation correctly
selecting `verify-auto-release-specs-fallback.py` and correctly excluding
a fixture harness whose subject block has no covered capture; the live
run reports zero non-conforming stubs and zero duplicate literals
(SC-004/SC-005).

To see the duplication check fail:

```bash
grep -n '"message":"Not Found"' .github/scripts/*.py
```

Confirm the only match is inside `wc_shell_harness.py` (or a call site
using `gh_error_stub_arm`, not a literal). Then temporarily paste the
literal JSON-error-body string into a second `.github/scripts/verify-*.py`
file and re-run `verify-gh-error-stub-conformance.py` — expect a failure
naming that file and `wc_shell_harness.py`. Remove the scratch edit
afterward.

## 4. Cross-harness proof the stub shape is load-bearing (SC-004)

```bash
python .github/scripts/verify-auto-release-specs-fallback.py --self-test
```

Expected: passes. Then mutate `auto-release.yml`'s shipped `specs/`
fallback block to drop its `slug=""` reset on the 404 branch (the exact
#482/#497 regression), and re-run the same command — expect it to now
fail, proving the migrated stub (research.md D9) still exercises the real
defect class, not just a decorative shape. Revert the mutation afterward.

## 5. Full suite, unchanged pass count plus the two new gates (SC-007)

```bash
python .github/scripts/run-local-gates.py
```

Expected: every gate that passed before this feature still passes (no
existing gate's subject or arguments changed — FR-004's "no behaviour
change on a successful read" holds for every corrected site), plus Gate
126 and Gate 127's four steps (live + self-test each), plus
`verify-auto-release-specs-fallback.py`'s own steps still passing after
its stub-arm migration (research.md D9). Compare the reported gate count
before/after implementation to confirm growth by exactly the two gates
this feature adds.
