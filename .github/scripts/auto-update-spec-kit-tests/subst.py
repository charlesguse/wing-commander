"""Substitute GitHub Actions ${{ expr }} placeholders in an extracted step.

Pairs come as EXPR=VALUE on argv (EXPR is the trimmed inner text). Any
expression left unmatched becomes the empty string, exactly as Actions renders
an undefined/skipped needs.* output.
"""
import re, sys
path = sys.argv[1]
mapping = {}
for pair in sys.argv[2:]:
    k, _, v = pair.partition("=")
    mapping[k.strip()] = v
src = open(path, encoding="utf-8").read()
unmatched = set()
def repl(m):
    inner = m.group(1).strip()
    if inner in mapping:
        return mapping[inner]
    unmatched.add(inner)
    return ""
out = re.sub(r"\$\{\{(.*?)\}\}", repl, src)
open(path, "w", encoding="utf-8", newline="\n").write(out)
if unmatched:
    sys.stderr.write("    [subst] rendered as empty: %s\n" % ", ".join(sorted(unmatched)))
