import os
import sys

sys.path.insert(0, os.path.join(".github", "scripts"))
import m as mod  # noqa: E402
from m import handle, loop_item  # noqa: E402,F401

NAME = mod.__name__


def local(mod):
    return mod.anything
