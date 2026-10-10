"""Random bash run: steps with one planted gh write call."""
import random

EXPRS = [
    "${{ inputs.x }}", "${{ github.event.issue.number }}",
    "${{ inputs.a || 'b' }}", "${{ inputs.a && inputs.b }}",
    "${{ contains(x, '}}') }}", "${{ format('`{0}', x) }}",
    "${{ format('''{0}', x) }}", "${{ inputs.a != '\"' }}",
    "${{ steps.s.outputs.v == '$(' }}", "${{ x == '#' }}",
    "${{ fromJSON('{\"a\":1}').a }}", "${{ x || ')' }}",
    "${{ toJSON(x) }}", "${{ x == '`' && 'a' || 'b' }}",
]

PLAIN = ["a", "b1", "x.y", "--flag", "-n", "foo=bar", "1", "'", ")", "}", "#",
         "(", "{", "`", '"', "$", "\\", "|", "&", ";", "<<", "((", "))", "-X",
         "GET", "POST", "${", "$(", "#x", "a#b", "'#'", "\\#", "\\'", '\\"',
         "\\`", "\\$", "$$", "$#", "$?", "${#}", "!", "*", "~", "=", "{a,b}"]

VARS = ["A", "B", "X", "t", "v"]
OPS = [":-", "-", ":+", "+", "#", "##", "%", "%%", "/", "//", "^^", ",,",
       ":=", "=", "/#", "/%"]


