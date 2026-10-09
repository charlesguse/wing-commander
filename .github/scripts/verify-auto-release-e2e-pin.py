#!/usr/bin/env python3
"""auto-release.yml's end-to-end run calls the stages through an annotated
tag on the verified head, the shape every adopter's `@v2` pin takes.

WHY THIS EXISTS
---------------
verify-e2e used to pin the test repository's wrappers at a bare commit SHA.
Adopters pin `@v2` or `@v2.x.y`, both annotated tags, and through an
annotated tag github.job_workflow_sha is the tag object's SHA rather than
the commit's. v2.7.4 shipped a pipeline-checkout guard that compared that
SHA with HEAD unpeeled: it passed every end-to-end run and failed every
adopter (#928). The e2e could not have caught it, because nothing in it
ever resolved a tag.

The two pieces this checks:

  - e2e-pin (its own job, the only one holding `contents: write`) removes
    every e2e-verify-* tag an earlier run left, touching no other tag even
    when the server returns one, then creates a tag OBJECT on the verified
    head and a ref naming it. Nothing deletes this run's tag when the run
    ends: the test repository's wrappers keep naming it until the next
    run re-scaffolds them, so the next run's sweep is what replaces it.
    Any failure publishes no tag and a one-line reason (a gh error can
    span two lines, and a bare second line in $GITHUB_OUTPUT fails the
    step), and the step still exits 0.
  - verify-e2e's pin check reads the tag back: a ref to a tag object that
    peels to exactly the verified head, or a fail-infra verdict naming
    what it found. A lightweight tag, a tag on another commit, a missing
    tag and an e2e-pin failure are each told apart. verify-e2e runs after
    a failed e2e-pin (!cancelled()), so that failure is named too.

The harness EXECUTES the shipped steps (wc_shell_harness.run_step) against
a `gh` stub that keeps refs and tag objects in a JSON file and applies the
caller's own --jq program with the real jq, and chains them: the check
runs against the state e2e-pin left. Static checks pin the job graph: the
fixture's `uses:` rewrite names the pin tag, the scaffold waits for the
pin check, the check's verdict is in verify-e2e's chain, and verify-e2e
itself never gets `contents: write`. Each MUTATION reverts one rule and
asserts the suite then fails.

Usage: python3 .github/scripts/verify-auto-release-e2e-pin.py
Requires: bash, jq.
"""
import json
import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import (ensure_jq, find_step, resolve_bash,  # noqa: E402
                              run_step, use_utf8_stdout)

WORKFLOW = ".github/workflows/auto-release.yml"
PIN_STEP = "Create the run-scoped annotated tag the test repository pins"
CHECK_STEP = "Confirm the pin tag is an annotated tag on the verified head"
SCAFFOLD_STEP = "Scaffold the fixture and push it to the test repository"
VERDICT_SCRIPT = os.path.join(".github", "actions", "_shared", "auto-release-verdict.sh")

HEAD = "a" * 40
OTHER = "b" * 40
V2_OBJ = "c" * 40
TAG = "e2e-verify-500-1"
STALE = "e2e-verify-400-1"

