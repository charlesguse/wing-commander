import os
import sys

sys.path.insert(0, os.path.join(".github", "scripts"))
import m as mod  # noqa: E402

VALUE = mod.renamed_away()
