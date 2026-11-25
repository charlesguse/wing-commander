import importlib.util
import sys

spec = importlib.util.spec_from_file_location("m", sys.argv[1])
