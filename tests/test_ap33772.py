"""Tests for AP33772 USB PD sink controller driver."""

import struct
import sys

sys.path.insert(0, "/code")
sys.path.insert(0, "/code/tests")

import machine
from testutil import assert_bytes_eq, assert_eq, assert_false, assert_true

from drivers.ap33772 import (
    AP33772,
    PPSPDO,
    STATUS_NEW_PDO,
    STATUS_OCP,
    STATUS_READY,
    FixedPDO,
    build_fixed_rdo,
    build_pps_rdo,
    parse_pdo,
)

# --- Helper to build mock AP33772 I2C device ---


def _make_ap33772(pdos=None):
    """Create AP33772 with mock I2C device and optional PDO data.

    Args:
        pdos: list of 4-byte PDO tuples to pre-load, or None for defaults

    Returns:
        (ap33772, i2c_device) tuple
    """
    i2c = machine.I2C(0)
    dev = machine.I2CDevice(addr=0x51, i2c=i2c)

    # Default: a typical 65W charger with 5V/3A, 9V/3A, 15V/3A, 20V/3.25A, PPS 3.3-21V/5A
    if pdos is None:
        pdos = [
            _make_fixed_pdo_bytes(5000, 3000),  # 5V 3A
            _make_fixed_pdo_bytes(9000, 3000),  # 9V 3A
            _make_fixed_pdo_bytes(15000, 3000),  # 15V 3A
            _make_fixed_pdo_bytes(20000, 3250),  # 20V 3.25A
            _make_pps_pdo_bytes(3300, 21000, 5000),  # PPS 3.3-21V 5A
        ]

    # Pack all PDO bytes
    pdo_data = b""
    for p in pdos:
        pdo_data += p

    dev.register_values[0x00] = pdo_data  # CMD_SRCPDO
    dev.register_values[0x1C] = bytes([len(pdos)])  # CMD_PDONUM
    dev.register_values[0x1D] = bytes([STATUS_READY])  # CMD_STATUS
    dev.register_values[0x1E] = bytes([0])  # CMD_MASK
    dev.register_values[0x20] = bytes([0])  # CMD_VOLTAGE
    dev.register_values[0x21] = bytes([0])  # CMD_CURRENT
    dev.register_values[0x22] = bytes([25])  # CMD_TEMP (25C)
    dev.register_values[0x30] = bytes(4)  # CMD_RDO

    ap = AP33772(i2c)
    return ap, dev