# The stub's state: {"refs": {"refs/tags/x": sha}, "tags": {obj_sha:
# {"object": sha, "type": "commit", "tag": name}}}. A ref whose sha is a
# key of "tags" is annotated; any other ref names a commit directly.
# STUB_FAIL is "METHOD path-glob" (fnmatch) for one call to fail with a
# 403; STUB_FAIL_DNS=1 makes that failure gh's two-line connection error
# instead; STUB_MATCH_ALL=1 makes matching-refs return every tag, the way a
# server that ignored the prefix would. Like real gh, an HTTP error prints
# its JSON body on stdout, --jq or not, and `gh: <message> (HTTP <n>)` on
# stderr; POST refs refuses a sha that names no object.
STUB_PY = r'''
import fnmatch, hashlib, json, os, subprocess, sys

args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(" ".join(args) + "\n")
if not args or args[0] != "api":
    sys.stderr.write("stub gh: unexpected call: %s\n" % " ".join(args))
    sys.exit(97)
method, path, fields, jq = "GET", None, {}, None
i = 1
while i < len(args):
    a = args[i]
    if a == "-X":
        method = args[i + 1]; i += 2; continue
    if a == "-f":
        k, _, v = args[i + 1].partition("="); fields[k] = v; i += 2; continue
    if a == "--jq":
        jq = args[i + 1]; i += 2; continue
    if path is None:
        path = a; i += 1; continue
    sys.stderr.write("stub gh: unexpected argument %s\n" % a)
    sys.exit(97)

state_file = os.environ["STUB_STATE"]
state = json.load(open(state_file))
refs, tags = state["refs"], state["tags"]

def fail(status, message):
    sys.stdout.write(json.dumps({"message": message, "status": str(status)}) + "\n")
    sys.stderr.write("gh: %s (HTTP %d)\n" % (message, status))
    sys.exit(1)

COMMITS = {"a" * 40, "b" * 40}

def ref_obj(name):
    sha = refs[name]
    return {"ref": name, "object": {"sha": sha, "type": "tag" if sha in tags else "commit"}}

spec = os.environ.get("STUB_FAIL", "")
if spec:
    m, _, glob = spec.partition(" ")
    if m == method and fnmatch.fnmatchcase(path, glob):
        if os.environ.get("STUB_FAIL_DNS"):
            sys.stderr.write("error connecting to api.github.com\n"
                             "check your internet connection or https://githubstatus.com\n")
            sys.exit(1)
        fail(403, "Resource not accessible by integration")

prefix = "repos/o/r/git/"
if not path.startswith(prefix):
    fail(404, "Not Found")
sub = path[len(prefix):]
body = None
if method == "GET" and sub.startswith("matching-refs/"):
    want = "refs/" + sub[len("matching-refs/"):]
    names = sorted(refs)
    if not os.environ.get("STUB_MATCH_ALL"):
        names = [n for n in names if n.startswith(want)]
    body = [ref_obj(n) for n in names]
elif method == "GET" and sub.startswith("ref/"):
    name = "refs/" + sub[len("ref/"):]
    if name not in refs:
        fail(404, "Not Found")
    body = ref_obj(name)
elif method == "GET" and sub.startswith("tags/"):
    sha = sub[len("tags/"):]
    if sha not in tags:
        fail(404, "Not Found")
    t = tags[sha]
    body = {"sha": sha, "tag": t["tag"], "object": {"sha": t["object"], "type": t["type"]}}
elif method == "POST" and sub == "tags":
    sha = hashlib.sha1(("%s %s %d" % (fields["tag"], fields["object"], len(tags))).encode()).hexdigest()
    tags[sha] = {"object": fields["object"], "type": fields["type"], "tag": fields["tag"]}
    body = {"sha": sha, "tag": fields["tag"], "object": {"sha": fields["object"], "type": fields["type"]}}
elif method == "POST" and sub == "refs":
    if fields["ref"] in refs:
        fail(422, "Reference already exists")
    if fields["sha"] not in tags and fields["sha"] not in COMMITS:
        fail(422, "Object does not exist")
    refs[fields["ref"]] = fields["sha"]
    body = ref_obj(fields["ref"])
elif method == "DELETE" and sub.startswith("refs/"):
    if sub not in refs:
        fail(422, "Reference does not exist")
    del refs[sub]
else:
    fail(404, "Not Found")

json.dump(state, open(state_file, "w"))
if body is not None:
    text = json.dumps(body)
    if jq is not None:
        proc = subprocess.run(["jq", "-r", jq], input=text, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        sys.exit(proc.returncode)
    sys.stdout.write(text + "\n")
'''

BASH = None
failures = []


