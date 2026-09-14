# Contract: FR-015/FR-015a/FR-015b — the fail-loud step stays red, the issue-writer gets an enumerated exemption

`research.md` R6/R7 explain the design choice; `data-model.md`'s
"Exemption registry" table gives the field shape. This is the one
genuinely new script this feature adds.

## What stays unchanged (FR-015)

Every call site's existing "Fail loud on non-healthy agent verdict"
step (`if: steps.<x>-verdict.outputs.verdict != 'healthy'`, `exit 1`) is
**not** touched by this feature. `rate-limited` is not `healthy`, so
every one of these steps keeps failing its job for it, exactly as for
`exhausted`/`failed`/`unclassifiable` today. No `needs`-gate anywhere
starts reading a rate-limited stage as completed successfully. This
requirement needs no new code — it falls out of leaving the condition
alone.

## What must change at each issue/comment-writing call site (FR-015a)

Any step, at any call site, whose own `if:` (or an enclosing job's
`if:`) is gated on a non-healthy verdict **and** which itself runs a
`gh issue create`, `gh issue comment`, or `gh pr comment` — i.e., a step
that turns a bad verdict into a durable, maintainer-facing artifact
beyond the run's own log — must stop doing that for `rate-limited`
specifically. Two shapes satisfy this:

1. **Narrow the condition.** Change `verdict != 'healthy'` (or
   equivalent) to also exclude `rate-limited`, e.g.
   `verdict != 'healthy' && verdict != 'rate-limited'`. This is the
   expected shape at `finalize.yml`/`cleanup.yml` (research.md R7) and
   any other non-watchdog site the gate below discovers.
2. **Be the sanctioned rate-limited handler.** The watchdog's two new
   steps (contracts/watchdog-reporting.md: `'Report "rate-limited" to
   lifecycle issue'`, `'Ensure usage-limit issue'`) are themselves what
   FR-015a calls "the only issue-facing outputs permitted for this
   class" — they don't exclude `rate-limited`, they exist *because of*
   it, and are registered as exempt rather than narrowed (shape 1 would
   be nonsensical for them — narrowing them would mean they never run).

No functional requirement asks for auto-detecting *which* shape a given
site should take — that is an implementation judgment call per site,
made when `tasks.md`/implementation actually visits each discovered
site. This contract only fixes what the **gate** checks: that one of the
two shapes is present.

## `.github/scripts/verify-rate-limited-exemption.py` (NEW — Gate 51)

**What it enumerates**: every step, in every job, in every
`.github/workflows/*.yml` file, YAML-parsed (never grepped, matching
Gate 23's stated rationale — flow-style or unusually indented steps must
not be silently missed), whose:

- `run:` body contains `gh issue create`, `gh issue comment`, or `gh pr
  comment` (a plain substring/regex test over the parsed `run:` string —
  no shell execution), **and**
- own `if:`, or the job's own `if:`, textually references
  `.outputs.verdict` (covers both `steps.<id>.outputs.verdict` and
  `needs.<job>.outputs.verdict` shapes).

**What it asserts, per discovered site**:

- PASS if `(file, step name)` is in `EXEMPT_SITES` (the registry,
  data-model.md).
- PASS if the site's own `if:` condition, parsed as a boolean
  expression, provably excludes the literal `rate-limited` (an
  `!= 'rate-limited'` term ANDed into the condition, or an explicit
  allow-list of values none of which is `rate-limited`).
- FAIL, naming the file and step, otherwise — this is the case FR-015b
  asks for: a new agent-bearing stage's issue-writing step that neither
  excludes `rate-limited` nor is registered as a sanctioned handler.

**Self-test** (matching Gate 6/7/12/23's "the detector actually
detects" precedent): a synthetic fixture workflow file containing (a) a
correctly-narrowed site (must PASS), (b) a correctly-registered
`EXEMPT_SITES` site (must PASS), and (c) a site gated on
`verdict != 'healthy'` alone with no exclusion and no registration (must
FAIL, by name) — proving the gate can fail its own subject, not just
pass every real site by coincidence (constitution VIII).

**Wiring**: added to `lint-workflows.yml`'s existing `lint` job as "Gate
51 — every verdict-gated issue/comment write excludes rate-limited or is
a registered handler," `run: python3
.github/scripts/verify-rate-limited-exemption.py`. Gate 10
(`wc_gate_registry.py`'s convention check) requires this in the same PR
that adds the script, or Gate 10 itself fails on the orphaned file.

## Relationship to Gate 23

Gate 23 (spec 037) enumerates a different thing — every
`claude-code-action` step declaring `--max-turns`, checking it carries
the ceiling/verdict/fail-loud wiring. Gate 51 enumerates issue/comment
*writers* gated on the verdict those steps produce, a downstream and
disjoint set of steps. The two gates share a coding pattern (dynamic
YAML enumeration over grepping) but check unrelated properties; Gate 51
is a new script, not an extension of `verify-gate-23.py`'s existing
dispatcher.
