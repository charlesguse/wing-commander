"""Extract every embedded `run:` script from the auto-update-spec-kit workflows.

Writes one .sh per job/step into $1 so each can be executed in isolation
against fixtures. GitHub Actions ${{ }} expressions are left verbatim; subst.py
renders them per scenario.

Extracting rather than copying is deliberate: the scripts under test are always
the ones the workflow actually ships, so this harness cannot drift away from
the workflow it is meant to verify.
"""
import os
import re
import sys

import yaml

FILES = [
    ".github/workflows/auto-update-spec-kit.yml",
    ".github/workflows/wing-commander-auto-update-spec-kit.yml",
]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def main():
    if len(sys.argv) < 3:
        sys.stderr.write("usage: extract.py <repo-root> <out-dir>\n")
        return 2
    repo, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    manifest = []
    for rel in FILES:
        path = os.path.join(repo, rel)
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        wf = os.path.basename(rel).replace(".yml", "")
        for job_name, job in (doc.get("jobs") or {}).items():
            for i, step in enumerate(job.get("steps") or []):
                if "run" not in step:
                    continue
                name = step.get("name", step.get("id", "step%d" % i))
                fn = "%s__%s__%02d-%s.sh" % (wf, slug(job_name), i, slug(name))
                body = step["run"]
                with open(os.path.join(out, fn), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(body if body.endswith("\n") else body + "\n")
                manifest.append((wf, job_name, name, step.get("id", ""), fn))
    with open(os.path.join(out, "MANIFEST.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        for row in manifest:
            fh.write("\t".join(row) + "\n")
    print("extracted %d run: steps" % len(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