class G:
    def __init__(self, rng):
        self.r = rng

    def ch(self, seq):
        return self.r.choice(seq)

    def p(self, x):
        return self.r.random() < x

    # ---------------------------------------------------------- words
    def sq(self, d):
        body = "".join(self.ch(["a", " ", '"', "`", "$(", ")", "${", "}", "#",
                                "\\", "{{", "}}", "-X GET", "|", ";", "\n"])
                       for _ in range(self.r.randint(0, 5)))
        if self.p(0.15):
            body += self.ch(EXPRS)
        return "'" + body.replace("'", "") + "'"

    def dq(self, d):
        parts = []
        for _ in range(self.r.randint(0, 4)):
            k = self.r.randint(0, 11)
            if k == 0:
                parts.append(self.ch(["a", " b", "'", "#", "(", ")", "{", "}",
                                      "|", ";", "&&", "-X GET", " # x",
                                      "\\\"", "\\`", "\\$", "\\\\", "$", "\n"]))
            elif k == 1 and d > 0:
                parts.append("$(" + self.cmd(d - 1) + ")")
            elif k == 2 and d > 0:
                parts.append(self.bt(d - 1, indq=True))
            elif k == 3 and d > 0:
                parts.append(self.param(d - 1, indq=True))
            elif k == 4:
                parts.append(self.ch(EXPRS))
            elif k == 5:
                parts.append("$((" + self.arith() + "))")
            elif k == 6:
                parts.append("$" + self.ch(VARS + ["$", "#", "?", "1"]))
            elif k == 7 and d > 0:
                # comment inside a substitution in double quotes
                parts.append("$(" + self.cmd(d - 1) + " #c'x\n)")
            elif k == 8 and d > 0:
                parts.append("`" + "echo " + self.ch(["'", "#x", "a", "\\`"]) + "`")
            elif k == 9:
                parts.append(self.ch(["\n# h ' `", "\n## x", "\n#", "$${", "\\" + self.ch(EXPRS),
                                      "`case $A in a) echo;; esac`", "`cat <<EOF | cat`",
                                      "${A:-{}", "${A%% #*}", "${A:-\\}}", "`echo \\` #\\``",
                                      "$(case $A in (a) echo;; b) :;; esac)"]))
            else:
                parts.append(self.ch(["x", "y z", "'q'"]))
        return '"' + "".join(parts) + '"'

    def bt(self, d, indq=False):
        inner = self.cmd(d)
        inner = inner.replace("\\", "\\\\").replace("`", "\\`")
        if indq:
            inner = inner.replace('"', '\\"') if self.p(0.3) else inner
        return "`" + inner + "`"

    def param(self, d, indq=False):
        v = self.ch(VARS)
        k = self.r.randint(0, 6)
        if k == 0:
            return "${" + v + "}"
        if k == 1:
            return "${#" + v + "}"
        if k == 2:
            return "${" + v + ":" + str(self.r.randint(0, 3)) + "}"
        op = self.ch(OPS)
        if op in ("/", "//", "/#", "/%"):
            pat = self.ch(["(", ")", "a", "{", "'x'", " #", "\\}", "\\/", "*"])
            rep = self.pword(d, indq)
            arg = pat + "/" + rep
        else:
            arg = self.pword(d, indq)
        return "${" + v + op + arg + "}"

    def pword(self, d, indq):
        out = []
        for _ in range(self.r.randint(0, 3)):
            k = self.r.randint(0, 9)
            if k == 0 and d > 0:
                out.append(self.param(d - 1, indq))
            elif k == 1 and d > 0:
                out.append("$(" + self.cmd(d - 1) + ")")
            elif k == 2:
                out.append(self.ch(EXPRS))
            elif k == 3:
                out.append(self.ch(["a b", " #x", "#", "{a}", "{", "|", ";",
                                    "&&", "-X GET", "(", ")", "\\}", "x"]))
            elif k == 4 and not indq:
                out.append(self.sq(d))
            elif k == 5:
                out.append(self.dq(d - 1) if d > 0 else '"q"')
            elif k == 6 and d > 0:
                out.append(self.bt(d - 1, indq))
            elif k == 7:
                out.append("$((" + self.arith() + "))")
            else:
                out.append(self.ch(["y", "*", "$$", "$A"]))
        return "".join(out)

    def extra(self, d):
        return self.ch([
            "`case $A in a) echo y;; esac`", "$(case $A in a) echo y;; esac)",
            "${A:-{a}b}", "${A:-{}", "${A%% #*}", "$${A}", "$$#", "${A//(/}",
            "${A:-${B:-" + self.ch(EXPRS) + "}}", "\\" + self.ch(EXPRS),
            "'" + self.ch(EXPRS).replace("'", "") + "'", "`echo '#'`",
            "`echo \\`echo x\\``", "`: #c`", "\"`echo ')'`\"", "${A:+`echo }`}",
            "$(( (1) << 2 ))", "$((A<<B))", "`cat <<'E'`", "${#A[@]}", "${A[0]:-x}",
            "${!A}", "$'\\''", "$\"x\"", "@(a|b)",
        ])

    def arith(self):
        return self.ch(["1 << 2", "A + 1", "1<<3", "(1+2)*3", "A >> 1",
                        "${#A} + 1", "2 ** 3", "A & 1", "1 < 2 ? 3 : 4"])

    def word(self, d):
        parts = []
        for _ in range(self.r.randint(1, 3)):
            k = self.r.randint(0, 11)
            if k == 0:
                parts.append(self.sq(d))
            elif k == 1:
                parts.append(self.dq(d))
            elif k == 2 and d > 0:
                parts.append("$(" + self.cmd(d - 1) + ")")
            elif k == 3 and d > 0:
                parts.append(self.bt(d - 1))
            elif k == 4:
                parts.append(self.param(d))
            elif k == 5:
                parts.append(self.ch(EXPRS))
            elif k == 6:
                parts.append("$((" + self.arith() + "))")
            elif k == 7:
                parts.append(self.ch(PLAIN))
            elif k == 8 and d > 0:
                parts.append("$(" + self.cmd(d - 1) + " #c'x\n)")
            elif k == 9:
                parts.append(self.extra(d))
            else:
                parts.append(self.ch(["w", "x1", "$A", "$$", "\\#"]))
        return "".join(parts)

    # ---------------------------------------------------------- commands
    def simple(self, d):
        c = self.ch(["echo", "printf %s", "true", ":", "echo -n"])
        words = [self.word(d) for _ in range(self.r.randint(0, 3))]
        s = " ".join([c] + words)
        if self.p(0.2):
            s += " #" + self.ch(["", " x'", " `", ' "', " $(", " ${", " gh run list", " )"])
        return s

    def cmd(self, d):
        k = self.r.randint(0, 12)
        if k == 0:
            return "A=" + self.word(d)
        if k == 1:
            return "(( A = " + self.arith() + " ))"
        if k == 2 and d > 0:
            return "{ " + self.cmd(d - 1) + "; }"
        if k == 3 and d > 0:
            return "( " + self.cmd(d - 1) + " )"
        if k == 4 and d > 0:
            return self.cmd(d - 1) + self.ch([" ; ", " && ", " || ", " | "]) + self.cmd(d - 1)
        if k == 5 and d > 0:
            return "if " + self.cmd(d - 1) + "; then " + self.cmd(d - 1) + "; fi"
        if k == 6:
            return "x=$((" + self.arith() + "))"
        return self.simple(d)

    def heredoc(self):
        delim = self.ch(["EOF", "EOF-1", "END_X", "PY"])
        q = self.ch(["", "'", '"'])
        dash = self.ch(["", "-"])
        opener = "cat <<" + dash + q + delim + q
        if self.p(0.3):
            opener += self.ch([" | cat", " > /dev/null", " ; echo 'x"])[:12]
            if opener.endswith("'x"):
                opener += "'"
        body = "\n".join(self.ch(["a ' b", "` x", '"', "$(", "gh run list", "# c",
                                  "))", "x <<EOF2", "${", "}"])
                         for _ in range(self.r.randint(0, 3)))
        body = body.replace("$(", "$ (").replace("`", "'")  # body must not execute
        return opener + "\n" + body + ("\n" if body else "") + ("\t" if dash and self.p(0.3) else "") + delim

    def noise_line(self, d):
        k = self.r.randint(0, 9)
        if k == 0:
            return self.heredoc()
        if k == 1:
            return "# " + self.ch(["it's", "a `b", '"', "$(", "${"])
        if k == 2:
            return self.cmd(d) + " \\\n  " + self.word(d)
        if k == 3:
            return "echo $(( 1 << 2 )) " + self.word(d)
        if k == 4:
            return "x=$(\n  " + self.cmd(d) + " # it's\n  " + self.cmd(d) + "\n)"
        return self.cmd(d)

    # ---------------------------------------------------------- planted call
    def planted(self, d, kind):
        if kind == "verb":
            call = "gh issue create --title " + self.ch(["t", '"$(echo x)"', "`date`", "${A:-x}"])
        else:
            m = self.ch(["-X POST", "-XPOST", "--method POST", "--method=POST",
                         "-X 'POST'", '-X "POST"', "-X PATCH", "-iX POST"])
            args = [m]
            for _ in range(self.r.randint(0, 3)):
                args.insert(self.r.randint(0, len(args)),
                            self.ch(["-f", "-F", "-H", "--jq"]) + " " +
                            self.ch(["b=" + self.word(d), self.word(d),
                                     '"$(echo -X GET)"', "${A:--X GET}",
                                     "`echo -X GET`", self.extra(d), self.dq(d),
                                     'b="`echo "a b"`"', 'b="`echo \'a b\' # x`"',
                                     'b="$(echo "a b" # it\'s\n)"', '"${A:-"a b"}"',
                                     '\\' + self.ch(EXPRS), "'" + self.ch(["a b", '"', "`", "$(", "#"]) + "'",
                                     'b="`case $A in a) echo "x y";; esac`"',
                                     '"`printf %s "$A" | tr -d "\\n"`"']))
            if self.p(0.1):
                args.append("-X GET")
            call = "gh api repos/{owner}/{repo}/issues " + " ".join(args)
        # wrap it in a context
        ctx = self.r.randint(0, 16)
        if ctx == 0:
            return call
        if ctx == 1:
            return self.cmd(d) + self.ch([" ; ", " && ", " || ", " | "]) + call
        if ctx == 2:
            return 'echo "' + self.ch(["", "id ", "'"]) + "$(" + call + ')"'
        if ctx == 3:
            return 'echo "`' + call.replace("`", "\\`") + '`"'
        if ctx == 4:
            return "echo `" + call.replace("`", "\\`") + "`"
        if ctx == 5:
            return "echo ${A:-$(" + call + ")}"
        if ctx == 6:
            return 'echo "${A:-$(' + call + ')}"'
        if ctx == 7:
            return "if true; then " + call + "; fi"
        if ctx == 8:
            return "{ " + call + "; }"
        if ctx == 9:
            return "( " + call + " )"
        if ctx == 10:
            return self.simple(d) + " #" + self.ch(["'", "`", '"']) + "\n" + call
        if ctx == 11:
            return "x=$(\n  " + call + "\n)"
        if ctx == 12:
            return "echo " + self.word(d) + "; " + call
        if ctx == 13:
            return 'echo "' + self.ch(EXPRS) + '" `' + call.replace("`", "\\`") + "`"
        if ctx == 14:
            return "(( A = 1 << 2 )); " + call
        if ctx == 15:
            return "echo $(( 1 << 2 )) " + self.word(d) + " && " + call
        return self.cmd(d) + " && \\\n  " + call

    def script(self, kind):
        d = self.r.randint(1, 3)
        pre = [self.noise_line(d) for _ in range(self.r.randint(0, 4))]
        post = [self.noise_line(d) for _ in range(self.r.randint(0, 2))]
        return "\n".join(pre + [self.planted(d, kind)] + post) + "\n"
