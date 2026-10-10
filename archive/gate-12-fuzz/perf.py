import sys, time
sys.path.insert(0, '.')
from load import PR, MAIN
cases = {
 'heredocs': "cat <<EOF\nx\nEOF\n" * 400 + "gh issue create\n",
 'calls': 'gh api repos/{owner}/{repo}/issues -f b="`echo "a b"`" -X POST\n' * 1000,
 'bt-chain': 'echo "' + '`echo a`' * 3000 + '"\ngh issue create\n',
 'unclosed-bt': ('x="`echo\n' + 'gh issue create\n') * 300,
 'comments': ('# it\'s `x`\necho "a\n# b"\n') * 1000 + "gh issue create\n",
 'nested-esc': 'x=`' + 'echo \\` #c\\` ' * 2000 + '`\ngh issue create\n',
 'deep-brace': 'gh api repos/{owner}/{repo}/issues -f a=' + '${A:-`' * 200 + '`}' * 200 + ' -X POST\n',
 'many-bt-in-brace': 'gh api repos/{owner}/{repo}/issues -f a=${A:-' + '`x`' * 5000 + '} -X POST\n',
 'unclosed-expr-bt': 'gh api repos/{owner}/{repo}/issues -f a="' + '`${{' * 2000 + '" -X POST\n',
}
for name, s in cases.items():
    for gn, g in (('PR', PR), ('MAIN', MAIN)):
        t = time.time(); r = g.executable_gh_calls(s)
        for m, cl, a in r[:5]:
            if m.group('apipath'): g.api_level(cl, a)
        print(f"{name:18} {gn:4} {time.time()-t:7.2f}s calls={len(r)}")
