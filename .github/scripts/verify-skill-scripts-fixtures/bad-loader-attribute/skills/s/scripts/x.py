import importlib.util
import os

spec = importlib.util.spec_from_file_location("m", os.path.join("scripts", "m.py"))
loaded = importlib.util.module_from_spec(spec)
VALUE = loaded.renamed_away()
