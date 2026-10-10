"""Load a Gate 12 source's function definitions (not its main loop)."""
import types


def load(path):
    src = open(path).read()
    cut = src.index("\napp_perms = parse_app_permissions()")
    mod = types.ModuleType("g")
    exec(compile(src[:cut], path, "exec"), mod.__dict__)
    return mod


PR = load(__file__.rsplit("/", 1)[0] + "/pr_gate.py")
MAIN = load(__file__.rsplit("/", 1)[0] + "/main_gate.py")


def verdict(g, run, kind):
    """-> 'missed' | 'read' | 'fail' | 'write' for the planted call."""
    best = "missed"
    rank = {"missed": 0, "read": 1, "fail": 2, "write": 2}
    for m, cmdline, assigns in g.executable_gh_calls(run):
        if kind == "verb":
            if m.group("verb1") == "issue" and m.group("verb2") == "create":
                v = "write"
            else:
                continue
        else:
            ap = m.group("apipath")
            if not ap or "issues" not in ap:
                continue
            lvl, _ = g.api_level(cmdline, assigns)
            v = {"write": "write", "read": "read", None: "fail"}[lvl]
        if rank[v] > rank[best]:
            best = v
    return best


PERMS = {"actions": "read", "contents": "read", "issues": "read",
         "pull-requests": "read"}


def verdict(g, run, kind):  # noqa: F811 -- the real check path
    """-> 'write' when Gate 12 flags anything (the planted write, or the
    call failing closed), else 'missed'."""
    failures, notes = [], []
    for m, cmdline, assigns in g.executable_gh_calls(run):
        g.check_gh_invocation("w", m, cmdline, assigns, "default", None,
                              PERMS, {}, failures, notes)
    return "write" if failures else "missed"
