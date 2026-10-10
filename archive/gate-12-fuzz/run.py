import json, os, random, re, subprocess, sys, tempfile, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen  # noqa
from load import PR, MAIN, verdict  # noqa

EXPR_RE = re.compile(PR._EXPR)
STUB = os.path.join(HERE, "stub")
os.makedirs(STUB, exist_ok=True)
with open(os.path.join(STUB, "gh"), "w") as f:
    f.write('#!/bin/bash\nfor a in "$@"; do printf "%s\\x1f" "$a"; done >> "$GHLOG"; printf "\\x1e" >> "$GHLOG"\n')
os.chmod(os.path.join(STUB, "gh"), 0o755)

RANK = {"missed": 0, "read": 1, "fail": 2, "write": 2}


def truth(script, kind):
    sub = EXPR_RE.sub("EXPRV", script)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "s.sh")
        open(p, "w").write(sub)
        if subprocess.run(["bash", "-n", p], capture_output=True).returncode:
            return None
        log = os.path.join(td, "log")
        open(log, "w").close()
        try:
            subprocess.run(["bash", p], cwd=td, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=3,
                           env={"PATH": STUB + ":/usr/bin:/bin", "GHLOG": log})
        except subprocess.TimeoutExpired:
            return None
        best = "none"
        for line in open(log).read().split("\x1e")[:-1]:
            argv = line.split("\x1f")[:-1]
            if kind == "verb":
                if argv[:2] == ["issue", "create"]:
                    best = "write"
            elif argv[:1] == ["api"] and any("issues" in a for a in argv[1:2]):
                meth = "GET"
                k = 1
                while k < len(argv):
                    a = argv[k]
                    if a in ("-X", "--method", "-iX") and k + 1 < len(argv):
                        meth = argv[k + 1]; k += 2; continue
                    if a.startswith("--method="):
                        meth = a.split("=", 1)[1]
                    elif re.match(r"-i*X.", a):
                        meth = re.sub(r"^-i*X", "", a)
                    k += 1
                v = "write" if meth in ("POST", "PATCH", "PUT", "DELETE") else "read"
                if v == "write" or best == "none":
                    best = v
        return best


def one(seed):
    r = random.Random(seed)
    kind = r.choice(["verb", "api"])
    s = gen.G(r).script(kind)
    pos = [m.start() for m in re.finditer(r"\$\{\{", s)]
    if any(not any(s.startswith(e, p) for e in gen.EXPRS) for p in pos):
        return None
    t = truth(s, kind)
    if t is None:
        return None
    t0 = time.time(); vp = verdict(PR, s, kind); tp = time.time() - t0
    t0 = time.time(); vm = verdict(MAIN, s, kind); tm = time.time() - t0
    issues = []
    if RANK[vp] < RANK[vm] and t != "none":
        issues.append("lenient-vs-main" + ("" if t == "write" else "-truthread"))
    if t == "write" and RANK[vp] < 2:
        tag = "FN" + ("-both" if RANK[vm] < 2 else "-PRonly")
        if RANK[vm] < 2:
            orig = PR.strip_comments
            PR.strip_comments = lambda x: x
            try:
                if RANK[verdict(PR, s, kind)] == 2:
                    tag += "-stripcomments"
            finally:
                PR.strip_comments = orig
            orig = PR.strip_heredocs
            PR.strip_heredocs = lambda x: x
            try:
                if RANK[verdict(PR, s, kind)] == 2:
                    tag += "-heredocbody"
            finally:
                PR.strip_heredocs = orig
        issues.append(tag)
    if tp > 1.0:
        issues.append("slow")
    return dict(seed=seed, kind=kind, truth=t, pr=vp, main=vm, tp=tp, tm=tm,
                issues=issues, script=s if issues else None)


if __name__ == "__main__":
    start, count = int(sys.argv[1]), int(sys.argv[2])
    out = sys.argv[3]
    stats = {}
    with Pool(int(os.environ.get("J", "8"))) as pool, open(out, "w") as fo:
        valid = 0
        for res in pool.imap_unordered(one, range(start, start + count), chunksize=50):
            if res is None:
                continue
            valid += 1
            key = (res["truth"], res["pr"], res["main"])
            stats[str(key)] = stats.get(str(key), 0) + 1
            if res["issues"]:
                fo.write(json.dumps(res) + "\n")
    print("valid", valid)
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(v, k)
