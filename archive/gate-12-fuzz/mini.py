"""Delta-minimize a script keeping: truth write, PR verdict < write
(or a custom predicate)."""
import json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from run import truth, verdict, PR, MAIN, RANK  # noqa


def pred_factory(kind, mode):
    def pred(s):
        import re, gen
        if any(not any(s.startswith(e, m.start()) for e in gen.EXPRS)
               for m in re.finditer(r"\$\{\{", s)):
            return False
        if ("repos/{owner}/{repo}/issues " if kind == "api" else "gh issue create") not in s:
            return False
        t = truth(s, kind)
        if t != "write":
            return False
        vp = verdict(PR, s, kind)
        if mode == "pronly":
            return RANK[vp] < 2 and RANK[verdict(MAIN, s, kind)] == 2
        return RANK[vp] < 2
    return pred


def ddmin(s, pred):
    # chunk deletion, characters
    n = 2
    while len(s) >= 2:
        chunk = max(1, len(s) // n)
        removed = False
        for i in range(0, len(s), chunk):
            cand = s[:i] + s[i + chunk:]
            if pred(cand):
                s = cand
                n = max(n - 1, 2)
                removed = True
                break
        if not removed:
            if chunk == 1:
                break
            n = min(len(s), n * 2)
    return s


if __name__ == "__main__":
    d = json.loads(sys.argv[1]) if sys.argv[1].startswith("{") else None
    kind, mode, script = d["kind"], d.get("mode", "any"), d["script"]
    out = ddmin(script, pred_factory(kind, mode))
    print(json.dumps({"mode": mode, "kind": kind, "min": out}))
