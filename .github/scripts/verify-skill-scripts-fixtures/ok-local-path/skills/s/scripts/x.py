import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import sibling_helper  # noqa: E402,F401  (a skill-local helper, not .github/scripts)