def check(name, cond, detail=""):
    if cond:
        print("[ok] {0}".format(name))
    else:
        failures.append(name)
        print("::error::verify-auto-release-e2e-pin: {0} -- {1}".format(name, detail))


def base_state():
    """v2 and v2.7.4 annotated on another commit, a stale pin tag from an
    earlier run, and a tag that only shares the prefix's first letters."""
    return {"refs": {"refs/tags/v2": V2_OBJ, "refs/tags/v2.7.4": V2_OBJ,
                     "refs/tags/" + STALE: "d" * 40, "refs/tags/e2e-verifyX": OTHER},
            "tags": {V2_OBJ: {"object": OTHER, "type": "commit", "tag": "v2"},
                     "d" * 40: {"object": OTHER, "type": "commit", "tag": STALE}}}


class Sandbox(object):
    def __init__(self, state):
        self.root = tempfile.mkdtemp(prefix="wc-ar-e2e-pin-")
        self.bindir = os.path.join(self.root, "bin")
        os.makedirs(self.bindir)
        stub_py = os.path.join(self.root, "stub_gh.py")
        open(stub_py, "w").write(STUB_PY)
        gh = os.path.join(self.bindir, "gh")
        with open(gh, "w", newline="\n") as fh:
            fh.write('#!/usr/bin/env bash\nexec "{0}" "{1}" "$@"\n'.format(
                sys.executable.replace("\\", "/"), stub_py.replace("\\", "/")))
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        self.state = os.path.join(self.root, "state.json")
        json.dump(state, open(self.state, "w"))
        self.log = os.path.join(self.root, "gh.log")
        open(self.log, "w").close()

    def run(self, script, env_extra):
        workdir = tempfile.mkdtemp(dir=self.root)
        runner_temp = tempfile.mkdtemp(dir=self.root)
        helper = os.path.join(workdir, VERDICT_SCRIPT)
        os.makedirs(os.path.dirname(helper))
        shutil.copyfile(VERDICT_SCRIPT, helper)
        open(self.log, "w").close()
        env = {"PATH": self.bindir + os.pathsep + os.environ["PATH"],
               "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "500",
               "STUB_STATE": self.state, "STUB_LOG": self.log,
               "STUB_FAIL": "", "STUB_MATCH_ALL": "", "GH_TOKEN": "t"}
        env.update(env_extra)
        rc, out, outputs, summary = run_step(BASH, script, workdir, env, runner_temp)
        return rc, out, outputs, summary, open(self.log).read()

    def refs(self):
        return json.load(open(self.state))["refs"]

    def tags(self):
        return json.load(open(self.state))["tags"]

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


PIN_ENV = {"HEAD_SHA": HEAD, "PREFIX": "e2e-verify-", "TAG": TAG}


def check_env(**kw):
    env = {"PIN_TAG": TAG, "PIN_FAILURE": "", "E2E_REPO": "o/e2e",
           "HEAD_SHA": HEAD, "MODE": "default-runner"}
    env.update(kw)
    return env


def verdict_of(outputs):
    try:
        return json.loads(outputs.get("verdict", ""))
    except ValueError:
        return {}


class _Stop(Exception):
    pass


def suite(steps, quiet=False):
    """Every case, reported; quiet (a mutation run) stops at the first miss."""
    failed = []

    def ck(name, cond, detail=""):
        if not cond:
            failed.append(name)
            if quiet:
                raise _Stop()
        if not quiet:
            check(name, cond, detail)

    try:
        cases(steps, ck)
    except _Stop:
        pass
    return failed


