"""Parse $GITHUB_OUTPUT the way the Actions runner does (incl. <<HEREDOC)."""
import sys
path, key = sys.argv[1], sys.argv[2]
vals, i = {}, 0
lines = open(path, encoding="utf-8").read().split("\n")
while i < len(lines):
    line = lines[i]
    if "<<" in line and line.split("<<")[0].strip() and "=" not in line.split("<<")[0]:
        k, delim = line.split("<<", 1)
        k, delim = k.strip(), delim.strip()
        i += 1
        buf = []
        while i < len(lines) and lines[i] != delim:
            buf.append(lines[i]); i += 1
        vals[k] = "\n".join(buf)
    elif "=" in line:
        k, v = line.split("=", 1)
        vals[k] = v
    i += 1
sys.stdout.write(vals.get(key, ""))
