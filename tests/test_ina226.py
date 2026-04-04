"""Tests for INA226 power monitor driver."""

import struct
import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

import machine
from testutil import assert_eq, assert_near

from drivers.ina226 import (
    AVG_16,
    DIE_ID,
    INA226,
    MANUFACTURER_ID,
    MODE_SHUNT_BUS_CONT,
    VBUS_1100US,
    VSHUNT_1100US,
)


def _make_ina226(shunt_ohms=0.005, max_current=5.5):
    """Create an INA226 with a mock I2C device pre-populated with register data."""
    i2c = machine.I2C(0)
    dev = machine.I2CDevice(addr=0x40, i2c=i2c)

    # Pre-populate all readable registers with zeros (2 bytes each)
    for reg in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07):
        dev.register_values[reg] = bytes(2)

    # Manufacturer and die ID
    dev.register_values[0xFE] = struct.pack(">H", MANUFACTURER_ID)
    dev.register_values[0xFF] = struct.pack(">H", DIE_ID)

    ina = INA226(i2c, shunt_ohms=shunt_ohms, max_current=max_current)
    return ina, dev


def test_manufacturer_id():
    ina, dev = _make_ina226()
    assert_eq(ina.manufacturer_id(), 0x5449)


def test_die_id():
    ina, dev = _make_ina226()
    assert_eq(ina.die_id(), 0x2260)


def test_bus_voltage_zero():
    ina, dev = _make_ina226()
    dev.register_values[0x02] = struct.pack(">H", 0)
    assert_near(ina.bus_voltage(), 0.0, 0.001)


def test_bus_voltage_5v():
    ina, dev = _make_ina226()
    # 5V / 1.25mV = 4000 raw counts
    dev.register_values[0x02] = struct.pack(">H", 4000)
    assert_near(ina.bus_voltage(), 5.0, 0.01)


def test_bus_voltage_20v():
    ina, dev = _make_ina226()
    # 20V / 1.25mV = 16000 raw counts
    dev.register_values[0x02] = struct.pack(">H", 16000)
    assert_near(ina.bus_voltage(), 20.0, 0.01)


def test_shunt_voltage_positive():
    ina, dev = _make_ina226()
    # 1A through 5mΩ = 5mV shunt voltage
    # 5mV / 2.5uV = 2000 raw counts
    dev.register_values[0x01] = struct.pack(">h", 2000)
    assert_near(ina.shunt_voltage(), 0.005, 0.0001)


def test_shunt_voltage_negative():
    ina, dev = _make_ina226()
    # Negative shunt voltage (reverse current)
    dev.register_values[0x01] = struct.pack(">h", -2000)
    assert_near(ina.shunt_voltage(), -0.005, 0.0001)


def test_calibration_value():
    """Verify calibration register calculation for 5mΩ shunt, 5.5A max."""
    ina, dev = _make_ina226()
    # current_lsb = 5.5 / 32768 = 0.000167846...
    # cal = 0.00512 / (0.005 * current_lsb) = 6101.8... -> int = 6101
    expected_lsb = 5.5 / 32768
    expected_cal = int(0.00512 / (0.005 * expected_lsb))
    assert_eq(ina._cal, expected_cal)


def test_current_reading():
    """Verify current conversion using calibrated LSB."""
    ina, dev = _make_ina226()
    ina.init()
    # Simulate 1A reading: raw = 1.0 / current_lsb
    current_lsb = 5.5 / 32768
    raw_1a = int(1.0 / current_lsb)
    dev.register_values[0x04] = struct.pack(">h", raw_1a)
    assert_near(ina.current(), 1.0, 0.01, "1A current reading")


def test_current_reading_3a():
    ina, dev = _make_ina226()
    ina.init()
    current_lsb = 5.5 / 32768
    raw_3a = int(3.0 / current_lsb)
    dev.register_values[0x04] = struct.pack(">h", raw_3a)
    assert_near(ina.current(), 3.0, 0.01, "3A current reading")


def test_power_reading():
    """Verify power conversion."""
    ina, dev = _make_ina226()
    ina.init()
    # Power register raw value: power_watts / power_lsb
    power_lsb = (5.5 / 32768) * 25
    raw_10w = int(10.0 / power_lsb)
    dev.register_values[0x03] = struct.pack(">H", raw_10w)
    assert_near(ina.power(), 10.0, 0.1, "10W power reading")


def test_init_writes_config_and_calibration():
    """Verify init() writes config and calibration registers."""
    ina, dev = _make_ina226()
    ina.init()

    # Check config register was written
    config_written = struct.unpack(">H", dev.register_values[0x00])[0]
    expected_config = AVG_16 | VBUS_1100US | VSHUNT_1100US | MODE_SHUNT_BUS_CONT
    assert_eq(config_written, expected_config, "config register")

    # Check calibration register was written
    cal_written = struct.unpack(">H", dev.register_values[0x05])[0]
    assert_eq(cal_written, ina._cal, "calibration register")


def test_init_custom_config():
    """Verify init() with custom configuration."""
    ina, dev = _make_ina226()
    custom_config = 0x4127  # some custom value
    ina.init(config=custom_config)
    config_written = struct.unpack(">H", dev.register_values[0x00])[0]
    assert_eq(config_written, custom_config)


def test_reset():
    """Verify reset writes 0x8000 to config register."""
    ina, dev = _make_ina226()
    ina.reset()
    config_written = struct.unpack(">H", dev.register_values[0x00])[0]
    assert_eq(config_written, 0x8000, "reset bit")


def test_different_shunt_calibration():
    """Verify calibration changes with different shunt resistance."""
    ina_5m, _ = _make_ina226(shunt_ohms=0.005, max_current=5.5)
    ina_10m, _ = _make_ina226(shunt_ohms=0.010, max_current=5.5)
    # 10mΩ shunt should have ~half the calibration value
    assert_near(ina_10m._cal, ina_5m._cal / 2, 1, "10m vs 5m cal")
