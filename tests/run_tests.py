"""Minimal test runner for MicroPython Unix port.

Discovers test_*.py files in tests/, runs all functions starting with test_,
reports pass/fail summary.

Usage: micropython tests/run_tests.py [test_file_pattern]
"""

import os
import sys

import mip  # Install logging from micropython-lib (needed by mock_machine, idempotent)

mip.install("logging")

# Add project root and lib to path
sys.path.insert(0, "/code")
sys.path.insert(0, "/code/lib")
sys.path.insert(0, "/code/lib/mock_machine")

# Bootstrap mock_machine before any test imports
import mock_machine  # noqa: E402

mock_machine.register_as_machine()


def discover_tests(test_dir, pattern=None):
    """Find test_*.py files in test_dir, optionally filtered by pattern."""
    test_files = []
    for name in sorted(os.listdir(test_dir)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if pattern is None or pattern in name:
            test_files.append(name)
    return test_files


def load_and_run(test_dir, filename):
    """Import a test module and run all test_ functions. Returns (passed, failed, errors)."""
    module_name = filename[:-3]  # strip .py
    passed = 0
    failed = 0
    errors = []

    # Import the module
    module_path = f"{test_dir}/{filename}"
    spec = {}
    try:
        exec(compile(open(module_path).read(), module_path, "exec"), spec)
    except Exception as e:
        print(f"  ERROR loading {filename}: {e}")
        return 0, 0, [(filename, e)]

    # Find and run test_ functions
    test_funcs = sorted(k for k in spec if k.startswith("test_") and callable(spec[k]))
    for name in test_funcs:
        try:
            spec[name]()
            passed += 1
            print(f"  PASS {name}")
        except AssertionError as e:
            failed += 1
            errors.append((f"{module_name}.{name}", e))
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            failed += 1
            errors.append((f"{module_name}.{name}", e))
            print(f"  ERROR {name}: {type(e).__name__}: {e}")

    return passed, failed, errors


def main():
    test_dir = "/code/tests"
    pattern = sys.argv[1] if len(sys.argv) > 1 else None

    test_files = discover_tests(test_dir, pattern)
    if not test_files:
        print("No test files found.")
        sys.exit(1)

    total_passed = 0
    total_failed = 0
    all_errors = []

    for filename in test_files:
        print(f"\n{filename}")
        p, f, errs = load_and_run(test_dir, filename)
        total_passed += p
        total_failed += f
        all_errors.extend(errs)

    # Summary
    print(f"\n{'=' * 40}")
    print(f"{total_passed} passed, {total_failed} failed")

    if all_errors:
        print("\nFailures:")
        for name, err in all_errors:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print("All tests passed.")


main()