def cases(steps, ck):
    pin, chk = steps

    # --- e2e-pin, then the check against what it left -------------------
    sb = Sandbox(base_state())
    try:
        rc, out, o, summary, calls = sb.run(pin, PIN_ENV)
        refs, tags = sb.refs(), sb.tags()
        obj = refs.get("refs/tags/" + TAG, "")
        ck("e2e-pin creates a tag OBJECT on the verified head and a ref naming it",
           rc == 0 and o.get("tag") == TAG and o.get("failure") == ""
           and obj in tags and tags[obj] == {"object": HEAD, "type": "commit", "tag": TAG},
           "rc={0} outputs={1} ref={2!r}\n{3}".format(rc, o, obj, out))
        ck("e2e-pin removes the tag an earlier run left, and no other tag",
           "refs/tags/" + STALE not in refs and refs.get("refs/tags/v2") == V2_OBJ
           and refs.get("refs/tags/v2.7.4") == V2_OBJ and "refs/tags/e2e-verifyX" in refs,
           "refs={0}".format(sorted(refs)))
        rc, out, o, summary, calls = sb.run(chk, check_env())
        ck("the pin check passes the tag e2e-pin created, with no verdict",
           rc == 0 and o.get("ok") == "true" and "verdict" not in o,
           "rc={0} outputs={1}\n{2}".format(rc, o, out))
        rc, out, o, summary, calls = sb.run(pin, dict(PIN_ENV, TAG="e2e-verify-501-1"))
        ck("the next run's e2e-pin replaces this run's tag, so one exists at a time",
           rc == 0 and "refs/tags/" + TAG not in sb.refs() and "refs/tags/e2e-verify-501-1" in sb.refs()
           and sorted(r for r in sb.refs() if r.startswith("refs/tags/e2e-verify-")) == ["refs/tags/e2e-verify-501-1"],
           "refs={0}".format(sorted(sb.refs())))
    finally:
        sb.close()

    sb = Sandbox(base_state())
    try:
        rc, out, o, summary, calls = sb.run(pin, dict(PIN_ENV, STUB_MATCH_ALL="1"))
        ck("the sweep never deletes a tag outside its prefix, whatever the server returns",
           rc == 0 and sb.refs().get("refs/tags/v2") == V2_OBJ
           and "refs/tags/e2e-verifyX" in sb.refs() and "refs/tags/" + STALE not in sb.refs(),
           "rc={0} refs={1}\n{2}".format(rc, sorted(sb.refs()), calls))
    finally:
        sb.close()

    for name, fail, needle in (
            ("a failed tag-object create publishes no tag, says why, and exits 0",
             "POST repos/o/r/git/tags", "creating the annotated tag object"),
            ("a failed ref create publishes no tag, says why, and exits 0",
             "POST repos/o/r/git/refs", "creating refs/tags/" + TAG)):
        sb = Sandbox(base_state())
        try:
            rc, out, o, summary, calls = sb.run(pin, dict(PIN_ENV, STUB_FAIL=fail))
            ck(name, rc == 0 and o.get("tag") == "" and needle in o.get("failure", "")
               and "HTTP 403" in o.get("failure", "") and "refs/tags/" + TAG not in sb.refs(),
               "rc={0} outputs={1}\n{2}".format(rc, o, out))
        finally:
            sb.close()

    sb = Sandbox(base_state())
    try:
        rc, out, o, summary, calls = sb.run(pin, dict(PIN_ENV, STUB_FAIL="POST repos/o/r/git/tags",
                                                      STUB_FAIL_DNS="1"))
        failure = o.get("failure", "")
        ck("a two-line gh error reaches the failure output whole, on one line",
           rc == 0 and o.get("tag") == "" and "error connecting to api.github.com" in failure
           and "check your internet connection" in failure and "\n" not in failure,
           "rc={0} outputs={1}\n{2}".format(rc, o, out))
    finally:
        sb.close()

    for name, fail in (("a sweep that cannot list is a warning; the tag is still created",
                        "GET repos/o/r/git/matching-refs/*"),
                       ("a sweep that cannot delete is a warning; the tag is still created",
                        "DELETE repos/o/r/git/refs/tags/" + STALE)):
        sb = Sandbox(base_state())
        try:
            rc, out, o, summary, calls = sb.run(pin, dict(PIN_ENV, STUB_FAIL=fail))
            ck(name, rc == 0 and o.get("tag") == TAG and "::warning::" in out
               and "refs/tags/" + TAG in sb.refs(),
               "rc={0} outputs={1}\n{2}".format(rc, o, out))
        finally:
            sb.close()

    # --- the pin check on each wrong shape ------------------------------
    def check_case(name, state, env, needle):
        sb = Sandbox(state)
        try:
            rc, out, o, summary, calls = sb.run(chk, env)
            v = verdict_of(o)
            ck(name, rc == 0 and o.get("ok") == "false" and v.get("outcome") == "fail-infra"
               and v.get("verified_head") == HEAD and needle in v.get("observed", ""),
               "rc={0} outputs={1}\n{2}".format(rc, o, out))
        finally:
            sb.close()

    st = base_state()
    st["refs"]["refs/tags/" + TAG] = HEAD
    check_case("a lightweight tag on the verified head is refused as lightweight",
               st, check_env(), "a lightweight tag")
    st = base_state()
    st["tags"]["e" * 40] = {"object": OTHER, "type": "commit", "tag": TAG}
    st["refs"]["refs/tags/" + TAG] = "e" * 40
    check_case("an annotated tag on another commit is refused, naming that commit",
               st, check_env(), "peels to commit " + OTHER)
    check_case("a missing tag is refused",
               base_state(), check_env(), "reading refs/tags/" + TAG)
    check_case("e2e-pin's own failure reaches the verdict",
               base_state(), check_env(PIN_TAG="", PIN_FAILURE="creating refs/tags/x: HTTP 403"),
               "creating refs/tags/x: HTTP 403")
    check_case("an e2e-pin that never finished is named as such",
               base_state(), check_env(PIN_TAG="", PIN_FAILURE=""), "e2e-pin job published no tag")
    st = base_state()
    st["tags"]["e" * 40] = {"object": HEAD, "type": "commit", "tag": TAG}
    st["refs"]["refs/tags/" + TAG] = "e" * 40
    sb = Sandbox(st)
    try:
        rc, out, o, summary, calls = sb.run(chk, check_env(STUB_FAIL="GET repos/o/r/git/tags/*"))
        ck("an unreadable tag object is refused",
           o.get("ok") == "false" and "reading the tag object" in verdict_of(o).get("observed", ""),
           "rc={0} outputs={1}\n{2}".format(rc, o, out))
    finally:
        sb.close()


