"""Record which repository files one gate's Python processes read.

`run-local-gates.py --record-reads` copies this module into a throwaway
virtual environment, beside a `.pth` line that imports it, and runs every
Python gate with that environment's interpreter. Each Python process the
gate starts, `-I` children included, then imports this module at startup.
It is inert unless WC_TRACE_OUT, WC_TRACE_GATE and WC_TRACE_ROOT are set.

What a process records, as repo-relative paths (outside WC_TRACE_ROOT,
and inside .git/, is dropped):

  * reads: every file it opens (the `open` audit event), stats
    (os.stat/os.lstat, so os.path.exists and friends count), or globs as
    a literal path; and every directory it lists (`os.listdir`,
    `os.scandir`, so os.walk, glob, pathlib iterdir/glob, shutil.copytree
    and unittest discovery all count), recorded with a trailing "/". The
    import system's own directory listings and source opens are skipped:
    an import is recorded as code, below;
  * code: every file whose code it executes (the `exec` and
    `cpython.run_file` audit events, which an import, runpy and exec of a
    compiled file all raise);
  * spawns: each child process's program name. A child is started with
    the WC_TRACE_* variables put back into an env= dict that dropped
    them, so a Python child is traced too. A path a child's argv names is
    a read (a script handed to bash, a file handed to jq), and `git
    ls-files`/`git grep` read their pathspecs, or the directory they run
    in when they name none. What a non-Python child reads by itself is
    not seen: run-local-gates.py decides what that means for the gate.

Each process writes `<pid>-<n>.json` under WC_TRACE_OUT when it starts,
with "done": false, and rewrites it at exit with "done": true, so a
process that died without exiting leaves its mark.
"""
import os
import sys

_OUT = os.environ.get("WC_TRACE_OUT")
_GATE = os.environ.get("WC_TRACE_GATE")
_ROOT = os.environ.get("WC_TRACE_ROOT")
_KEYS = ("WC_TRACE_OUT", "WC_TRACE_GATE", "WC_TRACE_ROOT")


