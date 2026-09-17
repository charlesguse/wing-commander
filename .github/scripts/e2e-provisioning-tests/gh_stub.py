"""A `gh` stub backed by a JSON state file ($GH_STATE), implementing only the
subcommands provision-e2e-target.sh / e2e-provisioning/checks.sh call.

State shape:
  {"repos": {"OWNER/NAME": {"exists": bool, "description": str|None,
                            "diskUsage": int, "defaultBranch": str,
                            "secrets": [str,...], "labels": [str,...],
                            "variables": {NAME: value}, "contents": {path: str},
                            "installation": bool}}
For the container_image_pin element, "this repository's own pinned value" is
just another entry in "repos", keyed by whatever GITHUB_REPOSITORY names in
the test.

Every invocation is appended to $GH_CALLS, matching the auto-update-spec-kit-tests
convention (.github/scripts/auto-update-spec-kit-tests/gh_stub.py).
"""
import base64
import json
import os
import sys

STATE = os.environ["GH_STATE"]
CALLS = os.environ.get("GH_CALLS")


def load():
    with open(STATE, encoding="utf-8") as fh:
        s = json.load(fh)
    s.setdefault("repos", {})
    return s


def save(s):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1)


def log(argv):
    if CALLS:
        with open(CALLS, "a", encoding="utf-8") as fh:
            fh.write(" ".join(argv) + "\n")


def opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def repo_of(argv, pos_index=None):
    r = opt(argv, "--repo")
    if r:
        return r
    if pos_index is not None and pos_index < len(argv) and not argv[pos_index].startswith("-"):
        return argv[pos_index]
    return None


def get_repo(s, full):
    return s["repos"].get(full)