def static_checks(jobs, steps):
    writers = sorted(k for k, j in jobs.items()
                     if ((j or {}).get("permissions") or {}).get("contents") == "write")
    check("e2e-pin is the only job that can write contents",
          writers == ["e2e-pin"], "contents: write jobs: {0}".format(writers))
    verify_job = jobs["verify-e2e"]
    verify_if = str(verify_job.get("if", ""))
    check("verify-e2e needs e2e-pin and still runs when e2e-pin failed, so its check names it",
          "e2e-pin" in (verify_job.get("needs") or []) and "!cancelled()" in verify_if
          and "needs.detect.result == 'success'" in verify_if
          and "needs.detect.outputs.run-verification == 'true'" in verify_if,
          "needs={0} if={1!r}".format(verify_job.get("needs"), verify_if))
    deleters = ["{0} / {1}".format(name, (step or {}).get("name"))
                for name, job in jobs.items() if name != "e2e-pin"
                for step in (job or {}).get("steps") or []
                if "-X DELETE" in ((step or {}).get("run") or "")
                and "git/refs/tags" in ((step or {}).get("run") or "")]
    check("nothing but e2e-pin's sweep deletes a tag, so the test repository's pin keeps resolving",
          not deleters, "deleting steps: {0}".format(deleters))
    scaffold = steps["scaffold"]
    run = scaffold.get("run", "")
    check("the fixture's uses: rewrite names the pin tag, never the bare head",
          "/.github/workflows/${stage}@${PIN_TAG}#" in run and "${stage}@${HEAD_SHA}" not in run
          and (scaffold.get("env") or {}).get("PIN_TAG") == "${{ needs.e2e-pin.outputs.tag }}",
          "scaffold env={0}".format(scaffold.get("env")))
    check("the scaffold waits for the pin check",
          "steps.pin.outputs.ok == 'true'" in str(scaffold.get("if", "")),
          "if={0!r}".format(scaffold.get("if")))
    chain = str((verify_job.get("outputs") or {}).get("verdict", ""))
    check("the pin check's verdict is in verify-e2e's chain, ahead of the scaffold's",
          "steps.pin.outputs.verdict" in chain
          and chain.index("steps.pin.outputs.verdict") < chain.index("steps.scaffold.outputs.verdict"),
          chain)
    pin_env = steps["pin"].get("env") or {}
    check("e2e-pin names its tag under its sweep prefix, unique to the run attempt",
          pin_env.get("PREFIX") == "e2e-verify-"
          and pin_env.get("TAG") == "e2e-verify-${{ github.run_id }}-${{ github.run_attempt }}",
          "env={0}".format(pin_env))
    check("the check reads e2e-pin's outputs",
          (steps["check"].get("env") or {}).get("PIN_TAG") == "${{ needs.e2e-pin.outputs.tag }}"
          and (steps["check"].get("env") or {}).get("PIN_FAILURE") == "${{ needs.e2e-pin.outputs.failure }}",
          "env={0}".format(steps["check"].get("env")))