def _make_fixed_pdo_bytes(voltage_mv, max_current_ma):
    """Encode a Fixed PDO as 4 bytes (little-endian)."""
    # Fixed: type=0b00 (bits 31:30), voltage in 50mV (bits 19:10), current in 10mA (bits 9:0)
    dword = 0  # type bits 31:30 = 0b00
    dword |= ((voltage_mv // 50) & 0x3FF) << 10
    dword |= (max_current_ma // 10) & 0x3FF
    return struct.pack("<I", dword)


def _make_pps_pdo_bytes(min_voltage_mv, max_voltage_mv, max_current_ma):
    """Encode a PPS PDO as 4 bytes (little-endian)."""
    # PPS: type=0b11 (bits 31:30), max_v in 100mV (bits 24:17), min_v in 100mV (bits 15:8),
    #       current in 50mA (bits 6:0)
    dword = 0b11 << 30  # type bits
    dword |= ((max_voltage_mv // 100) & 0xFF) << 17
    dword |= ((min_voltage_mv // 100) & 0xFF) << 8
    dword |= (max_current_ma // 50) & 0x7F
    return struct.pack("<I", dword)


# --- PDO Parsing Tests ---


def test_parse_fixed_pdo_5v():
    raw = _make_fixed_pdo_bytes(5000, 3000)
    pdo = parse_pdo(raw, 1)
    assert_true(isinstance(pdo, FixedPDO))
    assert_eq(pdo.voltage_mv, 5000)
    assert_eq(pdo.max_current_ma, 3000)
    assert_eq(pdo.index, 1)


def test_parse_fixed_pdo_20v():
    raw = _make_fixed_pdo_bytes(20000, 3250)
    pdo = parse_pdo(raw, 4)
    assert_true(isinstance(pdo, FixedPDO))
    assert_eq(pdo.voltage_mv, 20000)
    assert_eq(pdo.max_current_ma, 3250)
    assert_eq(pdo.index, 4)


def test_parse_pps_pdo():
    raw = _make_pps_pdo_bytes(3300, 21000, 5000)
    pdo = parse_pdo(raw, 5)
    assert_true(isinstance(pdo, PPSPDO))
    assert_eq(pdo.min_voltage_mv, 3300)
    assert_eq(pdo.max_voltage_mv, 21000)
    assert_eq(pdo.max_current_ma, 5000)
    assert_eq(pdo.index, 5)


def test_parse_pps_pdo_narrow_range():
    """PPS with narrow voltage range (e.g., 5-9V)."""
    raw = _make_pps_pdo_bytes(5000, 9000, 3000)
    pdo = parse_pdo(raw, 3)
    assert_true(isinstance(pdo, PPSPDO))
    assert_eq(pdo.min_voltage_mv, 5000)
    assert_eq(pdo.max_voltage_mv, 9000)
    assert_eq(pdo.max_current_ma, 3000)


# --- RDO Construction Tests ---


def test_build_fixed_rdo_position():
    """RDO position field is in bits 30:28."""
    rdo_bytes = build_fixed_rdo(3, 1000, 1000)
    dword = struct.unpack("<I", rdo_bytes)[0]
    pos = (dword >> 28) & 0x7
    assert_eq(pos, 3, "PDO position")


def test_build_fixed_rdo_currents():
    """RDO operating and max current fields."""
    rdo_bytes = build_fixed_rdo(1, 2500, 3000)
    dword = struct.unpack("<I", rdo_bytes)[0]
    op_current = ((dword >> 10) & 0x3FF) * 10  # 10mA LSB
    max_current = (dword & 0x3FF) * 10
    assert_eq(op_current, 2500, "operating current")
    assert_eq(max_current, 3000, "max current")


def test_build_pps_rdo_voltage():
    """PPS RDO voltage field (20mV resolution)."""
    rdo_bytes = build_pps_rdo(5, 12000, 3000)
    dword = struct.unpack("<I", rdo_bytes)[0]
    voltage = ((dword >> 9) & 0x7FF) * 20  # 20mV LSB
    assert_eq(voltage, 12000, "PPS voltage")


def test_build_pps_rdo_current():
    """PPS RDO current field (50mA resolution)."""
    rdo_bytes = build_pps_rdo(5, 12000, 3000)
    dword = struct.unpack("<I", rdo_bytes)[0]
    current = (dword & 0x7F) * 50  # 50mA LSB
    assert_eq(current, 3000, "PPS current")


def test_build_pps_rdo_position():
    rdo_bytes = build_pps_rdo(5, 5000, 1000)
    dword = struct.unpack("<I", rdo_bytes)[0]
    pos = (dword >> 28) & 0x7
    assert_eq(pos, 5, "PPS PDO position")


# --- AP33772 Class Tests ---


def test_read_pdos_default_charger():
    """Read PDOs from a typical 65W charger."""
    ap, dev = _make_ap33772()
    fixed, pps = ap.read_pdos()
    assert_eq(len(fixed), 4, "fixed PDO count")
    assert_eq(len(pps), 1, "PPS PDO count")
    assert_eq(fixed[0].voltage_mv, 5000)
    assert_eq(fixed[3].voltage_mv, 20000)
    assert_eq(pps[0].min_voltage_mv, 3300)
    assert_eq(pps[0].max_voltage_mv, 21000)


def test_read_pdos_no_pps():
    """Charger with only fixed PDOs (no PPS)."""
    pdos = [
        _make_fixed_pdo_bytes(5000, 3000),
        _make_fixed_pdo_bytes(9000, 2000),
        _make_fixed_pdo_bytes(12000, 1500),
    ]
    ap, dev = _make_ap33772(pdos)
    fixed, pps = ap.read_pdos()
    assert_eq(len(fixed), 3)
    assert_eq(len(pps), 0)
    assert_false(ap.has_pps)


def test_has_pps():
    ap, dev = _make_ap33772()
    ap.read_pdos()
    assert_true(ap.has_pps)


def test_read_status_ready():
    ap, dev = _make_ap33772()
    assert_true(ap.is_ready())


def test_read_status_new_pdo():
    ap, dev = _make_ap33772()
    dev.register_values[0x1D] = bytes([STATUS_READY | STATUS_NEW_PDO])
    assert_true(ap.has_new_pdo())


def test_check_protection_none():
    ap, dev = _make_ap33772()
    prot = ap.check_protection()
    assert_false(prot["ovp"])
    assert_false(prot["ocp"])
    assert_false(prot["otp"])


def test_check_protection_ocp():
    ap, dev = _make_ap33772()
    dev.register_values[0x1D] = bytes([STATUS_OCP])
    prot = ap.check_protection()
    assert_true(prot["ocp"])
    assert_false(prot["ovp"])


def test_read_voltage():
    ap, dev = _make_ap33772()
    # 12V = 12000mV / 80mV per LSB = 150
    dev.register_values[0x20] = bytes([150])
    assert_eq(ap.read_voltage_mv(), 12000)


def test_read_current():
    ap, dev = _make_ap33772()
    # 2.4A = 2400mA / 24mA per LSB = 100
    dev.register_values[0x21] = bytes([100])
    assert_eq(ap.read_current_ma(), 2400)


def test_read_temperature():
    ap, dev = _make_ap33772()
    dev.register_values[0x22] = bytes([42])
    assert_eq(ap.read_temperature(), 42)


# --- Voltage Selection Algorithm Tests ---


def test_select_voltage_pps_in_range():
    """When target is within PPS range, prefer PPS."""
    ap, dev = _make_ap33772()
    ap.read_pdos()
    pdo, voltage = ap.select_voltage(12000)
    assert_true(isinstance(pdo, PPSPDO), "should select PPS")
    assert_eq(voltage, 12000)


def test_select_voltage_pps_rounds_to_20mv():
    """PPS voltage should round down to 20mV steps."""
    ap, dev = _make_ap33772()
    ap.read_pdos()
    pdo, voltage = ap.select_voltage(12010)  # Not on 20mV boundary
    assert_true(isinstance(pdo, PPSPDO))
    assert_eq(voltage, 12000, "should round to 20mV step")


def test_select_voltage_exact_fixed():
    """When target exactly matches a fixed PDO and no PPS, use fixed."""
    pdos = [
        _make_fixed_pdo_bytes(5000, 3000),
        _make_fixed_pdo_bytes(9000, 3000),
        _make_fixed_pdo_bytes(20000, 3000),
    ]
    ap, dev = _make_ap33772(pdos)
    ap.read_pdos()
    pdo, voltage = ap.select_voltage(9000)
    assert_true(isinstance(pdo, FixedPDO))
    assert_eq(voltage, 9000)


def test_select_voltage_between_fixed():
    """Target between two fixed PDOs — pick lower one."""
    pdos = [
        _make_fixed_pdo_bytes(5000, 3000),
        _make_fixed_pdo_bytes(9000, 3000),
        _make_fixed_pdo_bytes(20000, 3000),
    ]
    ap, dev = _make_ap33772(pdos)
    ap.read_pdos()
    pdo, voltage = ap.select_voltage(12000)
    assert_true(isinstance(pdo, FixedPDO))
    assert_eq(voltage, 9000, "should pick 9V (closest below 12V)")


def test_select_voltage_below_all():
    """Target below lowest fixed PDO — no suitable PDO."""
    pdos = [
        _make_fixed_pdo_bytes(9000, 3000),
        _make_fixed_pdo_bytes(20000, 3000),
    ]
    ap, dev = _make_ap33772(pdos)
    ap.read_pdos()
    pdo, voltage = ap.select_voltage(5000)
    assert_eq(pdo, None, "no suitable PDO")
    assert_eq(voltage, 0)


def test_select_voltage_pps_extends_fixed():
    """PPS max exceeds best fixed PDO — prefer PPS."""
    pdos = [
        _make_fixed_pdo_bytes(5000, 3000),
        _make_fixed_pdo_bytes(9000, 3000),
        _make_pps_pdo_bytes(3300, 11000, 3000),  # PPS goes up to 11V
    ]
    ap, dev = _make_ap33772(pdos)
    ap.read_pdos()
    pdo, voltage = ap.select_voltage(10000)
    assert_true(isinstance(pdo, PPSPDO), "PPS should win over 9V fixed")
    assert_eq(voltage, 10000)


# --- Request Tests ---


def test_request_fixed_pdo():
    """Requesting a fixed PDO writes correct RDO to register."""
    ap, dev = _make_ap33772()
    ap.read_pdos()
    ap.request_fixed_pdo(ap.fixed_pdos[2])  # 15V 3A, index=3

    rdo_bytes = dev.register_values[0x30]
    dword = struct.unpack("<I", rdo_bytes)[0]
    pos = (dword >> 28) & 0x7
    assert_eq(pos, 3, "PDO position should be 3")


def test_request_pps_clamps_voltage():
    """PPS request clamps voltage to PDO range."""
    ap, dev = _make_ap33772()
    ap.read_pdos()
    pps = ap.pps_pdos[0]  # 3.3-21V

    # Request 25V — should clamp to 21V
    actual_v, actual_i = ap.request_pps(pps, 25000, 3000)
    assert_eq(actual_v, 21000, "clamped to max")

    # Request 1V — should clamp to 3.3V (rounded to 20mV = 3300)
    actual_v, actual_i = ap.request_pps(pps, 1000, 3000)
    assert_eq(actual_v, 3300, "clamped to min")


def test_request_pps_clamps_current():
    """PPS request clamps current to PDO max."""
    ap, dev = _make_ap33772()
    ap.read_pdos()
    pps = ap.pps_pdos[0]  # max 5A

    actual_v, actual_i = ap.request_pps(pps, 12000, 7000)
    assert_eq(actual_i, 5000, "clamped to max current")


def test_request_pps_rounds_to_steps():
    """PPS request rounds to 20mV voltage and 50mA current steps."""
    ap, dev = _make_ap33772()
    ap.read_pdos()
    pps = ap.pps_pdos[0]

    actual_v, actual_i = ap.request_pps(pps, 12010, 3030)
    assert_eq(actual_v, 12000, "voltage rounded to 20mV")
    assert_eq(actual_i, 3000, "current rounded to 50mA")


def test_reset_writes_zeros():
    """Reset sends all-zero RDO."""
    ap, dev = _make_ap33772()
    ap.reset()
    assert_bytes_eq(dev.register_values[0x30], bytes(4), "reset RDO")
