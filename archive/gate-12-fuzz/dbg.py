import sys
sys.path.insert(0, '.')
from load import PR, MAIN
s = sys.argv[1].encode().decode('unicode_escape') if len(sys.argv) > 1 else sys.stdin.read()
for name, g in (("PR", PR), ("MAIN", MAIN)):
    text = g.strip_comments(g.strip_heredocs(s))
    fl = g.executable_flags(text)
    print(name, repr(text))
    print(name, "".join("x" if f else "." for f in fl))
    for m, cl, a in g.executable_gh_calls(s):
        print(name, "call", repr(m.group(0)), "cmdline", repr(cl[1]), "blank", repr(cl[0]))
        if m.group("apipath"):
            print(name, "  level", g.api_level(cl, a))