# (name, which step: 0 pin / 1 check, old, new)
MUTATIONS = (
    ("the sweep's own prefix guard removed", 0,
     '"refs/tags/${PREFIX}"*) ;;', '*) ;;'),
    ("the ref pointed at the commit (a lightweight tag)", 0,
     '-f sha="$obj"', '-f sha="$HEAD_SHA"'),
    ("an empty tag object accepted", 0,
     'if [ -z "$obj" ]; then', 'if false; then'),
    ("a failed tag-object create's error body kept as the object", 0,
     '\n  obj=""\n', '\n'),
    ("the failure text left multi-line", 0,
     'why="$(printf \'%s\' "$1" | tr \'\\r\\n\' \'  \')"', 'why="$1"'),
    ("the lightweight-tag check removed", 1,
     'if [ "$ref_type" != "tag" ]; then', 'if false; then'),
    ("the peel comparison removed", 1,
     'elif [ "$peeled" != "commit ${HEAD_SHA}" ]; then', 'elif false; then'),
)


def main():
    global BASH
    use_utf8_stdout()
    ensure_jq()
    BASH = resolve_bash()
    steps = {"pin": find_step(WORKFLOW, PIN_STEP), "check": find_step(WORKFLOW, CHECK_STEP),
             "scaffold": find_step(WORKFLOW, SCAFFOLD_STEP)}
    import yaml
    jobs = (yaml.safe_load(open(WORKFLOW, encoding="utf-8")) or {}).get("jobs") or {}
    scripts = [steps["pin"]["run"], steps["check"]["run"]]
    for name, idx, old, _new in MUTATIONS:
        if scripts[idx].count(old) != 1:
            sys.exit("::error file={0}::mutation {1!r} no longer matches the step text "
                     "exactly once. Update the mutation with the step.".format(WORKFLOW, name))
    static_checks(jobs, steps)
    suite(scripts)
    for name, idx, old, new in MUTATIONS:
        mutated = list(scripts)
        mutated[idx] = mutated[idx].replace(old, new)
        check("mutation caught: " + name, bool(suite(mutated, quiet=True)),
              "the suite stayed green with this rule reverted")
    if failures:
        print("verify-auto-release-e2e-pin: {0} failure(s)".format(len(failures)))
        sys.exit(1)
    print("verify-auto-release-e2e-pin: ok")


if __name__ == "__main__":
    main()
