"""Smoke test to verify test infrastructure works."""

import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

import machine
from testutil import assert_eq, assert_true


def test_mock_machine_available():
    """mock_machine provides Pin and I2C."""
    assert_true(hasattr(machine, "Pin"))
    assert_true(hasattr(machine, "I2C"))


def test_mock_i2c_device():
    """Can create I2C bus with mock device and read registers."""
    i2c = machine.I2C(0)
    dev = machine.I2CDevice(addr=0x40, i2c=i2c)
    dev.register_values[0x02] = bytes([0x10, 0x20])
    result = i2c.readfrom_mem(0x40, 0x02, 2)
    assert_eq(list(result), [0x10, 0x20])


def test_mock_pin():
    """Can create and read pin values."""
    p = machine.Pin(99, machine.Pin.OUT, value=0)
    assert_eq(p.value(), 0)
    p.value(1)
    assert_eq(p.value(), 1)
