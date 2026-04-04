"""Tests for debounced button driver."""

import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

import machine
from testutil import assert_eq, assert_false, assert_true

from drivers.button import EVENT_LONG, EVENT_NONE, EVENT_SHORT, Button


class FakeClock:
    """Controllable clock for testing time-dependent code."""

    def __init__(self, start_ms=0):
        self._now = start_ms

    def ticks_ms(self):
        return self._now

    @staticmethod
    def ticks_diff(a, b):
        return a - b

    def advance(self, ms):
        self._now += ms


def _make_button(clock=None, debounce_ms=50, short_max=1000, long_min=1500):
    """Create a button with a mock pin and optional fake clock."""
    if clock is None:
        clock = FakeClock()
    pin = machine.Pin(10, machine.Pin.IN, value=1)  # Active-low: 1 = not pressed
    btn = Button(
        pin,
        debounce_ms=debounce_ms,
        short_press_max_ms=short_max,
        long_press_min_ms=long_min,
        _ticks_ms=clock.ticks_ms,
        _ticks_diff=clock.ticks_diff,
    )
    return btn, pin, clock


def _press(btn, pin, clock, debounce_ms=50):
    """Simulate a debounced button press (pin goes low, wait past debounce)."""
    pin.value(0)
    btn.update()  # Registers state change, starts debounce timer
    clock.advance(debounce_ms + 10)
    return btn.update()  # Debounce elapsed, press detected


def _release(btn, pin, clock, debounce_ms=50):
    """Simulate a debounced button release (pin goes high, wait past debounce)."""
    pin.value(1)
    btn.update()  # Registers state change
    clock.advance(debounce_ms + 10)
    return btn.update()  # Debounce elapsed, release detected


# --- Basic state tests ---


def test_initial_state_not_pressed():
    btn, pin, clock = _make_button()
    assert_false(btn.is_pressed)
    assert_eq(btn.update(), EVENT_NONE)


def test_pin_low_within_debounce_ignored():
    """Press within debounce window should not register."""
    btn, pin, clock = _make_button(debounce_ms=50)
    pin.value(0)
    btn.update()  # Registers change
    clock.advance(30)  # Only 30ms — still within debounce
    assert_eq(btn.update(), EVENT_NONE)
    assert_false(btn.is_pressed)


def test_press_detected_after_debounce():
    """Press should be detected after debounce window."""
    btn, pin, clock = _make_button(debounce_ms=50)
    event = _press(btn, pin, clock, debounce_ms=50)
    assert_eq(event, EVENT_NONE, "press start returns no event")
    assert_true(btn.is_pressed)


# --- Short press tests ---


def test_short_press():
    """Quick press and release generates SHORT event."""
    btn, pin, clock = _make_button(debounce_ms=50)

    _press(btn, pin, clock)  # Press start
    clock.advance(200)  # Hold for 200ms
    btn.update()  # Still held

    event = _release(btn, pin, clock)
    assert_eq(event, EVENT_SHORT)


def test_short_press_at_boundary():
    """Press exactly at short_press_max_ms is still SHORT."""
    btn, pin, clock = _make_button(debounce_ms=50, short_max=1000)

    _press(btn, pin, clock)
    clock.advance(940)  # 60 from debounce + 940 = 1000ms total hold

    event = _release(btn, pin, clock)
    assert_eq(event, EVENT_SHORT)


# --- Long press tests ---


def test_long_press_fires_while_held():
    """Long press fires EVENT_LONG while button is still held."""
    btn, pin, clock = _make_button(debounce_ms=50, long_min=1500)

    _press(btn, pin, clock)  # Press start
    clock.advance(1500)
    event = btn.update()
    assert_eq(event, EVENT_LONG)


def test_long_press_no_short_on_release():
    """After a long press, release should NOT generate SHORT."""
    btn, pin, clock = _make_button(debounce_ms=50, long_min=1500)

    _press(btn, pin, clock)
    clock.advance(1500)
    btn.update()  # Long fires

    event = _release(btn, pin, clock)
    assert_eq(event, EVENT_NONE, "no SHORT after LONG")


def test_long_press_fires_only_once():
    """Long press should fire exactly once per press."""
    btn, pin, clock = _make_button(debounce_ms=50, long_min=1500)

    _press(btn, pin, clock)
    clock.advance(1500)
    assert_eq(btn.update(), EVENT_LONG)

    clock.advance(500)
    assert_eq(btn.update(), EVENT_NONE)
    clock.advance(500)
    assert_eq(btn.update(), EVENT_NONE)


# --- Debounce tests ---


def test_bounce_during_press_filtered():
    """Rapid toggles (bounce) during press should be filtered."""
    btn, pin, clock = _make_button(debounce_ms=50)

    # Simulate bouncy press: rapid 0-1-0-1-0 within debounce window
    pin.value(0)
    clock.advance(5)
    btn.update()
    pin.value(1)
    clock.advance(5)
    btn.update()
    pin.value(0)
    clock.advance(5)
    btn.update()

    assert_false(btn.is_pressed, "still debouncing")

    # Settle and wait past debounce
    clock.advance(55)
    btn.update()  # Now stable
    assert_true(btn.is_pressed)


# --- Edge case: hold between short and long thresholds ---


def test_hold_between_short_and_long():
    """Hold longer than short_max but shorter than long_min — no event on release."""
    btn, pin, clock = _make_button(debounce_ms=50, short_max=1000, long_min=1500)

    _press(btn, pin, clock)
    clock.advance(1200)  # Past short_max, before long_min
    assert_eq(btn.update(), EVENT_NONE)

    event = _release(btn, pin, clock)
    assert_eq(event, EVENT_NONE, "no SHORT because hold > short_max")


# --- Repeated presses ---


def test_two_short_presses():
    """Two sequential short presses should each produce SHORT."""
    btn, pin, clock = _make_button(debounce_ms=50)

    _press(btn, pin, clock)
    clock.advance(100)
    assert_eq(_release(btn, pin, clock), EVENT_SHORT)

    clock.advance(100)

    _press(btn, pin, clock)
    clock.advance(100)
    assert_eq(_release(btn, pin, clock), EVENT_SHORT)
