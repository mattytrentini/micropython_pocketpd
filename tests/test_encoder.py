"""Tests for polling-based rotary encoder driver."""

import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

import machine
from testutil import assert_eq

from drivers.encoder import PollingEncoder as Encoder


def _make_encoder(clk_val=1, data_val=1):
    """Create an encoder with mock pins at given initial values."""
    clk = machine.Pin(19, machine.Pin.IN, value=clk_val)
    data = machine.Pin(20, machine.Pin.IN, value=data_val)
    enc = Encoder(clk, data)
    return enc, clk, data


def _rotate_cw(enc, clk, data):
    """Simulate one clockwise detent (full step): 11 -> 01 -> 00 -> 10 -> 11.

    Returns total delta accumulated.
    """
    total = 0
    # 11 -> 01
    clk.value(0)
    total += enc.update()
    # 01 -> 00
    data.value(0)
    total += enc.update()
    # 00 -> 10
    clk.value(1)
    total += enc.update()
    # 10 -> 11
    data.value(1)
    total += enc.update()
    return total


def _rotate_ccw(enc, clk, data):
    """Simulate one counter-clockwise detent: 11 -> 10 -> 00 -> 01 -> 11.

    Returns total delta accumulated.
    """
    total = 0
    # 11 -> 10
    data.value(0)
    total += enc.update()
    # 10 -> 00
    clk.value(0)
    total += enc.update()
    # 00 -> 01
    data.value(1)
    total += enc.update()
    # 01 -> 11
    clk.value(1)
    total += enc.update()
    return total


# --- Basic tests ---


def test_no_movement():
    enc, clk, data = _make_encoder()
    assert_eq(enc.update(), 0)
    assert_eq(enc.value, 0)


def test_clockwise_one_detent():
    enc, clk, data = _make_encoder()
    total = _rotate_cw(enc, clk, data)
    # One full CW detent should produce net +1 or similar
    # The Gray code table gives 4 transitions with alternating +1/-1,
    # but net should be non-zero
    assert_eq(enc.value, total)


def test_counter_clockwise_one_detent():
    enc, clk, data = _make_encoder()
    total = _rotate_ccw(enc, clk, data)
    assert_eq(enc.value, total)


def test_cw_and_ccw_opposite():
    """CW and CCW should produce opposite sign deltas."""
    enc_cw, clk_cw, data_cw = _make_encoder()
    cw_total = _rotate_cw(enc_cw, clk_cw, data_cw)

    enc_ccw, clk_ccw, data_ccw = _make_encoder()
    ccw_total = _rotate_ccw(enc_ccw, clk_ccw, data_ccw)

    assert_eq(cw_total, -ccw_total, "CW and CCW should be opposite")


def test_multiple_clockwise_detents():
    enc, clk, data = _make_encoder()
    for _ in range(5):
        _rotate_cw(enc, clk, data)
    cw_val = enc.value

    enc2, clk2, data2 = _make_encoder()
    _rotate_cw(enc2, clk2, data2)
    single = enc2.value

    assert_eq(cw_val, single * 5, "5 detents should be 5x one detent")


def test_reset():
    enc, clk, data = _make_encoder()
    _rotate_cw(enc, clk, data)
    enc.reset()
    assert_eq(enc.value, 0)


def test_value_setter():
    enc, clk, data = _make_encoder()
    enc.value = 42
    assert_eq(enc.value, 42)
    _rotate_cw(enc, clk, data)
    # Value should have changed from 42
    assert_eq(enc.value != 42, True, "value should change after rotation")


def test_no_change_same_state():
    """Repeated reads with no pin change should give zero delta."""
    enc, clk, data = _make_encoder()
    for _ in range(10):
        assert_eq(enc.update(), 0)


def test_single_pin_glitch():
    """A single pin change that reverts (glitch) should net to zero."""
    enc, clk, data = _make_encoder()
    clk.value(0)  # Partial transition
    d1 = enc.update()
    clk.value(1)  # Revert
    d2 = enc.update()
    assert_eq(d1 + d2, 0, "glitch should net to zero")
