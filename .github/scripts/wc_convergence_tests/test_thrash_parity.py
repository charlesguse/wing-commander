"""SC-003 / T018: the review-until-clean skill's thrash_signals.py and the
automated loops' wc_convergence.py give identical signals on one recorded
history -- both CLIs run as subprocesses, as each caller runs them."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.normpath(os.path.join(SCRIPTS, "..", ".."))
MODULE_CLI = os.path.join(SCRIPTS, "wc_convergence.py")
SKILL_CLI = os.path.join(ROOT, ".claude", "skills", "review-until-clean", "scripts", "thrash_signals.py")


class Parity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
                              + list(args), cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, text):
        with open(os.path.join(self.repo, "f.py"), "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")
        return self.git("rev-parse", "HEAD")

    def run_cli(self, *argv):
        proc = subprocess.run([sys.executable, "-I"] + list(argv), cwd=self.repo,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def build(self):
        self.git("init", "-q", "-b", "main")
        base = self.commit("a\nb\nc\n")
        self.git("checkout", "-q", "-b", "pr")
        h0 = self.commit("a\nb\nc\npr1\npr2\n")
        h1 = self.commit("a\nb\nc\npr1-fixed\npr2\nfix1\n")
        h2 = self.commit("a\nb\nc\npr1-fixed\npr2\nfix1-refixed\nfix2\n")
        return base, h0, h1, h2

    def test_history_decisions_are_identical(self):
        base, h0, h1, h2 = self.build()
        history = [
            {"round": 1, "head_sha": h0, "findings": [{"fingerprint": "a", "file": "f.py", "line": 4}]},
            {"round": 2, "head_sha": h1, "findings": [{"fingerprint": "b", "file": "f.py", "line": 6},
                                                      {"fingerprint": "c", "file": "f.py"}]},
            {"round": 3, "head_sha": h2, "findings": [{"fingerprint": "d", "file": "f.py", "line": 7},
                                                      {"fingerprint": "e", "file": "f.py", "line": 2}]},
        ]
        path = os.path.join(self.repo, "history.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(history, fh)
        loops = self.run_cli(MODULE_CLI, "decide", "--history", path, "--base", base, "--json")
        skill = self.run_cli(SKILL_CLI, "--history", path, "--base", base, "--json")
        self.assertEqual(loops, skill)
        self.assertTrue(loops["stop"])  # the history must exercise the rules, not only agree

    def test_measure_reports_are_identical(self):
        base, h0, h1, h2 = self.build()
        skill = self.run_cli(SKILL_CLI, "--base", base, "--heads", ",".join((h0, h1, h2)),
                             "--finding", "f.py:4", "--finding", "f.py:6", "--json")
        sys.path.insert(0, SCRIPTS)
        import wc_convergence as wc
        module = wc.measure(base, [h0, h1, h2], ["f.py:4", "f.py:6"], self.repo, [])
        self.assertEqual(skill, json.loads(json.dumps(module)))


if __name__ == "__main__":
    unittest.main()
