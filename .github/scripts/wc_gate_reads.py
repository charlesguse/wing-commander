"""The traced read map that `run-local-gates.py --changed` selects from.

`.github/scripts/gate-reads.json` maps every PR-time gate to what it was
seen to read when it last ran under `run-local-gates.py --record-reads`
(wc_gate_trace.py is the recorder). An entry is one of:

  {"code": [...], "digest": "...", "reads": [...], "children": [...]}
      a traced Python gate: the repository files its processes executed
      (`code`) and their digest, every file it opened or stat'ed and every
      directory it listed (`reads`, directories end in "/", "./" is the
      root), and the programs it started that the trace cannot see into
      (`children`, such as bash; their own reads are not in `reads`);
  {"always": "<why>"}
      a gate the trace cannot vouch for -- a shell gate, one that failed
      or had a process die while recorded -- so every change picks it.

A gate is keyed by its runner label (gate_label), and an inline gate by
its `inline-<slug>.sh` name (inline_gate_names). An entry is stale when
its code no longer has the digest it was recorded with: stale_keys()
names those, and verify-run-local-gates-changed.py (Gate 176) fails on
them and on any registry gate the map lacks. Refresh with

    python .github/scripts/run-local-gates.py --record-reads --changed

which re-records every gate a change since origin/main reaches (a stale
entry's code is one of its reads, so its gate is always among them), or
with `--record-reads` alone for the whole suite.
"""
import hashlib
import json
import os
import re

MAP_PATH = ".github/scripts/gate-reads.json"
_SLUG_HEAD = re.compile(r"Gate \d+")


def inline_gate_names(names):
    """The `inline-<slug>.sh` file name for each inline gate's step name,
    in order: `gate-N` for a step named "Gate N ...", else a slug of the
    name; a later step sharing a slug gets `-2`, `-3`, ..."""
    out, seen = [], set()
    for name in names:
        head = _SLUG_HEAD.match(name)
        slug = (head.group(0).lower().replace(" ", "-") if head
                else re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40])
        base, n = slug, 1
        while slug in seen:
            n += 1
            slug = f"{base}-{n}"
        seen.add(slug)
        out.append(f"inline-{slug}.sh")
    return out


def load(root="."):
    """The map, or {} when it is absent or unreadable."""
    try:
        with open(os.path.join(root, MAP_PATH), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(entries, root="."):
    with open(os.path.join(root, MAP_PATH), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(entries, fh, indent=1, sort_keys=True)
        fh.write("\n")


def digest(root, code, cache=None):
    """sha256 over each code path and its content (CRLF read as LF, so a
    Windows checkout agrees); a missing file hashes as missing."""
    cache = {} if cache is None else cache
    h = hashlib.sha256()
    for rel in sorted(code):
        if rel not in cache:
            try:
                with open(os.path.join(root, rel), "rb") as fh:
                    cache[rel] = hashlib.sha256(
                        fh.read().replace(b"\r\n", b"\n")).hexdigest()
            except OSError:
                cache[rel] = "missing"
        h.update(f"{rel}\0{cache[rel]}\n".encode())
    return h.hexdigest()


def stale_keys(root, entries, keys=None):
    """Sorted keys among `keys` (default: all) whose traced entry's code
    digest no longer matches."""
    cache = {}
    out = []
    for key in sorted(entries if keys is None else keys):
        entry = entries.get(key)
        if isinstance(entry, dict) and "always" not in entry and (
                digest(root, entry.get("code", []), cache)
                != entry.get("digest")):
            out.append(key)
    return out


def covers(entry, path):
    """Why a traced entry's reads cover `path`, or None: the file itself,
    or a directory above it that the gate listed."""
    reads = entry.get("_set")
    if reads is None:
        reads = entry["_set"] = frozenset(entry.get("reads", ()))
    if path in reads:
        return f"opened {path!r} when traced"
    if "./" in reads:
        return "listed the repository root when traced"
    parts = path.split("/")
    for i in range(len(parts) - 1, 0, -1):
        d = "/".join(parts[:i]) + "/"
        if d in reads:
            return f"listed {d!r} when traced"
    return None
