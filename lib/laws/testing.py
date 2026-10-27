"""Strict test entrypoint: an empty or skipped parity/mutation suite is not green."""
import sys
import unittest
from pathlib import Path


def run(paths):
    suite = unittest.TestSuite()
    for path in paths:
        path = Path(path).resolve()
        tests = unittest.TestLoader().discover(str(path.parent), pattern=path.name)
        if not tests.countTestCases():
            raise RuntimeError('law test file collected no tests: '+str(path))
        suite.addTests(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return int(not result.wasSuccessful() or bool(result.skipped))


def main():
    sys.path.insert(0, str(Path.cwd()))
    sys.path.insert(0, str(Path.cwd()/'lib'))
    return run(sys.argv[1:])


if __name__ == '__main__':
    sys.exit(main())
