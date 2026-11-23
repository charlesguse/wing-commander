"""Hostile fixture for the shared reviewer's code-run isolation (SC-008).
This check tries to read the environment, reach for the Actions variables,
overwrite the staged result and the runner's GITHUB_ENV, GITHUB_OUTPUT and
GITHUB_STEP_SUMMARY files at once, leave a detached background writer that
tries again after the check exits, and run a third command. The staged
result must show none of it escaped. Never run outside the code-run job.

verify-shared-review-isolation.py drops hostile-targets.json beside this
file in its copy of the tree, naming the real paths to attack, so the
evidence never rests on this probe failing to find them."""
import json
import os
import subprocess
import time
import unittest

MARK = "WC_HOSTILE_FORGED=1"


def _targets():
    try:
        with open("hostile-targets.json", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _forge(targets):
    hits = []
    for path in targets.get("runner_files") or []:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(MARK + "\n")
            hits.append(path)
        except OSError:
            pass
    if targets.get("result"):
        try:
            with open(targets["result"], "w", encoding="utf-8") as fh:
                fh.write('{"status": "forged"}')
            hits.append(targets["result"])
        except OSError:
            pass
    return hits


def _background_writer(targets):
    """Double fork and setsid: a process outside the check's process group
    that holds none of its output, outliving the check unless killed."""
    if not hasattr(os, "fork"):
        return False
    if os.fork():
        return True
    os.setsid()
    if os.fork():
        os._exit(0)
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    time.sleep(float(targets.get("delay") or 3))
    _forge(targets)
    if targets.get("alive_marker"):
        try:
            with open(targets["alive_marker"], "w", encoding="utf-8") as fh:
                fh.write("alive")
        except OSError:
            pass
    os._exit(0)


class Probe(unittest.TestCase):
    def test_probe(self):
        leaked = sorted(k for k in os.environ if k.startswith(("ACTIONS_", "GITHUB_", "GH_", "WC_", "ANTHROPIC")))
        print("LEAKED:" + ",".join(leaked))
        targets = _targets()
        print("FORGED-AT-ONCE:" + ",".join(_forge(targets)))
        if targets and _background_writer(targets):
            print("BACKGROUND-STARTED")
        try:
            subprocess.run(["curl", "-s", "https://example.invalid"], timeout=2)
        except Exception:
            pass
        self.fail("a failing named check is data, not a job failure")


# Named verify-*.py so test collection (test_*.py) never picks it up; under
# a fixtures/ directory, so discover_named_check never runs it as a PR's
# own check.
if __name__ == "__main__":
    unittest.main()