def _install():
    import atexit
    import json
    import threading

    root = os.path.realpath(_ROOT)
    reads, code, spawns = set(), set(), set()
    local = threading.local()
    record = []
    real_stat, real_lstat, real_exit = os.stat, os.lstat, os._exit
    real_open = open

    def rel(path, base=None):
        if isinstance(path, int) or path is None:
            return None
        try:
            path = os.fsdecode(os.fspath(path))
        except TypeError:
            return None
        full = os.path.realpath(os.path.join(base or os.getcwd(), path))
        if full == root:
            return "."
        if not full.startswith(root + os.sep):
            return None
        out = os.path.relpath(full, root).replace(os.sep, "/")
        return None if out == ".git" or out.startswith(".git/") else out

    def add_dir(path, base=None):
        got = rel("." if path is None else path, base)
        if got is not None:
            reads.add("./" if got == "." else got + "/")

    def add_file(path, base=None):
        got = rel(path, base)
        if got not in (None, "."):
            reads.add(got)

    def from_import():
        # The audit hook is called from C: frame 0 is this function, 1 the
        # hook, 2 whoever called os.listdir/open. The import system's own
        # frames are frozen.
        f = sys._getframe(2)
        return f is not None and f.f_code.co_filename.startswith(
            "<frozen importlib")

    def child(args):
        exe, argv, cwd, env = args
        if isinstance(env, dict):
            for key in _KEYS:
                env.setdefault(key, os.environ[key])
        if isinstance(argv, (str, bytes, os.PathLike)):
            argv = [argv]
        argv = [os.fsdecode(a) if isinstance(a, (bytes, os.PathLike))
                else a for a in (argv or [])]
        argv = [a for a in argv if isinstance(a, str)]
        prog = os.path.basename(os.fsdecode(exe) if exe else
                                (argv[0].split()[0] if argv and argv[0]
                                 else ""))
        spawns.add(prog)
        base = os.fsdecode(cwd) if cwd else None
        if prog in ("git", "git.exe"):
            opts = argv[1:]
            if "-C" in opts:
                i = opts.index("-C")
                if i + 1 < len(opts):
                    base = os.path.join(base or os.getcwd(), opts[i + 1])
                    opts = opts[:i] + opts[i + 2:]
            sub = [a for a in opts if not a.startswith("-")]
            if sub and sub[0] in ("ls-files", "grep"):
                specs = [a for a in sub[1:] if a != "--"]
                if sub[0] == "grep":
                    specs = specs[1:]
                if not specs:
                    add_dir(".", base)
                for spec in specs:
                    head = spec.split("*")[0].split("?")[0].split("[")[0]
                    if head != spec:
                        add_dir(head.rsplit("/", 1)[0] if "/" in head
                                else ".", base)
                    else:
                        add_path(spec, base, True)
            return
        for a in argv[1:]:
            if a and not a.startswith("-"):
                add_path(a, base, False)

    def add_path(path, base, missing_too):
        # A child's argument: a directory is read as one, a file as one,
        # and anything else (a flag value, a word) only when asked.
        got = rel(path, base)
        if got is None:
            return
        full = os.path.join(root, got)
        if got == "." or os.path.isdir(full):
            add_dir(path, base)
        elif missing_too or os.path.exists(full):
            add_file(path, base)

    def hook(event, args):
        if getattr(local, "busy", False):
            return
        local.busy = True
        try:
            if event == "open":
                # os.open (mode None) may name its path relative to a
                # dir_fd the event does not carry (shutil.rmtree does),
                # so it counts only when it names a file from here.
                if not from_import() and (args[1] is not None
                                          or os.path.exists(args[0])):
                    add_file(args[0])
            elif event in ("os.listdir", "os.scandir"):
                if not from_import():
                    add_dir(args[0])
            elif event in ("glob.glob", "glob.glob/2"):
                pattern = args[0]
                if isinstance(pattern, (str, bytes)) and not any(
                        c in os.fsdecode(pattern) for c in "*?["):
                    add_file(pattern, args[2] if len(args) > 2 and
                             isinstance(args[2], (str, bytes)) else None)
            elif event == "exec":
                name = getattr(args[0], "co_filename", None)
                got = rel(name) if name and not name.startswith("<") else None
                if got not in (None, "."):
                    code.add(got)
            elif event == "cpython.run_file":
                got = rel(args[0])
                if got not in (None, "."):
                    code.add(got)
            elif event == "subprocess.Popen":
                child(args)
            elif event == "os.system":
                spawns.add("sh")
        except Exception:
            pass
        finally:
            local.busy = False

    def stat_hook(real):
        def traced(path, *a, **k):
            if not getattr(local, "busy", False):
                local.busy = True
                try:
                    if k.get("dir_fd") is None:
                        add_file(path)
                except Exception:
                    pass
                finally:
                    local.busy = False
            return real(path, *a, **k)
        traced.__name__ = real.__name__
        return traced

    def write(done):
        local.busy = True
        try:
            if not record:
                record.append(os.path.join(
                    _OUT, f"{os.getpid()}-{os.urandom(4).hex()}.json"))
            main = getattr(sys.modules.get("__main__"), "__file__", None)
            got = rel(main) if main else None
            if got not in (None, "."):
                code.add(got)
            data = {"gate": _GATE, "pid": os.getpid(), "done": done,
                    "argv": [str(a) for a in sys.argv],
                    "reads": sorted(reads), "code": sorted(code),
                    "spawns": sorted(spawns)}
            tmp = record[0] + ".tmp"
            with real_open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, record[0])
        except Exception:
            pass
        finally:
            local.busy = False

    def forked():
        # A forked child is its own process: its own record, started
        # "not done" so one that never exits cleanly still shows.
        record.clear()
        write(False)

    def exit_now(status):
        write(True)
        real_exit(status)

    write(False)
    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=forked)
    os._exit = exit_now
    os.stat = stat_hook(real_stat)
    os.lstat = stat_hook(real_lstat)
    for group in (os.supports_dir_fd, os.supports_fd,
                  os.supports_follow_symlinks):
        if real_stat in group:
            group.add(os.stat)
        if real_lstat in group:
            group.add(os.lstat)
    sys.addaudithook(hook)
    atexit.register(write, True)


if _OUT and _GATE and _ROOT:
    _install()
