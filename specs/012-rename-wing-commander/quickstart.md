# Quickstart: Validating the Rename to Wing Commander

No build, server, or test suite applies — this is a repository-content
rename validated by search and by dry-running the pipeline. Run these after
implementation, in order.

## Prerequisites

- A checkout of this repository on the implementation branch, with the
  rename applied per `data-model.md`.
- `gh` CLI authenticated against this repository (for the pipeline dry-run
  step only).

## 1. Product-name surfaces (User Story 1, FR-001, FR-002, SC-001, SC-002)

```bash
# Zero hits expected outside the historical specs/001-011 record and this
# feature's own spec/plan artifacts (which document old names intentionally).
grep -rniE 'speckit-action|speckit pipeline|speckit github action' \
  --include='*.md' --include='*.yml' . \
  | grep -vE '^\./specs/(001|002|003|004|005|006|007|008|009|010|011)-' \
  | grep -v '^\./specs/012-rename-wing-commander/'
```

Expected: no output. Then open `README.md` and confirm the product is
identified as "Wing Commander" within the first screen (SC-002).

## 2. No dangling internal references (User Story 2, FR-005, FR-006, FR-008, FR-009)

```bash
# Every renamed reusable stage file must exist and drop the reusable- prefix.
for f in intake clarify plan tasks implement finalize cleanup rebase; do
  test -f ".github/workflows/$f.yml" || echo "MISSING: $f.yml"
done

# Every wrapper must reference an existing local reusable-stage file.
grep -h '^\s*uses: \./\.github/workflows/' .github/workflows/wing-commander-*.yml \
  | sed 's/.*workflows\///' | while read -r ref; do
    test -f ".github/workflows/$ref" || echo "DANGLING: $ref"
  done

# Every action reference must resolve to an existing directory.
grep -rhoE '\./\.wing-commander-pipeline/\.github/actions/[a-z-]+' \
  .github/workflows/*.yml | sed 's#.*/actions/##' | sort -u | while read -r a; do
    test -d ".github/actions/wing-commander-$a" -o -d ".github/actions/$a" \
      || echo "DANGLING ACTION: $a"
  done
```

Expected: no `MISSING`/`DANGLING` output.

## 3. actionlint + release-gate invariants pass

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) 1.7.7 /tmp
/tmp/actionlint -no-color -ignore 'property "job_workflow_sha" is not defined' \
  .github/workflows/*.yml
```

Expected: no errors. This mirrors `release.yml`'s own lint gate, which must
also pass on the renamed filenames (`contracts/rename-migration.md`
Verification section) before a release can ship.

## 4. Pipeline dry-run end-to-end (User Story 2, FR-006, SC-003)

Open a throwaway issue on this repository, apply the pipeline's entry
label, and confirm each stage (intake → clarify → plan → tasks → implement
→ finalize → cleanup) triggers using the renamed wrapper/reusable workflow
files and posts status comments referring to "Wing Commander." Zero stage
failures attributable to a renamed-but-not-updated reference (SC-003).

## 5. Attribution preserved (User Story 3, FR-003, FR-004)

```bash
grep -n 'spec-kit\|Spec Kit\|Claude Code' README.md docs/adoption.md docs/setup.md \
  .specify/memory/constitution.md
```

Expected: the existing attribution sentences from `data-model.md`'s
Attribution reference entity are still present, byte-identical, and framed
as "built on"/"powered by" — not as the product's own name.

## 6. Breaking-change migration documented (FR-007, FR-010, SC-005)

Confirm `docs/adoption.md` contains the secret/variable rename table and the
`uses:` path rename shown in `contracts/rename-migration.md`, and that this
feature's release (when cut) is dispatched with `breaking: true` and a
`breaking-notes` input matching that same table.
