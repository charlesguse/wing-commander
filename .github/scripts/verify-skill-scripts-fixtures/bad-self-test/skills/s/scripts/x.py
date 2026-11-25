import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--self-test", action="store_true")
if parser.parse_args().self_test:
    sys.exit(1)
