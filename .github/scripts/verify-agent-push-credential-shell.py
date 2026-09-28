#!/usr/bin/env python3
"""Gate 121 - behavioral proof for mint-credential.sh, Gate 120's shell
companion (contracts/agent-push-credential-gate.md).

WHY THIS EXISTS
---------------
Gate 120 is a static structural check: it proves every push-capable agent
step is wired to call `wing-commander-agent-push-credential`, but it never
executes the shell that composite installs as a `git credential.helper` --
`mint-credential.sh` (specs/071-agent-push-credential, research.md
D2/D3/D6). That script signs a GitHub App JWT and exchanges it for an
installation token entirely in plain shell; its success/failure shape is a
runtime fact Gate 120's structural inspection cannot see. This gate drives
the SHIPPED script directly, the same way Gate 69 already does for the
credential-relay mechanism.

WHAT THIS CHECKS
----------------
1. A successful mint: stdout is exactly
   `username=x-access-token\\npassword=<the stubbed token>\\n`, exit 0.
2. A token-mint call answered 401: stdout empty, stderr's first line
   matches `^wing-commander-agent-push-credential: mint failed:
   token-mint-failed$`, exit 1.
3. `WC_AGENT_PUSH_KEY_PATH` pointing at a nonexistent file: `key-unreadable`
   reason, exit 1, and the stubbed `curl` records zero invocations (the
   script must fail before ever attempting a network call).

MECHANISM
---------
`curl` is stubbed via a shell function shadowing the name on PATH for the
duration of the test (the same stubbing convention `wc_shell_harness.py`
establishes), returning a fixed installation-lookup response then a fixed
token-mint response, keyed off the URL path the shipped script requests
("/installation" vs "/access_tokens") so both calls in one invocation are
answered correctly regardless of order. Every invocation is counted in a
call-log file, which check 3 asserts stays empty.

The RSA keypair `WC_AGENT_PUSH_KEY_PATH` points at is generated fresh, once
per run, into a tempdir via `openssl genrsa` -- a throwaway key, never
checked into the repository (a private key file in git history, even a
labeled-throwaway one, is the kind of thing a secret scanner flags and a
future reader has to re-verify is inert; generating it at test time makes
that question moot while remaining exactly as fixed/deterministic for the
duration of one gate run as a checked-in file would be).

Usage: python3 .github/scripts/verify-agent-push-credential-shell.py [--self-test]
Requires: bash, openssl (both present on ubuntu-latest runners; T002).
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wc_shell_harness import resolve_bash, run_step, use_utf8_stdout  # noqa: E402

SCRIPT_PATH = ".github/actions/wing-commander-agent-push-credential/mint-credential.sh"

CURL_STUB = """#!/bin/sh
echo x >> "$CURL_CALL_LOG"
url=""
for arg in "$@"; do
  case "$arg" in
    http*) url="$arg" ;;
  esac
done
case "$url" in
  */installation)
    printf '%s\\n%s' "$WC_TEST_INSTALL_BODY" "$WC_TEST_INSTALL_STATUS"
    ;;
  */access_tokens)
    printf '%s\\n%s' "$WC_TEST_MINT_BODY" "$WC_TEST_MINT_STATUS"
    ;;
  *)
    printf '%s\\n%s' '{}' '500'
    ;;
