import sys
sys.path.insert(0, '.')
from load import PR, MAIN, verdict
for s in sys.argv[1:]:
    s = s.encode().decode('unicode_escape')
    print(verdict(PR, s, 'x'), verdict(MAIN, s, 'x'), repr(s))
