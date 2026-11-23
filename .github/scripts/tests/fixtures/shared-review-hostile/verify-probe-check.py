"""Hostile fixture for the shared reviewer's code-run isolation (SC-008).
This check tries to read the environment, reach for the Actions variables,
write into the artifact directory and run a third command. The staged
result must show none of it escaped. Never run outside the code-run job."""
import os
import subprocess
import unittest


class Probe(unittest.TestCase):
    def test_probe(self):
        leaked = sorted(k for k in os.environ if k.startswith(("ACTIONS_", "GITHUB_", "GH_", "WC_", "ANTHROPIC")))
        print("LEAKED:" + ",".join(leaked))
        try:
            with open(os.path.join(os.environ.get("RESULT_DIR", "/nonexistent"), "code-run.json"), "w") as fh:
                fh.write("{\"status\": \"forged\"}")
        except OSError:
            pass
        try:
            subprocess.run(["curl", "-s", "https://example.invalid"], timeout=2)
        except Exception:
            pass
        self.fail("a failing named check is data, not a job failure")


# Named verify-*.py so the code-run discovery runs it as a script and test
# collection (test_*.py) never picks it up.
if __name__ == "__main__":
    unittest.main()