def main():
    argv = sys.argv[1:]
    log(sys.argv)
    s = load()
    cmd = argv[0] if argv else ""

    # ---- gh repo -----------------------------------------------------
    if cmd == "repo":
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "create":
            full = argv[2]
            s["repos"][full] = {
                "exists": True, "description": None, "diskUsage": 0,
                "defaultBranch": "main", "secrets": [], "labels": [],
                "variables": {}, "contents": {}, "installation": False,
            }
            save(s)
            print("https://github.com/%s" % full)
            return 0
        if sub == "view":
            full = repo_of(argv, 2)
            repo = get_repo(s, full)
            if not repo or not repo.get("exists"):
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            if "--json" in argv:
                fields = opt(argv, "--json", "").split(",")
                out = {}
                for f in fields:
                    if f == "description":
                        out[f] = repo.get("description")
                    elif f == "diskUsage":
                        out[f] = repo.get("diskUsage", 0)
                    elif f == "defaultBranchRef":
                        out[f] = {"name": repo.get("defaultBranch", "main")}
                    elif f == "nameWithOwner":
                        out[f] = full
                if "-q" in argv:
                    q = opt(argv, "-q")
                    # Only the exact jq expressions this feature's code uses.
                    if q == ".description":
                        print(out.get("description") or "")
                    elif q == ".nameWithOwner":
                        print(out.get("nameWithOwner") or "")
                    elif q == '.defaultBranchRef.name // "main"' or q == '.defaultBranchRef.name // empty':
                        print((out.get("defaultBranchRef") or {}).get("name") or "")
                    else:
                        sys.stderr.write("gh stub: unhandled -q %r for repo view\n" % q)
                        return 1
                else:
                    print(json.dumps(out))
            return 0
        if sub == "edit":
            full = argv[2]
            repo = get_repo(s, full)
            if not repo:
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            desc = opt(argv, "--description")
            if desc is not None:
                repo["description"] = desc
            save(s)
            return 0

    # ---- gh secret -----------------------------------------------------
    if cmd == "secret":
        sub = argv[1]
        if sub == "set":
            name = argv[2]
            full = opt(argv, "--repo")
            repo = get_repo(s, full)
            if not repo:
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            if name not in repo["secrets"]:
                repo["secrets"].append(name)
            save(s)
            return 0
        if sub == "list":
            full = opt(argv, "--repo")
            repo = get_repo(s, full)
            if not repo:
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            for name in repo["secrets"]:
                print("%s\tsome-date" % name)
            return 0

    # ---- gh label --------------------------------------------------------
    if cmd == "label":
        sub = argv[1]
        name = argv[2]
        full = opt(argv, "--repo")
        repo = get_repo(s, full)
        if not repo:
            sys.stderr.write("gh: repository %s not found\n" % full)
            return 1
        if sub == "create":
            if name not in repo["labels"]:
                repo["labels"].append(name)
                # Content mutates the repository (diskUsage stays a
                # commit-content proxy for other elements only).
            save(s)
            return 0
        if sub == "view":
            return 0 if name in repo["labels"] else 1

    # ---- gh variable -----------------------------------------------------
    if cmd == "variable":
        sub = argv[1]
        if sub == "set":
            name = argv[2]
            full = opt(argv, "--repo")
            value = opt(argv, "--body", "")
            repo = get_repo(s, full)
            if not repo:
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            repo["variables"][name] = value
            save(s)
            return 0
        if sub == "list":
            full = opt(argv, "--repo")
            repo = get_repo(s, full)
            if not repo:
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            variables = repo["variables"]
            if "-q" in argv:
                q = opt(argv, "-q")
                if q == '.[] | select(.name=="WING_COMMANDER_CONTAINER_IMAGE") | .value':
                    if "WING_COMMANDER_CONTAINER_IMAGE" in variables:
                        print(variables["WING_COMMANDER_CONTAINER_IMAGE"])
                    return 0
                sys.stderr.write("gh stub: unhandled -q %r for variable list\n" % q)
                return 1
            print(json.dumps([{"name": k, "value": v} for k, v in variables.items()]))
            return 0

    # ---- gh api ------------------------------------------------------
    if cmd == "api":
        path = argv[1]
        method = opt(argv, "-X") or opt(argv, "--method") or "GET"
        parts = path.strip("/").split("/")
        # repos/OWNER/NAME/installation
        if len(parts) == 4 and parts[0] == "repos" and parts[3] == "installation":
            full = "%s/%s" % (parts[1], parts[2])
            repo = get_repo(s, full)
            if repo and repo.get("installation"):
                print("{}")
                return 0
            sys.stderr.write("gh: not installed\n")
            return 1
        # repos/OWNER/NAME/contents/PATH
        if len(parts) >= 5 and parts[0] == "repos" and parts[3] == "contents":
            full = "%s/%s" % (parts[1], parts[2])
            filepath = "/".join(parts[4:])
            repo = get_repo(s, full)
            if not repo:
                sys.stderr.write("gh: repository %s not found\n" % full)
                return 1
            if method == "PUT":
                fields = {}
                i = 0
                while i < len(argv):
                    if argv[i] in ("-f", "--raw-field", "--field"):
                        kv = argv[i + 1]
                        k, _, v = kv.partition("=")
                        fields[k] = v
                        i += 2
                    else:
                        i += 1
                content = fields.get("content", "")
                repo["contents"][filepath] = content
                repo["diskUsage"] = repo.get("diskUsage", 0) + max(1, len(base64.b64decode(content or "")))
                save(s)
                print(json.dumps({"content": {"sha": "stubsha-%s" % filepath}}))
                return 0
            # GET
            if filepath in repo["contents"]:
                if "-q" in argv and opt(argv, "-q") == ".sha":
                    print("stubsha-%s" % filepath)
                else:
                    print(json.dumps({"sha": "stubsha-%s" % filepath}))
                return 0
            sys.stderr.write("gh: 404 %s\n" % filepath)
            return 1
        sys.stderr.write("gh stub: unhandled api path %s\n" % path)
        return 1

    sys.stderr.write("gh stub: unhandled command: %s\n" % " ".join(argv))
    return 1


if __name__ == "__main__":
    sys.exit(main())
