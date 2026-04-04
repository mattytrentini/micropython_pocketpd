"""Test assertion helpers for MicroPython."""


def _fmt(msg, detail):
    """Format assertion message with optional prefix."""
    if msg:
        return msg + ": " + detail
    return detail


def assert_eq(actual, expected, msg=""):
    """Assert two values are equal with a descriptive message."""
    if actual != expected:
        raise AssertionError(_fmt(msg, "expected %r, got %r" % (expected, actual)))


def assert_near(actual, expected, tolerance, msg=""):
    """Assert a numeric value is within tolerance of expected."""
    if abs(actual - expected) > tolerance:
        raise AssertionError(
            _fmt(msg, "expected %s +/- %s, got %s" % (expected, tolerance, actual))
        )


def assert_true(value, msg=""):
    """Assert value is truthy."""
    if not value:
        raise AssertionError(msg or ("expected truthy, got %r" % (value,)))


def assert_false(value, msg=""):
    """Assert value is falsy."""
    if value:
        raise AssertionError(msg or ("expected falsy, got %r" % (value,)))


def assert_raises(exc_type, func, *args, **kwargs):
    """Assert that calling func(*args, **kwargs) raises exc_type."""
    try:
        func(*args, **kwargs)
    except exc_type:
        return
    except Exception as e:
        raise AssertionError(
            "expected %s, got %s: %s" % (exc_type.__name__, type(e).__name__, e)
        ) from None
    raise AssertionError("expected %s, but no exception raised" % exc_type.__name__)


def assert_bytes_eq(actual, expected, msg=""):
    """Assert two byte sequences are equal, showing hex on failure."""
    if actual != expected:
        raise AssertionError(_fmt(msg, "expected %s, got %s" % (expected.hex(), actual.hex())))