esac
"""

BASH = None


def mint_script():
    with open(SCRIPT_PATH, encoding="utf-8") as fh:
        return fh.read()


def gen_key(workdir):
    key_path = os.path.join(workdir, "test-key.pem")
    proc = subprocess.run(["openssl", "genrsa", "-out", key_path, "2048"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"::error::Gate 121: could not generate a throwaway test "
                 f"RSA key -- {proc.stderr}")
    return key_path


def new_curl_stub(workdir):
    bindir = os.path.join(workdir, "bin")
    os.makedirs(bindir, exist_ok=True)
    calls = os.path.join(workdir, "curl_calls")
    open(calls, "w").close()
    path = os.path.join(bindir, "curl")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(CURL_STUB)
    os.chmod(path, 0o755)
    return bindir, calls


def run_mint(script, workdir, key_path, env_extra):
    bindir, calls = new_curl_stub(workdir)
    env = {
        "WC_AGENT_PUSH_KEY_PATH": key_path,
        "WC_AGENT_PUSH_APP_ID": "123456",
        "WC_AGENT_PUSH_OWNER": "acme",
        "WC_AGENT_PUSH_REPO": "widgets",
        "CURL_CALL_LOG": calls,
        "PATH": bindir + os.pathsep + os.environ["PATH"],
    }
    env.update(env_extra)
    runner_temp = os.path.join(workdir, "runner_temp")
    os.makedirs(runner_temp, exist_ok=True)
    rc, out, _outputs, _summary = run_step(
        BASH, script, workdir, env, runner_temp, path_prepend=bindir)
    with open(calls, encoding="utf-8") as fh:
        n_calls = len(fh.read().splitlines())
    return rc, out, n_calls


def check_successful_mint(root, script=None):
    script = script or mint_script()
    failures = []
    workdir = tempfile.mkdtemp(dir=root)
    key_path = gen_key(workdir)
    rc, out, _ = run_mint(script, workdir, key_path, {
        "WC_TEST_INSTALL_BODY": '{"id": 999}', "WC_TEST_INSTALL_STATUS": "200",
        "WC_TEST_MINT_BODY": '{"token": "ghs_stubbedtoken123"}', "WC_TEST_MINT_STATUS": "201",
    })
    if rc != 0:
        failures.append(f"a successful mint exited {rc}, expected 0: {out!r}")
    expected = "username=x-access-token\npassword=ghs_stubbedtoken123\n"
    if out != expected:
        failures.append(f"a successful mint's stdout was {out!r}, expected "
                        f"exactly {expected!r}")
    return failures


def check_mint_failure_401(root, script=None):
    """run_step's `out` is stdout+stderr combined; the failure path writes
    only to stderr (stdout stays empty), so `out` here IS stderr's text.

    The stubbed 401 body carries a `.token` field alongside the error
    message -- deliberately, so that mut_ignore_mint_status (which drops
    the HTTP-status check and falls through to the same jq token
    extraction the success path uses) is actually observable here: without
    a `.token` field, the downstream empty-token guard would independently
    reject the mutated script's output for the same reason the status
    check would have, and the mutation would look inert."""
    script = script or mint_script()
    failures = []
    workdir = tempfile.mkdtemp(dir=root)
    key_path = gen_key(workdir)
    rc, out, _ = run_mint(script, workdir, key_path, {
        "WC_TEST_INSTALL_BODY": '{"id": 999}', "WC_TEST_INSTALL_STATUS": "200",
        "WC_TEST_MINT_BODY": '{"message": "Bad credentials", "token": "leaked-token"}',
        "WC_TEST_MINT_STATUS": "401",
    })
    if rc != 1:
        failures.append(f"a 401 token-mint response exited {rc}, expected 1: {out!r}")
    first_line = out.splitlines()[0] if out else ""
    expected = "wing-commander-agent-push-credential: mint failed: token-mint-failed"
    if first_line != expected:
        failures.append(f"a 401 token-mint response's stderr first line was "
                        f"{first_line!r}, expected exactly {expected!r} "
                        f"(full output: {out!r})")
    return failures


def check_key_unreadable(root, script=None):
    script = script or mint_script()
    failures = []
    workdir = tempfile.mkdtemp(dir=root)
    missing_key = os.path.join(workdir, "nonexistent-key.pem")
    rc, out, n_calls = run_mint(script, workdir, missing_key, {
        "WC_TEST_INSTALL_BODY": '{"id": 999}', "WC_TEST_INSTALL_STATUS": "200",
        "WC_TEST_MINT_BODY": '{"token": "should-never-be-reached"}', "WC_TEST_MINT_STATUS": "201",
    })
    if rc != 1:
        failures.append(f"a missing key file exited {rc}, expected 1: {out!r}")
    first_line = out.splitlines()[0] if out else ""
    expected = "wing-commander-agent-push-credential: mint failed: key-unreadable"
    if first_line != expected:
        failures.append(f"a missing key file's stderr first line was "
                        f"{first_line!r}, expected exactly {expected!r}")
    if n_calls != 0:
        failures.append(f"a missing key file made {n_calls} network call(s) "
                        f"via the stubbed curl -- expected 0 (the script "
                        f"must fail before ever attempting a mint)")
    return failures


def main(argv):
    global BASH
    use_utf8_stdout()
    BASH = resolve_bash()
    if not shutil.which("openssl"):
        sys.exit("::error::Gate 121: openssl is not on PATH -- the shipped "
                 "script under test signs its JWT with it, so nothing here "
                 "can run without it.")

    if "--self-test" in argv:
        return self_test()

    root = tempfile.mkdtemp(prefix="gate121-")
    try:
        failures = (check_successful_mint(root)
                    + check_mint_failure_401(root)
                    + check_key_unreadable(root))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for f in failures:
        print(f"::error::Gate 121: {f}")
    print(f"Gate 121: mint-credential.sh behavior; {len(failures)} failure(s).")
    return 1 if failures else 0


def mut_ignore_mint_status():
    """Regression: the script stops checking the token-mint HTTP status and
    treats every response as success -- the 401 case would then leak
    whatever body the API returned instead of failing loud."""
    script = mint_script()
    mutated = script.replace(
        'case "$token_status" in\n  2??) ;;\n  *) fail "token-mint-failed" ;;\nesac\n',
        '')
    if mutated == script:
        sys.exit("::error::Gate 121 self-test: mut_ignore_mint_status "
                 "changed nothing -- the shipped script's text was "
                 "rewritten; update the mutation to match.")
    return mutated


def mut_no_key_check():
    """Regression: BOTH the upfront key-readability guard AND the downstream
    empty-signature guard removed -- a missing key file would fall through
    openssl's own silent failure (2>/dev/null) into a network call made
    with a malformed JWT, instead of failing loud before ever reaching the
    network. Removing only the upfront guard is not observable on its own
    here: the downstream empty-signature check independently catches the
    same nonexistent-file case, so both must go for this mutation to change
    anything this check can see."""
    script = mint_script()
    mutated = script.replace(
        'if [ -z "$key_path" ] || [ ! -r "$key_path" ]; then\n  fail "key-unreadable"\nfi\n',
        '')
    mutated = mutated.replace(
        'if [ -z "$signature_b64" ]; then\n  fail "key-unreadable"\nfi\n',
        '')
    if mutated == script:
        sys.exit("::error::Gate 121 self-test: mut_no_key_check changed "
                 "nothing -- the shipped script's text was rewritten; "
                 "update the mutation to match.")
    return mutated


def self_test():
    problems = []
    root = tempfile.mkdtemp(prefix="gate121-selftest-")
    try:
        clean = (check_successful_mint(root)
                 + check_mint_failure_401(root)
                 + check_key_unreadable(root))
        if clean:
            problems.append("the clean shipped script FAILED its own "
                            "checks: " + "; ".join(clean))
        else:
            print("[ok] all three scenarios pass against the shipped script")

        broke = check_mint_failure_401(root, mut_ignore_mint_status())
        if not broke:
            problems.append("MUTATION SURVIVED -- a script that ignores "
                            "the token-mint HTTP status broke nothing in "
                            "the 401 check.")
        else:
            print(f"[ok] token-mint status check removed: {len(broke)} "
                  f"assertion(s) fail.")

        broke = check_key_unreadable(root, mut_no_key_check())
        if not broke:
            problems.append("MUTATION SURVIVED -- a script with the key-"
                            "readability guard removed broke nothing in "
                            "the key-unreadable check.")
        else:
            print(f"[ok] key-readability guard removed: {len(broke)} "
                  f"assertion(s) fail.")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for p in problems:
        print(f"::error::Gate 121 self-test: {p}")
    if problems:
        return 1
    print("Gate 121 self-test: clean shipped script passes; each mutation fails.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
